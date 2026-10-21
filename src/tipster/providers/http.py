"""Cliente HTTP de proveedores: caché, presupuesto, rate limit, reintentos y registro de créditos.

La clave del proveedor viaja en los parámetros de la petición, pero se elimina de todo lo que se
registra: parámetros, mensajes de error, base de datos y respuestas crudas guardadas.
"""

import hashlib
import json
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

import httpx

from tipster.errors import (
    ProviderAuthError,
    ProviderResponseError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from tipster.providers.base import RequestRecord, ResponseCache
from tipster.providers.budget import CreditBudget

QUOTA_EXHAUSTED_CODE = "OUT_OF_USAGE_CREDITS"  # The Odds API, documentado [B]
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class HttpPolicy:
    timeout_s: float = 20.0
    min_interval_s: float = 1.0  # provisional: el límite real del proveedor no está verificado
    max_retries: int = 3
    backoff_base_s: float = 1.0
    max_jitter_s: float = 0.5


@dataclass(frozen=True)
class HttpResult:
    data: object
    record: RequestRecord
    captured_at: datetime  # momento de la petición que trajo los datos (original si es caché)


class JsonFetcher(Protocol):
    """Lo que necesita un proveedor para pedir JSON: HttpClient en vivo u OfflineFetcher."""

    source: str  # origen que se guarda en cada cuota

    def get_json(
        self, endpoint: str, params: Mapping[str, str], *, estimated_cost: int
    ) -> HttpResult: ...


def params_key(params: Mapping[str, str]) -> str:
    """Parámetros ordenados en forma de query string (sin la clave)."""
    return urlencode(sorted(params.items()))


def _header_int(headers: httpx.Headers, name: str) -> int | None:
    value = headers.get(name)
    try:
        return None if value is None else int(float(value))
    except ValueError:
        return None


class HttpClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        secret_params: Mapping[str, str],
        policy: HttpPolicy,
        budget: CreditBudget,
        cache: ResponseCache | None,
        cache_ttl: timedelta,
        raw_dir: Path | None,
        clock: Callable[[], datetime],
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.provider = provider
        self.source = provider
        self._secrets = dict(secret_params)
        self._policy = policy
        self._budget = budget
        self._cache = cache
        self._cache_ttl = cache_ttl
        self._raw_dir = raw_dir
        self._clock = clock
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._last_request: float | None = None
        self._http = httpx.Client(base_url=base_url, timeout=policy.timeout_s, transport=transport)

    # -- utilidades -------------------------------------------------------------------------

    def _redact(self, text: str) -> str:
        for secret in self._secrets.values():
            if secret:
                text = text.replace(secret, "***")
        return text

    def _record(
        self, endpoint: str, key: str, requested_at: datetime, **fields: object
    ) -> RequestRecord:
        data: dict[str, object] = {
            "provider": self.provider,
            "endpoint": endpoint,
            "params_key": key,
            "http_status": None,
            "from_cache": False,
            "cost": None,
            "credits_used": None,
            "credits_remaining": None,
            "requested_at": requested_at,
            "duration_ms": None,
            "raw_path": None,
            "error": None,
        }
        data.update(fields)
        if isinstance(data["error"], str):
            data["error"] = self._redact(data["error"])
        return RequestRecord.model_validate(data)

    def _wait_rate_limit(self) -> None:
        if self._last_request is not None:
            elapsed = self._monotonic() - self._last_request
            if elapsed < self._policy.min_interval_s:
                self._sleep(self._policy.min_interval_s - elapsed)
        self._last_request = self._monotonic()

    def _backoff(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = _header_int(response.headers, "Retry-After")
            if retry_after is not None:
                return float(retry_after)
        return (
            self._policy.backoff_base_s * 2.0**attempt + self._jitter() * self._policy.max_jitter_s
        )

    def _save_raw(self, endpoint: str, key: str, requested_at: datetime, text: str) -> str | None:
        if self._raw_dir is None:
            return None
        folder = self._raw_dir / self.provider
        folder.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(f"{endpoint}?{key}".encode(), usedforsecurity=False).hexdigest()[:10]
        path = folder / f"{requested_at.strftime('%Y%m%dT%H%M%S%fZ')}_{digest}.json"
        path.write_text(self._redact(text), encoding="utf-8")
        return str(path)

    # -- API --------------------------------------------------------------------------------

    def get_json(
        self, endpoint: str, params: Mapping[str, str], *, estimated_cost: int
    ) -> HttpResult:
        key = params_key(params)
        now = self._clock()

        cached = self._from_cache(endpoint, key, now)
        if cached is not None:
            return cached

        self._budget.reserve(estimated_cost)
        response: httpx.Response | None = None
        error: str | None = None
        for attempt in range(self._policy.max_retries + 1):
            if attempt:
                self._sleep(self._backoff(attempt - 1, response))
            self._wait_rate_limit()
            requested_at = self._clock()
            started = self._monotonic()
            try:
                response = self._http.get(endpoint, params={**params, **self._secrets})
            except httpx.HTTPError as exc:
                response, error = None, f"{type(exc).__name__}: {exc}"
                continue
            duration = int((self._monotonic() - started) * 1000)
            if response.status_code in _RETRY_STATUSES and not self._quota_exhausted(response):
                error = f"HTTP {response.status_code}"
                continue
            return self._handle(
                endpoint,
                key,
                requested_at=requested_at,
                duration=duration,
                response=response,
                estimated_cost=estimated_cost,
            )

        record = self._record(
            endpoint,
            key,
            self._clock(),
            http_status=None if response is None else response.status_code,
            error=error,
        )
        if response is not None and response.status_code == 429:
            raise RateLimitedError(f"{self.provider}: 429 tras {attempt + 1} intentos", record)
        raise ProviderUnavailableError(
            f"{self.provider}: {record.error} tras {attempt + 1} intentos", record
        )

    def _from_cache(self, endpoint: str, key: str, now: datetime) -> HttpResult | None:
        if self._cache is None or self._cache_ttl <= timedelta(0):
            return None
        hit = self._cache.lookup(self.provider, endpoint, key, self._cache_ttl, now)
        if hit is None:
            return None
        try:
            data = json.loads(Path(hit.raw_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # respuesta cruda perdida o corrupta: se pide de nuevo
        record = self._record(
            endpoint, key, now, http_status=200, from_cache=True, cost=0, raw_path=hit.raw_path
        )
        return HttpResult(data=data, record=record, captured_at=hit.requested_at)

    @staticmethod
    def _quota_exhausted(response: httpx.Response) -> bool:
        return QUOTA_EXHAUSTED_CODE in response.text

    def _handle(
        self,
        endpoint: str,
        key: str,
        *,
        requested_at: datetime,
        duration: int,
        response: httpx.Response,
        estimated_cost: int,
    ) -> HttpResult:
        status = response.status_code
        cost = _header_int(response.headers, "x-requests-last")
        fields: dict[str, object] = {
            "http_status": status,
            "duration_ms": duration,
            "cost": cost,
            "credits_used": _header_int(response.headers, "x-requests-used"),
            "credits_remaining": _header_int(response.headers, "x-requests-remaining"),
        }
        if status >= 400:
            record = self._record(
                endpoint, key, requested_at, error=self._redact(response.text[:300]), **fields
            )
            if self._quota_exhausted(response):
                raise QuotaExhaustedError(f"{self.provider}: créditos agotados", record)
            if status in (401, 403):
                raise ProviderAuthError(
                    f"{self.provider}: credenciales rechazadas ({status})", record
                )
            raise ProviderResponseError(f"{self.provider}: respuesta {status}", record)

        # Sin cabecera de coste se cobra la estimación: mejor pasarse que quedarse corto.
        self._budget.charge(cost if cost is not None else estimated_cost)
        try:
            data = response.json()
        except ValueError as exc:
            record = self._record(endpoint, key, requested_at, error="JSON inválido", **fields)
            raise ProviderResponseError(f"{self.provider}: JSON inválido", record) from exc
        raw_path = self._save_raw(endpoint, key, requested_at, response.text)
        record = self._record(endpoint, key, requested_at, raw_path=raw_path, **fields)
        return HttpResult(data=data, record=record, captured_at=requested_at)

    def close(self) -> None:
        self._http.close()

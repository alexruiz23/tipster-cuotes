"""Cliente HTTP con transporte simulado: reintentos, errores, presupuesto, caché y clave oculta."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from tests.factories import NOW
from tipster.errors import (
    BudgetExceededError,
    ProviderAuthError,
    ProviderResponseError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from tipster.providers.base import CachedResponse
from tipster.providers.budget import CreditBudget
from tipster.providers.http import HttpClient, HttpPolicy

KEY = "clave-secreta-de-prueba-1234"
ENDPOINT = "/v4/sports/soccer_epl/odds"
PARAMS = {"markets": "h2h,totals", "bookmakers": "pinnacle"}
CREDIT_HEADERS = {"x-requests-last": "2", "x-requests-used": "12", "x-requests-remaining": "488"}

Handler = Callable[[httpx.Request], httpx.Response]


class FakeTime:
    def __init__(self) -> None:
        self.sleeps: list[float] = []
        self.mono = 100.0

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.mono += seconds

    def monotonic(self) -> float:
        return self.mono


class FakeCache:
    def __init__(self, hit: CachedResponse | None) -> None:
        self.hit = hit

    def lookup(
        self, provider: str, endpoint: str, params_key: str, max_age: timedelta, now: datetime
    ) -> CachedResponse | None:
        return self.hit


def _client(
    handler: Handler,
    tmp_path: Path,
    *,
    budget: CreditBudget | None = None,
    cache: FakeCache | None = None,
    time: FakeTime | None = None,
    calls: list[httpx.Request] | None = None,
) -> HttpClient:
    seen = calls if calls is not None else []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    fake = time or FakeTime()
    return HttpClient(
        provider="the_odds_api",
        base_url="https://api.example.test",
        secret_params={"apiKey": KEY},
        policy=HttpPolicy(min_interval_s=1.0, max_retries=3, backoff_base_s=1.0, max_jitter_s=0.5),
        budget=budget or CreditBudget(30),
        cache=cache,
        cache_ttl=timedelta(seconds=60),
        raw_dir=tmp_path / "raw",
        clock=lambda: NOW,
        sleep=fake.sleep,
        monotonic=fake.monotonic,
        jitter=lambda: 0.0,
        transport=httpx.MockTransport(recording),
    )


def _ok(body: object = ()) -> httpx.Response:
    return httpx.Response(
        200, json=list(body) if isinstance(body, tuple) else body, headers=CREDIT_HEADERS
    )


def test_peticion_correcta_registra_creditos_y_oculta_la_clave(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    client = _client(lambda r: _ok([{"id": "x"}]), tmp_path, calls=calls)
    result = client.get_json(ENDPOINT, PARAMS, estimated_cost=2)

    assert result.data == [{"id": "x"}]
    assert calls[0].url.params["apiKey"] == KEY  # la clave sí viaja al proveedor…
    record = result.record
    assert (record.http_status, record.cost, record.credits_used, record.credits_remaining) == (
        200,
        2,
        12,
        488,
    )
    assert record.params_key == "bookmakers=pinnacle&markets=h2h%2Ctotals"
    assert not record.from_cache
    assert result.captured_at == NOW
    # …pero nunca queda en el registro ni en la respuesta cruda guardada.
    assert KEY not in record.model_dump_json()
    assert record.raw_path is not None
    raw = Path(record.raw_path).read_text(encoding="utf-8")
    assert KEY not in raw
    assert json.loads(raw) == [{"id": "x"}]


def test_reintenta_5xx_con_backoff_y_acaba_bien(tmp_path: Path) -> None:
    responses = iter([httpx.Response(503), httpx.Response(502), _ok()])
    time = FakeTime()
    client = _client(lambda r: next(responses), tmp_path, time=time)
    assert client.get_json(ENDPOINT, PARAMS, estimated_cost=2).record.http_status == 200
    assert time.sleeps == [1.0, 2.0]


def test_respeta_retry_after(tmp_path: Path) -> None:
    responses = iter([httpx.Response(429, headers={"Retry-After": "5"}), _ok()])
    time = FakeTime()
    _client(lambda r: next(responses), tmp_path, time=time).get_json(
        ENDPOINT, PARAMS, estimated_cost=2
    )
    assert time.sleeps == [5.0]


def test_429_persistente_tras_los_reintentos(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    time = FakeTime()
    client = _client(lambda r: httpx.Response(429), tmp_path, time=time, calls=calls)
    with pytest.raises(RateLimitedError) as excinfo:
        client.get_json(ENDPOINT, PARAMS, estimated_cost=2)
    assert len(calls) == 4  # 1 intento + 3 reintentos
    assert time.sleeps == [1.0, 2.0, 4.0]
    assert excinfo.value.record is not None
    assert excinfo.value.record.http_status == 429


def test_5xx_persistente(tmp_path: Path) -> None:
    with pytest.raises(ProviderUnavailableError):
        _client(lambda r: httpx.Response(500), tmp_path).get_json(
            ENDPOINT, PARAMS, estimated_cost=2
        )


def test_error_de_red_persistente_sin_filtrar_la_clave(tmp_path: Path) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"fallo al conectar con {request.url}", request=request)

    with pytest.raises(ProviderUnavailableError) as excinfo:
        _client(fail, tmp_path).get_json(ENDPOINT, PARAMS, estimated_cost=2)
    assert KEY not in str(excinfo.value)
    assert excinfo.value.record is not None
    assert KEY not in excinfo.value.record.model_dump_json()


@pytest.mark.parametrize("status", [401, 403])
def test_credenciales_rechazadas_no_se_reintentan(status: int, tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    client = _client(lambda r: httpx.Response(status), tmp_path, calls=calls)
    with pytest.raises(ProviderAuthError):
        client.get_json(ENDPOINT, PARAMS, estimated_cost=2)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [401, 429])
def test_creditos_agotados_se_detectan_por_el_cuerpo(status: int, tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    body = {"message": "Usage quota has been reached", "error_code": "OUT_OF_USAGE_CREDITS"}
    client = _client(lambda r: httpx.Response(status, json=body), tmp_path, calls=calls)
    with pytest.raises(QuotaExhaustedError):
        client.get_json(ENDPOINT, PARAMS, estimated_cost=2)
    assert len(calls) == 1


def test_otro_4xx_no_se_reintenta(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    client = _client(lambda r: httpx.Response(422, json={"message": "x"}), tmp_path, calls=calls)
    with pytest.raises(ProviderResponseError):
        client.get_json(ENDPOINT, PARAMS, estimated_cost=2)
    assert len(calls) == 1


def test_json_invalido(tmp_path: Path) -> None:
    bad = httpx.Response(200, content=b"<html>no es json</html>", headers=CREDIT_HEADERS)
    with pytest.raises(ProviderResponseError):
        _client(lambda r: bad, tmp_path).get_json(ENDPOINT, PARAMS, estimated_cost=2)


def test_el_presupuesto_corta_antes_de_llamar(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    budget = CreditBudget(3)
    client = _client(lambda r: _ok(), tmp_path, budget=budget, calls=calls)
    client.get_json(ENDPOINT, PARAMS, estimated_cost=2)
    with pytest.raises(BudgetExceededError):
        client.get_json(ENDPOINT, {"markets": "h2h"}, estimated_cost=2)
    assert len(calls) == 1
    assert budget.spent == 2
    assert budget.remaining == 1


def test_acierto_de_cache_no_llama_ni_gasta_y_conserva_la_hora_original(tmp_path: Path) -> None:
    raw = tmp_path / "cached.json"
    raw.write_text('[{"id": "cacheado"}]', encoding="utf-8")
    original = NOW - timedelta(seconds=30)
    calls: list[httpx.Request] = []
    budget = CreditBudget(30)
    cache = FakeCache(CachedResponse(request_id=7, requested_at=original, raw_path=str(raw)))
    client = _client(lambda r: _ok(), tmp_path, budget=budget, cache=cache, calls=calls)
    result = client.get_json(ENDPOINT, PARAMS, estimated_cost=2)
    assert calls == []
    assert budget.spent == 0
    assert result.data == [{"id": "cacheado"}]
    assert result.captured_at == original
    assert (result.record.from_cache, result.record.cost, result.record.http_status) == (
        True,
        0,
        200,
    )


def test_intervalo_minimo_entre_peticiones(tmp_path: Path) -> None:
    time = FakeTime()
    client = _client(lambda r: _ok(), tmp_path, time=time)
    client.get_json(ENDPOINT, PARAMS, estimated_cost=1)
    time.mono += 0.25
    client.get_json(ENDPOINT, {"markets": "h2h"}, estimated_cost=1)
    assert time.sleeps == [pytest.approx(0.75)]

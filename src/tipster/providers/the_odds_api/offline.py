"""Respuestas grabadas de The Odds API para `tipster scan --offline DIR` (P2).

El directorio contiene `manifest.json` (origen, aviso y hora de captura), `sports.json` y un
`odds_<clave>.json` por competición. Todo se evalúa a la hora de captura del manifiesto: la
salida se marca «DATOS GRABADOS, NO EN VIVO».
"""

import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from tipster.domain.competitions import THE_ODDS_API
from tipster.domain.models import to_utc
from tipster.errors import ConfigError, ProviderUnavailableError
from tipster.providers.base import RequestRecord
from tipster.providers.http import HttpResult, params_key
from tipster.providers.the_odds_api.client import SPORTS_ENDPOINT

OFFLINE_SOURCE = f"{THE_ODDS_API}:offline"
_ODDS_ENDPOINT = re.compile(r"^/v4/sports/(?P<key>[a-z0-9_]+)/odds$")


class OfflineFetcher:
    source = OFFLINE_SOURCE

    def __init__(self, directory: Path) -> None:
        manifest_path = directory / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.captured_at: datetime = to_utc(datetime.fromisoformat(manifest["captured_at"]))
            self.origin: str = str(manifest["origen"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConfigError(
                f"{manifest_path}: falta o es inválido (necesita 'origen' y 'captured_at' con zona)"
            ) from exc
        if self.captured_at.tzinfo is None:
            raise ConfigError(f"{manifest_path}: 'captured_at' debe llevar zona horaria")
        self.notice: str = str(manifest.get("aviso", ""))
        self._directory = directory

    def _file_for(self, endpoint: str) -> Path | None:
        if endpoint == SPORTS_ENDPOINT:
            return self._directory / "sports.json"
        match = _ODDS_ENDPOINT.match(endpoint)
        return None if match is None else self._directory / f"odds_{match['key']}.json"

    def get_json(
        self, endpoint: str, params: Mapping[str, str], *, estimated_cost: int
    ) -> HttpResult:
        path = self._file_for(endpoint)
        record = RequestRecord(
            provider=THE_ODDS_API,
            endpoint=endpoint,
            params_key=params_key(params),
            http_status=None,  # no hubo petición HTTP: nunca sirve como caché
            from_cache=False,
            cost=0,
            credits_used=None,
            credits_remaining=None,
            requested_at=self.captured_at,
            duration_ms=None,
            raw_path=None if path is None else str(path),
        )
        if path is None or not path.exists():
            raise ProviderUnavailableError(
                f"No hay respuesta grabada para {endpoint} en {self._directory}", record
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return HttpResult(data=data, record=record, captured_at=self.captured_at)

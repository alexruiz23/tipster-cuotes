"""Resultados de The Odds API (`/scores`): estructura de la documentación, NO VERIFICADA con una
respuesta real (ADR 012). Datos inventados para tests."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tipster.errors import ProviderResponseError
from tipster.providers.budget import CreditBudget
from tipster.providers.http import HttpClient, HttpPolicy
from tipster.providers.the_odds_api.client import TheOddsApiProvider

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
PAYLOAD = [
    {
        "id": "a1", "sport_key": "soccer_epl", "completed": True,
        "home_team": "Local Prueba FC", "away_team": "Visitante Prueba CF",
        "scores": [
            {"name": "Local Prueba FC", "score": "2"},
            {"name": "Visitante Prueba CF", "score": "1"},
        ],
    },
    {
        "id": "a2", "sport_key": "soccer_epl", "completed": False,
        "home_team": "Ciudad Ficticia CF", "away_team": "Atlético Inventado", "scores": None,
    },
    {
        "id": "a3", "sport_key": "soccer_epl", "completed": True,
        "home_team": "Equipo Uno", "away_team": "Equipo Dos",
        "scores": [{"name": "Equipo Dos", "score": "0"}, {"name": "Equipo Uno", "score": "0"}],
    },
]  # fmt: skip


def _provider(payload: object, calls: list[httpx.Request]) -> TheOddsApiProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        headers = {"x-requests-last": "2", "x-requests-remaining": "480", "x-requests-used": "20"}
        return httpx.Response(200, content=json.dumps(payload).encode(), headers=headers)

    http = HttpClient(
        provider="the_odds_api",
        base_url="https://api.the-odds-api.com",
        secret_params={"apiKey": "clave-de-prueba"},  # gitleaks:allow (clave falsa de test)
        policy=HttpPolicy(min_interval_s=0),
        budget=CreditBudget(30),
        cache=None,
        cache_ttl=timedelta(0),
        raw_dir=None,
        clock=lambda: NOW,
        transport=httpx.MockTransport(handler),
    )
    return TheOddsApiProvider(http)


def test_parsea_resultados_completados_y_pendientes() -> None:
    calls: list[httpx.Request] = []
    batch = _provider(PAYLOAD, calls).fetch_scores("premier", days_from=1)
    by_id = {s.external_id: s for s in batch.scores}
    assert (by_id["a1"].completed, by_id["a1"].home_goals, by_id["a1"].away_goals) == (True, 2, 1)
    assert (by_id["a2"].completed, by_id["a2"].home_goals) == (False, None)
    # los marcadores se asignan por nombre de equipo, no por el orden de la lista
    assert (by_id["a3"].home_goals, by_id["a3"].away_goals) == (0, 0)
    assert calls[0].url.path == "/v4/sports/soccer_epl/scores"
    assert calls[0].url.params["daysFrom"] == "1"
    assert batch.request.cost == 2


def test_un_partido_completado_sin_marcador_valido_es_un_error() -> None:
    bad = [{**PAYLOAD[0], "scores": [{"name": "Local Prueba FC", "score": "2"}]}]
    with pytest.raises(ProviderResponseError, match="marcador"):
        _provider(bad, []).fetch_scores("premier", days_from=1)

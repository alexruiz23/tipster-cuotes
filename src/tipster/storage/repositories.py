"""Protocolos de repositorio. La implementación SQLite está en `sqlite.py`; una de PostgreSQL
implementaría los mismos protocolos (ADR 004)."""

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from tipster.domain.models import Event, OddsQuote, Pick
from tipster.providers.base import RequestRecord

RunStatus = Literal["ok", "parcial", "error"]


class EventRepository(Protocol):
    def upsert(self, event: Event, provider: str, external_id: str) -> None: ...

    def get(self, event_id: str) -> Event | None: ...


class OddsRepository(Protocol):
    def add_batch(self, request_id: int, quotes: Sequence[OddsQuote]) -> list[int]: ...

    def latest(self, event_id: str, market_id: str) -> list[OddsQuote]: ...


class PickRepository(Protocol):
    def add(self, run_id: int, picks: Sequence[Pick]) -> None: ...

    def for_run(self, run_id: int) -> list[Pick]: ...


class RunRepository(Protocol):
    def start(self, command: str, settings_snapshot: Mapping[str, object]) -> int: ...

    def record_request(self, run_id: int, record: RequestRecord) -> int: ...

    def finish(self, run_id: int, status: RunStatus) -> None: ...

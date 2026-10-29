"""CLI de tipster-cuotes (Typer): `scan` (Fase 1) e `ingest` (Fase 2)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from tipster import DISCLAIMER
from tipster.cli.render import disclaimer, offline_banner, render_scan
from tipster.config import Settings
from tipster.errors import ConfigError, IngestError
from tipster.history.hf_dataset import ATTRIBUTION, DATASET_REVISION, fetch_tables
from tipster.history.ingest import DEFAULT_ALIASES, ingest, load_aliases
from tipster.providers.base import OddsProvider
from tipster.providers.budget import CreditBudget
from tipster.providers.http import HttpClient, HttpPolicy
from tipster.providers.the_odds_api.client import BASE_URL, TheOddsApiProvider
from tipster.providers.the_odds_api.offline import OfflineFetcher
from tipster.services.scan import ScanService
from tipster.storage.db import MEMORY, connect
from tipster.storage.sqlite import (
    SqliteEventRepository,
    SqliteOddsRepository,
    SqlitePickRepository,
    SqliteResponseCache,
    SqliteRunRepository,
)

EXIT_RUN_ERROR = 1
EXIT_CONFIG = 2

app = typer.Typer(
    help=f"Tipster de fútbol que solo recomienda apuestas.\n\n{DISCLAIMER}",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root() -> None:
    """Tipster de fútbol que solo recomienda apuestas."""


def _settings(
    console: Console, max_creditos: int | None, competicion: list[str] | None
) -> Settings:
    overrides: dict[str, object] = {}
    if max_creditos is not None:
        overrides["max_credits_per_run"] = max_creditos
    if competicion:
        overrides["competitions"] = tuple(competicion)
    try:
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        console.print("[bold red]Configuración inválida:[/]")
        for error in exc.errors():
            console.print(f"  - {error['msg']}", markup=False)
        raise typer.Exit(EXIT_CONFIG) from exc


@app.command()
def scan(
    offline: Annotated[
        Path | None,
        typer.Option(
            "--offline",
            help="Directorio con respuestas grabadas: no llama a la red ni gasta créditos.",
            file_okay=False,
        ),
    ] = None,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Base de datos. Con --offline, por defecto en memoria."),
    ] = None,
    max_creditos: Annotated[
        int | None, typer.Option("--max-creditos", min=0, help="Presupuesto de esta ejecución.")
    ] = None,
    competicion: Annotated[
        list[str] | None, typer.Option("--competicion", help="Repetible; por defecto, todas.")
    ] = None,
) -> None:
    """Lee cuotas, calcula la probabilidad justa y muestra las oportunidades."""
    console = Console()
    disclaimer(console)
    settings = _settings(console, max_creditos, competicion)

    if offline is not None:
        try:
            fetcher = OfflineFetcher(offline)
        except ConfigError as exc:
            console.print(f"[bold red]{exc}[/]")
            raise typer.Exit(EXIT_CONFIG) from exc
        offline_banner(console, fetcher.origin, fetcher.captured_at, fetcher.notice)
        captured_at = fetcher.captured_at

        def clock() -> datetime:
            return captured_at

        conn = connect(db or MEMORY)
        provider: OddsProvider = TheOddsApiProvider(fetcher)
    else:
        if settings.odds_api_key is None:
            console.print(
                "[bold red]Falta ODDS_API_KEY.[/] Defínela en .env o en el entorno (ver "
                ".env.example), o usa --offline DIR para trabajar con datos grabados."
            )
            raise typer.Exit(EXIT_CONFIG)

        def clock() -> datetime:
            return datetime.now(UTC)

        conn = connect(db or settings.db_path)
        http = HttpClient(
            provider=TheOddsApiProvider.name,
            base_url=BASE_URL,
            secret_params={"apiKey": settings.odds_api_key.get_secret_value()},
            policy=HttpPolicy(min_interval_s=settings.min_request_interval_s),
            budget=CreditBudget(settings.max_credits_per_run),
            cache=SqliteResponseCache(conn),
            cache_ttl=timedelta(seconds=settings.cache_ttl_seconds),
            raw_dir=settings.raw_dir,
            clock=clock,
        )
        provider = TheOddsApiProvider(http)

    try:
        result = ScanService(
            provider=provider,
            events=SqliteEventRepository(conn, clock),
            odds=SqliteOddsRepository(conn),
            picks=SqlitePickRepository(conn),
            runs=SqliteRunRepository(conn, clock),
            settings=settings,
            clock=clock,
        ).run()
    finally:
        conn.close()
    render_scan(console, result, settings.timezone)
    if result.status == "error":
        raise typer.Exit(EXIT_RUN_ERROR)


def main() -> None:
    app()


@app.command("ingest")
def ingest_command(
    from_year: Annotated[
        int, typer.Option("--from", help="Primer año de temporada (desde el 1 de agosto).")
    ] = 2016,
    to_year: Annotated[
        int, typer.Option("--to", help="Último año de temporada (hasta el 31 de julio siguiente).")
    ] = 2025,
    db: Annotated[Path | None, typer.Option("--db", help="Base de datos.")] = None,
) -> None:
    """Descarga el histórico de Hugging Face y lo guarda en SQLite (idempotente)."""
    console = Console()
    settings = _settings(console, None, None)
    conn = connect(db or settings.db_path)
    try:
        fetched = fetch_tables(settings.raw_dir / "huggingface")
        for name, file in fetched.items():
            state = "descargado" if file.downloaded else "ya estaba"
            console.print(f"{name}.parquet {state} · sha256 {file.sha256[:16]}…", markup=False)
        result = ingest(
            conn,
            next(iter(fetched.values())).path.parent,
            date(from_year, 8, 1),
            date(to_year + 1, 7, 31),
            aliases=load_aliases(DEFAULT_ALIASES),
            clock=lambda: datetime.now(UTC),
        )
    except IngestError as exc:
        console.print(f"[bold red]{exc}[/]")
        raise typer.Exit(EXIT_RUN_ERROR) from exc
    finally:
        conn.close()
    pct = 100 * result.with_pinnacle / result.matches_loaded if result.matches_loaded else 0
    console.print(f"Partidos leídos: {result.matches_read}", markup=False)
    console.print(f"Duplicados eliminados: {result.duplicates_removed}", markup=False)
    console.print(f"Partidos cargados: {result.matches_loaded}", markup=False)
    console.print(
        f"Partidos con cuota de Pinnacle completa: {result.with_pinnacle} ({pct:.1f} %)",
        markup=False,
    )
    console.print(f"Años cubiertos: {result.first_date} a {result.last_date}", markup=False)
    for competition, count in result.per_competition.items():
        console.print(f"  {competition}: {count}", markup=False)
    console.print(f"Revisión del dataset: {DATASET_REVISION}", markup=False)
    console.print(ATTRIBUTION, markup=False)

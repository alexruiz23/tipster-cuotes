"""Salida de `tipster scan`: aviso, tabla de oportunidades y resumen. Solo escribe a stdout."""

from datetime import datetime
from zoneinfo import ZoneInfo

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tipster import DISCLAIMER
from tipster.domain.bookmakers import get_bookmaker
from tipster.domain.markets import SELECTION_LABELS, get_market
from tipster.domain.models import Opportunity
from tipster.pricing.classify import Label, format_age
from tipster.services.scan import ScanResult

NON_ES_TAG = "FEED NO-ES · VERIFICA LA CUOTA EN LA WEB .ES"  # D1
OFFLINE_TAG = "DATOS GRABADOS, NO EN VIVO"  # P2
_SHOWN = (Label.POSIBLE_ERROR, Label.VALUE, Label.REVISION_MANUAL)


def disclaimer(console: Console) -> None:
    console.print(Panel(DISCLAIMER, title="Aviso", border_style="yellow"))


def offline_banner(console: Console, origin: str, captured_at: datetime, notice: str) -> None:
    console.print(
        f"[bold red]{OFFLINE_TAG}[/] · origen: {origin} · evaluado a la hora de captura "
        f"{captured_at.isoformat()}"
    )
    if notice:
        console.print(f"[dim]{notice}[/]")


def _local(value: datetime, tz: ZoneInfo) -> str:
    return value.astimezone(tz).strftime("%d/%m %H:%M:%S")


def _row(o: Opportunity, now: datetime, tz: ZoneInfo) -> list[str]:
    bookmaker = get_bookmaker(o.quote.bookmaker_id)
    label = o.label.value if o.feed_es else f"{o.label.value}\n{NON_ES_TAG}"
    return [
        f"{o.event.name}\n{_local(o.event.kickoff, tz)}",
        get_market(o.quote.market_id).name,
        SELECTION_LABELS[o.quote.selection],
        f"{bookmaker.brand} ({bookmaker.jurisdiction})",
        f"{o.quote.price:.2f}",
        f"{o.fair_odds:.3f}",
        "—" if o.p_model is None else f"{o.p_model * 100:.1f} %",
        f"{o.p_market * 100:.1f} %",
        f"{o.ev * 100:+.2f} %",
        "—" if o.stake is None else f"{o.stake:.2f}",
        label,
        o.reference_bookmaker_id,
        f"{_local(o.quote.captured_at, tz)}\nlast_update hace {format_age(o.quote.age(now))}",
    ]


def render_scan(console: Console, result: ScanResult, timezone: str) -> None:
    tz = ZoneInfo(timezone)
    shown = sorted(
        (o for o in result.opportunities if o.label in _SHOWN), key=lambda o: o.ev, reverse=True
    )
    table = Table(title="Oportunidades", show_lines=True)
    for column in (
        "Partido",
        "Mercado",
        "Selección",
        "Casa",
        "Cuota",
        "Cuota justa",
        "p_modelo",
        "p_mercado",
        "EV",
        "Stake",
        "Etiqueta",
        "Ref.",
        "Captura",
    ):
        table.add_column(column, no_wrap=column == "Etiqueta")
    for opportunity in shown:
        table.add_row(*_row(opportunity, result.evaluated_at, tz))
    console.print(table)

    by_label = {label: sum(p.opportunity.label is label for p in result.picks) for label in _SHOWN}
    console.print(
        f"Evaluado a: {_local(result.evaluated_at, tz)} ({timezone}) · "
        f"devig: {result.devig_method.value}"
    )
    console.print(
        f"Picks: {len(result.picks)} (VALUE {by_label[Label.VALUE]} · "
        f"POSIBLE ERROR {by_label[Label.POSIBLE_ERROR]})"
    )
    if result.discards:
        parts = " · ".join(f"{reason} {n}" for reason, n in result.discards.most_common())
        console.print(f"Descartadas: {parts}")
    for c in result.competitions:
        extra = f"{c.events} partidos, {c.quotes} cuotas" if c.status == "ok" else c.detail
        console.print(f"  {c.competition_id}: {c.status} ({extra})")
    remaining = "—" if result.credits_remaining is None else str(result.credits_remaining)
    console.print(
        f"Créditos gastados: {result.credits_spent} · restantes según el proveedor: {remaining} · "
        f"peticiones: {result.requests} · desde caché: {result.cache_hits}"
    )
    console.print(
        "Todas las cuotas llevan «liquidez desconocida»: The Odds API no da liquidez ni límites."
    )
    if result.aborted:
        console.print(f"[bold red]Ejecución cortada:[/] {result.aborted}")
    if result.warnings:
        console.print(f"Avisos ({len(result.warnings)}):")
        for warning in result.warnings:
            console.print(f"  - {warning}", markup=False)
    console.print(f"Estado de la ejecución {result.run_id}: {result.status}")

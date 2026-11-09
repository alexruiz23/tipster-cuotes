"""`tipster notify`: texto de picks, liquidaciones y estado; envío simulado (sin red)."""

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from tests.integration.test_close_settle import NOW, FakeScores, _open, _settle
from tipster.cli import app as cli
from tipster.config import Settings
from tipster.providers.base import MatchScore
from tipster.services.notify import picks_text, settled_text
from tipster.storage.db import connect

TZ = ZoneInfo("Europe/Madrid")


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # sin .env a la vista
    path = tmp_path / "t.sqlite"
    conn = connect(path)
    _open(conn, "e2", minutes_to_kickoff=600, stake=0.0)
    # cada _open crea su propio scan: el último es el del pick con stake
    _open(conn, "e1", minutes_to_kickoff=600, stake=1.0, price=11.0)
    conn.commit()
    conn.close()
    return path


def _sent(monkeypatch: pytest.MonkeyPatch, ok: bool = True) -> list[tuple[str, str, str]]:
    sent: list[tuple[str, str, str]] = []

    def fake(text: str, *, token: str, chat_id: str) -> bool:
        sent.append((text, token, chat_id))
        return ok

    monkeypatch.setattr(cli, "send_message", fake)
    return sent


def test_picks_text_lista_solo_los_picks_con_stake(db: Path) -> None:
    conn = connect(db)
    text = picks_text(conn, TZ)
    assert text.startswith("Último scan: 1 picks con stake")
    assert "@ 11" in text and "stake 1.00 €" in text and "verifica la cuota" in text
    assert text.count("–") == 1  # un solo partido
    conn.close()


def test_picks_text_sin_scan_o_sin_stake() -> None:
    conn = connect(":memory:")
    assert picks_text(conn, TZ) == "Último scan: sin picks con stake."
    conn.close()


def test_settled_text_resume_los_liquidados_de_hoy(db: Path) -> None:
    conn = connect(db)
    _open(conn, "e3", minutes_to_kickoff=-180, stake=1.0, price=2.0)
    _settle(conn, FakeScores([MatchScore("xe3", True, 2, 1)]))
    bank = conn.execute("SELECT balance_after FROM bankroll_entries ORDER BY id DESC").fetchone()[0]
    text = settled_text(conn, TZ, NOW, bank)
    assert text is not None
    assert "Liquidados hoy: 1" in text and "GANADO" in text and "+1.00 €" in text
    assert "bankroll 1001.00" in text
    assert settled_text(conn, TZ, NOW.replace(day=NOW.day + 2), bank) is None
    conn.close()


def test_notify_envia_picks_y_estado_con_las_credenciales_del_entorno(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _sent(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100")
    result = CliRunner().invoke(cli.app, ["notify", "--picks", "--status", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert [(s[1], s[2]) for s in sent] == [("tok", "-100")] * 2
    assert sent[0][0].startswith("Último scan") and sent[1][0].startswith("PAPER TRADING")


def test_notify_settle_sin_liquidados_no_envia_nada(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _sent(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    result = CliRunner().invoke(cli.app, ["notify", "--settle", "--db", str(db)])
    assert result.exit_code == 0 and sent == []
    assert "Nada que enviar" in result.output


def test_notify_sin_token_falla_con_mensaje_claro(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _sent(monkeypatch)
    result = CliRunner().invoke(cli.app, ["notify", "--status", "--db", str(db)])
    assert result.exit_code == 2
    assert "TELEGRAM_BOT_TOKEN" in result.output and sent == []


def test_notify_sin_opciones_pide_que_enviar(db: Path) -> None:
    result = CliRunner().invoke(cli.app, ["notify", "--db", str(db)])
    assert result.exit_code == 2 and "--picks" in result.output


def test_notify_devuelve_error_si_el_envio_falla(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _sent(monkeypatch, ok=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    result = CliRunner().invoke(cli.app, ["notify", "--status", "--db", str(db)])
    assert result.exit_code == 1


def test_el_token_no_se_guarda_en_la_configuracion_de_las_ejecuciones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRETO")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    snap = Settings(_env_file=None).snapshot()
    assert "SECRETO" not in str(snap) and "123" not in str(snap)

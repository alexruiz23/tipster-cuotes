"""`send_message` con `httpx.post` simulado: nunca se llama a Telegram de verdad."""

import logging

import httpx
import pytest

from tipster.notifications import telegram


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_envia_json_a_la_url_del_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def post(url: str, *, json: dict[str, str], timeout: float) -> _Resp:
        calls.append((url, json))
        return _Resp(200)

    monkeypatch.setattr(httpx, "post", post)
    assert telegram.send_message("hola", token="T0KEN", chat_id="42") is True
    assert calls == [
        ("https://api.telegram.org/botT0KEN/sendMessage", {"chat_id": "42", "text": "hola"})
    ]


def test_recorta_mensajes_largos(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    def post(url: str, *, json: dict[str, str], timeout: float) -> _Resp:
        sent.append(json["text"])
        return _Resp(200)

    monkeypatch.setattr(httpx, "post", post)
    telegram.send_message("x" * 5000, token="t", chat_id="1")
    assert len(sent[0]) == telegram.MAX_LEN


def test_token_invalido_avisa_y_no_lanza(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(401))
    with caplog.at_level(logging.WARNING):
        assert telegram.send_message("hola", token="SECRETO", chat_id="1") is False
    assert "401" in caplog.text
    assert "SECRETO" not in caplog.text


def test_fallo_de_red_avisa_sin_filtrar_el_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*a: object, **k: object) -> _Resp:
        raise httpx.ConnectError("fallo en https://api.telegram.org/botSECRETO/sendMessage")

    monkeypatch.setattr(httpx, "post", boom)
    with caplog.at_level(logging.WARNING):
        assert telegram.send_message("hola", token="SECRETO", chat_id="1") is False
    assert "ConnectError" in caplog.text
    assert "SECRETO" not in caplog.text

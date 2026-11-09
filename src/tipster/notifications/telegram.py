"""Notificaciones salientes por Telegram. Solo envía; no hay bot interactivo ni webhooks."""

import logging

import httpx

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 4096  # límite de Telegram por mensaje
TIMEOUT_S = 10.0


def send_message(text: str, *, token: str, chat_id: str) -> bool:
    """Envía `text` al chat. Devuelve False (y avisa en el log) si falla; nunca lanza.

    Los errores de httpx incluyen la URL, que lleva el token: solo se registra su tipo.
    """
    if len(text) > MAX_LEN:
        text = text[: MAX_LEN - 1] + "…"
    try:
        response = httpx.post(
            API.format(token=token), json={"chat_id": chat_id, "text": text}, timeout=TIMEOUT_S
        )
    except httpx.HTTPError as exc:
        log.warning("Telegram: no se pudo enviar el mensaje (%s)", type(exc).__name__)
        return False
    if response.status_code != 200:
        log.warning(
            "Telegram: respuesta HTTP %s; revisa el token y el chat id", response.status_code
        )
        return False
    return True

"""Jerarquía de excepciones del proyecto. Todas heredan de `TipsterError`."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tipster.providers.base import RequestRecord


class TipsterError(Exception):
    """Error base de tipster-cuotes."""


class RegistryError(TipsterError):
    """Se pidió una competición, mercado o casa que no está en su registro."""


class ConfigError(TipsterError):
    """Configuración inválida o incompleta."""


class DevigError(TipsterError, ValueError):
    """Las cuotas no permiten obtener probabilidades válidas con el método pedido."""


class IngestError(TipsterError):
    """La ingesta del histórico encontró datos inconsistentes o un fichero alterado."""


class FitError(TipsterError):
    """El ajuste de un modelo no convergió o produjo parámetros inaceptables."""


class ProviderError(TipsterError):
    """Error base de un proveedor de cuotas. `record` describe la petición fallida, si la hubo."""

    def __init__(self, message: str, record: "RequestRecord | None" = None) -> None:
        super().__init__(message)
        self.record = record


class ProviderAuthError(ProviderError):
    """Credenciales del proveedor rechazadas (401/403). No se reintenta."""


class QuotaExhaustedError(ProviderError):
    """El proveedor indica que se agotaron los créditos (OUT_OF_USAGE_CREDITS). No se reintenta."""


class BudgetExceededError(ProviderError):
    """La petición superaría el presupuesto de créditos de la ejecución. No se llega a hacer."""


class RateLimitedError(ProviderError):
    """429 persistente tras agotar los reintentos."""


class ProviderUnavailableError(ProviderError):
    """Error de red, timeout o 5xx tras agotar los reintentos."""


class ProviderResponseError(ProviderError):
    """Respuesta inválida (JSON o esquema) u otro error 4xx."""

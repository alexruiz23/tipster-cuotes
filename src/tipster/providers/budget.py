"""Presupuesto de créditos por ejecución: se comprueba antes de cada petición."""

from tipster.errors import BudgetExceededError


class CreditBudget:
    def __init__(self, max_credits: int) -> None:
        if max_credits < 0:
            raise ValueError("El presupuesto no puede ser negativo")
        self.max_credits = max_credits
        self.spent = 0

    @property
    def remaining(self) -> int:
        return self.max_credits - self.spent

    def reserve(self, estimated: int) -> None:
        """Lanza BudgetExceededError si la petición estimada no cabe en lo que queda."""
        if estimated > self.remaining:
            raise BudgetExceededError(
                f"La petición costaría ~{estimated} créditos y quedan {self.remaining} de "
                f"{self.max_credits} en esta ejecución"
            )

    def charge(self, actual: int) -> None:
        self.spent += actual

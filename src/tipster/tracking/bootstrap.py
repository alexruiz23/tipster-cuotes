"""Intervalos con bootstrap por bloques (semanas): lo usan el backtest y el `status`.

Los picks de una misma semana comparten mercado, noticias y jornada; tratarlos como independientes
estrecha el intervalo. Se remuestrean semanas enteras, con semilla fija para que el informe no
cambie de una ejecución a otra con los mismos datos."""

import random
from collections.abc import Sequence

MIN_BLOCKS = 4  # con menos semanas el intervalo es pura apariencia: no se da
N_BOOT = 2000


def block_bootstrap_ci(
    blocks: Sequence[Sequence[float]],
    *,
    n_boot: int = N_BOOT,
    seed: int = 1,
    min_blocks: int = MIN_BLOCKS,
) -> tuple[float, float] | None:
    """Intervalo del 95 % de la media de todos los valores, remuestreando bloques enteros.

    None si hay menos de `min_blocks` bloques con datos."""
    blocks = [b for b in blocks if b]
    if len(blocks) < max(min_blocks, 2):
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [x for block in rng.choices(blocks, k=len(blocks)) for x in block]
        means.append(sum(sample) / len(sample))
    means.sort()
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]

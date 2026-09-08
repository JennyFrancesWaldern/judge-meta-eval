"""Seeded-run helper so pipeline runs are deterministic and reproducible."""
import random


def set_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass


def seeded(seed: int, fn: "Callable", *args, **kwargs):
    """Run fn under a fixed seed, restoring the prior random state afterward."""
    state = random.getstate()
    set_seed(seed)
    try:
        return fn(*args, **kwargs)
    finally:
        random.setstate(state)

import random

from src import seeding


def test_same_seed_same_sequence():
    seeding.set_seed(42)
    first = [random.random() for _ in range(5)]
    seeding.set_seed(42)
    second = [random.random() for _ in range(5)]
    assert first == second


def test_seeded_helper_is_reproducible():
    def draw():
        return random.random()

    a = seeding.seeded(7, draw)
    b = seeding.seeded(7, draw)
    assert a == b

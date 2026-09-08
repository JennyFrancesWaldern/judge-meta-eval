import pytest

from src import cache


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    yield


def test_roundtrip():
    cache.set("key1", {"a": 1})
    assert cache.get("key1") == {"a": 1}


def test_missing_key_returns_none():
    assert cache.get("does-not-exist") is None


def test_cached_decorator_avoids_recompute():
    calls = []

    @cache.cached
    def expensive(x):
        calls.append(x)
        return x * 2

    assert expensive(3) == 6
    assert expensive(3) == 6
    assert calls == [3]

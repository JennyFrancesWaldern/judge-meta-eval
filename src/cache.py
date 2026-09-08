"""Disk-backed cache for API responses, keyed by a hash of the request.

Cached responses are committed to cache/ so a reader can rerun the pipeline
without paying for API calls again.
"""
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


def _key_to_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def get(key: str) -> Any | None:
    path = _key_to_path(key)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def set(key: str, value: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _key_to_path(key)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def cached(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: cache fn's result under a key built from its arguments."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key = json.dumps(
            {"fn": fn.__name__, "args": args, "kwargs": kwargs},
            sort_keys=True,
            default=str,
        )
        hit = get(key)
        if hit is not None:
            return hit["value"]
        value = fn(*args, **kwargs)
        set(key, {"value": value})
        return value

    return wrapper

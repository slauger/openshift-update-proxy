"""Simple in-memory TTL cache shared by upstream lookups."""

import time
from typing import Any

from openshift_update_proxy.config import Config


def get(cfg: Config, key: str) -> Any:
    entry = cfg.cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def put(cfg: Config, key: str, value: Any, ttl: float) -> None:
    if ttl > 0:
        cfg.cache[key] = (time.monotonic() + ttl, value)

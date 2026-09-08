"""Update graph lookups against the Cincinnati API."""

import logging
from typing import cast

import requests

from openshift_update_proxy import cache
from openshift_update_proxy.config import Config

logger = logging.getLogger("openshift-update-proxy")


def fetch_version_payloads(cfg: Config, channel: str, arch: str) -> dict[str, str]:
    """Return a mapping of release version to payload digest for an update channel."""
    cache_key = f"graph;{channel};{arch}"
    cached = cache.get(cfg, cache_key)
    if cached is not None:
        return cast(dict[str, str], cached)

    logger.info("fetching update graph for channel %s (%s)", channel, arch)
    response = requests.get(
        f"{cfg.api_upstream}/upgrades_info/v1/graph",
        params={"channel": channel, "arch": arch},
        headers={"Accept": "application/json"},
        verify=cfg.ssl_verify,
        timeout=cfg.request_timeout,
    )
    response.raise_for_status()

    payloads = {}
    for node in response.json().get("nodes", []):
        version = node.get("version")
        payload = node.get("payload") or ""
        if version and ":" in payload:
            payloads[version] = payload.rsplit(":", 1)[-1]

    cache.put(cfg, cache_key, payloads, cfg.lifecycle_cache_ttl)
    return payloads

"""Supported OpenShift version lookups backed by the Red Hat product lifecycle API."""

import logging

import requests

from openshift_update_proxy import cache, graph
from openshift_update_proxy.catalog import version_key
from openshift_update_proxy.config import Config

logger = logging.getLogger("openshift-update-proxy")

PRODUCT_NAME = "OpenShift Container Platform"


def build_supported(cfg: Config, channel_prefix: str, arch: str) -> list[dict]:
    """Combine lifecycle and update graph data into one entry per supported minor."""
    entries = []
    for minor in fetch_supported_minors(cfg):
        channel = f"{channel_prefix}-{minor['version']}"
        entries.append(
            {
                "version": minor["version"],
                "support_phase": minor["support_phase"],
                "channel": channel,
                "latest_release": fetch_latest_release(cfg, channel, arch),
            }
        )
    return entries


def fetch_supported_minors(cfg: Config) -> list[dict]:
    """Return all 4.x minor versions that are not end-of-life, newest first."""
    cache_key = "lifecycle-minors"
    cached = cache.get(cfg, cache_key)
    if cached is not None:
        return list(cached)

    logger.info("fetching product lifecycle data from %s", cfg.lifecycle_upstream)
    response = requests.get(
        f"{cfg.lifecycle_upstream}/products",
        params={"name": PRODUCT_NAME},
        verify=cfg.ssl_verify,
        timeout=cfg.request_timeout,
    )
    response.raise_for_status()
    payload = response.json()

    minors = []
    for product in payload.get("data", []):
        # the API reports the product as "Red Hat OpenShift Container Platform"
        if PRODUCT_NAME not in (product.get("name") or ""):
            continue
        for version in product.get("versions", []):
            name = (version.get("name") or "").strip()
            phase = version.get("type") or ""
            if not name.startswith("4.") or phase.lower() == "end of life":
                continue
            minors.append({"version": name, "support_phase": phase})

    minors.sort(key=lambda minor: version_key(minor["version"]), reverse=True)
    cache.put(cfg, cache_key, minors, cfg.lifecycle_cache_ttl)
    return minors


def fetch_latest_release(cfg: Config, channel: str, arch: str) -> str | None:
    """Return the highest release version in the given update channel, if any."""
    versions = list(graph.fetch_version_payloads(cfg, channel, arch))
    if not versions:
        return None
    return max(versions, key=version_key)

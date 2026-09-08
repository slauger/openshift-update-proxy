"""Operator catalog lookups backed by the Red Hat Pyxis API (catalog.redhat.com)."""

import logging
import re
from typing import cast

import requests

from openshift_update_proxy import cache
from openshift_update_proxy.config import Config

logger = logging.getLogger("openshift-update-proxy")

# Pyxis identifiers (package, organization, channel, ocp_version) are plain
# tokens; anything else would allow injecting additional RSQL filter clauses
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

BUNDLE_INCLUDE = ",".join(
    (
        "data.channel_name",
        "data.csv_name",
        "data.version",
        "data.is_default_channel",
        "data.creation_date",
        "total",
        "page",
        "page_size",
    )
)

PAGE_SIZE = 500


def valid_identifier(value: str) -> bool:
    return bool(IDENTIFIER_PATTERN.match(value))


def fetch_bundles(
    cfg: Config,
    package: str,
    organization: str,
    channel: str | None = None,
    ocp_version: str | None = None,
    latest_only: bool = False,
) -> list[dict]:
    """Fetch all operator bundles matching the given filters, following pagination."""
    filters = [f"package=={package}", f"organization=={organization}"]
    if channel:
        filters.append(f"channel_name=={channel}")
    if ocp_version:
        filters.append(f"ocp_version=={ocp_version}")
    if latest_only:
        filters.append("latest_in_channel==true")

    cache_key = ";".join(filters)
    cached = cache.get(cfg, cache_key)
    if cached is not None:
        return cast(list[dict], cached)

    bundles: list[dict] = []
    page = 0
    while True:
        logger.info("fetching operator bundles from pyxis: %s (page %d)", cache_key, page)
        params: dict[str, str | int] = {
            "filter": ";".join(filters),
            "include": BUNDLE_INCLUDE,
            "page_size": PAGE_SIZE,
            "page": page,
        }
        response = requests.get(
            f"{cfg.catalog_upstream}/operators/bundles",
            params=params,
            verify=cfg.ssl_verify,
            timeout=cfg.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()

        data = payload.get("data", [])
        bundles.extend(data)

        total = payload.get("total", len(bundles))
        page += 1
        if not data or len(bundles) >= total:
            break

    cache.put(cfg, cache_key, bundles, cfg.catalog_cache_ttl)
    return bundles


def build_channels(bundles: list[dict]) -> tuple[str | None, list[dict]]:
    """Reduce latest-in-channel bundles to one entry per channel.

    Pyxis returns one record per (channel, ocp_version); keep the highest
    version seen for each channel.
    """
    channels: dict[str, dict] = {}
    default_channel = None

    for bundle in bundles:
        name = bundle.get("channel_name")
        version = bundle.get("version")
        if not name or not version:
            continue

        current = channels.get(name)
        if current is None or version_key(version) > version_key(current["latest_version"]):
            channels[name] = {
                "name": name,
                "latest_version": version,
                "latest_csv": bundle.get("csv_name"),
            }

        if bundle.get("is_default_channel"):
            default_channel = name

    return default_channel, sorted(channels.values(), key=lambda channel: channel["name"])


def build_releases(bundles: list[dict]) -> list[dict]:
    """Reduce bundles to the Renovate custom datasource format.

    Pyxis returns one record per (version, ocp_version); deduplicate by
    version and keep the earliest creation date as release timestamp.
    """
    releases: dict[str, dict] = {}

    for bundle in bundles:
        version = bundle.get("version")
        if not version:
            continue

        release = releases.setdefault(version, {"version": version})
        timestamp = bundle.get("creation_date")
        if timestamp and timestamp < release.get("releaseTimestamp", "~"):
            release["releaseTimestamp"] = timestamp

    return sorted(releases.values(), key=lambda release: version_key(release["version"]))


def version_key(version: str) -> tuple:
    """Sort key for version strings; numeric segments compare numerically."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.split(r"[.+-]", version)
        if part
    )

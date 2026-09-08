"""Configuration from environment variables."""

import os

TRUTHY = ("1", "true", "yes", "on")


class Config:
    def __init__(self) -> None:
        self.api_upstream = os.environ.get("API_UPSTREAM", "https://api.openshift.com/api/").rstrip(
            "/"
        )
        self.mirror_upstream = os.environ.get(
            "MIRROR_UPSTREAM", "https://mirror.openshift.com/pub/"
        ).rstrip("/")
        self.signature_upstream = os.environ.get(
            "SIGNATURE_UPSTREAM",
            "https://mirror.openshift.com/pub/openshift-v4/signatures/openshift/release/",
        ).rstrip("/")
        self.catalog_upstream = os.environ.get(
            "CATALOG_UPSTREAM", "https://catalog.redhat.com/api/containers/v1/"
        ).rstrip("/")
        self.catalog_cache_ttl = float(os.environ.get("CATALOG_CACHE_TTL", "600"))
        self.lifecycle_upstream = os.environ.get(
            "LIFECYCLE_UPSTREAM", "https://access.redhat.com/product-life-cycles/api/v1/"
        ).rstrip("/")
        self.lifecycle_cache_ttl = float(os.environ.get("LIFECYCLE_CACHE_TTL", "3600"))
        self.cache: dict[str, tuple[float, object]] = {}
        self.ssl_verify = os.environ.get("INSECURE_SKIP_TLS_VERIFY", "").lower() not in TRUTHY
        self.request_timeout = float(os.environ.get("REQUEST_TIMEOUT", "30"))
        self.listen_host = os.environ.get("LISTEN_HOST", "0.0.0.0")
        self.listen_port = int(os.environ.get("LISTEN_PORT", "5000"))

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
        self.ssl_verify = os.environ.get("INSECURE_SKIP_TLS_VERIFY", "").lower() not in TRUTHY
        self.request_timeout = float(os.environ.get("REQUEST_TIMEOUT", "30"))
        self.listen_host = os.environ.get("LISTEN_HOST", "0.0.0.0")
        self.listen_port = int(os.environ.get("LISTEN_PORT", "5000"))

"""Flask application serving as a forwarding proxy for OpenShift update resources."""

import base64
import logging
import re

import requests
from flask import Flask, Response, jsonify, request

from openshift_update_proxy import __version__
from openshift_update_proxy.config import Config

logger = logging.getLogger("openshift-update-proxy")

# hop-by-hop and encoding-related headers must not be copied to the client,
# as the payload is re-encoded by the WSGI server
EXCLUDED_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

DIGEST_PATTERN = re.compile(r"^(sha256[:=])?(?P<digest>[0-9a-f]{64})$")

CONFIGMAP_TEMPLATE = """apiVersion: v1
kind: ConfigMap
metadata:
  name: signature-sha256-{short_digest}
  namespace: openshift-config-managed
  labels:
    release.openshift.io/verification-signatures: ""
binaryData:
{binary_data}"""


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)
    app.config["proxy"] = config or Config()

    @app.route("/")
    def index() -> Response:
        return jsonify(
            {
                "name": "openshift-update-proxy",
                "version": __version__,
                "endpoints": ["/api/", "/pub/", "/signatures/", "/configmaps/", "/healthz"],
            }
        )

    @app.route("/healthz")
    def healthz() -> Response:
        return jsonify({"status": "ok"})

    @app.route("/api/<path:path>")
    def api_proxy(path: str) -> Response:
        cfg = app.config["proxy"]
        return _forward(cfg, f"{cfg.api_upstream}/{path}", params=request.args)

    @app.route("/pub/<path:path>")
    def mirror_proxy(path: str) -> Response:
        cfg = app.config["proxy"]
        return _forward(cfg, f"{cfg.mirror_upstream}/{path}")

    @app.route("/signatures/<path:path>")
    def signature_proxy(path: str) -> Response:
        cfg = app.config["proxy"]
        return _forward(cfg, f"{cfg.signature_upstream}/{path}")

    @app.route("/configmaps/<digest>")
    def signature_configmap(digest: str) -> Response:
        cfg = app.config["proxy"]

        match = DIGEST_PATTERN.match(digest)
        if not match:
            return Response(
                "invalid digest, expected sha256=<64 hex chars>\n",
                status=400,
                mimetype="text/plain",
            )

        signatures = _fetch_signatures(cfg, match.group("digest"))
        if not signatures:
            return Response("no signatures found for digest\n", status=404, mimetype="text/plain")

        return Response(
            _render_configmap(match.group("digest"), signatures),
            mimetype="application/yaml",
        )

    return app


def _forward(cfg: Config, url: str, params: dict | None = None) -> Response:
    logger.info("forwarding request from source %s to upstream %s", request.remote_addr, url)

    upstream = requests.get(
        url,
        params=params,
        verify=cfg.ssl_verify,
        timeout=cfg.request_timeout,
    )

    headers = {
        key: value for key, value in upstream.headers.items() if key.lower() not in EXCLUDED_HEADERS
    }

    return Response(upstream.content, status=upstream.status_code, headers=headers)


def _fetch_signatures(cfg: Config, digest: str, limit: int = 10) -> list[bytes]:
    signatures = []

    for index in range(1, limit + 1):
        url = f"{cfg.signature_upstream}/sha256={digest}/signature-{index}"
        response = requests.get(url, verify=cfg.ssl_verify, timeout=cfg.request_timeout)

        if response.status_code != 200:
            break

        signatures.append(response.content)

    return signatures


def _render_configmap(digest: str, signatures: list[bytes]) -> str:
    binary_data = "\n".join(
        f"  sha256-{digest}-{index}: {base64.b64encode(signature).decode('ascii')}"
        for index, signature in enumerate(signatures, start=1)
    )

    return CONFIGMAP_TEMPLATE.format(short_digest=digest[:16], binary_data=binary_data)

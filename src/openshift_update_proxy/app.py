"""Flask application serving as a forwarding proxy for OpenShift update resources."""

import base64
import logging
import re

import requests
from flask import Flask, Response, jsonify, request

from openshift_update_proxy import __version__, catalog, graph, lifecycle
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

VERSION_PATTERN = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.\d+[A-Za-z0-9.+-]*$")

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
                "endpoints": [
                    "/api/",
                    "/pub/",
                    "/signatures/",
                    "/configmaps/",
                    "/catalog/",
                    "/operators/",
                    "/lifecycle/",
                    "/versions/",
                    "/healthz",
                ],
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

    @app.route("/catalog/<path:path>")
    def catalog_proxy(path: str) -> Response:
        cfg = app.config["proxy"]
        return _forward(cfg, f"{cfg.catalog_upstream}/{path}", params=request.args)

    @app.route("/lifecycle/<path:path>")
    def lifecycle_proxy(path: str) -> Response:
        cfg = app.config["proxy"]
        return _forward(cfg, f"{cfg.lifecycle_upstream}/{path}", params=request.args)

    @app.route("/versions/v1/supported")
    def supported_versions() -> Response:
        cfg = app.config["proxy"]

        channel_prefix = request.args.get("channel_prefix", "stable")
        arch = request.args.get("arch", "amd64")

        error = _validate_identifiers(channel_prefix, arch)
        if error:
            return error

        try:
            versions = lifecycle.build_supported(cfg, channel_prefix, arch)
        except requests.RequestException as exc:
            return _upstream_error(exc)

        return jsonify(
            {
                "product": lifecycle.PRODUCT_NAME,
                "architecture": arch,
                "versions": versions,
            }
        )

    @app.route("/operators/v1/<organization>/<package>/channels")
    def operator_channels(organization: str, package: str) -> Response:
        cfg = app.config["proxy"]

        error = _validate_identifiers(organization, package)
        if error:
            return error

        try:
            bundles = catalog.fetch_bundles(
                cfg,
                package,
                organization,
                ocp_version=request.args.get("ocp_version"),
                latest_only=True,
            )
        except requests.RequestException as exc:
            return _upstream_error(exc)

        if not bundles:
            return Response(
                "no bundles found for package/organization\n",
                status=404,
                mimetype="text/plain",
            )

        default_channel, channels = catalog.build_channels(bundles)
        return jsonify(
            {
                "package": package,
                "organization": organization,
                "default_channel": default_channel,
                "channels": channels,
            }
        )

    @app.route("/operators/v1/<organization>/<package>/<channel>/releases")
    def operator_releases(organization: str, package: str, channel: str) -> Response:
        cfg = app.config["proxy"]

        error = _validate_identifiers(organization, package, channel)
        if error:
            return error

        try:
            bundles = catalog.fetch_bundles(
                cfg,
                package,
                organization,
                channel=channel,
                ocp_version=request.args.get("ocp_version"),
            )
        except requests.RequestException as exc:
            return _upstream_error(exc)

        if not bundles:
            return Response(
                "no bundles found for package/organization/channel\n",
                status=404,
                mimetype="text/plain",
            )

        return jsonify({"releases": catalog.build_releases(bundles)})

    @app.route("/configmaps/<ref>")
    def signature_configmap(ref: str) -> Response:
        cfg = app.config["proxy"]

        digest_match = DIGEST_PATTERN.match(ref)
        version_match = VERSION_PATTERN.match(ref)

        if digest_match:
            digest = digest_match.group("digest")
        elif version_match:
            arch = request.args.get("arch", "amd64")
            channel_prefix = request.args.get("channel_prefix", "stable")

            error = _validate_identifiers(arch, channel_prefix)
            if error:
                return error

            channel = (
                f"{channel_prefix}-{version_match.group('major')}.{version_match.group('minor')}"
            )
            try:
                payloads = graph.fetch_version_payloads(cfg, channel, arch)
            except requests.RequestException as exc:
                return _upstream_error(exc)

            found = payloads.get(ref)
            if not found:
                return Response(
                    f"version {ref} not found in channel {channel} ({arch})\n",
                    status=404,
                    mimetype="text/plain",
                )
            digest = found
        else:
            return Response(
                "invalid reference, expected sha256=<64 hex chars> or a release version"
                " like 4.16.8\n",
                status=400,
                mimetype="text/plain",
            )

        signatures = _fetch_signatures(cfg, digest)
        if not signatures:
            return Response("no signatures found for digest\n", status=404, mimetype="text/plain")

        return Response(_render_configmap(digest, signatures), mimetype="application/yaml")

    return app


def _validate_identifiers(*values: str) -> Response | None:
    candidates = list(values)
    ocp_version = request.args.get("ocp_version")
    if ocp_version:
        candidates.append(ocp_version)

    for value in candidates:
        if not catalog.valid_identifier(value):
            return Response(
                f"invalid identifier: {value}\n",
                status=400,
                mimetype="text/plain",
            )
    return None


def _upstream_error(exc: requests.RequestException) -> Response:
    logger.warning("upstream request failed: %s", exc)
    return Response(
        "upstream request failed\n",
        status=502,
        mimetype="text/plain",
    )


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

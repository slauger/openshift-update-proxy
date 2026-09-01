import base64

from conftest import FakeResponse

import openshift_update_proxy.app as app_module

DIGEST = "a" * 64


def test_index(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json["name"] == "openshift-update-proxy"


def test_healthz(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_api_proxy_forwards_url_and_params(client, monkeypatch):
    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(b'{"nodes": []}', headers={"Content-Type": "application/json"})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    response = client.get("/api/upgrades_info/v1/graph?channel=stable-4.16&arch=amd64")

    assert response.status_code == 200
    assert captured["url"] == "https://api.openshift.com/api/upgrades_info/v1/graph"
    assert captured["params"]["channel"] == "stable-4.16"
    assert captured["params"]["arch"] == "amd64"
    assert response.content_type == "application/json"


def test_api_proxy_preserves_upstream_status(client, monkeypatch):
    monkeypatch.setattr(
        app_module.requests, "get", lambda *a, **kw: FakeResponse(b"not found", 404)
    )

    response = client.get("/api/does/not/exist")

    assert response.status_code == 404
    assert response.data == b"not found"


def test_mirror_proxy_forwards_binary_content(client, monkeypatch):
    payload = bytes(range(256))
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return FakeResponse(payload, headers={"Content-Type": "application/octet-stream"})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    response = client.get("/pub/openshift-v4/clients/ocp/latest/sha256sum.txt")

    assert response.status_code == 200
    assert captured["url"] == (
        "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/latest/sha256sum.txt"
    )
    assert response.data == payload


def test_signature_proxy(client, monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return FakeResponse(b"signature-blob")

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    response = client.get(f"/signatures/sha256={DIGEST}/signature-1")

    assert response.status_code == 200
    assert captured["url"] == (
        "https://mirror.openshift.com/pub/openshift-v4/signatures/openshift/release/"
        f"sha256={DIGEST}/signature-1"
    )
    assert response.data == b"signature-blob"


def test_configmap_rejects_invalid_digest(client):
    response = client.get("/configmaps/not-a-digest")

    assert response.status_code == 400


def test_configmap_returns_404_without_signatures(client, monkeypatch):
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **kw: FakeResponse(b"", 404))

    response = client.get(f"/configmaps/sha256={DIGEST}")

    assert response.status_code == 404


def test_configmap_renders_all_signatures(client, monkeypatch):
    signatures = {
        f"sha256={DIGEST}/signature-1": b"first",
        f"sha256={DIGEST}/signature-2": b"second",
    }

    def fake_get(url, **kwargs):
        for suffix, content in signatures.items():
            if url.endswith(suffix):
                return FakeResponse(content)
        return FakeResponse(b"", 404)

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    response = client.get(f"/configmaps/sha256={DIGEST}")

    assert response.status_code == 200
    body = response.data.decode()
    assert f"name: signature-sha256-{DIGEST[:16]}" in body
    assert "namespace: openshift-config-managed" in body
    assert 'release.openshift.io/verification-signatures: ""' in body
    assert f"sha256-{DIGEST}-1: {base64.b64encode(b'first').decode()}" in body
    assert f"sha256-{DIGEST}-2: {base64.b64encode(b'second').decode()}" in body


def test_configmap_accepts_bare_digest(client, monkeypatch):
    def fake_get(url, **kwargs):
        if url.endswith("signature-1"):
            return FakeResponse(b"sig")
        return FakeResponse(b"", 404)

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    response = client.get(f"/configmaps/{DIGEST}")

    assert response.status_code == 200


def test_ssl_verify_enabled_by_default(config):
    assert config.ssl_verify is True


def test_ssl_verify_disabled_via_env(monkeypatch):
    from openshift_update_proxy.config import Config

    monkeypatch.setenv("INSECURE_SKIP_TLS_VERIFY", "true")

    assert Config().ssl_verify is False

import requests
from conftest import FakeResponse

import openshift_update_proxy.app as app_module
import openshift_update_proxy.catalog as catalog_module
from openshift_update_proxy.catalog import build_releases, version_key


def bundle(channel, version, csv=None, default=False, created="2026-01-01T00:00:00+00:00"):
    return {
        "channel_name": channel,
        "version": version,
        "csv_name": csv or f"some-operator.v{version}",
        "is_default_channel": default,
        "creation_date": created,
    }


def test_catalog_proxy_forwards_url_and_params(client, monkeypatch):
    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(b'{"data": []}', headers={"Content-Type": "application/json"})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    response = client.get("/catalog/operators/indices?filter=organization==redhat-operators")

    assert response.status_code == 200
    assert captured["url"] == "https://catalog.redhat.com/api/containers/v1/operators/indices"
    assert captured["params"]["filter"] == "organization==redhat-operators"


def test_channels_deduplicates_and_reports_default(client, monkeypatch):
    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["filter"] = params["filter"]
        return FakeResponse(
            json_data={
                "data": [
                    bundle("stable-6.1", "6.1.9"),
                    bundle("stable-6.2", "6.2.2", default=True),
                    bundle("stable-6.2", "6.2.12", default=True),
                ],
                "total": 3,
                "page": 0,
                "page_size": 500,
            }
        )

    monkeypatch.setattr(catalog_module.requests, "get", fake_get)

    response = client.get("/operators/v1/redhat-operators/cluster-logging/channels")

    assert response.status_code == 200
    assert captured["url"].endswith("/operators/bundles")
    assert "package==cluster-logging" in captured["filter"]
    assert "organization==redhat-operators" in captured["filter"]
    assert "latest_in_channel==true" in captured["filter"]
    assert response.json["default_channel"] == "stable-6.2"
    assert response.json["channels"] == [
        {"name": "stable-6.1", "latest_version": "6.1.9", "latest_csv": "some-operator.v6.1.9"},
        {"name": "stable-6.2", "latest_version": "6.2.12", "latest_csv": "some-operator.v6.2.12"},
    ]


def test_channels_passes_ocp_version_filter(client, monkeypatch):
    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["filter"] = params["filter"]
        return FakeResponse(json_data={"data": [bundle("stable", "1.0.0")], "total": 1})

    monkeypatch.setattr(catalog_module.requests, "get", fake_get)

    response = client.get(
        "/operators/v1/redhat-operators/cluster-logging/channels?ocp_version=4.16"
    )

    assert response.status_code == 200
    assert "ocp_version==4.16" in captured["filter"]


def test_releases_renders_renovate_format(client, monkeypatch):
    def fake_get(url, params=None, **kwargs):
        return FakeResponse(
            json_data={
                "data": [
                    bundle("stable", "1.10.0", created="2026-02-01T00:00:00+00:00"),
                    bundle("stable", "1.9.1", created="2026-01-01T00:00:00+00:00"),
                    bundle("stable", "1.10.0", created="2026-01-15T00:00:00+00:00"),
                ],
                "total": 3,
            }
        )

    monkeypatch.setattr(catalog_module.requests, "get", fake_get)

    response = client.get("/operators/v1/redhat-operators/some-operator/stable/releases")

    assert response.status_code == 200
    assert response.json == {
        "releases": [
            {"version": "1.9.1", "releaseTimestamp": "2026-01-01T00:00:00+00:00"},
            {"version": "1.10.0", "releaseTimestamp": "2026-01-15T00:00:00+00:00"},
        ]
    }


def test_releases_follows_pagination(client, monkeypatch):
    pages = [
        {"data": [bundle("stable", "1.0.0")], "total": 2, "page": 0, "page_size": 1},
        {"data": [bundle("stable", "1.1.0")], "total": 2, "page": 1, "page_size": 1},
    ]
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append(params["page"])
        return FakeResponse(json_data=pages[params["page"]])

    monkeypatch.setattr(catalog_module.requests, "get", fake_get)

    response = client.get("/operators/v1/redhat-operators/some-operator/stable/releases")

    assert response.status_code == 200
    assert calls == [0, 1]
    assert [release["version"] for release in response.json["releases"]] == ["1.0.0", "1.1.0"]


def test_releases_are_cached(client, monkeypatch):
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append(url)
        return FakeResponse(json_data={"data": [bundle("stable", "1.0.0")], "total": 1})

    monkeypatch.setattr(catalog_module.requests, "get", fake_get)

    client.get("/operators/v1/redhat-operators/some-operator/stable/releases")
    client.get("/operators/v1/redhat-operators/some-operator/stable/releases")

    assert len(calls) == 1


def test_releases_returns_404_for_unknown_package(client, monkeypatch):
    monkeypatch.setattr(
        catalog_module.requests,
        "get",
        lambda *a, **kw: FakeResponse(json_data={"data": [], "total": 0}),
    )

    response = client.get("/operators/v1/redhat-operators/does-not-exist/stable/releases")

    assert response.status_code == 404


def test_releases_returns_502_on_upstream_error(client, monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.ConnectionError("upstream down")

    monkeypatch.setattr(catalog_module.requests, "get", fake_get)

    response = client.get("/operators/v1/redhat-operators/some-operator/stable/releases")

    assert response.status_code == 502


def test_releases_rejects_invalid_identifiers(client):
    response = client.get("/operators/v1/redhat-operators/pkg;evil==true/stable/releases")

    assert response.status_code == 400


def test_channels_rejects_invalid_ocp_version(client):
    response = client.get(
        "/operators/v1/redhat-operators/cluster-logging/channels?ocp_version=4.16;x==y"
    )

    assert response.status_code == 400


def test_version_key_sorts_numerically():
    versions = ["6.2.12", "6.2.2", "6.10.0", "6.2.2-1"]

    assert sorted(versions, key=version_key) == ["6.2.2", "6.2.2-1", "6.2.12", "6.10.0"]


def test_build_releases_skips_bundles_without_version():
    releases = build_releases([{"channel_name": "stable"}, bundle("stable", "1.0.0")])

    assert [release["version"] for release in releases] == ["1.0.0"]

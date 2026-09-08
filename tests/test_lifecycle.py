import requests
from conftest import FakeResponse

import openshift_update_proxy.app as app_module
import openshift_update_proxy.graph as graph_module
import openshift_update_proxy.lifecycle as lifecycle_module

LIFECYCLE_PAYLOAD = {
    "data": [
        {
            "name": "Red Hat OpenShift Container Platform",
            "versions": [
                {"name": "4.22", "type": "Full Support"},
                {"name": "4.20", "type": "Maintenance Support"},
                {"name": "4.17", "type": "End of life"},
                {"name": "3.11", "type": "Full Support"},
            ],
        }
    ]
}


def graph_payload(versions):
    return {
        "nodes": [
            {"version": version, "payload": f"quay.io/x/release@sha256:{'0' * 64}"}
            for version in versions
        ]
    }


def patch_upstreams(monkeypatch, fake_get):
    monkeypatch.setattr(lifecycle_module.requests, "get", fake_get)
    monkeypatch.setattr(graph_module.requests, "get", fake_get)


def fake_upstreams(graphs, calls=None):
    def fake_get(url, params=None, **kwargs):
        if calls is not None:
            calls.append((url, params))
        if "product-life-cycles" in url:
            return FakeResponse(json_data=LIFECYCLE_PAYLOAD)
        channel = params["channel"]
        return FakeResponse(json_data=graph_payload(graphs.get(channel, [])))

    return fake_get


def test_lifecycle_proxy_forwards_url_and_params(client, monkeypatch):
    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(b'{"data": []}', headers={"Content-Type": "application/json"})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    response = client.get("/lifecycle/products?name=OpenShift+Container+Platform")

    assert response.status_code == 200
    assert captured["url"] == "https://access.redhat.com/product-life-cycles/api/v1/products"
    assert captured["params"]["name"] == "OpenShift Container Platform"


def test_supported_versions_filters_and_sorts(client, monkeypatch):
    graphs = {
        "stable-4.22": ["4.22.2", "4.22.10", "4.22.9"],
        "stable-4.20": ["4.20.5"],
    }
    patch_upstreams(monkeypatch, fake_upstreams(graphs))

    response = client.get("/versions/v1/supported")

    assert response.status_code == 200
    assert response.json["product"] == "OpenShift Container Platform"
    assert response.json["architecture"] == "amd64"
    assert response.json["versions"] == [
        {
            "version": "4.22",
            "support_phase": "Full Support",
            "channel": "stable-4.22",
            "latest_release": "4.22.10",
        },
        {
            "version": "4.20",
            "support_phase": "Maintenance Support",
            "channel": "stable-4.20",
            "latest_release": "4.20.5",
        },
    ]


def test_supported_versions_reports_empty_channel_as_null(client, monkeypatch):
    graphs = {"stable-4.22": ["4.22.1"]}
    patch_upstreams(monkeypatch, fake_upstreams(graphs))

    response = client.get("/versions/v1/supported")

    assert response.status_code == 200
    latest = {v["version"]: v["latest_release"] for v in response.json["versions"]}
    assert latest == {"4.22": "4.22.1", "4.20": None}


def test_supported_versions_honors_channel_prefix_and_arch(client, monkeypatch):
    calls = []
    patch_upstreams(monkeypatch, fake_upstreams({}, calls))

    response = client.get("/versions/v1/supported?channel_prefix=eus&arch=arm64")

    assert response.status_code == 200
    graph_calls = [params for url, params in calls if "upgrades_info" in url]
    assert {params["channel"] for params in graph_calls} == {"eus-4.22", "eus-4.20"}
    assert {params["arch"] for params in graph_calls} == {"arm64"}


def test_supported_versions_uses_cache(client, monkeypatch):
    calls = []
    graphs = {"stable-4.22": ["4.22.1"], "stable-4.20": ["4.20.1"]}
    patch_upstreams(monkeypatch, fake_upstreams(graphs, calls))

    client.get("/versions/v1/supported")
    client.get("/versions/v1/supported")

    lifecycle_calls = [url for url, params in calls if "product-life-cycles" in url]
    graph_calls = [url for url, params in calls if "upgrades_info" in url]
    assert len(lifecycle_calls) == 1
    assert len(graph_calls) == 2


def test_supported_versions_rejects_invalid_prefix(client):
    response = client.get("/versions/v1/supported?channel_prefix=stable;x==y")

    assert response.status_code == 400


def test_supported_versions_returns_502_on_upstream_error(client, monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.ConnectionError("upstream down")

    patch_upstreams(monkeypatch, fake_get)

    response = client.get("/versions/v1/supported")

    assert response.status_code == 502

import json

import pytest
import requests

from openshift_update_proxy.app import create_app
from openshift_update_proxy.config import Config


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def client(config):
    app = create_app(config)
    app.testing = True
    return app.test_client()


class FakeResponse:
    def __init__(self, content=b"", status_code=200, headers=None, json_data=None):
        if json_data is not None:
            content = json.dumps(json_data).encode()
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

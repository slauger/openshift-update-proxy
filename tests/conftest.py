import pytest

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
    def __init__(self, content=b"", status_code=200, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

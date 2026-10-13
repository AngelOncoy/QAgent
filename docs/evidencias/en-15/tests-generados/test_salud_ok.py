import pytest
from fastapi.testclient import TestClient

from api_mvp import app


@pytest.fixture
def client():
    overrides_anteriores = dict(app.dependency_overrides)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides_anteriores)


def test_salud_ok(client):
    response = client.request("GET", "/salud")
    assert response.status_code == 200
    assert response.json() == {"estado": "ok"}

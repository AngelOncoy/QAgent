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


def test_descuento_normal(client):
    response = client.request(
        "GET", "/descuento", params={"precio": 100, "porcentaje": 20}
    )
    assert response.status_code == 200
    assert response.json() == {"precio_final": 80.0}


def test_precio_negativo(client):
    response = client.request(
        "GET", "/descuento", params={"precio": -1, "porcentaje": 20}
    )
    assert response.status_code == 422

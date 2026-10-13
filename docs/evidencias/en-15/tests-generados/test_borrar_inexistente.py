import pytest
from fastapi.testclient import TestClient

from api_mvp import Repositorio, app, obtener_repositorio


@pytest.fixture
def client():
    overrides_anteriores = dict(app.dependency_overrides)
    app.dependency_overrides[obtener_repositorio] = Repositorio
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides_anteriores)


def test_borrar_inexistente(client):
    response = client.request("DELETE", "/items/999")
    assert response.status_code == 404

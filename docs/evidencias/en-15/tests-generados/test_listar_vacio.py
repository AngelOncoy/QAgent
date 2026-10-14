import pytest
from fastapi.testclient import TestClient

from api_mvp import Repositorio, app, obtener_repositorio


@pytest.fixture
def client():
    overrides_anteriores = dict(app.dependency_overrides)
    doble_obtener_repositorio = Repositorio()
    app.dependency_overrides[obtener_repositorio] = lambda: doble_obtener_repositorio
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides_anteriores)


def test_listar(client):
    response = client.request("GET", "/items")
    assert response.status_code == 200

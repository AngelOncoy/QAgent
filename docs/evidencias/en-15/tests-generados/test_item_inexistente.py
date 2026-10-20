import pytest
from fastapi.testclient import TestClient

from api_mvp import ItemEntrada, Repositorio, app, obtener_repositorio


@pytest.fixture
def client():
    overrides_anteriores = dict(app.dependency_overrides)
    doble_obtener_repositorio = Repositorio()
    doble_obtener_repositorio.crear(ItemEntrada(nombre="lapiz", precio=2.5))
    app.dependency_overrides[obtener_repositorio] = lambda: doble_obtener_repositorio
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides_anteriores)


def test_obtener_existente(client):
    response = client.request("GET", "/items/1")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "nombre": "lapiz", "precio": 2.5}


def test_obtener_inexistente(client):
    response = client.request("GET", "/items/999")
    assert response.status_code == 404


def test_id_no_numerico(client):
    response = client.request("GET", "/items/abc")
    assert response.status_code == 422

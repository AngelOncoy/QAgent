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


def test_crear_valido(client):
    response = client.request(
        "POST", "/items", json={"nombre": "lapiz", "precio": 2.5}
    )
    assert response.status_code == 201
    cuerpo = response.json()
    assert cuerpo["nombre"] == "lapiz"
    assert cuerpo["precio"] == 2.5


def test_precio_cero(client):
    response = client.request(
        "POST", "/items", json={"nombre": "lapiz", "precio": 0}
    )
    assert response.status_code == 422


def test_nombre_vacio(client):
    response = client.request(
        "POST", "/items", json={"nombre": "", "precio": 1.0}
    )
    assert response.status_code == 422

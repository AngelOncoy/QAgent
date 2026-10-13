"""Pruebas de endpoints escritas a mano para `bench_api/api_mvp.py` (EN-16).

Tienen la forma acordada con EN-15: `TestClient(app)`, el repositorio se reemplaza
con `app.dependency_overrides` y se limpia en una fixture, y las aserciones son
sobre `r.status_code` y `r.json()`. Sirven de entrada al Reviewer en las pruebas,
como si las hubiera escrito el Generator. Son texto: aquí no se ejecutan.
"""

from __future__ import annotations

_FIXTURE = """\
import pytest
from fastapi.testclient import TestClient

from api_mvp import ItemEntrada, Repositorio, app, obtener_repositorio


@pytest.fixture
def cliente():
    repo = Repositorio()
    repo.crear(ItemEntrada(nombre="lapiz", precio=2.5))
    app.dependency_overrides[obtener_repositorio] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()
"""

PRUEBAS = {
    "GET /salud": _FIXTURE
    + """

def test_salud_ok(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok"}
""",
    "POST /items": _FIXTURE
    + """

def test_crear_valido(cliente):
    r = cliente.post("/items", json={"nombre": "lapiz", "precio": 2.5})
    assert r.status_code == 201
    assert r.json()["nombre"] == "lapiz"
    assert r.json()["precio"] == 2.5


def test_precio_cero(cliente):
    r = cliente.post("/items", json={"nombre": "lapiz", "precio": 0})
    assert r.status_code == 422


def test_nombre_vacio(cliente):
    r = cliente.post("/items", json={"nombre": "", "precio": 1.0})
    assert r.status_code == 422
""",
    "GET /items": _FIXTURE
    + """

def test_listar(cliente):
    r = cliente.get("/items")
    assert r.status_code == 200
""",
    "GET /items/{item_id}": _FIXTURE
    + """

def test_obtener_existente(cliente):
    r = cliente.get("/items/1")
    assert r.status_code == 200
    assert r.json() == {"id": 1, "nombre": "lapiz", "precio": 2.5}


def test_obtener_inexistente(cliente):
    r = cliente.get("/items/999")
    assert r.status_code == 404


def test_id_no_numerico(cliente):
    r = cliente.get("/items/abc")
    assert r.status_code == 422
""",
    "DELETE /items/{item_id}": _FIXTURE
    + """

def test_borrar_existente(cliente):
    r = cliente.delete("/items/1")
    assert r.status_code == 204


def test_borrar_inexistente(cliente):
    r = cliente.delete("/items/999")
    assert r.status_code == 404


def test_borrar_id_no_numerico(cliente):
    r = cliente.delete("/items/abc")
    assert r.status_code == 422
""",
    "GET /descuento": _FIXTURE
    + """

def test_descuento_normal(cliente):
    r = cliente.get("/descuento", params={"precio": 100, "porcentaje": 20})
    assert r.status_code == 200
    assert r.json() == {"precio_final": 80.0}


def test_precio_negativo(cliente):
    r = cliente.get("/descuento", params={"precio": -1, "porcentaje": 20})
    assert r.status_code == 422
""",
}

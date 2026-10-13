"""Pruebas del analizador de rutas FastAPI y del mapa de llamadas (EN-14).

Todo es análisis estático: no hace falta FastAPI instalado ni se ejecuta el código
de ejemplo (los textos solo se leen con ``ast``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyagent.analysis import analizar_proyecto
from pyagent.analysis.rutas import nombre_punteado

RAIZ_REPO = Path(__file__).resolve().parents[2]

API = '''
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field


class Producto(BaseModel):
    nombre: str = Field(min_length=1)
    precio: float = Field(gt=0)
    stock: int = 0


def obtener_db():
    return {}


def formatear(texto: str) -> str:
    return texto.strip()


app = FastAPI()


@app.get("/salud")
def salud():
    """Devuelve ok."""
    return {"estado": "ok"}


@app.post("/productos", response_model=Producto, status_code=status.HTTP_201_CREATED)
def crear(producto: Producto, db=Depends(obtener_db)):
    return producto


@app.get("/productos/{producto_id}")
async def obtener(
    producto_id: int,
    request: Request,
    detalle: bool = False,
    limite: Annotated[int, Query(ge=1, le=50)] = 10,
):
    if producto_id < 0:
        raise HTTPException(status_code=404, detail="No existe")
    raise HTTPException(status.HTTP_403_FORBIDDEN)


@app.api_route("/eco", methods=["GET", "POST", "HEAD"])
def eco(texto: str = Query(min_length=2)):
    return {"texto": formatear(texto)}
'''


def escribir(raiz: Path, ruta: str, texto: str) -> None:
    destino = raiz / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")


def endpoints(raiz: Path) -> dict[str, dict]:
    return {
        e["objetivo"]: e
        for m in analizar_proyecto(raiz)["modulos"]
        for e in m["endpoints"]
    }


@pytest.fixture
def api(tmp_path: Path) -> dict[str, dict]:
    escribir(tmp_path, "main.py", API)
    return endpoints(tmp_path)


# --- Criterio 1: rutas, métodos, parámetros, cuerpo y respuesta -------------------
def test_lista_cada_ruta_con_metodo_y_objetivo(api):
    assert sorted(api) == [
        "GET /eco",
        "GET /productos/{producto_id}",
        "GET /salud",
        "POST /eco",
        "POST /productos",
    ]
    assert api["GET /salud"]["manejador"] == "salud"
    assert api["GET /salud"]["docstring"] == "Devuelve ok."


def test_status_code_declarado_o_200_por_defecto(api):
    crear = api["POST /productos"]
    assert (crear["status_code"], crear["status_code_declarado"]) == (201, True)
    salud = api["GET /salud"]
    assert (salud["status_code"], salud["status_code_declarado"]) == (200, False)
    assert crear["response_model"] == "Producto"


def test_cuerpo_dependencias_y_parametros(api):
    crear = api["POST /productos"]
    assert crear["cuerpo"]["nombre"] == "producto"
    assert crear["cuerpo"]["modelo"] == "Producto"
    assert crear["dependencias"] == [
        {
            "parametro": "db",
            "funcion": "obtener_db",
            "en_proyecto": "main.py::obtener_db",
        }
    ]

    obtener = api["GET /productos/{producto_id}"]
    assert [p["nombre"] for p in obtener["parametros_ruta"]] == ["producto_id"]
    consulta = {p["nombre"]: p for p in obtener["parametros_consulta"]}
    assert set(consulta) == {
        "detalle",
        "limite",
    }  # Request no es un dato de la petición
    assert consulta["detalle"]["requerido"] is False
    assert consulta["limite"]["tipo"] == "int"
    assert consulta["limite"]["restricciones"] == {"ge": 1, "le": 50}
    assert obtener["es_async"] is True


def test_excepciones_http_que_lanza(api):
    obtener = api["GET /productos/{producto_id}"]
    assert [(e["status_code"], e["detalle"]) for e in obtener["excepciones_http"]] == [
        (404, "No existe"),
        (403, None),
    ]


def test_api_route_con_varios_metodos_ignora_los_no_soportados(api):
    assert "HEAD /eco" not in api
    eco = api["GET /eco"]
    assert eco["parametros_consulta"][0]["restricciones"] == {"min_length": 2}
    assert eco["llama_a"] == ["main.py::formatear"]


def test_rango_de_lineas_del_manejador(api):
    salud = api["GET /salud"]
    assert salud["linea"] < salud["linea_fin"]


# --- Criterio 2: modelos Pydantic y llama_a ----------------------------------------
def test_modelos_pydantic_con_restricciones(tmp_path):
    escribir(tmp_path, "main.py", API)
    modulo = analizar_proyecto(tmp_path)["modulos"][0]
    [producto] = modulo["modelos"]
    campos = {c["nombre"]: c for c in producto["campos"]}
    assert campos["nombre"]["restricciones"] == {"min_length": 1}
    assert campos["precio"]["requerido"] is True
    assert campos["stock"] == {
        "nombre": "stock",
        "tipo": "int",
        "requerido": False,
        "por_defecto": "0",
        "restricciones": {},
    }


def test_modelo_hereda_campos_de_otro_modulo(tmp_path):
    escribir(
        tmp_path,
        "app/modelos/base.py",
        "from pydantic import BaseModel\n\nclass Base(BaseModel):\n    id: int\n",
    )
    escribir(
        tmp_path,
        "app/modelos/usuario.py",
        "from .base import Base\n\nclass Usuario(Base):\n    correo: str\n",
    )
    modulos = {m["ruta"]: m for m in analizar_proyecto(tmp_path)["modulos"]}
    [usuario] = modulos["app/modelos/usuario.py"]["modelos"]
    assert usuario["hereda_de"] == ["Base"]
    assert [c["nombre"] for c in usuario["campos"]] == ["id", "correo"]


def test_llama_a_resuelve_imports_del_proyecto_y_omite_lo_demas(tmp_path):
    escribir(
        tmp_path,
        "tienda/precios.py",
        "def redondear(x):\n    return round(x, 2)\n\ndef _privada():\n    pass\n",
    )
    escribir(
        tmp_path,
        "tienda/ventas.py",
        "import math\n"
        "from tienda.precios import redondear as r, _privada\n"
        "from tienda import precios\n\n"
        "def total(a, b):\n"
        "    _privada()\n"
        "    math.sqrt(a)\n"
        "    precios.redondear(a)\n"
        "    return r(a + b) + total(0, 0)\n",
    )
    modulos = {m["ruta"]: m for m in analizar_proyecto(tmp_path)["modulos"]}
    [total] = modulos["tienda/ventas.py"]["funciones"]
    assert total["llama_a"] == ["tienda/precios.py::redondear"]


# --- Criterio 3: los manejadores salen de las funciones -----------------------------
def test_los_manejadores_no_se_cuentan_como_funciones(tmp_path):
    escribir(tmp_path, "main.py", API)
    resultado = analizar_proyecto(tmp_path)
    nombres = [f["nombre"] for f in resultado["modulos"][0]["funciones"]]
    assert nombres == ["obtener_db", "formatear"]
    assert resultado["resumen"]["total_funciones_publicas"] == 2
    assert resultado["resumen"]["total_endpoints"] == 5


def test_decoradores_que_no_son_de_fastapi_no_crean_endpoints(tmp_path):
    escribir(
        tmp_path,
        "otro.py",
        "import functools\nfrom flask import Flask\n\napp = Flask(__name__)\n\n"
        "@app.get('/x')\ndef vista():\n    pass\n\n"
        "@functools.lru_cache\ndef cacheada():\n    pass\n",
    )
    modulo = analizar_proyecto(tmp_path)["modulos"][0]
    assert modulo["endpoints"] == []
    assert [f["nombre"] for f in modulo["funciones"]] == ["vista", "cacheada"]


def test_no_ejecuta_el_codigo(tmp_path):
    escribir(
        tmp_path,
        "main.py",
        "raise SystemExit('no debía ejecutarse')\n" + API,
    )
    assert len(endpoints(tmp_path)) == 5


# --- Prefijos de APIRouter e include_router -----------------------------------------
def test_prefijos_de_router_e_include_router_entre_modulos(tmp_path):
    escribir(
        tmp_path,
        "app/rutas/items.py",
        "from fastapi import APIRouter\n\nrouter = APIRouter(prefix='/items')\n\n"
        "@router.get('/{item_id}')\ndef leer(item_id: int):\n    pass\n\n"
        "@router.post('')\ndef crear():\n    pass\n",
    )
    escribir(
        tmp_path,
        "app/main.py",
        "from fastapi import FastAPI\nfrom app.rutas import items\n\napp = FastAPI()\n"
        "app.include_router(items.router, prefix='/api/v1')\n",
    )
    rutas = endpoints(tmp_path)
    assert sorted(rutas) == ["GET /api/v1/items/{item_id}", "POST /api/v1/items"]
    assert all(e["resuelta"] for e in rutas.values())
    assert rutas["POST /api/v1/items"]["app"] == "router"


def test_router_sin_incluir_o_con_prefijo_no_literal_queda_sin_resolver(tmp_path):
    escribir(
        tmp_path,
        "suelto.py",
        "from fastapi import APIRouter\n\nrouter = APIRouter(prefix='/x')\n\n"
        "@router.get('/y')\ndef y():\n    pass\n",
    )
    escribir(
        tmp_path,
        "dinamico.py",
        "from fastapi import APIRouter, FastAPI\n\nPREFIJO = '/v2'\napp = FastAPI()\n"
        "otro = APIRouter()\n\n@otro.get('/z')\ndef z():\n    pass\n\n"
        "app.include_router(otro, prefix=PREFIJO)\n",
    )
    rutas = endpoints(tmp_path)
    assert rutas["GET /x/y"]["resuelta"] is False
    assert rutas["GET /z"]["resuelta"] is False


@pytest.mark.parametrize(
    ("ruta", "esperado"),
    [
        ("main.py", "main"),
        ("app/api/rutas.py", "app.api.rutas"),
        ("app/__init__.py", "app"),
    ],
)
def test_nombre_punteado(ruta, esperado):
    assert nombre_punteado(ruta) == esperado


# --- Criterio 6: evidencia sobre el banco de la API ---------------------------------
def test_banco_de_la_api_tiene_sus_6_endpoints():
    rutas = endpoints(RAIZ_REPO / "bench_api")
    assert sorted(rutas) == [
        "DELETE /items/{item_id}",
        "GET /descuento",
        "GET /items",
        "GET /items/{item_id}",
        "GET /salud",
        "POST /items",
    ]
    assert rutas["POST /items"]["status_code"] == 201
    assert rutas["POST /items"]["cuerpo"]["modelo"] == "ItemEntrada"
    assert rutas["DELETE /items/{item_id}"]["status_code"] == 204
    assert [
        e["status_code"] for e in rutas["DELETE /items/{item_id}"]["excepciones_http"]
    ] == [404]
    assert rutas["GET /descuento"]["llama_a"] == ["api_mvp.py::calcular_descuento"]
    assert all(e["resuelta"] for e in rutas.values())

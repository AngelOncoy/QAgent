"""#74: mutmut real sobre el manejador de un endpoint FastAPI pequeño, en el sandbox.

Usa `TestClient` y `dependency_overrides`, como las pruebas de endpoint que genera QAgent.
Se omite si Docker no está disponible; la imagen derivada instala FastAPI (con red).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.sandbox import (
    ImagenNoEncontrada,
    LimitesSandbox,
    construir_imagen_base,
    ejecutar_mutacion,
    preparar_imagen,
)
from qagent.sandbox.mutacion import OK

pytestmark = [pytest.mark.docker, pytest.mark.red]

LIMITES = LimitesSandbox(cpus=1.0, memoria="512m", timeout_s=300)

API = '''from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI()


class Pedido(BaseModel):
    total: float = Field(gt=0)


def obtener_tasa() -> float:
    return 0.18 if True else 0.0


@app.post("/pedidos", status_code=201)
def crear(pedido: Pedido, tasa: float = Depends(obtener_tasa)) -> dict:
    """Aplica la tasa; rechaza totales mayores a 1000."""
    if pedido.total > 1000:
        raise HTTPException(status_code=422, detail="total muy alto")
    return {"total": round(pedido.total * (1 + tasa), 2)}
'''

PRUEBA_DEBIL = """from fastapi.testclient import TestClient

from api import app, obtener_tasa

app.dependency_overrides[obtener_tasa] = lambda: 0.5
cliente = TestClient(app)


def test_crea_pedido():
    respuesta = cliente.post("/pedidos", json={"total": 10})
    assert respuesta.status_code == 201
    assert respuesta.json() == {"total": 15.0}
"""


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    raiz = tmp_path / "proyecto"
    raiz.mkdir()
    (raiz / "api.py").write_text(API, encoding="utf-8")
    (raiz / "requirements.txt").write_text("fastapi>=0.110\n", encoding="utf-8")
    return raiz


@pytest.fixture
def imagen(cliente_docker, proyecto: Path) -> str:
    try:
        return preparar_imagen(proyecto, cliente_docker)
    except ImagenNoEncontrada:
        construir_imagen_base(cliente_docker)
        return preparar_imagen(proyecto, cliente_docker)


def test_muta_solo_el_manejador_y_una_prueba_debil_deja_sobrevivientes(
    imagen, proyecto: Path, tmp_path: Path
) -> None:
    pruebas = tmp_path / "pruebas"
    pruebas.mkdir()
    (pruebas / "test_api.py").write_text(PRUEBA_DEBIL, encoding="utf-8")

    resultado = ejecutar_mutacion(
        imagen,
        proyecto,
        pruebas,
        "api.py",
        [],
        LIMITES,
        inicios={"crear": 16},
        manejadores=["crear"],
    )

    assert set(resultado.funciones) == {"crear"}
    crear = resultado.funciones["crear"]
    assert crear.estado == OK, resultado.salida
    assert crear.detectados >= 1
    # La prueba no cubre el 422 del total alto: algún mutante de esa rama sobrevive.
    assert crear.sobrevivientes, resultado.salida
    assert 0 < crear.puntuacion < 100
    # Los sobrevivientes están en el cuerpo del manejador (líneas 17-20), no en
    # `obtener_tasa` (dependencia simulada) ni en el modelo Pydantic.
    lineas = {s.linea for s in crear.sobrevivientes if s.linea is not None}
    assert lineas and lineas <= set(range(17, 21)), crear.sobrevivientes
    # El archivo del usuario no cambia.
    assert (proyecto / "api.py").read_text(encoding="utf-8") == API

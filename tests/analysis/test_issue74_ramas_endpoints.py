"""#74: decisiones (`ramas`) del manejador de cada endpoint, solo con `ast`."""

from __future__ import annotations

from pathlib import Path

from qagent.analysis import analizar_proyecto
from qagent.proyectos.vista_previa import generar_vista_previa

API = """
from fastapi import FastAPI, HTTPException

app = FastAPI()


@app.get("/salud")
def salud():
    return {"ok": True}


@app.get("/items/{item_id}")
def obtener(item_id: int):
    if item_id < 0:
        raise HTTPException(status_code=422, detail="negativo")
    raise HTTPException(status_code=404, detail="no existe")


@app.post("/pagos")
async def pagar(monto: float):
    try:
        total = 100 / monto
    except ZeroDivisionError:
        raise HTTPException(status_code=400, detail="monto cero")
    except ValueError:
        raise HTTPException(status_code=400, detail="monto inválido")
    return {"total": total if total > 1 else 1}


@app.get("/anidada")
def anidada():
    def interna(x):
        if x:
            return 1
        return 0
    return {"valor": interna(True)}
"""


def _endpoints(raiz: Path) -> dict[str, dict]:
    return {
        e["objetivo"]: e
        for m in analizar_proyecto(raiz)["modulos"]
        for e in m["endpoints"]
    }


def test_cuenta_las_decisiones_del_manejador(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(API, encoding="utf-8")

    endpoints = _endpoints(tmp_path)

    assert endpoints["GET /salud"]["ramas"] == 0
    # Un `if`; lanzar HTTPException no es una decisión por sí mismo.
    assert endpoints["GET /items/{item_id}"]["ramas"] == 1
    # Dos `except` y una expresión ternaria; el `try` no suma por sí solo.
    assert endpoints["POST /pagos"]["ramas"] == 3
    # Las ramas de una función anidada no son del manejador.
    assert endpoints["GET /anidada"]["ramas"] == 0


def test_la_vista_previa_propone_profundizar_endpoints_con_decisiones(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.py").write_text(API, encoding="utf-8")

    [modulo] = generar_vista_previa(tmp_path)["modulos"]

    propuesta = {e["objetivo"]: e["critica_propuesta"] for e in modulo["endpoints"]}
    assert propuesta == {
        "GET /salud": False,
        "GET /items/{item_id}": True,
        "POST /pagos": True,
        "GET /anidada": False,
    }

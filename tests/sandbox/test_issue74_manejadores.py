"""#74: aislar el cuerpo de los manejadores para mutmut, sin Docker ni FastAPI.

El código reescrito se ejecuta aquí con un `app` falso que solo registra rutas: es
código de ejemplo de la prueba, no del usuario.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
from pathlib import Path

import pytest

from qagent.sandbox import mutacion
from qagent.sandbox.manejadores import (
    aislar_manejadores,
    motivo_no_aislable,
    nombre_aislado,
)
from qagent.sandbox.modelos import LimitesSandbox, ResultadoSandbox
from qagent.sandbox.mutacion import ERROR, OK, ejecutar_mutacion

API = '''from dependencias import Depends, obtener_db


class Pedido:
    def __init__(self, total):
        self.total = total


@app.post("/pedidos", status_code=201)
def crear(pedido: Pedido, db=Depends(obtener_db), *, nota: str = "") -> dict:
    """Crea un pedido."""
    if pedido.total <= 0:
        raise ValueError("total inválido")
    return {"total": pedido.total, "db": db, "nota": nota}


@app.get("/a")
@app.get("/b")
async def leer(item_id: int):
    return {"id": item_id if item_id > 0 else 0}


def ayuda(x):
    return x + 1
'''


class AppFalsa:
    """Registra (método, ruta, función) en el orden en que se decoran."""

    def __init__(self) -> None:
        self.rutas: list[tuple[str, str, object]] = []

    def _registrar(self, metodo: str):
        def decorador(ruta: str, **_opciones):
            def aplicar(funcion):
                self.rutas.append((metodo, ruta, funcion))
                return funcion

            return aplicar

        return decorador

    def __getattr__(self, metodo: str):
        return self._registrar(metodo.upper())


def _ejecutar(fuente: str) -> tuple[dict, AppFalsa]:
    app = AppFalsa()
    espacio = {
        "app": app,
        "__name__": "api",
        "__builtins__": __builtins__,
    }
    dependencias = type(
        "Mod", (), {"Depends": staticmethod(lambda f: ("depende", f)), "obtener_db": 1}
    )
    import sys

    sys.modules["dependencias"] = dependencias
    try:
        exec(compile(fuente, "api.py", "exec", dont_inherit=True), espacio)  # noqa: S102 — código de la prueba
    finally:
        del sys.modules["dependencias"]
    return espacio, app


def test_el_cuerpo_queda_en_una_funcion_sin_decorador() -> None:
    nuevo = aislar_manejadores(API, ["crear", "leer"])

    arbol = ast.parse(nuevo)
    funciones = {
        n.name: n
        for n in arbol.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    original = {
        n.name: n
        for n in ast.parse(API).body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for manejador in ("crear", "leer"):
        aislado = funciones[nombre_aislado(manejador)]
        assert aislado.decorator_list == []
        assert ast.dump(aislado.args) == ast.dump(original[manejador].args)
        assert [ast.dump(n) for n in aislado.body] == [
            ast.dump(n) for n in original[manejador].body
        ]
    # El primer manejador no se mueve; los demás bajan por los envoltorios de arriba
    # (los sobrevivientes se ubican con la línea relativa al `def`).
    assert funciones[nombre_aislado("crear")].lineno == original["crear"].lineno
    assert isinstance(funciones[nombre_aislado("leer")], ast.AsyncFunctionDef)
    # Lo que no es manejador no se toca.
    assert "def ayuda(x):\n    return x + 1" in nuevo
    assert "class Pedido:" in nuevo


def test_el_envoltorio_conserva_firma_decoradores_y_orden_de_rutas() -> None:
    _, app_original = _ejecutar(API)
    espacio, app = _ejecutar(aislar_manejadores(API, ["crear", "leer"]))

    assert [(m, r) for m, r, _ in app.rutas] == [
        (m, r) for m, r, _ in app_original.rutas
    ]
    crear = espacio["crear"]
    assert str(inspect.signature(crear)) == (
        "(pedido: api.Pedido, db=('depende', 1), *, nota: str = '') -> dict"
    )
    resultado = crear(espacio["Pedido"](5), db="mi-db", nota="hola")
    assert resultado == {"total": 5, "db": "mi-db", "nota": "hola"}
    with pytest.raises(ValueError, match="total inválido"):
        crear(espacio["Pedido"](0))
    leer = espacio["leer"]
    assert inspect.iscoroutinefunction(leer)
    assert asyncio.run(leer(3)) == {"id": 3}


@pytest.mark.parametrize(
    "fuente, manejador, motivo",
    [
        ("def f():\n    return 1\n", "g", "No se encontró el manejador g"),
        ("def f():\n    return 1\n", "f", "no tiene el decorador"),
        (
            "@app.get('/s')\nasync def f():\n    yield 1\n",
            "f",
            "generador asíncrono",
        ),
        ("def f(:\n", "f", "no se pudo analizar"),
    ],
)
def test_explica_cuando_no_se_puede_aislar(fuente, manejador, motivo) -> None:
    assert motivo in motivo_no_aislable(fuente, manejador)
    with pytest.raises(ValueError):
        aislar_manejadores(fuente, [manejador])


def test_ejecutar_mutacion_envia_el_modulo_aislado_y_devuelve_el_nombre_del_manejador(
    monkeypatch, tmp_path: Path
) -> None:
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    (proyecto / "api.py").write_text(API, encoding="utf-8")
    pruebas = tmp_path / "pruebas"
    pruebas.mkdir()
    (pruebas / "test_api.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    vistas = {}

    def falso(
        imagen, comando, proyecto_, tests, limites, entorno, al_terminar, cliente
    ):
        vistas["funciones"] = json.loads(entorno["QAGENT_MUT_FUNCIONES"])
        vistas["pruebas"] = sorted(p.name for p in Path(tests).iterdir())
        vistas["aislado"] = (Path(tests) / mutacion.ARCHIVO_AISLADO).read_text(
            encoding="utf-8"
        )
        salida = tmp_path / "out"
        salida.mkdir()
        (salida / mutacion.ARCHIVO_RESULTADO).write_text(
            json.dumps(
                {
                    "estado": "ok",
                    "codigos": {
                        "api.x__qagent_manejador_crear__mutmut_1": 1,
                        "api.x__qagent_manejador_crear__mutmut_2": 0,
                        "api.x_ayuda__mutmut_1": 1,
                    },
                    "cambios": {
                        "api.x__qagent_manejador_crear__mutmut_2": (
                            "@@ -1,4 +1,4 @@\n def x():\n     doc\n"
                            "-    if pedido.total <= 0:\n+    if pedido.total <= 1:\n"
                        )
                    },
                }
            ),
            encoding="utf-8",
        )
        al_terminar(proyecto_, salida)
        return ResultadoSandbox(exit_code=0, stdout="", stderr="", duracion_s=1.0)

    monkeypatch.setattr(mutacion, "ejecutar_en_sandbox", falso)

    resultado = ejecutar_mutacion(
        "img",
        proyecto,
        pruebas,
        "api.py",
        ["ayuda"],
        LimitesSandbox(timeout_s=60),
        inicios={"ayuda": 26, "crear": 10},
        manejadores=["crear"],
    )

    assert vistas["funciones"] == ["ayuda", "_qagent_manejador_crear"]
    assert vistas["pruebas"] == [mutacion.ARCHIVO_AISLADO, "test_api.py"]
    assert vistas["aislado"] == aislar_manejadores(API, ["crear"])
    # Las pruebas originales no se modifican.
    assert sorted(p.name for p in pruebas.iterdir()) == ["test_api.py"]
    crear = resultado.funciones["crear"]
    assert crear.funcion == "crear"
    assert crear.estado == OK
    assert crear.puntuacion == 50.0
    assert crear.sobrevivientes[0].linea == 12
    assert resultado.funciones["ayuda"].puntuacion == 100.0
    assert set(resultado.funciones) == {"ayuda", "crear"}
    # El archivo del usuario nunca cambia.
    assert (proyecto / "api.py").read_text(encoding="utf-8") == API


def test_un_manejador_no_aislable_queda_con_error_sin_ir_al_sandbox(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "api.py").write_text("def suelto():\n    return 1\n", encoding="utf-8")

    def no_llamar(*_args, **_kwargs):
        raise AssertionError("no debía ejecutarse el sandbox")

    monkeypatch.setattr(mutacion, "ejecutar_en_sandbox", no_llamar)

    resultado = ejecutar_mutacion(
        "img", tmp_path, tmp_path, "api.py", [], manejadores=["suelto"]
    )

    assert resultado.funciones["suelto"].estado == ERROR
    assert "no tiene el decorador" in resultado.funciones["suelto"].mensaje


def test_el_script_reemplaza_el_modulo_solo_si_hay_manejadores_aislados() -> None:
    script = mutacion.SCRIPT_MUTACION
    assert (
        f'Path("{mutacion.CARPETA_PRUEBAS}") / "{mutacion.ARCHIVO_AISLADO}"' in script
    )
    assert "aislado.unlink()" in script
    assert script.index("shutil.copytree") < script.index("aislado.is_file()")

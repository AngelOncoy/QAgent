"""EN-09: lectura del resultado de mutmut, sin Docker."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.sandbox import mutacion
from qagent.sandbox.modelos import LimitesSandbox, ResultadoSandbox
from qagent.sandbox.mutacion import (
    CONFIG_PROPIA,
    ERROR,
    OK,
    TIEMPO_AGOTADO,
    ejecutar_mutacion,
    funcion_del_mutante,
    interpretar,
    linea_y_cambio,
    puntuacion,
)

DIFF = """# calc.x_descuento__mutmut_3: survived
--- calc.py
+++ calc.py
@@ -1,5 +1,5 @@
 def descuento(precio: float, vip: bool) -> float:
     \"\"\"Aplica 10 % si es VIP y el precio supera 100.\"\"\"
-    if vip and precio > 100:
+    if vip and precio > 101:
         return precio * 0.9
     return precio
"""


@pytest.mark.parametrize(
    "detectados, sobrevivientes, esperado",
    [(3, 1, 75.0), (2, 1, 66.7), (5, 0, 100.0), (0, 4, 0.0), (0, 0, None)],
)
def test_puntuacion(detectados, sobrevivientes, esperado) -> None:
    assert puntuacion(detectados, sobrevivientes) == esperado


@pytest.mark.parametrize(
    "mutante, funcion",
    [
        ("calc.x_descuento__mutmut_3", "descuento"),
        ("pkg.sub.calc.x_es_par__mutmut_12", "es_par"),
        ("calc.x_x_raro__mutmut_1", "x_raro"),
    ],
)
def test_funcion_del_mutante(mutante, funcion) -> None:
    assert funcion_del_mutante(mutante) == funcion


def test_linea_y_cambio_del_diff() -> None:
    assert linea_y_cambio(DIFF) == (
        3,
        "if vip and precio > 100: → if vip and precio > 101:",
    )


def test_linea_y_cambio_sin_diff() -> None:
    assert linea_y_cambio("") == (None, "")


def test_interpreta_detectados_sobrevivientes_y_no_evaluados() -> None:
    datos = {
        "estado": OK,
        "codigos": {
            "calc.x_descuento__mutmut_1": 1,  # killed
            "calc.x_descuento__mutmut_2": 36,  # timeout: lo detectó
            "calc.x_descuento__mutmut_3": 0,  # survived
            "calc.x_descuento__mutmut_4": None,  # no se evaluó
            "calc.x_descuento__mutmut_5": 34,  # skipped
            "calc.x_doble__mutmut_1": 33,  # sin pruebas: cuenta como sobreviviente
            "calc.x_otra__mutmut_1": 1,  # no se pidió: se ignora
        },
        "cambios": {"calc.x_descuento__mutmut_3": DIFF},
    }

    # descuento empieza en la línea 10 del archivo; el cambio está en su línea 3.
    resultado = interpretar(datos, ["descuento", "doble"], {"descuento": 10})

    descuento = resultado["descuento"]
    assert descuento.estado == OK
    assert descuento.detectados == 2
    assert [s.mutante for s in descuento.sobrevivientes] == [
        "calc.x_descuento__mutmut_3"
    ]
    assert descuento.sobrevivientes[0].linea == 12
    assert descuento.puntuacion == 66.7
    assert resultado["doble"].sobrevivientes[0].linea is None  # sin línea de inicio
    assert resultado["doble"].puntuacion == 0.0
    assert set(resultado) == {"descuento", "doble"}


def test_funcion_sin_mutantes_no_tiene_puntuacion() -> None:
    resultado = interpretar({"estado": OK, "codigos": {}}, ["vacia"])

    assert resultado["vacia"].puntuacion is None
    assert "no generó mutantes" in resultado["vacia"].mensaje


@pytest.mark.parametrize(
    "datos, estado",
    [
        ({"estado": CONFIG_PROPIA}, CONFIG_PROPIA),
        ({"estado": ERROR}, ERROR),
        (None, ERROR),
    ],
)
def test_sin_resultado_valido_no_hay_puntuacion(datos, estado) -> None:
    resultado = interpretar(datos, ["descuento"])

    assert resultado["descuento"].estado == estado
    assert resultado["descuento"].puntuacion is None
    assert resultado["descuento"].mensaje


def test_ejecutar_mutacion_pasa_archivo_y_funciones_sin_pythonpath(
    monkeypatch, tmp_path: Path
) -> None:
    llamadas = {}

    def falso(imagen, comando, proyecto, tests, limites, entorno, al_terminar, cliente):
        llamadas.update(comando=comando, entorno=entorno, limites=limites)
        salida = tmp_path / "out"
        salida.mkdir()
        (salida / mutacion.ARCHIVO_RESULTADO).write_text(
            '{"estado": "ok", "codigos": {"pkg.calc.x_f__mutmut_1": 1}}',
            encoding="utf-8",
        )
        al_terminar(tmp_path, salida)
        return ResultadoSandbox(exit_code=0, stdout="", stderr="", duracion_s=1.5)

    monkeypatch.setattr(mutacion, "ejecutar_en_sandbox", falso)
    limites = LimitesSandbox(timeout_s=90)

    resultado = ejecutar_mutacion(
        "img", tmp_path, tmp_path, "pkg/calc.py", ["f"], limites
    )

    assert llamadas["comando"][:2] == ["python", "-c"]
    assert llamadas["entorno"]["PYTHONPATH"] == ""
    assert llamadas["entorno"]["QAGENT_MUT_ARCHIVO"] == "pkg/calc.py"
    assert llamadas["entorno"]["QAGENT_MUT_FUNCIONES"] == '["f"]'
    assert llamadas["limites"] is limites
    assert resultado.funciones["f"].puntuacion == 100.0
    assert resultado.duracion_s == 1.5


def test_tiempo_agotado_no_da_puntuacion(monkeypatch, tmp_path: Path) -> None:
    def lento(*_args, **_kwargs):
        return ResultadoSandbox(exit_code=137, stdout="", stderr="", timed_out=True)

    monkeypatch.setattr(mutacion, "ejecutar_en_sandbox", lento)

    resultado = ejecutar_mutacion(
        "img", tmp_path, tmp_path, "calc.py", ["f"], LimitesSandbox(timeout_s=30)
    )

    assert resultado.funciones["f"].estado == TIEMPO_AGOTADO
    assert resultado.funciones["f"].puntuacion is None
    assert "30 s" in resultado.funciones["f"].mensaje


def test_el_script_copia_las_pruebas_dentro_del_proyecto() -> None:
    """Fuera del proyecto, mutmut cuenta como «killed» a todos los mutantes."""
    script = mutacion.SCRIPT_MUTACION
    assert f'shutil.copytree("/work/tests", "{mutacion.CARPETA_PRUEBAS}")' in script
    assert (
        f'"pytest_add_cli_args_test_selection": "{mutacion.CARPETA_PRUEBAS}"' in script
    )
    assert '"only_mutate": archivo' in script
    assert "--max-children" in script

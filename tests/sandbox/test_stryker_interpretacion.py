"""Pruebas de interpretación del informe JSON de Stryker (#179).

Verifica la conversión a ResultadoMutacion, cálculo de Mutation Score con
la fórmula estándar (`puntuacion`) y extracción de sobrevivientes con línea y cambio.
"""

from pathlib import Path

from qagent.sandbox.mutacion import ERROR, OK
from qagent.sandbox.stryker import interpretar_stryker

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "javascript"
    / "stryker-report.json"
)


def test_interpretar_informe_stryker_grabado() -> None:
    """Convierte el fixture grabado a ResultadoMutacion con métricas esperadas."""
    informe_json = FIXTURE_PATH.read_text(encoding="utf-8")
    rangos = {
        "calcularDescuento": (1, 6),
        "formatearMoneda": (8, 10),
    }

    resultado = interpretar_stryker(
        informe_json,
        "src/precios.ts",
        ["calcularDescuento", "formatearMoneda"],
        rangos=rangos,
    )

    assert resultado.modulo == "src/precios.ts"
    assert set(resultado.funciones.keys()) == {"calcularDescuento", "formatearMoneda"}

    # calcularDescuento: 2 killed + 1 timeout = 3 detectados; 1 survived. Total = 4.
    # puntuacion = 3 / 4 * 100 = 75.0 %
    desc = resultado.funciones["calcularDescuento"]
    assert desc.estado == OK
    assert desc.detectados == 3
    assert len(desc.sobrevivientes) == 1
    assert desc.puntuacion == 75.0

    # Sobreviviente: línea 3, cambio de operador '*' a '/'
    sobreviviente = desc.sobrevivientes[0]
    assert sobreviviente.linea == 3
    assert "* → /" in sobreviviente.cambio
    assert "BinaryExpression" in sobreviviente.mutante

    # formatearMoneda: 0 detectados, 1 survived. Total = 1.
    # puntuacion = 0 / 1 * 100 = 0.0 %
    form = resultado.funciones["formatearMoneda"]
    assert form.estado == OK
    assert form.detectados == 0
    assert len(form.sobrevivientes) == 1
    assert form.puntuacion == 0.0
    assert form.sobrevivientes[0].linea == 9
    assert "'$' → \"\"" in form.sobrevivientes[0].cambio


def test_interpretar_funcion_sin_mutantes() -> None:
    """Una función sin mutantes evaluables queda sin score (None)."""
    datos = {
        "files": {
            "src/a.ts": {
                "source": "export function f() { return 1; }",
                "mutants": [],
            }
        }
    }
    resultado = interpretar_stryker(datos, "src/a.ts", ["f"], rangos={"f": (1, 1)})
    f = resultado.funciones["f"]
    assert f.estado == OK
    assert f.puntuacion is None
    assert f.detectados == 0
    assert len(f.sobrevivientes) == 0
    assert "no generó mutantes evaluables" in (f.mensaje or "")


def test_interpretar_mutante_con_error_tecnico() -> None:
    """CompileError o RuntimeError marca el estado de la función como error."""
    datos = {
        "files": {
            "src/a.ts": {
                "source": "export function f() { return 1; }",
                "mutants": [
                    {
                        "id": "1",
                        "mutatorName": "Syntax",
                        "status": "CompileError",
                        "location": {"start": {"line": 1, "column": 1}},
                    }
                ],
            }
        }
    }
    resultado = interpretar_stryker(datos, "src/a.ts", ["f"], rangos={"f": (1, 1)})
    f = resultado.funciones["f"]
    assert f.estado == ERROR
    assert "CompileError" in (f.mensaje or "")


def test_interpretar_json_invalido_o_vacio() -> None:
    """JSON vacío o dañado devuelve error para todas las funciones."""
    r1 = interpretar_stryker("", "src/a.ts", ["f"])
    assert r1.funciones["f"].estado == ERROR

    r2 = interpretar_stryker("{invalido", "src/a.ts", ["f"])
    assert r2.funciones["f"].estado == ERROR

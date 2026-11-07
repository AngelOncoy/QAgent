"""Pruebas sin Docker del comando de mutación con Stryker (#179).

Verifica que el comando de Stryker se delimite a las funciones críticas
seleccionadas (por rangos de líneas), nunca al repositorio completo.
"""

from pathlib import Path

import pytest

from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.sandbox.stryker_comando import comando_stryker

MODULO_TS = "src/precios.ts"
MODULO_JS = "src/personas.mjs"


def test_comando_stryker_acotado_a_rangos_de_lineas() -> None:
    """El comando delimita la mutación con --mutate exacto a los rangos."""
    rangos = {"calcularDescuento": (1, 15), "formatearMoneda": (20, 30)}
    comando = comando_stryker(
        MODULO_TS, ["calcularDescuento", "formatearMoneda"], rangos=rangos
    )

    assert comando.comando[0] == "stryker"
    assert comando.comando[1] == "run"
    assert ".qagent-stryker.json" in comando.comando
    assert "--concurrency" in comando.comando
    assert comando.entorno["NODE_ENV"] == "test"
    assert comando.entorno["NO_COLOR"] == "1"

    # Verificar que el mutate contiene las líneas exactas
    arg_mutate = next(a for a in comando.comando if a.startswith("--mutate="))
    assert "src/precios.ts:1-15" in arg_mutate
    assert "src/precios.ts:20-30" in arg_mutate
    # Nunca al repositorio completo ni archivos sin líneas
    assert "src/**/*.ts" not in arg_mutate
    assert not arg_mutate.endswith("src/precios.ts")


def test_comando_stryker_desde_adaptadores() -> None:
    """Tanto JavaScriptAdapter como TypeScriptAdapter arman comando_mutacion."""
    rangos_ts = {"calcularDescuento": (5, 25)}
    cmd_ts = TypeScriptAdapter().comando_mutacion(
        MODULO_TS, ["calcularDescuento"], rangos=rangos_ts
    )
    assert cmd_ts.comando[0] == "stryker"
    assert any("src/precios.ts:5-25" in a for a in cmd_ts.comando)

    rangos_js = {"clasificarEdad": (10, 40)}
    cmd_js = JavaScriptAdapter().comando_mutacion(
        MODULO_JS, ["clasificarEdad"], rangos=rangos_js
    )
    assert cmd_js.comando[0] == "stryker"
    assert any("src/personas.mjs:10-40" in a for a in cmd_js.comando)


def test_comando_extrae_rangos_si_archivo_existe(tmp_path: Path, monkeypatch) -> None:
    """Si no se pasan rangos explícitos pero el archivo existe, los deduce con tree-sitter."""
    archivo = tmp_path / "calc.js"
    archivo.write_text(
        "export function sumar(a, b) {\n  return a + b;\n}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    cmd = comando_stryker("calc.js", ["sumar"])
    arg_mutate = next(a for a in cmd.comando if a.startswith("--mutate="))
    assert "calc.js:1-3" in arg_mutate


def test_comando_determinista_y_sin_duplicados() -> None:
    """El orden de funciones y duplicados no cambia el comando resultante."""
    rangos = {"a": (1, 5), "b": (10, 20)}
    cmd1 = comando_stryker("src/a.ts", ["a", "b", "a"], rangos=rangos)
    cmd2 = comando_stryker("src/a.ts", ["b", "a"], rangos=rangos)
    assert cmd1.comando == cmd2.comando


@pytest.mark.parametrize(
    "funciones",
    [
        [],
        [""],
        ["sumar; rm -rf /"],
        ["sumar extra"],
    ],
)
def test_rechaza_funciones_invalidas(funciones: list[str]) -> None:
    """Lista vacía o nombres con caracteres de inyección fallan."""
    with pytest.raises(ValueError):
        comando_stryker("src/a.ts", funciones, rangos={f: (1, 5) for f in funciones})


@pytest.mark.parametrize(
    "modulo",
    [
        "../precios.ts",
        "/src/precios.ts",
        "src/precios.py",
        "src/precios.java",
        "src/*.ts",
        "src/precios?.js",
    ],
)
def test_rechaza_rutas_no_admitidas(modulo: str) -> None:
    """Rutas absolutas, recorridos o extensiones no JS/TS se rechazan."""
    with pytest.raises(ValueError):
        comando_stryker(modulo, ["f"], rangos={"f": (1, 5)})


@pytest.mark.parametrize(
    "rango",
    [
        (0, 5),
        (10, 5),
        (-1, 5),
    ],
)
def test_rechaza_rangos_invalidos(rango: tuple[int, int]) -> None:
    """Rangos con inicio < 1 o fin < inicio se rechazan."""
    with pytest.raises(ValueError):
        comando_stryker("src/a.ts", ["f"], rangos={"f": rango})

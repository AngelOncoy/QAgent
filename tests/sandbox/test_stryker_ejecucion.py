"""Pruebas de ejecución de Stryker en el sandbox sin Docker (#179).

Verifica la orquestación del sandbox con Stryker simulando la ejecución en
Docker: límites de tiempo, configuración propia, timeout y lectura del informe.
"""

from pathlib import Path

import pytest

from qagent.sandbox.modelos import ResultadoSandbox
from qagent.sandbox.mutacion import CONFIG_PROPIA, ERROR, OK, TIEMPO_AGOTADO
from qagent.sandbox.stryker_ejecucion import ejecutar_stryker

FUENTE_TS = """export function calcular(a: number, b: number): number {
  if (a > 0) {
    return a + b;
  }
  return b;
}
"""

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "javascript"
    / "stryker-report.json"
)


@pytest.fixture
def proyecto_mock(tmp_path: Path):
    """Crea una estructura básica de proyecto TS y pruebas aprobadas."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    (proyecto / "package.json").write_text("{}", encoding="utf-8")
    src = proyecto / "src"
    src.mkdir()
    (src / "precios.ts").write_text(FUENTE_TS, encoding="utf-8")

    pruebas = tmp_path / "pruebas"
    pruebas.mkdir()
    (pruebas / "test.ts").write_text("// test", encoding="utf-8")

    return proyecto, pruebas


def test_ejecutar_stryker_flujo_exitoso(proyecto_mock, monkeypatch) -> None:
    """Simula una ejecución Docker exitosa que genera el informe de Stryker."""
    proyecto, pruebas = proyecto_mock
    reporte_contenido = FIXTURE_PATH.read_text(encoding="utf-8")

    def mock_ejecutar_en_sandbox(*args, **kwargs):
        al_terminar = kwargs.get("al_terminar")
        copia = args[2]
        salida = kwargs.get("salida", Path(args[2]).parent / "salida")
        salida.mkdir(parents=True, exist_ok=True)
        (salida / "mutation.json").write_text(reporte_contenido, encoding="utf-8")
        if al_terminar:
            al_terminar(copia, salida)

        return ResultadoSandbox(
            exit_code=0,
            stdout="Mutation testing complete",
            stderr="",
            comando=list(args[1]),
            limites=args[4],
            duracion_s=2.5,
        )

    monkeypatch.setattr(
        "qagent.sandbox.stryker_ejecucion.ejecutar_en_sandbox",
        mock_ejecutar_en_sandbox,
    )

    resultado = ejecutar_stryker(
        None,
        proyecto,
        pruebas,
        "src/precios.ts",
        ["calcular"],
    )

    assert resultado.modulo == "src/precios.ts"
    assert resultado.duracion_s == 2.5
    f = resultado.funciones["calcular"]
    assert f.estado == OK


def test_ejecutar_stryker_detecta_configuracion_propia(proyecto_mock) -> None:
    """Si el proyecto tiene stryker.config.json, devuelve estado config_propia."""
    proyecto, pruebas = proyecto_mock
    (proyecto / "stryker.config.json").write_text("{}", encoding="utf-8")

    resultado = ejecutar_stryker(
        None,
        proyecto,
        pruebas,
        "src/precios.ts",
        ["calcular"],
    )

    f = resultado.funciones["calcular"]
    assert f.estado == CONFIG_PROPIA
    assert "propia configuración" in (f.mensaje or "")


def test_ejecutar_stryker_maneja_tiempo_agotado(proyecto_mock, monkeypatch) -> None:
    """Si Docker termina por timed_out, la función queda en tiempo_agotado."""
    proyecto, pruebas = proyecto_mock

    def mock_timeout(*args, **kwargs):
        return ResultadoSandbox(
            exit_code=124,
            stdout="",
            stderr="Killed",
            comando=list(args[1]),
            limites=args[4],
            timed_out=True,
            duracion_s=120.0,
        )

    monkeypatch.setattr(
        "qagent.sandbox.stryker_ejecucion.ejecutar_en_sandbox",
        mock_timeout,
    )

    resultado = ejecutar_stryker(
        None,
        proyecto,
        pruebas,
        "src/precios.ts",
        ["calcular"],
    )

    f = resultado.funciones["calcular"]
    assert f.estado == TIEMPO_AGOTADO
    assert "agotó el tiempo" in (f.mensaje or "")


def test_ejecutar_stryker_maneja_salida_no_cero_sin_informe(
    proyecto_mock, monkeypatch
) -> None:
    """Si el runner falla técnicamente sin producir informe, queda en error."""
    proyecto, pruebas = proyecto_mock

    def mock_error(*args, **kwargs):
        return ResultadoSandbox(
            exit_code=1,
            stdout="",
            stderr="Cannot find module",
            comando=list(args[1]),
            limites=args[4],
            duracion_s=1.0,
        )

    monkeypatch.setattr(
        "qagent.sandbox.stryker_ejecucion.ejecutar_en_sandbox",
        mock_error,
    )

    resultado = ejecutar_stryker(
        None,
        proyecto,
        pruebas,
        "src/precios.ts",
        ["calcular"],
    )

    f = resultado.funciones["calcular"]
    assert f.estado == ERROR
    assert "código 1" in (f.mensaje or "")

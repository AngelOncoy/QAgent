"""#115: el tiempo de pytest sale de junit.xml, no del contenedor."""

from __future__ import annotations

from pathlib import Path

from qagent.sandbox import ResultadoSandbox, parsear_junit, resumir_ejecucion
from qagent.sandbox.modelos import LimitesSandbox

GRABACIONES = Path(__file__).parent / "grabaciones"
LIMITES = LimitesSandbox(cpus=1.0, memoria="1g", timeout_s=60)


def _xml() -> str:
    return (GRABACIONES / "mixto.junit.xml").read_text(encoding="utf-8")


def test_duracion_pytest_se_toma_de_junit() -> None:
    xml = _xml()
    salida = ResultadoSandbox(1, "", "", None, junit_xml=xml)

    resumen = resumir_ejecucion(
        salida,
        imagen="qagent-sandbox:base",
        comando=["pytest"],
        limites=LIMITES,
    )

    assert resumen["duracion_s"] == salida.duracion_s
    assert resumen["duracion_pytest_s"] == parsear_junit(xml).duracion_s


def test_sin_junit_la_duracion_de_pytest_es_null() -> None:
    salida = ResultadoSandbox(0, "1 passed", "", None)

    resumen = resumir_ejecucion(
        salida,
        imagen="qagent-sandbox:base",
        comando=["pytest"],
        limites=LIMITES,
    )

    assert resumen["duracion_pytest_s"] is None

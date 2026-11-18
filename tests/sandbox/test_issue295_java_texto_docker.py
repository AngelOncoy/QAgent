"""Generator → guardrail → JUnit real, con implementación correcta y defectuosa."""

from pathlib import Path

import pytest

from qagent.agents.generator import GeneratorAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import TokenTracker
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.sandbox.modelos import IMAGEN_JAVA, LimitesSandbox
from tests.agents.test_generator_java import ClienteJUnitGrabado
from tests.agents.test_issue295_java_texto import (
    CODIGO_CANONICO,
    casos_de_borde,
    preparar_texto,
)
from tests.lenguajes.test_issue295_java_texto import CODIGO_ORIGINAL

pytestmark = pytest.mark.docker


@pytest.mark.parametrize(
    "implementacion,codigo,fallos",
    [
        ("correcta", CODIGO_ORIGINAL, 0),
        ("correcta", CODIGO_CANONICO, 0),
        ("builder", CODIGO_CANONICO, 0),
        ("defectuosa", CODIGO_CANONICO, 1),
        ("nula", CODIGO_CANONICO, 1),
        ("bordes", "", 0),
    ],
    ids=[
        "original",
        "canonico",
        "stringbuilder",
        "contenido-incorrecto",
        "null-inesperado",
        "bordes",
    ],
)
def test_comparacion_textual_llega_a_junit_y_detecta_defectos(
    cliente_docker, tmp_path: Path, implementacion: str, codigo: str, fallos: int
) -> None:
    proyecto = tmp_path / "proyecto"
    contrato = preparar_texto(
        proyecto, "correcta" if implementacion == "bordes" else implementacion
    )
    if implementacion == "bordes":
        codigo = casos_de_borde(contrato)
    originales = {p: p.read_bytes() for p in proyecto.rglob("*") if p.is_file()}
    tracker = TokenTracker()
    generado = GeneratorAgent(
        ClienteJUnitGrabado(codigo), tracker, es_simulado=True, ruta_proyecto=proyecto
    ).generar(contrato, 1, None)
    adaptador = JavaAdapter()
    assert adaptador.validar_oraculo(contrato, generado["codigo"], proyecto) is None
    pruebas = tmp_path / "pruebas"
    archivo = pruebas / generado["archivo"]
    archivo.parent.mkdir(parents=True)
    archivo.write_text(generado["codigo"], encoding="utf-8")
    resultado = ejecutar_comando_pruebas(
        IMAGEN_JAVA,
        adaptador.comando_pruebas(contrato["modulo"]),
        proyecto,
        pruebas,
        leer_cobertura=adaptador.leer_cobertura,
        archivo_informe=adaptador.entorno_sandbox().informe,
        limites=LimitesSandbox(cpus=2, memoria="2g", timeout_s=120),
        cliente=cliente_docker,
        preparar=adaptador.preparador_sandbox(),
        leer_informe=adaptador.lector_informe_sandbox(),
    )
    informe = adaptador.interpretar_resultados(resultado.junit_xml or "")
    assert informe["total"] == len(contrato["casos"]), resultado.stdout
    assert informe["errores"] == informe["omitidos"] == 0, resultado.stdout
    assert informe["fallaron"] == fallos, resultado.stdout
    clasificacion = adaptador.clasificar_ejecucion(resultado)
    if fallos:
        assert clasificacion is not None
        assert clasificacion.tipo == "fallo_asercion"
    else:
        assert resultado.exit_code == 0
        assert clasificacion is None
    assert tracker.total_tokens == 0
    assert all(p.read_bytes() == contenido for p, contenido in originales.items())
    print(
        f"#295: {implementacion}; {informe['total']} JUnit reales; fallos={fallos}; originales intactos; 0 tokens"
    )

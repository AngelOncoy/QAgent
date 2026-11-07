"""#262: los omitidos conservan su lenguaje sin inventar pruebas ni veredictos."""

import copy
import json

import pytest

from qagent import contracts
from qagent.agents.planner import PlannerAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import FakeLLMClient, TokenTracker, cargar_precios
from qagent.orchestrator import Orquestador
from qagent.storage import escribir_corrida
from qagent.storage.exportar_informe import datos_informe
from qagent.storage.vista_ejecucion import omitidos_con_lenguaje, vista_ejecucion
from qagent.storage.vista_reporte import vista_reporte
from tests.orchestrator.fakes import GeneratorSimulado, ReviewerGuionado


def test_omision_java_conserva_lenguaje_en_archivo_vistas_e_informe(tmp_path) -> None:
    """Una respuesta sin casos permanece omitida y se identifica como Java."""
    (tmp_path / "Banco.java").write_text(
        "class Banco { public int f(int x) {return x;} }", encoding="utf-8"
    )
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    tracker = TokenTracker()
    planner = PlannerAgent(
        FakeLLMClient(grabaciones={"Banco.java::Banco.f": []}),
        tracker,
        es_simulado=True,
        adaptador=JavaAdapter(),
        perfil="humo",
    )
    resultado = Orquestador(
        planner,
        GeneratorSimulado(tracker),
        ReviewerGuionado(tracker, []),
        tracker=tracker,
    ).ejecutar(modulo)
    assert resultado.objetivos == []
    [omitido] = resultado.omitidos
    assert omitido["lenguaje"] == "java"
    rutas = escribir_corrida(
        tmp_path,
        resultado,
        tracker,
        cargar_precios(),
        "humo",
        omitidos=[{"modulo": "Banco.java", **omitido}],
    )
    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    contracts.validar(contracts.RUN_LOG, results)
    assert results["omitidos"][0]["lenguaje"] == "java"
    assert vista_ejecucion(results)["omitidos"][0]["lenguaje"] == "java"
    assert vista_reporte(results, None)["omitidos"][0]["lenguaje"] == "java"
    assert datos_informe(tmp_path, rutas.run_id)["omitidos"][0]["lenguaje"] == "java"
    assert tracker.total_tokens == 0

    # Compatibilidad: el metadato era opcional en corridas anteriores a #262.
    results["omitidos"][0].pop("lenguaje")
    contracts.validar(contracts.RUN_LOG, results)
    anterior = copy.deepcopy(results)
    assert vista_ejecucion(results)["omitidos"][0]["lenguaje"] == "java"
    assert vista_reporte(results, None)["omitidos"][0]["lenguaje"] == "java"
    assert results == anterior

    results["omitidos"][0]["lenguaje"] = "inexistente"
    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar(contracts.RUN_LOG, results)


@pytest.mark.parametrize(
    ("modulo", "lenguaje"),
    [
        ("Banco.java", "java"),
        ("banco.py", "python"),
        ("banco.ts", "typescript"),
        ("banco.js", "javascript"),
    ],
)
def test_recupera_omitidos_anteriores_con_el_registro(modulo, lenguaje) -> None:
    """Reconoce rutas históricas sin ejecutar código ni exigir que el archivo exista."""
    original = [
        {"modulo": modulo, "objetivo": "f", "tipo": "funcion", "motivo": "sin casos"}
    ]
    assert omitidos_con_lenguaje(original)[0]["lenguaje"] == lenguaje
    assert "lenguaje" not in original[0]


def test_lenguaje_explicito_se_conserva_y_desconocido_no_se_inventa() -> None:
    """La identidad persistida prevalece; una ruta desconocida no se llama Python."""
    assert (
        omitidos_con_lenguaje([{"modulo": "sin-extension", "lenguaje": "java"}])[0][
            "lenguaje"
        ]
        == "java"
    )
    assert "lenguaje" not in omitidos_con_lenguaje([{"modulo": "sin-extension"}])[0]

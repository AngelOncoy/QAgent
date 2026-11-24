"""Objetivos Java no ejecutables no consumen Planner ni Generator (#301).

Con proveedores simulados y grabados: cero tokens, sin Docker ni red. El esperado
de los casos sale de la grabación, nunca de ejecutar Java.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qagent.agents.planner import PlannerAgent
from qagent.config import cargar_configuracion
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.base import ResultadoConstruccion
from qagent.llm import FakeLLMClient, RespuestaLLM, TokenTracker
from qagent.orchestrator import corrida
from qagent.orchestrator.orquestador import Orquestador
from qagent.sandbox.modelos import ResultadoSandbox
from tests.agents.test_generator_java import CODIGO
from tests.lenguajes.test_issue305_construccion_java import POM

BANCO = """package ejemplo;
public class Banco {
    /** Devuelve el doble. @return dos veces x */
    public static int duplicar(int x) { return x * 2; }
    /** Regla del banco. */
    public interface Regla {
        /** @return el valor de la regla */
        int valor();
    }
}
"""
FORMA = """package ejemplo;
public abstract class Forma {
    /** @return el área */
    public abstract double area();
    /** @return 1 */
    public int uno() { return 1; }
}
"""
CASOS = [
    {
        "id": "positivo",
        "entrada": {"x": 2},
        "valor_esperado": 4,
        "origen": "docstring",
        "categoria": "normal",
    }
]
GRABACIONES = {
    "Banco.java::Banco.duplicar": CASOS,
    # Si el filtro fallara, el modelo simulado sí respondería por estos objetivos.
    "Banco.java::Banco.Regla.valor": CASOS,
    "Forma.java::Forma.uno": CASOS,
}


def _proyecto(raiz: Path) -> dict[str, dict]:
    carpeta = raiz / "src/main/java/ejemplo"
    carpeta.mkdir(parents=True)
    (carpeta / "Banco.java").write_text(BANCO, encoding="utf-8")
    (carpeta / "Forma.java").write_text(FORMA, encoding="utf-8")
    (raiz / "pom.xml").write_text(POM, encoding="utf-8")
    return {
        m["ruta"].rsplit("/", 1)[-1]: m for m in JavaAdapter().analizar(raiz)["modulos"]
    }


class ClienteContado(FakeLLMClient):
    """Registra rol y prompt de cada llamada; el Generator devuelve un JUnit grabado."""

    def __init__(self) -> None:
        super().__init__(grabaciones=GRABACIONES)
        self.llamadas: list[tuple[str, str]] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.llamadas.append((rol, prompt))
        if rol == "generator":
            return RespuestaLLM(
                contenido=CODIGO,
                modelo="fake-java",
                tokens_entrada=0,
                tokens_salida=0,
                costo_usd=0,
            )
        return super().generar(prompt, rol)


def _planner(cliente: ClienteContado) -> PlannerAgent:
    return PlannerAgent(
        cliente, TokenTracker(), es_simulado=True, adaptador=JavaAdapter()
    )


def test_modulo_sin_objetivos_ejecutables_no_llama_al_planner(tmp_path: Path) -> None:
    modulos = _proyecto(tmp_path)
    cliente = ClienteContado()
    planner = _planner(cliente)

    assert planner.planificar(modulos["Forma.java"]) == []

    assert cliente.llamadas == []
    assert "abstracta sin cuerpo" in planner.omitidas["Forma.area"]
    assert "subclase concreta" in planner.omitidas["Forma.uno"]


def test_modulo_mixto_solo_envia_los_ejecutables(tmp_path: Path) -> None:
    modulos = _proyecto(tmp_path)
    cliente = ClienteContado()
    planner = _planner(cliente)

    plan = planner.planificar(modulos["Banco.java"])

    assert [c["objetivo"] for c in plan] == ["Banco.duplicar"]
    [(rol, prompt)] = cliente.llamadas
    assert rol == "planner"
    assert "Banco.duplicar" in prompt
    assert "Banco.Regla.valor" not in prompt
    assert "abstracta sin cuerpo" in planner.omitidas["Banco.Regla.valor"]
    # La inferencia sin Javadoc tampoco recibe objetivos no ejecutables.
    assert "Banco.Regla.valor" not in json.dumps(plan)


def test_spec_antigua_no_lleva_un_objetivo_no_ejecutable_al_generator(
    tmp_path: Path,
) -> None:
    modulos = _proyecto(tmp_path)
    forma = modulos["Forma.java"]
    funcion = next(f for f in forma["funciones"] if f["nombre"] == "Forma.uno")
    antiguo = {
        "version": "3",
        "lenguaje": "java",
        "framework_pruebas": "junit5",
        "modulo": forma["ruta"],
        "huella": forma["huella"],
        "tipo": "funcion",
        "objetivo": "Forma.uno",
        "firma": funcion["firma"],
        "critical": False,
        "llama_a": [],
        "casos": [{**CASOS[0], "entrada": {}, "valor_esperado": 1}],
    }
    generator = MagicMock()
    orquestador = Orquestador(
        planner=_planner(ClienteContado()),
        generator=generator,
        reviewer=MagicMock(),
        tracker=TokenTracker(),
    )

    plan = orquestador.planificar(forma, plan_reutilizado=[antiguo])

    assert plan.error is None
    assert plan.contratos == []
    assert "subclase concreta" in plan.motivos_omision["Forma.uno"]
    assert "abstracta sin cuerpo" in plan.motivos_omision["Forma.area"]
    generator.generar.assert_not_called()


@pytest.fixture
def cliente_de_corrida(monkeypatch) -> ClienteContado:
    cliente = ClienteContado()
    monkeypatch.setattr(corrida, "crear_cliente", lambda *a, **k: cliente)
    return cliente


def test_corrida_omite_con_motivo_y_solo_genera_lo_ejecutable(
    tmp_path: Path, cliente_de_corrida: ClienteContado
) -> None:
    _proyecto(tmp_path)
    junit = (
        '<testsuite tests="1" failures="0" errors="0" skipped="0">'
        '<testcase name="test_positivo" classname="ejemplo.BancoTest" time="0.01"/>'
        "</testsuite>"
    )

    resultado = corrida.ejecutar_corrida(
        tmp_path,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda r: "imagen-simulada",
        validar_construccion=lambda *a, **k: ResultadoConstruccion(
            "aprobado", "aprobado", "Construcción aprobada"
        ),
        ejecutor=lambda *a, **k: ResultadoSandbox(0, "", "", junit_xml=junit),
    )

    roles = [rol for rol, _ in cliente_de_corrida.llamadas]
    prompts_planner = [p for r, p in cliente_de_corrida.llamadas if r == "planner"]
    assert roles.count("planner") == 1, "Forma.java no debe llegar al Planner"
    assert "Forma." not in prompts_planner[0]
    assert roles.count("generator") == 1
    assert resultado.aceptadas == 1, resultado.motivo
    assert resultado.objetivos_omitidos == 3
    assert resultado.tokens == 0

    results = json.loads(
        (tmp_path / ".qagent/runs" / resultado.run_id / "results.json").read_text(
            encoding="utf-8"
        )
    )
    motivos = {o["objetivo"]: o["motivo"] for o in results["omitidos"]}
    assert set(motivos) == {"Banco.Regla.valor", "Forma.area", "Forma.uno"}
    assert "abstracta sin cuerpo" in motivos["Forma.area"]
    assert "subclase concreta" in motivos["Forma.uno"]

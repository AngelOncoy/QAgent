"""Componentes React en el orquestador, la selección y la corrida (#171).

Sin Docker ni red: el Planner y el Generator usan la IA simulada y el Reviewer es
guionado. La ejecución real está en ``tests/sandbox/test_react_corrida_docker.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.javascript_componentes import MOTIVO_SIN_ORACULO
from qagent.llm import TokenTracker, cargar_precios
from qagent.llm.fake import FakeLLMClient
from qagent.orchestrator import Orquestador
from qagent.orchestrator.corrida import omitidos_de_interfaz
from qagent.proyectos.seleccion import SeleccionInvalida, filtrar_modulos
from qagent.storage import escribir_corrida
from tests.lenguajes.test_banco_react import BANCO, GRABACIONES
from tests.orchestrator.fakes import ReviewerGuionado


def _modulos() -> dict[str, dict]:
    return {m["ruta"]: m for m in TypeScriptAdapter().analizar(BANCO)["modulos"]}


def _orquestador(decisiones: list[str]) -> Orquestador:
    tracker = TokenTracker()
    return Orquestador(
        PlannerAgent(
            FakeLLMClient(grabaciones=GRABACIONES),
            tracker,
            es_simulado=True,
            adaptador=TypeScriptAdapter(),
        ),
        GeneratorAgent(
            FakeLLMClient(grabaciones={}),
            tracker,
            es_simulado=True,
            ruta_proyecto=BANCO,
        ),
        ReviewerGuionado(tracker, decisiones),
        tracker=tracker,
    )


def test_orquestador_planifica_y_revisa_componentes(tmp_path: Path) -> None:
    resultado = _orquestador(["accept"]).ejecutar(_modulos()["src/Boton.tsx"])
    [objetivo] = resultado.objetivos
    assert objetivo.objetivo == "Boton"
    assert objetivo.contrato["tipo"] == "componente"
    assert objetivo.decision == "accept"
    rutas = escribir_corrida(
        tmp_path, [resultado], TokenTracker(), cargar_precios(), "std"
    )
    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    assert results["objetivos"][0]["tipo"] == "componente"


def test_componente_sin_oraculo_queda_omitido_y_se_registra(tmp_path: Path) -> None:
    resultado = _orquestador([]).ejecutar(_modulos()["src/Libre.tsx"])
    assert resultado.objetivos == []
    assert resultado.omitidos == [
        {
            "objetivo": "Libre",
            "tipo": "componente",
            "lenguaje": "typescript",
            "motivo": MOTIVO_SIN_ORACULO[0].upper() + MOTIVO_SIN_ORACULO[1:] + ".",
        }
    ]
    rutas = escribir_corrida(
        tmp_path,
        [resultado],
        TokenTracker(),
        cargar_precios(),
        "std",
        omitidos=[{"modulo": "src/Libre.tsx", **o} for o in resultado.omitidos],
    )
    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    assert results["omitidos"][0]["tipo"] == "componente"


# --- Selección -----------------------------------------------------------------------


def test_seleccion_admite_componentes_por_nombre() -> None:
    modulos = list(_modulos().values())
    [boton] = filtrar_modulos(
        modulos, [{"ruta": "src/Boton.tsx", "componentes": ["Boton"]}]
    )
    assert [c["nombre"] for c in boton["componentes"]] == ["Boton"]
    assert boton["funciones"] == []
    assert "src/Boton.tsx" in {m["ruta"] for m in filtrar_modulos(modulos, None)}


def test_seleccion_rechaza_componentes_inexistentes() -> None:
    with pytest.raises(SeleccionInvalida, match="Fantasma"):
        filtrar_modulos(
            list(_modulos().values()),
            [{"ruta": "src/Boton.tsx", "componentes": ["Fantasma"]}],
        )


# --- Frameworks no soportados (CA6) -------------------------------------------------


def test_omitidos_de_interfaz_con_componentes_jsx(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"preact": "10.0.0"}}), encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Vista.jsx").write_text(
        "export function Vista() { return <i />; }\n"
        "/** @returns {number} @example doble(2) // => 4 */\n"
        "export const doble = (x) => x * 2;\n",
        encoding="utf-8",
    )
    analisis = JavaScriptAdapter().analizar(tmp_path)
    [modulo] = analisis["modulos"]
    assert "componentes" not in modulo
    assert [c["nombre"] for c in modulo["componentes_no_soportados"]] == ["Vista"]
    assert [f["nombre"] for f in modulo["funciones"]] == ["doble"]

    [omitido] = omitidos_de_interfaz(analisis)
    assert omitido["modulo"] == "src/Vista.jsx"
    assert omitido["tipo"] == "componente"
    assert omitido["motivo"].startswith("Componentes no soportados (Preact)")


def test_omitidos_de_interfaz_sin_componentes_analizables(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"astro": "5.0.0"}}), encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "util.ts").write_text(
        "export const f = (x: number): number => x;\n", encoding="utf-8"
    )
    [omitido] = omitidos_de_interfaz(TypeScriptAdapter().analizar(tmp_path))
    assert omitido == {
        "modulo": "package.json",
        "objetivo": "Componentes de Astro",
        "tipo": "componente",
        "motivo": "Componentes no soportados (Astro): QAgent prueba solo los archivos "
        "de lógica .ts/.js de este proyecto.",
    }


def test_react_no_genera_omitidos_de_interfaz() -> None:
    assert omitidos_de_interfaz(TypeScriptAdapter().analizar(BANCO)) == []
    assert omitidos_de_interfaz({"modulos": []}) == []

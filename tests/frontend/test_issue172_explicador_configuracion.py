"""EP-10 (#172): Configuración muestra la etapa del Explicador para agregar su API."""

from __future__ import annotations

from pathlib import Path

from qagent.llm.precios import AGENTES

RAIZ = Path(__file__).resolve().parents[2]
CONFIGURACION = (
    RAIZ / "src" / "qagent" / "frontend" / "componentes" / "configuracion"
) / "configuracion.js"


def _js() -> str:
    return CONFIGURACION.read_text(encoding="utf-8")


def test_cada_agente_tiene_nombre_de_etapa_para_personas() -> None:
    js = _js()
    etapas = js[js.index("const ETAPA = {") : js.index("};", js.index("const ETAPA"))]

    for agente in AGENTES:
        assert f"{agente}:" in etapas, agente
    assert "Explicando resultados" in etapas


def test_la_demostracion_lista_las_cuatro_etapas() -> None:
    lista = ", ".join(f"'{a}'" for a in AGENTES).replace(", ", ",")
    assert f"[{lista}]" in _js()

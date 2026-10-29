"""Pruebas de las funciones puras de scripts/sincronizar_notion.py (sin red)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "scripts" / "sincronizar_notion.py"
_spec = importlib.util.spec_from_file_location("sincronizar_notion", RUTA)
sn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sn)


def _issue(**cambios):
    base = {
        "number": 7,
        "title": "HU - Ver el historial",
        "url": "https://github.com/AngelOncoy/QAgent/issues/7",
        "state": "OPEN",
        "createdAt": "2026-10-28T10:00:00Z",
        "closedAt": None,
        "body": "### Descripción\nTexto.\n---\n### Criterios de Aceptación\n- [ ] Uno",
        "labels": {"nodes": [{"name": "HU"}]},
        "assignees": {"nodes": [{"login": "AngelOncoy"}]},
        "parent": None,
    }
    base.update(cambios)
    return base


@pytest.mark.parametrize(
    ("titulo", "etiquetas", "esperado"),
    [
        ("EN-21 - Alinear el contrato", [], ("EN", "EN - Alinear el contrato")),
        ("HU - Ver el historial", [], ("HU", "HU - Ver el historial")),
        ("Fix: aislar las pruebas", [], ("FIX", "FIX - Aislar las pruebas")),
        ("FIX/UI — Recuperar Humo", [], ("FIX", "FIX - Recuperar Humo")),
        ("Feat: nueva vista", [], ("TA", "TA - Nueva vista")),
        ("BU: la corrida se detiene", [], ("BU", "BU - La corrida se detiene")),
        ("TA-01 - Banco Java", [], ("TA", "TA - Banco Java")),
        (
            "EP-14 - Verificar correcciones",
            [],
            ("Épica", "EP-14 · Verificar correcciones"),
        ),
        ("Algo sin prefijo", ["SPK"], ("SPK", "SPK - Algo sin prefijo")),
    ],
)
def test_normalizar_titulo(titulo, etiquetas, esperado):
    assert sn.normalizar_titulo(titulo, etiquetas) == esperado


def test_descripcion_y_criterios_con_secciones_markdown():
    desc, crit = sn.descripcion_y_criterios(_issue()["body"])
    assert desc == "Texto."
    assert crit == "- [ ] Uno"


def test_descripcion_usa_problema_y_objetivo_si_no_hay_descripcion():
    cuerpo = "## Problema\nFalla X.\n## Objetivo\nArreglar X.\n## Criterios de aceptación\n- [ ] Y"
    desc, crit = sn.descripcion_y_criterios(cuerpo)
    assert desc == "Falla X.\n\nArreglar X."
    assert crit == "- [ ] Y"


def test_descripcion_desde_html():
    cuerpo = "<h3>Descripción</h3><p>Hola</p><h3>Criterios de aceptación</h3><ul><li>A</li></ul>"
    desc, crit = sn.descripcion_y_criterios(cuerpo)
    assert desc == "Hola"
    assert crit == "- A"


def test_texto_notion_parte_en_bloques_de_2000():
    bloques = sn.texto_notion("a" * 4500)
    assert [len(b["text"]["content"]) for b in bloques] == [2000, 2000, 500]


def test_fila_nueva_abierta():
    props = sn.propiedades(_issue(), None, None, "Sprint 2")
    assert props["Status"]["select"]["name"] == sn.ABIERTO
    assert props["Sprint"]["select"]["name"] == "Sprint 2"
    assert props["Fecha Inicio"]["date"] == {"start": "2026-10-28"}
    assert "Fecha Fin" not in props
    assert props["Responsable"]["people"] == [{"id": sn.EQUIPO["AngelOncoy"]}]


def test_fila_nueva_con_epica():
    padre = {"number": 198, "title": "EP-14 - X", "url": "u"}
    props = sn.propiedades(_issue(parent=padre), None, "id-epica", "Sprint 2")
    assert props["Épica"]["relation"] == [{"id": "id-epica"}]
    assert props["Tipo PBI"]["select"]["name"] == "Epica 14"


def test_responsable_fuera_del_equipo_no_se_toca():
    issue = _issue(assignees={"nodes": [{"login": "AlejoCY"}]})
    assert "Responsable" not in sn.propiedades(issue, None, None, "Sprint 2")


def test_fila_existente_no_pisa_doing():
    actual = {
        "Status": {"select": {"name": "Doing (En curso)"}},
        "Fecha Fin": {"date": None},
    }
    props = sn.propiedades(_issue(), actual, None, "Sprint 2")
    assert "Status" not in props
    assert "Sprint" not in props
    assert "Fecha Inicio" not in props


def test_fila_existente_cerrada_solo_cambia_estado_y_fecha():
    actual = {
        "Status": {"select": {"name": "Doing (En curso)"}},
        "Fecha Fin": {"date": None},
    }
    issue = _issue(state="CLOSED", closedAt="2026-10-30T12:00:00Z")
    props = sn.propiedades(issue, actual, None, "Sprint 2")
    assert props == {
        "Status": {"select": {"name": sn.CERRADO}},
        "Fecha Fin": {"date": {"start": "2026-10-30"}},
    }


def test_reabrir_vuelve_a_abierto_y_borra_fecha_fin():
    actual = {
        "Status": {"select": {"name": sn.CERRADO}},
        "Fecha Fin": {"date": {"start": "x"}},
    }
    props = sn.propiedades(_issue(), actual, None, "Sprint 2")
    assert props["Status"]["select"]["name"] == sn.ABIERTO
    assert props["Fecha Fin"] == {"date": None}

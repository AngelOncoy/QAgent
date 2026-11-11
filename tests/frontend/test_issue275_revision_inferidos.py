"""Estructura de la interfaz para el contrato inferido (#275, ADR-015)."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def test_el_modal_de_revision_esta_montado_en_el_index() -> None:
    index = leer("index.html")

    assert 'data-componente="revision/modal-revision-inferidos"' in index
    assert (
        '<script src="componentes/revision/modal-revision-inferidos.js"></script>'
        in index
    )
    assert "registrarComponente('revision/modal-revision-inferidos'" in leer(
        "componentes/revision/modal-revision-inferidos.js"
    )


def test_el_evento_de_revision_llega_al_modal() -> None:
    assert "revision_inferidos" in leer("js/puente-python.js")
    assert "abrirRevisionInferidos" in leer("js/puente-python.js")


def test_el_modal_responde_a_python_y_no_se_cierra_solo() -> None:
    modal = leer("componentes/revision/modal-revision-inferidos.js")

    assert "responder_revision_inferidos" in modal
    # Si se cerrara al hacer clic fuera, la corrida quedaría esperando sin salida.
    assert "stopImmediatePropagation" in modal


def test_preparar_ofrece_inferir_y_revisar_y_los_envia_a_la_corrida() -> None:
    preparar = leer("componentes/config-pruebas/config-pruebas.js")
    monitor = leer("componentes/monitor/monitor.js")

    assert "Inferir funciones sin docstring" in preparar
    assert "Revisar contratos inferidos" in preparar
    assert "tokInferidas" in preparar  # la estimación va aparte
    assert "INFERIR_SIN_DOCSTRING && REVISAR_INFERIDOS" in monitor

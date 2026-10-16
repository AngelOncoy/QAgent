"""Contrato frontend de la corrección de proyectos recientes (issue #61)."""

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"
MODAL = (FRONTEND / "componentes" / "inicio" / "modal-clonar.js").read_text(
    encoding="utf-8"
)
INICIO = (FRONTEND / "componentes" / "inicio" / "inicio.js").read_text(encoding="utf-8")


def _fin_clonado() -> str:
    return MODAL[MODAL.index("async function finClonado") :]


def test_clonado_exitoso_actualiza_recientes_antes_de_abrir_vista_previa() -> None:
    cuerpo = _fin_clonado()

    assert "await cargarRecientes()" in cuerpo
    assert cuerpo.index("await cargarRecientes()") < cuerpo.index("loadProject(")
    assert "loadProject(nombreRepo(url), 'git', url, br, r.destino)" in cuerpo


def test_error_de_clonado_no_actualiza_recientes() -> None:
    cuerpo = _fin_clonado()
    rama_error, rama_exito = cuerpo.split("$('cloneTitle').textContent = 'Listo'", 1)

    assert "if(!r.ok)" in rama_error
    assert "return;" in rama_error
    assert "cargarRecientes" not in rama_error
    assert "await cargarRecientes()" in rama_exito


def test_advertencia_de_persistencia_no_impide_la_navegacion_y_se_escapa() -> None:
    cuerpo = _fin_clonado()

    assert "if(r.advertencia)" in cuerpo
    assert "escHtml(r.advertencia)" in cuerpo
    assert "loadProject(" in cuerpo


def test_renderizado_de_recientes_actualiza_lista_y_contador() -> None:
    assert "renderRecientes();" in INICIO
    assert "$('recCount').textContent = RECIENTES.length" in INICIO
    assert "$('recList').innerHTML = RECIENTES.map" in INICIO

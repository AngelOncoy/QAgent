"""Regresiones del alcance de Vista previa y del selector para Clonar."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def test_archivos_vacios_quedan_desmarcados_deshabilitados_y_atenuados() -> None:
    js = leer("componentes/vista-previa/vista-previa.js")
    css = leer("componentes/vista-previa/vista-previa.css")

    assert "sel: tieneObjetivos" in js
    assert "m.sel = false" in js
    assert "'disabled'" in js
    assert "sin objetivos analizables" in js
    assert ".tree .row.no-targets" in css


def test_funciones_y_endpoints_habilitan_modulo_y_seleccionar_todos_ignora_vacios() -> (
    None
):
    js = leer("componentes/vista-previa/vista-previa.js")

    assert "fns.length > 0 || endpoints.length > 0" in js
    assert "function seleccionarTodosModulos" in js
    assert "m.sel = moduloTieneObjetivos(m) && seleccionado" in js
    assert "const totalObjetivos" in js


def test_seleccion_persiste_y_se_envia_al_backend() -> None:
    vista = leer("componentes/vista-previa/vista-previa.js")
    monitor = leer("componentes/monitor/monitor.js")

    assert "function obtenerSeleccionObjetivos" in vista
    assert "filter(f => f.inc).map(f => f.n)" in vista
    assert "start_run(projectPath, profile, obtenerSeleccionObjetivos())" in monitor


def test_examinar_usa_selector_nativo_sin_clonar_y_conserva_cancelacion() -> None:
    js = leer("componentes/inicio/modal-clonar.js")
    cuerpo = js[
        js.index("async function examinarDestinoClonado") : js.index("function doClone")
    ]

    assert "Examinar…" in js
    assert "await api.select_folder()" in cuerpo
    assert "if(!carpetaPadre) return" in cuerpo
    assert "destinoEnCarpeta(String(carpetaPadre), nombreRepo(url))" in cuerpo
    assert "clonar_repositorio" not in cuerpo


def test_destino_sigue_editable_y_clonacion_usa_rama_y_modo_superficial() -> None:
    js = leer("componentes/inicio/modal-clonar.js")

    assert 'oninput="dirEditado=true;vUrl()"' in js
    assert (
        "const url = $('url').value, br = $('branch').value, dir = $('dir').value.trim(), shallow = $('shallow').checked"
        in js
    )
    assert "clonar_repositorio(url, br, dir, shallow)" in js

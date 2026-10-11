"""Regresiones estructurales para el FIX de interfaces de QAgent."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "frontend"


def _leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def test_las_vistas_desplazables_pueden_reducirse_dentro_del_main() -> None:
    estilos = _leer("css/layout.css")

    regla_scroll = estilos[
        estilos.index(".scroll{") : estilos.index("}", estilos.index(".scroll{"))
    ]

    assert "min-width:0" in regla_scroll
    assert "min-height:0" in regla_scroll
    assert "overflow:auto" in regla_scroll


def test_inicio_no_fuerza_una_altura_que_centre_contenido_fuera_de_la_ventana() -> None:
    estilos = _leer("componentes/inicio/inicio.css")

    regla_inicio = estilos[
        estilos.index(".welcome{") : estilos.index("}", estilos.index(".welcome{"))
    ]

    assert "min-height:100%" in regla_inicio
    assert regla_inicio.startswith(".welcome{min-height:100%")


def test_historial_envuelve_sus_tablas_en_contenedores_desplazables() -> None:
    historial = _leer("componentes/historial/historial.js")
    estilos = _leer("css/componentes.css")

    assert historial.count('<div class="table-scroll"><table>') == 2
    assert ".table-scroll{max-width:100%;overflow-x:auto}" in estilos


def test_vista_previa_se_compacta_en_ventanas_de_poca_altura() -> None:
    estilos = _leer("componentes/vista-previa/vista-previa.css")

    assert "@media(max-height:700px)" in estilos
    assert "#s-preview .page" in estilos


def test_guia_de_uso_se_muestra_como_no_disponible() -> None:
    sidebar = _leer("componentes/sidebar/sidebar.js")
    opcion = sidebar[sidebar.index('title="No disponible en esta versión"') :]
    opcion = opcion[: opcion.index("</a>")]

    assert 'aria-disabled="true"' in sidebar
    assert 'class="off"' in sidebar
    assert "No disponible" in opcion
    assert "onclick=" not in opcion


def test_monitor_envuelve_el_resumen_y_recorta_las_rutas_largas() -> None:
    monitor = _leer("componentes/monitor/monitor.css")
    logica_monitor = _leer("componentes/monitor/monitor.js")
    barra = _leer("componentes/barra-corrida/barra-corrida.css")
    ejecucion = _leer("componentes/ejecucion/ejecucion.css")

    assert ".monwrap{width:100%;max-width:900px;min-width:0" in monitor
    assert ".nextbox{display:flex;align-items:center;gap:12px;flex-wrap:wrap" in monitor
    assert ".nextbox>span{flex:1 1 100%;min-width:0" in monitor
    assert "overflow-wrap:anywhere" in monitor
    assert ".mon-top{flex-wrap:wrap;min-width:0}" in barra
    assert (
        ".repoLbl{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis}"
        in barra
    )
    assert 'style="margin-left:auto"' not in logica_monitor
    assert "style.marginLeft = 'auto'" not in logica_monitor
    assert ".nextbox{" not in ejecucion

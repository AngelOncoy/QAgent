"""Regresiones estructurales para el FIX de interfaces de QAgent."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


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


def test_proyecto_actual_e_historial_empiezan_deshabilitados_sin_proyecto() -> None:
    """Sin proyecto abierto, Proyecto actual e Historial se ven pero no se pueden abrir."""
    sidebar = _leer("componentes/sidebar/sidebar.js")

    for destino in ("proyecto", "history"):
        posicion = sidebar.index(f'data-h="{destino}"')
        enlace = sidebar[sidebar.rindex("<a ", 0, posicion) :]
        enlace = enlace[: enlace.index("</a>")]
        assert 'class="off"' in enlace
        assert 'aria-disabled="true"' in enlace
    # Solo se habilitan cuando hay un proyecto abierto
    assert "habilitarEnlace(a, !!vistaProyecto)" in sidebar


def test_monitor_envuelve_el_resumen_y_recorta_las_rutas_largas() -> None:
    # Rediseño «En curso»: el contenido tiene un ancho máximo centrado y los textos largos
    # (funciones y archivos de la actividad) se cortan dentro de su caja. La barra de corrida ya no existe.
    monitor = _leer("componentes/monitor/monitor.css")
    logica_monitor = _leer("componentes/monitor/monitor.js")
    ejecucion = _leer("componentes/ejecucion/ejecucion.css")

    assert "#s-monitor .page.prg{width:100%;max-width:var(--contenido-max)" in monitor
    assert (
        ".prg-actividad b{display:block;font-weight:var(--peso-medio);overflow-wrap:anywhere}"
        in monitor
    )
    assert ".prg-actual-nombre{" in monitor and "overflow-wrap:anywhere" in monitor
    assert 'style="margin-left:auto"' not in logica_monitor
    assert "style.marginLeft = 'auto'" not in logica_monitor
    assert ".nextbox{" not in ejecucion


def test_pasos_del_proyecto_se_desbloquean_secuencialmente() -> None:
    pasos = _leer("componentes/pasos-proyecto/pasos-proyecto.js")
    vista_previa = _leer("componentes/vista-previa/vista-previa.js")
    config_pruebas = _leer("componentes/config-pruebas/config-pruebas.js")
    monitor = _leer("componentes/monitor/monitor.js")

    # Al inicio, solo Explorar (Vista previa) y Preparar (Configuración de pruebas) están disponibles
    assert '<a data-v="preview">' in pasos
    assert '<a data-v="tests">' in pasos
    assert '<a data-v="monitor" class="hide off">' in pasos
    assert '<a data-v="exec" class="hide off">' in pasos
    # El informe dejó de ser un paso: el recorrido termina en Resultados (exec).
    assert 'data-v="report"' not in pasos

    # Funciones de control de la secuencia
    assert "function desbloquearVista(" in pasos
    assert "function reiniciarVistasProyecto(" in pasos

    # Al cargar un proyecto (local o git), se reinicia el flujo
    assert "reiniciarVistasProyecto()" in vista_previa

    # Escoger un perfil en configuración de pruebas desbloquea el Monitor
    assert "desbloquearVista('monitor')" in config_pruebas

    # Al terminar la corrida en el monitor, se desbloquean ejecución e historial
    assert "desbloquearVista('exec')" in monitor
    assert "desbloquearVista('history')" in monitor

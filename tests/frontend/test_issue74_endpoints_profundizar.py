"""#74: Decisiones y Profundizar en la tabla de endpoints, y su envío y conteo."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"
VISTA_JS = (FRONTEND / "componentes" / "vista-previa" / "vista-previa.js").read_text(
    encoding="utf-8"
)
CONFIG_JS = (
    FRONTEND / "componentes" / "config-pruebas" / "config-pruebas.js"
).read_text(encoding="utf-8")


def cuerpo(js: str, inicio: str) -> str:
    desde = js.index(inicio)
    return js[desde : js.index("\n}\n", desde)]


def test_cada_endpoint_trae_sus_decisiones_y_la_marca_propuesta() -> None:
    assert "br: e.ramas || 0," in VISTA_JS
    assert "crit: e.critica_propuesta ?? ((e.ramas || 0) > 0)," in VISTA_JS


def test_la_tabla_muestra_decisiones_y_una_marca_editable() -> None:
    render = cuerpo(VISTA_JS, "function renderEndpoints")
    assert '<td class="mono">${e.br}</td>' in render
    assert 'onclick="toggleEndpointCrit(${mi},${ei})"' in render
    assert "Se aplica si activas Profundizar en la configuración de pruebas." in render
    marca = cuerpo(VISTA_JS, "function toggleEndpointCrit")
    assert "e.crit = !e.crit;" in marca
    assert "e.inc" not in marca  # Profundizar no altera Incluir


def test_la_seleccion_envia_los_endpoints_marcados_e_incluidos() -> None:
    seleccion = cuerpo(VISTA_JS, "function obtenerSeleccionObjetivos")
    assert (
        "(m.endpoints || []).filter(e => endpointElegible(e) && e.inc && e.crit)"
        ".map(e => e.objetivo)"
    ) in seleccion


def test_la_configuracion_cuenta_funciones_y_endpoints_prioritarios() -> None:
    calc = cuerpo(CONFIG_JS, "function calc()")
    assert "const epsPrioritarios = estStd.endpoints.filter(e=>e.crit).length;" in calc
    assert (
        "const prioritarias = estStd.fns.filter(f=>f.crit).length + epsPrioritarios;"
        in calc
    )
    texto = cuerpo(CONFIG_JS, "function textoPrioritarias")
    assert "y ${ep} prioritarios" in texto
    assert "textoPrioritarias(prioritarias - epsPrioritarios, epsPrioritarios)" in (
        cuerpo(CONFIG_JS, "function renderOpcionesPruebas")
    )

"""Contrato funcional y estructural del selector Funciones/Endpoints (issue #66).

Comprueba, sin backend ni navegador, el selector de tipo de objetivo, la nueva tabla de
endpoints (Calidad, Estado, Respuesta, Errores, Simula, Incluir), la agrupación por
archivo con plegado propio, la selección y el envío al backend. Cuando hay Node
disponible, además ejecuta las funciones puras reales sobre datos simulados (no solo
busca texto): la lógica no puede quedar «bien escrita pero mal calculada».
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"
VISTA_JS_PATH = FRONTEND / "componentes" / "vista-previa" / "vista-previa.js"
CONFIG_JS_PATH = FRONTEND / "componentes" / "config-pruebas" / "config-pruebas.js"

VISTA_JS = VISTA_JS_PATH.read_text(encoding="utf-8")
CONFIG_JS = CONFIG_JS_PATH.read_text(encoding="utf-8")
ESTADO_JS = (FRONTEND / "js" / "estado.js").read_text(encoding="utf-8")
VISTA_CSS = (FRONTEND / "componentes" / "vista-previa" / "vista-previa.css").read_text(
    encoding="utf-8"
)
TOKENS = (FRONTEND / "css" / "tokens.css").read_text(encoding="utf-8")


def cuerpo(nombre_funcion: str) -> str:
    """Cuerpo (sin la firma) de una función de varias líneas."""
    inicio = VISTA_JS.index(f"function {nombre_funcion}")
    return VISTA_JS[inicio : VISTA_JS.index("\n}", inicio)]


def _encabezados_endpoints() -> list[str]:
    bloque = VISTA_JS[VISTA_JS.index('<table class="ep-table">') :]
    thead = bloque[: bloque.index("</thead>")]
    return [
        texto.strip()
        for texto in re.findall(r"<th[^>]*>(.*?)</th>", thead, re.DOTALL)
        if '<span class="vh"' not in texto
    ]


def _columnas_tooltips() -> list[str]:
    bloque = VISTA_JS[VISTA_JS.index('<table class="ep-table">') :]
    thead = bloque[: bloque.index("</thead>")]
    return re.findall(r'data-tip="([^"]+)"', thead)


# ---------------- 1-5. Selector de tipo de objetivo ----------------


def test_existe_un_selector_con_dos_vistas() -> None:
    for marca in (
        'id="tabFns"',
        'id="tabEps"',
        'id="vistaFns"',
        'id="vistaEps"',
        "onclick=\"cambiarVistaObjetivos('funciones')\"",
        "onclick=\"cambiarVistaObjetivos('endpoints')\"",
    ):
        assert marca in VISTA_JS
    assert "function cambiarVistaObjetivos" in VISTA_JS
    assert "function aplicarVistaObjetivos" in VISTA_JS


def test_el_selector_es_accesible_por_teclado_y_lectores() -> None:
    assert 'role="tablist"' in VISTA_JS
    assert 'role="tab"' in VISTA_JS
    assert "aria-selected" in VISTA_JS
    assert 'aria-controls="vistaFns"' in VISTA_JS
    assert 'aria-controls="vistaEps"' in VISTA_JS
    assert ".obj-tab:disabled" in VISTA_CSS


def test_el_selector_muestra_el_total_detectado_no_el_seleccionado() -> None:
    assert "function totalFuncionesDetectadas" in VISTA_JS
    assert "function totalEndpointsDetectados" in VISTA_JS
    assert "$('tabFnsN').textContent = nFns" in VISTA_JS
    assert "$('tabEpsN').textContent = nEps" in VISTA_JS
    # Los totales se calculan sobre todos los módulos analizables, no sobre los seleccionados.
    assert (
        "MODULES.filter(m => !m.error).flatMap(m => m.endpoints || []).length"
        in VISTA_JS
    )


def test_la_vista_por_defecto_es_funciones() -> None:
    assert "let VISTA_OBJETIVOS = 'funciones'" in VISTA_JS


def test_una_opcion_sin_objetivos_queda_deshabilitada_con_explicacion() -> None:
    assert "$('tabFns').disabled = nFns === 0" in VISTA_JS
    assert "$('tabEps').disabled = nEps === 0" in VISTA_JS
    assert "No se detectaron endpoints en el proyecto" in VISTA_JS
    assert "No se detectaron funciones en el proyecto" in VISTA_JS
    assert "aria-disabled" in VISTA_JS


def test_cambiar_de_vista_no_recarga_ni_pierde_la_seleccion() -> None:
    bloque = cuerpo("cambiarVistaObjetivos")
    for prohibido in (
        "loadProject",
        "obtener_vista_previa",
        "renderTree",
        "reiniciarPlegadoArchivos",
        ".inc",
        "m.sel",
    ):
        assert prohibido not in bloque
    assert "VISTA_OBJETIVOS = cual" in bloque


# ---------------- 6-9. Tabla de endpoints: columnas y tooltips ----------------


def test_columnas_de_la_tabla_de_endpoints_en_orden() -> None:
    assert _encabezados_endpoints() == [
        "Función / endpoint",
        "Complejidad",
        "Desde la última vez",
        "Profundizar",  # #74
    ]


def test_cada_columna_de_endpoint_tiene_tooltip() -> None:
    render = cuerpo("renderEndpoints")
    assert "title=" in render
    assert "Ruta no disponible: no se puede probar" in render
    assert "Profundizar: solicita un análisis más exhaustivo del endpoint" in render
    assert 'title="${detalle}"' in render


def test_todas_las_filas_comparten_las_nueve_columnas() -> None:
    render = cuerpo("renderEndpoints")
    assert 'colspan="5"' in render
    assert '<td class="col-incl">' in render
    assert '<td class="fn"' in render
    assert "<td>${textoComplejidad(e.br)}</td>" in render
    assert "<td>${textoDesdeUltimaVez(m)}</td>" in render
    assert '<td class="col-prof">' in render


# ---------------- 10-14. Contenido de las celdas ----------------


def test_calidad_de_endpoint_no_depende_del_numero_de_estado() -> None:
    render = cuerpo("renderEndpoints")
    assert "Función ${e.manejador ? escHtml(e.manejador) : '—'}" in render
    assert "Estado ${estado}" in render
    assert "Respuesta ${respuesta}" in render
    assert "Simula: " in render


def test_el_estado_no_declarado_se_atenua() -> None:
    assert "e.status_code_declarado ? '' : ' (por defecto)'" in VISTA_JS


def test_la_respuesta_vacia_muestra_guion() -> None:
    assert "e.response_model ? escHtml(e.response_model) : '—'" in VISTA_JS


def test_los_errores_resumen_los_codigos_http() -> None:
    assert "e.excepciones_http || []" in VISTA_JS
    assert "Errores HTTP:" in VISTA_JS
    assert "Sin errores HTTP identificados" in VISTA_JS


def test_simula_muestra_depends_y_no_inventa() -> None:
    assert "Sin Depends" in VISTA_JS
    assert "'Simula: ' + e.dependencias.join(', ')" in VISTA_JS


def test_los_textos_del_proyecto_se_escapan() -> None:
    assert "e.metodo ? escHtml(e.metodo) : 'SIN MÉTODO'" in VISTA_JS
    assert "e.ruta ? escHtml(e.ruta) : 'Ruta no disponible'" in VISTA_JS
    assert "e.manejador ? escHtml(e.manejador) : '—'" in VISTA_JS


# ---------------- 15-18. Endpoints no resueltos e inclusión ----------------


def test_un_endpoint_sin_ruta_no_se_puede_incluir() -> None:
    assert "function endpointElegible(e){ return !!e.objetivo; }" in VISTA_JS
    assert "Ruta no disponible: no se puede probar" in VISTA_JS
    assert "ep-no-resuelta" in VISTA_JS


def test_incluir_un_endpoint_individual_actualiza_la_seleccion() -> None:
    assert "function toggleEndpoint" in VISTA_JS
    marca = cuerpo("toggleEndpoint")
    assert "e.inc = !e.inc;" in marca
    assert "renderFns();" in marca


# ---------------- 23-26. Envío al backend y estimación ----------------


def test_obtener_seleccion_solo_envia_endpoints_resueltos_e_incluidos() -> None:
    bloque = cuerpo("obtenerSeleccionObjetivos")
    assert "filter(e => endpointElegible(e) && e.inc)" in VISTA_JS
    assert "m.sel && moduloTieneObjetivos(m)" in bloque


def test_la_estimacion_cuenta_solo_los_endpoints_elegidos() -> None:
    inicio = CONFIG_JS.index("function estFor")
    bloque = CONFIG_JS[inicio : CONFIG_JS.index("\n}", inicio)]
    assert "(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc)" in bloque


def test_el_pie_y_los_contadores_usan_la_seleccion() -> None:
    assert "endpointElegible(r.e) && r.e.inc" in VISTA_JS
    assert "const total = fns.length + endpoints.length" in VISTA_JS


def test_no_se_confunde_con_la_pantalla_de_perfiles() -> None:
    assert "renderProfiles" not in VISTA_JS


# ---------------- 27-30. Datos de demostración, tokens y sintaxis ----------------


def test_la_demostracion_incluye_endpoints_resueltos_y_no_resueltos() -> None:
    assert "endpoints:[" in ESTADO_JS
    assert "objetivo:null" in ESTADO_JS
    assert "endpointsElegibles" not in ESTADO_JS


def test_los_tokens_del_selector_existen_y_se_usan() -> None:
    # Rediseño: el selector usa los tokens del sistema (fondo hundido y seleccionado).
    for token in ("--hundido", "--accion-suave", "--enlace", "--texto-3"):
        assert f"{token}:" in TOKENS
    assert "var(--hundido)" in VISTA_CSS
    assert "var(--accion-suave)" in VISTA_CSS


# ---------------- Comportamiento real de las funciones puras (Node) ----------------

_HARNESS = r"""
const fs = require('fs');
const ruta = process.argv[2];
const src = fs.readFileSync(ruta, 'utf8');
function registrarComponente(){}
const window = {};
const document = { querySelectorAll: () => [], querySelector: () => null };
function $(id){ return null; }
const ICO_ESCUDO = '', ICO_FLECHA = '', ICO_OK = '', ICO_ERROR = '';
const factory = new Function(
  'registrarComponente', 'window', 'document', '$', 'MODULES', 'ICO_ESCUDO', 'ICO_FLECHA', 'ICO_OK', 'ICO_ERROR',
  src + '\nreturn {endpointElegible, endpointsElegibles, endpointsIncluidos, moduloTieneObjetivos, totalFuncionesDetectadas, totalEndpointsDetectados};'
);
const MODS = [
  { path:'a.py', sel:true, fns:[{n:'f1', inc:true}], endpoints:[
    { objetivo:'GET /a', inc:true, response_model:'A', status_code:200, status_code_declarado:true },
    { objetivo:'POST /a', inc:true, response_model:null, status_code:200, status_code_declarado:false },
    { objetivo:'GET /b', inc:false, response_model:'B', status_code:200, status_code_declarado:false },
    { objetivo:null, inc:false, response_model:null, status_code:200, status_code_declarado:false }
  ]},
  { path:'b.py', sel:true, fns:[], endpoints:[
    { objetivo:'DELETE /c', inc:true, response_model:null, status_code:204, status_code_declarado:true }
  ]}
];
const api = factory(registrarComponente, window, document, $, MODS, ICO_ESCUDO, ICO_FLECHA, ICO_OK, ICO_ERROR);
const out = {
  elegible: {
    resuelto: api.endpointElegible({objetivo:'GET /a'}),
    sin_objetivo: api.endpointElegible({objetivo:null}),
    vacio: api.endpointElegible({objetivo:''})
  },
  conteos: {
    funciones: api.totalFuncionesDetectadas(),
    endpoints: api.totalEndpointsDetectados()
  },
  incluidos: {
    a: api.endpointsIncluidos(MODS[0]).map(e => e.objetivo),
    b: api.endpointsIncluidos(MODS[1]).map(e => e.objetivo),
    soloFn: api.moduloTieneObjetivos({fns:[{inc:true}], endpoints:[]}),
    soloEp: api.moduloTieneObjetivos({fns:[], endpoints:[{objetivo:'GET /a', inc:true}]}),
    conError: api.moduloTieneObjetivos({error:{}, fns:[], endpoints:[]})
  }
};
console.log(JSON.stringify(out));
"""


def _ejecutar_harness(tmp_path: Path) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está disponible para probar el comportamiento real.")
    harness = tmp_path / "harness_endpoints.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    try:
        resultado = subprocess.run(
            [node, str(harness), str(VISTA_JS_PATH)],
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
    except OSError:
        pytest.skip("No se pudo ejecutar Node en este entorno.")
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


def test_comportamiento_de_elegibilidad_y_conteos(tmp_path: Path) -> None:
    datos = _ejecutar_harness(tmp_path)
    assert datos["elegible"] == {
        "resuelto": True,
        "sin_objetivo": False,
        "vacio": False,
    }
    assert datos["conteos"]["funciones"] == 1
    assert datos["conteos"]["endpoints"] == 5  # incluye el no resuelto: es lo detectado


def test_comportamiento_de_inclusion(tmp_path: Path) -> None:
    incluidos = _ejecutar_harness(tmp_path)["incluidos"]
    assert incluidos["a"] == [
        "GET /a",
        "POST /a",
    ]  # el no resuelto y el no incluido quedan fuera
    assert incluidos["b"] == ["DELETE /c"]
    assert incluidos["soloFn"] is True
    assert incluidos["soloEp"] is True
    assert incluidos["conError"] is False


def test_sin_errores_de_sintaxis_javascript() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está disponible para validar la sintaxis JavaScript.")
    for ruta in (VISTA_JS_PATH, CONFIG_JS_PATH):
        resultado = subprocess.run(
            [node, "--check", str(ruta)],
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        assert resultado.returncode == 0, resultado.stderr

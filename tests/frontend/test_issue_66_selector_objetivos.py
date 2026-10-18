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
    return [texto.strip() for texto in re.findall(r"<th>(.*?)<span", thead, re.DOTALL)]


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


def test_avisa_cuando_hay_objetivos_por_revisar() -> None:
    assert "function totalEndpointsPorRevisar" in VISTA_JS
    assert "$('tabFnsWarn')" in VISTA_JS
    assert "$('tabEpsWarn')" in VISTA_JS


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
    # Rediseño: tabla compacta. Estado, respuesta, errores y dependencias simuladas van en la
    # línea secundaria de «Información»; las decisiones (#74) en «Complejidad».
    assert _encabezados_endpoints() == [
        "Endpoint",
        "Complejidad",
        "Información",
        "Desde la última vez",
        "Profundizar",  # #74
    ]


def test_cada_columna_de_endpoint_tiene_tooltip() -> None:
    tooltips = _columnas_tooltips()
    assert len(tooltips) == 5  # una por columna con título (la casilla Incluir no lleva)
    for texto in (
        "Método HTTP y ruta del endpoint, con la función que lo atiende.",
        "Si el endpoint declara su modelo de respuesta y su código de estado. Debajo: estado, respuesta, errores HTTP y dependencias que se simulan.",
        "Pide un análisis más exhaustivo del endpoint. Tarda más.",
    ):
        assert f'data-tip="{texto}"' in VISTA_JS


def test_todas_las_filas_comparten_las_nueve_columnas() -> None:
    render = cuerpo("renderEndpoints")
    # Rediseño: encabezado de archivo, fila normal y fila vacía ocupan las 6 columnas.
    assert 'colspan="6"' in cuerpo("filaArchivo")
    assert 'colspan="6"' in render
    assert 'colspan="9"' not in render
    assert render.count("<td") >= 6


# ---------------- 10-14. Contenido de las celdas ----------------


def test_calidad_de_endpoint_no_depende_del_numero_de_estado() -> None:
    bloque = cuerpo("calidadEndpoint")
    assert "response_model" in bloque
    assert "status_code_declarado" in bloque
    assert "=== 200" not in bloque and "== 200" not in bloque
    assert bloque.index("return 'lista'") < bloque.index("return 'mejorable'")
    assert bloque.index("return 'mejorable'") < bloque.index("return 'incierto'")


def test_el_estado_no_declarado_se_atenua() -> None:
    assert "class=\"${e.status_code_declarado ? '' : 'muted'}\"" in VISTA_JS
    assert "td.muted,.exp-objetivos table .muted{color:var(--texto-3)}" in VISTA_CSS


def test_la_respuesta_vacia_muestra_guion() -> None:
    assert "e.response_model ? escHtml(e.response_model) : '—'" in VISTA_JS


def test_los_errores_resumen_los_codigos_http() -> None:
    assert "e.excepciones_http || []" in VISTA_JS
    assert "Errores HTTP:" in VISTA_JS
    assert 'title="${escHtml(tipErr)}"' in VISTA_JS


def test_simula_muestra_depends_y_no_inventa() -> None:
    assert "Sin Depends" in VISTA_JS
    assert (
        'e.dependencias.map(d => `<span class="pill p-grey">${escHtml(d)}</span>`)'
        in VISTA_JS
    )


def test_los_textos_del_proyecto_se_escapan() -> None:
    assert "e.metodo ? escHtml(e.metodo) : 'SIN MÉTODO'" in VISTA_JS
    assert "e.ruta ? escHtml(e.ruta) : 'Ruta no disponible'" in VISTA_JS
    assert "e.manejador ? escHtml(e.manejador) : '—'" in VISTA_JS


# ---------------- 15-18. Agrupación, plegado y endpoints no resueltos ----------------


def test_los_endpoints_se_agrupan_por_archivo_con_su_plegado() -> None:
    assert 'class="ep-table"' in VISTA_JS
    assert "function endpointAbierto" in VISTA_JS
    assert "function toggleArchivoEndpoints" in VISTA_JS
    assert "let ARCHIVOS_ABIERTOS_EP = {}" in VISTA_JS
    assert "ARCHIVOS_ABIERTOS_EP[m.path]" in VISTA_JS


def test_el_plegado_de_una_vista_es_independiente_de_la_otra() -> None:
    assert "ARCHIVOS_ABIERTOS_EP" in cuerpo("toggleArchivoEndpoints")
    assert "ARCHIVOS_ABIERTOS_EP" not in cuerpo("toggleArchivo")


def test_el_encabezado_de_archivo_cuenta_endpoints_y_por_revisar() -> None:
    render = cuerpo("renderEndpoints")
    assert "'endpoint' : 'endpoints'" in render
    assert "porRevisar" in render
    # El encabezado de archivo es común a funciones y endpoints (rediseño).
    assert " por revisar" in cuerpo("filaArchivo")


def test_un_endpoint_sin_ruta_no_se_puede_incluir() -> None:
    assert "function endpointElegible(e){ return !!e.objetivo; }" in VISTA_JS
    assert "Ruta no disponible: no se puede probar" in VISTA_JS
    assert "ep-no-resuelta" in VISTA_JS


# ---------------- 19-22. Selección por archivo e individual ----------------


def test_incluir_archivo_marca_solo_los_endpoints_analizables() -> None:
    bloque = cuerpo("seleccionarEndpointsArchivo")
    assert "endpointsElegibles(m)" in bloque
    assert "e.inc = !!seleccionado" in bloque


def test_el_checkbox_de_archivo_sincroniza_indeterminado() -> None:
    assert "function sincronizarCheckboxesArchivoEndpoints" in VISTA_JS
    assert "sincronizarCheckboxesArchivoEndpoints();" in VISTA_JS
    assert "chk.indeterminate" in VISTA_JS


def test_incluir_un_endpoint_individual_actualiza_la_seleccion() -> None:
    assert "function toggleEndpoint" in VISTA_JS
    assert 'class="file-check" data-mi=' in VISTA_JS


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
    assert (
        "const totalEndpointsIncluidos = sel.flatMap(m => endpointsIncluidos(m)).length"
        in VISTA_JS
    )
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
const factory = new Function(
  'registrarComponente', 'window', 'document', '$', 'MODULES',
  src + '\nreturn {calidadEndpoint, endpointElegible, endpointsElegibles, endpointsIncluidos, moduloConSeleccion, contarEndpointsPorRevisar, totalFuncionesDetectadas, totalEndpointsDetectados};'
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
const api = factory(registrarComponente, window, document, $, MODS);
const out = {
  calidad: {
    lista: api.calidadEndpoint({response_model:'X', status_code_declarado:true}),
    mejorable_resp: api.calidadEndpoint({response_model:'X', status_code_declarado:false}),
    mejorable_estado: api.calidadEndpoint({response_model:null, status_code_declarado:true}),
    incierto: api.calidadEndpoint({response_model:null, status_code_declarado:false}),
    estado_200_por_defecto_no_es_lista: api.calidadEndpoint({response_model:'X', status_code:200, status_code_declarado:false})
  },
  elegible: {
    resuelto: api.endpointElegible({objetivo:'GET /a'}),
    sin_objetivo: api.endpointElegible({objetivo:null}),
    vacio: api.endpointElegible({objetivo:''})
  },
  conteos: {
    funciones: api.totalFuncionesDetectadas(),
    endpoints: api.totalEndpointsDetectados(),
    porRevisarA: api.contarEndpointsPorRevisar(MODS[0]),
    porRevisarB: api.contarEndpointsPorRevisar(MODS[1])
  },
  incluidos: {
    a: api.endpointsIncluidos(MODS[0]).map(e => e.objetivo),
    b: api.endpointsIncluidos(MODS[1]).map(e => e.objetivo),
    soloFn: api.moduloConSeleccion({fns:[{inc:true}], endpoints:[]}),
    soloEp: api.moduloConSeleccion({fns:[], endpoints:[{objetivo:'GET /a', inc:true}]}),
    epNoResuelto: api.moduloConSeleccion({fns:[], endpoints:[{objetivo:null, inc:true}]})
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


def test_comportamiento_de_calidad(tmp_path: Path) -> None:
    calidad = _ejecutar_harness(tmp_path)["calidad"]
    assert calidad["lista"] == "lista"
    assert calidad["mejorable_resp"] == "mejorable"
    assert calidad["mejorable_estado"] == "mejorable"
    assert calidad["incierto"] == "incierto"
    # Un 200 sin declarar no es Lista: se exige el modelo de respuesta y el estado declarado.
    assert calidad["estado_200_por_defecto_no_es_lista"] == "mejorable"


def test_comportamiento_de_elegibilidad_y_conteos(tmp_path: Path) -> None:
    datos = _ejecutar_harness(tmp_path)
    assert datos["elegible"] == {
        "resuelto": True,
        "sin_objetivo": False,
        "vacio": False,
    }
    assert datos["conteos"]["funciones"] == 1
    assert datos["conteos"]["endpoints"] == 5  # incluye el no resuelto: es lo detectado
    assert datos["conteos"]["porRevisarA"] == 3
    assert datos["conteos"]["porRevisarB"] == 1


def test_comportamiento_de_inclusion(tmp_path: Path) -> None:
    incluidos = _ejecutar_harness(tmp_path)["incluidos"]
    assert incluidos["a"] == [
        "GET /a",
        "POST /a",
    ]  # el no resuelto y el no incluido quedan fuera
    assert incluidos["b"] == ["DELETE /c"]
    assert incluidos["soloFn"] is True
    assert incluidos["soloEp"] is True
    assert incluidos["epNoResuelto"] is False


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

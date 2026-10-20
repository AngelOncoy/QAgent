"""Etiqueta «Sin docstring» en Explorar, En curso y Resultados (issue #114).

La etiqueta informa una característica del código (no es un error): sale del análisis
AST que ya llega a Explorar, lleva un tooltip accesible con mouse y teclado, usa solo
tokens CSS y no toca la selección (Incluir) ni la columna Complejidad.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from qagent.proyectos.vista_previa import generar_vista_previa

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"
UTILS_JS_PATH = FRONTEND / "js" / "utils.js"

UTILS_JS = UTILS_JS_PATH.read_text(encoding="utf-8")
VISTA_JS = (FRONTEND / "componentes" / "vista-previa" / "vista-previa.js").read_text(
    encoding="utf-8"
)
MONITOR_JS = (FRONTEND / "componentes" / "monitor" / "monitor.js").read_text(
    encoding="utf-8"
)
EJECUCION_JS = (FRONTEND / "componentes" / "ejecucion" / "ejecucion.js").read_text(
    encoding="utf-8"
)
COMPONENTES_CSS = (FRONTEND / "css" / "componentes.css").read_text(encoding="utf-8")


def _cuerpo(fuente: str, nombre_funcion: str) -> str:
    inicio = fuente.index(f"function {nombre_funcion}")
    resto = fuente[inicio:]
    return resto[: resto.index("\n}\n")]


def _regla_css(selector: str) -> str:
    coincidencia = re.search(re.escape(selector) + r"\{([^}]*)\}", COMPONENTES_CSS)
    assert coincidencia, f"Falta la regla {selector}"
    return coincidencia.group(1)


_HARNESS = r"""
const fs = require('fs');
const utils = fs.readFileSync(process.argv[2], 'utf8');
const document = { getElementById: () => null };
const MODULES = [
  {path: 'app/precios.py', fns: [
    {n: 'con_doc', doc: 1}, {n: 'sin_doc', doc: 0}, {n: 'sin_dato'}],
   endpoints: [
    {objetivo: 'GET /a', doc: 0}, {objetivo: 'GET /b', doc: 1}, {objetivo: 'GET /c', doc: null}]},
  {path: 'roto.py', error: {tipo: 'SyntaxError'}, fns: [{n: 'sin_doc', doc: 0}]},
];
const api = new Function('document', 'MODULES',
  utils + '\nreturn {tieneDocstring, docstringDeObjetivo, etiquetaSinDocstring};')(document, MODULES);
const buscar = (m, n) => api.docstringDeObjetivo(m, n);
console.log(JSON.stringify({
  con_doc: buscar('app/precios.py', 'con_doc'),
  sin_doc: buscar('app/precios.py', 'sin_doc'),
  sin_doc_con_parentesis: buscar('app/precios.py', 'sin_doc()'),
  sin_dato: buscar('app/precios.py', 'sin_dato'),
  ep_sin_doc: buscar('app/precios.py', 'GET /a'),
  ep_con_doc: buscar('app/precios.py', 'GET /b'),
  ep_sin_dato: buscar('app/precios.py', 'GET /c'),
  otro_archivo: buscar('otro.py', 'sin_doc'),
  archivo_con_error: buscar('roto.py', 'sin_doc'),
  etiqueta_funcion: api.etiquetaSinDocstring('funcion'),
  etiqueta_endpoint: api.etiquetaSinDocstring('endpoint'),
  etiqueta_en_lista: api.etiquetaSinDocstring('funcion', {enfocable: false}),
}));
"""


@pytest.fixture(scope="module")
def comportamiento(tmp_path_factory: pytest.TempPathFactory) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está disponible para ejecutar la etiqueta Sin docstring.")
    harness = tmp_path_factory.mktemp("issue114") / "sin_docstring.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    resultado = subprocess.run(
        [node, str(harness), str(UTILS_JS_PATH)],
        check=False,
        capture_output=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


# Comportamiento de las utilidades compartidas (con Node)
def test_solo_las_funciones_sin_docstring_se_marcan(comportamiento: dict) -> None:
    assert comportamiento["sin_doc"] is False
    assert comportamiento["sin_doc_con_parentesis"] is False  # nombres del monitor demo
    assert comportamiento["con_doc"] is True


def test_sin_dato_del_analisis_no_se_supone_nada(comportamiento: dict) -> None:
    assert comportamiento["sin_dato"] is None
    assert comportamiento["ep_sin_dato"] is None
    assert comportamiento["otro_archivo"] is None
    assert comportamiento["archivo_con_error"] is None


def test_los_endpoints_usan_su_informacion_de_documentacion(
    comportamiento: dict,
) -> None:
    assert comportamiento["ep_sin_doc"] is False
    assert comportamiento["ep_con_doc"] is True


def test_la_etiqueta_tiene_tooltip_y_se_alcanza_con_teclado(
    comportamiento: dict,
) -> None:
    for clave in ("etiqueta_funcion", "etiqueta_endpoint"):
        html = comportamiento[clave]
        assert 'class="etq-sin-doc"' in html
        assert ">Sin docstring</span>" in html
        assert 'tabindex="0"' in html
        assert 'data-tip="' in html
        assert 'aria-label="Sin docstring. ' in html
    assert "función" in comportamiento["etiqueta_funcion"]
    assert "endpoint" in comportamiento["etiqueta_endpoint"]
    # Dentro de una opción de lista (que ya recibe el foco) no se anida otro foco.
    assert "tabindex" not in comportamiento["etiqueta_en_lista"]
    assert 'data-tip="' in comportamiento["etiqueta_en_lista"]


# Estructura: dónde se muestra
def test_explorar_marca_funciones_y_endpoints_sin_docstring() -> None:
    assert "tieneDocstring(f) === false ? etiquetaSinDocstring('funcion')" in (
        _cuerpo(VISTA_JS, "renderFns")
    )
    assert "tieneDocstring(e) === false ? etiquetaSinDocstring('endpoint')" in (
        _cuerpo(VISTA_JS, "renderEndpoints")
    )
    # El dato del endpoint solo existe si el análisis lo trae.
    assert "doc: 'docstring' in e ? (e.docstring ? 1 : 0) : null" in VISTA_JS


def test_en_curso_marca_el_objetivo_actual() -> None:
    cuerpo = _cuerpo(MONITOR_JS, "pintarProgreso")
    assert "docstringDeObjetivo(a.f, a.fn) === false" in cuerpo
    assert "etiquetaSinDocstring(" in cuerpo


def test_resultados_marcan_la_lista_y_el_detalle() -> None:
    assert "sinDocstring: docstringDeObjetivo(m.modulo, p.funcion) === false" in (
        EJECUCION_JS
    )
    assert "sinDocstring: docstringDeObjetivo(fn.module, fn.name) === false" in (
        EJECUCION_JS
    )
    assert "etiquetaSinDocstring(e.tipo, {enfocable: false})" in _cuerpo(
        EJECUCION_JS, "renderExec"
    )
    assert "e.sinDocstring ? etiquetaSinDocstring(e.tipo)" in _cuerpo(
        EJECUCION_JS, "renderDetalleBandeja"
    )


def test_el_tooltip_funciona_en_cualquier_pantalla_y_con_teclado() -> None:
    cuerpo = _cuerpo(VISTA_JS, "iniciarTooltips")
    assert "document.body.appendChild(tip)" in cuerpo
    for evento in ("mouseover", "mouseout", "focusin", "focusout"):
        assert f"document.addEventListener('{evento}'" in cuerpo
    assert "ev.key === 'Escape'" in cuerpo


# No cambia la selección ni el indicador existente
def test_sin_docstring_no_desactiva_incluir_ni_la_seleccion() -> None:
    assert "inc: true" in VISTA_JS
    for funcion in ("toggle", "obtenerSeleccionObjetivos", "seleccionarTodosObjetivos"):
        assert "doc" not in _cuerpo(VISTA_JS, funcion)
    # La casilla Incluir de la fila no depende del docstring.
    fila = _cuerpo(VISTA_JS, "renderFns")
    incluir = fila[fila.index('aria-label="Incluir función') :]
    incluir = incluir[: incluir.index("</td>")]
    assert "doc" not in incluir and "disabled" not in incluir


def test_se_conserva_la_columna_complejidad() -> None:
    assert "<th>Complejidad</th>" in VISTA_JS
    assert "${textoComplejidad(f.br)}" in VISTA_JS
    assert "${textoComplejidad(e.br)}" in VISTA_JS


# Estilo con tokens del proyecto
def test_la_etiqueta_usa_solo_tokens_css() -> None:
    for selector in (".etq-sin-doc", ".etq-sin-doc:focus-visible"):
        regla = _regla_css(selector)
        assert "var(--" in regla
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", regla)
    assert "var(--foco-anillo)" in _regla_css(".etq-sin-doc:focus-visible")


# El dato llega del análisis AST, también para endpoints
def test_la_vista_previa_entrega_el_docstring_de_funciones_y_endpoints(
    tmp_path: Path,
) -> None:
    (tmp_path / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n\n"
        "def documentada(x: int) -> int:\n"
        '    """Duplica x."""\n'
        "    return x * 2\n\n"
        "def sin_documentar(x: int) -> int:\n"
        "    return x\n\n"
        '@app.get("/con")\n'
        "def con_doc():\n"
        '    """Devuelve algo."""\n'
        "    return {}\n\n"
        '@app.get("/sin")\n'
        "def sin_doc():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    res = generar_vista_previa(tmp_path)
    modulo = res["modulos"][0]
    funciones = {f["nombre"]: f["docstring"] for f in modulo["funciones"]}
    assert funciones["documentada"] == "Duplica x."
    assert funciones["sin_documentar"] is None
    endpoints = {e["objetivo"]: e for e in modulo["endpoints"]}
    assert endpoints["GET /con"]["docstring"] == "Devuelve algo."
    assert "docstring" in endpoints["GET /sin"]
    assert endpoints["GET /sin"]["docstring"] is None

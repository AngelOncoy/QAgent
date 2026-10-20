"""Regresiones de los cuatro defectos frontend confirmados en la issue #92."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pytest

from qagent.analysis import analizar_proyecto

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"
VISTA_JS_PATH = FRONTEND / "componentes" / "vista-previa" / "vista-previa.js"
ESTADO_JS_PATH = FRONTEND / "js" / "estado.js"

VISTA_JS = VISTA_JS_PATH.read_text(encoding="utf-8")
VISTA_CSS = (FRONTEND / "componentes" / "vista-previa" / "vista-previa.css").read_text(
    encoding="utf-8"
)
INDEX_HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")


class _Enlaces(HTMLParser):
    """Recoge los elementos ``link`` del documento sin depender de un navegador."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "link":
            self.links.append({clave: valor or "" for clave, valor in attrs})


_HARNESS_DECISIONES = r"""
const fs = require('fs');
const vista = fs.readFileSync(process.argv[2], 'utf8');
const estado = fs.readFileSync(process.argv[3], 'utf8');
function registrarComponente(){}
const window = {};
const document = { querySelectorAll: () => [], querySelector: () => null };
function $(id){ return null; }
const ICO_ESCUDO = '', ICO_FLECHA = '', ICO_OK = '', ICO_ERROR = '';
const factory = new Function(
  'registrarComponente', 'window', 'document', '$', 'MODULES', 'ICO_ESCUDO', 'ICO_FLECHA', 'ICO_OK', 'ICO_ERROR',
  vista + '\nreturn {normalizarDecisiones, textoDecisiones};'
);
const api = factory(registrarComponente, window, document, $, [], ICO_ESCUDO, ICO_FLECHA, ICO_OK, ICO_ERROR);
const demo = new Function(

  estado.split('const IN_RUN')[0] + '\nreturn MODULES;'
)();
const valores = [4, 0, undefined, null, NaN, 7];
console.log(JSON.stringify({
  normalizados: valores.map(v => api.normalizarDecisiones(v)),
  textos: valores.map(v => api.textoDecisiones(v)),
  demo: demo.flatMap(m => m.endpoints || []).map(e => api.textoDecisiones(e.br))
}));
"""


def _decisiones_reales(tmp_path: Path) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está disponible para ejecutar la regresión #92.")
    harness = tmp_path / "issue92_decisiones.js"
    harness.write_text(_HARNESS_DECISIONES, encoding="utf-8")
    resultado = subprocess.run(
        [node, str(harness), str(VISTA_JS_PATH), str(ESTADO_JS_PATH)],
        check=False,
        capture_output=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


def test_decisiones_preserva_valores_validos_y_el_cero(tmp_path: Path) -> None:
    datos = _decisiones_reales(tmp_path)
    assert datos["normalizados"][:2] == [4, 0]
    assert datos["textos"][:2] == ["4", "0"]
    assert datos["normalizados"][-1] == 7
    assert datos["textos"][-1] == "7"


def test_decisiones_ausentes_tienen_representacion_segura(tmp_path: Path) -> None:
    datos = _decisiones_reales(tmp_path)
    assert datos["normalizados"][2:5] == [None, None, None]
    assert datos["textos"][2:5] == ["\N{EM DASH}", "\N{EM DASH}", "\N{EM DASH}"]


def test_endpoints_demo_no_renderizan_valores_javascript(tmp_path: Path) -> None:
    textos = _decisiones_reales(tmp_path)["demo"]
    assert textos
    assert not ({"undefined", "null", "NaN", "[object Object]"} & set(textos))


def test_analizador_real_entrega_decisiones_numericas(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n\n"
        "@app.get('/salud')\n"
        "def salud(activo: bool):\n"
        "    if activo:\n"
        "        return {'ok': True}\n"
        "    return {'ok': False}\n",
        encoding="utf-8",
    )
    analisis = analizar_proyecto(tmp_path)
    endpoint = analisis["modulos"][0]["endpoints"][0]
    assert endpoint["objetivo"] == "GET /salud"
    assert endpoint["ramas"] == 1


def test_tablas_anchas_quedan_dentro_de_su_scroll_interno() -> None:
    assert re.search(
        r"\.exp-rejilla\s*\{[^}]*min-width\s*:\s*0", VISTA_CSS
    ) or re.search(r"\.exp-objetivos\s*\{[^}]*min-width\s*:\s*0", VISTA_CSS)
    assert re.search(r"\.obj-vista\s*\{[^}]*min-width\s*:\s*0", VISTA_CSS)
    assert re.search(r"\.table-scroll\s*\{[^}]*overflow", VISTA_CSS)


def test_grid_se_apila_antes_del_ancho_minimo_de_pywebview() -> None:
    breakpoints = [
        int(valor)
        for valor in re.findall(r"@media\s*\(max-width\s*:\s*(\d+)px\)", VISTA_CSS)
    ]
    assert any(valor >= 1024 for valor in breakpoints)
    assert re.search(
        r"@media\s*\(max-width\s*:\s*\d+px\)\s*\{[^}]*\.exp-rejilla\s*\{[^}]*grid-template-columns\s*:\s*minmax\(0,\s*1fr\)",
        VISTA_CSS,
        re.DOTALL,
    )


def test_encabezado_del_arbol_admite_ajuste_sin_ocultar_el_control() -> None:
    assert 'id="selectAllModules"' in VISTA_JS
    assert "seleccionarTodosModulos(this.checked)" in VISTA_JS
    assert ".tree .row" in VISTA_CSS


def test_favicon_oficial_existe_y_es_svg_valido() -> None:
    parser = _Enlaces()
    parser.feed(INDEX_HTML)
    iconos = [link for link in parser.links if "icon" in link.get("rel", "").split()]
    assert len(iconos) == 1
    assert iconos[0].get("type") == "image/svg+xml"
    ruta = FRONTEND / iconos[0]["href"]
    assert ruta.is_file()
    raiz_svg = ET.parse(ruta).getroot()
    assert raiz_svg.tag.endswith("svg")

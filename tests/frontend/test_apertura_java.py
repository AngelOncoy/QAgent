"""Renderizado y selección Java reales en JavaScript, con datos del puente Python."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from qagent.app.desktop import DesktopAPI
from qagent.proyectos.seleccion import filtrar_modulos

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src/qagent/frontend/componentes"


@pytest.mark.parametrize(
    "banco", ["bench_java", "bench_java/src/test/resources/spring"]
)
def test_abrir_y_seleccionar_java_desde_javascript(tmp_path: Path, banco: str) -> None:
    """El componente muestra Java, habilita Analizar y envía objetivos válidos al backend."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite comprobar el comportamiento del frontend.")
    proyecto = tmp_path / "proyecto"
    shutil.copytree(
        RAIZ / banco, proyecto, ignore=shutil.ignore_patterns("target", ".qagent")
    )
    api = DesktopAPI()
    inspeccion = api.inspeccionar_carpeta(str(proyecto))
    vista = api.obtener_vista_previa(str(proyecto))
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const entrada = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodos = new Map();
function $(id) {
  if (!nodos.has(id)) nodos.set(id, {innerHTML:'', textContent:'', disabled:false,
    classList:{toggle(){}}, setAttribute(){}});
  return nodos.get(id);
}
const ctx = vm.createContext({$, window:{pywebview:{api:{}}},
  document:{querySelectorAll:()=>[]}, registrarComponente(){}, go(){},
  escHtml:x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;'), MODULES:[],
  eleccionPruebas:{unitarias:true,endpoints:true}});
vm.runInContext(fs.readFileSync(entrada.abrir, 'utf8'), ctx);
ctx.inspeccion = entrada.inspeccion;
vm.runInContext('showOpenReal(inspeccion)', ctx);
assert.equal($('openOk').disabled, false);
assert.match($('openCount').innerHTML, /Archivos Java/);
assert.match($('openReconocido').innerHTML, /Listo para analizar/);
assert.match($('openReconocido').innerHTML, /\.java/);
assert.doesNotMatch($('openReconocido').innerHTML, /Python/);
vm.runInContext(fs.readFileSync(entrada.vistaJS, 'utf8'), ctx);
ctx.vista = entrada.vista;
vm.runInContext('cargarDatosVistaPrevia(vista)', ctx);
assert.equal(vm.runInContext('PROYECTO_NOMBRE_LENGUAJE', ctx), 'Java');
assert.equal($('projLenguaje').textContent, 'Java · JUnit 5');
assert.equal($('sideLenguaje').textContent, 'Java · JUnit 5');
assert.equal($('resumenModulos').textContent, entrada.vista.resumen.total_modulos);
const seleccion = vm.runInContext('obtenerSeleccionObjetivos()', ctx);
assert.ok(seleccion.length > 0);
process.stdout.write(JSON.stringify(seleccion));
"""
    resultado = subprocess.run(
        [node, "-e", script],
        input=json.dumps(
            {
                "inspeccion": inspeccion,
                "vista": vista,
                "abrir": str(FRONTEND / "inicio/modal-abrir.js"),
                "vistaJS": str(FRONTEND / "vista-previa/vista-previa.js"),
            }
        ),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr
    seleccion = json.loads(resultado.stdout)
    filtrados = filtrar_modulos(vista["modulos"], seleccion)
    assert (
        sum(len(m["funciones"]) for m in filtrados)
        == vista["resumen"]["total_funciones_publicas"]
    )
    assert (
        sum(len(m["endpoints"]) for m in filtrados)
        == vista["resumen"]["total_endpoints"]
    )

"""#253: Resultados conserva Java y muestra el diagnóstico como texto seguro."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_resultados_renderiza_lenguaje_y_error_del_planner() -> None:
    """Ejecuta el componente real y comprueba el HTML de un fallo y una corrida antigua."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite comprobar el comportamiento del frontend.")
    componente = (
        Path(__file__).resolve().parents[2]
        / "src/qagent/frontend/componentes/ejecucion/ejecucion.js"
    )
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const entrada = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodos = new Map();
function $(id) {
  if (!nodos.has(id)) nodos.set(id, {innerHTML:'', textContent:''});
  return nodos.get(id);
}
const detalle = $('bnjDetalle');
const ctx = vm.createContext({
  registrarComponente(){}, $, window:{},
  document:{querySelector:()=>({textContent:'bench_java'})},
  docstringDeObjetivo:()=>true,
  escHtml:x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
});
const fuente = fs.readFileSync(entrada.ruta, 'utf8');
// Los iconos compartidos son decoración; el render y el escape son los reales.
for (const nombre of fuente.match(/ICO_[A-Z_]+/g) || []) ctx[nombre] = '';
vm.runInContext(fuente, ctx);
ctx.vista = {run_id:'253', modulos:[{modulo:'Banco.java', pruebas:[{
  funcion:'Banco.mayor', identificador:'Banco.mayor', tipo:'funcion',
  lenguaje:'java', estado:'sin_veredicto', intento_final:0,
  motivo_sin_veredicto:'error_planner',
  detalle_error_planner:'casos/0/id: <script> no cumple el contrato'
}]}]};
vm.runInContext('renderDetalleBandeja(elementosProbados(vista)[0])', ctx);
assert.match(detalle.innerHTML, /Lenguaje: java/);
assert.match(detalle.innerHTML, /Ver motivo del fallo de planificación/);
assert.match(detalle.innerHTML, /casos\/0\/id: &lt;script&gt;/);
assert.doesNotMatch(detalle.innerHTML, /<script>/);
assert.doesNotMatch(detalle.innerHTML, /Lenguaje: python/);
vm.runInContext('renderCabeceraBandeja(elementosProbados(vista), vista)', ctx);
assert.match($('bnjSub').textContent, /bench_java · Java/);
assert.doesNotMatch($('bnjSub').textContent, /Python/);
ctx.vista.modulos[0].pruebas[0].lenguaje = 'python';
vm.runInContext('renderCabeceraBandeja(elementosProbados(vista), vista)', ctx);
assert.match($('bnjSub').textContent, /Python/);
ctx.vista.modulos[0].pruebas[0].lenguaje = 'java';
delete ctx.vista.modulos[0].pruebas[0].detalle_error_planner;
vm.runInContext('renderDetalleBandeja(elementosProbados(vista)[0])', ctx);
assert.doesNotMatch(detalle.innerHTML, /Ver motivo del fallo de planificación/);
assert.match(detalle.innerHTML, /Lenguaje: java/);
"""
    resultado = subprocess.run(
        [node, "-e", script],
        input=json.dumps({"ruta": str(componente)}),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_monitor_muestra_pendientes_reales_durante_la_corrida() -> None:
    """Renderiza 0/3, 1/3 y 3/3 sin presentar pendientes falsamente resueltos."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite comprobar el comportamiento del frontend.")
    componente = (
        Path(__file__).resolve().parents[2]
        / "src/qagent/frontend/componentes/monitor/monitor.js"
    )
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const entrada = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodos = new Map();
function $(id) {
  if (!nodos.has(id)) nodos.set(id, {innerHTML:'', textContent:'', style:{},
    classList:{add(){},toggle(){}}, setAttribute(){}});
  return nodos.get(id);
}
const ctx = vm.createContext({registrarComponente(){}, $, window:{}, paused:false,
  document:{querySelector:()=>({textContent:'bench_java'})}});
const fuente = fs.readFileSync(entrada.ruta, 'utf8');
for (const nombre of fuente.match(/ICO_[A-Z_]+/g) || []) ctx[nombre] = '';
vm.runInContext(fuente, ctx);
vm.runInContext('reiniciarProgreso(); PRG.total = 3;', ctx);
for (const hechos of [0, 1, 3]) {
  ctx.hechos = hechos;
  vm.runInContext('PRG.hechos = hechos; pintarProgreso()', ctx);
  assert.match($('prgAvanceTxt').textContent, new RegExp(`${3-hechos} pendientes de 3 seleccionados`));
  assert.equal($('prgPct').textContent, Math.round(hechos/3*100) + ' %');
}
"""
    resultado = subprocess.run(
        [node, "-e", script],
        input=json.dumps({"ruta": str(componente)}),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr

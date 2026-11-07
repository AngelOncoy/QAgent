"""#262: el componente separa la explicación legible del log técnico sin IA."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_log_tecnico_no_se_muestra_como_explicacion_principal() -> None:
    """Renderiza la evidencia conservando el detalle y la explicación de IA existente."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite comprobar el componente JavaScript.")
    componente = (
        Path(__file__).resolve().parents[2]
        / "src/qagent/frontend/componentes/ejecucion/ejecucion.js"
    )
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const nodos = new Map();
function $(id) {
  if (!nodos.has(id)) nodos.set(id,{innerHTML:'',textContent:''});
  return nodos.get(id);
}
const ctx = vm.createContext({$, window:{}, registrarComponente(){},
  document:{querySelector:()=>({textContent:'bench_java'})},
  docstringDeObjetivo:()=>true,
  escHtml:x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')});
const fuente = fs.readFileSync(JSON.parse(fs.readFileSync(0,'utf8')).ruta,'utf8');
for (const nombre of fuente.match(/ICO_[A-Z_]+/g) || []) ctx[nombre]='';
vm.runInContext(fuente,ctx);
ctx.reporte = {resumen_ejecucion:'La prueba esperaba 2.5 y obtuvo 2.0.',
  intentos:[{feedback:'[INFO] MAVEN_LOG_EXTENSO <script>'}]};
vm.runInContext(`
  function pintar() {
    renderDetalleBandeja({bandeja:'bug',nombre:'Banco.promedio',modulo:'Banco.java',
      lenguaje:'java', ...detalleDeReporte(reporte)});
  }
  pintar();`,ctx);
let html = $('bnjDetalle').innerHTML;
assert.match(html,/La prueba esperaba 2.5 y obtuvo 2.0/);
assert.doesNotMatch(html.split('<details')[0],/MAVEN_LOG_EXTENSO/);
assert.match(html,/Ver detalle técnico/);
assert.match(html,/MAVEN_LOG_EXTENSO &lt;script&gt;/);
ctx.reporte.explicacion = {resumen:'Explicación de IA conservada',origen:'ia'};
vm.runInContext('pintar()',ctx);
assert.match($('bnjDetalle').innerHTML,/Explicación de IA conservada/);
delete ctx.reporte.explicacion;
delete ctx.reporte.resumen_ejecucion;
vm.runInContext('pintar()',ctx);
assert.doesNotMatch($('bnjDetalle').innerHTML.split('<details')[0],/MAVEN_LOG_EXTENSO/);
ctx.omitidos = {omitidos:[{modulo:'Banco.java',objetivo:'Banco.sinCasos',tipo:'funcion',
  lenguaje:'java',motivo:'No hay resultado esperado verificable.'}]};
vm.runInContext('renderDetalleBandeja(elementosOmitidos(omitidos)[0])',ctx);
assert.match($('bnjDetalle').innerHTML,/Lenguaje: java/);
assert.match($('bnjDetalle').innerHTML,/No hay resultado esperado verificable/);
assert.doesNotMatch($('bnjDetalle').innerHTML,/Lenguaje: python/);
delete ctx.omitidos.omitidos[0].lenguaje;
vm.runInContext('renderDetalleBandeja(elementosOmitidos(omitidos)[0])',ctx);
assert.match($('bnjDetalle').innerHTML,/Lenguaje: no registrado/);
ctx.vista={perfil:'humo',perfil_nombre:'Humo',modulos:[{modulo:'Banco.java',pruebas:[{
  funcion:'Banco.envio',identificador:'Banco.envio',tipo:'funcion',lenguaje:'java',estado:'aprobado'
}]}]};
vm.runInContext('renderCabeceraBandeja(elementosProbados(vista),vista)',ctx);
assert.match($('bnjSub').textContent,/Perfil: Humo/);
vm.runInContext('renderDetalleBandeja(elementosProbados(vista)[0])',ctx);
assert.match($('bnjDetalle').innerHTML,/Pasó el caso probado/);
ctx.vista.perfil='std'; ctx.vista.perfil_nombre='Estándar';
vm.runInContext('renderCabeceraBandeja(elementosProbados(vista),vista)',ctx);
assert.match($('bnjSub').textContent,/Perfil: Estándar/);
vm.runInContext('renderDetalleBandeja(elementosProbados(vista)[0])',ctx);
assert.match($('bnjDetalle').innerHTML,/Pasaron los casos probados/);
"""
    resultado = subprocess.run(
        [node, "-e", script],
        input=json.dumps({"ruta": str(componente)}),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr

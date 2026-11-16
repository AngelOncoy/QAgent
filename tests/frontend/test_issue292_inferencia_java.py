"""Renderizado real de hallazgos inferidos, separado de posibles bugs con contrato."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_cabecera_no_confirma_un_fallo_inferido():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está disponible para verificar la interfaz.")
    archivo = (
        Path(__file__).resolve().parents[2]
        / "src/qagent/frontend/componentes/ejecucion/ejecucion.js"
    )
    script = r"""
const fs = require('fs'); const vm = require('vm'); const assert = require('assert/strict');
const nodos = new Map();
function $(id) { if (!nodos.has(id)) nodos.set(id,{innerHTML:'',textContent:'',classList:{toggle(){}}}); return nodos.get(id); }
const ctx = vm.createContext({$,window:{},document:{querySelector:()=>null},registrarComponente(){},
  ICO_ESCUDO:'',ICO_INFO:'',ICO_BUSCAR:'',
  enAppEscritorio:()=>false,pctTexto:x=>String(x),tiempoReal:x=>String(x),escHtml:x=>String(x)});
vm.runInContext(fs.readFileSync(JSON.parse(fs.readFileSync(0,'utf8')), 'utf8'),ctx);
ctx.elementos = [{bandeja:'bug',inferido:true,lenguaje:'java',nombre:'Calc.producto',cobLineas:100,tipo:'funcion'}];
vm.runInContext("renderCabeceraBandeja(elementos, {perfil:'humo',total_procesados:1,total_seleccionados:1,total_elegibles:1})",ctx);
assert.match($('bnjTitulo').textContent,/regresión inferida a revisar/);
assert.doesNotMatch($('bnjTitulo').textContent,/Todo pasó/);
assert.match($('kpis').innerHTML,/Posibles bugs<\/span><b[^>]*>0<\/b>/);
assert.match($('bnjResumen').textContent,/0 con contrato · 1 de regresión sin contrato documentado/);
ctx.elementos.push({bandeja:'bug',inferido:false,nombre:'Calc.documentado'});
const mixto = vm.runInContext("estadoGeneral(elementos, {})",ctx);
assert.match(mixto.texto,/1 posible bug.*Calc.documentado.*1 hallazgo/);
ctx.elementos = [{bandeja:'paso',inferido:true}];
assert.match(vm.runInContext("estadoGeneral(elementos, {})",ctx).texto,/probado.*regresión sin contrato/);
ctx.elementos.push({bandeja:'omitida',inferido:false});
assert.doesNotMatch(vm.runInContext("estadoGeneral(elementos, {})",ctx).texto,/Todo pasó/);
"""
    resultado = subprocess.run(
        [node, "-e", script],
        input=json.dumps(str(archivo)),
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr

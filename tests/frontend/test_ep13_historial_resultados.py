"""Regresión de EP-13: Historial abre Arquitectura y E2E en Preparar."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CONFIG_PRUEBAS = (
    RAIZ / "src/qagent/frontend/componentes/config-pruebas/config-pruebas.js"
)
NAVEGACION = RAIZ / "src/qagent/frontend/js/navegacion.js"
HISTORIAL = RAIZ / "src/qagent/frontend/componentes/historial/historial.js"


def test_historial_muestra_arquitectura_y_e2e_en_preparar() -> None:
    """Ejecuta el JS real y comprueba pantalla, contenido y Run ID visibles."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite comprobar el comportamiento real del frontend.")
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const entrada = JSON.parse(fs.readFileSync(0, 'utf8'));

class ListaClases {
  constructor(...nombres) { this.nombres = new Set(nombres); }
  add(...nombres) { nombres.forEach(n => this.nombres.add(n)); }
  remove(...nombres) { nombres.forEach(n => this.nombres.delete(n)); }
  contains(nombre) { return this.nombres.has(nombre); }
  toggle(nombre, forzar) {
    const activo = forzar === undefined ? !this.contains(nombre) : Boolean(forzar);
    activo ? this.add(nombre) : this.remove(nombre);
    return activo;
  }
}

const nodos = new Map();
function $(id) {
  if (!nodos.has(id)) nodos.set(id, {
    id, innerHTML:'', textContent:'', disabled:false,
    classList:new ListaClases('hide'),
    setAttribute(){}, scrollIntoView(){},
  });
  return nodos.get(id);
}
const pantallas = ['welcome','open','clone','preview','tests','monitor','exec','export','history','config'];
pantallas.forEach(nombre => $('s-' + nombre));

const api = {
  async obtener_resultado_arquitectura(_ruta, runId) {
    return {ok:true, run_id:runId, reglas:[{
      nombre:'No deben existir ciclos', estado:'incumple',
      hallazgos:[{desde:'interfaz', hacia:'dominio', archivo:'vista.py', linea:3}],
    }]};
  },
  async obtener_resultado_e2e(_ruta, runId) {
    return {ok:true, run_id:runId, status:'falla', summary:{passed:1, failed:1, no_verdict:0},
      routes:[{path:'/error', status:'falla', http_status:500, reason:'HTTP 500', screenshot:'capturas/error.png'}]};
  },
};
const ctx = vm.createContext({
  $, window:{pywebview:{api}}, document:{querySelectorAll:()=>[]},
  registrarComponente(){}, projectPath:'C:/fixture',
  escHtml:valor=>String(valor).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),
  renderExec(){}, renderExport(){}, renderHistory(){}, renderConfig(){}, cargarRecientes(){},
  actualizarSidebar(){}, actualizarPasos(){}, toastError(){}, toast(){},
  console, setTimeout, clearTimeout,
});
const fuente = fs.readFileSync(entrada.config, 'utf8');
for (const nombre of fuente.match(/ICO_[A-Z_]+/g) || []) ctx[nombre] = '';
vm.runInContext(fs.readFileSync(entrada.nav, 'utf8'), ctx);
vm.runInContext(fuente, ctx);

function activarHistorial() {
  pantallas.forEach(nombre => $('s-' + nombre).classList.toggle('hide', nombre !== 'history'));
}
function visible(id) { return !$(id).classList.contains('hide'); }

(async () => {
  activarHistorial();
  await vm.runInContext("abrirResultadoArquitectura('run-arq-175')", ctx);
  assert.equal(visible('s-tests'), true);
  assert.equal(visible('s-config'), false);
  assert.equal(visible('s-history'), false);
  assert.equal(visible('prepArqResultado'), true);
  assert.match($('prepArqResultado').innerHTML, /run-arq-175/);
  assert.match($('prepArqResultado').innerHTML, /reglas incumplidas/);
  assert.match($('prepArqResultado').innerHTML, /vista\.py:3/);

  activarHistorial();
  await vm.runInContext("abrirResultadoE2E('run-e2e-175')", ctx);
  assert.equal(visible('s-tests'), true);
  assert.equal(visible('s-config'), false);
  assert.equal(visible('s-history'), false);
  assert.equal(visible('prepE2EResultado'), true);
  assert.match($('prepE2EResultado').innerHTML, /run-e2e-175/);
  assert.match($('prepE2EResultado').innerHTML, /HTTP 500/);
  assert.match($('prepE2EResultado').innerHTML, /capturas\/error\.png/);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    resultado = subprocess.run(
        [node, "-e", script],
        input=json.dumps({"config": str(CONFIG_PRUEBAS), "nav": str(NAVEGACION)}),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_historial_conserva_apertura_de_corridas_normales_y_antiguas() -> None:
    """El hotfix no altera los fallbacks existentes de Historial."""
    historial = HISTORIAL.read_text(encoding="utf-8")
    funcion = historial.split("function abrirCorridaSeleccionada()", 1)[1].split(
        "function ", 1
    )[0]

    assert "fila.es_arquitectura" in funcion
    assert "abrirResultadoArquitectura(histSel)" in funcion
    assert "fila.es_e2e" in funcion
    assert "abrirResultadoE2E(histSel)" in funcion
    assert "!tieneResultados(fila)" in funcion
    assert "cargarEjecucionReal(histSel)" in funcion

"""Issue 266, fase 1: cifras y estado final de En curso y Resultados.

C1: los endpoints seleccionados cuentan y aparecen en Resultados (en la demostración, como
«No se probaron», porque solo simula funciones). C2: lo estancado o sin veredicto se muestra
como «sin prueba» y el estado final distingue completada, con incidencias y parcial. C3:
«Aprobados» y «Cobertura» dicen sobre cuántos objetivos se calculan.

Se ejecutan los componentes reales en Node (vm), sin navegador; sin Node se omiten.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"

# Entorno mínimo del navegador: nodos falsos para $() y un document con createElement.
_PRELUDIO = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const rutas = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodos = new Map();
function nodo() {
  return {innerHTML: '', textContent: '', style: {}, disabled: false,
    classList: {toggle() {}, add() {}, remove() {}, contains: () => false},
    setAttribute() {}};
}
function $(id) { if (!nodos.has(id)) nodos.set(id, nodo()); return nodos.get(id); }
const documento = {
  querySelector: () => ({textContent: 'tienda'}), querySelectorAll: () => [], addEventListener() {},
  createElement() {
    const d = {_t: ''};
    Object.defineProperty(d, 'innerHTML', {set(v) { d._t = String(v).replace(/<[^>]*>/g, ''); }});
    Object.defineProperty(d, 'textContent', {get() { return d._t; }});
    return d;
  },
};
const ctx = vm.createContext({$, window: {addEventListener() {}}, document: documento, registrarComponente() {},
  docstringDeObjetivo: () => true, etiquetaSinDocstring: () => '',
  escHtml: x => String(x).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
  setInterval: () => 0, clearInterval() {}, console});
const cargar = r => {
  const fuente = fs.readFileSync(r, 'utf8');
  for (const nombre of fuente.match(/ICO_[A-Z_]+/g) || []) if (!(nombre in ctx)) ctx[nombre] = '';
  vm.runInContext(fuente, ctx);
};
rutas.forEach(cargar);
const js = codigo => vm.runInContext(codigo, ctx);
"""


def _node(script: str, *archivos: str) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite ejecutar los componentes JavaScript.")
    rutas = [str(FRONTEND / a) for a in archivos]
    resultado = subprocess.run(
        [node, "-e", _PRELUDIO + script],
        input=json.dumps(rutas),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr or resultado.stdout


DEMO = ("js/estado.js", "js/datos-corrida.js")


def test_c1_la_demostracion_lista_los_endpoints_seleccionados() -> None:
    _node(
        r"""
const todos = js('elementosDemo()');
const endpoints = todos.filter(e => e.tipo === 'endpoint');
const esperados = js('endpointsDeLaDemo()');
assert.ok(esperados.length > 0);
assert.equal(endpoints.length, esperados.length);
for (const e of endpoints) {
  assert.equal(e.bandeja, 'omitida');
  assert.match(e.explicacion, /no ejecuta endpoints/);
}
// Un endpoint sin ruta resuelta o en una carpeta excluida no cuenta como seleccionado.
assert.ok(!esperados.some(e => !e.objetivo));
js('renderCabeceraBandeja(elementosDemo(), null)');
const n = js('RUN.length'), sin = js('sinPruebaDemo()'), eps = esperados.length;
assert.equal($('bnjResumen').textContent.split(':')[0],
  `${n + eps} seleccionados · ${n} elegibles · ${n} procesados (${sin} sin prueba) · ${eps} omitidos · 0 pendientes`);
""",
        *DEMO,
        "componentes/ejecucion/ejecucion.js",
    )


def test_c1_c2_la_corrida_de_demostracion_cuenta_endpoints_y_termina_con_incidencias() -> (
    None
):
    _node(
        r"""
js('reiniciarProgreso(); skipRun();');
const eps = js('endpointsDeLaDemo().length'), sin = js('sinPruebaDemo()');
assert.equal(sin, 2);   // reserve_stock_atomic (rechazada) y validate_credit_card_token (estancada)
assert.equal($('prgTitulo').textContent, 'Corrida completada con incidencias');
assert.equal($('prgAvanceTxt').textContent,
  `9 procesados (2 sin prueba) · ${eps} omitidos · 0 pendientes de ${9 + eps} seleccionados`);
assert.match($('prgAlertaTitulo').textContent, /2 funciones quedaron sin prueba y \d+ endpoints no se ejecutaron/);
""",
        *DEMO,
        "componentes/monitor/monitor.js",
    )


def test_c2_el_estado_final_distingue_completada_incidencias_y_parcial() -> None:
    _node(
        r"""
const t = fin => js('tituloFinCorrida')(fin);
assert.equal(t({ok: true}), 'Corrida completada');
assert.equal(t({ok: true, incidencias: true}), 'Corrida completada con incidencias');
assert.equal(t({ok: true, pendientes: 2}), 'Corrida parcial');
assert.equal(t({ok: false, pendientes: 3}), 'Corrida parcial');
assert.equal(t({ok: false, pendientes: 0}), 'Corrida detenida');
assert.equal(t({ok: false, cancelada: true, pendientes: 4}), 'Corrida cancelada');
""",
        *DEMO,
        "componentes/monitor/monitor.js",
    )


def test_c2_una_estancada_del_backend_no_deja_la_corrida_en_verde() -> None:
    _node(
        r"""
js('reiniciarProgreso(); modoReal = true;');
js(`monitorFinReal({estado: 'fin', run_id: null, estancadas: 1, sin_veredicto: 0, aceptadas: 3,
  bugs_detectados: 0, objetivos_omitidos: 0, total_pendientes: 0, total_seleccionados: 4,
  total_procesados: 4, tipo_terminacion: 'completada_con_errores', motivo: null, tokens: 0})`);
assert.equal($('prgTitulo').textContent, 'Corrida completada con incidencias');
assert.equal($('prgAvanceTxt').textContent, '4 procesados (1 sin prueba) · 0 omitidos · 0 pendientes de 4 seleccionados');
assert.equal($('prgAlertaTitulo').textContent, '1 objetivo quedó sin prueba');
""",
        *DEMO,
        "componentes/monitor/monitor.js",
    )


def test_c2_lo_pendiente_deja_la_corrida_parcial() -> None:
    _node(
        r"""
js('reiniciarProgreso(); modoReal = true;');
js(`monitorFinReal({estado: 'fallo_controlado', run_id: null, estancadas: 0, sin_veredicto: 0,
  aceptadas: 2, bugs_detectados: 0, objetivos_omitidos: 0, total_pendientes: 3,
  total_seleccionados: 5, total_procesados: 2, tipo_terminacion: 'limitada_recursos',
  motivo: 'Se alcanzó el presupuesto de tokens', tokens: 10})`);
assert.equal($('prgTitulo').textContent, 'Corrida parcial');
assert.match($('prgAvanceTxt').textContent, /2 procesados · 0 omitidos · 3 pendientes de 5 seleccionados/);
""",
        *DEMO,
        "componentes/monitor/monitor.js",
    )


def test_c3_aprobados_y_cobertura_dicen_sobre_cuantos_objetivos() -> None:
    _node(
        r"""
// Demostración: la cobertura promedia solo lo que tiene prueba (pasó o posible bug).
js('renderCabeceraBandeja(elementosDemo(), null)');
const conPrueba = js("RUN.filter(f => BANDEJA_DEMO[f.status] === 'paso' || BANDEJA_DEMO[f.status] === 'bug')");
const media = Math.round(conPrueba.reduce((s, f) => s + f.lines_cov, 0) / conPrueba.length);
let kpis = $('kpis').innerHTML;
assert.match(kpis, new RegExp(`<b>${media} %</b>`));
assert.match(kpis, new RegExp(`Promedio de ${conPrueba.length} de 9 objetivos procesados · lo que no tiene prueba no cuenta`));
assert.match(kpis, /<b class="bnj-cifra-aviso">\d+ \/ 9<\/b>/);
assert.match(kpis, /Sobre 9 objetivos procesados · 2 sin prueba · 1 posible bug/);

// Backend: el número es el de results.json y se dice si incluye objetivos sin prueba.
const vista = {run_id: 'r1', perfil: 'std', total_procesados: 3, total_seleccionados: 3,
  total_elegibles: 3, total_pendientes: 0, omitidos: [],
  indicadores: {cobertura: {lineas: 80, ramas: null, exige_ramas: true}, costo: {tokens_total: 10}},
  modulos: [{modulo: 'm.py', pruebas: [
    {funcion: 'a', identificador: 'a', tipo: 'funcion', estado: 'aprobado', cobertura_lineas: 90},
    {funcion: 'b', identificador: 'b', tipo: 'funcion', estado: 'aprobado', cobertura_lineas: 90},
    {funcion: 'c', identificador: 'c', tipo: 'funcion', estado: 'estancado', cobertura_lineas: 60}]}]};
ctx.vista = vista;
js('renderCabeceraBandeja(elementosReales(vista), vista)');
kpis = $('kpis').innerHTML;
assert.match(kpis, /<b>80 %<\/b>/);
assert.match(kpis, /Promedio de 3 de 3 objetivos procesados \(incluye 1 sin prueba\)/);
assert.match(kpis, /<b class="bnj-cifra-aviso">2 \/ 3<\/b>/);
assert.match($('bnjResumen').textContent, /3 procesados \(1 sin prueba\)/);

// Todo aprobado: sin aviso y sin «sin prueba».
vista.modulos[0].pruebas[2].estado = 'aprobado';
js('renderCabeceraBandeja(elementosReales(vista), vista)');
kpis = $('kpis').innerHTML;
assert.match(kpis, /<b class="">3 \/ 3<\/b>/);
assert.doesNotMatch($('bnjResumen').textContent, /sin prueba/);

// Sin cobertura medida (null) no se cuenta como 0 %.
vista.modulos[0].pruebas.forEach(p => { p.cobertura_lineas = null; });
vista.indicadores.cobertura.lineas = null;
js('renderCabeceraBandeja(elementosReales(vista), vista)');
assert.match($('kpis').innerHTML, /Sin objetivos con cobertura medida/);
""",
        *DEMO,
        "componentes/ejecucion/ejecucion.js",
    )


# --- Fases 2 y 3 hechas antes sobre develop (I3, I5, I7, M3) --------------------------------


def _texto(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def test_i3_profundizar_queda_deshabilitado_sin_incluir() -> None:
    vista = _texto("componentes/vista-previa/vista-previa.js")
    celdas = [c[: c.index("</td>")] for c in vista.split('<td class="col-prof">')[1:]]
    funcion = next(c for c in celdas if "escHtml(f.n)" in c)
    endpoint = next(c for c in celdas if "toggleEndpointCrit" in c)
    assert "${f.inc ? '' : 'disabled'}" in funcion
    assert "Incluye la función para poder profundizar en ella." in funcion
    assert "${elegible && e.inc ? '' : 'disabled'}" in endpoint
    assert "Incluye el endpoint para poder profundizar en él." in endpoint


def test_i5_si_solo_faltan_los_tipos_el_titulo_lo_dice() -> None:
    _node(
        r"""
const destino = js('destinoBloqueoPrevio');
assert.equal(destino([{ok: false, tipos: true}, {ok: true}]), 'tipos');
assert.equal(destino([{ok: false, tipos: true}, {ok: false}]), null);
assert.equal(destino([{ok: true}]), null);
""",
        *DEMO,
        "componentes/config-pruebas/config-pruebas.js",
    )
    config = _texto("componentes/config-pruebas/config-pruebas.js")
    assert "=== 'tipos' ? 'Elige qué tipos de prueba hacer'" in config


def test_i7_el_aviso_de_vigencia_dice_que_hacer() -> None:
    config = _texto("componentes/config-pruebas/config-pruebas.js")
    assert "No se pudo comprobar la vigencia de las pruebas guardadas." not in config
    assert (
        "No se pudo confirmar si las pruebas guardadas siguen vigentes. "
        "Vuelve a abrir el proyecto para comprobarlo." in config
    )


def test_m3_los_tokens_sin_dato_no_remiten_a_la_app_dentro_de_la_app() -> None:
    _node(
        r"""
const vista = {run_id: 'r1', perfil: 'std', total_procesados: 1, omitidos: [],
  indicadores: {cobertura: {lineas: null, ramas: null}, costo: {tokens_total: null}},
  modulos: [{modulo: 'm.py', pruebas: [{funcion: 'a', identificador: 'a', tipo: 'funcion', estado: 'aprobado'}]}]};
ctx.vista = vista;
js('renderCabeceraBandeja(elementosReales(vista), vista)');
assert.match($('kpis').innerHTML, /Disponible en la app de escritorio/);
ctx.window.pywebview = {api: {}};
js('renderCabeceraBandeja(elementosReales(vista), vista)');
assert.match($('kpis').innerHTML, /Esta corrida no registró el consumo de tokens/);
assert.doesNotMatch($('kpis').innerHTML, /Disponible en la app de escritorio/);
""",
        *DEMO,
        "componentes/ejecucion/ejecucion.js",
    )

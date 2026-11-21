"""El Monitor conserva el diagnóstico sin pedir resultados de pruebas inexistentes."""

from tests.frontend.test_issue266_cifras_estados import DEMO, _node


def test_construccion_fallida_no_abre_resultados_ni_reportes_inexistentes():
    _node(
        r"""
ctx.cargarEjecucionReal = () => { throw Error('No existe results.json'); };
ctx.cargarReporteReal = () => { throw Error('No existe detalle.json'); };
js('reiniciarProgreso(); modoReal = true; modoRealUsado = true;');
js(`monitorFinReal({estado:'fallo_controlado', run_id:'construccion-fallida',
  carpeta:'.qagent/runs/construccion-fallida', construccion:{estado:'fallido'},
  motivo:'Las fuentes no compilan. No se llamó a la IA.', tokens:0,
  aceptadas:0, bugs_detectados:0, estancadas:0, total_pendientes:1,
  total_seleccionados:1, total_procesados:0, tipo_terminacion:'detenida_error'})`);
assert.equal($('prgTokens').textContent, '0');
assert.match($('prgAlertaTxt').textContent, /No se llamó a la IA/);
assert.ok(!$('prgAcciones').innerHTML.includes('Ver resultados'));
""",
        *DEMO,
        "componentes/monitor/monitor.js",
    )


def test_construccion_aprobada_conserva_la_carga_normal_de_resultados():
    _node(
        r"""
const cargas = [];
ctx.cargarEjecucionReal = id => cargas.push(['resultados', id]);
ctx.cargarReporteReal = id => cargas.push(['reporte', id]);
js('reiniciarProgreso(); modoReal = true; modoRealUsado = true;');
js(`monitorFinReal({estado:'fin', run_id:'compatible', carpeta:'.qagent/runs/compatible',
  construccion:{estado:'aprobado'}, aceptadas:1, bugs_detectados:0,
  estancadas:0, total_pendientes:0, total_seleccionados:1, total_procesados:1, tokens:0})`);
assert.deepEqual(cargas, [['resultados','compatible'], ['reporte','compatible']]);
assert.ok($('prgAcciones').innerHTML.includes('Ver resultados'));
""",
        *DEMO,
        "componentes/monitor/monitor.js",
    )

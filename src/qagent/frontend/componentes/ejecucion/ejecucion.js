// ejecucion.js — pantalla «Resultados» (resultados de la corrida) como bandeja de problemas
// HTML del componente (se monta en el marcador data-componente="ejecucion/ejecucion" de index.html)
// Bandejas por estado a la izquierda, lista priorizada al centro (primero lo que requiere atención) y el
// detalle de la función o endpoint elegido a la derecha. La lista sale de obtener_ejecucion(); el detalle
// (prueba generada, salida, lo esperado e intentos) de obtener_reporte() de la misma corrida.
// Los íconos compartidos (ICO_*) vienen de inicio/modal-abrir.js y modal-clonar.js.
const ICO_COPIAR = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
const ICO_DESCARGAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>';
const ICO_CAPAS = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/></svg>';
const ICO_RELOJ = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
const ICO_DESPLEGAR = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const ICO_SIN_PRUEBA = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/></svg>';
const ICO_OMITIDO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>';

registrarComponente('ejecucion/ejecucion', `<!-- ===== 5. PRUEBAS: BANDEJA DE PROBLEMAS ===== -->
<section id="s-exec" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <header class="ini-barra">
    <nav class="ini-migas" aria-label="Ubicación"><span class="repoName"></span><span aria-hidden="true">/</span><span aria-current="page">Resultados</span></nav>
    <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
  </header>
  <div class="scroll"><div class="page bnj">

    <div class="np-cabecera">
      <div>
        <h1 class="ini-titulo" id="bnjTitulo">Resultados de la corrida</h1>
        <p class="np-subtitulo" id="bnjSub"></p>
      </div>
      <div class="bnj-acciones">
        <button type="button" class="ini-btn ini-btn-principal" onclick="openExport()">${ICO_DESCARGAR}Exportar informe</button>
      </div>
    </div>

    <!-- issue 139: en la app, sin resultados no se muestra la demostración sino este aviso -->
    <div class="np-aviso np-aviso-info hide" id="bnjVacio">${ICO_INFO}<div><b>Este proyecto todavía no tiene resultados</b>
      <span>Cuando una corrida termine, sus resultados aparecerán aquí. Una corrida que no llegó a terminar (por ejemplo, porque se cerró la aplicación) queda en el Historial como «Interrumpida».</span>
      <button type="button" class="ini-enlace" onclick="go('preview')">Ir a Explorar</button></div></div>

    <div class="exp-cifras bnj-cifras" id="kpis"></div>
    <p class="np-meta" id="bnjResumen"></p>

    <div class="bnj-filtros">
      <label class="np-campo exp-buscar"><span class="exp-buscar-ico">${ICO_BUSCAR}</span><input class="np-input" id="execSearch" type="search" placeholder="Buscar función, endpoint o archivo" autocomplete="off" spellcheck="false" oninput="filtrarEjecucion(this.value)" aria-label="Buscar función, endpoint o archivo"></label>
      <div class="np-campo bnj-select"><select class="np-input" id="bnjTipo" aria-label="Tipo" onchange="filterType=this.value;renderExec()"></select>${ICO_DESPLEGAR}</div>
      <div class="np-campo bnj-select"><select class="np-input" id="bnjArchivo" aria-label="Archivo" onchange="filtroArchivo=this.value;renderExec()"></select>${ICO_DESPLEGAR}</div>
    </div>

    <div class="bnj-rejilla">
      <nav class="bnj-bandejas" aria-label="Bandejas"><span class="bnj-etiqueta">Bandejas</span><div id="bnjBandejas"></div></nav>
      <section class="bnj-lista-col" aria-labelledby="bnjListaTitulo">
        <h2 id="bnjListaTitulo">Primero lo que requiere atención</h2>
        <div class="bnj-lista" id="suites" role="listbox" aria-labelledby="bnjListaTitulo"></div>
        <p class="np-meta" id="bnjNotaLista"></p>
      </section>
      <section class="np-tarjeta bnj-detalle" id="bnjDetalle" aria-live="polite"></section>
    </div>

    <div class="bnj-prioridades" id="bnjPrioridades"></div>
    <p class="np-meta bnj-definiciones">Cobertura: porcentaje de líneas del código que ejecutaron las pruebas. Fortaleza de las pruebas: si detectan errores introducidos a propósito; solo se mide en las funciones críticas.</p>
  </div></div>
</section>
`);

// El informe completo ya no es una pantalla: su evidencia está en el detalle de cada elemento y el
// documento formal se genera desde «Exportar informe». Abrir el reporte de una corrida (historial,
// proyectos recientes) lleva a Resultados con esa corrida.
async function cargarReporteReal(runId = null, navegar = true){
  return cargarEjecucionReal(runId, navegar);
}

/* ---------------- Estado de la pantalla ---------------- */
let filterState = 'todos';      // bandeja elegida
let filterType = 'todos';       // funciones, endpoints o ambos
let filtroArchivo = 'todos';
let execSearchQuery = '';
let seleccionBandeja = null;    // id del elemento abierto en el detalle
let ELEMENTOS_BANDEJA = [];     // elementos de la última vista (los onclick usan su índice)

function filtrarEjecucion(val){
  execSearchQuery = (val || '').trim().toLowerCase();
  renderExec();
}
function limpiarBusquedaEjecucion(){
  $('execSearch').value = '';
  filtrarEjecucion('');
}

/* Bandejas para personas, en orden de prioridad. Cada estado del backend (o de la demo) cae en una. */
const BANDEJAS = [
  {k:'bug',      t:'Posibles bugs',             chip:'Posible bug',                   cls:'bug',    ico:() => ICO_ERROR},
  {k:'sin',      t:'Sin prueba',                chip:'No se pudo generar la prueba', cls:'error',  ico:() => ICO_SIN_PRUEBA},
  {k:'tiempo',   t:'Tiempo agotado',            chip:'Tiempo agotado',               cls:'aviso',  ico:() => ICO_RELOJ},
  {k:'repetir',  t:'Requieren corrida nueva',   chip:'Requiere corrida nueva',       cls:'aviso',  ico:() => ICO_REINTENTAR},
  // Seleccionados que no se probaron: sin resultado esperado verificable o ruta sin resolver.
  {k:'omitida',  t:'No se probaron',            chip:'No se probó',                  cls:'aviso',  ico:() => ICO_OMITIDO},
  {k:'paso',     t:'Pasaron',                   chip:'Pasó',                         cls:'exito',  ico:() => ICO_OK},
];
const BANDEJA = Object.fromEntries(BANDEJAS.map(b => [b.k, b]));
const ORDEN_BANDEJA = Object.fromEntries(BANDEJAS.map((b, i) => [b.k, i]));
// Estados reales (vista_ejecucion.py) y de la demostración (ST) → bandeja.
const BANDEJA_REAL = {aprobado:'paso', bug_detectado:'bug', requiere_corrida_nueva:'repetir', rechazado_laundering:'sin', estancado:'sin', sin_veredicto:'sin'};
const BANDEJA_DEMO = {passed:'paso', low_mutation:'paso', rejected_oracle:'bug', rejected_laundering:'sin', stuck:'sin'};
const MOTIVO_SIN_PRUEBA = {
  estancado: 'No se logró una prueba que pase después de todos los intentos.',
  rechazado_laundering: 'Las pruebas generadas debilitaban el criterio esperado y se rechazaron.',
  sin_veredicto: 'La verificación no terminó con un veredicto.',
};
// Por qué quedó sin veredicto (motivo_sin_veredicto de results.json; FIX-02).
const MOTIVO_SIN_VEREDICTO = {
  tiempo_agotado: 'Un agente o el proveedor de IA no respondió a tiempo; la corrida siguió con lo demás.',
  error_contrato_planner: 'La propuesta del Planner no cumplía el contrato, así que no se generó una prueba.',
  error_planner: 'El Planner no pudo planificar este objetivo (por ejemplo, respondió con un formato inválido); la corrida siguió con lo demás.',
};

/* ---------------- Modelo común de cada elemento ---------------- */
// Corrida real: lista de obtener_ejecucion(); el detalle se completa con obtener_reporte().
let ejecucionReal = null;
let detalleReal = null;          // {run_id, porClave: {"modulo::funcion": funcion del reporte}}
let reporteReal = null;          // último obtener_reporte(); lo usa Exportar (corrida y proyecto)
let cargandoDetalle = false;
const tiempoReal = s => s===null || s===undefined ? '—' : (s < 1 ? Math.round(s*1000) + ' ms' : Number(s).toFixed(1) + ' s');
const pctTexto = v => v===null || v===undefined ? '—' : Math.round(Number(v)) + ' %';

function elementosReales(v){
  return [...elementosProbados(v), ...elementosOmitidos(v)];
}
// Lo que se seleccionó pero no se probó, con el motivo que dio el backend.
function elementosOmitidos(v){
  return (v.omitidos || []).map(o => ({
    id: 'omitido::' + o.modulo + '::' + o.objetivo, modulo: o.modulo, tipo: o.tipo,
    nombre: o.identificador || o.objetivo, endpoint: o.tipo === 'endpoint',
    bandeja: 'omitida', critica: false, omitido: true, explicacion: o.motivo || null,
    sinDocstring: o.tipo === 'funcion' && docstringDeObjetivo(o.modulo, o.objetivo) === false,
  }));
}
function elementosProbados(v){
  return v.modulos.flatMap(m => m.pruebas.map(p => {
    const bandeja = BANDEJA_REAL[p.estado] || 'sin';
    const det = detalleReal && detalleReal.run_id === v.run_id ? detalleReal.porClave[m.modulo + '::' + p.funcion] : null;
    return {
      id: m.modulo + '::' + p.funcion, modulo: m.modulo, tipo: p.tipo,
      nombre: p.identificador, endpoint: p.tipo === 'endpoint',
      bandeja, critica: !!p.critical, intento: p.intento_final, duracion: p.duracion_s,
      sinDocstring: docstringDeObjetivo(m.modulo, p.funcion) === false,
      duracionGeneracion: p.duracion_generacion_s, duracionSandbox: p.duracion_sandbox_s,
      duracionPytest: p.duracion_pytest_s,
      cobLineas: p.cobertura_lineas, cobRamas: p.cobertura_ramas, estadoBackend: p.estado,
      motivoSinVeredicto: p.motivo_sin_veredicto || null,
      ...detalleDeReporte(det),
    };
  }));
}
// Del reporte: prueba generada, salida de pytest, lo esperado y si se bloqueó un intento de debilitarla.
function detalleDeReporte(f){
  if (!f) return {cargando: !!(window.pywebview && window.pywebview.api && window.pywebview.api.obtener_reporte)};
  const intentos = f.intentos || [];
  const ultimo = intentos[intentos.length - 1] || {};
  const casos = (f.contrato_http && f.contrato_http.casos) || [];
  const comportamiento = f.contrato && Array.isArray(f.contrato.comportamiento_esperado) ? f.contrato.comportamiento_esperado : [];
  const esperado = casos.length
    ? casos.slice(0, 2).map(c => `${c.descripcion || c.id || 'Caso'}: ${JSON.stringify(c.respuesta_esperada)}`).join('\n')
    : comportamiento.slice(0, 3).join('\n');
  return {
    explicacion: ultimo.feedback || null,
    codigo: f.codigo || null,
    traza: f.traza || null,
    esperado: esperado || null,
    debilitada: intentos.some(i => i.laundering_detectado),
    firma: f.firma || f.manejador || null,
    // Ejecución del último intento que llegó al sandbox: cada caso con esperado y obtenido.
    ...ejecucionDeIntentos(intentos),
    // Evidencia de auditoría (antes en la pantalla del informe).
    controles: Array.isArray(f.controles) ? f.controles : [],
    casos,
    categorias: f.texto_categorias || null,
    intentos,
    fortaleza: f.mutation_score === null || f.mutation_score === undefined ? null : Number(f.mutation_score),
    sobrevivientes: (f.mutacion && f.mutacion.sobrevivientes) || [],
  };
}
function ejecucionDeIntentos(intentos){
  const conEjecucion = intentos.filter(i => i.ejecucion);
  const ej = conEjecucion.length ? conEjecucion[conEjecucion.length - 1].ejecucion : null;
  if (!ej) return {casosEjecutados: [], lineasSinCubrir: null, salida: null, fallo: null};
  const casosEjecutados = Array.isArray(ej.casos) ? ej.casos : [];
  // El primer caso que falló con valores es el que mejor explica el posible bug.
  const fallo = casosEjecutados.find(c => (c.resultado === 'fallo' || c.resultado === 'error')
    && ((c.esperado !== null && c.esperado !== undefined) || (c.obtenido !== null && c.obtenido !== undefined))) || null;
  return {casosEjecutados, lineasSinCubrir: Array.isArray(ej.lineas_sin_cubrir) ? ej.lineas_sin_cubrir.map(Number) : null, salida: ej.salida || null, fallo};
}
// Demostración (sin pywebview): datos de js/datos-corrida.js.
function elementosDemo(){
  return RUN.map(fn => ({
    id: fn.id, modulo: fn.module, tipo: 'funcion', nombre: fn.name, endpoint: false,
    bandeja: BANDEJA_DEMO[fn.status] || 'sin', critica: !!fn.crit, intento: fn.iterations,
    sinDocstring: docstringDeObjetivo(fn.module, fn.name) === false,
    duracion: null, cobLineas: fn.lines_cov, cobRamas: fn.branch_cov,
    explicacion: fn.diag || null, codigo: fn.code || null, traza: (fn.logs || []).join('\n') || null,
    esperado: fn.cmp ? fn.cmp.original : null,
    debilitada: fn.status === 'rejected_laundering' || (fn.cmp && fn.cmp.state === 'relaxed'),
    firma: fn.signature || null, estadoBackend: fn.status,
  }));
}

/* ---------------- Carga de la corrida real ---------------- */
let cargandoEjecucion = false;
// `silencioso`: sin aviso de error cuando no haber resultados es un caso esperado
// (al reabrir un proyecto cuyas corridas se interrumpieron, issue 139).
async function cargarEjecucionReal(runId = null, navegar = true, {silencioso = false} = {}){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.obtener_ejecucion) return;
  if(cargandoEjecucion) return;
  cargandoEjecucion = true;
  try {
    const r = await api.obtener_ejecucion(projectPath, runId || null);
    if(!r || !r.ok){
      if (!silencioso && typeof toastError === 'function') toastError(escHtml((r && r.motivo) || 'No se pudieron leer los resultados de la corrida.'));
      return;
    }
    ejecucionReal = r; filterState = 'todos'; filterType = 'todos'; filtroArchivo = 'todos'; seleccionBandeja = null;
    if (typeof desbloquearVista === 'function') {
      desbloquearVista('exec');
    }
    if (navegar) go('exec'); else renderExec();
  } finally {
    cargandoEjecucion = false;
  }
}
// El detalle sale del reporte de la misma corrida; se pide una vez por corrida.
async function cargarDetalleReal(runId){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.obtener_reporte || cargandoDetalle) return;
  if(detalleReal && detalleReal.run_id === runId) return;
  cargandoDetalle = true;
  try {
    const r = await api.obtener_reporte(projectPath, runId);
    const porClave = {};
    if (r && r.ok) {
      reporteReal = r;   // Exportar lee de aquí la corrida y el proyecto
      (r.funciones || []).forEach(f => { porClave[f.modulo + '::' + f.funcion] = f; });
    }
    detalleReal = {run_id: runId, porClave};
  } catch (err) {
    console.error('Error al leer el detalle de la corrida:', err);
    detalleReal = {run_id: runId, porClave: {}};
  } finally {
    cargandoDetalle = false;
  }
  renderExec();
}


/* ---------------- Renderizado ---------------- */
// Dentro de la app de escritorio (pywebview) los datos son siempre los del proyecto.
function enAppEscritorio(){ return !!(window.pywebview && window.pywebview.api); }
function renderExec(){
  if (typeof desbloquearVista === 'function') {
    desbloquearVista('exec');
  }
  const v = ejecucionReal;
  // issue 139: la demostración es solo para el navegador sin Python; en la app, sin
  // resultados se muestra un estado vacío, nunca datos de ejemplo como si fueran reales.
  const sinResultados = !v && enAppEscritorio();
  $('s-exec').classList.toggle('bnj-sin-datos', sinResultados);
  $('bnjVacio').classList.toggle('hide', !sinResultados);
  if (sinResultados) {
    $('bnjTitulo').textContent = 'Resultados';
    $('bnjSub').textContent = document.querySelector('.ini-migas .repoName') ? document.querySelector('.ini-migas .repoName').textContent : '';
    ['kpis', 'bnjResumen', 'bnjBandejas', 'suites', 'bnjNotaLista', 'bnjDetalle', 'bnjPrioridades'].forEach(id => { $(id).innerHTML = ''; });
    ELEMENTOS_BANDEJA = [];
    return;
  }
  if (v) cargarDetalleReal(v.run_id);
  const todos = v ? elementosReales(v) : elementosDemo();
  todos.sort((a, b) => ORDEN_BANDEJA[a.bandeja] - ORDEN_BANDEJA[b.bandeja] || (b.critica - a.critica));
  ELEMENTOS_BANDEJA = todos;

  renderCabeceraBandeja(todos, v);
  renderFiltrosBandeja(todos);

  // Filtros: tipo y archivo, búsqueda y bandeja.
  const filtrados = todos.filter(e =>
    (filterType === 'todos' || e.tipo === filterType) &&
    (filtroArchivo === 'todos' || e.modulo === filtroArchivo) &&
    (!execSearchQuery || (e.nombre + ' ' + e.modulo).toLowerCase().includes(execSearchQuery)));
  const cuenta = k => filtrados.filter(e => e.bandeja === k).length;
  $('bnjBandejas').innerHTML = [{k:'todos', t:'Todos', ico:() => ICO_CAPAS}, ...BANDEJAS].map(b => {
    const n = b.k === 'todos' ? filtrados.length : cuenta(b.k);
    if (b.k !== 'todos' && b.k !== 'paso' && !n && filterState !== b.k) return '';
    return `<button type="button" class="bnj-bandeja ${filterState === b.k ? 'on' : ''} ${b.cls ? 'bnj-' + b.cls : ''}" onclick="filterState='${b.k}';renderExec()">
      <span class="bnj-bandeja-ico">${b.ico()}</span><span class="bnj-bandeja-n">${n}</span><span class="bnj-bandeja-t">${b.t}</span></button>`;
  }).join('') + '<span class="np-meta bnj-orden">Orden: prioridad y archivo</span>';

  const lista = filtrados.filter(e => filterState === 'todos' || e.bandeja === filterState);
  if (!lista.some(e => e.id === seleccionBandeja)) seleccionBandeja = lista.length ? lista[0].id : null;
  $('suites').innerHTML = lista.map(e => {
    const b = BANDEJA[e.bandeja];
    const accion = e.bandeja === 'tiempo' ? `<button type="button" class="ini-enlace bnj-accion" onclick="event.stopPropagation();go('config')">Ver tiempo máximo →</button>` : '';
    return `<div class="bnj-item ${e.id === seleccionBandeja ? 'on' : ''}" role="option" aria-selected="${e.id === seleccionBandeja}" tabindex="0"
        onclick="seleccionarBandeja(${ELEMENTOS_BANDEJA.indexOf(e)})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}">
      <div class="bnj-item-cab"><span class="bnj-nombre">${escHtml(e.nombre)}</span>${e.sinDocstring ? etiquetaSinDocstring(e.tipo, {enfocable: false}) : ''}${e.critica ? '<span class="bnj-critica">Crítica</span>' : ''}</div>
      <span class="bnj-ruta">${escHtml(e.modulo)}</span>
      <span class="np-chip np-chip-${b.cls}">${b.ico()}${b.chip}</span>${accion}
    </div>`;
  }).join('') || `<div class="bnj-vacio">${execSearchQuery ? 'Nada coincide con la búsqueda.' : 'No hay resultados en esta bandeja.'}
      ${execSearchQuery ? '<button type="button" class="ini-enlace" onclick="limpiarBusquedaEjecucion()">Limpiar búsqueda</button>' : ''}</div>`;
  $('bnjNotaLista').textContent = `${lista.length} de ${todos.length} resultados`;

  renderDetalleBandeja(todos.find(e => e.id === seleccionBandeja));
  renderPrioridades(todos);
}
function seleccionarBandeja(i){ const e = ELEMENTOS_BANDEJA[i]; if(e){ seleccionBandeja = e.id; renderExec(); } }

// Estado general de la corrida: lo usan el título de Resultados y el resumen de Exportar.
// Mismo criterio que respuesta_principal() en storage/vista_ejecucion.py (informes):
// «Todo pasó» solo si se probó algo, nada falló ni quedó sin prueba, nada se omitió y la
// corrida terminó.
function estadoGeneral(todos, v){
  const n = k => todos.filter(e => e.bandeja === k).length;
  const bugs = todos.filter(e => e.bandeja === 'bug');
  const omitidas = n('omitida'), probados = todos.length - omitidas;
  const sinPrueba = n('sin') + n('tiempo') + n('repetir');
  const incompleta = !!(v && (v.es_parcial || ['detenida_error', 'cancelada', 'limitada_recursos'].includes(v.tipo_terminacion)));
  const pendientes = v && Number.isFinite(Number(v.total_pendientes)) ? Number(v.total_pendientes) : 0;
  const noSeProbaron = `${omitidas} ${omitidas === 1 ? 'objetivo no se probó' : 'objetivos no se probaron'}`;
  const quedaronPendientes = `${pendientes} ${pendientes === 1 ? 'objetivo quedó pendiente' : 'objetivos quedaron pendientes'}`;
  // `corto`: la etiqueta del chip de Exportar.
  if (bugs.length) return {tipo:'bug', corto:`${bugs.length} ${bugs.length === 1 ? 'posible bug' : 'posibles bugs'}`,
    texto:`${bugs.length} ${bugs.length === 1 ? 'posible bug' : 'posibles bugs'}. Empieza por ${bugs[0].nombre}.`};
  if (!probados) return {tipo:'aviso', corto:'Nada probado', texto: incompleta ? `La corrida se detuvo antes de probar algo: ${quedaronPendientes}.`
    : omitidas ? `No se probó nada: ${noSeProbaron}.` : 'No se probó ninguna función ni endpoint.'};
  if (sinPrueba) return {tipo:'aviso', corto:'Faltan pruebas por revisar', texto:'Sin posibles bugs, pero faltan pruebas por revisar.'};
  if (omitidas && incompleta) return {tipo:'aviso', corto:'Corrida incompleta', texto:`Sin posibles bugs en lo probado, pero ${noSeProbaron} y ${quedaronPendientes}.`};
  if (omitidas) return {tipo:'aviso', corto:`${omitidas} sin probar`, texto:`Sin posibles bugs en lo probado, pero ${noSeProbaron}.`};
  if (incompleta) return {tipo:'aviso', corto:'Corrida incompleta', texto:`Sin posibles bugs en lo probado, pero la corrida no terminó: ${quedaronPendientes}.`};
  return {tipo:'exito', corto:'Todo pasó', texto:`Todo pasó: ${probados} ${probados === 1 ? 'función o endpoint verificado' : 'funciones y endpoints verificados'}.`};
}

// Título que responde la pregunta: cuántos posibles bugs y por dónde empezar.
function renderCabeceraBandeja(todos, v){
  const n = k => todos.filter(e => e.bandeja === k).length;
  const bugs = todos.filter(e => e.bandeja === 'bug');
  $('bnjTitulo').textContent = estadoGeneral(todos, v).texto;
  const duracion = v && typeof v.duracion_total_s === 'number' ? v.duracion_total_s : null;
  const partes = [document.querySelector('.ini-migas .repoName') ? document.querySelector('.ini-migas .repoName').textContent : '', 'Python'];
  if (v && v.fecha) partes.push(new Date(v.fecha).toLocaleString('es-PE', {day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'}));
  if (duracion !== null) partes.push('Duración total medida ' + (duracion >= 60 ? `${Math.floor(duracion / 60)} min ${Math.round(duracion % 60)} s` : tiempoReal(duracion)));
  if (v && v.es_simulado) partes.push('IA simulada');
  if (v && v.es_humo) partes.push('Corrida Humo: lo principal es cuántas pruebas pasan');   // #75
  if (v && v.motivo_fallo) partes.push('Detención: ' + v.motivo_fallo);
  $('bnjSub').textContent = partes.filter(Boolean).join(' · ');

  // Cifras: pruebas que pasan, posibles bugs, cobertura y tokens (nunca costos).
  const total = todos.length, pasaron = n('paso'), omitidas = n('omitida');
  const procesados = v && Number.isFinite(Number(v.total_procesados)) ? Number(v.total_procesados) : total - omitidas;
  const seleccionados = v && Number.isFinite(Number(v.total_seleccionados)) ? Number(v.total_seleccionados) : total;
  const elegibles = v && Number.isFinite(Number(v.total_elegibles)) ? Number(v.total_elegibles) : Math.max(0, seleccionados - omitidas);
  const pendientes = v && Number.isFinite(Number(v.total_pendientes)) ? Number(v.total_pendientes) : Math.max(0, elegibles - procesados);
  const porRevisar = Math.max(0, procesados - pasaron);
  const subPasaron = [`${porRevisar} procesados con algo por revisar`, omitidas ? `${omitidas} sin probar (omitidos)` : '', pendientes ? `${pendientes} pendientes` : ''].filter(Boolean).join(' · ');
  const k = v ? v.indicadores : null;
  const cobertura = k ? k.cobertura.lineas : (total ? todos.reduce((s, e) => s + (Number(e.cobLineas) || 0), 0) / total : null);
  const ramas = k ? k.cobertura.ramas : null;
  const tokens = k ? k.costo.tokens_total : null;
  const reales = k && k.costo ? k.costo.tokens_reales : null;
  const estimados = k && k.costo ? k.costo.tokens_estimados : null;
  const subTokens = tokens === null
    ? 'Disponible en la app de escritorio'
    : (estimados > 0)
    ? `${Number(reales || 0).toLocaleString('es-PE')} reales · ${Number(estimados).toLocaleString('es-PE')} estimados`
    : 'Sumando las tres etapas';
  $('kpis').innerHTML = `
    <div class="exp-cifra"><span class="exp-cifra-etq">Aprobados</span><b>${pasaron} / ${procesados}</b><span class="exp-cifra-sub">${subPasaron}</span></div>
    <div class="exp-cifra"><span class="exp-cifra-etq">Posibles bugs</span><b class="${bugs.length ? 'bnj-cifra-bug' : ''}">${bugs.length}</b><span class="exp-cifra-sub">En ${bugs.length} de ${procesados} objetivos procesados</span></div>
    <div class="exp-cifra"><span class="exp-cifra-etq" title="Porcentaje de líneas del código que ejecutaron las pruebas">Cobertura ⓘ</span><b>${pctTexto(cobertura)}</b><span class="exp-cifra-sub">${k && k.cobertura.exige_ramas === false ? 'Ramas no exigidas en Humo' : ramas !== null && ramas !== undefined ? pctTexto(ramas) + ' de las ramas' : 'De las líneas del código'}</span></div>
    <div class="exp-cifra"><span class="exp-cifra-etq">Tokens de la corrida</span><b>${tokens === null ? '—' : Number(tokens).toLocaleString('es-PE')}</b><span class="exp-cifra-sub">${subTokens}</span></div>`;
  const etiquetasResumen = {
    bug: ['posible bug', 'posibles bugs'], sin: ['sin prueba', 'sin pruebas'],
    tiempo: ['tiempo agotado', 'tiempos agotados'], repetir: ['requiere corrida nueva', 'requieren corrida nueva'],
    omitida: ['no se probó', 'no se probaron'], paso: ['pasó', 'pasaron'],
  };
  $('bnjResumen').textContent = `${seleccionados} seleccionados · ${elegibles} elegibles · ${procesados} procesados · ${omitidas} omitidos · ${pendientes} pendientes: ` +
    BANDEJAS.map(b => [n(b.k), b.k]).filter(([c]) => c).map(([c, k]) => `${c} ${etiquetasResumen[k][c === 1 ? 0 : 1]}`).join(' · ');
}
function renderFiltrosBandeja(todos){
  const tipos = [...new Set(todos.map(e => e.tipo))];
  $('bnjTipo').innerHTML = `<option value="todos">Funciones y endpoints</option>`
    + (tipos.includes('funcion') ? `<option value="funcion" ${filterType === 'funcion' ? 'selected' : ''}>Solo funciones</option>` : '')
    + (tipos.includes('endpoint') ? `<option value="endpoint" ${filterType === 'endpoint' ? 'selected' : ''}>Solo endpoints</option>` : '');
  const archivos = [...new Set(todos.map(e => e.modulo))].sort();
  $('bnjArchivo').innerHTML = `<option value="todos">Todos los archivos</option>`
    + archivos.map(a => `<option value="${escHtml(a)}" ${filtroArchivo === a ? 'selected' : ''}>${escHtml(a)}</option>`).join('');
}

// Panel derecho: la evidencia del elemento elegido.
function renderDetalleBandeja(e){
  if (!e) { $('bnjDetalle').innerHTML = '<p class="np-texto">Elige una función o un endpoint para ver su evidencia.</p>'; return; }
  const b = BANDEJA[e.bandeja];
  const explicacion = e.explicacion || MOTIVO_SIN_VEREDICTO[e.motivoSinVeredicto]
    || (e.bandeja === 'sin' ? MOTIVO_SIN_PRUEBA[e.estadoBackend] : null)
    || (e.bandeja === 'repetir' ? 'El código cambió desde que se guardó esta prueba: hay que generarla de nuevo.' : null)
    || (e.bandeja === 'paso' ? 'La prueba pasó en el entorno aislado.' : null);
  const cargando = e.cargando ? '<p class="np-meta">Cargando la evidencia…</p>' : '';
  $('bnjDetalle').innerHTML = `
    <div class="bnj-det-cab">
      <div><h2 class="bnj-det-nombre">${escHtml(e.nombre)}${e.sinDocstring ? etiquetaSinDocstring(e.tipo) : ''}</h2><span class="bnj-ruta">${escHtml(e.modulo)}${e.firma ? ' · ' + escHtml(e.firma) : ''}</span></div>
      ${e.critica ? '<span class="np-chip np-chip-progreso">Crítica</span>' : ''}
    </div>
    <span class="np-chip np-chip-${b.cls}">${b.ico()}${e.bandeja === 'bug' ? 'Posible bug en tu código' : b.chip}</span>
    ${explicacion ? `<p class="bnj-explicacion">${escHtml(explicacion)}</p>` : ''}
    ${e.omitido && e.tipo === 'funcion' ? '<p class="np-meta">Para probarla, describe en su docstring qué debe devolver o qué error lanza. QAgent no deduce el resultado esperado ejecutando el código.</p>' : ''}
    ${cargando}
    ${e.fallo ? `<div class="bnj-valores">
        <div class="bnj-esperado"><span class="bnj-caja-etq">Esperado</span><pre>${escHtml(e.fallo.esperado ?? '—')}</pre></div>
        <div class="bnj-obtenido"><span class="bnj-caja-etq">Obtenido${e.fallo.operador && e.fallo.operador !== '==' ? ' (condición: ' + escHtml(e.fallo.operador) + ')' : ''}</span><pre>${escHtml(e.fallo.obtenido ?? '—')}</pre></div>
      </div>`
      : e.esperado ? `<div class="bnj-esperado"><span class="bnj-caja-etq">Esperado según el contrato</span><pre>${escHtml(e.esperado)}</pre></div>` : ''}
    ${e.codigo ? `<div class="bnj-bloque"><div class="bnj-bloque-cab"><b>Prueba generada</b><button type="button" class="ini-enlace" onclick="copiarPruebaBandeja()">${ICO_COPIAR}Copiar prueba</button></div>
      <pre class="bnj-codigo" id="bnjCodigo">${escHtml(e.codigo)}</pre></div>` : ''}
    ${e.lineasSinCubrir ? `<p class="bnj-sin-probar ${e.lineasSinCubrir.length ? '' : 'completo'}">${e.lineasSinCubrir.length ? 'Código sin probar · líneas ' + e.lineasSinCubrir.join(', ') : 'Todas las líneas de la función se ejecutaron en las pruebas'}</p>` : ''}
    <p class="np-meta bnj-datos">${e.intento ? `${e.intento} de 3 intentos` : ''}${e.cobLineas !== null && e.cobLineas !== undefined ? ` · cobertura ${pctTexto(e.cobLineas)} de líneas${e.cobRamas !== null && e.cobRamas !== undefined ? ' y ' + pctTexto(e.cobRamas) + ' de ramas' : ''}` : ''}${e.duracion !== null && e.duracion !== undefined ? ' · ' + tiempoReal(e.duracion) + ' medidos' : ''}${e.duracionGeneracion !== null && e.duracionGeneracion !== undefined ? ` · escritura ${tiempoReal(e.duracionGeneracion)}` : ''}${e.duracionSandbox !== null && e.duracionSandbox !== undefined ? ` · sandbox ${tiempoReal(e.duracionSandbox)}` : ''}${e.duracionPytest !== null && e.duracionPytest !== undefined ? ` · pytest ${tiempoReal(e.duracionPytest)}` : ''}</p>
    ${e.traza || e.salida ? `<details class="np-detalle"><summary>Ver detalle técnico</summary><pre class="np-log bnj-salida-pytest">${escHtml(e.traza || e.salida)}</pre></details>` : ''}
    ${e.debilitada ? `<div class="np-aviso np-aviso-aviso">${ICO_AVISO_CLON}<div><b>Criterio original conservado</b><span>Se bloqueó un intento de debilitar esta prueba. ${e.bandeja === 'bug' ? 'El posible bug sigue visible.' : ''}</span></div></div>` : ''}
    ${evidenciaAuditoria(e)}`;
}

/* Evidencia de auditoría: controles de integridad, casos del contrato, intentos y fortaleza de
   las pruebas. Plegada por defecto; solo aparecen los bloques que la corrida guardó. */
const CONTROL_ESTADO = {ok:['exito', () => ICO_OK, 'En orden'], falla:['bug', () => ICO_ERROR, 'No cumple'],
  no_aplica:['neutro', () => ICO_CIRCULO, 'No aplica'], pendiente:['neutro', () => ICO_CIRCULO, 'Pendiente'], sin_dato:['neutro', () => ICO_CIRCULO, 'Sin dato']};
const DECISION_TEXTO = {accept:'Aceptada', retry:'Se reintentó', bug_detectado:'Posible bug', stalled:'Sin prueba válida', requiere_corrida_nueva:'Requiere corrida nueva'};
const RESULTADO_CASO = {paso:['exito', () => ICO_OK, 'Pasó'], fallo:['bug', () => ICO_ERROR, 'Falló'],
  error:['bug', () => ICO_ERROR, 'Error'], omitido:['neutro', () => ICO_CIRCULO, 'Omitido']};
// Un caso de pytest en el sandbox. Los que fallan muestran dónde, los valores, la pila y la traza.
function casoEjecutadoHtml(c){
  const [cls, ico, txt] = RESULTADO_CASO[c.resultado] || RESULTADO_CASO.error;
  const falla = c.resultado === 'fallo' || c.resultado === 'error';
  const valores = falla && ((c.esperado !== null && c.esperado !== undefined) || (c.obtenido !== null && c.obtenido !== undefined))
    ? `<pre>Esperado: ${escHtml(c.esperado ?? '—')}\nObtenido: ${escHtml(c.obtenido ?? '—')}</pre>` : '';
  const pila = (c.pila || []).map(m => `${escHtml(m.archivo)}:${Number(m.linea)}${m.detalle ? ' · ' + escHtml(m.detalle) : ''}${m.codigo ? '\n    ' + escHtml(m.codigo) : ''}`).join('\n');
  return `<li class="bnj-ev-${cls}"><span class="bnj-ev-ico">${ico()}</span><span>
    <span><span class="np-mono">${escHtml(c.nombre || '')}</span> · ${txt}${c.duracion_s ? ' · ' + tiempoReal(c.duracion_s) : ''}</span>
    ${falla && c.mensaje ? `<span class="np-meta">${escHtml(c.tipo_error ? c.tipo_error + ': ' : '')}${escHtml(String(c.mensaje).split('\n')[0])}</span>` : ''}
    ${falla && c.archivo ? `<span class="np-meta">En ${escHtml(c.archivo)}:${Number(c.linea)}${c.codigo ? ' → ' + escHtml(c.codigo) : ''}</span>` : ''}
    ${valores}
    ${pila ? `<details class="np-detalle"><summary>Pila de llamadas</summary><pre>${pila}</pre></details>` : ''}
    ${c.traza ? `<details class="np-detalle"><summary>Traza completa de pytest</summary><pre>${escHtml(c.traza)}</pre></details>` : ''}
  </span></li>`;
}
function evidenciaAuditoria(e){
  const bloques = [];
  if (e.casosEjecutados && e.casosEjecutados.length) {
    const pasaron = e.casosEjecutados.filter(c => c.resultado === 'paso').length;
    bloques.push(`<div class="bnj-ev"><b>Casos ejecutados · ${pasaron} de ${e.casosEjecutados.length} pasaron</b><ul>${e.casosEjecutados.map(casoEjecutadoHtml).join('')}</ul></div>`);
  }
  if (e.controles && e.controles.length) {
    const enOrden = e.controles.filter(c => c.estado === 'ok').length;
    bloques.push(`<div class="bnj-ev"><b>Controles de integridad · ${enOrden} de ${e.controles.length} en orden</b><ul>${e.controles.map(c => {
      const [cls, ico, txt] = CONTROL_ESTADO[c.estado] || CONTROL_ESTADO.sin_dato;
      return `<li class="bnj-ev-${cls}"><span class="bnj-ev-ico">${ico()}</span><span>${escHtml(c.etiqueta || c.clave || '')}<span class="np-meta">${escHtml(c.nota || txt)}</span></span></li>`;
    }).join('')}</ul></div>`);
  }
  if ((e.casos && e.casos.length) || e.categorias) {
    bloques.push(`<div class="bnj-ev"><b>Casos del contrato${e.categorias ? ' · ' + escHtml(e.categorias) : ''}</b>${(e.casos || []).map(c => `<div class="bnj-ev-caso">
      <span>${escHtml(c.descripcion || c.id || 'Caso')}</span>
      <pre>Petición: ${escHtml(JSON.stringify(c.peticion))}\nRespuesta esperada: ${escHtml(JSON.stringify(c.respuesta_esperada))}</pre></div>`).join('')}</div>`);
  }
  if (e.intentos && e.intentos.length) {
    bloques.push(`<div class="bnj-ev"><b>Historial de intentos</b><ol>${e.intentos.map((i, n) => `<li><span class="bnj-ev-num">Intento ${escHtml(String(i.intento || n + 1))}</span>
      <span>${escHtml(DECISION_TEXTO[i.decision] || i.decision || '—')}${i.laundering_detectado ? ' · se bloqueó debilitarla' : ''}${i.tipo_fallo ? ' · ' + escHtml(i.tipo_fallo) : ''}${i.duracion_s !== null && i.duracion_s !== undefined ? ' · ' + tiempoReal(i.duracion_s) : ''}
      ${i.feedback ? `<span class="np-meta">${escHtml(i.feedback)}</span>` : ''}</span></li>`).join('')}</ol></div>`);
  }
  if (e.fortaleza !== null && e.fortaleza !== undefined) {
    const vivos = e.sobrevivientes || [];
    bloques.push(`<div class="bnj-ev"><b>Fortaleza de las pruebas · ${Math.round(e.fortaleza)} %</b>
      <span class="np-meta">${vivos.length ? `${vivos.length} ${vivos.length === 1 ? 'cambio introducido a propósito no fue detectado' : 'cambios introducidos a propósito no fueron detectados'}:` : 'Las pruebas detectaron todos los cambios introducidos a propósito.'}</span>
      ${vivos.length ? `<ul>${vivos.map(s => `<li><span class="bnj-ev-num">${s.linea === null || s.linea === undefined ? 'Línea —' : 'Línea ' + Number(s.linea)}</span><code>${escHtml(s.cambio || s.mutante || '')}</code></li>`).join('')}</ul>` : ''}</div>`);
  }
  if (!bloques.length) return '';
  return `<details class="np-detalle bnj-evidencia"><summary>Evidencia de auditoría</summary><div class="bnj-ev-lista">${bloques.join('')}</div></details>`;
}
function copiarPruebaBandeja(){
  const texto = $('bnjCodigo') ? $('bnjCodigo').textContent : '';
  if (!texto) return;
  const ok = () => toast('Prueba copiada.');
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(texto).then(ok, () => toastError('No se pudo copiar.'));
  else toastError('No se pudo copiar.');
}

// Prioridades: los posibles bugs, críticos primero (ya vienen ordenados).
function renderPrioridades(todos){
  const bugs = todos.filter(e => e.bandeja === 'bug').slice(0, 3);
  $('bnjPrioridades').innerHTML = bugs.map((e, i) => `<button type="button" class="np-tarjeta bnj-prioridad" onclick="filterState='todos';seleccionarBandeja(${ELEMENTOS_BANDEJA.indexOf(e)})">
      <span class="bnj-prioridad-n">Prioridad ${i + 1}</span><b>Corrige ${escHtml(e.nombre)}</b>
      <span class="np-meta">${escHtml((e.explicacion || 'La prueba encontró un comportamiento distinto al esperado.').split(/(?<=\.)\s/)[0])}</span></button>`).join('');
}

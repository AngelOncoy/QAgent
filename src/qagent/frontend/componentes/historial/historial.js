// historial.js — pantalla «Historial»: corridas del proyecto, comparación con la anterior y pruebas guardadas
// HTML del componente (se monta en el marcador data-componente="historial/historial" de index.html)
// Dos estados: vacío («Aún no hay corridas») y con datos (tabla de corridas, «Mejoró frente a la anterior»
// y «Pruebas guardadas»). Los datos salen de obtener_historial(); sin pywebview se usa una demostración.
// Los íconos compartidos (ICO_*) vienen de inicio/, ejecucion/ y exportar/.
const ICO_HISTORIAL = '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg>';
const ICO_COMPARAR = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="6" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M6 8v5a3 3 0 0 0 3 3h4M18 16v-5a3 3 0 0 0-3-3h-4"/><path d="m11 14 2 2-2 2M13 6l-2 2 2 2"/></svg>';
const ICO_PRUEBAS = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M8 7V4h8l4 4v10h-4"/><path d="M4 8h8l4 4v8H4z"/><path d="M12 8v4h4"/></svg>';
const ICO_CALENDARIO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>';
const ICO_FILTRO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4"/></svg>';

registrarComponente('historial/historial', `<!-- ===== HISTORIAL (por proyecto) ===== -->
<section id="s-history" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <header class="ini-barra">
    <nav class="ini-migas" aria-label="Ubicación"><span class="repoName"></span><span aria-hidden="true">/</span><span aria-current="page" id="histMiga">Historial</span></nav>
    <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
  </header>
  <div class="scroll"><div class="page hst">

    <div class="np-cabecera">
      <div>
        <h1 class="ini-titulo" id="histTitulo">Historial</h1>
        <p class="np-subtitulo" id="histSub"></p>
      </div>
      <button type="button" class="ini-btn ini-btn-principal hide" id="histAbrir" onclick="abrirCorridaSeleccionada()">${ICO_DOCUMENTO}Abrir resultados seleccionados</button>
    </div>

    <div class="hst-filtros" id="histFiltros">
      <div class="np-campo hst-select">${ICO_CALENDARIO}<select class="np-input" id="histFecha" aria-label="Fechas" onchange="renderHistoryReal(historialDatos)">
        <option value="0">Todas las fechas</option><option value="7">Últimos 7 días</option><option value="30">Últimos 30 días</option></select>${ICO_DESPLEGAR}</div>
      <div class="np-campo hst-select">${ICO_FILTRO}<select class="np-input" id="histTipo" aria-label="Tipo de corrida" onchange="renderHistoryReal(historialDatos)"></select>${ICO_DESPLEGAR}</div>
    </div>

    <!-- Estado vacío -->
    <div class="hst-vacio-bloque hide" id="histVacio">
      <section class="np-tarjeta hst-vacio">
        <span class="hst-vacio-ico">${ICO_HISTORIAL}</span>
        <h2>Aún no hay corridas.</h2>
        <p class="np-texto">Prueba tu primer proyecto. Elige qué funciones revisar y QAgent guardará aquí la evidencia, las pruebas y los tokens de cada corrida.</p>
        <button type="button" class="ini-btn ini-btn-principal" onclick="go('preview')">${ICO_FLECHA}Preparar mi primera prueba</button>
        <p class="np-meta">No ejecutaremos tu código en tu máquina. Se verificará en un entorno aislado.</p>
      </section>
      <div class="hst-ayudas">
        <section class="np-tarjeta"><span class="hst-ayuda-ico">${ICO_DOCUMENTO}</span><h2>Resultados recuperables</h2><p class="np-texto">Vuelve a cualquier resultado sin repetir la corrida.</p></section>
        <section class="np-tarjeta"><span class="hst-ayuda-ico">${ICO_COMPARAR}</span><h2>Comparación con la anterior</h2><p class="np-texto">Ve si mejoraron los bugs, la cobertura y los tokens.</p></section>
        <section class="np-tarjeta"><span class="hst-ayuda-ico">${ICO_PRUEBAS}</span><h2>Tus pruebas guardadas</h2><p class="np-texto">Consulta y descarga las pruebas para seguir trabajando.</p></section>
      </div>
    </div>

    <!-- Con datos -->
    <div class="hst-datos hide" id="histDatos">
      <div class="table-scroll hst-tabla-marco"><table class="hst-tabla">
        <thead><tr><th>Fecha</th><th>Tipo</th><th>Resultado</th><th>Duración</th><th>Pasan</th><th>Tokens</th><th>Resultados</th></tr></thead>
        <tbody id="histTable"></tbody>
      </table></div>
      <p class="np-meta hide" id="histSinFiltro">Ninguna corrida coincide con los filtros.</p>

      <div class="np-rejilla hst-rejilla">
        <section class="hst-comparar" id="histComparar" aria-live="polite"></section>
        <section class="np-tarjeta" id="histPruebas"></section>
      </div>
      <p class="np-meta">Repetir pruebas guardadas: volver a correr las pruebas aprobadas para comprobar que los cambios no rompieron lo que antes funcionaba. No usa IA.</p>
    </div>
  </div></div>
</section>
`);

/* ---------------- Estado de la pantalla ---------------- */
let historialDatos = null;   // última respuesta de obtener_historial() (o la demostración)
let histSel = null;          // run_id de la corrida elegida en la tabla

// Demostración (sin pywebview): mismo formato que construir_historial().
const HISTORIAL_DEMO = {
  demo: true,
  corridas: [
    {run_id:'8841-B', fecha:'2026-09-25T14:32:00', perfil:'deep', perfil_nombre:'Estándar + profundizar', posibles_bugs:1, pasaron:6, total_objetivos:9, total_seleccionados:9, total_procesados:9, total_pendientes:0, tipo_terminacion:'completada', terminacion_nombre:'Completada', es_parcial:false, pruebas_ejecutadas:9, pruebas_aprobadas:6, errores_tecnicos:2, objetivos_omitidos:0, no_procesados_por_detencion:0, duracion_s:154.2, cobertura_lineas:84, total_tokens:142500, tokens_planner:21400, resumen_specs:{reutilizado:4, regenerado:2}, requieren_corrida_nueva:0},
    {run_id:'8791-A', fecha:'2026-09-19T16:40:00', perfil:'reg', perfil_nombre:'Repetir pruebas guardadas', posibles_bugs:0, pasaron:6, total_objetivos:6, total_seleccionados:6, total_procesados:6, total_pendientes:0, tipo_terminacion:'completada', terminacion_nombre:'Completada', es_parcial:false, pruebas_ejecutadas:6, pruebas_aprobadas:6, errores_tecnicos:0, objetivos_omitidos:0, no_procesados_por_detencion:0, duracion_s:62.0, cobertura_lineas:80, total_tokens:0, tokens_planner:0, resumen_specs:{}, requieren_corrida_nueva:0},
    {run_id:'8730-A', fecha:'2026-09-12T10:05:00', perfil:'deep', perfil_nombre:'Estándar + profundizar', posibles_bugs:3, pasaron:5, total_objetivos:9, total_seleccionados:9, total_procesados:9, total_pendientes:0, tipo_terminacion:'completada_con_errores', terminacion_nombre:'Completada con errores', es_parcial:false, pruebas_ejecutadas:9, pruebas_aprobadas:5, errores_tecnicos:1, objetivos_omitidos:0, no_procesados_por_detencion:0, duracion_s:181.5, cobertura_lineas:78, total_tokens:171300, tokens_planner:48000, resumen_specs:{generado:6}, requieren_corrida_nueva:0},
  ],
  resumen_guardadas: {
    planes_almacenados: 2,
    especificaciones_totales: 2,
    archivos_prueba: 4,
    pruebas_aceptadas: 23,
    pruebas_regresion: 4,
    defectos_detectados: 4,
  },
  specs: [
    {archivo:'pricing.spec.json', modulo:'services/pricing.py', ultima_accion:'reutilizado'},
    {archivo:'cart.spec.json', modulo:'services/cart.py', ultima_accion:'regenerado'},
  ],
  pruebas_guardadas: [
    {archivo:'test_pricing.py', pruebas:8}, {archivo:'test_cart.py', pruebas:6},
    {archivo:'test_discounts.py', pruebas:5}, {archivo:'test_inventory.py', pruebas:4},
  ],
};

async function renderHistory(){
  const api = window.pywebview && window.pywebview.api;
  if(api && api.obtener_historial){
    try {
      const datos = await api.obtener_historial(projectPath);
      if(datos && datos.ok){ histSel = null; renderHistoryReal(datos); return; }
    } catch(err) {
      console.error('No se pudo cargar el historial:', err);
    }
  }
  histSel = null;
  renderHistoryReal(HISTORIAL_DEMO);
}

const numero = v => Number(v || 0).toLocaleString('es-PE');
const fechaCorta = f => { const d = new Date(f); return isNaN(d) ? String(f || '—') : d.toLocaleString('es-PE', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'}); };
const duracionCorta = s => {
  if (s === null || s === undefined || !isFinite(Number(s))) return '—';
  const v = Number(s);
  return v < 1 ? Math.round(v * 1000) + ' ms' : v >= 60 ? Math.floor(v / 60) + ' min ' + Math.round(v % 60) + ' s' : Number(v).toFixed(1) + ' s';
};
const conSigno = (v, texto) => (v > 0 ? '+' : v < 0 ? '−' : '') + texto;

function renderHistoryReal(datos){
  historialDatos = datos;
  const nombreProyecto = (datos.proyecto || (typeof projectPath === 'string' ? projectPath.split(/[\\/]/).filter(Boolean).pop() : '') || '').trim();
  if(nombreProyecto) document.querySelectorAll('.repoName').forEach(e => e.textContent = nombreProyecto);
  const proyecto = document.querySelector('#s-history .repoName').textContent || 'tu proyecto';
  const corridas = datos.corridas || [];
  const vacio = !corridas.length;

  $('histVacio').classList.toggle('hide', !vacio);
  $('histDatos').classList.toggle('hide', vacio);
  $('histAbrir').classList.toggle('hide', vacio);
  $('histMiga').textContent = 'Historial de ' + proyecto;
  $('histTitulo').textContent = vacio ? 'Historial de ' + proyecto : 'El trabajo anterior, a mano';
  $('histSub').textContent = vacio ? 'Aquí se conservarán tus resultados y pruebas después de cada corrida.'
    : 'Reabre resultados, compara cambios y recupera pruebas guardadas.';
  // Sin corridas solo queda el filtro de fechas, como en la maqueta.
  $('histTipo').closest('.hst-select').classList.toggle('hide', vacio);
  if(vacio) return;

  // Filtros: fechas y tipo de corrida (los nombres de perfil vienen del backend).
  const tipos = [...new Set(corridas.map(h => h.perfil_nombre || h.perfil || '—'))];
  const tipoActual = $('histTipo').value || 'todos';
  $('histTipo').innerHTML = '<option value="todos">Todos los tipos</option>'
    + tipos.map(t => `<option value="${escHtml(t)}" ${t === tipoActual ? 'selected' : ''}>${escHtml(t)}</option>`).join('');
  const dias = Number($('histFecha').value || 0);
  const desde = dias ? Date.now() - dias * 864e5 : 0;
  const visibles = corridas.filter(h => (!desde || new Date(h.fecha).getTime() >= desde)
    && (tipoActual === 'todos' || (h.perfil_nombre || h.perfil || '—') === tipoActual));
  if(!visibles.some(h => h.run_id === histSel)) histSel = visibles.length ? visibles[0].run_id : null;

  $('histSinFiltro').classList.toggle('hide', visibles.length > 0);
  $('histTable').innerHTML = visibles.map(h => {
    const nomPerfil = h.perfil_nombre || h.perfil || '—';   // el nombre sale del backend (#70)
    const sinIA = h.perfil === 'reg' || h.perfil === 'reg_deep';
    const abrir = datos.demo ? "go('exec')" : `cargarEjecucionReal('${escHtml(h.run_id)}')`;
    const tokens = sinIA ? '— (sin IA)' : numero(h.total_tokens);
    const sel = h.total_seleccionados || h.total_objetivos || 0;
    const proc = h.total_procesados || h.total_objetivos || 0;
    const pend = h.total_pendientes || 0;
    const pasanCelda = h.pasaron === null || h.pasaron === undefined
      ? '—'
      : h.es_parcial && pend > 0
        ? `<div class="hst-pasan" title="${h.pasaron} objetivos pasaron de ${proc} procesados con veredicto (${sel} seleccionados inicialmente, ${pend} no procesados por detención)"><b>${h.pasaron} / ${proc}</b> <span class="np-meta">procesados</span><span class="np-meta hst-pasan-sub">(${pend} pend. de ${sel})</span></div>`
        : `<div class="hst-pasan" title="${h.pasaron} objetivos pasaron de ${proc} procesados con veredicto (${sel} seleccionados)"><b>${h.pasaron} / ${proc}</b> <span class="np-meta">procesados</span></div>`;

    return `<tr class="${h.run_id === histSel ? 'on' : ''}" tabindex="0" aria-selected="${h.run_id === histSel}" onclick="seleccionarCorridaHistorial('${escHtml(h.run_id)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}">
      <td>${escHtml(fechaCorta(h.fecha))}</td>
      <td>${escHtml(nomPerfil)}</td>
      <td>${chipResultadoHistorial(h)}</td>
      <td class="np-mono" title="${h.duracion_s === null || h.duracion_s === undefined ? 'Corrida anterior a la medición de duración' : 'Duración medida de la corrida'}">${duracionCorta(h.duracion_s)}</td>
      <td class="np-mono">${pasanCelda}</td>
      <td class="np-mono" title="${sinIA ? 'Repetir pruebas guardadas no llama a la IA' : 'Analizando: ' + numero(h.tokens_planner) + ' tokens'}">${tokens}</td>
      <td>${datos.demo || tieneResultados(h) ? `<button type="button" class="ini-enlace" onclick="event.stopPropagation();${abrir}">Abrir</button>` : '<span class="np-meta" title="Esta corrida no dejó resultados">—</span>'}</td></tr>`;
  }).join('');

  renderComparacionHistorial(corridas);
  renderPruebasGuardadas(datos);
}

function chipResultadoHistorial(h){
  const repetir = h.requieren_corrida_nueva ? `<span class="np-meta hst-nota">${h.requieren_corrida_nueva} requieren corrida nueva</span>` : '';
  if(h.pasaron === null || h.pasaron === undefined) {
    // issue 139: una corrida que la app no llegó a terminar se ve como tal, no «en curso».
    const sin = h.tipo_terminacion === 'interrumpida' ? 'Interrumpida' : 'Sin resultados';
    return `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}${sin}</span>${repetir}`;
  }

  const term = h.tipo_terminacion || (h.estado === 'fallo_controlado' ? 'detenida_error' : 'completada');
  const termNombre = h.terminacion_nombre || (term === 'completada' ? 'Completada' : term === 'completada_con_errores' ? 'Completada con errores' : term === 'cancelada' ? 'Cancelada' : term === 'limitada_recursos' ? 'Limitada por recursos' : 'Detenida por error');

  let chipTerm = '';
  if(term === 'completada'){
    chipTerm = `<span class="np-chip np-chip-exito">${ICO_OK}${escHtml(termNombre)}</span>`;
  } else if(term === 'completada_con_errores'){
    chipTerm = `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}${escHtml(termNombre)}</span>`;
  } else if(term === 'cancelada' || term === 'limitada_recursos'){
    chipTerm = `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}${escHtml(termNombre)}</span>`;
  } else {
    chipTerm = `<span class="np-chip np-chip-bug">${ICO_ERROR}${escHtml(termNombre)}</span>`;
  }

  let chipBugs = '';
  if(h.posibles_bugs){
    chipBugs = `<span class="np-chip np-chip-bug">${ICO_ERROR}${h.posibles_bugs} ${h.posibles_bugs === 1 ? 'posible bug' : 'posibles bugs'}</span>`;
  }

  const parcial = h.es_parcial && h.total_pendientes ? `<span class="np-meta hst-nota">Parcial (${h.total_procesados || h.total_objetivos} de ${h.total_seleccionados})</span>` : '';

  return `<div class="hst-chips">${chipTerm}${chipBugs}</div>${parcial}${repetir}`;
}

function seleccionarCorridaHistorial(runId){
  histSel = runId;
  renderHistoryReal(historialDatos);
}
function abrirCorridaSeleccionada(){
  if(!histSel) return;
  if(historialDatos && historialDatos.demo) { go('exec'); return; }
  // issue 139: una corrida interrumpida (o sin results.json) no tiene resultados que abrir.
  const fila = ((historialDatos && historialDatos.corridas) || []).find(h => h.run_id === histSel);
  if (fila && !tieneResultados(fila)) {
    toast(fila.tipo_terminacion === 'interrumpida'
      ? 'Esta corrida se interrumpió antes de terminar: no dejó resultados que abrir.'
      : 'Esta corrida no dejó resultados que abrir.', I('alertc', 'var(--aviso-t)', 16));
    return;
  }
  cargarEjecucionReal(histSel);
}
// Si la corrida dejó resultados que se puedan abrir en Resultados.
function tieneResultados(h){ return !(h.pasaron === null || h.pasaron === undefined); }

// La corrida elegida frente a la anterior (la lista viene de la más reciente a la más antigua).
function renderComparacionHistorial(corridas){
  const i = corridas.findIndex(h => h.run_id === histSel);
  const actual = corridas[i], previa = i >= 0 ? corridas[i + 1] : null;
  const caja = $('histComparar');
  if(!actual){ caja.innerHTML = ''; return; }
  if(!previa){
    caja.innerHTML = `<div class="hst-comparar-cab"><h2>Primera corrida del proyecto</h2></div>
      <p class="np-meta">Cuando haya otra corrida, aquí verás si mejoraron los bugs, la cobertura y los tokens.</p>`;
    return;
  }
  const hay = v => v !== null && v !== undefined;
  const dBugs = hay(actual.posibles_bugs) && hay(previa.posibles_bugs) ? actual.posibles_bugs - previa.posibles_bugs : null;
  const dCob = hay(actual.cobertura_lineas) && hay(previa.cobertura_lineas) ? Math.round(actual.cobertura_lineas - previa.cobertura_lineas) : null;
  const dTok = Number(actual.total_tokens || 0) - Number(previa.total_tokens || 0);
  const tasa = h => hay(h.pasaron) && h.total_objetivos ? h.pasaron / h.total_objetivos : null;
  const dTasa = tasa(actual) !== null && tasa(previa) !== null ? tasa(actual) - tasa(previa) : null;
  const tendencia = dBugs ? -Math.sign(dBugs) : dTasa ? Math.sign(dTasa) : 0;
  const [titulo, chip] = tendencia > 0 ? ['Mejoró frente a la anterior', `<span class="np-chip np-chip-exito">${ICO_OK}Tendencia positiva</span>`]
    : tendencia < 0 ? ['Empeoró frente a la anterior', `<span class="np-chip np-chip-bug">${ICO_ERROR}Tendencia negativa</span>`]
    : ['Igual que la anterior', ''];

  const cifra = (etq, valor, sub) => `<div class="exp-cifra"><span class="exp-cifra-etq">${etq}</span><b>${valor}</b><span class="exp-cifra-sub">${sub}</span></div>`;
  const cambios = [];
  if(hay(actual.pasaron) && hay(previa.pasaron)){
    const verbo = actual.pasaron > previa.pasaron ? 'aumentaron' : actual.pasaron < previa.pasaron ? 'bajaron' : 'se mantuvieron';
    cambios.push(`Las funciones y endpoints que pasan ${verbo} de ${previa.pasaron} a ${actual.pasaron}. Se procesaron ${actual.total_procesados || actual.total_objetivos} en esta corrida (de ${actual.total_seleccionados || actual.total_objetivos} seleccionados); la anterior tenía ${previa.total_procesados || previa.total_objetivos}.`);
  }
  const reutilizados = (actual.resumen_specs || {}).reutilizado || 0;
  const avisoParcial = actual.es_parcial
    ? `<div class="hst-aviso-parcial">
        <span class="hst-ayuda-ico">${ICO_AVISO_CLON}</span>
        <div>
          <b>Corrida parcial (${escHtml(actual.terminacion_nombre)})</b>
          <p class="np-meta">Se procesaron ${actual.total_procesados || actual.total_objetivos} de ${actual.total_seleccionados || actual.total_objetivos} objetivos seleccionados (${actual.total_pendientes || 0} no procesados por detención). Los resultados corresponden a los objetivos evaluados.</p>
        </div>
      </div>`
    : '';

  caja.innerHTML = `<div class="hst-comparar-cab"><h2>${titulo}</h2>${chip}</div>
    <p class="np-meta">${escHtml(fechaCorta(actual.fecha))} frente a ${escHtml(fechaCorta(previa.fecha))}</p>
    ${avisoParcial}
    <div class="exp-cifras">
      ${cifra('Posibles bugs', dBugs === null ? '—' : conSigno(dBugs, String(Math.abs(dBugs))), dBugs === null ? 'Sin datos de una de las corridas' : `De ${previa.posibles_bugs} a ${actual.posibles_bugs}`)}
      ${cifra('<span title="Porcentaje de líneas del código que ejecutaron las pruebas">Cobertura ⓘ</span>', dCob === null ? '—' : conSigno(dCob, Math.abs(dCob) + ' pp'), dCob === null ? 'Sin datos de una de las corridas' : `De ${Math.round(previa.cobertura_lineas)} % a ${Math.round(actual.cobertura_lineas)} %`)}
      ${cifra('Tokens', conSigno(dTok, numero(Math.abs(dTok))), `De ${numero(previa.total_tokens)} a ${numero(actual.total_tokens)}`)}
    </div>
    <div class="np-tarjeta hst-cambio">
      <h2>Qué cambió</h2>
      ${cambios.map(c => `<p class="np-texto">${escHtml(c)}</p>`).join('')}
      <p class="np-texto">Objetivos: <b>${actual.total_seleccionados || actual.total_objetivos}</b> seleccionados, <b>${actual.total_procesados || actual.total_objetivos}</b> procesados (${actual.total_pendientes || 0} pendientes). Aprobados: <b>${actual.pasaron || 0}</b>, bugs: <b>${actual.posibles_bugs || 0}</b>, errores técnicos: <b>${actual.errores_tecnicos || 0}</b>.</p>
      ${reutilizados ? `<p class="hst-reutilizado">${reutilizados} ${reutilizados === 1 ? 'plan de prueba reutilizado' : 'planes de prueba reutilizados'} sin cambios desde la última vez.</p>` : ''}
      <p class="np-meta">Cobertura: porcentaje de líneas del código que ejecutaron las pruebas.</p>
    </div>`;
}

function renderPruebasGuardadas(datos){
  const pruebas = datos.pruebas_guardadas || [], specs = datos.specs || [];
  const resumen = datos.resumen_guardadas || {};
  const total = pruebas.reduce((s, p) => s + (Number(p.pruebas) || 0), 0);
  const planesAlmacenados = resumen.planes_almacenados !== undefined ? resumen.planes_almacenados : specs.length;
  const pruebasAceptadas = resumen.pruebas_aceptadas !== undefined ? resumen.pruebas_aceptadas : total;
  const archivosPrueba = resumen.archivos_prueba !== undefined ? resumen.archivos_prueba : pruebas.length;
  const disponiblesRegresion = resumen.pruebas_regresion !== undefined ? resumen.pruebas_regresion : pruebas.length;
  const defectosDetectados = resumen.defectos_detectados !== undefined ? resumen.defectos_detectados : 0;
  const reutilizados = specs.filter(spec => spec.ultima_accion === 'reutilizado').length;

  const descargaPlanes = specs.length
    ? `<button type="button" class="ini-enlace hst-enlace" onclick="descargarSpecsReal(null)">Descargar planes (.zip)</button>`
    : '';

  if(!pruebas.length && !specs.length){
    $('histPruebas').innerHTML = `<h2>Pruebas guardadas</h2>
      <p class="np-texto">Aún no hay pruebas ni planes guardados. Se guardan las que pasan la verificación, para volver a correrlas después.</p>`;
    return;
  }

  $('histPruebas').innerHTML = `<h2>Pruebas guardadas</h2>
    <div class="hst-clasif-grid">
      <div class="hst-clasif-card">
        <span class="hst-clasif-num">${numero(planesAlmacenados)}</span>
        <b class="hst-clasif-tit">Planes de prueba</b>
        <span class="np-meta">Specs en <span class="np-mono">.qagent/specs/</span></span>
      </div>
      <div class="hst-clasif-card">
        <span class="hst-clasif-num">${numero(archivosPrueba)}</span>
        <b class="hst-clasif-tit">Archivos de prueba</b>
        <span class="np-meta">Módulos en <span class="np-mono">.qagent/tests/</span></span>
      </div>
      <div class="hst-clasif-card">
        <span class="hst-clasif-num">${numero(pruebasAceptadas)}</span>
        <b class="hst-clasif-tit">Pruebas aceptadas</b>
        <span class="np-meta">Casos de prueba aprobados</span>
      </div>
      <div class="hst-clasif-card">
        <span class="hst-clasif-num">${numero(disponiblesRegresion)}</span>
        <b class="hst-clasif-tit">Para regresión</b>
        <span class="np-meta">Listas sin costo de IA</span>
      </div>
    </div>
    ${defectosDetectados ? `<p class="hst-defectos-nota">${ICO_ERROR}${numero(defectosDetectados)} ${defectosDetectados === 1 ? 'defecto detectado' : 'defectos detectados'} en el historial (en reportes).</p>` : ''}
    <p class="np-texto">Las aprobadas en las corridas del proyecto disponibles para regresión.</p>
    <ul class="hst-archivos">${pruebas.slice(0, 2).map(p => `<li class="np-mono">${escHtml(p.archivo)} · ${p.pruebas} ${p.pruebas === 1 ? 'prueba' : 'pruebas'}</li>`).join('')}</ul>
    ${pruebas.length > 2 ? `<p class="np-meta">Y otros ${pruebas.length - 2} archivos de pruebas</p>` : ''}
    <div class="hst-acciones-guardadas">
      ${pruebas.length ? `<button type="button" class="ini-btn" onclick="descargarPruebasReal()">${ICO_DESCARGAR}Descargar</button>` : ''}
      ${descargaPlanes}
    </div>`;
}

async function descargarPruebasReal(){
  const api = window.pywebview && window.pywebview.api;
  if(!(api && api.descargar_pruebas_zip)){
    toast('La descarga está disponible en la aplicación de escritorio.');
    return;
  }
  try {
    const r = await api.descargar_pruebas_zip(projectPath);
    if(r && r.cancelado) return;
    if(!r || !r.ok){ toastError(escHtml((r && r.motivo) || 'No se pudo crear el ZIP.')); return; }
    toast(`Se guardó <span class="mono">${escHtml(r.nombre)}</span> en <span class="mono">${escHtml(r.ruta)}</span>`);
  } catch(err) {
    toastError('No se pudieron descargar las pruebas: ' + escHtml(String(err)));
  }
}

async function descargarSpecsReal(modulo){
  const api = window.pywebview && window.pywebview.api;
  if(!(api && api.descargar_specs_zip)){
    toast('La descarga está disponible en la aplicación de escritorio.');
    return;
  }
  try {
    const r = await api.descargar_specs_zip(projectPath, modulo);
    if(r && r.cancelado) return;
    if(!r || !r.ok){ toastError(escHtml((r && r.motivo) || 'No se pudo crear el ZIP.')); return; }
    toast(`Se guardó <span class="mono">${escHtml(r.nombre)}</span> en <span class="mono">${escHtml(r.ruta)}</span>`);
  } catch(err) {
    toastError('No se pudieron descargar los planes: ' + escHtml(String(err)));
  }
}

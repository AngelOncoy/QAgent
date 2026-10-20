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
    {run_id:'8841-B', fecha:'2026-09-25T14:32:00', perfil:'deep', perfil_nombre:'Estándar + profundizar', posibles_bugs:1, pasaron:6, total_objetivos:9, duracion_s:154.2, cobertura_lineas:84, total_tokens:142500, tokens_planner:21400, resumen_specs:{reutilizado:4, regenerado:2}, requieren_corrida_nueva:0},
    {run_id:'8791-A', fecha:'2026-09-19T16:40:00', perfil:'reg', perfil_nombre:'Repetir pruebas guardadas', posibles_bugs:0, pasaron:6, total_objetivos:6, duracion_s:62.0, cobertura_lineas:80, total_tokens:0, tokens_planner:0, resumen_specs:{}, requieren_corrida_nueva:0},
    {run_id:'8730-A', fecha:'2026-09-12T10:05:00', perfil:'deep', perfil_nombre:'Estándar + profundizar', posibles_bugs:3, pasaron:5, total_objetivos:9, duracion_s:181.5, cobertura_lineas:78, total_tokens:171300, tokens_planner:48000, resumen_specs:{generado:6}, requieren_corrida_nueva:0},
  ],
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
    return `<tr class="${h.run_id === histSel ? 'on' : ''}" tabindex="0" aria-selected="${h.run_id === histSel}" onclick="seleccionarCorridaHistorial('${escHtml(h.run_id)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}">
      <td>${escHtml(fechaCorta(h.fecha))}</td>
      <td>${escHtml(nomPerfil)}</td>
      <td>${chipResultadoHistorial(h)}</td>
      <td class="np-mono" title="${h.duracion_s === null || h.duracion_s === undefined ? 'Corrida anterior a la medición de duración' : 'Duración medida de la corrida'}">${duracionCorta(h.duracion_s)}</td>
      <td class="np-mono">${h.pasaron === null || h.pasaron === undefined ? '—' : `${h.pasaron} / ${h.total_objetivos}`}</td>
      <td class="np-mono" title="${sinIA ? 'Repetir pruebas guardadas no llama a la IA' : 'Analizando: ' + numero(h.tokens_planner) + ' tokens'}">${tokens}</td>
      <td><button type="button" class="ini-enlace" onclick="event.stopPropagation();${abrir}">Abrir</button></td></tr>`;
  }).join('');

  renderComparacionHistorial(corridas);
  renderPruebasGuardadas(datos);
}

function chipResultadoHistorial(h){
  const repetir = h.requieren_corrida_nueva ? `<span class="np-meta hst-nota">${h.requieren_corrida_nueva} requieren corrida nueva</span>` : '';
  if(h.pasaron === null || h.pasaron === undefined) return `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}Sin resultados</span>${repetir}`;
  if(h.posibles_bugs) return `<span class="np-chip np-chip-bug">${ICO_ERROR}${h.posibles_bugs} ${h.posibles_bugs === 1 ? 'posible bug' : 'posibles bugs'}</span>${repetir}`;
  if(h.pasaron === h.total_objetivos) return `<span class="np-chip np-chip-exito">${ICO_OK}Pasó</span>${repetir}`;
  return `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}Faltan pruebas</span>${repetir}`;
}

function seleccionarCorridaHistorial(runId){
  histSel = runId;
  renderHistoryReal(historialDatos);
}
function abrirCorridaSeleccionada(){
  if(!histSel) return;
  if(historialDatos && historialDatos.demo) go('exec');
  else cargarEjecucionReal(histSel);
}

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
    cambios.push(`Las funciones y endpoints que pasan ${verbo} de ${previa.pasaron} a ${actual.pasaron}. Se verificaron ${actual.total_objetivos} en esta corrida; la anterior tenía ${previa.total_objetivos}.`);
  }
  const reutilizados = (actual.resumen_specs || {}).reutilizado || 0;
  caja.innerHTML = `<div class="hst-comparar-cab"><h2>${titulo}</h2>${chip}</div>
    <p class="np-meta">${escHtml(fechaCorta(actual.fecha))} frente a ${escHtml(fechaCorta(previa.fecha))}</p>
    <div class="exp-cifras">
      ${cifra('Posibles bugs', dBugs === null ? '—' : conSigno(dBugs, String(Math.abs(dBugs))), dBugs === null ? 'Sin datos de una de las corridas' : `De ${previa.posibles_bugs} a ${actual.posibles_bugs}`)}
      ${cifra('<span title="Porcentaje de líneas del código que ejecutaron las pruebas">Cobertura ⓘ</span>', dCob === null ? '—' : conSigno(dCob, Math.abs(dCob) + ' pp'), dCob === null ? 'Sin datos de una de las corridas' : `De ${Math.round(previa.cobertura_lineas)} % a ${Math.round(actual.cobertura_lineas)} %`)}
      ${cifra('Tokens', conSigno(dTok, numero(Math.abs(dTok))), `De ${numero(previa.total_tokens)} a ${numero(actual.total_tokens)}`)}
    </div>
    <div class="np-tarjeta hst-cambio">
      <h2>Qué cambió</h2>
      ${cambios.map(c => `<p class="np-texto">${escHtml(c)}</p>`).join('')}
      ${reutilizados ? `<p class="hst-reutilizado">${reutilizados} ${reutilizados === 1 ? 'plan de prueba reutilizado' : 'planes de prueba reutilizados'} sin cambios desde la última vez.</p>` : ''}
      <p class="np-meta">Cobertura: porcentaje de líneas del código que ejecutaron las pruebas.</p>
    </div>`;
}

function renderPruebasGuardadas(datos){
  const pruebas = datos.pruebas_guardadas || [], specs = datos.specs || [];
  const total = pruebas.reduce((s, p) => s + (Number(p.pruebas) || 0), 0);
  const reutilizados = specs.filter(spec => spec.ultima_accion === 'reutilizado').length;
  const planes = specs.length ? `<p class="np-meta">${specs.length} ${specs.length === 1 ? 'plan de prueba guardado' : 'planes de prueba guardados'}${reutilizados ? ` · ${reutilizados} reutilizados en la última corrida` : ''}.
      <button type="button" class="ini-enlace hst-enlace" onclick="descargarSpecsReal(null)">Descargar planes (.zip)</button></p>` : '';
  if(!pruebas.length){
    $('histPruebas').innerHTML = `<h2>Pruebas guardadas</h2>
      <p class="np-texto">Aún no hay pruebas guardadas. Se guardan las que pasan la verificación, para volver a correrlas después.</p>${planes}`;
    return;
  }
  $('histPruebas').innerHTML = `<h2>Pruebas guardadas</h2>
    <div class="hst-pruebas-total"><span class="hst-ayuda-ico">${ICO_PRUEBAS}</span><div><b>${numero(total)} ${total === 1 ? 'prueba' : 'pruebas'}</b><span class="np-meta">Python · pytest</span></div></div>
    <p class="np-texto">Las aprobadas en las corridas del proyecto. Incluyen las que revelan posibles bugs.</p>
    <ul class="hst-archivos">${pruebas.slice(0, 2).map(p => `<li class="np-mono">${escHtml(p.archivo)} · ${p.pruebas} ${p.pruebas === 1 ? 'prueba' : 'pruebas'}</li>`).join('')}</ul>
    ${pruebas.length > 2 ? `<p class="np-meta">Y otros ${pruebas.length - 2} archivos de pruebas</p>` : ''}
    <button type="button" class="ini-btn" onclick="descargarPruebasReal()">${ICO_DESCARGAR}Descargar</button>
    ${planes}`;
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

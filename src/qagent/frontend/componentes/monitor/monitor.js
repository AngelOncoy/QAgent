// monitor.js — pantalla «En curso» (progreso en vivo de la corrida)
// HTML del componente (se monta en el marcador data-componente="monitor/monitor" de index.html)
// Etapas (Analizando → Escribiendo pruebas → Verificando), avance, aviso de pruebas que se intentaron
// debilitar, función actual y actividad reciente. En la app las filas llegan de Python (corrida_evento);
// en el navegador se reproduce la demostración (EVENTS). Los íconos ICO_* vienen de inicio/ y ejecucion/.
const ICO_ANALIZAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/></svg>';
const ICO_ESCRIBIR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m8 8-4 4 4 4M16 8l4 4-4 4"/></svg>';
const ICO_DETENER = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
const ICO_ESCUDO_ALERTA = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="M12 8v5M12 16h.01"/></svg>';

registrarComponente('monitor/monitor', `<!-- ===== 4. EN CURSO: PROGRESO EN VIVO ===== -->
<section id="s-monitor" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <header class="ini-barra">
    <nav class="ini-migas" aria-label="Ubicación"><span class="repoName"></span><span aria-hidden="true">/</span><span aria-current="page">Progreso en vivo</span></nav>
    <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
  </header>
  <div class="scroll"><div class="page prg">

    <div class="np-cabecera">
      <div>
        <h1 class="ini-titulo" id="prgTitulo">Preparando la corrida</h1>
        <p class="np-subtitulo" id="prgSub"></p>
      </div>
      <div class="prg-acciones" id="prgAcciones"></div>
    </div>

    <div class="prg-etapas" id="prgEtapas"></div>

    <div class="prg-avance">
      <div class="prg-avance-cab"><span id="prgAvanceTxt">Preparando…</span><span class="prg-pct" id="prgPct"></span></div>
      <div class="np-barra prg-barra"><i id="prgBarra"></i></div>
    </div>

    <div class="np-aviso np-aviso-info hide" id="prgEntorno">${ICO_GIRANDO}<div><b>Instalando las dependencias del proyecto en el entorno aislado</b><span>La primera corrida con este requirements.txt instala sus librerías (por ejemplo torch u opencv) y puede tardar varios minutos según tu conexión. Las siguientes corridas reutilizan lo instalado.</span><span class="prg-entorno-paso" id="prgEntornoPaso"></span></div></div>

    <div class="np-aviso np-aviso-aviso hide" id="prgAlerta">${ICO_AVISO_CLON}<div><b id="prgAlertaTitulo"></b><span id="prgAlertaTxt"></span></div></div>

    <div class="prg-rejilla">
      <div class="np-columna">
        <section class="np-tarjeta" id="prgActual" aria-live="polite"></section>
        <section class="np-tarjeta" aria-labelledby="prgActividadTitulo">
          <h2 id="prgActividadTitulo">Actividad reciente</h2>
          <ol class="prg-actividad" id="timeline"></ol>
          <span class="np-meta"><span id="evCount">0</span> pasos registrados</span>
        </section>
      </div>
      <div class="np-columna">
        <section class="np-tarjeta prg-cifra"><span class="exp-cifra-etq">Tokens de la corrida</span><b id="prgTokens">—</b><span class="np-meta" id="prgTokensSub">Se muestran al terminar la corrida</span></section>
        <section class="np-tarjeta prg-cifra"><span class="exp-cifra-etq">Trabajo conservado</span><b id="prgReuso">0</b><span class="np-meta">Sin cambios desde la última vez. Se reutiliza lo ya verificado.</span></section>
      </div>
    </div>

    <p class="np-meta">El código se ejecuta en un entorno aislado, sin internet ni acceso a tu máquina.</p>
  </div></div>
</section>
`);

// p = funciones terminadas (de 9). Los 12 primeros eventos son los de tu diseño; el resto completa las 9 funciones de la corrida.
const EVENTS = [
  {a:'reuse',    f:'services/pricing.py',   fn:'calculate_discount()', t:'Spec vigente reutilizado (<span class="mono">.qagent/specs/pricing.spec.json</span>): el código no cambió desde la corrida #8730-A. Análisis omitido · 0 tokens del Planner.', p:0},
  {a:'generator',f:'services/pricing.py',   fn:'calculate_discount()', t:'Generando suite pytest con fixtures parametrizadas para validación de topes de descuento.', p:0},
  {a:'reviewer', f:'services/pricing.py',   fn:'calculate_discount()', t:'Sandbox completado exitosamente: 3/3 tests aprobados. Cobertura: 100%. Aserciones legítimas verificadas.', p:1},
  {a:'reuse',    f:'services/inventory.py', fn:'reserve_stock_atomic()', t:'Spec vigente reutilizado (<span class="mono">.qagent/specs/inventory.spec.json</span>): contrato con lock atómico y rollback obligatorio ya definido. 0 tokens del Planner.', p:1},
  {a:'generator',f:'services/inventory.py', fn:'reserve_stock_atomic()', t:'Reintento 2/3: Sintetizando nueva prueba con mock de cliente Redis asíncrono.', p:1},
  {a:'guard',    f:'services/inventory.py', fn:'reserve_stock_atomic()', t:'Aserciones rechazadas: se detectó relajación deliberada (Assertion Laundering: <span class="mono">lock.is_acquired()</span> → <span class="mono">assert res is not None</span>). Reintento programado.', guard:['Filtro Anti-Laundering: Aserción modificada no autorizada','RETRY 2/3 ACTIVADO'], p:1},
  {a:'guard',    f:'services/inventory.py', fn:'reserve_stock_atomic()', t:'Intento 3/3 repite la misma relajación (hash del diff repetido). Se detiene el ciclo: prueba RECHAZADA para revisión humana.', guard:['Filtro Anti-Laundering: relajación repetida','CICLO DETENIDO'], p:2},
  {a:'planner',  f:'services/cart.py',      fn:'calculate_tax_breakdown()', t:'cart.py cambió desde la corrida anterior: analizando árbol de dependencias tributarias y excepciones de estados exentos. Spec regenerado en <span class="mono">.qagent/specs/cart.spec.json</span>.', p:2},
  {a:'generator',f:'services/cart.py',      fn:'calculate_tax_breakdown()', t:'Generando pruebas pytest para reglas fiscales complejas (California 7.25% vs Exentos de impuestos).', p:2},
  {a:'reviewer', f:'services/cart.py',      fn:'calculate_tax_breakdown()', t:'Ejecutado en sandbox aislado: 2/2 tests pasaron en 110ms. Aserciones estrictas comprobadas.', p:3},
  {a:'planner',  f:'services/discounts.py', fn:'compute_loyalty_multiplier()', t:'discounts.py cambió: evaluando reglas de negocio para antigüedad de clientes y límites de fidelidad. Spec regenerado.', p:3},
  {a:'generator',f:'services/discounts.py', fn:'compute_loyalty_multiplier()', t:'Generando test_compute_loyalty_basic con verificación de umbrales.', p:3},
  {a:'watch',    f:'services/discounts.py', fn:'compute_loyalty_multiplier()', t:'Alerta de calidad: Cobertura de línea 98% alcanzada, pero Mutation Score bajo (38%). Sobrevivieron 5 mutantes.', p:4},
  {a:'planner',  f:'services/cart.py',      fn:'apply_bulk_promotion()', t:'Contrato: "descuenta la unidad más barata cada 3 items" → para 6 items de $10 el descuento esperado es 20.0.', p:4},
  {a:'generator',f:'services/cart.py',      fn:'apply_bulk_promotion()', t:'Reintento 2/3: la iteración 1 falló (esperado 20.0, obtenido 10.0); nueva versión con aserción <span class="mono">== 10.0</span>.', p:4},
  {a:'oracle',   f:'services/cart.py',      fn:'apply_bulk_promotion()', t:'Valor esperado 10.0 no es trazable al contrato: el Generator copió el resultado real. Prueba rechazada y ciclo cortado — el fallo apunta a un defecto del código, no de la prueba.', guard:['Filtro de Oráculo: valor esperado sin origen en el contrato','POSIBLE BUG EN CÓDIGO'], p:5},
  {a:'generator',f:'services/payments.py',  fn:'validate_credit_card_token()', t:'Reintento 3/3: la prueba sigue llamando a la pasarela real en 127.0.0.1:8443 (sin mock).', p:5},
  {a:'stuck',    f:'services/payments.py',  fn:'validate_credit_card_token()', t:'Límite de 3/3 intentos alcanzado: el sandbox no tiene red y la prueba no simula la pasarela. Requiere un fixture de mock (intervención humana).', guard:['Control de convergencia: 3/3 intentos sin éxito','ESTANCADO'], p:6},
  {a:'reviewer', f:'services/payments.py',  fn:'refund_charge_idempotent()', t:'Iteración 1 falló por ImportError (causa: importación); iteración 2 aprobada: idempotencia verificada, 19/20 mutantes eliminados.', p:7},
  {a:'reviewer', f:'services/shipping.py',  fn:'estimate_delivery_window()', t:'1/1 test aprobado en 142ms. Cobertura 96%. Función no crítica: mutmut no aplica.', p:8},
  {a:'reviewer', f:'services/inventory.py', fn:'check_low_stock_alerts()', t:'1/1 test aprobado en 135ms. Cobertura 92%. Corrida completa: 9 de 9 funciones procesadas.', p:9},
];
const RUN_TOTAL = 9;

let monitorStarted=false, runDone=false, monTimer=null, agoTimer=null, shown=[], evIdx=0;
// Cada paso también se imprime, con hora, en la consola de Python (solo en la app de escritorio).
function registrarEnPython(evento){
  const api = window.pywebview && window.pywebview.api;
  if(api && api.registrar_evento) api.registrar_evento(evento).catch(() => {});
}

/* ---------------- Estado de la corrida que se muestra ---------------- */
// Etapa de cada tipo de fila: los agentes internos no se nombran en la interfaz.
const ETAPA_DE = {planner:'analizar', reuse:'analizar', generator:'escribir', reviewer:'verificar', guard:'verificar', watch:'verificar', oracle:'verificar', stuck:'verificar'};
const ETAPAS_PRG = [
  {k:'analizar',  t:'Analizando',          ico:() => ICO_ANALIZAR, titulo:'Analizando el proyecto'},
  {k:'escribir',  t:'Escribiendo pruebas', ico:() => ICO_ESCRIBIR, titulo:'Escribiendo las pruebas'},
  {k:'verificar', t:'Verificando',         ico:() => ICO_OK,       titulo:'Verificando las pruebas'},
];
let PRG = null;   // {inicio, etapa, hechos, total, porEtapa:{k:Set}, reuso:Set, actual, fin, alerta}
function reiniciarProgreso(){
  PRG = {inicio: Date.now(), etapa: null, hechos: 0, total: null, porEtapa: {analizar:new Set(), escribir:new Set(), verificar:new Set()},
         reuso: new Set(), actual: null, fin: null, alerta: null, pasos: []};
  $('timeline').innerHTML = ''; $('evCount').textContent = '0';
  $('prgTokens').textContent = '—'; $('prgTokensSub').textContent = 'Se muestran al terminar la corrida';
  $('prgAlerta').classList.add('hide');
}
const horaCorta = t => new Date(t).toLocaleTimeString('es-PE', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
const duracionTexto = s => s === null || s === undefined ? '—' : (s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : s < 1 ? Math.round(s * 1000) + ' ms' : Number(s).toFixed(1) + ' s');
function transcurrido(){
  const s = Math.floor(((PRG.fin ? PRG.fin.t : Date.now()) - PRG.inicio) / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')} transcurridos`;
}

// Registra una fila (real o de la demostración) y vuelve a pintar la pantalla.
function registrarPaso({a, f, fn, t, guard, hechos, total, tipo_objetivo, transcurrido_s, duracion_objetivo_s}){
  // El backend es la fuente de verdad del tiempo; este reloj solo interpola
  // entre eventos. Si llega el tiempo medido, se reancla el inicio local.
  if (typeof transcurrido_s === 'number' && isFinite(transcurrido_s)) {
    PRG.inicio = Date.now() - Math.max(0, transcurrido_s) * 1000;
    PRG.medido = true;
  }
  const etapa = ETAPA_DE[a] || null, clave = [f, fn].filter(Boolean).join('::');
  if (etapa) { PRG.etapa = etapa; if (clave) PRG.porEtapa[etapa].add(clave); }
  if (a === 'reuse' && clave) PRG.reuso.add(clave);
  if (typeof hechos === 'number' && total) { PRG.hechos = hechos; PRG.total = total; }
  if (fn) PRG.actual = {fn, f, tipo: tipo_objetivo, etapa: etapa || PRG.etapa, texto: t, pasos: (PRG.actual && PRG.actual.fn === fn ? PRG.actual.pasos : 0) + 1,
    duracion: typeof duracion_objetivo_s === 'number' ? duracion_objetivo_s : (PRG.actual && PRG.actual.fn === fn ? PRG.actual.duracion : null)};
  // Al preparar el entorno aislado se instalan las dependencias del proyecto (solo la primera vez
  // con ese requirements.txt). El backend no informa avance en ese paso: se explica la espera.
  // El backend informa cada paso de la instalación («Descargando torch (821.0 MB)»): el aviso sigue
  // visible con el último paso hasta que llega la primera etapa de la corrida.
  if (etapa) PRG.preparandoEntorno = false;
  else if (/entorno aislado/i.test(String(t || ''))) PRG.preparandoEntorno = true;
  if (PRG.preparandoEntorno && !etapa) PRG.pasoEntorno = textoPlano(t || '');
  if (a === 'guard') PRG.alerta ={titulo:'Se bloqueó un intento de debilitar una prueba', texto:`En ${fn || 'una función'} la prueba generada relajaba la comprobación. Se mantiene el criterio original: el posible bug no se esconde.`};
  if (a === 'oracle') PRG.alerta = {titulo:'Posible bug detectado', texto:`En ${fn || 'una función'} el resultado no coincide con lo que dice el contrato. Se conserva la prueba para que lo revises.`};
  PRG.pasos.unshift({hora: Date.now(), a, fn, t, guard});
  PRG.pasos = PRG.pasos.slice(0, 8);
  $('evCount').textContent = String(Number($('evCount').textContent) + 1);
  pintarProgreso();
}

/* ---------------- Pintado ---------------- */
function pintarProgreso(){
  if (!PRG) return;
  const etapaActual = ETAPAS_PRG.find(e => e.k === PRG.etapa);
  $('prgTitulo').textContent = PRG.fin ? (
      PRG.fin.cancelada ? 'Corrida cancelada'
      : PRG.fin.conErrores ? 'Corrida completada con errores'
      : PRG.fin.conAvisos ? 'Corrida completada con avisos'
      : PRG.fin.ok ? 'Corrida completada'
      : 'Corrida detenida'
    )
    : PRG.preparandoEntorno ? 'Preparando el entorno aislado'
    : etapaActual ? etapaActual.titulo : 'Preparando la corrida';
  $('prgEntorno').classList.toggle('hide', !(PRG.preparandoEntorno && !PRG.fin));
  $('prgEntornoPaso').textContent = PRG.pasoEntorno && !/^Preparando el entorno aislado/i.test(PRG.pasoEntorno) ? PRG.pasoEntorno : '';
  const proyecto = (document.querySelector('.ini-migas .repoName') || {}).textContent || '';
  $('prgSub').textContent = [proyecto, `Corrida iniciada a las ${new Date(PRG.inicio).toLocaleTimeString('es-PE', {hour:'2-digit', minute:'2-digit'})}`, transcurrido()].filter(Boolean).join(' · ');

  // Etapas: hecha, actual o pendiente; con cuántas funciones o endpoints pasaron por ella.
  const indice = PRG.fin ? ETAPAS_PRG.length : ETAPAS_PRG.findIndex(e => e.k === PRG.etapa);
  $('prgEtapas').innerHTML = ETAPAS_PRG.map((e, i) => {
    const estado = i < indice ? 'hecho' : i === indice ? 'actual' : 'pendiente';
    const n = PRG.porEtapa[e.k].size;
    const det = e.k === 'verificar' && PRG.total ? `${PRG.hechos} de ${PRG.total} completadas`
      : e.k === 'analizar' ? `${n} ${n === 1 ? 'elemento revisado' : 'elementos revisados'}`
      : `${n} ${n === 1 ? 'prueba escrita' : 'pruebas escritas'}`;
    const ico = estado === 'hecho' ? ICO_OK : estado === 'actual' ? ICO_GIRANDO : ICO_CIRCULO;
    return `<div class="prg-etapa prg-etapa-${estado}"><span class="prg-etapa-ico">${ico}</span><div><b>${e.t}</b><span class="np-meta">${det}</span></div></div>`;
  }).join('');

  // Lo omitido (sin resultado esperado verificable o ruta sin resolver) también está resuelto.
  const omitidos = PRG.fin ? (PRG.fin.omitidos || 0) : 0;
  const pct = PRG.total ? Math.min(100, Math.round((PRG.hechos + omitidos) / PRG.total * 100)) : (PRG.fin ? 100 : 0);
  $('prgAvanceTxt').textContent = PRG.total
    ? `${PRG.hechos} de ${PRG.total} funciones y endpoints completados` + (omitidos ? ` · ${omitidos} no se ${omitidos === 1 ? 'probó' : 'probaron'}` : '')
    : (PRG.fin ? 'Corrida terminada' : 'Preparando la corrida…');
  $('prgPct').textContent = PRG.total || PRG.fin ? pct + ' %' : '';
  $('prgBarra').style.width = pct + '%';

  $('prgAlerta').classList.toggle('hide', !PRG.alerta);
  if (PRG.alerta) { $('prgAlertaTitulo').textContent = PRG.alerta.titulo; $('prgAlertaTxt').textContent = PRG.alerta.texto; }

  // Función actual
  const a = PRG.actual;
  $('prgActual').innerHTML = !a ? '<h2>Función actual</h2><p class="np-texto">Esperando el primer paso de la corrida…</p>'
    : `<h2>${PRG.fin ? 'Última función' : 'Función actual'}</h2>
      <div class="prg-actual-cab"><span><span class="prg-actual-nombre">${escHtml(a.fn)}</span>${docstringDeObjetivo(a.f, a.fn) === false ? etiquetaSinDocstring(a.tipo === 'endpoint' ? 'endpoint' : 'funcion') : ''}</span>
        ${PRG.fin ? '' : `<span class="np-chip np-chip-progreso">${ICO_GIRANDO}${(ETAPAS_PRG.find(e => e.k === a.etapa) || {t:'En curso'}).t}</span>`}</div>
      <span class="bnj-ruta">${escHtml(a.f || '')}${a.tipo === 'endpoint' ? ' · Endpoint' : ''}</span>
      <span class="np-meta">${a.pasos} ${a.pasos === 1 ? 'paso registrado' : 'pasos registrados'} en esta función${a.duracion !== null && a.duracion !== undefined ? ` · ${duracionTexto(a.duracion)} medidos` : ''}</span>
      ${a.texto ? `<p class="np-texto">${escHtml(textoPlano(a.texto))}</p>` : ''}`;

  // Actividad reciente (lo más nuevo arriba)
  $('timeline').innerHTML = PRG.pasos.map(p => {
    const alerta = p.a === 'guard' || p.a === 'oracle' || p.a === 'stuck' || p.a === 'fallo';
    const etapa = ETAPAS_PRG.find(e => e.k === ETAPA_DE[p.a]);
    const titulo = p.guard ? textoPlano(p.guard[1]) : etapa ? etapa.t : 'QAgent';
    return `<li class="${alerta ? 'prg-paso-alerta' : ''}"><span class="prg-hora">${horaCorta(p.hora)}</span>
      <span class="prg-paso-ico">${alerta ? ICO_ESCUDO_ALERTA : etapa ? etapa.ico() : ICO_CIRCULO}</span>
      <div><b>${escHtml(titulo)}${p.fn ? ` · <span class="np-mono">${escHtml(p.fn)}</span>` : ''}</b><span class="np-meta">${escHtml(textoPlano(p.t || ''))}</span></div></li>`;
  }).join('');

  $('prgReuso').textContent = PRG.reuso.size;
  pintarAccionesProgreso();
}
// Los textos de la demostración traen etiquetas HTML: se muestran como texto plano (y escapados).
function textoPlano(t){ const d = document.createElement('div'); d.innerHTML = String(t); return d.textContent || ''; }

function pintarAccionesProgreso(){
  if (PRG.fin) {
    $('prgAcciones').innerHTML = PRG.fin.runId || !modoRealUsado
      ? `<button type="button" class="ini-btn ini-btn-principal" onclick="verResultadosDeCorrida()">${ICO_FLECHA}Ver resultados</button>`
      : '';
    return;
  }
  if (modoReal) {
    $('prgAcciones').innerHTML = `<button type="button" class="ini-btn" id="btnDetenerCorrida" onclick="detenerCorridaReal()">${ICO_DETENER}Detener corrida</button>`;
    return;
  }
  $('prgAcciones').innerHTML = `<button type="button" class="ini-btn ini-btn-principal" onclick="togglePause();pintarAccionesProgreso()">${paused ? ICO_INICIAR + 'Reanudar corrida' : ICO_PAUSA_PREP + 'Pausar corrida'}</button>`;
}
let modoRealUsado = false;
function verResultadosDeCorrida(){
  if (typeof desbloquearVista === 'function') { desbloquearVista('exec'); desbloquearVista('history'); }
  if (PRG && PRG.fin && PRG.fin.runId && typeof cargarEjecucionReal === 'function') cargarEjecucionReal(PRG.fin.runId);
  else go('exec');
}
function iniciarRelojProgreso(){
  clearInterval(agoTimer);
  agoTimer = setInterval(() => { if (PRG && !PRG.fin) $('prgSub').textContent = $('prgSub').textContent.replace(/\d{2}:\d{2} transcurridos$/, transcurrido()); }, 1000);
}

/* ---------------- Demostración (sin pywebview) ---------------- */
function pushEvent(){
  if(evIdx>=EVENTS.length){ finishRun(); return; }
  const e = EVENTS[evIdx]; evIdx++;
  registrarEnPython({tipo:e.a, archivo:e.f, funcion:e.fn, progreso:`${e.p}/${RUN_TOTAL}`, mensaje: textoPlano(e.t) + (e.guard ? ` [${e.guard[0]}: ${e.guard[1]}]` : '')});
  registrarPaso({a:e.a, f:e.f, fn:e.fn, t:e.t, guard:e.guard, hechos:e.p, total:RUN_TOTAL});
  if(evIdx>=EVENTS.length) finishRun();
}
async function startMonitor(){
  if (!entornoListo) { toast(escHtml(entornoMotivo)); return; }
  if (window.pywebview && window.pywebview.api) {
    // Python verifica Docker (HU-13) y el entorno completo (EN-06) antes de iniciar.
    const r = await window.pywebview.api.start_run(projectPath, profile, obtenerSeleccionObjetivos());
    if (r && r.status === 'docker_no_disponible') {
      toastError(escHtml(r.mensaje));
      actualizarSandbox();
      verificarEntorno();
      return;
    }
    if (r && r.status === 'blocked') { await verificarEntorno(); toastError(escHtml(r.motivo)); return; }
    if (r && r.status === 'seleccion_invalida') { toastError(escHtml(r.mensaje)); return; }
    if (r && r.status === 'en_curso') { toast(escHtml(r.mensaje)); return; }
    // Docker listo: la corrida real corre en Python y las filas llegan por corrida_evento.
    if (r && r.modo === 'real') { iniciarMonitorReal(); return; }
  }
  if (typeof desbloquearVista === 'function') desbloquearVista('monitor');
  ejecucionReal = null; reporteReal = null;   // la demostración usa sus propios datos de ejemplo
  monitorStarted = true; runDone = false; evIdx = 0; shown = []; modoRealUsado = false; paused = false;
  document.querySelectorAll('#views a[data-v=exec]').forEach(a=>a.classList.add('hide','off'));
  reiniciarProgreso();
  if (!window.pywebview) {
    $('barraDemo').classList.remove('hide');
    $('skipBtn').classList.remove('hide');
  }
  go('monitor');
  pintarProgreso(); iniciarRelojProgreso();
  pushEvent(); clearInterval(monTimer); monTimer = setInterval(pushEvent, 900);
}
function finishRun(){
  if(runDone) return; runDone = true; clearInterval(monTimer); clearInterval(agoTimer);
  ejecucionReal = null; reporteReal = null;
  registrarEnPython({tipo:'fin', agente:'Corrida #' + RUN_ID, mensaje:`completada: ${RUN_TOTAL} funciones procesadas`});
  $('skipBtn').classList.add('hide');
  if (typeof desbloquearVista === 'function') { desbloquearVista('exec'); desbloquearVista('history'); }
  PRG.fin = {ok: true, t: Date.now(), runId: null};
  if (typeof metrics === 'function') { const m = metrics(); $('prgTokens').textContent = Number(m.tokens).toLocaleString('es-PE'); $('prgTokensSub').textContent = 'Datos de la demostración'; }
  pintarProgreso();
}
function skipRun(){
  registrarEnPython({tipo:'control', agente:'Monitor', mensaje:'Completar la corrida de golpe'});
  while(!runDone) pushEvent();
}

/* ---------------- Corrida real (pipeline de Python) ---------------- */
// Con la app de escritorio y Docker listo, las filas llegan de Python (evento corrida_evento)
// en lugar de EVENTS. Todo texto que viene del proyecto o de la IA se escapa con escHtml.
let modoReal = false;
function iniciarMonitorReal(){
  if (typeof desbloquearVista === 'function') desbloquearVista('monitor');
  ejecucionReal = null; reporteReal = null; modoReal = true; modoRealUsado = true; monitorStarted = true; runDone = false; shown = [];
  clearInterval(monTimer);
  document.querySelectorAll('#views a[data-v=exec]').forEach(a=>a.classList.add('hide','off'));
  $('skipBtn').classList.add('hide');
  reiniciarProgreso();
  go('monitor');
  pintarProgreso(); iniciarRelojProgreso();
}
async function detenerCorridaReal(){
  const btn = $('btnDetenerCorrida');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Deteniendo corrida…';
  }
  if (window.pywebview && window.pywebview.api && window.pywebview.api.detener_corrida) {
    try {
      const res = await window.pywebview.api.detener_corrida();
      if (typeof toast === 'function') toast(res.mensaje || 'Deteniendo corrida de forma controlada…');
    } catch (err) {
      console.error('Error al detener la corrida:', err);
    }
  }
}

function monitorEventoReal(d){
  if(!modoReal || runDone || !d) return;
  if(d.tokens_acumulados !== undefined && d.tokens_acumulados !== null && $('prgTokens')){
    const tok = Number(d.tokens_acumulados);
    if(Number.isFinite(tok)) $('prgTokens').textContent = tok.toLocaleString('es-PE');
    const reales = Number(d.tokens_reales || 0);
    const estimados = Number(d.tokens_estimados || 0);
    if(Number.isFinite(estimados) && estimados > 0){
      $('prgTokensSub').textContent = `${reales.toLocaleString('es-PE')} reales · ${estimados.toLocaleString('es-PE')} estimados`;
    } else if(d.limite_tokens){
      const lim = Number(d.limite_tokens);
      if(Number.isFinite(lim)) $('prgTokensSub').textContent = `de ${lim.toLocaleString('es-PE')} configurados`;
    } else {
      $('prgTokensSub').textContent = 'Tokens acumulados';
    }
  }
  if(d.alerta_presupuesto && PRG){
    PRG.alerta = {titulo:'Presupuesto de tokens', texto: d.t || 'Se ha alcanzado un umbral alto de consumo de tokens.'};
    if($('prgAlerta')) $('prgAlerta').classList.remove('hide');
  }
  registrarPaso({a:d.a, f:d.f, fn:d.identificador || d.fn, t:d.t || '', guard:d.guard, hechos:d.total ? Number(d.hechos) : undefined, total:Number(d.total) || null, tipo_objetivo:d.tipo_objetivo,
    transcurrido_s: typeof d.transcurrido_s === 'number' ? d.transcurrido_s : undefined,
    duracion_objetivo_s: typeof d.duracion_objetivo_s === 'number' ? d.duracion_objetivo_s : undefined});
}
function monitorFinReal(r){
  if(!modoReal || !r) return;
  runDone = true; modoReal = false; clearInterval(agoTimer);
  const ok = r.estado === 'fin';
  const cancelada = Boolean(r.cancelada || (!ok && /cancelad/i.test(r.motivo || '')));
  const conErrores = Boolean(ok && (Number(r.sin_veredicto || 0) > 0 || (r.motivo && /error/i.test(r.motivo))));
  const duracion = typeof r.duracion_s === 'number' && isFinite(r.duracion_s) && r.duracion_s >= 0 ? r.duracion_s : null;
  if (duracion !== null) PRG.inicio = Date.now() - duracion * 1000;
  const omitidos = Number(r.objetivos_omitidos || 0);
  PRG.fin = {ok, cancelada, conErrores, conAvisos: ok && omitidos > 0, omitidos, t: Date.now(), runId: r.run_id && r.carpeta ? r.run_id : null, duracion};
  // El total y lo procesado salen del resumen final, no de los eventos en vivo.
  if (Number(r.total_seleccionados) > 0) PRG.total = Number(r.total_seleccionados);
  if (Number.isFinite(Number(r.total_procesados))) PRG.hechos = Number(r.total_procesados);
  // Resumen final: aprobadas, posibles bugs y tokens (sin costos).
  $('prgTokens').textContent = Number(r.tokens || 0).toLocaleString('es-PE');
  const sinVeredictoTxt = Number(r.sin_veredicto || 0) > 0 ? ` · ${Number(r.sin_veredicto)} sin veredicto` : '';
  const omitidosTxt = omitidos ? ` · ${omitidos} sin probar` : '';
  $('prgTokensSub').textContent = `${Number(r.aceptadas)} ${Number(r.aceptadas) === 1 ? 'aprobada' : 'aprobadas'} · ${Number(r.bugs_detectados)} ${Number(r.bugs_detectados) === 1 ? 'posible bug' : 'posibles bugs'} · ${Number(r.estancadas)} sin prueba${sinVeredictoTxt}${omitidosTxt}`;
  if (r.motivo) {
    const titulo = cancelada ? 'Corrida cancelada por el usuario'
      : conErrores ? 'Corrida completada con errores'
      : ok ? 'Corrida completada con avisos'
      : 'La corrida se detuvo';
    PRG.alerta = {titulo, texto: r.motivo};
  } else if (omitidos) {
    PRG.alerta = {titulo: `${omitidos} ${omitidos === 1 ? 'objetivo no se probó' : 'objetivos no se probaron'}`,
      texto: 'No tienen un resultado esperado verificable en su especificación o su ruta no se pudo resolver. Revísalos en Resultados, en «No se probaron».'};
  }
  if(PRG.fin.runId){   // HU-18: Resultados lee el results.json de esta corrida
    if (typeof desbloquearVista === 'function') { desbloquearVista('exec'); desbloquearVista('history'); }
    if (typeof cargarEjecucionReal === 'function') cargarEjecucionReal(r.run_id, false);
    if (typeof cargarReporteReal === 'function') cargarReporteReal(r.run_id, false);
  }
  pintarProgreso();
}

// Pausa de la demostración (antes en la barra de corrida). La de una corrida real llega con HU-10.
let paused = false;
function togglePause(){
  if (modoReal && !runDone) { toast('Por ahora no se puede pausar una corrida real (HU-10).'); return; }
  if(runDone) return;
  paused = !paused;
  registrarEnPython({tipo:'control', agente:'Monitor', mensaje: paused ? 'Corrida pausada' : 'Corrida reanudada'});
  clearInterval(monTimer); if(!paused) monTimer = setInterval(pushEvent, 900);
}

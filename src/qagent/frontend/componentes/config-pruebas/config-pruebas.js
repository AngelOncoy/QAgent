// config-pruebas.js — pantalla «Preparar»: qué hacer, tipos de prueba, críticas y comprobaciones previas
// HTML del componente (se monta en el marcador data-componente="config-pruebas/config-pruebas" de index.html)
// Tres formas de correr (#69 y #70): generar pruebas nuevas, volver a correr las guardadas o analizar a fondo
// las críticas. Esta última activa la columna Profundizar de Explorar. Los íconos (ICO_*) vienen de
// inicio/modal-abrir.js, que se carga antes.
const ICO_INICIAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M7 5v14l11-7z"/></svg>';
const ICO_AJUSTES = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>';
const ICO_CANDADO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
const ICO_PAUSA_PREP = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/></svg>';

registrarComponente('config-pruebas/config-pruebas', `<!-- ===== 3. PREPARAR ===== -->
<section id="s-tests" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <header class="ini-barra">
    <nav class="ini-migas" aria-label="Ubicación"><span class="repoName"></span><span aria-hidden="true">/</span><span aria-current="page">Preparar prueba</span></nav>
    <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
  </header>
  <div class="scroll"><div class="page prep">

    <div class="np-cabecera">
      <div>
        <h1 class="ini-titulo" id="prepTitulo">Prepara una corrida fiable</h1>
        <p class="np-subtitulo" id="prepSub"></p>
      </div>
      <button type="button" class="ini-btn ini-btn-principal" id="toPlan" onclick="accionPrincipalPreparar()"><span id="toPlanIco">${ICO_INICIAR}</span><span id="toPlanTxt">Iniciar prueba</span></button>
    </div>

    <div class="np-aviso np-aviso-aviso hide" id="prepBloqueo">${ICO_AVISO_CLON}<div><b>Todavía no podemos iniciar la prueba</b><span id="prepBloqueoTxt"></span></div></div>

    <div class="prep-rejilla">
      <div class="np-columna">
        <section class="np-tarjeta prep-modo-tarjeta" aria-labelledby="prepModoTitulo">
          <h2 id="prepModoTitulo">¿Qué quieres hacer?</h2>
          <div class="prep-modos" id="cfgModo" role="radiogroup" aria-labelledby="prepModoTitulo"></div>
        </section>

        <div class="prep-fila">
          <section class="np-tarjeta" aria-labelledby="prepTiposTitulo">
            <h2 id="prepTiposTitulo">Tipos de prueba</h2>
            <div class="prep-lista" id="prepTipos"></div>
          </section>
          <section class="np-tarjeta" aria-labelledby="prepCritTitulo">
            <h2 id="prepCritTitulo">Funciones críticas</h2>
            <div class="prep-lista" id="prepCriticas"></div>
          </section>
        </div>

        <div class="np-aviso np-aviso-info">${ICO_INFO}<div><b>Fortaleza de las pruebas</b><span>Mide si las pruebas detectan errores introducidos a propósito. Solo se mide en las funciones que marques como críticas.</span></div></div>
      </div>

      <div class="np-columna">
        <section class="np-tarjeta" id="prepComprobaciones" aria-live="polite"></section>
        <section class="np-tarjeta" id="prepLimites"></section>
        <p class="np-meta">Si una prueba revela un posible bug, conservaremos el criterio original. No la debilitamos para hacerla pasar.</p>
      </div>
    </div>

  </div></div>
</section>
`);

// #69: la elección de la pantalla se traduce al perfil que recibe start_run (std, deep o reg, #70).
// Sin críticas marcadas no hay nada que analizar a fondo: se corre como Estándar.
function perfilDeEleccion({modo}, prioritarias){
  if (modo === 'repetir') return 'reg';
  if (modo === 'fondo') return prioritarias > 0 ? 'deep' : 'std';
  return 'std';
}

// Objetivos que entran en la corrida: lo incluido en Explorar, según los tipos de prueba elegidos.
function estFor(k){
  const p = PROFILES.find(x=>x.k===k);
  const mods = MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m));
  const fns = eleccionPruebas.unitarias === false ? [] : mods.flatMap(m=>m.fns).filter(f=>f.inc);
  const endpoints = eleccionPruebas.endpoints === false ? [] : mods.flatMap(m=>(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc));
  const objetivos = mods.flatMap(m=>[
    ...(eleccionPruebas.unitarias === false ? [] : m.fns.filter(f=>f.inc)),
    ...(eleccionPruebas.endpoints === false ? [] : (m.endpoints || []).filter(e=>endpointElegible(e) && e.inc))
  ].map(objetivo=>({...objetivo, reuse: SPEC_STATUS[m.path]==='reuse'})));
  const reused = k==='reg' ? 0 : objetivos.filter(objetivo=>objetivo.reuse).length;
  const total = objetivos.length;
  const et = {P: (total - reused) * p.tok * EST_SPLIT.P, G: total * p.tok * EST_SPLIT.G, R: total * p.tok * EST_SPLIT.R};
  const tok = Math.round(et.P + et.G + et.R);
  return {p, fns, endpoints, total, reused, tok, time: Math.max(1, Math.round(total * p.t))};
}

// #74: «4 funciones y 2 endpoints críticos» según lo marcado en Profundizar.
function textoPrioritarias(fns, eps){
  if (!eps) return `${fns} ${fns===1 ? 'función crítica' : 'funciones críticas'}`;
  const ep = `${eps} ${eps===1 ? 'endpoint' : 'endpoints'}`;
  if (!fns) return `${ep} ${eps===1 ? 'crítico' : 'críticos'}`;
  return `${fns} ${fns===1 ? 'función' : 'funciones'} y ${ep} críticos`;
}
function elegirPruebas(cambio){
  eleccionPruebas = {...eleccionPruebas, ...cambio};
  calc();
  if (typeof desbloquearVista === 'function') desbloquearVista('monitor');
}
// Uso de IA estimado de la corrida completa, en palabras
function usoIA(tok){
  if (!tok) return 'sin IA';
  return tok < 50000 ? 'bajo' : tok < 200000 ? 'medio' : 'alto';
}

/* ---------- ¿Qué quieres hacer? ---------- */
const MODOS_PREPARAR = [
  {k:'nuevas',  t:'Generar pruebas nuevas',     d:'Crear casos para lo que cambió y reutilizar lo que sigue igual.'},
  {k:'repetir', t:'Volver a correr las guardadas', d:'Regresión: comprueba que los cambios no rompieron lo que antes funcionaba. No usa IA.',
    tip:'Regresión: volver a correr las pruebas guardadas para comprobar que los cambios no rompieron lo que antes funcionaba.'},
  {k:'fondo',   t:'Análisis a fondo de críticas', d:'Busca casos límite y mide la fortaleza de las pruebas. Tarda más.'},
];
function renderModosPreparar(){
  const {modo} = eleccionPruebas;
  $('cfgModo').innerHTML = MODOS_PREPARAR.map(o => {
    const bloqueado = o.k === 'repetir' && !HAS_PRIOR_RUN;
    return `<button type="button" role="radio" class="prep-modo ${modo===o.k?'on':''}" aria-checked="${modo===o.k}"
      ${bloqueado ? 'disabled title="Requiere una corrida previa de este proyecto"' : (o.tip ? `title="${o.tip}"` : '')} onclick="elegirPruebas({modo:'${o.k}'})">
      <span class="prep-radio" aria-hidden="true"></span>
      <span><b>${o.t}</b><span class="prep-desc">${bloqueado ? 'Disponible después de la primera corrida de este proyecto.' : o.d}</span></span>
    </button>`;
  }).join('');
}

/* ---------- Tipos de prueba y funciones críticas ---------- */
function renderTiposPrueba(){
  const mods = MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m));
  const nFns = mods.flatMap(m=>m.fns).filter(f=>f.inc).length;
  const nEps = mods.flatMap(m=>(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc)).length;
  const fila = (clave, titulo, n, singular, plural) => `<label class="prep-casilla ${n ? '' : 'dis'}">
      <input type="checkbox" class="exp-caja" ${eleccionPruebas[clave] === true && n ? 'checked' : ''} ${n ? '' : 'disabled'} onchange="elegirPruebas({${clave}:this.checked})">
      <span><b>${titulo}</b><span class="prep-desc">${n} ${n === 1 ? singular : plural}</span></span>
    </label>`;
  $('prepTipos').innerHTML = fila('unitarias', 'Unitarias', nFns, 'función seleccionada', 'funciones seleccionadas')
    + fila('endpoints', 'Endpoints API', nEps, 'endpoint seleccionado', 'endpoints seleccionados');
}
// Críticas: funciones y endpoints incluidos y marcados en Profundizar. Se muestran tres; el resto
// se ve y se edita en la columna Profundizar de Explorar (visible con «Análisis a fondo»).
function renderCriticas(){
  const criticas = [];
  MODULES.forEach((m, mi) => {
    if(!m.sel || m.error || !moduloTieneObjetivos(m)) return;
    (m.fns || []).forEach((f, fi) => { if(f.inc && f.crit) criticas.push({n:f.n, fn:`toggle(${mi},${fi},'crit')`}); });
    (m.endpoints || []).forEach((e, ei) => { if(endpointElegible(e) && e.inc && e.crit) criticas.push({n:e.objetivo, fn:`toggleEndpointCrit(${mi},${ei})`}); });
  });
  $('prepCritTitulo').textContent = `Funciones críticas · ${criticas.length}`;
  const visibles = criticas.slice(0, 3), resto = criticas.length - visibles.length;
  const enlace = resto > 0 ? `Ver y editar las otras ${resto} ${resto === 1 ? 'crítica' : 'críticas'}` : (criticas.length ? 'Editar en Explorar' : 'Marcar críticas en Explorar');
  $('prepCriticas').innerHTML = (visibles.map(c => `<label class="prep-casilla">
      <input type="checkbox" class="exp-caja" checked aria-label="Crítica: ${escHtml(c.n)}" onchange="${c.fn}"><span class="np-mono">${escHtml(c.n)}</span>
    </label>`).join('') || '<p class="prep-desc">Todavía no hay funciones críticas marcadas.</p>')
    + (eleccionPruebas.modo !== 'fondo' && criticas.length ? '<p class="prep-desc">Se analizan a fondo al elegir «Análisis a fondo de críticas».</p>' : '')
    + `<button type="button" class="ini-enlace prep-enlace" onclick="irACriticas()">${enlace}</button>`;
}
// Para marcar o revisar críticas hace falta la columna Profundizar de Explorar.
function irACriticas(){
  if (eleccionPruebas.modo !== 'fondo') elegirPruebas({modo:'fondo'});
  go('preview');
}

/* ---------- Comprobaciones previas ----------
   Salen de la verificación real del entorno (EN-06: configuración, claves, Docker y Git) y de la
   selección. Sin pywebview es una demostración: todo se muestra como listo. */
// Lo incluido en Explorar, sin aplicar los tipos de prueba (lo usan el pie de Explorar y las comprobaciones).
function seleccionExplorar(){
  const mods = MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m));
  return {
    fns: mods.flatMap(m=>m.fns).filter(f=>f.inc),
    endpoints: mods.flatMap(m=>(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc)),
  };
}
const algunTipoElegido = () => eleccionPruebas.unitarias === true || eleccionPruebas.endpoints === true;

function comprobacionesPrevias(total, reused){
  const lista = [];
  const r = typeof ENTORNO_VERIFICADO !== 'undefined' ? ENTORNO_VERIFICADO : null;
  const demo = !(window.pywebview && window.pywebview.api);
  const porId = id => r && (r.comprobaciones || []).find(c => c.id === id);
  if (demo) {
    lista.push({ok:true, t:'IA conectada', d:'Modo demostración'});
    lista.push({ok:true, t:'Motor activo', d:'Entorno aislado · sin internet'});
  } else if (!r) {
    lista.push({ok:null, t:'Verificando el entorno…', d:'IA, motor y configuración'});
  } else {
    const ia = porId('claves'), motor = porId('docker'), conf = porId('config'), git = porId('git');
    if (ia) lista.push(ia.ok ? {ok:true, t:'IA conectada', d: r.simulado ? 'IA simulada · sin consumo de tokens' : 'Proveedor configurado'}
                             : {ok:false, t:'Conecta tu proveedor de IA', d:ia.mensaje, a:'Configurar IA'});
    if (motor) lista.push(motor.ok ? {ok:true, t:'Motor activo', d:'Entorno aislado · sin internet'}
                         : motor.opcional ? {ok:true, t:'Motor opcional', d:'No se usa con la IA simulada'}
                         : {ok:false, pausa:true, t:'Inicia el motor', d:motor.mensaje, a:'Ir al motor'});
    if (conf && !conf.ok) lista.push({ok:false, t:'Revisa la configuración', d:conf.mensaje, a:'Abrir Configuración'});
    if (git && !git.ok) lista.push({ok:false, t:'Git no disponible', d:git.mensaje, a:'Abrir Configuración'});
  }
  const exp = seleccionExplorar(), enExplorar = exp.fns.length + exp.endpoints.length;
  if (!enExplorar) lista.push({ok:false, t:'Elige qué probar', d:'No hay funciones ni endpoints seleccionados.', a:'Ir a Explorar', explorar:true});
  else if (!algunTipoElegido()) lista.push({ok:false, t:'Elige un tipo de prueba', d:'Marca Unitarias, Endpoints API o ambas.', tipos:true});
  else if (!total) lista.push({ok:false, t:'Elige qué probar', d:'El tipo de prueba elegido no tiene nada seleccionado.', a:'Ir a Explorar', explorar:true});
  else lista.push({ok:true, t:'Selección válida', d:`${total} ${total === 1 ? 'función o endpoint' : 'funciones y endpoints'}`});
  if (reused) lista.push({ok:true, t:'Trabajo reutilizable', d:`${reused} sin cambios desde la última vez`});
  return lista;
}
function renderComprobaciones(lista){
  const pendientes = lista.filter(c => c.ok === false).length;
  const ico = c => c.ok === null ? ICO_GIRANDO : c.ok ? ICO_OK : c.pausa ? ICO_PAUSA_PREP : ICO_ERROR;
  const clase = c => c.ok === null ? 'progreso' : c.ok ? 'exito' : c.pausa ? 'aviso' : 'bug';
  $('prepComprobaciones').innerHTML = `<h2>${pendientes ? 'Comprobaciones previas' : 'Todo listo para empezar'}</h2>
    ${pendientes ? `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}${pendientes} ${pendientes === 1 ? 'pendiente' : 'pendientes'} de resolver</span>`
                 : `<span class="np-chip np-chip-exito">${ICO_OK}Comprobaciones completas</span>`}
    <ul class="prep-checks">${lista.map(c => `<li class="prep-check-${clase(c)}">
      <span class="prep-check-ico">${ico(c)}</span>
      <div><b>${escHtml(c.t)}</b><span class="prep-desc">${escHtml(c.d || '')}</span>
        ${c.a ? `<button type="button" class="ini-enlace prep-enlace" onclick="${c.explorar ? "go('preview')" : "go('config')"}">${c.a}</button>` : ''}</div>
    </li>`).join('')}</ul>`;
  return pendientes;
}

/* ---------- Límites de la corrida / Inicio no disponible ---------- */
// Intentos y tiempo máximo vigentes (los carga Configuración con obtener_limites).
function textoLimites(){
  const lim = typeof LIMITES !== 'undefined' ? LIMITES : {max_intentos: 3, timeout_s: 120};
  const n = lim.max_intentos;
  const tok = lim.max_tokens_por_corrida ? ` · presupuesto máx. ${Number(lim.max_tokens_por_corrida).toLocaleString('es-PE')} tokens` : '';
  return `Hasta ${n} ${n === 1 ? 'intento' : 'intentos'} por función · tiempo máximo ${lim.timeout_s} s por prueba${tok}`;
}
function renderDetallesCorrida(e, bloqueado, prioritarias, epsPrioritarios = 0){
  const {p, reused, tok} = e;
  if (bloqueado) {
    $('prepLimites').innerHTML = `<h2>Inicio no disponible</h2>
      <button type="button" class="ini-btn" disabled>${ICO_CANDADO}Iniciar prueba</button>
      <p class="np-meta">Se habilitará cuando todo esté listo. No perderás tus opciones.</p>`;
    return;
  }
  const filas = [
    textoLimites(),
    `Uso de IA estimado: <b>${usoIA(tok)}</b>${tok ? ` · ~${tok.toLocaleString('es-PE')} tokens` : ''}`,
    `Duración aproximada: <b>${p.duracion}</b> · ~${e.time} min`,
    reused ? `${reused} sin cambios: se reutiliza el trabajo anterior.` : '',
    profile==='deep' ? `Análisis a fondo en ${textoPrioritarias(prioritarias - epsPrioritarios, epsPrioritarios)}: comprueba con mutación si las pruebas detectan errores. No usa tokens, pero tarda más.` : '',
    profile==='reg' ? 'Solo se vuelven a correr pruebas guardadas: no se usa IA.' : 'Los tokens se mostrarán en vivo y por función.',
  ];
  $('prepLimites').innerHTML = `<h2>Límites de esta corrida</h2>
    <div class="prep-limites" id="cfgDetalles">${filas.filter(Boolean).map(f => `<p>${f}</p>`).join('')}</div>
    <button type="button" class="ini-enlace prep-enlace" onclick="go('config')">Ajustar en Configuración</button>`;
}

// Botón principal: inicia la corrida si todo está listo; si no, lleva a resolver lo pendiente.
let destinoBloqueo = null;
const NUMEROS = ['', 'una', 'dos', 'tres', 'cuatro', 'cinco', 'seis'];
function accionPrincipalPreparar(){
  if (destinoBloqueo === 'tipos') {
    const primera = document.querySelector('#prepTipos input:not(:disabled)');
    if (primera) { primera.scrollIntoView({block:'center', behavior:'smooth'}); primera.focus(); }
    return;
  }
  if (destinoBloqueo) { go(destinoBloqueo); return; }
  startMonitor();
}

function calc(){
  if (eleccionPruebas.modo === 'repetir' && !HAS_PRIOR_RUN) eleccionPruebas.modo = 'nuevas';
  // La columna Profundizar de Explorar solo se ve con «Análisis a fondo de críticas».
  if (typeof mostrarProfundizar === 'function') mostrarProfundizar(eleccionPruebas.modo === 'fondo');
  // #74: los endpoints marcados también cuentan como críticos.
  const estStd = estFor('std');
  const epsPrioritarios = estStd.endpoints.filter(e=>e.crit).length;
  const prioritarias = estStd.fns.filter(f=>f.crit).length + epsPrioritarios;
  profile = perfilDeEleccion(eleccionPruebas, prioritarias);
  const e = estFor(profile), {fns, endpoints, total, tok, reused} = e;
  runEstimate = {tok};
  const exp = seleccionExplorar();   // el pie de Explorar cuenta su selección, sin los tipos de Preparar
  renderPieVistaPrevia(exp.fns, exp.fns.filter(f=>!f.doc).length, exp.endpoints);

  renderModosPreparar();
  renderTiposPrueba();
  renderCriticas();
  const lista = comprobacionesPrevias(total, reused);
  const pendientes = renderComprobaciones(lista);
  const verificando = lista.some(c => c.ok === null);
  const bloqueado = !verificando && (!entornoListo || !total || pendientes > 0);

  // Cabecera: título, resumen y botón principal según el estado.
  const resumen = `${total} ${total === 1 ? 'seleccionada' : 'seleccionadas'} · ${fns.length} ${fns.length === 1 ? 'función' : 'funciones'} y ${endpoints.length} ${endpoints.length === 1 ? 'endpoint' : 'endpoints'} · Python`;
  $('prepSub').textContent = bloqueado ? 'Tu selección está guardada. Resuelve estos puntos antes de empezar.' : resumen;
  $('prepTitulo').textContent = verificando ? 'Comprobando tu entorno…'
    : !bloqueado ? 'Prepara una corrida fiable'
    : pendientes <= 1 ? 'Falta una comprobación' : `Faltan ${NUMEROS[pendientes] || pendientes} comprobaciones`;
  // El botón principal lleva a resolver lo pendiente: Explorar, los tipos de esta pantalla o Configuración.
  const pend = lista.filter(c => c.ok === false);
  destinoBloqueo = !bloqueado ? null
    : pend.length && pend.every(c => c.explorar) ? 'preview'
    : pend.length && pend.every(c => c.tipos) ? 'tipos'
    : 'config';
  $('toPlanIco').innerHTML = bloqueado ? ICO_AJUSTES : ICO_INICIAR;
  $('toPlanTxt').textContent = !bloqueado ? 'Iniciar prueba'
    : {preview:'Volver a Explorar', tipos:'Elegir tipo de prueba', config:'Resolver en Configuración'}[destinoBloqueo];
  $('toPlan').disabled = verificando;
  const problemas = lista.filter(c => c.ok === false).map(c => c.t.toLowerCase());
  $('prepBloqueo').classList.toggle('hide', !bloqueado);
  $('prepBloqueoTxt').textContent = problemas.length ? `Falta: ${problemas.join(', ')}.` : entornoMotivo;

  renderDetallesCorrida(e, bloqueado, prioritarias, epsPrioritarios);
}

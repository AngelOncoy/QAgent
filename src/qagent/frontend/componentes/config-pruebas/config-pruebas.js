// config-pruebas.js — pantalla de configuración de pruebas (#69): qué hacer, tipo de prueba, profundizar y detalles de la corrida
// HTML del componente (se monta en el marcador data-componente="config-pruebas/config-pruebas" de index.html)
registrarComponente('config-pruebas/config-pruebas', `<!-- ===== 3. CONFIGURACIÓN DE PRUEBAS ===== -->
<section id="s-tests" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <div class="topbar">
    <div class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h6l2 2h10v10H3z"/></svg><b>repo:</b> <span class="repoLbl"></span></div>
    <div class="stepper">
      <span class="done"><b>✓</b>Proyecto</span><span class="chev">›</span>
      <span class="done"><b>✓</b>Vista previa</span><span class="chev">›</span>
      <span class="on"><b>3</b>Configuración de pruebas</span><span class="chev">›</span>
      <span><b>4</b>Ejecución</span>
    </div>
  </div>
  <div class="scroll"><div class="page">

    <!-- Alcance elegido en la Vista previa -->
    <div class="card"><div class="scope" id="scopeSum"></div></div>

    <!-- Configuración: opciones, no planes (#69) -->
    <div class="card">
      <h4>Configuración de las pruebas</h4>
      <div class="bd">
        <div class="cfg-pregunta">¿Qué quieres hacer?</div>
        <div class="cfg-modo" id="cfgModo" role="radiogroup" aria-label="Qué quieres hacer"></div>
        <div id="cfgOpciones"></div>
        <details class="cfg-detalles">
          <summary>Detalles de la corrida</summary>
          <div class="cfg-detalles-cuerpo" id="cfgDetalles"></div>
        </details>
      </div>
    </div>

  </div></div>
  <div class="footbar">
    <span class="msg" id="footMsg2"></span>
    <button class="btn" style="margin-left:auto" onclick="go('preview')">← Volver a la vista previa</button>
    <button class="btn primary" id="toPlan" onclick="startMonitor()">Iniciar corrida →</button>
  </div>
</section>
`);

// Nombre de cada perfil en el pie de la pantalla
const NOMBRE_ELECCION = {humo:'Humo', std:'Estándar', deep:'Estándar + profundizar', reg:'Repetir pruebas guardadas', reg_deep:'Repetir pruebas guardadas + profundizar'};

function estFor(k){
  const p = PROFILES.find(x=>x.k===k);
  const mods = MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m));
  const fns = mods.flatMap(m=>m.fns).filter(f=>f.inc);
  const endpoints = mods.flatMap(m=>(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc));
  const objetivos = mods.flatMap(m=>[
    ...m.fns.filter(f=>f.inc),
    ...(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc)
  ].map(objetivo=>({...objetivo, reuse: SPEC_STATUS[m.path]==='reuse'})));
  const reused = k==='reg' ? 0 : objetivos.filter(objetivo=>objetivo.reuse).length;
  const total = objetivos.length;
  const et = {P: (total - reused) * p.tok * EST_SPLIT.P, G: total * p.tok * EST_SPLIT.G, R: total * p.tok * EST_SPLIT.R};
  const tok = Math.round(et.P + et.G + et.R);
  const saved = Math.round(reused * p.tok * EST_SPLIT.P);
  return {p, fns, endpoints, total, reused, et, tok, saved, time: Math.max(1, Math.round(total * p.t))};
}
// #69: la elección de la pantalla se traduce al perfil que recibe start_run (humo, std, deep,
// reg o reg_deep, #70). Sin funciones prioritarias marcadas no hay nada que profundizar.
// Al repetir solo cuentan las prioritarias con prueba guardada vigente (`repetibles`).
function perfilDeEleccion({modo, tipo, profundizar, profundizarRepetir = false}, prioritarias, repetibles = 0){
  if (modo === 'repetir') return profundizarRepetir && repetibles > 0 ? 'reg_deep' : 'reg';
  if (tipo === 'humo') return 'humo';
  return profundizar && prioritarias > 0 ? 'deep' : 'std';
}
// #70: prioritarias incluidas que tienen una prueba guardada que se puede repetir hoy.
function prioritariasRepetibles(){
  return MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m))
    .flatMap(m=>m.fns.filter(f=>f.inc && f.crit).map(f=>m.path + '::' + f.n))
    .filter(clave=>PRUEBAS_REPETIBLES===null || PRUEBAS_REPETIBLES.has(clave)).length;
}
// #74: «4 funciones y 2 endpoints prioritarios» según lo marcado en Profundizar.
function textoPrioritarias(fns, eps){
  if (!eps) return `${fns} ${fns===1 ? 'función prioritaria' : 'funciones prioritarias'}`;
  const ep = `${eps} ${eps===1 ? 'endpoint' : 'endpoints'}`;
  if (!fns) return `${ep} ${eps===1 ? 'prioritario' : 'prioritarios'}`;
  return `${fns} ${fns===1 ? 'función' : 'funciones'} y ${ep} prioritarios`;
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
function renderOpcionesPruebas(prioritarias, repetibles = 0, epsPrioritarios = 0){
  const {modo, tipo, profundizar, profundizarRepetir = false} = eleccionPruebas;
  const perfil = k => PROFILES.find(p => p.k === k);
  $('cfgModo').innerHTML = [
    ['nuevas', 'Generar pruebas nuevas', false],
    ['repetir', 'Repetir pruebas guardadas', !HAS_PRIOR_RUN],
  ].map(([k, texto, bloqueado]) => `<button type="button" role="radio" aria-checked="${modo===k}" class="${modo===k?'on':''}"
      ${bloqueado ? 'disabled title="Requiere una corrida previa de este proyecto"' : ''} onclick="elegirPruebas({modo:'${k}'})">${texto}</button>`).join('');

  if (modo === 'repetir') {
    const reg = perfil('reg'), deep = perfil('deep');
    const apagadaRep = repetibles === 0;
    const cuantasRep = `${repetibles} ${repetibles===1 ? 'función prioritaria' : 'funciones prioritarias'}`;
    $('cfgOpciones').innerHTML = `<div class="cfg-repetir">
      <div class="cfg-titulo">${reg.n} <span class="pill p-green">sin IA</span></div>
      <span class="cfg-desc">${reg.descripcion}</span>
      <span class="cfg-desc">Se repiten las pruebas aprobadas de los objetivos seleccionados; las de código que cambió se marcan como «requiere corrida nueva».</span>
    </div>
    <label class="cfg-profundizar ${apagadaRep?'dis':''}" ${apagadaRep ? 'title="Ninguna función marcada tiene una prueba guardada vigente"' : ''}>
      <input type="checkbox" ${profundizarRepetir && !apagadaRep ? 'checked' : ''} ${apagadaRep ? 'disabled' : ''} onchange="elegirPruebas({profundizarRepetir:this.checked})">
      <span><b>${deep.n} en ${cuantasRep}</b> <span class="caja caja-${deep.tipo_caja}">${TIPO_CAJA[deep.tipo_caja]}</span>
        <span class="cfg-desc">Comprueba con mutación (mutmut) si las pruebas guardadas detectan errores. Tarda más, pero no usa IA. Solo cuentan las funciones marcadas que tienen una prueba guardada vigente; si nada cambió desde la última vez, se reutiliza su resultado.
          <a href="#" onclick="go('preview');return false">Cambiar cuáles</a></span></span>
    </label>`;
    return;
  }

  const opcion = k => {
    const p = perfil(k);
    return `<label class="cfg-opcion ${tipo===k?'on':''}">
      <input type="radio" name="tipoPrueba" ${tipo===k?'checked':''} onchange="elegirPruebas({tipo:'${k}'})">
      <span><b>${p.n}</b><span class="cfg-desc">${p.descripcion}</span></span>
    </label>`;
  };
  const deep = perfil('deep');
  const apagada = tipo === 'humo' || prioritarias === 0;
  const porque = tipo === 'humo' ? 'Disponible con el tipo Estándar' : 'Marca funciones en la vista previa para profundizar (o endpoints)';
  const cuantas = textoPrioritarias(prioritarias - epsPrioritarios, epsPrioritarios);
  $('cfgOpciones').innerHTML = `<div class="cfg-pregunta">Tipos de prueba</div>
    ${opcion('humo')}
    ${opcion('std')}
    <label class="cfg-profundizar ${apagada?'dis':''}" ${apagada ? `title="${porque}"` : ''}>
      <input type="checkbox" ${profundizar && !apagada ? 'checked' : ''} ${apagada ? 'disabled' : ''} onchange="elegirPruebas({profundizar:this.checked})">
      <span><b>${deep.n} en ${cuantas}</b> <span class="caja caja-${deep.tipo_caja}">${TIPO_CAJA[deep.tipo_caja]}</span>
        <span class="cfg-desc">${deep.descripcion} Las funciones y los endpoints se marcan en la columna Profundizar de la vista previa; en un endpoint solo se muta el código de su manejador.
          <a href="#" onclick="go('preview');return false">Cambiar cuáles</a></span></span>
    </label>`;
}
function renderDetallesCorrida(e, prioritarias, repetibles = 0, epsPrioritarios = 0){
  const {p, reused, et, tok, saved} = e;
  const repite = profile==='reg' || profile==='reg_deep';
  const filas = [
    `Uso de IA estimado: <b>${usoIA(tok)}</b>${tok ? ` · ~${tok.toLocaleString('es-PE')} tokens` : ''}`,
    `Duración aproximada: <b>${p.duracion}</b> · ~${e.time} min`,
    repite
      ? 'Solo se ejecutan pruebas guardadas: ningún agente llama a la IA.'
      : 'Por agente: ' + ['P','G','R'].map(k => `${AGENTS_CFG[k].name} ~${Math.round(et[k]).toLocaleString('es-PE')}`).join(' · ') + ' tokens',
    reused ? `♻ ${reused} objetivo(s) reutilizan su spec vigente: el Planner no trabaja ahí (ahorro ≈ ${saved.toLocaleString('es-PE')} tokens).` : '',
    profile==='deep' ? `mutmut se aplicará a <b>${textoPrioritarias(prioritarias - epsPrioritarios, epsPrioritarios)}</b>: no consume tokens, sí tiempo de CPU.` : '',
    profile==='reg_deep' ? `mutmut se aplicará a <b>${repetibles}</b> función(es) prioritaria(s) con prueba guardada vigente: no consume tokens, pero suma tiempo de CPU a la duración (salvo las que se reutilizan).` : '',
  ];
  $('cfgDetalles').innerHTML = filas.filter(Boolean).map(f => `<div>${f}</div>`).join('');
}
function calc(){
  if (eleccionPruebas.modo === 'repetir' && !HAS_PRIOR_RUN) eleccionPruebas.modo = 'nuevas';
  // #74: los endpoints marcados también cuentan como prioritarios (solo al generar).
  const estStd = estFor('std');
  const epsPrioritarios = estStd.endpoints.filter(e=>e.crit).length;
  const prioritarias = estStd.fns.filter(f=>f.crit).length + epsPrioritarios;
  const repetibles = prioritariasRepetibles();
  profile = perfilDeEleccion(eleccionPruebas, prioritarias, repetibles);
  const e = estFor(profile==='reg_deep' ? 'reg' : profile), {fns, endpoints, total, tok} = e;
  runEstimate = {tok};
  const noDoc = fns.filter(f=>!f.doc).length;
  const nMods = obtenerSeleccionObjetivos().length;
  $('fnCount').textContent = fns.length + ' incluidas';
  // Resumen del alcance (pantalla 3)
  $('scopeSum').innerHTML = `<span style="font-size:12px;color:var(--mut)">Alcance elegido en la vista previa:</span>
    <span class="pill p-grey">${total} objetivos · ${fns.length} funciones · ${endpoints.length} endpoints · ${nMods} ${nMods===1?'módulo':'módulos'}</span>
    <span class="pill p-grey">★ ${textoPrioritarias(prioritarias - epsPrioritarios, epsPrioritarios)}</span>
    ${noDoc?`<span class="pill p-amber">⚠ ${noDoc} sin docstring</span>`:''}
    <button class="btn" onclick="go('preview')">Editar selección</button>`;
  renderPieVistaPrevia(fns, noDoc, endpoints);
  // Pie de la pantalla 3 (elección y alcance)
  let msg = '', block = false;
  if(!entornoListo){ msg = `<span class="err">${escHtml(entornoMotivo)}</span>`; block = true; }
  else if(!total){ msg = 'No hay objetivos seleccionados: vuelve a la vista previa.'; block = true; }
  else if(noDoc){ msg = `<span class="warn">⚠ ${noDoc} función(es) sin docstring: se generarán, pero con oráculo débil (se marcará en el informe).</span>`; }
  else msg = profile==='reg' ? 'Repetir pruebas guardadas: se re-ejecutan sin IA.'
    : profile==='reg_deep' ? `Repetir pruebas guardadas + profundizar: sin IA · mutmut en ${repetibles} función(es).`
    : `Listo: ${total} objetivos · ${NOMBRE_ELECCION[profile]}.`;
  $('footMsg2').innerHTML = msg; $('toPlan').disabled = block;
  renderOpcionesPruebas(prioritarias, repetibles, epsPrioritarios);
  renderDetallesCorrida(e, prioritarias, repetibles, epsPrioritarios);
}

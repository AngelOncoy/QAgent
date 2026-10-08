// config-pruebas.js — pantalla de configuración de pruebas: perfiles, comparación de costos y estimación
// HTML del componente (se monta en el marcador data-componente="config-pruebas/config-pruebas" de index.html)
registrarComponente('config-pruebas/config-pruebas', `<!-- ===== 3. CONFIGURACIÓN DE PRUEBAS (nueva) ===== -->
<section id="s-tests" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <div class="topbar">
    <div class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h6l2 2h10v10H3z"/></svg><b>repo:</b> <span class="repoLbl">github.com/retail-ai/ecommerce-core</span></div>
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

    <!-- Perfil de análisis -->
    <div class="card">
      <h4>Perfil de análisis <span class="pill p-grey">elige uno · todos generan pruebas unitarias pytest</span></h4>
      <div class="bd">
        <div class="profiles" id="profiles"></div>
        <div class="phase2"><span class="hint" style="margin:0">Fuera del alcance de la Fase 1:</span>
          <span class="x">Integración</span><span class="x">API REST</span><span class="x">Carga / estrés</span><span class="x">Extremo a extremo</span><span class="pill p-grey">Fase 2</span></div>

      </div>
    </div>

    <!-- Comparación de los 4 perfiles con la selección actual -->
    <div class="card">
      <h4>Comparación de perfiles <span class="pill p-grey">con las funciones que seleccionaste</span></h4>
      <table class="cmp">
        <thead><tr><th>Perfil</th><th>Qué genera</th><th>Usa IA</th><th>Mutation testing</th><th>Tokens aprox.</th><th>Costo aprox.</th><th>Tiempo aprox.</th></tr></thead>
        <tbody id="cmpBody"></tbody>
      </table>
      <div class="hint" style="padding:8px 16px 14px">Haz clic en una fila para elegir ese perfil. El costo baja cuando se reutilizan specs vigentes y es cero en Regresión.</div>
    </div>

    <!-- Costo estimado del perfil elegido -->
    <div class="card">
        <h4>Costo estimado <span class="pill p-grey">referencial, se compara con el real al final</span></h4>
        <div class="bd">
          <div class="estimate">
            <div><div class="k">Funciones</div><div class="v" id="eFn">0</div></div>
            <div><div class="k">Tokens aprox.</div><div class="v" id="eTok">0</div></div>
            <div><div class="k">Costo aprox.</div><div class="v" id="eCost">S/ 0.00</div></div>
            <div><div class="k">Tiempo aprox.</div><div class="v" id="eTime">0 min</div></div>
          </div>
          <div class="eagents" id="eAgents"></div>
          <div class="hint" id="eNote" style="margin-top:10px"></div>
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

function estFor(k){
  const p = PROFILES.find(x=>x.k===k);
  const mods = MODULES.filter(m=>m.sel && !m.error);
  const fns = mods.flatMap(m=>m.fns).filter(f=>f.inc);
  const selFns = mods.flatMap(m=>m.fns.filter(f=>f.inc).map(f=>({...f, reuse: SPEC_STATUS[m.path]==='reuse'})));
  const reused = k==='reg' ? 0 : selFns.filter(f=>f.reuse).length;
  const et = {P: (fns.length - reused) * p.tok * EST_SPLIT.P, G: fns.length * p.tok * EST_SPLIT.G, R: fns.length * p.tok * EST_SPLIT.R};
  const tok = Math.round(et.P + et.G + et.R), cost = agentCost(et) * FX;
  const saved = Math.round(reused * p.tok * EST_SPLIT.P), savedPen = saved * AGENTS_CFG.P.price / 1e6 * FX;
  return {p, fns, reused, et, tok, cost, saved, savedPen, time: Math.max(1, Math.round(fns.length * p.t))};
}
function pickProfile(k){ profile = k; calc(); }
function renderProfiles(){
  $('profiles').innerHTML = PROFILES.map(p => {
    const locked = p.k==='reg' && !HAS_PRIOR_RUN;
    const e = estFor(p.k), over = e.cost > TOPE_PEN;
    return `
    <div class="prof ${p.k===profile?'on':''} ${locked?'dis':''}" onclick="${locked?'':`pickProfile('${p.k}')`}">
      <b>${p.n}</b>${p.k==='reg'&&HAS_PRIOR_RUN?'<span class="pill p-green" style="margin-left:6px">sin IA</span>':''}<p>${p.d}</p>
      <div class="foot"><span class="pill ${p.pill}">${p.tok? '~'+p.tok.toLocaleString('es-PE')+' tokens/fn':'0 tokens'}</span>${p.m.map(x=>`<span class="pill p-grey">${x}</span>`).join('')}</div>
      <div class="pcost"><span>Costo aprox.</span><b class="${over?'over':''}">S/ ${e.cost.toFixed(2)}</b><span>· ${e.time} min</span></div>
      ${locked?`<div class="why">Requiere una corrida previa de este proyecto.</div>`:(p.k==='reg'?`<div class="hint" style="margin-top:8px">6 pruebas aprobadas guardadas en .pyagent/tests/ (última: corrida #8791-A). En el demo se simula la corrida Profunda.</div>`:'')}
    </div>`;}).join('');
}
function renderCompare(){
  const GEN = {humo:'1 caso feliz por función', std:'Casos felices, límite y excepciones', deep:'Igual que Estándar', reg:'Pruebas ya aprobadas y guardadas'};
  const crit = MODULES.filter(m=>m.sel).flatMap(m=>m.fns).filter(f=>f.inc && f.crit).length;
  $('cmpBody').innerHTML = PROFILES.map(p => {
    const locked = p.k==='reg' && !HAS_PRIOR_RUN, e = estFor(p.k), over = e.cost > TOPE_PEN;
    return `<tr class="pick ${p.k===profile?'sel':''} ${locked?'dis':''}" onclick="${locked?'':`pickProfile('${p.k}')`}">
      <td><b>${p.n}</b></td><td>${GEN[p.k]}</td><td>${p.k==='reg'?'No':'Sí'}</td>
      <td>${p.k==='deep' ? 'Sí · '+crit+' función(es) crítica(s)' : '—'}</td>
      <td class="mono">${p.tok ? '~'+e.tok.toLocaleString('es-PE') : '0'}</td>
      <td class="mono ${over?'over':''}">S/ ${e.cost.toFixed(2)}${over?' · supera el tope':''}</td>
      <td class="mono">${e.time} min</td></tr>`;
  }).join('');
}
function calc(){
  const e = estFor(profile), {p, fns, reused, et, tok, cost, saved, savedPen} = e, cap = TOPE_PEN;
  runEstimate = {tok, pen:cost};
  $('eAgents').innerHTML = profile==='reg'
    ? '<span class="ea"><i style="background:var(--emerald-500)"></i>Regresión: solo se ejecutan pruebas guardadas · ningún agente llama a la IA</span>'
    : ['P','G','R'].map(k => `<span class="ea"><i style="background:${{P:'var(--blue-500)',G:'var(--purple-500)',R:'var(--emerald-500)'}[k]}"></i>${AGENTS_CFG[k].name}: ~${Math.round(et[k]).toLocaleString('es-PE')} tok · S/ ${(et[k]*AGENTS_CFG[k].price/1e6*FX).toFixed(2)}</span>`).join('')
      + `<span class="ea tope">Tope por corrida: <b>S/ ${TOPE_PEN.toFixed(2)}</b> · definido por el equipo (ver Configuración)</span>`;
  const noDoc = fns.filter(f=>!f.doc).length, crit = fns.filter(f=>f.crit).length;
  const nMods = MODULES.filter(m=>m.sel).length;
  $('fnCount').textContent = fns.length + ' incluidas';
  $('eFn').textContent = fns.length;
  $('eTok').textContent = '~' + tok.toLocaleString('es-PE');
  $('eCost').textContent = 'S/ ' + cost.toFixed(2);
  $('eCost').style.color = cost>cap ? 'var(--red-t)' : '';
  $('eTime').textContent = e.time + ' min';
  $('eNote').innerHTML = `Costo calculado con el precio de cada agente (Planner US$ ${AGENTS_CFG.P.price.toFixed(2)} · Generator y Reviewer US$ ${AGENTS_CFG.G.price.toFixed(2)} por millón de tokens).` +
    (reused ? `<br>♻ ${reused} función(es) reutilizan su spec vigente: el Planner no trabaja ahí (ahorro ≈ ${saved.toLocaleString('es-PE')} tokens · S/ ${savedPen.toFixed(2)}).` : '') +
    (profile==='deep' ? `<br>mutmut se aplicará a <b>${crit}</b> función(es) crítica(s): no consume tokens, sí tiempo de CPU.` : '');
  // Resumen del alcance (pantalla 3)
  $('scopeSum').innerHTML = `<span style="font-size:12px;color:var(--mut)">Alcance elegido en la vista previa:</span>
    <span class="pill p-grey">${fns.length} funciones · ${nMods} ${nMods===1?'módulo':'módulos'}</span>
    <span class="pill p-grey">★ ${crit} crítica(s)</span>
    ${noDoc?`<span class="pill p-amber">⚠ ${noDoc} sin docstring</span>`:''}
    <button class="btn" onclick="go('preview')">Editar selección</button>`;
  renderPieVistaPrevia(fns, noDoc);
  // Pie de la pantalla 3 (perfil y costo)
  let msg = '', block = false;
  if(!fns.length){ msg = 'No hay funciones seleccionadas: vuelve a la vista previa.'; block = true; }
  else if(cost>cap){ msg = `<span class="err">El costo estimado supera el tope de S/ ${cap.toFixed(2)} definido por el equipo. Reduce funciones o elige un perfil más liviano.</span>`; block = true; }
  else if(noDoc){ msg = `<span class="warn">⚠ ${noDoc} función(es) sin docstring: se generarán, pero con oráculo débil (se marcará en el informe).</span>`; }
  else msg = profile==='reg' ? 'Regresión: re-ejecuta pruebas guardadas sin IA. (En el demo se muestra la corrida Profunda #8841-B.)' : `Listo: ${fns.length} funciones · perfil ${p.n}.`;
  $('footMsg2').innerHTML = msg; $('toPlan').disabled = block;
  renderProfiles(); renderCompare();
}


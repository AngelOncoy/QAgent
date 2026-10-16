// config-pruebas.js — pantalla de configuración de pruebas: perfiles, comparación y estimación de tokens y duración
// HTML del componente (se monta en el marcador data-componente="config-pruebas/config-pruebas" de index.html)
registrarComponente('config-pruebas/config-pruebas', `<!-- ===== 3. CONFIGURACIÓN DE PRUEBAS (nueva) ===== -->
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

    <!-- Perfil de análisis -->
    <div class="card">
      <h4>Perfil de análisis <span class="pill p-grey">elige uno · todos generan pruebas unitarias pytest</span></h4>
      <div class="bd">
        <div class="profiles" id="profiles"></div>
        <div class="leyenda-caja">
          <span><span class="caja caja-negra">Caja negra</span>: evalúa entradas y salidas sin mirar el código.</span>
          <span><span class="caja caja-blanca">Caja blanca</span>: evalúa el código por dentro (caminos, ramas, cobertura).</span>
        </div>
      </div>
    </div>

    <!-- Comparación de los 4 perfiles con la selección actual -->
    <div class="card">
      <h4>Comparación de perfiles <span class="pill p-grey">con las funciones que seleccionaste</span></h4>
      <div class="table-scroll"><table class="cmp">
        <thead><tr><th>Perfil</th><th>Qué genera</th><th>Usa IA</th><th>Mutation testing</th><th>Tokens aprox.</th><th>Duración aprox.</th></tr></thead>
        <tbody id="cmpBody"></tbody>
      </table></div>
      <div class="hint" style="padding:8px 16px 14px">Haz clic en una fila para elegir ese perfil. Los tokens bajan cuando se reutilizan specs vigentes y son cero en Regresión.</div>
    </div>

    <!-- Estimación del perfil elegido -->
    <div class="card">
        <h4>Estimación <span class="pill p-grey">referencial, se compara con la real al final</span></h4>
        <div class="bd">
          <div class="estimate">
            <div><div class="k">Objetivos</div><div class="v" id="eFn">0</div></div>
            <div><div class="k">Tokens aprox.</div><div class="v" id="eTok">0</div></div>
            <div><div class="k">Duración aprox.</div><div class="v" id="eTime">0 min</div></div>
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
  const mods = MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m));
  const fns = mods.flatMap(m=>m.fns).filter(f=>f.inc);
  const endpoints = mods.flatMap(m=>m.endpoints || []);
  const objetivos = mods.flatMap(m=>[
    ...m.fns.filter(f=>f.inc),
    ...(m.endpoints || [])
  ].map(objetivo=>({...objetivo, reuse: SPEC_STATUS[m.path]==='reuse'})));
  const reused = k==='reg' ? 0 : objetivos.filter(objetivo=>objetivo.reuse).length;
  const total = objetivos.length;
  const et = {P: (total - reused) * p.tok * EST_SPLIT.P, G: total * p.tok * EST_SPLIT.G, R: total * p.tok * EST_SPLIT.R};
  const tok = Math.round(et.P + et.G + et.R);
  const saved = Math.round(reused * p.tok * EST_SPLIT.P);
  return {p, fns, endpoints, total, reused, et, tok, saved, time: Math.max(1, Math.round(total * p.t))};
}
function pickProfile(k){
  profile = k;
  calc();
  if (typeof desbloquearVista === 'function') desbloquearVista('monitor');
}
function renderProfiles(){
  $('profiles').innerHTML = PROFILES.map(p => {
    const locked = p.k==='reg' && !HAS_PRIOR_RUN;
    const e = estFor(p.k);
    return `
    <div class="prof ${p.k===profile?'on':''} ${locked?'dis':''}" onclick="${locked?'':`pickProfile('${p.k}')`}">
      <div class="prof-cab"><b>${p.n}</b>${p.k==='reg'&&HAS_PRIOR_RUN?'<span class="pill p-green">sin IA</span>':''}<span class="caja caja-${p.tipo_caja}">${TIPO_CAJA[p.tipo_caja]}</span></div>
      <p>${p.descripcion}</p>
      <div class="foot"><span class="pill ${p.pill}">${p.tok? '~'+p.tok.toLocaleString('es-PE')+' tokens/fn':'0 tokens'}</span>${p.m.map(x=>`<span class="pill p-grey">${x}</span>`).join('')}</div>
      <div class="pdur"><span>Duración aprox.</span><b>${p.duracion}</b><span>· ${e.time} min</span></div>
      ${locked?`<div class="why">Requiere una corrida previa de este proyecto.</div>`:''}
    </div>`;}).join('');
}
function renderCompare(){
  const GEN = {humo:'1 caso feliz por función', std:'Casos felices, límite y excepciones', deep:'Igual que Estándar', reg:'Pruebas ya aprobadas y guardadas'};
  const crit = MODULES.filter(m=>m.sel).flatMap(m=>m.fns).filter(f=>f.inc && f.crit).length;
  $('cmpBody').innerHTML = PROFILES.map(p => {
    const locked = p.k==='reg' && !HAS_PRIOR_RUN, e = estFor(p.k);
    return `<tr class="pick ${p.k===profile?'sel':''} ${locked?'dis':''}" onclick="${locked?'':`pickProfile('${p.k}')`}">
      <td><b>${p.n}</b></td><td>${GEN[p.k]}</td><td>${p.k==='reg'?'No':'Sí'}</td>
      <td>${p.k==='deep' ? 'Sí · '+crit+' función(es) crítica(s)' : '—'}</td>
      <td class="mono">${p.tok ? '~'+e.tok.toLocaleString('es-PE') : '0'}</td>
      <td class="mono">${p.duracion} · ${e.time} min</td></tr>`;
  }).join('');
}
function calc(){
  const e = estFor(profile), {p, fns, endpoints, total, reused, et, tok, saved} = e;
  runEstimate = {tok};
  $('eAgents').innerHTML = profile==='reg'
    ? '<span class="ea"><i style="background:var(--emerald-500)"></i>Regresión: solo se ejecutan pruebas guardadas · ningún agente llama a la IA</span>'
    : ['P','G','R'].map(k => `<span class="ea"><i style="background:${{P:'var(--blue-500)',G:'var(--purple-500)',R:'var(--emerald-500)'}[k]}"></i>${AGENTS_CFG[k].name}: ~${Math.round(et[k]).toLocaleString('es-PE')} tok</span>`).join('');
  const noDoc = fns.filter(f=>!f.doc).length, crit = fns.filter(f=>f.crit).length;
  const nMods = obtenerSeleccionObjetivos().length;
  $('fnCount').textContent = fns.length + ' incluidas';
  $('eFn').textContent = total;
  $('eTok').textContent = '~' + tok.toLocaleString('es-PE');
  $('eTime').textContent = `${p.duracion} · ${e.time} min`;
  $('eNote').innerHTML = [
    reused ? `♻ ${reused} función(es) reutilizan su spec vigente: el Planner no trabaja ahí (ahorro ≈ ${saved.toLocaleString('es-PE')} tokens).` : '',
    profile==='deep' ? `mutmut se aplicará a <b>${crit}</b> función(es) crítica(s): no consume tokens, sí tiempo de CPU.` : '',
  ].filter(Boolean).join('<br>');
  // Resumen del alcance (pantalla 3)
  $('scopeSum').innerHTML = `<span style="font-size:12px;color:var(--mut)">Alcance elegido en la vista previa:</span>
    <span class="pill p-grey">${total} objetivos · ${fns.length} funciones · ${endpoints.length} endpoints · ${nMods} ${nMods===1?'módulo':'módulos'}</span>
    <span class="pill p-grey">★ ${crit} crítica(s)</span>
    ${noDoc?`<span class="pill p-amber">⚠ ${noDoc} sin docstring</span>`:''}
    <button class="btn" onclick="go('preview')">Editar selección</button>`;
  renderPieVistaPrevia(fns, noDoc, endpoints);
  // Pie de la pantalla 3 (perfil y alcance)
  let msg = '', block = false;
  if(!entornoListo){ msg = `<span class="err">${escHtml(entornoMotivo)}</span>`; block = true; }
  else if(!total){ msg = 'No hay objetivos seleccionados: vuelve a la vista previa.'; block = true; }
  else if(noDoc){ msg = `<span class="warn">⚠ ${noDoc} función(es) sin docstring: se generarán, pero con oráculo débil (se marcará en el informe).</span>`; }
  else msg = profile==='reg' ? 'Regresión: re-ejecuta pruebas guardadas sin IA.' : `Listo: ${total} objetivos · perfil ${p.n}.`;
  $('footMsg2').innerHTML = msg; $('toPlan').disabled = block;
  renderProfiles(); renderCompare();
}


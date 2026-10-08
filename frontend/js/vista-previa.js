// vista-previa.js — vista previa y configuración de pruebas
/* ---------------- Vista previa ---------------- */
async function loadProject(name, src, where, br='main', ruta=''){
  if(!apiRec()) demoRegistrar(name, src, where);
  document.querySelectorAll('.repoName').forEach(e=>e.textContent=name);
  document.querySelectorAll('.repoLbl').forEach(e=>e.textContent = src==='git' ? where.replace('https://','').replace(/\.git$/,'') : where);
  document.querySelectorAll('.brLbl').forEach(e=>e.textContent=br); $('branchLbl').textContent = br;
  monitorStarted = false; 
  projectPath = ruta ? ruta : (src==='git' ? 'E:\\Proyectos\\' + name : where);

  if (window.pywebview && window.pywebview.api && (window.pywebview.api.obtener_vista_previa || window.pywebview.api.analizar_proyecto)) {
    try {
      const fn = window.pywebview.api.obtener_vista_previa || window.pywebview.api.analizar_proyecto;
      const res = await fn(projectPath);
      if (res && res.ok) {
        cargarDatosVistaPrevia(res);
      } else {
        aplicarResumenDemo();
      }
    } catch (err) {
      console.error("Error al obtener la vista previa por AST:", err);
      aplicarResumenDemo();
    }
  } else {
    aplicarResumenDemo();
  }

  renderTree(); 
  renderProfiles(); 
  go('preview');
}
function renderTree(){
  let h = '';
  const dirsVistos = new Set();
  MODULES.forEach((m, i) => {
    const partes = m.path.split('/');
    if (partes.length > 1) {
      const dir = partes.slice(0, -1).join('/') + '/';
      if (!dirsVistos.has(dir)) {
        dirsVistos.add(dir);
        h += `<div class="row dir">📁 ${escHtml(dir)}</div>`;
      }
    }
    const nombreArchivo = partes[partes.length - 1];
    if (m.error) {
      h += `<div class="row ind" style="color:var(--red-t)"><span class="mono">📄 ${escHtml(nombreArchivo)}</span><span class="pill p-red" style="margin-left:auto">no se pudo analizar</span></div>`;
    } else {
      const fnConRamas = (m.fns || []).filter(f => f.br > 0).length;
      h += `<div class="row ind"><input type="checkbox" ${m.sel ? 'checked' : ''} onchange="MODULES[${i}].sel=this.checked;renderFns()"> <span class="mono">${escHtml(nombreArchivo)}</span><span class="n" title="${fnConRamas} funciones con ramas">${m.fns.length} fn</span></div>`;
    }
  });
  h += '<div class="row dir ign">📁 tests/ <span class="n">ignorado</span></div>';
  h += '<div class="row dir ign">📁 .pyagent/ <span class="n">ignorado</span></div>';
  $('tree').innerHTML = h;
  renderFns();
}
function renderFns(){
  const sel = MODULES.filter(m => m.sel && !m.error);
  const totalFns = sel.flatMap(m => m.fns).length;
  $('modCount').textContent = sel.length + (sel.length === 1 ? ' módulo' : ' módulos');
  $('fnCount').textContent = totalFns + ' incluidas';
  let h = '';
  
  MODULES.forEach((m, mi) => {
    if (m.error) {
      h += `<tr><td colspan="6" style="background:var(--panel2);color:var(--red-t);font-family:var(--mono);font-size:11px;padding:9px 12px">
        <b>📄 ${escHtml(m.path)}</b> <span class="pill p-red" style="margin-left:8px">no se pudo analizar</span>
        <div class="sub" style="color:var(--red-t);margin-top:3px">
          Error de sintaxis (${escHtml(m.error.tipo || 'SyntaxError')}${m.error.linea ? ' en línea ' + m.error.linea : ''}): ${escHtml(m.error.mensaje || 'Error al analizar archivo')}
        </div>
      </td></tr>`;
      return;
    }
    if (!m.sel) return;
    
    const sp = SPEC_STATUS[m.path];
    const spTag = sp === 'reuse' 
      ? '<span class="pill p-green" style="margin-left:8px">♻ spec vigente · Planner se omite</span>' 
      : sp === 'stale' 
        ? '<span class="pill p-amber" style="margin-left:8px">↻ código cambió · spec se regenera</span>' 
        : '<span class="pill p-grey" style="margin-left:8px">sin spec previo</span>';
    const conRamasCount = (m.fns || []).filter(f => f.br > 0).length;
    const ramasTag = `<span class="pill p-grey" style="margin-left:6px" title="${conRamasCount} funciones con ramas">${conRamasCount} con ramas</span>`;
    
    h += `<tr><td colspan="6" style="background:var(--panel2);font-family:var(--mono);font-size:11px;color:var(--mut)"><b>${escHtml(m.path)}</b>${ramasTag}${spTag}</td></tr>`;
    m.fns.forEach((f, fi) => {
      const docHtml = f.doc 
        ? '<span class="ok">✓</span>' 
        : '<span class="warn" title="el valor esperado no tendrá fuente (oráculo débil)">⚠ falta</span>';
      const tipadoHtml = f.typed ? '<span class="ok">✓</span>' : '<span class="no">✗</span>';
      h += `<tr>
        <td class="fn">${escHtml(f.n)}<div class="sub">${escHtml(f.sig)}</div></td>
        <td class="${f.typed ? 'ok' : 'no'}">${tipadoHtml}</td>
        <td class="${f.doc ? 'ok' : 'warn'}" ${f.doc ? '' : 'title="el valor esperado no tendrá fuente (oráculo débil)"'}>${docHtml}</td>
        <td class="mono">${f.br}</td>
        <td><button class="star ${f.crit ? 'on' : ''}" onclick="toggle(${mi},${fi},'crit')">${f.crit ? '★' : '☆'}</button></td>
        <td><input type="checkbox" ${f.inc ? 'checked' : ''} onchange="toggle(${mi},${fi},'inc')"></td>
      </tr>`;
    });
  });
  
  $('fnTable').innerHTML = h || '<tr><td colspan="6" class="hint">Selecciona al menos un módulo.</td></tr>';
  calc();
}
function toggle(mi,fi,k){ MODULES[mi].fns[fi][k] = !MODULES[mi].fns[fi][k]; renderFns(); }
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
    ? '<span class="ea"><i style="background:#10b981"></i>Regresión: solo se ejecutan pruebas guardadas · ningún agente llama a la IA</span>'
    : ['P','G','R'].map(k => `<span class="ea"><i style="background:${{P:'#3b82f6',G:'#a855f7',R:'#10b981'}[k]}"></i>${AGENTS_CFG[k].name}: ~${Math.round(et[k]).toLocaleString('es-PE')} tok · S/ ${(et[k]*AGENTS_CFG[k].price/1e6*FX).toFixed(2)}</span>`).join('')
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
  // Pie de la pantalla 2 (alcance)
  let m1 = '', b1 = false;
  if(!fns.length){ m1 = 'Selecciona al menos una función.'; b1 = true; }
  else if(noDoc){ m1 = `<span class="warn">⚠ ${noDoc} función(es) sin docstring: se generarán, pero con oráculo débil (se marcará en el informe).</span>`; }
  else m1 = `${fns.length} funciones seleccionadas · siguiente paso: elegir el perfil de pruebas.`;
  $('footMsg').innerHTML = m1; $('toTests').disabled = b1;
  // Pie de la pantalla 3 (perfil y costo)
  let msg = '', block = false;
  if(!fns.length){ msg = 'No hay funciones seleccionadas: vuelve a la vista previa.'; block = true; }
  else if(cost>cap){ msg = `<span class="err">El costo estimado supera el tope de S/ ${cap.toFixed(2)} definido por el equipo. Reduce funciones o elige un perfil más liviano.</span>`; block = true; }
  else if(noDoc){ msg = `<span class="warn">⚠ ${noDoc} función(es) sin docstring: se generarán, pero con oráculo débil (se marcará en el informe).</span>`; }
  else msg = profile==='reg' ? 'Regresión: re-ejecuta pruebas guardadas sin IA. (En el demo se muestra la corrida Profunda #8841-B.)' : `Listo: ${fns.length} funciones · perfil ${p.n}.`;
  $('footMsg2').innerHTML = msg; $('toPlan').disabled = block;
  renderProfiles(); renderCompare();
}


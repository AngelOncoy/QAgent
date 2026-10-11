// ejecucion.js — pantalla de ejecución de pruebas: KPIs, filtros y detalle por función
// HTML del componente (se monta en el marcador data-componente="ejecucion/ejecucion" de index.html)
registrarComponente('ejecucion/ejecucion', `<!-- ===== 5. EJECUCIÓN DE PRUEBAS (según tu diseño en React) ===== -->
<section id="s-exec" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <div class="scroll"><div class="execwrap">
    <div class="kpis" id="kpis"></div>

    <div class="toolbar">
      <div class="tleft"><span class="flbl"><span class='ico' data-i='filter' data-c='var(--slate-300-c)'></span> Filtrar:</span><div id="fbtns"></div></div>
      <div class="cmd2"><span class='ico' data-i='term' data-c='var(--blue-400)'></span> docker run --rm --network none pyagent-sandbox:base pytest -v --cov --cov-branch</div>
    </div>
    <div id="suites"></div>
  </div></div>
</section>
`);

/* ---------------- Ejecución de pruebas ---------------- */
let filterState = 'ALL';
const expanded = {fn_1:true, fn_2:true};
function renderExecKpis(){
  const m = metrics(), passOk = m.pass >= META.pass[0], msOk = m.ms >= META.ms, est = runEstimate;
  $('kpis').innerHTML = `
  <div class="kpi"><div class="kh"><span>PASS RATE</span>${I('checkc','var(--emerald-400)',15)}</div>
    <div class="kmid"><div class="kv" style="color:${passOk?'var(--slate-200)':'var(--amber-300)'}">${pct(m.pass)} <small>/ ${META.pass[0]}–${META.pass[1]}% meta</small></div>
    <div class="ks" style="color:${passOk?'var(--emerald-400)':'var(--amber-400)'}">${I(passOk?'check':'warn','currentColor',12)} ${passOk?'Dentro de la meta':'Bajo la meta'} · ${m.ok}/${m.n} suites sin error</div></div>
    <div><div class="kb"><i style="width:${m.pass}%;background:linear-gradient(90deg,var(--emerald-500),var(--teal-400))"></i></div>
    <div class="kscale"><span>0%</span><span class="c">Meta: ${META.pass[0]}%</span><span>100%</span></div></div></div>
  <div class="kpi"><div class="kh"><span>COBERTURA CÓDIGO</span>${I('merge','var(--blue-400)',15)}</div>
    <div class="kmid"><div class="kv kv2">${pct(m.lines,1)} <small>líneas</small> <em>|</em> <span style="color:var(--blue-400)">${pct(m.branch,1)}</span> <small>ramas</small></div>
    <div class="ks" style="color:var(--blue-400)">${I('target','var(--blue-400)',12)} Meta ≥ ${META.lines}% de líneas ${m.lines>=META.lines?'alcanzada':'no alcanzada'}</div></div>
    <div><div class="kb"><i style="width:${m.lines}%;background:var(--blue-500)"></i></div><div class="kb thin"><i style="width:${m.branch}%;background:var(--indigo-400)"></i></div></div></div>
  <div class="kpi"><div class="kh"><span>ITERACIONES PROMEDIO</span>${I('refresh','var(--purple-400)',15)}</div>
    <div class="kmid"><div class="kv">${m.iter.toFixed(1)} <small>/ 3.0 máx</small></div>
    <div class="ks" style="color:var(--purple-400)">${m.iter<META.iter?'Meta &lt; 2 cumplida':'Sobre la meta de 2'} <b style="color:var(--mut)">(${pct(m.iter/3*100)} del tope)</b></div></div>
    <div><div class="kb"><i style="width:${m.iter/3*100}%;background:linear-gradient(90deg,var(--purple-500),var(--indigo-500))"></i></div>
    <div class="kscale"><span>1.0</span><span class="c">Tope: 3.0</span></div></div></div>
  <div class="kpi"><div class="kh"><span>TOKENS POR AGENTE</span>${I('coins','var(--amber-400)',15)}</div>
    <div class="kmid"><div class="kv kv2">${kfmt(m.tokens)} <small>tokens</small></div>
    <div class="ktri"><span style="color:var(--blue-400)">P: <b>${AGENT_SPLIT.P}%</b></span><span style="color:var(--purple-400)">G: <b>${AGENT_SPLIT.G}%</b></span><span style="color:var(--emerald-400)">R: <b>${AGENT_SPLIT.R}%</b></span></div></div>
    <div><div class="kb"><i style="width:${AGENT_SPLIT.P}%;background:var(--blue-500)"></i><i style="width:${AGENT_SPLIT.G}%;background:var(--purple-500)"></i><i style="width:${AGENT_SPLIT.R}%;background:var(--emerald-500)"></i></div>
    <div class="kscale"><span>$${m.usd.toFixed(2)} USD</span><span>S/ ${m.pen.toFixed(2)} PEN</span></div>
    <div class="kscale" title="Estimación mostrada en la vista previa"><span>Estimado: ~${kfmt(est.tok)}</span><span>S/ ${est.pen.toFixed(2)}</span></div>
    <div class="kscale"><span style="color:var(--blue-300)">P $${m.agentUsd.P.toFixed(3)}</span><span style="color:var(--purple-300)">G $${m.agentUsd.G.toFixed(3)}</span><span style="color:var(--green-300)">R $${m.agentUsd.R.toFixed(3)}</span></div>
    <div class="kscale" style="color:var(--green-300)"><span>♻ 4 specs reutilizados</span><span>Planner omitido</span></div></div></div>
  <div class="kpi"><div class="kh"><span>MUTATION SCORE</span>${I('dna','var(--rose-400)',15)}</div>
    <div class="kmid"><div class="kv" style="color:${msOk?'var(--slate-200)':'var(--amber-300)'}">${pct(m.ms)} <small>/ ${META.ms}% meta</small></div>
    <div class="ks" style="color:var(--amber-400)">${I('warn','var(--amber-400)',12)} Brecha activa en ${m.gaps} funciones · solo ${m.crit} críticas</div></div>
    <div><div class="kb"><i style="width:${m.ms}%;background:linear-gradient(90deg,var(--amber-500),var(--rose-500))"></i></div>
    <div class="kscale"><span>0%</span><span class="c">Meta: ${META.ms}%</span><span>100%</span></div></div></div>`;
}
function renderExec(){
  if (ejecucionReal) { renderExecReal(ejecucionReal); return; }   // corrida real (HU-18)
  renderExecKpis();
  const keys = ['ALL', ...Object.keys(ST)];
  $('fbtns').innerHTML = keys.map(k => {
    const n = k==='ALL' ? RUN.length : RUN.filter(f=>f.status===k).length;
    const bg = k==='ALL' ? 'var(--blue-600)' : ST[k].c, lbl = k==='ALL' ? 'Todos' : ST[k].filter;
    return `<button class="fb2 ${filterState===k?'on':''}" style="${filterState===k?'background:'+bg:''}" onclick="filterState='${k}';renderExec()">${k!=='ALL'?`<i class="fdot" style="background:${ST[k].c}"></i>`:''}${lbl} (${n})</button>`;
  }).join('');
  const list = RUN.filter(f => filterState==='ALL' || f.status===filterState);
  const groups = {}; list.forEach(x => (groups[x.module] ||= []).push(x));
  $('suites').innerHTML = Object.keys(groups).map(m => `
    <div class="suite2">
      <div class="sh2"><div class="l">${I('file','var(--blue-400)',15)}<b>${m}</b><span class="c">(${groups[m].length} ${groups[m].length===1?'función':'funciones'} bajo prueba)</span></div>
        <div class="r"><span>${I('shield','var(--emerald-400)',13)} Strict AST Guard</span><span>Python 3.11</span></div></div>
      ${groups[m].map(fn => { const open = !!expanded[fn.id]; const s = ST[fn.status].exec;
        const audLbl = {clean:['✓ Intactas','var(--emerald-400)','Fidedigna'], relaxed:['⚠ Relajadas','var(--rose-400)','Relajada'], oracle:['⚠ Oráculo alterado','var(--fuchsia-400)','Valor copiado del código'], weak:['⚠ Débil','var(--amber-400)','Más laxa que el contrato']}[fn.cmp.state];
        const diagCls = {rejected_laundering:'d-rose', rejected_oracle:'d-fuch', stuck:'d-amber', low_mutation:'d-orange'}[fn.status] || 'd-amber';
        return `<div class="fnrow">
          <div class="fnhead" onclick="expanded['${fn.id}']=!expanded['${fn.id}'];renderExec()">
            <div class="l">${I(open?'chevD':'chevR','var(--slate-300-c)',15)}<span class="nm">${I(s[0],s[1],16)} test_${fn.name}()</span>
              <span class="bdg b-${fn.bv}">${esc(fn.badge)}</span>
              ${fn.status==='rejected_laundering'?'<span class="bdg b-laund">Assertion Laundering detectado</span>':''}
              ${fn.status==='rejected_oracle'?'<span class="bdg b-orc">Posible bug en el código</span>':''}</div>
            <div class="r"><span>Intento: <b style="color:${fn.iterations>1?'var(--amber-400)':'var(--slate-200)'}">${fn.iterations}/3</b></span>
              <span>${I('clock','var(--slate-300-c)',12)} ${fn.time}</span><span>Cov: <b style="color:var(--blue-400)">${fn.lines_cov}%</b></span>
              <span class="sbdg ${s[2]}">${I(s[3],'currentColor',12)} ${stExec(fn)}</span></div>
          </div>
          ${open ? `<div class="fnbody">
            ${fn.diag ? `<div class="diag ${diagCls}"><b>${I(fn.status==='rejected_oracle'?'bug':fn.status==='rejected_laundering'?'shieldA':'alertc','currentColor',15)} Diagnóstico del Reviewer Agent:</b><p>${esc(fn.diag)}</p></div>` : ''}
            <div class="g2">
              <div class="pn"><div class="pnh"><b>${I('code','var(--purple-400)',13)} Código PyTest (Generator Agent)</b><span>test_${fn.name}.py</span></div><pre>${hl(fn.code)}</pre></div>
              <div style="display:flex;flex-direction:column;gap:16px">
                <div class="pn"><div class="pnh"><b>${I('term','var(--emerald-400)',13)} Log del Sandbox Aislado (Docker)</b><span style="color:${ranOK(fn)?'var(--emerald-400)':'var(--rose-400)'};font-size:10px">exit status: ${ranOK(fn)&&fn.status==='passed'?0:1}</span></div>
                  <div class="logs">${fn.logs.map(l=>`<div class="${logCls(l)}">${esc(l)}</div>`).join('')}</div></div>
                <div class="pn"><div class="pnh"><b>${I('shieldC','var(--blue-400)',13)} Auditoría de Aserciones (AST Diff)</b><b style="color:${audLbl[1]}">${audLbl[0]}</b></div>
                  <div class="aud">
                    <div class="lbl"><span>Aserción de Contrato (Planner)</span><span style="color:var(--emerald-400)">Esperado estricto</span></div>
                    <div class="bx" style="color:var(--emerald-300)">${esc(fn.cmp.original)}</div>
                    <div class="lbl" style="padding-top:3px"><span>Aserción Sintetizada (Generator)</span><span style="color:${audLbl[1]};font-weight:700">${audLbl[2]}</span></div>
                    <div class="bx ${fn.cmp.state==='clean'?'':'bad'}" style="${fn.cmp.state==='oracle'?'border-color:var(--fuchsia-700);color:var(--fuchsia-300);background:var(--fuchsia-950-a40)':fn.cmp.state==='weak'?'border-color:var(--amber-700);color:var(--amber-300);background:var(--amber-950-a35)':''}">${esc(fn.cmp.modified)}</div>
                  </div></div>
              </div>
            </div></div>` : ''}
        </div>`; }).join('')}
    </div>`).join('');
}
function logCls(l){ return l.includes('PASSED')?'lg-ok':(l.includes('REJECT')||l.includes('FAILED')||l.includes('ERROR'))?'lg-err':(l.includes('DIFF')||l.includes('WARNING')||l.includes('ORACLE'))?'lg-diff':'lg-n'; }

/* ---------------- Ejecución de una corrida real (HU-18) ----------------
   Todo lo que se muestra viene de obtener_ejecucion() de Python, que lo calcula desde
   .pyagent/runs/<run_id>/results.json: aquí no se calcula ni se escribe ninguna cifra. */
let ejecucionReal = null;
const ESTADO_REAL = {   // estado de la vista -> colores e íconos del catálogo ST
  aprobado:{st:'passed', txt:'APROBADO'},
  bug_detectado:{st:'rejected_oracle', txt:'BUG DETECTADO'},
  rechazado_laundering:{st:'rejected_laundering', txt:'RECHAZADO: LAUNDERING'},
  estancado:{st:'stuck', txt:'ESTANCADO'},
  sin_veredicto:{st:'stuck', txt:'SIN VEREDICTO'},
};
const AGENTE_REAL = {planner:['P','var(--blue-400)'], generator:['G','var(--purple-400)'], reviewer:['R','var(--emerald-400)']};
const numReal = (v, d=1, suf='%') => v===null || v===undefined ? '—' : Number(v).toFixed(d) + suf;
const usdReal = v => v===null || v===undefined ? '—' : 'US$ ' + Number(v).toFixed(4);
const tiempoReal = s => s===null || s===undefined ? '—' : (s < 1 ? Math.round(s*1000) + ' ms' : Number(s).toFixed(1) + ' s');
async function cargarEjecucionReal(runId){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.obtener_ejecucion) return;
  const r = await api.obtener_ejecucion(projectPath, runId || null);
  if(!r || !r.ok){ toastError(escHtml((r && r.motivo) || 'No se pudieron leer los resultados de la corrida.')); return; }
  ejecucionReal = r; filterState = 'ALL';
  document.querySelectorAll('#views a[data-v=exec]').forEach(a=>a.classList.remove('off'));
  go('exec');
}
function metaTexto(cumple, conMeta, sinMeta){
  if(cumple===null || cumple===undefined) return `<div class="ks" style="color:var(--mut)">${sinMeta}</div>`;
  return `<div class="ks" style="color:${cumple?'var(--emerald-400)':'var(--amber-400)'}">${I(cumple?'check':'warn','currentColor',12)} ${conMeta}</div>`;
}
function renderExecRealKpis(v){
  const k = v.indicadores, pr = k.pass_rate, cv = k.cobertura, it = k.iteraciones, cs = k.costo;
  const barra = x => Math.max(0, Math.min(100, Number(x) || 0));
  const agentes = Object.entries(cs.por_agente).map(([a, f]) => { const [l, c] = AGENTE_REAL[a] || [a, 'var(--mut)'];
    return `<div class="kscale"><span style="color:${c}" title="${escHtml(a)}">${l}</span><span>${f.tokens.toLocaleString('es-PE')} tok · ${usdReal(f.costo_usd)}</span></div>`; }).join('');
  $('kpis').innerHTML = `
  <div class="kpi"><div class="kh"><span>PASS RATE</span>${I('checkc','var(--emerald-400)',15)}</div>
    <div class="kmid"><div class="kv">${numReal(pr.valor)} <small>${pr.meta===null?'':'/ meta ≥ ' + numReal(pr.meta, 0)}</small></div>
    ${metaTexto(pr.cumple, `${pr.cumple?'Dentro de la meta':'Bajo la meta'} · ${pr.pasaron}/${pr.total} pruebas sin error`, 'Meta no registrada en esta corrida')}</div>
    <div><div class="kb"><i style="width:${barra(pr.valor)}%;background:linear-gradient(90deg,var(--emerald-500),var(--teal-400))"></i></div></div></div>
  <div class="kpi"><div class="kh"><span>COBERTURA CÓDIGO</span>${I('merge','var(--blue-400)',15)}</div>
    <div class="kmid"><div class="kv">${numReal(cv.lineas)} <small>líneas</small></div>
    <div class="ks" style="color:var(--blue-400)">${numReal(cv.ramas)} de ramas</div>
    ${metaTexto(cv.cumple, `Meta ≥ ${numReal(cv.meta_lineas, 0)} de líneas ${cv.cumple?'alcanzada':'no alcanzada'}`, 'Meta no registrada en esta corrida')}</div>
    <div><div class="kb"><i style="width:${barra(cv.lineas)}%;background:var(--blue-500)"></i></div><div class="kb thin"><i style="width:${barra(cv.ramas)}%;background:var(--indigo-400)"></i></div></div></div>
  <div class="kpi"><div class="kh"><span>ITERACIONES PROMEDIO</span>${I('refresh','var(--purple-400)',15)}</div>
    <div class="kmid"><div class="kv">${numReal(it.valor, 2, '')} <small>/ ${it.tope} máx</small></div>
    ${metaTexto(it.cumple, `Meta ≤ ${numReal(it.meta_max, 1, '')} ${it.cumple?'cumplida':'superada'}`, 'Meta no registrada en esta corrida')}</div>
    <div><div class="kb"><i style="width:${barra((it.valor||0)/it.tope*100)}%;background:linear-gradient(90deg,var(--purple-500),var(--indigo-500))"></i></div></div></div>
  <div class="kpi"><div class="kh"><span>TOKENS Y COSTO POR AGENTE</span>${I('coins','var(--amber-400)',15)}</div>
    <div class="kmid"><div class="kv kv2">${usdReal(cs.costo_total_usd)} <small>${cs.tokens_total.toLocaleString('es-PE')} tokens</small></div>
    ${metaTexto(cs.cumple, `Tope por corrida: ${usdReal(cs.tope_usd)} ${cs.cumple?'respetado':'superado'}`, 'Tope no registrado en esta corrida')}</div>
    <div>${agentes}</div></div>
  <div class="kpi"><div class="kh"><span>MUTATION SCORE</span>${I('dna','var(--rose-400)',15)}</div>
    <div class="kmid"><div class="kv" style="color:var(--mut)">—</div>
    <div class="ks" style="color:var(--mut)">${escHtml(k.mutation_score.texto)}</div></div></div>`;
}
function actualizarBarraReal(v){   // barra superior: la corrida que se está mostrando
  const ok = v.estado_final === 'fin';
  $('ctxChip').className = 'chip ' + (ok ? 'done' : 'amber');
  $('ctxLbl').textContent = 'Corrida ' + v.run_id + ':'; $('curFile').textContent = ok ? 'completada' : 'detenida';
  $('progNum').textContent = v.total_funciones + ' funciones revisadas'; $('progBar').style.width = '100%';
  $('liveBtn').className = 'live done'; $('liveTxt').innerHTML = ok ? '✓ COMPLETADO' : 'DETENIDA';
}
function renderExecReal(v){
  actualizarBarraReal(v);
  renderExecRealKpis(v);
  const total = v.modulos.reduce((n, m) => n + m.pruebas.length, 0);
  const botones = [{clave:'ALL', etiqueta:'Todos', cantidad: total}, ...v.filtros];
  $('fbtns').innerHTML = botones.map(f => {
    const color = f.clave==='ALL' ? 'var(--blue-600)' : ST[ESTADO_REAL[f.clave].st].c, activo = filterState===f.clave;
    return `<button class="fb2 ${activo?'on':''}" style="${activo?'background:'+color:''}" onclick="filterState='${f.clave}';renderExec()">${f.clave!=='ALL'?`<i class="fdot" style="background:${color}"></i>`:''}${escHtml(f.etiqueta)} (${Number(f.cantidad)})</button>`;
  }).join('');
  const grupos = v.modulos.map(m => ({modulo: m.modulo, pruebas: m.pruebas.filter(p => filterState==='ALL' || p.estado===filterState)}))
                          .filter(g => g.pruebas.length);
  $('suites').innerHTML = grupos.length ? grupos.map(g => `
    <div class="suite2">
      <div class="sh2"><div class="l">${I('file','var(--blue-400)',15)}<b>${escHtml(g.modulo)}</b><span class="c">(${g.pruebas.length} ${g.pruebas.length===1?'función':'funciones'})</span></div>
        <div class="r"><span>Corrida ${escHtml(v.run_id)}</span>${v.es_simulado?'<span>IA simulada</span>':''}</div></div>
      ${g.pruebas.map(p => { const e = ESTADO_REAL[p.estado], s = ST[e.st].exec;
        const etiqueta = p.estado==='estancado' ? `Estancado ${p.intento_final}/3` + (MOTIVO_ESTANCADO[p.motivo_estancado] ? ` · ${MOTIVO_ESTANCADO[p.motivo_estancado]}` : '') : e.txt;
        return `<div class="fnrow"><div class="fnhead" style="cursor:default">
          <div class="l"><span class="nm">${I(s[0],s[1],16)} test_${escHtml(p.funcion)}()</span>${p.critical?'<span class="bdg b-orc">Crítica</span>':''}</div>
          <div class="r"><span>Intento final: <b style="color:${p.intento_final>1?'var(--amber-400)':'var(--slate-200)'}">${Number(p.intento_final)}/3</b></span>
            <span>${I('clock','var(--slate-300-c)',12)} ${tiempoReal(p.duracion_s)}</span>
            <span>Cov: <b style="color:var(--blue-400)">${numReal(p.cobertura_lineas)}</b> líneas · <b style="color:var(--blue-400)">${numReal(p.cobertura_ramas)}</b> ramas</span>
            <span class="sbdg ${s[2]}">${I(s[3],'currentColor',12)} ${escHtml(etiqueta)}</span></div>
        </div></div>`; }).join('')}
    </div>`).join('') : '<div class="suite2" style="padding:18px;color:var(--mut)">No hay pruebas con ese estado en esta corrida.</div>';
}

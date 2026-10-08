// ejecucion-informe.js — ejecución de pruebas, informe final y exportar
/* ---------------- Ejecución de pruebas ---------------- */
let filterState = 'ALL';
const expanded = {fn_1:true, fn_2:true};
function renderExecKpis(){
  const m = metrics(), passOk = m.pass >= META.pass[0], msOk = m.ms >= META.ms, est = runEstimate;
  $('kpis').innerHTML = `
  <div class="kpi"><div class="kh"><span>PASS RATE</span>${I('checkc','#34d399',15)}</div>
    <div class="kmid"><div class="kv" style="color:${passOk?'#e2e8f0':'#fcd34d'}">${pct(m.pass)} <small>/ ${META.pass[0]}–${META.pass[1]}% meta</small></div>
    <div class="ks" style="color:${passOk?'#34d399':'#fbbf24'}">${I(passOk?'check':'warn','currentColor',12)} ${passOk?'Dentro de la meta':'Bajo la meta'} · ${m.ok}/${m.n} suites sin error</div></div>
    <div><div class="kb"><i style="width:${m.pass}%;background:linear-gradient(90deg,#10b981,#2dd4bf)"></i></div>
    <div class="kscale"><span>0%</span><span class="c">Meta: ${META.pass[0]}%</span><span>100%</span></div></div></div>
  <div class="kpi"><div class="kh"><span>COBERTURA CÓDIGO</span>${I('merge','#60a5fa',15)}</div>
    <div class="kmid"><div class="kv kv2">${pct(m.lines,1)} <small>líneas</small> <em>|</em> <span style="color:#60a5fa">${pct(m.branch,1)}</span> <small>ramas</small></div>
    <div class="ks" style="color:#60a5fa">${I('target','#60a5fa',12)} Meta ≥ ${META.lines}% de líneas ${m.lines>=META.lines?'alcanzada':'no alcanzada'}</div></div>
    <div><div class="kb"><i style="width:${m.lines}%;background:#3b82f6"></i></div><div class="kb thin"><i style="width:${m.branch}%;background:#818cf8"></i></div></div></div>
  <div class="kpi"><div class="kh"><span>ITERACIONES PROMEDIO</span>${I('refresh','#c084fc',15)}</div>
    <div class="kmid"><div class="kv">${m.iter.toFixed(1)} <small>/ 3.0 máx</small></div>
    <div class="ks" style="color:#c084fc">${m.iter<META.iter?'Meta &lt; 2 cumplida':'Sobre la meta de 2'} <b style="color:var(--mut)">(${pct(m.iter/3*100)} del tope)</b></div></div>
    <div><div class="kb"><i style="width:${m.iter/3*100}%;background:linear-gradient(90deg,#a855f7,#6366f1)"></i></div>
    <div class="kscale"><span>1.0</span><span class="c">Tope: 3.0</span></div></div></div>
  <div class="kpi"><div class="kh"><span>TOKENS POR AGENTE</span>${I('coins','#fbbf24',15)}</div>
    <div class="kmid"><div class="kv kv2">${kfmt(m.tokens)} <small>tokens</small></div>
    <div class="ktri"><span style="color:#60a5fa">P: <b>${AGENT_SPLIT.P}%</b></span><span style="color:#c084fc">G: <b>${AGENT_SPLIT.G}%</b></span><span style="color:#34d399">R: <b>${AGENT_SPLIT.R}%</b></span></div></div>
    <div><div class="kb"><i style="width:${AGENT_SPLIT.P}%;background:#3b82f6"></i><i style="width:${AGENT_SPLIT.G}%;background:#a855f7"></i><i style="width:${AGENT_SPLIT.R}%;background:#10b981"></i></div>
    <div class="kscale"><span>$${m.usd.toFixed(2)} USD</span><span>S/ ${m.pen.toFixed(2)} PEN</span></div>
    <div class="kscale" title="Estimación mostrada en la vista previa"><span>Estimado: ~${kfmt(est.tok)}</span><span>S/ ${est.pen.toFixed(2)}</span></div>
    <div class="kscale"><span style="color:#93c5fd">P $${m.agentUsd.P.toFixed(3)}</span><span style="color:#d8b4fe">G $${m.agentUsd.G.toFixed(3)}</span><span style="color:#86efac">R $${m.agentUsd.R.toFixed(3)}</span></div>
    <div class="kscale" style="color:#86efac"><span>♻ 4 specs reutilizados</span><span>Planner omitido</span></div></div></div>
  <div class="kpi"><div class="kh"><span>MUTATION SCORE</span>${I('dna','#fb7185',15)}</div>
    <div class="kmid"><div class="kv" style="color:${msOk?'#e2e8f0':'#fcd34d'}">${pct(m.ms)} <small>/ ${META.ms}% meta</small></div>
    <div class="ks" style="color:#fbbf24">${I('warn','#fbbf24',12)} Brecha activa en ${m.gaps} funciones · solo ${m.crit} críticas</div></div>
    <div><div class="kb"><i style="width:${m.ms}%;background:linear-gradient(90deg,#f59e0b,#f43f5e)"></i></div>
    <div class="kscale"><span>0%</span><span class="c">Meta: ${META.ms}%</span><span>100%</span></div></div></div>`;
}
function renderExec(){
  renderExecKpis();
  const keys = ['ALL', ...Object.keys(ST)];
  $('fbtns').innerHTML = keys.map(k => {
    const n = k==='ALL' ? RUN.length : RUN.filter(f=>f.status===k).length;
    const bg = k==='ALL' ? '#2563eb' : ST[k].c, lbl = k==='ALL' ? 'Todos' : ST[k].filter;
    return `<button class="fb2 ${filterState===k?'on':''}" style="${filterState===k?'background:'+bg:''}" onclick="filterState='${k}';renderExec()">${k!=='ALL'?`<i class="fdot" style="background:${ST[k].c}"></i>`:''}${lbl} (${n})</button>`;
  }).join('');
  const list = RUN.filter(f => filterState==='ALL' || f.status===filterState);
  const groups = {}; list.forEach(x => (groups[x.module] ||= []).push(x));
  $('suites').innerHTML = Object.keys(groups).map(m => `
    <div class="suite2">
      <div class="sh2"><div class="l">${I('file','#60a5fa',15)}<b>${m}</b><span class="c">(${groups[m].length} ${groups[m].length===1?'función':'funciones'} bajo prueba)</span></div>
        <div class="r"><span>${I('shield','#34d399',13)} Strict AST Guard</span><span>Python 3.11</span></div></div>
      ${groups[m].map(fn => { const open = !!expanded[fn.id]; const s = ST[fn.status].exec;
        const audLbl = {clean:['✓ Intactas','#34d399','Fidedigna'], relaxed:['⚠ Relajadas','#fb7185','Relajada'], oracle:['⚠ Oráculo alterado','#e879f9','Valor copiado del código'], weak:['⚠ Débil','#fbbf24','Más laxa que el contrato']}[fn.cmp.state];
        const diagCls = {rejected_laundering:'d-rose', rejected_oracle:'d-fuch', stuck:'d-amber', low_mutation:'d-orange'}[fn.status] || 'd-amber';
        return `<div class="fnrow">
          <div class="fnhead" onclick="expanded['${fn.id}']=!expanded['${fn.id}'];renderExec()">
            <div class="l">${I(open?'chevD':'chevR','#8b9ab4',15)}<span class="nm">${I(s[0],s[1],16)} test_${fn.name}()</span>
              <span class="bdg b-${fn.bv}">${esc(fn.badge)}</span>
              ${fn.status==='rejected_laundering'?'<span class="bdg b-laund">Assertion Laundering detectado</span>':''}
              ${fn.status==='rejected_oracle'?'<span class="bdg b-orc">Posible bug en el código</span>':''}</div>
            <div class="r"><span>Intento: <b style="color:${fn.iterations>1?'#fbbf24':'#e2e8f0'}">${fn.iterations}/3</b></span>
              <span>${I('clock','#8b9ab4',12)} ${fn.time}</span><span>Cov: <b style="color:#60a5fa">${fn.lines_cov}%</b></span>
              <span class="sbdg ${s[2]}">${I(s[3],'currentColor',12)} ${s[4]}</span></div>
          </div>
          ${open ? `<div class="fnbody">
            ${fn.diag ? `<div class="diag ${diagCls}"><b>${I(fn.status==='rejected_oracle'?'bug':fn.status==='rejected_laundering'?'shieldA':'alertc','currentColor',15)} Diagnóstico del Reviewer Agent:</b><p>${esc(fn.diag)}</p></div>` : ''}
            <div class="g2">
              <div class="pn"><div class="pnh"><b>${I('code','#c084fc',13)} Código PyTest (Generator Agent)</b><span>test_${fn.name}.py</span></div><pre>${hl(fn.code)}</pre></div>
              <div style="display:flex;flex-direction:column;gap:16px">
                <div class="pn"><div class="pnh"><b>${I('term','#34d399',13)} Log del Sandbox Aislado (Docker)</b><span style="color:${ranOK(fn)?'#34d399':'#fb7185'};font-size:10px">exit status: ${ranOK(fn)&&fn.status==='passed'?0:1}</span></div>
                  <div class="logs">${fn.logs.map(l=>`<div class="${logCls(l)}">${esc(l)}</div>`).join('')}</div></div>
                <div class="pn"><div class="pnh"><b>${I('shieldC','#60a5fa',13)} Auditoría de Aserciones (AST Diff)</b><b style="color:${audLbl[1]}">${audLbl[0]}</b></div>
                  <div class="aud">
                    <div class="lbl"><span>Aserción de Contrato (Planner)</span><span style="color:#34d399">Esperado estricto</span></div>
                    <div class="bx" style="color:#6ee7b7">${esc(fn.cmp.original)}</div>
                    <div class="lbl" style="padding-top:3px"><span>Aserción Sintetizada (Generator)</span><span style="color:${audLbl[1]};font-weight:700">${audLbl[2]}</span></div>
                    <div class="bx ${fn.cmp.state==='clean'?'':'bad'}" style="${fn.cmp.state==='oracle'?'border-color:#a21caf;color:#f0abfc;background:rgba(74,4,78,.35)':fn.cmp.state==='weak'?'border-color:#b45309;color:#fcd34d;background:rgba(69,26,3,.35)':''}">${esc(fn.cmp.modified)}</div>
                  </div></div>
              </div>
            </div></div>` : ''}
        </div>`; }).join('')}
    </div>`).join('');
}
function logCls(l){ return l.includes('PASSED')?'lg-ok':(l.includes('REJECT')||l.includes('FAILED')||l.includes('ERROR'))?'lg-err':(l.includes('DIFF')||l.includes('WARNING')||l.includes('ORACLE'))?'lg-diff':'lg-n'; }

/* ---------------- Reporte Final ---------------- */
const rExpanded = {fn_3:true, fn_1:true, fn_4:true, fn_2:false};
const rTabs = {fn_3:'checklist', fn_1:'contract', fn_4:'test', fn_2:'checklist'};
let rFilter = 'ALL';
function jsonHL(obj){
  return JSON.stringify(obj, null, 2).split('\n').map(line => {
    const m = line.match(/^(\s*)(".*?")(\s*:\s*)(.*)$/);
    return m ? `<div><span style="color:#475569">${m[1]}</span><span class="jk">${esc(m[2])}</span><span style="color:#94a3b8">${m[3]}</span><span class="jv">${esc(m[4])}</span></div>` : `<div style="color:#cbd5e1">${esc(line)}</div>`;
  }).join('');
}
function chk(state, label, okTxt, badTxt, icoOk, icoBad, badCls='bad', wide=false){
  if(state===null) return `<div class="ck na${wide?' wide':''}"><div class="cl">${I('alertc','currentColor',15)}<span>${label}</span></div><span class="ct">— NO APLICA (función no crítica)</span></div>`;
  return `<div class="ck ${state?'ok':badCls}${wide?' wide':''}"><div class="cl">${I(state?icoOk:icoBad,'currentColor',15)}<span>${label}</span></div><span class="ct">${state?okTxt:badTxt}</span></div>`;
}
function renderReport(){
  const m = metrics();
  $('rmeta').innerHTML = `Corrida <b>#${RUN_ID}</b> · ${RUN_DATE} · perfil <b>Profundo</b> · ${m.n} funciones · rama <b>${$('branchLbl').textContent}</b><br><span style="font-size:11px">Modelos: Planner · ${AGENTS_CFG.P.model} &nbsp;|&nbsp; Generator · ${AGENTS_CFG.G.model} &nbsp;|&nbsp; Reviewer · ${AGENTS_CFG.R.model}</span>`;
  
  $('pillars').innerHTML = `
    <div class="pil"><div class="pt">${I('check','#34d399',12)}Pass Rate Final</div><div class="pv" style="color:${m.pass>=META.pass[0]?'#34d399':'#fcd34d'}">${pct(m.pass)}</div><div class="ps">${m.ok}/${m.n} suites sin error · meta ${META.pass[0]}%</div></div>
    <div class="pil"><div class="pt">${I('merge','#60a5fa',12)}Cobertura Total</div><div class="pv" style="color:#60a5fa;font-size:19px">${pct(m.lines,1)} <small>/ ${pct(m.branch,1)}</small></div><div class="ps">Líneas / Ramas</div></div>
    <div class="pil"><div class="pt">${I('coins','#fbbf24',12)}Costo Tokens</div><div class="pv" style="color:#fcd34d;font-size:18px">S/ ${m.pen.toFixed(2)} <small>PEN</small></div><div class="ps">$${m.usd.toFixed(2)} USD • ${kfmt(m.tokens)} tok</div></div>
    <div class="pil"><div class="pt">${I('shieldA','#fb7185',12)}Balance Global</div><div class="pv" style="font-size:19px"><span style="color:#34d399">${m.green} OK</span> <span style="color:#475569">/</span> <span style="color:#fb7185">${m.alerts} Alert</span></div><div class="ps" style="color:#fb7185">${m.critical_incidents} incidentes críticos · ${m.bugs} posible bug</div></div>`;
  const FL = [['ALL',`Todas (${m.n})`,'#2563eb'],['PASSED',`En Verde (${m.green})`,'#059669'],['ISSUES',`Incidentes / Anomalías (${m.alerts})`,'#e11d48']];
  $('rfbtns').innerHTML = FL.map(([k,n,c]) => `<button class="fb2 ${rFilter===k?'on':''}" style="${rFilter===k?'background:'+c:''}" onclick="rFilter='${k}';renderReport()">${n}</button>`).join('');
  $('legend2').innerHTML = Object.values(ST).map(s => `<span><i style="background:${s.c}"></i> ${s.filter}</span>`).join('');
  const list = RUN.filter(f => rFilter==='ALL' || (rFilter==='PASSED' ? f.status==='passed' : f.status!=='passed'));
  $('rcards').innerHTML = list.map(fn => {
    const st = ST[fn.status], open = !!rExpanded[fn.id], tab = rTabs[fn.id] || 'contract', warnSt = fn.status!=='passed';
    const badge = fn.status==='low_mutation' ? `${st.rep} (${fn.mutation_score}%)` : st.rep;
    let body = '';
    if(open){
      const tabs = [['contract','file','1. Contrato JSON (Planner)','#60a5fa'],['test','code','2. Test Generado (Pytest)','#c084fc'],['checklist','check','3. Checklist de Verificación','#34d399']];
      body = `<div class="rbody"><div class="rtabs">${tabs.map(([k,ic,n,c]) => `<button class="${tab===k?'on':''}" style="${tab===k?`color:${c};border-color:${c}`:''}" onclick="event.stopPropagation();rTabs['${fn.id}']='${k}';renderReport()">${I(ic,'currentColor',14)} ${n}</button>`).join('')}</div>`;
      if(tab==='contract') body += `<div class="rhd"><span>${I('code','#60a5fa',14)} Especificación de comportamiento inferida del AST y type-hints:</span><span class="rtag" style="color:#60a5fa;background:rgba(23,37,84,.6);border-color:rgba(30,64,175,.4)">schema: planner.contract.v2</span></div><div class="rcode json">${jsonHL(fn.contract)}</div>`;
      if(tab==='test') body += `<div class="rhd"><span>${I('term','#c084fc',14)} Suite de pruebas sintetizada por el Generator Agent:</span><span class="rtag" style="color:#c084fc;background:rgba(59,7,100,.6);border-color:rgba(107,33,168,.4)">runtime: pytest 7.4.x • pytest-cov</span></div><pre class="rcode">${hl(fn.code)}</pre>`
        + (fn.trace ? `<div class="rerr"><b>${I('warn','#fb7185',15)} Traza de Fallo durante la ejecución:</b><pre>${esc(fn.trace)}</pre></div>` : '');
      if(tab==='checklist') body += `<div class="rhd"><span>Verificaciones obligatorias de aceptación en sandbox hermético:</span><span style="color:#34d399">5 controles de integridad</span></div>
        <div class="cks">
          ${chk(fn.checks.syntax,'Compiló sin errores de sintaxis','☑️ OK','❌ FALLÓ','checkc','xc')}
          ${chk(fn.checks.sandbox,'Ejecutó en sandbox sin errores de entorno','☑️ OK','❌ FALLÓ ENTORNO','checkc','alertc')}
          ${chk(fn.checks.assertions_intact, fn.status==='rejected_oracle'?'Oráculo trazable al contrato (Anti-Laundering)':'Aserciones no relajadas (Anti-Laundering)','☑️ INTACTAS', fn.status==='rejected_oracle'?'⚠️ RECHAZADO: VALOR COPIADO DEL CÓDIGO':'⚠️ RECHAZADO: DIFF DETECTADO','shieldC','shieldA','bad strong')}
          ${chk(fn.checks.cov_met,`Cobertura líneas (${fn.lines_cov}%) y ramas (${fn.branch_cov}%) ≥ ${META.lines}%`,'☑️ UMBRAL CUBIERTO','❌ DEFICITARIO','checkc','xc')}
          ${chk(fn.checks.ms_met, fn.critical?`Mutation Score ≥ ${META.ms}% (obtenido: ${fn.mutation_score}%)`:'Mutation Score (mutmut)','☑️ SOBRE LA META','⚠️ MUTANTES SOBREVIVIERON · BAJO LA META','dna','warn','orange',true)}
        </div>` + (fn.trace ? `<div class="raud"><div class="rhd" style="margin:0 0 8px"><b style="color:#fb7185;display:flex;gap:8px;align-items:center">${I('term','#fb7185',14)} Traza de auditoría del Reviewer (Iteración ${fn.iterations}/3):</b><span class="rtag" style="color:#fda4af;background:#4c0519;border-color:#9f1239">SANDBOX_LOG_STDERR</span></div><pre>${esc(fn.trace)}</pre></div>` : '');
      body += '</div>';
    }
    return `<div class="rcard" style="border-left-color:${st.c};${warnSt?`box-shadow:0 0 0 1px ${st.c}33`:''}">
      <div class="rch" onclick="rExpanded['${fn.id}']=!rExpanded['${fn.id}'];renderReport()">
        <div class="l"><span class="mtag" style="${st.mb}">${fn.methodTag}</span>
          <div style="min-width:0"><div class="rn">${fn.name}() <span class="rmod">${fn.module}</span>${fn.critical?'<span class="rcrit">★ crítica</span>':''}</div><div class="rsig">${esc(fn.signature)}</div></div></div>
        <div class="r"><span class="rpill"><span style="color:var(--mut)">Cob:</span> <b style="color:#60a5fa">${fn.lines_cov}%</b></span>
          <span class="rpill" title="${fn.critical?'mutmut sobre función crítica':'No aplica: mutmut solo corre sobre funciones críticas'}"><span style="color:var(--mut)">Mutantes:</span> <b style="color:${fn.mutation_score===null?'var(--mut)':fn.mutation_score<META.ms?'#fb7185':'#34d399'}">${fn.mutation_score===null?'N/A':fn.mutation_score+'%'}</b></span>
          <span class="rsb ${st.repCls} ${fn.status==='rejected_laundering'?'pulse':''}">${I(st.repIco,'currentColor',13)} ${badge}</span>${I(open?'chevU':'chevD','#8b9ab4',20)}</div>
      </div>${body}</div>`;
  }).join('');
}

/* ---------------- Exportar informe ---------------- */
let expFmt = 'pdf';
function openExport(){
  $('expPath').value = projectPath + '\\.pyagent\\runs\\' + RUN_ID + '\\';
  setFmt(expFmt); openModal('m-export');
}
function setFmt(f){
  expFmt = f;
  document.querySelectorAll('.fmt').forEach(e => e.classList.toggle('on', e.dataset.f===f));
  $('expName').textContent = {pdf:`informe_${RUN_ID}.pdf`, md:`informe_${RUN_ID}.md`, json:`results_${RUN_ID}.json`}[f];
  document.querySelectorAll('.expOpt').forEach(e => e.disabled = f==='json');
}
function buildMarkdown(){
  const m = metrics(), inc = id => $(id).checked, ok = b => b ? '✅ Cumple' : '❌ No cumple';
  let md = `# Informe de auditoría de pruebas unitarias — Corrida #${RUN_ID}\n\n`;
  md += `- **Proyecto:** ${document.querySelector('.repoLbl').textContent}\n- **Rama:** ${$('branchLbl').textContent}\n- **Fecha:** ${RUN_DATE}\n- **Perfil:** Profundo · **Funciones evaluadas:** ${m.n} (${m.crit} críticas)\n- **Generado por:** PyAgent v2.4 (Planner → Generator → Reviewer)\n- **Modelos:** Planner: ${AGENTS_CFG.P.model} (US$ ${AGENTS_CFG.P.price}/M) · Generator: ${AGENTS_CFG.G.model} (US$ ${AGENTS_CFG.G.price}/M) · Reviewer: ${AGENTS_CFG.R.model} (US$ ${AGENTS_CFG.R.price}/M)\n- **Specs:** 4 reutilizados de corridas anteriores · 2 regenerados (cart.py, discounts.py cambiaron) · guardados en \`.pyagent/specs/\`\n\n`;
  md += `## 1. Resumen de métricas\n\n| Métrica | Resultado | Meta (carta) | Estado |\n|---|---|---|---|\n`;
  md += `| Pass Rate | ${pct(m.pass,1)} (${m.ok}/${m.n}) | ${META.pass[0]}–${META.pass[1]}% | ${ok(m.pass>=META.pass[0])} |\n`;
  md += `| Cobertura de líneas / ramas | ${pct(m.lines,1)} / ${pct(m.branch,1)} | ≥ ${META.lines}% líneas | ${ok(m.lines>=META.lines)} |\n`;
  md += `| Iteraciones promedio | ${m.iter.toFixed(2)} | < ${META.iter} (máx. 3) | ${ok(m.iter<META.iter)} |\n`;
  md += `| Tokens (P ${AGENT_SPLIT.P}% · G ${AGENT_SPLIT.G}% · R ${AGENT_SPLIT.R}%) | ${m.tokens.toLocaleString('es-PE')} · US$ ${m.usd.toFixed(2)} · S/ ${m.pen.toFixed(2)} | Reportar | ✅ Reportado |\n`;
  md += `| Costo por agente | Planner US$ ${m.agentUsd.P.toFixed(3)} · Generator US$ ${m.agentUsd.G.toFixed(3)} · Reviewer US$ ${m.agentUsd.R.toFixed(3)} | — | ✅ Reportado |\n`;
  md += `| Mutation Score (solo ${m.crit} funciones críticas) | ${pct(m.ms,1)} | ≥ ${META.ms}% | ${ok(m.ms>=META.ms)} |\n\n`;
  if(inc('expDetail')){
    md += `## 2. Resultado por función\n\n| Función | Módulo | Estado | Intentos | Cob. líneas | Cob. ramas | Mutation Score | Tokens |\n|---|---|---|---|---|---|---|---|\n`;
    RUN.forEach(f => md += `| ${f.name} | ${f.module} | ${ST[f.status].rep} | ${f.iterations}/3 | ${f.lines_cov}% | ${f.branch_cov}% | ${f.mutation_score===null?'N/A (no crítica)':f.mutation_score+'%'} | ${f.tokens.toLocaleString('es-PE')} |\n`);
    md += `\n`;
  }
  md += `## 3. Incidentes\n\n`;
  RUN.filter(f=>f.diag).forEach(f => {
    md += `### ${f.name} — ${ST[f.status].rep}\n\n${f.diag}\n\n`;
    if(inc('expTrace') && f.trace) md += '```text\n' + f.trace + '\n```\n\n';
  });
  if(inc('expCode')){ md += `## 4. Pruebas generadas\n\n`; RUN.forEach(f => md += `### tests/test_${f.name}.py\n\n\`\`\`python\n${f.code}\n\`\`\`\n\n`); }
  if(inc('expContract')){ md += `## 5. Contratos del Planner\n\n`; RUN.forEach(f => md += `### ${f.name}\n\n\`\`\`json\n${JSON.stringify(f.contract,null,2)}\n\`\`\`\n\n`); }
  return md;
}
function download(name, text, type){
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text],{type})); a.download = name; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href), 1000);
}
function doExport(){
  const name = $('expName').textContent, path = $('expPath').value + name;
  if(expFmt==='md') download(name, buildMarkdown(), 'text/markdown');
  if(expFmt==='json') download(name, JSON.stringify({run_id:RUN_ID, date:RUN_DATE, metrics:metrics(), functions:RUN.map(({code,logs,cmp,diag,trace,...r})=>r)}, null, 2), 'application/json');
  closeModal();
  toast(expFmt==='pdf' ? `Informe PDF guardado en ${path} <span style="color:var(--dim)">(simulado en el demo)</span>` : `Informe guardado en ${path} <span style="color:var(--dim)">(el demo lo descarga en tu navegador)</span>`);
}
function toast(html, icono = I('checkc','#34d399',16), ms = 5200){ const t = $('toast'); t.innerHTML = icono + '<span>' + html + '</span>'; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(()=>t.classList.remove('show'), ms); }
function toastError(html){ toast(html, I('alertc','#f87171',16), 8000); }


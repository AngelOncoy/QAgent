// informe.js — pantalla del informe final de la corrida
// HTML del componente (se monta en el marcador data-componente="informe/informe" de index.html)
registrarComponente('informe/informe', `<!-- ===== 6. REPORTE FINAL (según tu diseño React; sin referencias a Swagger/HTTP) ===== -->
<section id="s-report" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <div class="scroll"><div class="repwrap">
    <div class="ractions"><span id="rmeta"></span>
      <button class="btn" onclick="toast('En la app de escritorio se abre la carpeta '+projectPath+'\\\\.pyagent\\\\runs\\\\'+RUN_ID+' <span style=&quot;color:var(--dim)&quot;>(simulado)</span>')"><span class="ico" data-i="folder" data-c="var(--slate-300-c)"></span> Abrir carpeta de la corrida</button>
      <button class="btn primary" onclick="openExport()"><span class="ico" data-i="download" data-c="var(--white)"></span> Exportar informe</button></div>
    <div class="banner2">
      <div class="glow"></div>
      <div class="bl">
        <div class="brow"><span class="bbadge"><span class="ico" data-i="award" data-c="var(--emerald-400)"></span>INFORME EJECUTIVO DE ASEGURAMIENTO DE CALIDAD</span><span class="bmeta">QAgent Engine v2.4 • Run #8841-B</span></div>
        <h2>Auditoría de Suites de Prueba &amp; Mitigación de Vulnerabilidades de Código</h2>
        <p>Consolidado formal generado tras la ejecución de los agentes <span style="color:var(--blue-400)">Planner (AST)</span>, <span style="color:var(--purple-400)">Generator (Pytest)</span> y <span style="color:var(--emerald-400)">Reviewer (Sandbox &amp; Anti-Laundering)</span>. Verificación estricta de contratos inmutables, aislamiento de mocks y detección de relajación de aserciones.</p>
      </div>
      <div class="pillars" id="pillars"></div>
    </div>

    <div class="toolbar">
      <div class="tleft"><span class="flbl" style="font-weight:600">Filtro de inspección:</span><div id="rfbtns" style="display:flex;gap:6px;flex-wrap:wrap"></div></div>
      <div class="legend2" id="legend2"></div>
    </div>
    <div id="rcards" style="display:flex;flex-direction:column;gap:16px"></div>
  </div></div>
</section>
`);

/* ---------------- Reporte Final ---------------- */
const rExpanded = {fn_3:true, fn_1:true, fn_4:true, fn_2:false};
const rTabs = {fn_3:'checklist', fn_1:'contract', fn_4:'test', fn_2:'checklist'};
let rFilter = 'ALL';
function jsonHL(obj){
  return JSON.stringify(obj, null, 2).split('\n').map(line => {
    const m = line.match(/^(\s*)(".*?")(\s*:\s*)(.*)$/);
    return m ? `<div><span style="color:var(--slate-600)">${m[1]}</span><span class="jk">${esc(m[2])}</span><span style="color:var(--slate-400)">${m[3]}</span><span class="jv">${esc(m[4])}</span></div>` : `<div style="color:var(--slate-300)">${esc(line)}</div>`;
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
    <div class="pil"><div class="pt">${I('check','var(--emerald-400)',12)}Pass Rate Final</div><div class="pv" style="color:${m.pass>=META.pass[0]?'var(--emerald-400)':'var(--amber-300)'}">${pct(m.pass)}</div><div class="ps">${m.ok}/${m.n} suites sin error · meta ${META.pass[0]}%</div></div>
    <div class="pil"><div class="pt">${I('merge','var(--blue-400)',12)}Cobertura Total</div><div class="pv" style="color:var(--blue-400);font-size:19px">${pct(m.lines,1)} <small>/ ${pct(m.branch,1)}</small></div><div class="ps">Líneas / Ramas</div></div>
    <div class="pil"><div class="pt">${I('coins','var(--amber-400)',12)}Costo Tokens</div><div class="pv" style="color:var(--amber-300);font-size:18px">S/ ${m.pen.toFixed(2)} <small>PEN</small></div><div class="ps">$${m.usd.toFixed(2)} USD • ${kfmt(m.tokens)} tok</div></div>
    <div class="pil"><div class="pt">${I('shieldA','var(--rose-400)',12)}Balance Global</div><div class="pv" style="font-size:19px"><span style="color:var(--emerald-400)">${m.green} OK</span> <span style="color:var(--slate-600)">/</span> <span style="color:var(--rose-400)">${m.alerts} Alert</span></div><div class="ps" style="color:var(--rose-400)">${m.critical_incidents} incidentes críticos · ${m.bugs} posible bug</div></div>`;
  const FL = [['ALL',`Todas (${m.n})`,'var(--blue-600)'],['PASSED',`En Verde (${m.green})`,'var(--emerald-600)'],['ISSUES',`Incidentes / Anomalías (${m.alerts})`,'var(--rose-600)']];
  $('rfbtns').innerHTML = FL.map(([k,n,c]) => `<button class="fb2 ${rFilter===k?'on':''}" style="${rFilter===k?'background:'+c:''}" onclick="rFilter='${k}';renderReport()">${n}</button>`).join('');
  $('legend2').innerHTML = Object.values(ST).map(s => `<span><i style="background:${s.c}"></i> ${s.filter}</span>`).join('');
  const list = RUN.filter(f => rFilter==='ALL' || (rFilter==='PASSED' ? f.status==='passed' : f.status!=='passed'));
  $('rcards').innerHTML = list.map(fn => {
    const st = ST[fn.status], open = !!rExpanded[fn.id], tab = rTabs[fn.id] || 'contract', warnSt = fn.status!=='passed';
    const badge = fn.status==='low_mutation' ? `${st.rep} (${fn.mutation_score}%)` : st.rep;
    let body = '';
    if(open){
      const tabs = [['contract','file','1. Contrato JSON (Planner)','var(--blue-400)'],['test','code','2. Test Generado (Pytest)','var(--purple-400)'],['checklist','check','3. Checklist de Verificación','var(--emerald-400)']];
      body = `<div class="rbody"><div class="rtabs">${tabs.map(([k,ic,n,c]) => `<button class="${tab===k?'on':''}" style="${tab===k?`color:${c};border-color:${c}`:''}" onclick="event.stopPropagation();rTabs['${fn.id}']='${k}';renderReport()">${I(ic,'currentColor',14)} ${n}</button>`).join('')}</div>`;
      if(tab==='contract') body += `<div class="rhd"><span>${I('code','var(--blue-400)',14)} Especificación de comportamiento inferida del AST y type-hints:</span><span class="rtag" style="color:var(--blue-400);background:var(--blue-950-a60);border-color:var(--blue-800-a40)">schema: planner.contract.v2</span></div><div class="rcode json">${jsonHL(fn.contract)}</div>`;
      if(tab==='test') body += `<div class="rhd"><span>${I('term','var(--purple-400)',14)} Suite de pruebas sintetizada por el Generator Agent:</span><span class="rtag" style="color:var(--purple-400);background:var(--purple-950-a60);border-color:var(--purple-800-a40)">runtime: pytest 7.4.x • pytest-cov</span></div><pre class="rcode">${hl(fn.code)}</pre>`
        + (fn.trace ? `<div class="rerr"><b>${I('warn','var(--rose-400)',15)} Traza de Fallo durante la ejecución:</b><pre>${esc(fn.trace)}</pre></div>` : '');
      if(tab==='checklist') body += `<div class="rhd"><span>Verificaciones obligatorias de aceptación en sandbox hermético:</span><span style="color:var(--emerald-400)">5 controles de integridad</span></div>
        <div class="cks">
          ${chk(fn.checks.syntax,'Compiló sin errores de sintaxis','☑️ OK','❌ FALLÓ','checkc','xc')}
          ${chk(fn.checks.sandbox,'Ejecutó en sandbox sin errores de entorno','☑️ OK','❌ FALLÓ ENTORNO','checkc','alertc')}
          ${chk(fn.checks.assertions_intact, fn.status==='rejected_oracle'?'Oráculo trazable al contrato (Anti-Laundering)':'Aserciones no relajadas (Anti-Laundering)','☑️ INTACTAS', fn.status==='rejected_oracle'?'⚠️ RECHAZADO: VALOR COPIADO DEL CÓDIGO':'⚠️ RECHAZADO: DIFF DETECTADO','shieldC','shieldA','bad strong')}
          ${chk(fn.checks.cov_met,`Cobertura líneas (${fn.lines_cov}%) y ramas (${fn.branch_cov}%) ≥ ${META.lines}%`,'☑️ UMBRAL CUBIERTO','❌ DEFICITARIO','checkc','xc')}
          ${chk(fn.checks.ms_met, fn.critical?`Mutation Score ≥ ${META.ms}% (obtenido: ${fn.mutation_score}%)`:'Mutation Score (mutmut)','☑️ SOBRE LA META','⚠️ MUTANTES SOBREVIVIERON · BAJO LA META','dna','warn','orange',true)}
        </div>` + (fn.trace ? `<div class="raud"><div class="rhd" style="margin:0 0 8px"><b style="color:var(--rose-400);display:flex;gap:8px;align-items:center">${I('term','var(--rose-400)',14)} Traza de auditoría del Reviewer (Iteración ${fn.iterations}/3):</b><span class="rtag" style="color:var(--rose-300);background:var(--rose-950);border-color:var(--rose-800)">SANDBOX_LOG_STDERR</span></div><pre>${esc(fn.trace)}</pre></div>` : '');
      body += '</div>';
    }
    return `<div class="rcard" style="border-left-color:${st.c};${warnSt?`box-shadow:0 0 0 1px ${st.halo}`:''}">
      <div class="rch" onclick="rExpanded['${fn.id}']=!rExpanded['${fn.id}'];renderReport()">
        <div class="l"><span class="mtag" style="${st.mb}">${fn.methodTag}</span>
          <div style="min-width:0"><div class="rn">${fn.name}() <span class="rmod">${fn.module}</span>${fn.critical?'<span class="rcrit">★ crítica</span>':''}</div><div class="rsig">${esc(fn.signature)}</div></div></div>
        <div class="r"><span class="rpill"><span style="color:var(--mut)">Cob:</span> <b style="color:var(--blue-400)">${fn.lines_cov}%</b></span>
          <span class="rpill" title="${fn.critical?'mutmut sobre función crítica':'No aplica: mutmut solo corre sobre funciones críticas'}"><span style="color:var(--mut)">Mutantes:</span> <b style="color:${fn.mutation_score===null?'var(--mut)':fn.mutation_score<META.ms?'var(--rose-400)':'var(--emerald-400)'}">${fn.mutation_score===null?'N/A':fn.mutation_score+'%'}</b></span>
          <span class="rsb ${st.repCls} ${fn.status==='rejected_laundering'?'pulse':''}">${I(st.repIco,'currentColor',13)} ${badge}</span>${I(open?'chevU':'chevD','var(--slate-300-c)',20)}</div>
      </div>${body}</div>`;
  }).join('');
}

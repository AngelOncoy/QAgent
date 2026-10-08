// ejecucion.js — pantalla de ejecución de pruebas: KPIs, filtros y detalle por función
// HTML del componente (se monta en el marcador data-componente="ejecucion/ejecucion" de index.html)
registrarComponente('ejecucion/ejecucion', `<!-- ===== 5. EJECUCIÓN DE PRUEBAS (según tu diseño en React) ===== -->
<section id="s-exec" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <div class="scroll"><div class="execwrap">
    <div class="kpis" id="kpis"></div>

    <div class="toolbar">
      <div class="tleft"><span class="flbl"><span class='ico' data-i='filter' data-c='#8b9ab4'></span> Filtrar:</span><div id="fbtns"></div></div>
      <div class="cmd2"><span class='ico' data-i='term' data-c='#60a5fa'></span> docker run --rm --network none pyagent-sandbox:base pytest -v --cov --cov-branch</div>
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

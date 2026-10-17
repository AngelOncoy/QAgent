// informe.js — pantalla del informe final de la corrida
// HTML del componente (se monta en el marcador data-componente="informe/informe" de index.html)
registrarComponente('informe/informe', `<!-- ===== 6. REPORTE FINAL (según tu diseño React; sin referencias a Swagger/HTTP) ===== -->
<section id="s-report" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <div class="scroll"><div class="repwrap">
    <div class="ractions"><span id="rmeta"></span>
      <button class="btn" onclick="abrirCarpetaCorrida()"><span class="ico" data-i="folder" data-c="var(--slate-300-c)"></span> Abrir carpeta de la corrida</button>
      <button class="btn primary" onclick="openExport()"><span class="ico" data-i="download" data-c="var(--white)"></span> Exportar informe</button></div>
    <div class="banner2">
      <div class="glow"></div>
      <div class="bl">
        <div class="brow"><span class="bbadge"><span class="ico" data-i="award" data-c="var(--emerald-400)"></span>INFORME EJECUTIVO DE ASEGURAMIENTO DE CALIDAD</span><span class="bmeta">QAgent Engine</span></div>
        <h2>Auditoría de Suites de Prueba &amp; Mitigación de Vulnerabilidades de Código</h2>
        <p>Consolidado formal generado tras la ejecución de los agentes <span style="color:var(--blue-400)">Planner (AST)</span>, <span style="color:var(--purple-400)">Generator (Pytest)</span> y <span style="color:var(--emerald-400)">Reviewer (Sandbox &amp; Anti-Laundering)</span>. Verificación estricta de contratos inmutables, aislamiento de mocks y detección de relajación de aserciones.</p>
      </div>
      <div class="pillars" id="pillars"></div>
    </div>

    <div id="rentorno"></div>

    <div class="toolbar">
      <div class="tleft"><span class="flbl" style="font-weight:600">Tipo:</span><div id="rtypebtns" style="display:flex;gap:6px;flex-wrap:wrap"></div><span class="flbl">Resultado:</span><div id="rfbtns" style="display:flex;gap:6px;flex-wrap:wrap"></div></div>
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
  if (typeof desbloquearVista === 'function') {
    desbloquearVista('report');
    desbloquearVista('history');
  }
  modoReporte(!!reporteReal);
  if (reporteReal) { renderReportReal(reporteReal); return; }   // corrida real (HU-21)
  $('rentorno').innerHTML = '';   // la demostración no tiene datos de ejecución reales
  const m = metrics();
  $('rtypebtns').innerHTML = `<button class="fb2 on" style="background:var(--blue-600)">Funciones (${m.n})</button>`;
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
    const badge = fn.status==='low_mutation' ? `${st.rep} (${fn.mutation_score}%)` : stRep(fn);
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

/* ---------------- Reporte de auditoría de una corrida real (HU-21) ----------------
   Todo viene de obtener_reporte() de Python: las cifras y los controles de results.json,
   y el contrato, el test y la traza de detalle.json. Aquí no se calcula ninguna cifra. */
let reporteReal = null;
const rRealAbierto = {}, rRealTab = {};
let rTypeFilter = 'todos';
const ESTADO_REP = {   // estado de la función -> estilos del catálogo ST y texto de la etiqueta
  aprobado:{st:'passed', txt:'APROBADO'},
  bug_detectado:{st:'rejected_oracle', txt:'BUG DETECTADO'},
  requiere_corrida_nueva:{st:'stuck', txt:'REQUIERE CORRIDA NUEVA'},
  rechazado_laundering:{st:'rejected_laundering', txt:'RECHAZADO: LAUNDERING'},
  estancado:{st:'stuck', txt:'ESTANCADO'},
  sin_veredicto:{st:'stuck', txt:'SIN VEREDICTO'},
};
const CONTROL_REP = {   // estado del control -> clase, ícono y texto
  ok:['ok','checkc','☑️ OK'], falla:['bad','xc','❌ NO CUMPLE'], no_aplica:['na','alertc','— NO APLICA'],
  pendiente:['na','alertc','… PENDIENTE'], sin_dato:['na','alertc','— SIN DATO'],
};
const AGENTES_REP = [['planner','Planner'],['generator','Generator'],['reviewer','Reviewer']];
const numRep = (v, d=1) => v===null || v===undefined ? '—' : Number(v).toFixed(d) + '%';
let bmetaDemo = null;
function modoReporte(real){   // la carpeta simulada de la demo se oculta en una corrida real; exportar informe queda activo (HU-22)
  document.querySelectorAll('#s-report .ractions .btn:not(.primary)').forEach(b => b.classList.toggle('hide', real));
  const bm = document.querySelector('#s-report .bmeta'); if(!bm) return;
  if(bmetaDemo===null) bmetaDemo = bm.textContent;
  bm.textContent = (real && reporteReal) ? 'Corrida #' + reporteReal.run_id + (reporteReal.es_simulado ? ' · IA simulada' : '') : 'QAgent Engine ' + textoVersion();
}
let cargandoReporte = false;
async function cargarReporteReal(runId = null, navegar = true){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.obtener_reporte) return;
  if(cargandoReporte) return;
  cargandoReporte = true;
  try {
    const r = await api.obtener_reporte(projectPath, runId || null);
    if(!r || !r.ok){
      if (typeof toastError === 'function') toastError(escHtml((r && r.motivo) || 'No se pudo leer el reporte de la corrida.'));
      return;
    }
    reporteReal = r; rFilter = 'todas'; rTypeFilter = 'todos';
    if (typeof desbloquearVista === 'function') {
      desbloquearVista('report');
      desbloquearVista('history');
    }
    document.querySelectorAll('#views a[data-v=report]').forEach(a=>a.classList.remove('off'));
    if (navegar) {
      go('report');
    } else {
      renderReportReal(r);
    }
  } finally {
    cargandoReporte = false;
  }
}
function contratoRealHtml(f){
  if(!f.contrato) return `<div class="rhd"><span style="color:var(--mut)">Esta corrida no guardó el contrato (fue anterior al reporte de auditoría).</span></div>`;
  let html = `<div class="rhd"><span>${I('code','var(--blue-400)',14)} ${f.tipo==='endpoint'?'Petición y respuesta esperada definidas por el Planner:':'Casos y valores esperados definidos por el Planner:'}</span><span class="rtag" style="color:var(--blue-400);background:var(--blue-950-a60);border-color:var(--blue-800-a40)">planner_contract.v2</span></div>`;
  if(f.tipo==='endpoint' && f.contrato_http){
    html += `<div class="httpcases">${f.contrato_http.casos.map(c => `<section class="httpcase"><div class="httpcase-title"><b>${escHtml(c.id || 'Caso sin id')}</b>${c.categoria?`<span class="rkind">${escHtml(NOMBRE_CATEGORIA[c.categoria] || c.categoria)}</span>`:''}${c.descripcion?`<span>${escHtml(c.descripcion)}</span>`:''}</div><div class="httpgrid"><div><h5>Petición preparada</h5><div class="rcode json">${jsonHL(c.peticion)}</div></div><div><h5>Respuesta esperada</h5><div class="rcode json">${jsonHL(c.respuesta_esperada)}</div></div></div><div class="httporigin">Origen del oráculo: ${escHtml(c.origen || 'sin dato')}</div></section>`).join('')}</div>`;
  } else {
    html += `<div class="rcode json">${jsonHL(f.contrato)}</div>`;
  }
  return html;
}
/* ---------------- Casos de pytest y datos de la ejecución (EN-17) ---------------- */
const RES_CASO = {   // resultado del caso -> clase, ícono y texto
  paso:['ok','checkc','PASÓ'], fallo:['bad','xc','FALLÓ'], error:['bad','alertc','ERROR'], omitido:['na','alertc','OMITIDO'],
};
const DECISION_INTENTO = {   // decisión del Reviewer en un intento -> clase de la etiqueta y texto
  accept:['rs-ok','ACEPTADO'], retry:['rs-stk','REINTENTO'], bug_detectado:['rs-rej','BUG DETECTADO'], stalled:['rs-stk','ESTANCADO'],
};
const rRealCaso = {}, rRealIntento = {};
const segRep = s => (s===null || s===undefined) ? '—' : Number(s).toFixed(2) + ' s';

function filaFalloHtml(c){
  const pila = (c.pila || []).map(m => `<div class="rfr"><span class="rloc">${escHtml(m.archivo)}:${Number(m.linea)}</span>${m.detalle?`<span class="rdet">${escHtml(m.detalle)}</span>`:''}${m.codigo?`<code>${escHtml(m.codigo)}</code>`:''}</div>`).join('');
  const valores = (c.esperado!==null && c.esperado!==undefined) || (c.obtenido!==null && c.obtenido!==undefined)
    ? `<div class="rvals"><div class="rexp"><h5>Esperado</h5><pre>${escHtml(c.esperado ?? '—')}</pre></div><div class="robt"><h5>Obtenido${c.operador && c.operador!=='==' ? ' (condición: '+escHtml(c.operador)+')' : ''}</h5><pre>${escHtml(c.obtenido ?? '—')}</pre></div></div>` : '';
  return `<div class="rfail">
    <div class="rftitle">${I('warn','var(--rose-400)',15)}<b>${escHtml(c.tipo_error || 'Fallo')}</b>${c.mensaje?`<span>${escHtml(String(c.mensaje).split('\n')[0])}</span>`:''}</div>
    ${c.archivo ? `<div class="rfwhere"><span class="rloc">${escHtml(c.archivo)}:${Number(c.linea)}</span>${c.codigo?`<pre class="rline"><span class="rmark">&gt;</span> ${escHtml(c.codigo)}</pre>`:''}</div>` : ''}
    ${valores}
    ${pila ? `<div class="rpila"><h5>Pila de llamadas</h5>${pila}</div>` : ''}
    ${c.traza ? `<details class="rtraza"><summary>Traza completa de pytest</summary><pre>${escHtml(c.traza)}</pre></details>` : ''}
  </div>`;
}

// #76: nombre de cada categoría de caso y la categoría de un caso de pytest
// (`test_<id>` o `test_<id>[parámetros]`) según el contrato del Planner.
const NOMBRE_CATEGORIA = {normal:'Normal', limite:'Límite', error:'Error'};
function categoriaDeCaso(f, nombre){
  const id = String(nombre || '').split('[')[0].replace(/^test_/, '');
  return (f && f.categoria_por_caso || {})[id] || null;
}
function casoRealHtml(c, clave, categoria){
  const [cls, ic, txt] = RES_CASO[c.resultado] || RES_CASO.error;
  const falla = c.resultado==='fallo' || c.resultado==='error';
  const abierto = falla ? rRealCaso[clave] !== false : false;   // los fallos se muestran abiertos
  const claveJs = escHtml(JSON.stringify(clave));
  const resumen = falla && c.archivo ? `<span class="rloc">${escHtml(c.archivo)}:${Number(c.linea)}</span>` : (c.resultado==='omitido' && c.mensaje ? `<span class="rdet">${escHtml(c.mensaje)}</span>` : '');
  return `<div class="rcaso ${cls}">
    <div class="rcrow" ${falla ? `onclick="rRealCaso[${claveJs}]=${!abierto};renderReport()" style="cursor:pointer"` : ''}>
      <span class="rcst">${I(ic,'currentColor',14)} ${txt}</span>
      <span class="rcname">${escHtml(c.nombre)}</span>${categoria ? `<span class="rkind">${escHtml(NOMBRE_CATEGORIA[categoria] || categoria)}</span>` : ''}${resumen}
      <span class="rcdur">${segRep(c.duracion_s)}</span>${falla ? I(abierto?'chevU':'chevD','var(--slate-300-c)',16) : ''}
    </div>${abierto ? filaFalloHtml(c) : ''}</div>`;
}

function ejecucionRealHtml(f, id){
  const conEjecucion = (f.intentos || []).filter(i => i.ejecucion);
  if(!conEjecucion.length) return `<div class="rhd"><span style="color:var(--mut)">Esta corrida no guardó los casos de ejecución: ${f.intentos && f.intentos.length ? 'el test no llegó a ejecutarse en el sandbox o la corrida es anterior al informe detallado.' : 'es anterior al informe detallado.'}</span></div>`;
  const elegido = rRealIntento[id];
  const it = conEjecucion.find(i => i.intento===elegido) || conEjecucion[conEjecucion.length-1];
  const ej = it.ejecucion, t = ej.totales;
  const idJs = escHtml(JSON.stringify(id));
  const historial = f.intentos.map(i => {
    const [dcls, dtxt] = DECISION_INTENTO[i.decision] || ['rs-stk', String(i.decision || '').toUpperCase()];
    const clic = i.ejecucion ? `onclick="rRealIntento[${idJs}]=${Number(i.intento)};renderReport()"` : '';
    return `<div class="rint ${i.intento===it.intento?'on':''} ${i.ejecucion?'click':''}" ${clic}><b>Intento ${Number(i.intento)}</b><span class="rsb ${dcls}">${escHtml(dtxt)}</span>${i.tipo_fallo?`<span class="rdet">${i.tipo_fallo==='bug_codigo'?'el código no cumple el contrato':'el test estaba mal escrito'}</span>`:''}${i.laundering_detectado?'<span class="rdet" style="color:var(--rose-300)">aserciones relajadas</span>':''}${i.ejecucion?'':'<span class="rdet">no llegó al sandbox</span>'}</div>`;
  }).join('');
  const chips = `<div class="rchips"><span class="rchip ok">${Number(t.pasaron)} pasaron</span><span class="rchip ${t.fallaron?'bad':''}">${Number(t.fallaron)} fallaron</span><span class="rchip ${t.errores?'bad':''}">${Number(t.errores)} errores</span><span class="rchip">${Number(t.omitidos)} omitidos</span><span class="rchip">${segRep(ej.duracion_s)}</span><span class="rchip">exit code ${ej.exit_code===null?'—':Number(ej.exit_code)}</span>${ej.timeout?'<span class="rchip bad">TIEMPO AGOTADO</span>':''}${ej.oom?'<span class="rchip bad">SIN MEMORIA</span>':''}</div>`;
  const casos = ej.casos.length
    ? ej.casos.map(c => casoRealHtml(c, id + '::' + it.intento + '::' + c.nombre, categoriaDeCaso(f, c.nombre))).join('')
    : '<div class="rhd"><span style="color:var(--mut)">pytest no devolvió casos individuales (no se generó junit.xml); la salida completa está más abajo.</span></div>';
  const sinCubrir = Array.isArray(ej.lineas_sin_cubrir)
    ? `<div class="rhd" style="margin-top:12px"><span>Líneas de la función sin cubrir:</span><span class="rtag" style="color:${ej.lineas_sin_cubrir.length?'var(--amber-300)':'var(--emerald-300)'};border-color:var(--line2)">${ej.lineas_sin_cubrir.length ? ej.lineas_sin_cubrir.map(Number).join(', ') : 'ninguna'}</span></div>` : '';
  return `<div class="rhd"><span>${I('term','var(--purple-400)',14)} Resultado de cada caso de pytest en el sandbox:</span></div>
    <div class="rhist">${historial}</div>
    ${chips}
    <div class="rcasos">${casos}</div>
    ${sinCubrir}
    ${it.feedback ? `<div class="rhd" style="margin-top:12px"><span>Veredicto del Reviewer (intento ${Number(it.intento)}):</span></div><pre class="rcode rfeed">${escHtml(it.feedback)}</pre>` : ''}
    <details class="rtraza" style="margin-top:12px"><summary>Salida completa de pytest (stdout y stderr)</summary><pre>${escHtml(ej.salida || '(sin salida)')}</pre></details>`;
}

/* Color del Mutation Score según el control que calculó el backend (meta de ADR-001). */
function colorMutacion(f){
  const control = (f.controles || []).find(c => c.clave === 'mutation');
  if(f.mutation_score===null || !control) return 'var(--mut)';
  return control.estado==='ok' ? 'var(--emerald-400)' : control.estado==='falla' ? 'var(--rose-400)' : 'var(--mut)';
}

/* Mutantes que las pruebas no detectaron (EN-09): línea del archivo y cambio de mutmut. */
function sobrevivientesHtml(f){
  const vivos = (f.mutacion && f.mutacion.sobrevivientes) || [];
  if(!vivos.length) return '';
  const filas = vivos.map(s => `<div class="rfr"><span class="rloc">${s.linea===null || s.linea===undefined ? 'línea —' : 'línea ' + Number(s.linea)}</span><code>${escHtml(s.cambio || s.mutante)}</code></div>`).join('');
  return `<div class="rpila" style="margin-top:12px"><h5>Mutantes sobrevivientes (${vivos.length}): las pruebas no detectaron estos cambios</h5>${filas}</div>`;
}

function entornoRealHtml(v){
  const e = v.entorno, t = v.totales_casos;
  if(!e) return `<div class="rcard rent"><div class="rentbody" style="color:var(--mut)">${v.es_simulado ? 'Corrida con IA simulada: no se ejecutó nada en el sandbox, así que no hay datos de ejecución.' : 'Esta corrida no guardó los datos de ejecución (es anterior al informe detallado).'}</div></div>`;
  const celda = (k, val) => `<div><span>${k}</span><b>${escHtml(val === null || val === undefined || val === '' ? '—' : String(val))}</b></div>`;
  const l = e.limites || {};
  return `<details class="rcard rent" open><summary>${I('term','var(--blue-400)',14)} Datos de la ejecución</summary>
    <div class="rentbody"><div class="rentgrid">
      ${celda('Imagen del sandbox', e.imagen)}${celda('Python', e.python)}${celda('pytest', e.pytest)}${celda('Plataforma', e.plataforma)}
      ${celda('Límites', `${l.cpus ?? '—'} CPU · ${l.memoria ?? '—'} · ${l.timeout_s ?? '—'} s`)}${celda('Red', 'desactivada')}
      ${t ? celda('Casos ejecutados', `${t.total} (${t.pasaron} pasaron · ${t.fallaron} fallaron · ${t.errores} errores · ${t.omitidos} omitidos)`) : ''}
    </div><div class="rcmd"><span>Comando</span><code>${escHtml(e.comando || '—')}</code></div></div></details>`;
}

function renderReportReal(v){
  if (typeof actualizarBarraReal === 'function') actualizarBarraReal(v);
  $('rentorno').innerHTML = entornoRealHtml(v);
  const k = v.indicadores, fecha = new Date(v.fecha);
  const modelos = AGENTES_REP.filter(([a]) => v.modelos[a]).map(([a, n]) => `${n} · ${escHtml(v.modelos[a].modelo)} <span style="color:var(--dim)">(${escHtml(v.modelos[a].proveedor)})</span>`).join(' &nbsp;|&nbsp; ');
  $('rmeta').innerHTML = `Corrida <b>${escHtml(v.run_id)}</b> · ${escHtml(isNaN(fecha) ? v.fecha : fecha.toLocaleString('es-PE'))} · perfil <b>${escHtml(v.perfil_nombre || v.perfil)}</b> · ${Number(v.total_objetivos)} objetivos · rama <b>${escHtml(v.rama || 'sin repositorio Git')}</b><br><span style="font-size:11px">Modelos: ${modelos}</span>`
    + (v.texto_categorias ? `<br><span style="font-size:11px">Casos de la corrida: ${escHtml(v.texto_categorias)}</span>` : '')
    + (v.es_humo ? '<br><span style="font-size:11px">Humo: un caso normal por objetivo. El Pass Rate es la métrica principal; la cobertura de ramas no se exige.</span>' : '')
    + (v.motivo_fallo ? `<br><span style="color:var(--amber-300);font-size:11px">Corrida detenida: ${escHtml(v.motivo_fallo)}</span>` : '');
  const pr = k.pass_rate, cv = k.cobertura, cs = k.costo, bal = k.balance;
  $('pillars').innerHTML = `
    <div class="pil"><div class="pt">${I('check','var(--emerald-400)',12)}Pass Rate</div><div class="pv" style="color:${pr.meta!==null && pr.valor>=pr.meta?'var(--emerald-400)':'var(--amber-300)'}">${numRep(pr.valor)}</div><div class="ps">${pr.pasaron}/${pr.total} pruebas sin error${pr.meta!==null?' · meta '+numRep(pr.meta,0):''}</div></div>
    <div class="pil"><div class="pt">${I('merge','var(--blue-400)',12)}Cobertura</div><div class="pv" style="color:var(--blue-400);font-size:19px">${numRep(cv.lineas)} <small>/ ${numRep(cv.ramas)}</small></div><div class="ps">Líneas / Ramas (promedio)${cv.exige_ramas === false ? ' · ramas no exigidas en Humo' : ''}</div></div>
    <div class="pil"><div class="pt">${I('coins','var(--amber-400)',12)}Costo</div><div class="pv" style="color:var(--amber-300);font-size:18px">US$ ${Number(cs.usd).toFixed(4)}</div><div class="ps">${Number(cs.tokens).toLocaleString('es-PE')} tokens${cs.tope_usd!==null && cs.tope_usd!==undefined?' · tope US$ '+Number(cs.tope_usd).toFixed(2):''}</div></div>
    <div class="pil"><div class="pt">${I('shieldA','var(--rose-400)',12)}Balance</div><div class="pv" style="font-size:19px"><span style="color:var(--emerald-400)">${bal.ok} OK</span> <span style="color:var(--slate-600)">/</span> <span style="color:var(--rose-400)">${bal.alertas} alertas</span></div><div class="ps">OK = aceptada y con los 5 controles en orden</div></div>`;
  const colores = {todas:'var(--blue-600)', verde:'var(--emerald-600)', incidentes:'var(--rose-600)'};
  $('rtypebtns').innerHTML = v.filtros_tipo.map(f => `<button class="fb2 ${rTypeFilter===f.clave?'on':''}" style="${rTypeFilter===f.clave?'background:var(--blue-600)':''}" onclick="rTypeFilter='${f.clave}';renderReport()">${escHtml(f.etiqueta)} (${Number(f.cantidad)})</button>`).join('');
  $('rfbtns').innerHTML = v.filtros.map(f => `<button class="fb2 ${rFilter===f.clave?'on':''}" style="${rFilter===f.clave?'background:'+colores[f.clave]:''}" onclick="rFilter='${f.clave}';renderReport()">${escHtml(f.etiqueta)} (${Number(f.cantidad)})</button>`).join('');
  $('legend2').innerHTML = Object.values(ESTADO_REP).filter((e, i, a) => a.findIndex(x => x.st===e.st)===i).map(e => `<span><i style="background:${ST[e.st].c}"></i> ${escHtml(e.txt.toLowerCase())}</span>`).join('');
  const lista = v.funciones.filter(f => (rTypeFilter==='todos' || f.tipo===rTypeFilter) && (rFilter==='todas' || (rFilter==='verde' ? f.verde : !f.verde)));
  $('rcards').innerHTML = lista.length ? lista.map((f, i) => {
    const id = f.modulo + '::' + f.funcion, e = ESTADO_REP[f.estado], st = ST[e.st], abierto = !!rRealAbierto[id], tab = rRealTab[id] || 'checklist';
    const etiqueta = f.estado==='estancado' ? `ESTANCADO ${f.iteraciones}/3` : f.estado==='requiere_corrida_nueva' && f.texto_motivo_regresion ? `${e.txt} · ${f.texto_motivo_regresion}` : e.txt;
    const idJs = escHtml(JSON.stringify(id));
    let cuerpo = '';
    if(abierto){
      const tabs = [['contract','file','1. Contrato JSON (Planner)','var(--blue-400)'],['test','code','2. Test generado (pytest)','var(--purple-400)'],['checklist','check','3. Checklist de verificación','var(--emerald-400)'],['run','term','4. Ejecución y casos','var(--amber-300)']];
      cuerpo = `<div class="rbody"><div class="rtabs">${tabs.map(([t,ic,n,c]) => `<button class="${tab===t?'on':''}" style="${tab===t?`color:${c};border-color:${c}`:''}" onclick="event.stopPropagation();rRealTab[${idJs}]='${t}';renderReport()">${I(ic,'currentColor',14)} ${n}</button>`).join('')}</div>`;
      if(tab==='contract') cuerpo += contratoRealHtml(f);
      if(tab==='run') cuerpo += ejecucionRealHtml(f, id);
      if(tab==='test') cuerpo += (f.codigo
        ? `<div class="rhd"><span>${I('term','var(--purple-400)',14)} Último test generado por el Generator (intento ${f.iteraciones}/3):</span></div><pre class="rcode">${hl(f.codigo)}</pre>`
        : `<div class="rhd"><span style="color:var(--mut)">Esta corrida no guardó el test generado.</span></div>`)
        + (f.traza ? `<div class="rerr"><b>${I('warn','var(--rose-400)',15)} Traza del último intento (pytest / Reviewer):</b><pre>${escHtml(f.traza)}</pre></div>` : '');
      if(tab==='checklist') cuerpo += `<div class="rhd"><span>Controles del último intento, calculados al cerrar la corrida:</span><span style="color:var(--emerald-400)">5 controles</span></div>
        <div class="cks">${f.controles.map((c, j) => { const [cls, ic, txt] = CONTROL_REP[c.estado];
          return `<div class="ck ${cls}${j===4?' wide':''}" title="${escHtml(c.nota || '')}"><div class="cl">${I(ic,'currentColor',15)}<span>${escHtml(c.etiqueta)}</span></div><span class="ct">${c.nota ? escHtml(c.nota) : txt}</span></div>`; }).join('')}</div>`
        + sobrevivientesHtml(f);
      cuerpo += '</div>';
    }
    return `<div class="rcard" style="border-left-color:${st.c};${f.verde?'':`box-shadow:0 0 0 1px ${st.halo}`}">
      <div class="rch" onclick="rRealAbierto[${idJs}]=!rRealAbierto[${idJs}];renderReport()">
        <div class="l"><span class="mtag" style="${st.mb}">${f.verde?'OK':'ALERTA'}</span>
          <div style="min-width:0"><div class="rn">${f.tipo==='endpoint'?escHtml(f.identificador):escHtml(f.identificador)+'()'} <span class="rmod">${escHtml(f.modulo)}</span><span class="rkind">${f.tipo==='endpoint'?'Endpoint':'Función'}</span>${f.reutilizada?'<span class="rkind" title="La prueba aprobada guardada se volvió a ejecutar en el sandbox, sin IA">♻ Prueba repetida</span>':''}${f.critical?'<span class="rcrit">★ crítica</span>':''}</div><div class="rsig">${f.tipo==='endpoint'&&f.manejador?`Manejador: ${escHtml(f.manejador)} · `:''}${escHtml(f.firma || '')}</div>${f.texto_categorias ? `<div class="rsig" title="Casos del contrato por categoría">Casos: ${escHtml(f.texto_categorias)}</div>` : ''}${f.aviso_limites ? `<div class="rsig" style="color:var(--amber-300)">${I('warn','currentColor',12)} ${escHtml(f.aviso_limites)}</div>` : ''}</div></div>
        <div class="r"><span class="rpill"><span style="color:var(--mut)">Cob:</span> <b style="color:var(--blue-400)">${numRep(f.cobertura_lineas)}</b></span>
          <span class="rpill" title="${f.critical?(f.tipo==='endpoint'?'Mutation Score (mutmut) del manejador del endpoint prioritario':'Mutation Score (mutmut) de la función crítica'):'No aplica: mutmut solo corre sobre funciones críticas y endpoints prioritarios'}"><span style="color:var(--mut)">Mutantes:</span> <b style="color:${colorMutacion(f)}">${f.mutation_score===null?'N/A':numRep(f.mutation_score,0)}</b></span>
          <span class="rsb ${st.repCls}">${I(st.repIco,'currentColor',13)} ${escHtml(etiqueta)}</span>${I(abierto?'chevU':'chevD','var(--slate-300-c)',20)}</div>
      </div>${cuerpo}</div>`;
  }).join('') : '<div class="rcard" style="padding:18px;color:var(--mut)">No hay resultados para los filtros seleccionados.</div>';
}

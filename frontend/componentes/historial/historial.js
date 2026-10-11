// historial.js — pantalla «Historial de corridas y specs» del proyecto
// HTML del componente (se monta en el marcador data-componente="historial/historial" de index.html)
registrarComponente('historial/historial', `<!-- ===== 7. HISTORIAL DE CORRIDAS Y SPECS (por proyecto) ===== -->
<section id="s-history" class="hide scroll">
  <div class="page">
    <div class="card"><div class="projhead">
      <span class="t">Historial · <span class="repoName">ecommerce-core</span></span>
      <span class="pill p-grey">Se guarda en <span class="mono">.pyagent/</span> dentro del proyecto · no se borra entre sesiones</span>
    </div></div>
    <div class="card">
      <h4>Corridas <span class="pill p-grey" id="histCount"></span></h4>
      <table>
        <thead><tr><th>Corrida</th><th>Fecha</th><th>Perfil</th><th>Modelos</th><th>Specs</th><th>Pass Rate</th><th>Tokens</th><th>Costo</th><th></th></tr></thead>
        <tbody id="histTable"></tbody>
      </table>
      <div class="hint" style="padding:10px 16px 14px">El costo baja cuando se reutilizan specs (se omite el Planner, el agente más caro) y es cero en Regresión (no se llama a ninguna IA). La columna Modelos distingue corridas de control, por ejemplo los 3 agentes con el mismo modelo.</div>
    </div>
    <div class="card">
      <h4>Specs guardados <span class="pill p-grey">.pyagent/specs/</span>
        <button class="btn" style="margin-left:auto;font-size:10.5px;padding:6px 10px;text-transform:none;letter-spacing:0" onclick="descargarSpecsReal(null)">⤓ Descargar todos (.zip)</button></h4>
      <table>
        <thead><tr><th>Archivo</th><th>Funciones</th><th>Huella del código</th><th>Generado en</th><th>Estado</th><th></th></tr></thead>
        <tbody id="specTable"></tbody>
      </table>
      <div class="hint" style="padding:10px 16px 14px">Regla: cada spec guarda una huella del código y la documentación del módulo. Si cambian, el spec se regenera en la siguiente corrida. Las pruebas rechazadas (laundering u oráculo alterado) y las estancadas no se guardan para Regresión: solo las aprobadas.</div>
    </div>
  </div>
</section>
`);

const HISTORY = [
  {run:'8730-A', date:'12/09/2026 10:05', profile:'Profundo',  models:'Estándar del sistema', specs:'6 generados',                  pass:'56%', tokens:171300, split:{P:28,G:52,R:20}},
  {run:'8791-A', date:'19/09/2026 16:40', profile:'Regresión', models:'— (sin IA)',           specs:'— (sin IA)',                   pass:'100% (6/6 guardadas)', tokens:0, split:{P:0,G:0,R:0}},
  {run:'8841-B', date:'25/09/2026 14:32', profile:'Profundo',  models:'Estándar del sistema', specs:'4 reutilizados · 2 regenerados', pass:'67%', tokens:142500, split:null, current:true},
];
const SPEC_HASH = {'services/pricing.py':'a3f9c21','services/inventory.py':'7be04d9','services/payments.py':'c11e8a2','services/shipping.py':'5d20f7e','services/cart.py':'e94b1c0','services/discounts.py':'0fa7d33'};
function specName(mod){ return mod.split('/').pop().replace(/\.py$/,'') + '.spec.json'; }
async function renderHistory(){
  const api = window.pywebview && window.pywebview.api;
  if(api && api.obtener_historial){
    try {
      const datos = await api.obtener_historial(projectPath);
      if(datos && datos.ok){ renderHistoryReal(datos); return; }
    } catch(err) {
      console.error('No se pudo cargar el historial:', err);
    }
  }
  renderHistoryDemo();
}
function renderHistoryDemo(){
  $('histCount').textContent = HISTORY.length + ' registradas';
  $('histTable').innerHTML = HISTORY.slice().reverse().map(h => `<tr>
    <td class="mono">#${h.run}${h.current?' <span class="pill p-blue" style="margin-left:4px">actual</span>':''}</td>
    <td>${h.date}</td><td>${h.profile}</td><td style="font-size:11.5px">${h.models}</td><td>${h.specs}</td><td>${h.pass}</td><td class="mono">${h.tokens?kfmt(h.tokens):'0'}</td>
    <td class="mono">S/ ${(agentCost((sp => ({P:h.tokens*sp.P/100,G:h.tokens*sp.G/100,R:h.tokens*sp.R/100}))(h.split||AGENT_SPLIT))*FX).toFixed(2)}</td>
    <td>${h.current ? `<button class="btn" style="font-size:10.5px;padding:6px 10px" onclick="go('report')">Ver reporte</button>`
                    : `<button class="btn" style="font-size:10.5px;padding:6px 10px" onclick="toast('En la app real se abre el reporte archivado de la corrida #${h.run} <span style=&quot;color:var(--dim)&quot;>(simulado)</span>')">Ver reporte</button>`}</td></tr>`).join('');
  const mods = [...new Set(RUN.map(f=>f.module))];
  $('specTable').innerHTML = mods.map(mod => {
    const fns = RUN.filter(f=>f.module===mod), st = SPEC_STATUS[mod], name = specName(mod);
    const data = {modulo:mod, huella_codigo:SPEC_HASH[mod], generado_en:'#'+(st==='reuse'?'8730-A':RUN_ID), generado_por:'Planner v2.4', funciones:fns.map(f=>f.contract)};
    return `<tr>
      <td class="fn">.pyagent/specs/${name}<div class="sub">${mod}</div></td>
      <td>${fns.map(f=>`<div class="mono" style="font-size:11px">${f.name}</div>`).join('')}</td>
      <td class="mono">${SPEC_HASH[mod]}</td>
      <td class="mono">#${st==='reuse'?'8730-A':RUN_ID}</td>
      <td>${st==='reuse'?'<span class="pill p-green">♻ Vigente · reutilizado</span>':'<span class="pill p-amber">↻ Regenerado (el código cambió)</span>'}</td>
      <td><button class="btn" style="font-size:10.5px;padding:5px 9px" title="Descargar este spec" onclick='download(${JSON.stringify(name)}, ${JSON.stringify(JSON.stringify(data,null,2))}, "application/json")'>⤓</button></td></tr>`;
  }).join('');
}

function renderHistoryReal(datos){
  const corridas = datos.corridas || [], specs = datos.specs || [];
  $('histCount').textContent = corridas.length + ' registradas';
  $('histTable').innerHTML = corridas.length ? corridas.map((h, indice) => {
    const fecha = new Date(h.fecha), modelos = Object.values(h.modelos || {}).filter(Boolean).join(' · ') || '—';
    const s = h.resumen_specs || {}, partes = [];
    if(s.generado) partes.push(s.generado + ' generados');
    if(s.reutilizado) partes.push(s.reutilizado + ' reutilizados');
    if(s.regenerado) partes.push(s.regenerado + ' regenerados');
    return `<tr>
      <td class="mono">#${escHtml(h.run_id)}${indice===0?' <span class="pill p-blue" style="margin-left:4px">actual</span>':''}</td>
      <td>${escHtml(isNaN(fecha) ? h.fecha : fecha.toLocaleString('es-PE'))}</td>
      <td>${escHtml(h.perfil || '—')}</td><td style="font-size:11.5px">${escHtml(modelos)}</td>
      <td>${escHtml(partes.join(' · ') || '—')}</td><td>${h.pass_rate===null || h.pass_rate===undefined?'—':Number(h.pass_rate).toFixed(1)+'%'}</td>
      <td class="mono">${Number(h.total_tokens || 0).toLocaleString('es-PE')}<div class="sub">Planner: ${Number(h.tokens_planner || 0).toLocaleString('es-PE')}</div></td>
      <td class="mono">US$ ${Number(h.costo_usd || 0).toFixed(4)}</td>
      <td><button class="btn" style="font-size:10.5px;padding:6px 10px" onclick="cargarReporteReal('${escHtml(h.run_id)}')">Ver reporte</button></td></tr>`;
  }).join('') : '<tr><td colspan="9" class="hint">Todavía no hay corridas registradas.</td></tr>';

  $('specTable').innerHTML = specs.length ? specs.map(spec => {
    const accion = spec.ultima_accion;
    const estado = accion==='reutilizado'
      ? '<span class="pill p-green">♻ Vigente · reutilizado</span>'
      : accion==='regenerado'
        ? '<span class="pill p-amber">↻ Regenerado (el código cambió)</span>'
        : '<span class="pill p-blue">Generado</span>';
    return `<tr>
      <td class="fn">.pyagent/specs/${escHtml(spec.archivo)}<div class="sub">${escHtml(spec.modulo)}</div></td>
      <td>${(spec.funciones || []).map(f=>`<div class="mono" style="font-size:11px">${escHtml(f)}</div>`).join('')}</td>
      <td class="mono" title="${escHtml(spec.huella)}">${escHtml(spec.huella.slice(0,12))}…</td>
      <td class="mono">#${escHtml(spec.run_origen)}</td><td>${estado}</td>
      <td><button class="btn" style="font-size:10.5px;padding:5px 9px" title="Descargar este spec en ZIP" onclick='descargarSpecsReal(${JSON.stringify(spec.modulo)})'>⤓</button></td></tr>`;
  }).join('') : '<tr><td colspan="6" class="hint">Todavía no hay specs modulares guardadas.</td></tr>';
}

async function descargarSpecsReal(modulo){
  const api = window.pywebview && window.pywebview.api;
  if(!(api && api.descargar_specs_zip)){
    toast('La descarga ZIP está disponible en la aplicación de escritorio. <span style="color:var(--dim)">(demostración)</span>');
    return;
  }
  try {
    const r = await api.descargar_specs_zip(projectPath, modulo);
    if(r && r.cancelado) return;
    if(!r || !r.ok){ toastError(escHtml((r && r.motivo) || 'No se pudo crear el ZIP.')); return; }
    toast(`Se guardó <span class="mono">${escHtml(r.nombre)}</span> en <span class="mono">${escHtml(r.ruta)}</span>`);
  } catch(err) {
    toastError('No se pudo descargar el spec: ' + escHtml(String(err)));
  }
}

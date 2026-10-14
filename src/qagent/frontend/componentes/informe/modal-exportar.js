// modal-exportar.js — modal «Exportar informe» (HU-22): PDF, Markdown y JSON
// HTML del componente (se monta en el marcador data-componente="informe/modal-exportar" de index.html)
registrarComponente('informe/modal-exportar', `<!-- Exportar informe (HU-22) -->
<div class="overlay" id="m-export"><div class="modal" style="width:640px">
  <div class="mhead"><span class="ico" data-i="download" data-c="var(--blue-400)"></span> <span id="expTitle">Exportar informe de auditoría</span><button class="x" onclick="closeModal()">×</button></div>
  <div class="mcontent">
    <div><label class="l">Formato</label>
      <div class="fmts">
        <div class="fmt" data-f="pdf" onclick="setFmt('pdf')"><b>PDF</b><span>Documento formal para el auditor (evidencia).</span></div>
        <div class="fmt" data-f="md" onclick="setFmt('md')"><b>Markdown (.md)</b><span>Editable y versionable junto al código.</span></div>
        <div class="fmt" data-f="json" onclick="setFmt('json')"><b>JSON (results)</b><span>Datos crudos de métricas para otras herramientas.</span></div>
        <div class="fmt" data-f="html" onclick="setFmt('html')"><b>HTML Interactivo ✨</b><span>Dashboard visual con gráficas y secciones expandibles.</span></div>
      </div></div>
    <div><label class="l">Contenido del informe</label>
      <div class="expchk">
        <label class="chk"><input type="checkbox" checked disabled> Resumen de las 5 métricas vs. metas de la carta</label>
        <label class="chk"><input type="checkbox" class="expOpt" id="expDetail" checked> Resultado por función (estado, intentos, cobertura, Mutation Score, tokens)</label>
        <label class="chk"><input type="checkbox" class="expOpt" id="expTrace" checked> Trazas del Reviewer de los incidentes</label>
        <label class="chk"><input type="checkbox" class="expOpt" id="expCode"> Código de las pruebas generadas</label>
        <label class="chk"><input type="checkbox" class="expOpt" id="expContract"> Contratos JSON del Planner</label>
      </div></div>
    <div><label class="l">Guardar en</label>
      <div style="display:flex;gap:8px"><input class="inp" id="expPath" readonly><button class="btn" id="expChangeBtn" onclick="cambiarCarpetaExportar()">Cambiar…</button></div>
      <div class="hint">Archivo: <span class="mono" id="expName"></span> · por defecto dentro de la carpeta del proyecto, junto a los resultados de la corrida.</div></div>
  </div>
  <div class="mfoot"><button class="btn" onclick="closeModal()">Cancelar</button><button class="btn primary" id="expConfirmBtn" onclick="doExport()">Exportar</button></div>
</div></div>
`);

/* ---------------- Exportar informe (HU-22) ---------------- */
let expFmt = 'pdf';
let expCustomDir = null;

function runIdExportar(){
  return (typeof reporteReal !== 'undefined' && reporteReal && reporteReal.run_id) ? reporteReal.run_id : RUN_ID;
}

function proyectoBaseExportar(){
  if (typeof reporteReal !== 'undefined' && reporteReal && reporteReal.proyecto) return reporteReal.proyecto;
  return projectPath;
}

function carpetaPorDefectoExportar(){
  const base = String(proyectoBaseExportar() || '').replace(/[\\/]+$/, '');
  return base + '\\.qagent\\runs\\' + runIdExportar() + '\\';
}

function opcionesExportar(){
  return {
    detalle: $('expDetail').checked,
    trazas: $('expTrace').checked,
    codigo: $('expCode').checked,
    contratos: $('expContract').checked,
  };
}

async function openExport(){
  expCustomDir = null;
  const id = runIdExportar();
  if ($('expTitle')) $('expTitle').textContent = 'Exportar informe de auditoría · corrida #' + id;
  $('expPath').readOnly = true;
  $('expPath').value = carpetaPorDefectoExportar();
  setFmt(expFmt);
  openModal('m-export');
  const api = window.pywebview && window.pywebview.api;
  if (api && api.carpeta_corrida) {
    try {
      const carpeta = await api.carpeta_corrida(proyectoBaseExportar(), id);
      if (carpeta && !expCustomDir) $('expPath').value = carpeta;
    } catch (_) {}
  }
}

async function abrirCarpetaCorrida(){
  const api = window.pywebview && window.pywebview.api;
  if (api && api.abrir_carpeta_corrida) {
    try {
      const r = await api.abrir_carpeta_corrida(proyectoBaseExportar(), runIdExportar());
      if (r && r.ok) {
        toast(`Carpeta de la corrida abierta: <span class="mono">${escHtml(r.carpeta)}</span>`);
      } else {
        toastError(escHtml((r && r.motivo) || 'No se pudo abrir la carpeta de la corrida.'));
      }
      return;
    } catch (err) {
      toastError('No se pudo abrir la carpeta: ' + escHtml(String(err)));
      return;
    }
  }
  toast('En la app de escritorio se abre la carpeta '+projectPath+'\\.qagent\\runs\\'+RUN_ID+' <span style="color:var(--dim)">(simulado)</span>');
}

function setFmt(f){
  expFmt = f;
  const id = runIdExportar();
  document.querySelectorAll('.fmt').forEach(e => e.classList.toggle('on', e.dataset.f===f));
  $('expName').textContent = {pdf:`informe_${id}.pdf`, md:`informe_${id}.md`, json:`results_${id}.json`, html:`informe_${id}.html`}[f] || `informe_${id}.pdf`;
  document.querySelectorAll('.expOpt').forEach(e => e.disabled = false);
}

async function cambiarCarpetaExportar(){
  const api = window.pywebview && window.pywebview.api;
  if (api && api.select_folder) {
    try {
      const carpeta = await api.select_folder();
      if (!carpeta) return;
      expCustomDir = carpeta;
      $('expPath').value = String(carpeta).replace(/[\\/]+$/, '') + '\\';
      return;
    } catch (err) {
      toastError('No se pudo seleccionar la carpeta: ' + escHtml(String(err)));
      return;
    }
  }
  $('expPath').readOnly = false;
  $('expPath').focus();
  toast('En la aplicación de escritorio se abre el diálogo nativo; aquí puedes editar la ruta directamente.');
}

function buildMarkdown(){
  const m = metrics(), inc = id => $(id).checked, ok = b => b ? '✅ Cumple' : '❌ No cumple';
  let md = `# Informe de auditoría de pruebas unitarias — Corrida #${RUN_ID}\n\n`;
  md += `- **Proyecto:** ${document.querySelector('.repoLbl').textContent}\n- **Rama:** ${$('branchLbl').textContent}\n- **Fecha:** ${RUN_DATE}\n- **Perfil:** Profundo · **Funciones evaluadas:** ${m.n} (${m.crit} críticas)\n- **Generado por:** QAgent v2.4 (Planner → Generator → Reviewer)\n- **Modelos:** Planner: ${AGENTS_CFG.P.model} (US$ ${AGENTS_CFG.P.price}/M) · Generator: ${AGENTS_CFG.G.model} (US$ ${AGENTS_CFG.G.price}/M) · Reviewer: ${AGENTS_CFG.R.model} (US$ ${AGENTS_CFG.R.price}/M)\n- **Specs:** 4 reutilizados de corridas anteriores · 2 regenerados (cart.py, discounts.py cambiaron) · guardados en \`.qagent/specs/\`\n\n`;
  md += `## 1. Resumen de métricas\n\n| Métrica | Resultado | Meta (carta) | Estado |\n|---|---|---|---|\n`;
  md += `| Pass Rate | ${pct(m.pass,1)} (${m.ok}/${m.n}) | ${META.pass[0]}–${META.pass[1]}% | ${ok(m.pass>=META.pass[0])} |\n`;
  md += `| Cobertura de líneas / ramas | ${pct(m.lines,1)} / ${pct(m.branch,1)} | ≥ ${META.lines}% líneas | ${ok(m.lines>=META.lines)} |\n`;
  md += `| Iteraciones promedio | ${m.iter.toFixed(2)} | < ${META.iter} (máx. 3) | ${ok(m.iter<META.iter)} |\n`;
  md += `| Tokens (P ${AGENT_SPLIT.P}% · G ${AGENT_SPLIT.G}% · R ${AGENT_SPLIT.R}%) | ${m.tokens.toLocaleString('es-PE')} · US$ ${m.usd.toFixed(2)} · S/ ${m.pen.toFixed(2)} | Reportar | ✅ Cumple |\n`;
  md += `| Costo por agente | Planner US$ ${m.agentUsd.P.toFixed(3)} · Generator US$ ${m.agentUsd.G.toFixed(3)} · Reviewer US$ ${m.agentUsd.R.toFixed(3)} | — | ✅ Reportado |\n`;
  md += `| Mutation Score (solo ${m.crit} funciones críticas) | ${pct(m.ms,1)} | ≥ ${META.ms}% | ${ok(m.ms>=META.ms)} |\n\n`;
  if(inc('expDetail')){
    md += `## 2. Resultado por función\n\n| Función | Módulo | Estado | Intentos | Cob. líneas | Cob. ramas | Mutation Score | Tokens |\n|---|---|---|---|---|---|---|---|\n`;
    RUN.forEach(f => md += `| ${f.name} | ${f.module} | ${stRep(f)} | ${f.iterations}/3 | ${f.lines_cov}% | ${f.branch_cov}% | ${f.mutation_score===null?'N/A (no crítica)':f.mutation_score+'%'} | ${f.tokens.toLocaleString('es-PE')} |\n`);
    md += `\n`;
  }
  if(inc('expTrace')){
    md += `## 3. Incidentes\n\n`;
    RUN.filter(f=>f.diag).forEach(f => {
      md += `### ${f.name} — ${stRep(f)}\n\n${f.diag}\n\n`;
      if(f.trace) md += '```text\n' + f.trace + '\n```\n\n';
    });
  }
  if(inc('expCode')){ md += `## 4. Pruebas generadas\n\n`; RUN.forEach(f => md += `### tests/test_${f.name}.py\n\n\`\`\`python\n${f.code}\n\`\`\`\n\n`); }
  if(inc('expContract')){ md += `## 5. Contratos del Planner\n\n`; RUN.forEach(f => md += `### ${f.name}\n\n\`\`\`json\n${JSON.stringify(f.contract,null,2)}\n\`\`\`\n\n`); }
  return md;
}

function download(name, content, type){
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], {type}));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function limpiarTextoPdf(s){
  return String(s || '')
    .replace(/✅\s*Cumple/g, 'Cumple')
    .replace(/✅\s*Reportado/g, 'Cumple (Reportado)')
    .replace(/❌\s*No cumple/g, 'No cumple')
    .replace(/[✅☑️]/g, '[OK]')
    .replace(/[❌]/g, '[NO]')
    .replace(/[⚠️⚠]/g, '[!]')
    .replace(/♻/g, '[Spec]')
    .replace(/★/g, '[*]')
    .replace(/≥/g, '>=')
    .replace(/≤/g, '<=')
    .replace(/[→]/g, '->')
    .replace(/[•·]/g, '-')
    .replace(/[—–]/g, '-');
}

function envolverLineaPdf(linea, ancho){
  if (linea.length <= ancho) return [linea];
  const res = [];
  let rest = linea;
  while (rest.length > ancho) {
    let corte = rest.lastIndexOf(' ', ancho);
    if (corte <= 0) corte = ancho;
    res.push(rest.slice(0, corte));
    rest = '  ' + rest.slice(corte).trimStart();
  }
  if (rest) res.push(rest);
  return res;
}

function escaparLiteralPdf(s){
  const norm = limpiarTextoPdf(s).replace(/\t/g, '    ');
  let out = '';
  for (let i = 0; i < norm.length; i++) {
    const code = norm.charCodeAt(i);
    if (code === 0x5c || code === 0x28 || code === 0x29) out += '\\' + norm[i];
    else if (code >= 32 && code <= 126) out += norm[i];
    else if (code >= 128 && code <= 255) out += '\\' + code.toString(8).padStart(3, '0');
    else out += ' ';
  }
  return out;
}

function coloresEstadoPdf(st){
  if (st === 'passed') return ['0.06 0.68 0.46', '0.84 0.96 0.89', '0.04 0.42 0.24'];
  if (st === 'rejected_laundering') return ['0.88 0.18 0.30', '0.99 0.88 0.90', '0.68 0.10 0.20'];
  if (st === 'rejected_oracle') return ['0.72 0.16 0.82', '0.96 0.89 0.99', '0.48 0.08 0.58'];
  return ['0.85 0.48 0.04', '0.99 0.94 0.83', '0.58 0.30 0.04'];
}

const PESTANAS_PDF_JS = [
  [1, '1. Resumen & KPIs', 36.0, 102.0],
  [2, '2. Graficas y Estad.', 140.5, 102.0],
  [3, '3. Detalle Funcion', 245.0, 102.0],
  [4, '4. Incidentes', 349.5, 102.0],
  [5, '5. Codigo y Contratos', 454.0, 105.0],
];

function buildPdfBytes(){
  const m = metrics(), inc = id => $(id).checked, runId = runIdExportar();
  const repo = (document.querySelector('.repoLbl') && document.querySelector('.repoLbl').textContent) || projectPath || 'proyecto';
  const rama = ($('branchLbl') && $('branchLbl').textContent) || 'main';
  const modelosTxt = `Planner: ${AGENTS_CFG.P.model} (Anthropic) | Generator: ${AGENTS_CFG.G.model} (Xiaomi) | Reviewer: ${AGENTS_CFG.R.model} (OpenAI)`;
  const costoAgTxt = `Planner: ${Math.round(m.agentTok.P)} tokens (US$ ${m.agentUsd.P.toFixed(4)}) | Generator: ${Math.round(m.agentTok.G)} tokens (US$ ${m.agentUsd.G.toFixed(4)}) | Reviewer: ${Math.round(m.agentTok.R)} tokens (US$ ${m.agentUsd.R.toFixed(4)})`;
  const specsTxt = '4 reutilizados (services/pricing.py, services/inventory.py, services/payments.py, services/shipping.py) · 2 regenerados (services/cart.py, services/discounts.py) · guardados en .qagent/specs/';

  const bloques = [];
  bloques.push({
    tipo: 'banner',
    seccion: 1,
    titulo: `Informe de auditoría de pruebas unitarias — Corrida #${runId}`,
    sub1: `Proyecto: ${repo}  |  Rama: ${rama}`,
    sub2: `Fecha: ${RUN_DATE}  |  Perfil: Profundo  |  Funciones evaluadas: ${m.n} (${m.crit} críticas)`
  });

  // Tarjetas KPI interactivas (Estadísticas Relevantes)
  const kpis = [
    {titulo: 'PASS RATE', valor: pct(m.pass, 1), sub: `${m.ok}/${m.n} aprobadas`, pct: Math.max(0, Math.min(100, m.pass)), cumple: m.pass >= META.pass[0]},
    {titulo: 'COB. LINEAS', valor: pct(m.lines, 1), sub: `Ramas: ${pct(m.branch, 1)}`, pct: Math.max(0, Math.min(100, m.lines)), cumple: m.lines >= META.lines},
    {titulo: 'ITERACIONES', valor: m.iter.toFixed(2), sub: `Meta <= ${META.iter} (max 3)`, pct: Math.max(0, Math.min(100, (1 - Math.max(0, m.iter - 1) / 2) * 100)), cumple: m.iter <= META.iter},
    {titulo: 'COSTO CORRIDA', valor: `US$ ${m.usd.toFixed(4)}`, sub: `${m.tokens} tokens`, pct: Math.max(12, Math.min(100, (m.pen / Math.max(0.01, TOPE_PEN)) * 100)), cumple: m.pen <= TOPE_PEN},
    {titulo: 'MUTATION SCORE', valor: pct(m.ms, 1), sub: `${m.crit} criticas (>=60%)`, pct: Math.max(0, Math.min(100, m.ms)), cumple: m.ms >= META.ms},
  ];
  bloques.push({tipo: 'panel_kpis', seccion: 1, kpis});

  const filasMeta = [];
  envolverLineaPdf(modelosTxt, 82).forEach((ln, i) => filasMeta.push([i === 0 ? 'Modelos usados:' : '', ln]));
  envolverLineaPdf(costoAgTxt, 82).forEach((ln, i) => filasMeta.push([i === 0 ? 'Costo por agente:' : '', ln]));
  envolverLineaPdf(specsTxt, 82).forEach((ln, i) => filasMeta.push([i === 0 ? 'Specs:' : '', ln]));
  bloques.push({tipo: 'ficha_meta', seccion: 1, filas: filasMeta});

  bloques.push({tipo: 'h2', seccion: 1, texto: '1. Resumen de las 5 métricas'});
  bloques.push({tipo: 'tabla_cabecera', seccion: 1});
  const metricasFilas = [
    ['Pass Rate', `${pct(m.pass, 1)} (${m.ok}/${m.n})`, `>= ${META.pass[0]}%`, m.pass >= META.pass[0]],
    ['Cobertura de líneas / ramas', `${pct(m.lines, 1)} / ${pct(m.branch, 1)}`, `>= ${META.lines}% líneas`, m.lines >= META.lines],
    ['Iteraciones promedio', m.iter.toFixed(2), `<= ${META.iter} (máx. 3)`, m.iter <= META.iter],
    ['Tokens y costo de la corrida', `${m.tokens} tokens · US$ ${m.usd.toFixed(4)}`, `<= S/ ${TOPE_PEN.toFixed(2)}`, m.pen <= TOPE_PEN],
    [`Mutation Score (${m.crit} funciones críticas)`, `${pct(m.ms, 1)} (${m.crit} críticas)`, `>= ${META.ms}%`, m.ms >= META.ms],
  ];
  metricasFilas.forEach(([nom, res, meta, cumple], idx) => {
    bloques.push({tipo: 'tabla_metrica', seccion: 1, par: idx % 2 === 1, nombre: nom, resultado: res, meta, estado: cumple ? 'Cumple' : 'No cumple', cumple});
  });
  bloques.push({tipo: 'nota_agentes', seccion: 1, lineas: envolverLineaPdf(`Desglose de costo por agente: ${costoAgTxt} (Estado: Reportado)`, 90)});

  // Panel de Gráficas y Estadísticas Relevantes (Pestaña 2)
  const fnsGraf = RUN.slice(0, 6).map(f => ({
    nombre: String(f.name).slice(0, 18),
    lineas: Number(f.lines_cov || 0),
    ramas: Number(f.branch_cov || 0),
    ms: Number(f.mutation_score || 0),
    tieneMs: f.mutation_score !== null && f.mutation_score !== undefined
  }));
  const estCounts = {passed: 0, rejected_laundering: 0, rejected_oracle: 0, flaky: 0};
  RUN.forEach(f => { estCounts[f.status] = (estCounts[f.status] || 0) + 1; });
  const totTok = Math.max(1, Math.round(m.agentTok.P + m.agentTok.G + m.agentTok.R));
  const agentesGraf = [
    {nombre: 'Planner', tokens: Math.round(m.agentTok.P), usd: m.agentUsd.P, pct: (m.agentTok.P / totTok) * 100},
    {nombre: 'Generator', tokens: Math.round(m.agentTok.G), usd: m.agentUsd.G, pct: (m.agentTok.G / totTok) * 100},
    {nombre: 'Reviewer', tokens: Math.round(m.agentTok.R), usd: m.agentUsd.R, pct: (m.agentTok.R / totTok) * 100},
  ];
  const cumplidasN = metricasFilas.filter(x => x[3]).length;
  const insights = [
    `Cumplimiento global: ${cumplidasN}/5 metricas dentro de la meta de la carta (Pass Rate: ${pct(m.pass, 1)} vs. meta >= ${META.pass[0]}%).`,
    `Calidad estructural: cobertura media de ${pct(m.lines, 1)} en lineas y ${pct(m.branch, 1)} en ramas; Mutation Score de ${pct(m.ms, 1)} en criticas.`,
    `Auditoria de incidentes: ${estCounts.passed || 0} aprobadas, ${estCounts.rejected_laundering || 0} rechazadas por Laundering, ${estCounts.rejected_oracle || 0} bugs de oraculo y ${estCounts.flaky || 0} inestables.`
  ];
  bloques.push({
    tipo: 'panel_graficas',
    seccion: 2,
    funciones: fnsGraf,
    estados: estCounts,
    totalFn: Math.max(1, RUN.length),
    agentes: agentesGraf,
    insights
  });

  if (inc('expDetail')) {
    bloques.push({tipo: 'h2', seccion: 3, texto: '2. Resultado por función'});
    RUN.forEach(f => {
      const msLbl = f.mutation_score === null ? 'N/A (no crítica)' : f.mutation_score + '%';
      const ctrlTxt = `Controles: Sin errores de sintaxis: ${f.checks.syntax ? 'OK' : 'NO CUMPLE'}; Sandbox sin errores: ${f.checks.sandbox ? 'OK' : 'NO CUMPLE'}; Aserciones íntegras: ${f.checks.assertions_intact ? 'OK' : 'NO CUMPLE'}; Cobertura >= 60%: ${f.checks.cov_met ? 'OK' : 'NO CUMPLE'}; Mutation Score >= 60%: ${f.checks.ms_met === null ? 'NO APLICA' : (f.checks.ms_met ? 'OK' : 'NO CUMPLE')}`;
      bloques.push({
        tipo: 'tarjeta_funcion',
        seccion: 3,
        titulo: `${f.name} (${f.module})`,
        status: f.status,
        cobLineas: Number(f.lines_cov || 0),
        estadoLbl: ST[f.status].rep,
        metricas: `Intentos: ${f.iterations}/3  |  Cob. líneas: ${f.lines_cov}%  |  Cob. ramas: ${f.branch_cov}%  |  Mutation Score: ${msLbl}  |  Tokens: ${f.tokens}`,
        controles: envolverLineaPdf(ctrlTxt, 88)
      });
    });
  }

  if (inc('expTrace')) {
    bloques.push({tipo: 'h2', seccion: 4, texto: '3. Trazas del Reviewer de los incidentes'});
    RUN.filter(f => f.diag || f.trace).forEach(f => {
      bloques.push({tipo: 'encabezado_bloque', seccion: 4, titulo: `${f.name} (${f.module})`, etiqueta: ST[f.status].rep, acento: 'incidente'});
      const txt = [f.diag, f.trace].filter(Boolean).join('\n');
      const lns = [];
      txt.split('\n').forEach(s => envolverLineaPdf(s, 84).forEach(l => lns.push(l)));
      lns.forEach((ln, idx) => bloques.push({tipo: 'linea_codigo', seccion: 4, texto: ln, acento: 'incidente', ultima: idx === lns.length - 1}));
      bloques.push({tipo: 'espacio', seccion: 4, alto: 6});
    });
  }

  if (inc('expCode')) {
    bloques.push({tipo: 'h2', seccion: 5, texto: '4. Código de las pruebas generadas'});
    RUN.forEach(f => {
      bloques.push({tipo: 'encabezado_bloque', seccion: 5, titulo: `tests/test_${f.name}.py (${f.module})`, etiqueta: 'PYTEST SUITE', acento: 'codigo'});
      const lns = [];
      String(f.code || '').split('\n').forEach(s => envolverLineaPdf(s, 84).forEach(l => lns.push(l)));
      lns.forEach((ln, idx) => bloques.push({tipo: 'linea_codigo', seccion: 5, texto: ln, acento: 'codigo', ultima: idx === lns.length - 1}));
      bloques.push({tipo: 'espacio', seccion: 5, alto: 6});
    });
  }

  if (inc('expContract')) {
    bloques.push({tipo: 'h2', seccion: 5, texto: '5. Contratos JSON del Planner'});
    RUN.forEach(f => {
      bloques.push({tipo: 'encabezado_bloque', seccion: 5, titulo: `${f.name} (${f.module})`, etiqueta: 'PLANNER CONTRACT JSON', acento: 'contrato'});
      const lns = [];
      JSON.stringify(f.contract, null, 2).split('\n').forEach(s => envolverLineaPdf(s, 84).forEach(l => lns.push(l)));
      lns.forEach((ln, idx) => bloques.push({tipo: 'linea_codigo', seccion: 5, texto: ln, acento: 'contrato', ultima: idx === lns.length - 1}));
      bloques.push({tipo: 'espacio', seccion: 5, alto: 6});
    });
  }

  const paginas = [], seccionesPagina = [], paginaInicioSeccion = {1: 0};
  let comandos = [], y = 774, margenInf = 48, seccionActual = 1;
  function nuevaPagina(sec){
    if (sec !== undefined) seccionActual = sec;
    if (comandos.length) {
      paginas.push(comandos);
      seccionesPagina.push(seccionActual);
    }
    const escId = escaparLiteralPdf(runId);
    comandos = [
      '0.06 0.09 0.16 rg 36 804 523 22 re f',
      '0.06 0.73 0.51 rg 36 804 4 22 re f',
      `BT /F2 8.5 Tf 1 1 1 rg 48 812 Td (QAgent v2.4  |  Informe Interactivo de Auditoria  |  Corrida #${escId}) Tj ET`,
      'BT /F1 7.8 Tf 0.70 0.78 0.90 rg 425 812 Td (Verificacion RN-07 Activa) Tj ET'
    ];
    y = 774;
  }
  function asegurar(h, sec){
    if (sec !== undefined) {
      seccionActual = sec;
      if (paginaInicioSeccion[sec] === undefined) paginaInicioSeccion[sec] = paginas.length;
    }
    if (y - h < margenInf) {
      nuevaPagina(seccionActual);
      if (sec !== undefined && paginaInicioSeccion[sec] === paginas.length - 1) paginaInicioSeccion[sec] = paginas.length;
    }
  }
  nuevaPagina(1);

  bloques.forEach(b => {
    const secB = b.seccion || seccionActual;
    if (secB !== seccionActual && paginaInicioSeccion[secB] === undefined) paginaInicioSeccion[secB] = paginas.length;
    seccionActual = secB;

    if (b.tipo === 'espacio') { y -= (b.alto || 8); return; }
    if (b.tipo === 'banner') {
      const h = 62; asegurar(h + 6, secB);
      const top = y, base = top - h;
      comandos.push(`0.08 0.12 0.22 rg 36 ${base.toFixed(1)} 523 ${h.toFixed(1)} re f`);
      comandos.push(`0.23 0.51 0.96 rg 36 ${(top - 3).toFixed(1)} 523 3 re f`);
      comandos.push(`0.06 0.45 0.33 rg 48 ${(top - 18).toFixed(1)} 295 11 re f`);
      comandos.push(`BT /F2 7.2 Tf 0.85 0.99 0.92 rg 54 ${(top - 15).toFixed(1)} Td (INFORME INTERACTIVO DE ANALISIS DE DATOS Y AUDITORIA) Tj ET`);
      comandos.push(`BT /F2 12.5 Tf 1 1 1 rg 48 ${(top - 33).toFixed(1)} Td (${escaparLiteralPdf(b.titulo)}) Tj ET`);
      comandos.push(`BT /F1 8.2 Tf 0.80 0.86 0.95 rg 48 ${(top - 46).toFixed(1)} Td (${escaparLiteralPdf(b.sub1)}) Tj ET`);
      comandos.push(`BT /F1 8.2 Tf 0.72 0.80 0.92 rg 48 ${(top - 56).toFixed(1)} Td (${escaparLiteralPdf(b.sub2)}) Tj ET`);
      y = base - 7; return;
    }
    if (b.tipo === 'panel_kpis') {
      const h = 50; asegurar(h + 6, secB);
      const top = y, base = top - h, wCard = 100, gap = 5.75;
      b.kpis.forEach((kpi, idx) => {
        const cx = 36 + idx * (wCard + gap);
        const ac = kpi.cumple ? '0.06 0.68 0.46' : '0.88 0.18 0.30';
        const bgP = kpi.cumple ? '0.84 0.96 0.89' : '0.99 0.88 0.90';
        const fgP = kpi.cumple ? '0.04 0.42 0.24' : '0.68 0.10 0.20';
        const lblP = kpi.cumple ? 'OK' : 'META';
        comandos.push(`0.98 0.99 1.00 rg ${cx.toFixed(1)} ${base.toFixed(1)} ${wCard} ${h} re f`);
        comandos.push(`0.83 0.87 0.93 RG 0.6 w ${cx.toFixed(1)} ${base.toFixed(1)} ${wCard} ${h} re S`);
        comandos.push(`${ac} rg ${cx.toFixed(1)} ${(top - 3).toFixed(1)} ${wCard} 3 re f`);
        comandos.push(`BT /F2 6.8 Tf 0.35 0.42 0.52 rg ${(cx + 6).toFixed(1)} ${(top - 12).toFixed(1)} Td (${escaparLiteralPdf(kpi.titulo)}) Tj ET`);
        comandos.push(`${bgP} rg ${(cx + 72).toFixed(1)} ${(top - 14).toFixed(1)} 23 9 re f`);
        comandos.push(`BT /F2 6 Tf ${fgP} rg ${(cx + 75).toFixed(1)} ${(top - 11.5).toFixed(1)} Td (${lblP}) Tj ET`);
        comandos.push(`BT /F2 11 Tf 0.08 0.12 0.22 rg ${(cx + 6).toFixed(1)} ${(top - 26).toFixed(1)} Td (${escaparLiteralPdf(kpi.valor)}) Tj ET`);
        comandos.push(`BT /F1 6.8 Tf 0.38 0.44 0.54 rg ${(cx + 6).toFixed(1)} ${(top - 36).toFixed(1)} Td (${escaparLiteralPdf(kpi.sub)}) Tj ET`);
        const wBar = 88, fillW = Math.max(3, Math.min(wBar, (kpi.pct / 100) * wBar));
        comandos.push(`0.88 0.91 0.96 rg ${(cx + 6).toFixed(1)} ${(base + 5).toFixed(1)} ${wBar} 4 re f`);
        comandos.push(`${ac} rg ${(cx + 6).toFixed(1)} ${(base + 5).toFixed(1)} ${fillW.toFixed(1)} 4 re f`);
      });
      y = base - 7; return;
    }
    if (b.tipo === 'ficha_meta') {
      const h = 10 + b.filas.length * 11.5; asegurar(h + 6, secB);
      const top = y, base = top - h;
      comandos.push(`0.96 0.97 0.99 rg 36 ${base.toFixed(1)} 523 ${h.toFixed(1)} re f`);
      comandos.push(`0.82 0.86 0.92 RG 0.6 w 36 ${base.toFixed(1)} 523 ${h.toFixed(1)} re S`);
      comandos.push(`0.23 0.51 0.96 rg 36 ${base.toFixed(1)} 3.5 ${h.toFixed(1)} re f`);
      let cy = top - 12;
      b.filas.forEach(([etq, val]) => {
        if (etq) comandos.push(`BT /F2 8 Tf 0.12 0.18 0.28 rg 46 ${cy.toFixed(1)} Td (${escaparLiteralPdf(etq)}) Tj ET`);
        comandos.push(`BT /F1 8 Tf 0.20 0.25 0.34 rg 128 ${cy.toFixed(1)} Td (${escaparLiteralPdf(val)}) Tj ET`);
        cy -= 11.5;
      });
      y = base - 7; return;
    }
    if (b.tipo === 'h2') {
      asegurar(34, secB); y -= 3;
      const base = y - 17;
      comandos.push(`0.92 0.95 0.99 rg 36 ${base.toFixed(1)} 523 17 re f`);
      comandos.push(`0.15 0.39 0.92 rg 36 ${base.toFixed(1)} 4 17 re f`);
      comandos.push(`BT /F2 10 Tf 0.08 0.14 0.26 rg 46 ${(base + 4.8).toFixed(1)} Td (${escaparLiteralPdf(b.texto)}) Tj ET`);
      y = base - 5; return;
    }
    if (b.tipo === 'tabla_cabecera') {
      asegurar(36, secB);
      const base = y - 16;
      comandos.push(`0.11 0.16 0.26 rg 36 ${base.toFixed(1)} 523 16 re f`);
      comandos.push(`BT /F2 8 Tf 1 1 1 rg 44 ${(base + 4.8).toFixed(1)} Td (METRICA DE AUDITORIA) Tj ET`);
      comandos.push(`BT /F2 8 Tf 1 1 1 rg 225 ${(base + 4.8).toFixed(1)} Td (RESULTADO OBTENIDO) Tj ET`);
      comandos.push(`BT /F2 8 Tf 1 1 1 rg 370 ${(base + 4.8).toFixed(1)} Td (META) Tj ET`);
      comandos.push(`BT /F2 8 Tf 1 1 1 rg 478 ${(base + 4.8).toFixed(1)} Td (ESTADO) Tj ET`);
      y = base; return;
    }
    if (b.tipo === 'tabla_metrica') {
      asegurar(20, secB);
      const base = y - 18, bg = b.par ? '0.96 0.98 1.00' : '1 1 1';
      comandos.push(`${bg} rg 36 ${base.toFixed(1)} 523 18 re f`);
      comandos.push(`0.85 0.89 0.94 RG 0.5 w 36 ${base.toFixed(1)} 523 18 re S`);
      comandos.push(`BT /F2 8.2 Tf 0.10 0.15 0.24 rg 44 ${(base + 5.8).toFixed(1)} Td (${escaparLiteralPdf(b.nombre)}) Tj ET`);
      comandos.push(`BT /F1 8.2 Tf 0.14 0.19 0.28 rg 225 ${(base + 5.8).toFixed(1)} Td (${escaparLiteralPdf(b.resultado)}) Tj ET`);
      comandos.push(`BT /F1 8.2 Tf 0.28 0.34 0.44 rg 370 ${(base + 5.8).toFixed(1)} Td (${escaparLiteralPdf(b.meta)}) Tj ET`);
      const pillBg = b.cumple ? '0.84 0.96 0.89' : '0.99 0.88 0.90';
      const pillFg = b.cumple ? '0.04 0.42 0.24' : '0.68 0.10 0.20';
      comandos.push(`${pillBg} rg 468 ${(base + 3.0).toFixed(1)} 82 12 re f`);
      comandos.push(`BT /F2 7.5 Tf ${pillFg} rg 476 ${(base + 6.2).toFixed(1)} Td (${escaparLiteralPdf(b.estado)}) Tj ET`);
      y = base; return;
    }
    if (b.tipo === 'nota_agentes') {
      const h = 7 + b.lineas.length * 11; asegurar(h + 5, secB);
      const base = y - h;
      comandos.push(`0.94 0.96 0.99 rg 36 ${base.toFixed(1)} 523 ${h.toFixed(1)} re f`);
      comandos.push(`0.85 0.89 0.94 RG 0.5 w 36 ${base.toFixed(1)} 523 ${h.toFixed(1)} re S`);
      let cy = y - 10.5;
      b.lineas.forEach(ln => {
        comandos.push(`BT /F1 7.8 Tf 0.22 0.28 0.38 rg 44 ${cy.toFixed(1)} Td (${escaparLiteralPdf(ln)}) Tj ET`);
        cy -= 11;
      });
      y = base - 7; return;
    }
    if (b.tipo === 'panel_graficas') {
      const fns = b.funciones;
      const altoG = Math.max(136, 38 + fns.length * 17), altoIns = 44;
      asegurar(altoG + altoIns + 12, secB);
      paginaInicioSeccion[2] = paginas.length;
      const top = y, base = top - altoG;

      // Gráfica 1: Cobertura y Mutation por función
      comandos.push(`0.98 0.99 1.00 rg 36 ${base.toFixed(1)} 266 ${altoG.toFixed(1)} re f`);
      comandos.push(`0.82 0.86 0.92 RG 0.6 w 36 ${base.toFixed(1)} 266 ${altoG.toFixed(1)} re S`);
      comandos.push(`0.11 0.16 0.26 rg 36 ${(top - 16).toFixed(1)} 266 16 re f`);
      comandos.push(`BT /F2 7.6 Tf 1 1 1 rg 44 ${(top - 11).toFixed(1)} Td (GRAFICA 1: COBERTURA Y MUTATION POR FUNCION) Tj ET`);
      const ly = top - 26;
      comandos.push(`0.23 0.51 0.96 rg 44 ${ly.toFixed(1)} 7 5 re f`);
      comandos.push(`BT /F1 6.6 Tf 0.25 0.30 0.40 rg 54 ${ly.toFixed(1)} Td (Lineas) Tj ET`);
      comandos.push(`0.02 0.71 0.83 rg 88 ${ly.toFixed(1)} 7 5 re f`);
      comandos.push(`BT /F1 6.6 Tf 0.25 0.30 0.40 rg 98 ${ly.toFixed(1)} Td (Ramas) Tj ET`);
      comandos.push(`0.55 0.36 0.96 rg 132 ${ly.toFixed(1)} 7 5 re f`);
      comandos.push(`BT /F1 6.6 Tf 0.25 0.30 0.40 rg 142 ${ly.toFixed(1)} Td (Mutation) Tj ET`);
      comandos.push(`BT /F2 6.6 Tf 0.04 0.48 0.30 rg 202 ${ly.toFixed(1)} Td (| Meta >= 60%) Tj ET`);

      const barX = 126, barW = 132, metaX = barX + 0.60 * barW;
      let fy = top - 38;
      fns.forEach(fnItem => {
        comandos.push(`BT /F2 7 Tf 0.12 0.18 0.28 rg 42 ${(fy - 4).toFixed(1)} Td (${escaparLiteralPdf(fnItem.nombre)}) Tj ET`);
        comandos.push(`0.91 0.94 0.98 rg ${barX} ${(fy - 8).toFixed(1)} ${barW} 11 re f`);
        const wLin = Math.max(2, Math.min(barW, (fnItem.lineas / 100) * barW));
        const wRam = Math.max(2, Math.min(barW, (fnItem.ramas / 100) * barW));
        comandos.push(`0.23 0.51 0.96 rg ${barX} ${(fy - 0.5).toFixed(1)} ${wLin.toFixed(1)} 3.2 re f`);
        comandos.push(`0.02 0.71 0.83 rg ${barX} ${(fy - 4.2).toFixed(1)} ${wRam.toFixed(1)} 3.2 re f`);
        if (fnItem.tieneMs) {
          const wMs = Math.max(2, Math.min(barW, (fnItem.ms / 100) * barW));
          comandos.push(`0.55 0.36 0.96 rg ${barX} ${(fy - 7.9).toFixed(1)} ${wMs.toFixed(1)} 3.2 re f`);
        }
        comandos.push(`BT /F1 6.5 Tf 0.20 0.26 0.36 rg ${(barX + barW + 4).toFixed(1)} ${(fy - 4).toFixed(1)} Td (${Math.round(fnItem.lineas)}%/${Math.round(fnItem.ramas)}%) Tj ET`);
        fy -= 16.5;
      });
      comandos.push(`0.06 0.68 0.46 RG 0.8 w ${metaX.toFixed(1)} ${(base + 6).toFixed(1)} m ${metaX.toFixed(1)} ${(top - 30).toFixed(1)} l S`);

      // Gráfica 2: Distribución de estados
      const altoD1 = 66, baseD1 = top - altoD1;
      comandos.push(`0.98 0.99 1.00 rg 310 ${baseD1.toFixed(1)} 249 ${altoD1} re f`);
      comandos.push(`0.82 0.86 0.92 RG 0.6 w 310 ${baseD1.toFixed(1)} 249 ${altoD1} re S`);
      comandos.push(`0.11 0.16 0.26 rg 310 ${(top - 16).toFixed(1)} 249 16 re f`);
      comandos.push(`BT /F2 7.6 Tf 1 1 1 rg 318 ${(top - 11).toFixed(1)} Td (GRAFICA 2: DISTRIBUCION DE ESTADOS DE AUDITORIA) Tj ET`);
      const est = b.estados, totFn = b.totalFn, sx = 318, anchoSt = 233;
      const segmentos = [
        ['Aprobadas', est.passed || 0, '0.06 0.68 0.46'],
        ['Laundering', est.rejected_laundering || 0, '0.88 0.18 0.30'],
        ['Bug Oraculo', est.rejected_oracle || 0, '0.72 0.16 0.82'],
        ['Flaky/Otros', est.flaky || 0, '0.85 0.48 0.04'],
      ];
      comandos.push(`0.90 0.93 0.97 rg ${sx} ${(top - 32).toFixed(1)} ${anchoSt} 10 re f`);
      let curX = sx;
      segmentos.forEach(([_, cnt, col]) => {
        if (cnt > 0) {
          const segW = (cnt / totFn) * anchoSt;
          comandos.push(`${col} rg ${curX.toFixed(1)} ${(top - 32).toFixed(1)} ${segW.toFixed(1)} 10 re f`);
          curX += segW;
        }
      });
      segmentos.forEach(([nomS, cnt, col], idxS) => {
        const colX = 318 + (idxS % 2) * 118;
        const rowY = idxS < 2 ? top - 45 : top - 57;
        const pctS = Math.round((cnt / totFn) * 100);
        comandos.push(`${col} rg ${colX} ${rowY.toFixed(1)} 6 6 re f`);
        comandos.push(`BT /F1 7 Tf 0.18 0.24 0.34 rg ${colX + 10} ${rowY.toFixed(1)} Td (${escaparLiteralPdf(`${nomS}: ${cnt} (${pctS}%)`)}) Tj ET`);
      });

      // Gráfica 3: Tokens y costo por agente
      const topD2 = baseD1 - 6, altoD2 = topD2 - base;
      comandos.push(`0.98 0.99 1.00 rg 310 ${base.toFixed(1)} 249 ${altoD2.toFixed(1)} re f`);
      comandos.push(`0.82 0.86 0.92 RG 0.6 w 310 ${base.toFixed(1)} 249 ${altoD2.toFixed(1)} re S`);
      comandos.push(`0.11 0.16 0.26 rg 310 ${(topD2 - 15).toFixed(1)} 249 15 re f`);
      comandos.push(`BT /F2 7.5 Tf 1 1 1 rg 318 ${(topD2 - 10.5).toFixed(1)} Td (GRAFICA 3: TOKENS Y COSTO POR AGENTE IA) Tj ET`);
      const colAg = ['0.39 0.40 0.95', '0.96 0.62 0.04', '0.06 0.73 0.51'];
      let ay = topD2 - 27;
      b.agentes.forEach((agItem, idxA) => {
        const cA = colAg[idxA % colAg.length];
        comandos.push(`BT /F2 7.2 Tf 0.14 0.20 0.30 rg 318 ${ay.toFixed(1)} Td (${escaparLiteralPdf(agItem.nombre)}) Tj ET`);
        comandos.push(`0.90 0.93 0.97 rg 368 ${(ay - 1).toFixed(1)} 96 7 re f`);
        const wAg = Math.max(3, Math.min(96, (agItem.pct / 100) * 96));
        comandos.push(`${cA} rg 368 ${(ay - 1).toFixed(1)} ${wAg.toFixed(1)} 7 re f`);
        comandos.push(`BT /F1 6.8 Tf 0.22 0.28 0.38 rg 468 ${ay.toFixed(1)} Td (${escaparLiteralPdf(`${Math.round(agItem.pct)}% | US$ ${agItem.usd.toFixed(4)}`)}) Tj ET`);
        ay -= 14;
      });

      // Síntesis del Experto en Análisis de Datos
      const topIns = base - 5, baseIns = topIns - altoIns;
      comandos.push(`0.93 0.97 1.00 rg 36 ${baseIns.toFixed(1)} 523 ${altoIns} re f`);
      comandos.push(`0.75 0.85 0.96 RG 0.6 w 36 ${baseIns.toFixed(1)} 523 ${altoIns} re S`);
      comandos.push(`0.02 0.52 0.78 rg 36 ${baseIns.toFixed(1)} 4 ${altoIns} re f`);
      comandos.push(`BT /F2 7.8 Tf 0.05 0.28 0.48 rg 46 ${(topIns - 11).toFixed(1)} Td (SINTESIS DEL EXPERTO EN ANALISIS DE DATOS - HALLAZGOS ESTADISTICOS CLAVE) Tj ET`);
      let iy = topIns - 21.5;
      b.insights.forEach(insLn => {
        comandos.push(`BT /F1 7.4 Tf 0.14 0.22 0.34 rg 48 ${iy.toFixed(1)} Td (- ${escaparLiteralPdf(insLn)}) Tj ET`);
        iy -= 9.5;
      });
      y = baseIns - 8; return;
    }
    if (b.tipo === 'tarjeta_funcion') {
      const h = 38 + b.controles.length * 11; asegurar(h + 6, secB);
      const top = y, base = top - h;
      const [acento, badgeBg, badgeFg] = coloresEstadoPdf(b.status);
      comandos.push(`0.98 0.99 1.00 rg 36 ${base.toFixed(1)} 523 ${h.toFixed(1)} re f`);
      comandos.push(`0.83 0.87 0.93 RG 0.6 w 36 ${base.toFixed(1)} 523 ${h.toFixed(1)} re S`);
      comandos.push(`${acento} rg 36 ${base.toFixed(1)} 4 ${h.toFixed(1)} re f`);
      comandos.push(`BT /F2 9.2 Tf 0.08 0.12 0.20 rg 46 ${(top - 13).toFixed(1)} Td (${escaparLiteralPdf(b.titulo)}) Tj ET`);
      const cobL = Math.max(0, Math.min(100, b.cobLineas || 0));
      comandos.push(`0.88 0.92 0.97 rg 322 ${(top - 13).toFixed(1)} 80 5 re f`);
      comandos.push(`${acento} rg 322 ${(top - 13).toFixed(1)} ${((cobL / 100) * 80).toFixed(1)} 5 re f`);
      comandos.push(`${badgeBg} rg 412 ${(top - 16.5).toFixed(1)} 140 13 re f`);
      comandos.push(`BT /F2 7.2 Tf ${badgeFg} rg 418 ${(top - 12.5).toFixed(1)} Td (${escaparLiteralPdf(b.estadoLbl)}) Tj ET`);
      comandos.push(`0.93 0.95 0.98 rg 44 ${(top - 29).toFixed(1)} 508 12 re f`);
      comandos.push(`BT /F1 8 Tf 0.16 0.22 0.32 rg 48 ${(top - 25.5).toFixed(1)} Td (${escaparLiteralPdf(b.metricas)}) Tj ET`);
      let cy = top - 40;
      b.controles.forEach(ln => {
        comandos.push(`BT /F1 7.8 Tf 0.26 0.31 0.40 rg 46 ${cy.toFixed(1)} Td (${escaparLiteralPdf(ln)}) Tj ET`);
        cy -= 11;
      });
      y = base - 6; return;
    }
    if (b.tipo === 'encabezado_bloque') {
      asegurar(32, secB);
      const base = y - 16;
      const [bgH, barC, txtC] = b.acento === 'incidente'
        ? ['0.99 0.92 0.93', '0.88 0.18 0.30', '0.48 0.08 0.16']
        : (b.acento === 'contrato' ? ['0.91 0.95 0.99', '0.15 0.39 0.92', '0.08 0.22 0.48'] : ['0.94 0.92 0.99', '0.52 0.26 0.88', '0.26 0.12 0.48']);
      comandos.push(`${bgH} rg 36 ${base.toFixed(1)} 523 16 re f`);
      comandos.push(`${barC} rg 36 ${base.toFixed(1)} 3.5 16 re f`);
      comandos.push(`BT /F2 8.8 Tf ${txtC} rg 45 ${(base + 4.5).toFixed(1)} Td (${escaparLiteralPdf(b.titulo)}) Tj ET`);
      comandos.push(`BT /F2 7.2 Tf ${txtC} rg 420 ${(base + 5).toFixed(1)} Td (${escaparLiteralPdf(b.etiqueta)}) Tj ET`);
      y = base; return;
    }
    if (b.tipo === 'linea_codigo') {
      asegurar(12, secB);
      const base = y - 11;
      const barC = b.acento === 'incidente' ? '0.88 0.18 0.30' : (b.acento === 'contrato' ? '0.15 0.39 0.92' : '0.52 0.26 0.88');
      comandos.push(`0.96 0.97 0.99 rg 36 ${base.toFixed(1)} 523 11.2 re f`);
      comandos.push(`${barC} rg 36 ${base.toFixed(1)} 2.5 11.2 re f`);
      comandos.push(`0.84 0.88 0.93 RG 0.4 w 559 ${base.toFixed(1)} m 559 ${y.toFixed(1)} l S`);
      if (b.ultima) comandos.push(`0.84 0.88 0.93 RG 0.4 w 36 ${base.toFixed(1)} m 559 ${base.toFixed(1)} l S`);
      comandos.push(`BT /F3 7.8 Tf 0.14 0.18 0.26 rg 45 ${(base + 3).toFixed(1)} Td (${escaparLiteralPdf(b.texto)}) Tj ET`);
      y = base; return;
    }
  });
  if (comandos.length) {
    paginas.push(comandos);
    seccionesPagina.push(seccionActual);
  }

  const objetos = [], addObj = body => { objetos.push(body); return objetos.length; };
  const idCatalog = addObj(''), idPages = addObj('');
  const idFontReg = addObj('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
  const idFontBold = addObj('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');
  const idFontMono = addObj('<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>');

  const idsPaginas = [], idsStreams = [];
  paginas.forEach((cmds, idx) => {
    const secActiva = seccionesPagina[idx] || 1;
    PESTANAS_PDF_JS.forEach(([secId, etqTab, tx, tw]) => {
      const esActiva = secId === secActiva;
      const bgT = esActiva ? '0.15 0.39 0.92' : '0.91 0.94 0.98';
      const fgT = esActiva ? '1 1 1' : '0.22 0.28 0.38';
      cmds.push(`${bgT} rg ${tx.toFixed(1)} 785 ${tw.toFixed(1)} 15 re f`);
      if (esActiva) cmds.push(`0.06 0.73 0.51 rg ${tx.toFixed(1)} 785 ${tw.toFixed(1)} 2 re f`);
      cmds.push(`BT /F2 7.2 Tf ${fgT} rg ${(tx + 6).toFixed(1)} 790 Td (${escaparLiteralPdf(etqTab)}) Tj ET`);
    });
    const pieIzq = escaparLiteralPdf('QAgent Autonomous Test Engine  |  Informe Interactivo con Pestanas Clicables  |  Sin claves de IA (RN-07)');
    const pieDer = escaparLiteralPdf(`Pagina ${idx + 1} de ${paginas.length}`);
    cmds.push('0.84 0.88 0.93 RG 0.6 w 36 38 m 559 38 l S');
    cmds.push(`BT /F1 7.5 Tf 0.45 0.50 0.58 rg 36 26 Td (${pieIzq}) Tj ET`);
    cmds.push(`BT /F2 8 Tf 0.30 0.36 0.46 rg 492 26 Td (${pieDer}) Tj ET`);
    const stream = cmds.join('\n') + '\n';
    const idStream = addObj(`<< /Length ${stream.length} >>\nstream\n${stream}endstream`);
    const idPag = addObj('');
    idsStreams.push(idStream);
    idsPaginas.push(idPag);
  });

  const idsAnnots = PESTANAS_PDF_JS.map(([secId, _, tx, tw]) => {
    let pagIdx = paginaInicioSeccion[secId] !== undefined ? paginaInicioSeccion[secId] : 0;
    pagIdx = Math.max(0, Math.min(idsPaginas.length - 1, pagIdx));
    const idPagDest = idsPaginas[pagIdx];
    return addObj(`<< /Type /Annot /Subtype /Link /Rect [${tx.toFixed(1)} 785 ${(tx + tw).toFixed(1)} 800] /Border [0 0 0] /Dest [${idPagDest} 0 R /XYZ null 842 null] >>`);
  });

  const annotsStr = idsAnnots.map(id => `${id} 0 R`).join(' ');
  idsPaginas.forEach((idPag, idx) => {
    objetos[idPag - 1] = `<< /Type /Page /Parent ${idPages} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 ${idFontReg} 0 R /F2 ${idFontBold} 0 R /F3 ${idFontMono} 0 R >> >> /Contents ${idsStreams[idx]} 0 R /Annots [${annotsStr}] >>`;
  });

  const idOutlines = addObj('');
  const idsOutlineItems = PESTANAS_PDF_JS.map(() => addObj(''));
  PESTANAS_PDF_JS.forEach(([secId, etqTab], iTab) => {
    let pagIdx = paginaInicioSeccion[secId] !== undefined ? paginaInicioSeccion[secId] : 0;
    pagIdx = Math.max(0, Math.min(idsPaginas.length - 1, pagIdx));
    const idPagDest = idsPaginas[pagIdx];
    const prevStr = iTab > 0 ? ` /Prev ${idsOutlineItems[iTab - 1]} 0 R` : '';
    const nextStr = iTab + 1 < idsOutlineItems.length ? ` /Next ${idsOutlineItems[iTab + 1]} 0 R` : '';
    objetos[idsOutlineItems[iTab] - 1] = `<< /Title (${escaparLiteralPdf(etqTab)}) /Parent ${idOutlines} 0 R${prevStr}${nextStr} /Dest [${idPagDest} 0 R /XYZ null 842 null] >>`;
  });
  objetos[idOutlines - 1] = `<< /Type /Outlines /First ${idsOutlineItems[0]} 0 R /Last ${idsOutlineItems[idsOutlineItems.length - 1]} 0 R /Count ${idsOutlineItems.length} >>`;

  objetos[idCatalog - 1] = `<< /Type /Catalog /Pages ${idPages} 0 R /Outlines ${idOutlines} 0 R /PageMode /UseOutlines >>`;
  objetos[idPages - 1] = `<< /Type /Pages /Kids [${idsPaginas.map(id => id + ' 0 R').join(' ')}] /Count ${idsPaginas.length} >>`;

  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objetos.forEach((body, idx) => { offsets.push(pdf.length); pdf += `${idx + 1} 0 obj\n${body}\nendobj\n`; });
  const xrefPos = pdf.length;
  pdf += `xref\n0 ${objetos.length + 1}\n0000000000 65535 f \n`;
  for (let i = 1; i <= objetos.length; i++) pdf += String(offsets[i]).padStart(10, '0') + ' 00000 n \n';
  pdf += `trailer\n<< /Size ${objetos.length + 1} /Root ${idCatalog} 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`;

  const bytes = new Uint8Array(pdf.length);
  for (let i = 0; i < pdf.length; i++) bytes[i] = pdf.charCodeAt(i) & 0xff;
  return bytes;
}


async function doExport(){
  const api = window.pywebview && window.pywebview.api;
  if (api && api.exportar_informe) {
    try {
      const r = await api.exportar_informe(
        proyectoBaseExportar(),
        runIdExportar(),
        expFmt,
        opcionesExportar(),
        expCustomDir
      );
      if (!r || !r.ok) {
        toastError(escHtml((r && r.motivo) || 'No se pudo exportar el informe.'));
        return;
      }
      closeModal();
      toast(`Informe guardado en <span class="mono">${escHtml(r.ruta)}</span>`);
      return;
    } catch (err) {
      toastError('Error al exportar el informe: ' + escHtml(String(err)));
      return;
    }
  }

  const name = $('expName').textContent;
  const dir = String($('expPath').value || '').replace(/[\\\/]+$/, '');
  const path = dir + '\\' + name;
  const opts = opcionesExportar();
  if(expFmt==='pdf') download(name, buildPdfBytes(), 'application/pdf');
  if(expFmt==='md') download(name, buildMarkdown(), 'text/markdown');
  if(expFmt==='html') download(name, buildHtmlInteractivo(opts), 'text/html');
  if(expFmt==='json') {
    const funciones = opts.detalle ? RUN.map(f => {
      const {code, logs, cmp, diag, trace, contract, ...base} = f;
      if (opts.trazas && trace) base.trace = trace;
      if (opts.codigo && code) base.code = code;
      if (opts.contratos && contract) base.contract = contract;
      return base;
    }) : [];
    download(name, JSON.stringify({run_id:RUN_ID, date:RUN_DATE, metrics:metrics(), opciones:opts, functions:funciones}, null, 2), 'application/json');
  }
  closeModal();
  toast(`Informe descargado como <span class="mono">${escHtml(name)}</span> (ruta del proyecto: <span class="mono">${escHtml(path)}</span>)`);
}

function buildHtmlInteractivo(opts){
  const m = metrics(), runId = runIdExportar();
  const inc = id => opts ? opts[id] : true;
  const repo = (document.querySelector('.repoLbl') && document.querySelector('.repoLbl').textContent) || projectPath || 'proyecto';
  const rama = ($('branchLbl') && $('branchLbl').textContent) || 'main';
  const ok = b => b ? '<span class="pill pass">✓ Cumple</span>' : '<span class="pill fail">✗ No cumple</span>';
  const pctH = (v,d=1) => Number(v).toFixed(d)+'%';

  const stColors = {
    passed: {bg:'\x23ecfdf5', border:'\x2310b981', text:'\x23065f46', dot:'\x2310b981'},
    rejected_laundering: {bg:'\x23fff1f2', border:'\x23f43f5e', text:'\x239f1239', dot:'\x23f43f5e'},
    rejected_oracle: {bg:'\x23faf5ff', border:'\x23a855f7', text:'\x236b21a8', dot:'\x23a855f7'},
    flaky: {bg:'\x23fffbeb', border:'\x23f59e0b', text:'\x2392400e', dot:'\x23f59e0b'},
  };
  function stBadge(f){
    const c = stColors[f.status] || stColors.flaky;
    return `<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 11px;border-radius:20px;background:${c.bg};border:1.5px solid ${c.border};color:${c.text};font-size:11.5px;font-weight:700">`
      + `<span style="width:7px;height:7px;border-radius:50%;background:${c.dot}"></span>${escHtml(ST[f.status]?.rep||f.status)}</span>`;
  }

  const statusCounts = {};
  RUN.forEach(f => { statusCounts[f.status] = (statusCounts[f.status]||0) + 1; });
  const statusLabels = Object.keys(statusCounts);
  const statusValues = Object.values(statusCounts);
  const statusColors = statusLabels.map(s => stColors[s]?.dot || '\x2394a3b8');

  const kpiCardsHtml = [
    {lbl:'Pass Rate', val:pctH(m.pass), sub:`${m.ok} de ${m.n} funciones aprobadas`, bar:m.pass, ok:m.pass>=META.pass[0]},
    {lbl:'Cobertura Líneas / Ramas', val:pctH(m.lines), sub:`Ramas: ${pctH(m.branch)} (meta ≥ ${META.lines}%)`, bar:m.lines, ok:m.lines>=META.lines},
    {lbl:'Iteraciones Promedio', val:m.iter.toFixed(2), sub:`Meta ≤ ${META.iter} (máx. 3 intentos)`, bar:Math.max(10,(1-(m.iter-1)/2)*100), ok:m.iter<=META.iter},
    {lbl:'Costo y Tokens', val:`US$ ${m.usd.toFixed(4)}`, sub:`${m.tokens.toLocaleString('es-PE')} tokens · S/ ${m.pen.toFixed(2)}`, bar:Math.min(100,(m.pen/TOPE_PEN)*100), ok:m.pen<=TOPE_PEN},
    {lbl:'Mutation Score', val:pctH(m.ms), sub:`${m.crit} funciones críticas (meta ≥ ${META.ms}%)`, bar:m.ms, ok:m.ms>=META.ms},
  ].map(k => `<div class="kpi-card" style="border-top:4px solid ${k.ok?'\x2310b981':'\x23f43f5e'}">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <span class="kpi-lbl">${escHtml(k.lbl)}</span>
      <span class="pill ${k.ok?'pass':'fail'}" style="font-size:10.5px;padding:2px 8px">${k.ok?'CUMPLE':'NO CUMPLE'}</span>
    </div>
    <div class="kpi-val">${escHtml(k.val)}</div>
    <div class="kpi-sub">${escHtml(k.sub)}</div>
    <div class="kpi-bar-bg"><div class="kpi-bar-fill" style="width:${Math.max(4,Math.min(100,k.bar)).toFixed(0)}%;background:${k.ok?'\x2310b981':'\x23f43f5e'}"></div></div>
  </div>`).join('');

  const funcionCards = RUN.map(f => {
    const c = stColors[f.status] || stColors.flaky;
    const msLbl = f.mutation_score === null ? 'N/A (no crítica)' : f.mutation_score+'%';
    return `<div class="fn-card" data-status="${escHtml(f.status)}" data-name="${escHtml((f.name+' '+f.module).toLowerCase())}" style="border:1.5px solid ${c.border};border-left:5px solid ${c.border};background:\x23fff;border-radius:12px;padding:15px 18px;margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <div>
          <span style="font-weight:700;font-size:14.5px;color:\x230f172a">${escHtml(f.name)}</span>
          <span style="font-size:12px;color:\x2364748b;margin-left:8px">${escHtml(f.module)}</span>
        </div>
        ${stBadge(f)}
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:16px;margin-top:10px;font-size:12.5px;color:\x23334155">
        <span>⟳ <b>Intentos:</b> ${f.iterations}/3</span>
        <span>📊 <b>Cob. líneas:</b> ${f.lines_cov}%</span>
        <span>🌿 <b>Cob. ramas:</b> ${f.branch_cov}%</span>
        <span>🧬 <b>Mutation Score:</b> ${msLbl}</span>
        <span>💬 <b>Tokens:</b> ${(f.tokens||0).toLocaleString('es-PE')}</span>
      </div>
      <div style="margin-top:9px;font-size:11.5px;color:\x23475569;display:flex;flex-wrap:wrap;gap:12px">
        <span>${f.checks?.syntax?'✅':'❌'} Sin errores de sintaxis</span>
        <span>${f.checks?.sandbox?'✅':'❌'} Sandbox limpio</span>
        <span>${f.checks?.assertions_intact?'✅':'❌'} Aserciones íntegras</span>
        <span>${f.checks?.cov_met?'✅':'❌'} Cobertura ≥60%</span>
        <span>${f.checks?.ms_met===null?'➖ Mutation N/A':(f.checks?.ms_met?'✅':'❌')+' Mutation Score ≥60%'}</span>
      </div>
    </div>`;
  }).join('');

  const incidentesCards = RUN.filter(f => f.diag || f.trace).map(f => {
    const c = stColors[f.status] || stColors.rejected_laundering;
    return `<div style="border:1.5px solid ${c.border};border-radius:12px;overflow:hidden;margin-bottom:14px;background:\x23fff">
      <div style="padding:12px 16px;background:${c.bg};display:flex;justify-content:space-between;align-items:center">
        <b>${escHtml(f.name)} <span style="font-weight:400;color:\x2364748b">(${escHtml(f.module)})</span></b>
        ${stBadge(f)}
      </div>
      <div style="padding:14px 16px">
        <p style="font-size:13px;color:\x23334155;margin-bottom:8px">${escHtml(f.diag||'')}</p>
        ${f.trace ? `<pre style="padding:12px;background:\x230f172a;color:\x23e2e8f0;border-radius:8px;font-size:11.5px;overflow-x:auto;white-space:pre-wrap">${escHtml(f.trace)}</pre>` : ''}
      </div>
    </div>`;
  }).join('');

  const codigoContratosCards = RUN.map(f => `<div style="border:1px solid \x23e2e8f0;border-radius:12px;padding:14px 16px;margin-bottom:12px;background:\x23fff">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <b>tests/test_${escHtml(f.name)}.py <span style="font-weight:400;color:\x2364748b">(${escHtml(f.module)})</span></b>
      ${stBadge(f)}
    </div>
    ${inc('codigo') ? `<details open style="margin-bottom:8px"><summary style="cursor:pointer;font-size:12.5px;font-weight:600;color:\x234f46e5">🧪 Suite Pytest Generada</summary><pre style="margin-top:8px;padding:12px;background:\x231e1b4b;color:\x23e0e7ff;border-radius:8px;font-size:11.5px;overflow-x:auto">${escHtml(f.code||'')}</pre></details>` : ''}
    ${inc('contratos') ? `<details><summary style="cursor:pointer;font-size:12.5px;font-weight:600;color:\x230284c7">📐 Contrato JSON del Planner</summary><pre style="margin-top:8px;padding:12px;background:\x230c1a2e;color:\x237dd3fc;border-radius:8px;font-size:11.5px;overflow-x:auto">${escHtml(JSON.stringify(f.contract,null,2))}</pre></details>` : ''}
  </div>`).join('');

  const metricsRows = [
    ['Pass Rate', pctH(m.pass)+` (${m.ok}/${m.n} funciones)`, `≥ ${META.pass[0]}%`, m.pass >= META.pass[0]],
    ['Cobertura de líneas / ramas', pctH(m.lines)+' / '+pctH(m.branch), `≥ ${META.lines}% líneas`, m.lines >= META.lines],
    ['Iteraciones promedio', m.iter.toFixed(2), `≤ ${META.iter} (máx. 3)`, m.iter <= META.iter],
    ['Tokens y costo de la corrida', `${m.tokens.toLocaleString('es-PE')} tokens · US$ ${m.usd.toFixed(4)}`, `≤ S/ ${TOPE_PEN.toFixed(2)}`, m.pen <= TOPE_PEN],
    [`Mutation Score (${m.crit} críticas)`, pctH(m.ms), `≥ ${META.ms}%`, m.ms >= META.ms],
  ].map(([nm,res,meta,cumple],i) => `<tr style="background:${i%2?'\x23f8fafc':'\x23fff'}">
    <td style="padding:11px 14px;font-weight:600;color:\x231e293b;border-bottom:1px solid \x23e2e8f0">${escHtml(nm)}</td>
    <td style="padding:11px 14px;color:\x23334155;border-bottom:1px solid \x23e2e8f0">${escHtml(res)}</td>
    <td style="padding:11px 14px;color:\x2364748b;border-bottom:1px solid \x23e2e8f0">${escHtml(meta)}</td>
    <td style="padding:11px 14px;text-align:center;border-bottom:1px solid \x23e2e8f0">${ok(cumple)}</td>
  </tr>`).join('');

  const cumpleCount = [m.pass >= META.pass[0], m.lines >= META.lines, m.iter <= META.iter, m.pen <= TOPE_PEN, m.ms >= META.ms].filter(Boolean).length;
  const scoreColor = cumpleCount >= 4 ? '\x2310b981' : (cumpleCount >= 3 ? '\x23f59e0b' : '\x23f43f5e');

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Informe Interactivo QAgent — Corrida \x23${escHtml(runId)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"><\/script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:\x23f1f5f9;color:\x231e293b;min-height:100vh}
  .topbar{background:linear-gradient(135deg,\x230f172a 0%,\x231e3a5f 60%,\x231d4ed8 100%);padding:26px 36px;color:\x23fff;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
  .topbar-brand{display:flex;align-items:center;gap:14px}
  .topbar-logo{width:46px;height:46px;background:linear-gradient(135deg,\x233b82f6,\x2310b981);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800}
  .topbar-title h1{font-size:19px;font-weight:800;letter-spacing:-0.3px}
  .topbar-title p{font-size:13px;color:\x23cbd5e1;margin-top:3px}
  .score-badge{background:rgb\x61(255,255,255,0.1);border:1.5px solid rgb\x61(255,255,255,0.22);border-radius:14px;padding:10px 22px;text-align:center}
  .score-badge .num{font-size:30px;font-weight:800;color:${scoreColor};line-height:1}
  .score-badge .lbl{font-size:11px;color:\x23cbd5e1;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px}
  .nav-tabs{background:\x230f172a;padding:0 36px;display:flex;gap:6px;overflow-x:auto;border-bottom:2px solid \x231e293b;position:sticky;top:0;z-index:90}
  .nav-tab{padding:13px 18px;border:none;background:transparent;color:\x2394a3b8;font-size:13px;font-weight:700;cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap;transition:.15s}
  .nav-tab:hover{color:\x23fff;background:rgb\x61(255,255,255,0.04)}
  .nav-tab.active{color:\x23fff;border-bottom-color:\x233b82f6;background:rgb\x61(59,130,246,0.12)}
  .container{max-width:1140px;margin:0 auto;padding:24px}
  .tab-pane{display:none}.tab-pane.active{display:block}
  .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(195px,1fr));gap:14px;margin-bottom:20px}
  .kpi-card{background:\x23fff;border:1px solid \x23e2e8f0;border-radius:12px;padding:15px 16px;box-shadow:0 1px 3px rgb\x61(0,0,0,.05)}
  .kpi-lbl{font-size:11px;font-weight:700;color:\x2364748b;text-transform:uppercase;letter-spacing:.5px}
  .kpi-val{font-size:24px;font-weight:800;color:\x230f172a;margin:4px 0}
  .kpi-sub{font-size:12px;color:\x2364748b;margin-bottom:10px}
  .kpi-bar-bg{height:6px;background:\x23e2e8f0;border-radius:99px;overflow:hidden}
  .kpi-bar-fill{height:100%;border-radius:99px}
  .insight-box{background:linear-gradient(135deg,\x23eff6ff,\x23f0fdf4);border:1.5px solid \x2393c5fd;border-left:5px solid \x232563eb;border-radius:12px;padding:16px 20px;margin-bottom:20px}
  .insight-box h3{font-size:13.5px;font-weight:800;color:\x231e3a8a;margin-bottom:8px;text-transform:uppercase;letter-spacing:.4px}
  .insight-box ul{padding-left:18px;font-size:13px;color:\x231e293b;line-height:1.6}
  .meta-bar{background:\x23fff;border:1px solid \x23e2e8f0;border-radius:12px;padding:16px 20px;display:flex;flex-wrap:wrap;gap:16px;margin-bottom:20px}
  .meta-item{font-size:13px;color:\x2364748b}.meta-item b{color:\x231e293b}
  .card{background:\x23fff;border:1px solid \x23e2e8f0;border-radius:14px;margin-bottom:20px;overflow:hidden;box-shadow:0 1px 4px rgb\x61(0,0,0,.05)}
  .card-head{padding:15px 20px;background:\x23f8fafc;border-bottom:1px solid \x23e2e8f0;font-size:15px;font-weight:700;color:\x230f172a}
  .card-body{padding:20px}
  .charts-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}
  .chart-card{background:\x23f8fafc;border:1px solid \x23e2e8f0;border-radius:12px;padding:16px;text-align:center}
  .chart-card h3{font-size:12px;font-weight:700;color:\x2364748b;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}
  .chart-box{position:relative;height:180px}
  table{width:100%;border-collapse:collapse}
  th{background:\x231e293b;color:\x23fff;padding:10px 14px;text-align:left;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
  .pill{display:inline-flex;align-items:center;padding:3px 11px;border-radius:20px;font-size:12px;font-weight:700}
  .pill.pass{background:\x23d1fae5;color:\x23065f46;border:1.5px solid \x2310b981}
  .pill.fail{background:\x23ffe4e6;color:\x239f1239;border:1.5px solid \x23f43f5e}
  .filter-bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;align-items:center}
  .filter-btn{padding:6px 14px;border-radius:20px;border:1.5px solid \x23e2e8f0;background:\x23fff;font-size:12px;font-weight:600;cursor:pointer;color:\x23475569}
  .filter-btn.active{border-color:\x232563eb;background:\x23eff6ff;color:\x231d4ed8}
  .search-inp{padding:7px 14px;border-radius:20px;border:1.5px solid \x23cbd5e1;font-size:12.5px;min-width:220px}
  .print-btn{position:fixed;bottom:24px;right:24px;background:\x232563eb;color:\x23fff;border:none;border-radius:50px;padding:12px 22px;font-size:14px;font-weight:700;cursor:pointer;box-shadow:0 4px 16px rgb\x61(37,99,235,.4);z-index:999;display:flex;align-items:center;gap:8px}
  @media print{.print-btn,.nav-tabs,.filter-bar{display:none!important}.tab-pane{display:block!important;margin-bottom:20px}body{background:\x23fff}.topbar{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-brand">
    <div class="topbar-logo">QA</div>
    <div class="topbar-title">
      <h1>QAgent — Informe Interactivo de Análisis de Datos y Auditoría</h1>
      <p>Corrida \x23${escHtml(runId)} · ${escHtml(RUN_DATE)} · Navegación por pestañas y estadísticas · Verificación RN-07 activa</p>
    </div>
  </div>
  <div class="score-badge">
    <div class="num">${cumpleCount}/5</div>
    <div class="lbl">Métricas cumplidas</div>
  </div>
</div>

<div class="nav-tabs" id="navTabs">
  <button class="nav-tab active" onclick="switchTab('tab-resumen',this)">📊 1. Resumen & KPIs</button>
  <button class="nav-tab" onclick="switchTab('tab-graficas',this)">📈 2. Gráficas y Estadísticas</button>
  ${inc('detalle') ? `<button class="nav-tab" onclick="switchTab('tab-funciones',this)">🔍 3. Detalle por Función (${m.n})</button>` : ''}
  ${inc('trazas') ? `<button class="nav-tab" onclick="switchTab('tab-incidentes',this)">⚠️ 4. Incidentes y Trazas</button>` : ''}
  ${(inc('codigo')||inc('contratos')) ? `<button class="nav-tab" onclick="switchTab('tab-anexos',this)">🧪 5. Código y Contratos</button>` : ''}
  <button class="nav-tab" onclick="switchTab('all',this)">📑 Vista Completa</button>
</div>

<div class="container">
  <!-- PESTAÑA 1: RESUMEN Y KPIS -->
  <div class="tab-pane active" id="tab-resumen">
    <div class="kpi-grid">${kpiCardsHtml}</div>
    <div class="insight-box">
      <h3>💡 Síntesis del Experto en Análisis de Datos — Hallazgos Clave</h3>
      <ul>
        <li><b>Cumplimiento global (${cumpleCount}/5 métricas):</b> El Pass Rate alcanzó <b>${pctH(m.pass)}</b> (${m.ok} de ${m.n} funciones aprobadas) frente a la meta de ≥ ${META.pass[0]}%.</li>
        <li><b>Calidad estructural y mutación:</b> Cobertura promedio de <b>${pctH(m.lines)}</b> en líneas y <b>${pctH(m.branch)}</b> en ramas, con un Mutation Score de <b>${pctH(m.ms)}</b> en las ${m.crit} funciones críticas.</li>
        <li><b>Eficiencia y seguridad (RN-07):</b> Promedio de <b>${m.iter.toFixed(2)} iteraciones</b> por función y costo total de <b>US$ ${m.usd.toFixed(4)}</b> (S/ ${m.pen.toFixed(2)}). Cero claves de IA expuestas.</li>
      </ul>
    </div>
    <div class="meta-bar">
      <span class="meta-item">📁 <b>Proyecto:</b> ${escHtml(repo)}</span>
      <span class="meta-item">🌿 <b>Rama:</b> ${escHtml(rama)}</span>
      <span class="meta-item">📅 <b>Fecha:</b> ${escHtml(RUN_DATE)}</span>
      <span class="meta-item">🤖 <b>Modelos:</b> Planner: ${escHtml(AGENTS_CFG.P.model)} · Generator: ${escHtml(AGENTS_CFG.G.model)} · Reviewer: ${escHtml(AGENTS_CFG.R.model)}</span>
      <span class="meta-item">♻️ <b>Specs:</b> 4 reutilizados · 2 regenerados (.qagent/specs/)</span>
    </div>
    <div class="card">
      <div class="card-head">📋 1. Resumen de las 5 métricas vs. metas de la carta</div>
      <div class="card-body" style="padding:0">
        <table>
          <thead><tr><th>Métrica de Auditoría</th><th>Resultado Obtenido</th><th>Meta (carta)</th><th style="text-align:center">Estado</th></tr></thead>
          <tbody>${metricsRows}</tbody>
        </table>
        <div style="padding:14px 20px;background:\x23f8fafc;border-top:1px solid \x23e2e8f0;font-size:12.5px;color:\x23475569">
          <b>Costo por agente:</b> Planner US$ ${m.agentUsd.P.toFixed(4)} (${Math.round(m.agentTok.P)} tokens) · Generator US$ ${m.agentUsd.G.toFixed(4)} (${Math.round(m.agentTok.G)} tokens) · Reviewer US$ ${m.agentUsd.R.toFixed(4)} (${Math.round(m.agentTok.R)} tokens)
        </div>
      </div>
    </div>
  </div>

  <!-- PESTAÑA 2: GRÁFICAS Y ESTADÍSTICAS -->
  <div class="tab-pane" id="tab-graficas">
    <div class="card">
      <div class="card-head">📈 Panel Estadístico y Gráficas Interactivas</div>
      <div class="card-body">
        <div class="charts-grid">
          <div class="chart-card">
            <h3>Pass Rate Global</h3>
            <div class="chart-box"><canvas id="chartPass"></canvas></div>
            <p style="margin-top:8px;font-size:13px;font-weight:700">${pctH(m.pass)} (${m.ok}/${m.n} aprobadas)</p>
          </div>
          <div class="chart-card">
            <h3>Cobertura Promedio</h3>
            <div class="chart-box"><canvas id="chartCov"></canvas></div>
            <p style="margin-top:8px;font-size:13px;font-weight:700">Líneas: ${pctH(m.lines)} · Ramas: ${pctH(m.branch)}</p>
          </div>
          <div class="chart-card">
            <h3>Veredictos de Auditoría</h3>
            <div class="chart-box"><canvas id="chartStatus"></canvas></div>
            <p style="margin-top:8px;font-size:13px;color:\x2364748b">${m.n} funciones auditadas</p>
          </div>
          <div class="chart-card">
            <h3>Costo por Agente (US$)</h3>
            <div class="chart-box"><canvas id="chartCost"></canvas></div>
            <p style="margin-top:8px;font-size:13px;color:\x2364748b">Total: US$ ${m.usd.toFixed(4)}</p>
          </div>
        </div>
        <div class="chart-card" style="margin-top:18px">
          <h3>Comparativa por Función: Cobertura de Líneas, Ramas y Mutation Score (%)</h3>
          <div style="position:relative;height:260px"><canvas id="chartFnCompare"></canvas></div>
        </div>
      </div>
    </div>
  </div>

  <!-- PESTAÑA 3: DETALLE POR FUNCIÓN -->
  ${inc('detalle') ? `<div class="tab-pane" id="tab-funciones">
    <div class="card">
      <div class="card-head">🔍 2. Resultado detallado por función</div>
      <div class="card-body">
        <div class="filter-bar" id="filterBar">
          <input class="search-inp" id="fnSearch" placeholder="🔎 Buscar función o módulo..." oninput="aplicarFiltros()">
          <button class="filter-btn active" data-st="all" onclick="filtrarEstado('all',this)">Todas (${m.n})</button>
          ${statusLabels.map(s => `<button class="filter-btn" data-st="${escHtml(s)}" onclick="filtrarEstado('${escHtml(s)}',this)">${escHtml(ST[s]?.rep||s)} (${statusCounts[s]})</button>`).join('')}
        </div>
        <div id="fnList">${funcionCards}</div>
      </div>
    </div>
  </div>` : ''}

  <!-- PESTAÑA 4: INCIDENTES Y TRAZAS -->
  ${inc('trazas') ? `<div class="tab-pane" id="tab-incidentes">
    <div class="card">
      <div class="card-head">⚠️ 3. Trazas del Reviewer de los incidentes</div>
      <div class="card-body">${incidentesCards || '<p>No se registraron incidentes en esta corrida.</p>'}</div>
    </div>
  </div>` : ''}

  <!-- PESTAÑA 5: CÓDIGO Y CONTRATOS -->
  ${(inc('codigo')||inc('contratos')) ? `<div class="tab-pane" id="tab-anexos">
    <div class="card">
      <div class="card-head">🧪 4. Suites de prueba generadas y contratos del Planner</div>
      <div class="card-body">${codigoContratosCards}</div>
    </div>
  </div>` : ''}
</div>

<button class="print-btn" onclick="imprimirInforme()">🖨️ Imprimir / Guardar PDF</button>

<script>
let estadoFiltroActual = 'all';
function switchTab(tabId, btn){
  document.querySelectorAll('\x23navTabs .nav-tab').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  document.querySelectorAll('.tab-pane').forEach(p=>{
    if(tabId==='all') p.classList.add('active');
    else p.classList.toggle('active', p.id===tabId);
  });
}
function filtrarEstado(st, btn){
  estadoFiltroActual = st;
  document.querySelectorAll('\x23filterBar .filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  aplicarFiltros();
}
function aplicarFiltros(){
  const q = (document.getElementById('fnSearch')?.value || '').toLowerCase().trim();
  document.querySelectorAll('\x23fnList .fn-card').forEach(card=>{
    const okSt = estadoFiltroActual==='all' || card.dataset.status===estadoFiltroActual;
    const okQ = !q || (card.dataset.name||'').includes(q);
    card.style.display = (okSt && okQ) ? '' : 'none';
  });
}
function imprimirInforme(){
  switchTab('all', document.querySelector('\x23navTabs .nav-tab:last-child'));
  setTimeout(()=>window.print(), 150);
}
window.addEventListener('DOMContentLoaded', () => {
  if(typeof Chart === 'undefined') return;
  const chartDefaults = {plugins:{legend:{labels:{font:{size:11},boxWidth:12}}},responsive:true,maintainAspectRatio:false};
  new Chart(document.getElementById('chartPass'),{type:'doughnut',data:{labels:['Aprobadas','Con incidente'],datasets:[{data:[${m.ok},${m.n-m.ok}],backgroundColor:['\x2310b981','\x23f43f5e'],borderWidth:2,borderColor:'\x23f8fafc'}]},options:{...chartDefaults,cutout:'66%'}});
  new Chart(document.getElementById('chartCov'),{type:'bar',data:{labels:['Líneas','Ramas','Mutation'],datasets:[{data:[${m.lines.toFixed(1)},${m.branch.toFixed(1)},${m.ms.toFixed(1)}],backgroundColor:['\x233b82f6','\x2306b6d4','\x238b5cf6'],borderRadius:6}]},options:{...chartDefaults,scales:{y:{min:0,max:100,ticks:{callback:v=>v+'%'}}},plugins:{legend:{display:false}}}});
  new Chart(document.getElementById('chartStatus'),{type:'doughnut',data:{labels:${JSON.stringify(statusLabels.map(s=>ST[s]?.rep||s))},datasets:[{data:${JSON.stringify(statusValues)},backgroundColor:${JSON.stringify(statusColors)},borderWidth:2,borderColor:'\x23f8fafc'}]},options:{...chartDefaults,cutout:'58%'}});
  new Chart(document.getElementById('chartCost'),{type:'bar',data:{labels:['Planner','Generator','Reviewer'],datasets:[{data:[${m.agentUsd.P.toFixed(5)},${m.agentUsd.G.toFixed(5)},${m.agentUsd.R.toFixed(5)}],backgroundColor:['\x236366f1','\x23f59e0b','\x2310b981'],borderRadius:6}]},options:{...chartDefaults,scales:{y:{ticks:{callback:v=>'US$'+v}}},plugins:{legend:{display:false}}}});
  new Chart(document.getElementById('chartFnCompare'),{type:'bar',data:{labels:${JSON.stringify(RUN.map(f=>f.name))},datasets:[{label:'Cob. Líneas (%)',data:${JSON.stringify(RUN.map(f=>f.lines_cov))},backgroundColor:'\x233b82f6',borderRadius:4},{label:'Cob. Ramas (%)',data:${JSON.stringify(RUN.map(f=>f.branch_cov))},backgroundColor:'\x2306b6d4',borderRadius:4},{label:'Mutation Score (%)',data:${JSON.stringify(RUN.map(f=>f.mutation_score||0))},backgroundColor:'\x238b5cf6',borderRadius:4}]},options:{...chartDefaults,scales:{y:{min:0,max:100,ticks:{callback:v=>v+'%'}}}}});
});
<\/script>
</body>
</html>`;
}


// modal-exportar.js — modal «Exportar informe» (HU-020): PDF, Markdown y JSON
// HTML del componente (se monta en el marcador data-componente="informe/modal-exportar" de index.html)
registrarComponente('informe/modal-exportar', `<!-- Exportar informe (HU-020) -->
<div class="overlay" id="m-export"><div class="modal" style="width:640px">
  <div class="mhead"><span class="ico" data-i="download" data-c="var(--blue-400)"></span> Exportar informe de auditoría · corrida #8841-B<button class="x" onclick="closeModal()">×</button></div>
  <div class="mcontent">
    <div><label class="l">Formato</label>
      <div class="fmts">
        <div class="fmt" data-f="pdf" onclick="setFmt('pdf')"><b>PDF</b><span>Documento formal para el auditor (evidencia).</span></div>
        <div class="fmt" data-f="md" onclick="setFmt('md')"><b>Markdown (.md)</b><span>Editable y versionable junto al código.</span></div>
        <div class="fmt" data-f="json" onclick="setFmt('json')"><b>JSON (results)</b><span>Datos crudos de métricas para otras herramientas.</span></div>
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
      <div style="display:flex;gap:8px"><input class="inp" id="expPath" readonly><button class="btn" onclick="toast('En la app real se abre el diálogo nativo para elegir carpeta (simulado)')">Cambiar…</button></div>
      <div class="hint">Archivo: <span class="mono" id="expName"></span> · por defecto dentro de la carpeta del proyecto, junto a los resultados de la corrida.</div></div>
  </div>
  <div class="mfoot"><button class="btn" onclick="closeModal()">Cancelar</button><button class="btn primary" onclick="doExport()">Exportar</button></div>
</div></div>
`);

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
  md += `- **Proyecto:** ${document.querySelector('.repoLbl').textContent}\n- **Rama:** ${$('branchLbl').textContent}\n- **Fecha:** ${RUN_DATE}\n- **Perfil:** Profundo · **Funciones evaluadas:** ${m.n} (${m.crit} críticas)\n- **Generado por:** QAgent v2.4 (Planner → Generator → Reviewer)\n- **Modelos:** Planner: ${AGENTS_CFG.P.model} (US$ ${AGENTS_CFG.P.price}/M) · Generator: ${AGENTS_CFG.G.model} (US$ ${AGENTS_CFG.G.price}/M) · Reviewer: ${AGENTS_CFG.R.model} (US$ ${AGENTS_CFG.R.price}/M)\n- **Specs:** 4 reutilizados de corridas anteriores · 2 regenerados (cart.py, discounts.py cambiaron) · guardados en \`.pyagent/specs/\`\n\n`;
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

// barra-corrida.js — barra superior compartida por Monitor, Ejecución e Informe: progreso y pausa
// HTML del componente (se monta en el marcador data-componente="barra-corrida/barra-corrida" de index.html)
registrarComponente('barra-corrida/barra-corrida', `<!-- ===== Barra compartida Monitor / Ejecución / Reporte ===== -->
  <div class="topbar mon-top hide" id="runTop">
    <div class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h6l2 2h10v10H3z"/></svg><b>repo:</b> <span class="repoLbl">github.com/retail-ai/ecommerce-core</span></div>
    <span class="chev">›</span>
    <div class="chip amber" id="ctxChip"><span class="dot"></span><span><span id="ctxLbl">Analizando:</span><br><span id="curFile">services/pricing.py</span></span></div>
    <div class="prog">
      <div class="lbl">Progreso de<br>la corrida:</div>
      <div><div class="num" id="progNum">0 de 9 funciones <span>(0%)</span></div><div class="bar"><i id="progBar" style="width:0"></i></div></div>
    </div>
    <div class="live" id="liveBtn" onclick="togglePause()" title="Clic para pausar / reanudar"><i></i><span id="liveTxt">LIVE<br>AGENTS</span></div>
  </div>
`);

let paused = false;
function togglePause(){
  if(runDone) return;
  paused = !paused;
  $('liveBtn').classList.toggle('paused', paused);
  $('liveTxt').innerHTML = paused ? 'PAUSADO' : 'LIVE<br>AGENTS';
  clearInterval(monTimer); if(!paused) monTimer = setInterval(pushEvent, 900);
}

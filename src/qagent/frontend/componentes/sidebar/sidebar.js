// sidebar.js — barra lateral retráctil (drawer): navegación, espacio de trabajo y estado del motor
// HTML del componente (se monta en el marcador data-componente="sidebar/sidebar" de index.html)
// Plegada queda como un riel de íconos; cada enlace lleva title para verse como descripción emergente.
// Íconos en línea con stroke="currentColor": toman el color del texto, que viene de los tokens.
registrarComponente('sidebar/sidebar', `<!-- ======================= BARRA LATERAL ======================= -->
<aside id="lateral" class="lateral" aria-label="Navegación principal">
  <div class="lat-cabecera">
    <div class="logo" role="img" aria-label="QAgent"></div>
    <span class="lat-marca lat-txt">QAgent</span>
    <button type="button" class="lat-plegar" id="btnPlegar" onclick="alternarLateral()" aria-controls="lateral" aria-expanded="true" aria-label="Plegar la barra lateral" title="Plegar la barra lateral (Ctrl+B)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/><path class="lat-flecha" d="m15.5 10-2 2 2 2"/></svg>
    </button>
  </div>

  <!-- Menú general: sin proyecto abierto -->
  <div id="sideHome">
    <nav class="lat-nav" aria-label="General">
      <a class="on" data-h="welcome" onclick="go('welcome')"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 11 12 4l8 7v9H4z"/><path d="M10 20v-5h4v5"/></svg><span class="lat-txt">Inicio</span></a>
      <a data-h="config" onclick="go('config')"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg><span class="lat-txt">Configuración</span></a>
      <a class="off" aria-disabled="true" title="No disponible en esta versión"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 5h7v14H4zM13 5h7v14h-7z"/></svg><span class="lat-txt">Guía de uso</span><span class="lat-insignia lat-txt">No disponible</span></a>
    </nav>
  </div>

  <!-- Menú del proyecto abierto -->
  <div id="sideProj" class="hide">
    <div class="side-back-wrap">
      <button type="button" class="btn-side-back" id="btnVolverInicio" onclick="volverAInicio()" title="Volver a Inicio">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
        <span class="lat-txt">Volver a Inicio</span>
      </button>
    </div>
    <div class="lat-espacio lat-txt">
      <span class="lat-etiqueta">Espacio de trabajo</span>
      <b class="repoName"></b>
      <span class="lat-rama" id="sideBranch">Rama <span id="branchLbl">main</span></span>
    </div>
    <nav id="views" class="lat-nav" aria-label="Proyecto">
      <a data-v="preview"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/></svg><span class="lat-txt">Explorar</span></a>
      <a data-v="tests"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg><span class="lat-txt">Preparar</span></a>
      <a data-v="monitor" class="hide off"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 12h4l3-7 4 14 3-7h4"/></svg><span class="lat-txt">En curso</span></a>
      <a data-v="exec" class="hide off"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg><span class="lat-txt">Pruebas</span></a>
      <a data-v="report" class="hide off"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M6 3h9l4 4v14H6z"/><path d="M9 12h7M9 16h7"/></svg><span class="lat-txt">Resultados</span></a>
      <a data-v="history" class="hide off"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg><span class="lat-txt">Historial</span></a>
    </nav>
  </div>

  <!-- Estado del motor de ejecución (entorno aislado) -->
  <div class="sidefoot">
    <div class="lat-motor" id="sbRow">
      <span class="dot" id="sbDot" aria-hidden="true"></span>
      <div class="lat-motor-texto lat-txt">
        <b id="sbTxt">Motor activo</b>
        <small id="sbDetalle">Entorno aislado · sin internet</small>
        <button type="button" class="lat-motor-ayuda" id="sbAyuda" style="display:none" onclick="go('config')"><span id="sbAyudaTxt"></span></button>
      </div>
    </div>
    <div class="lat-pie lat-txt">QAgent · Escritorio</div>
  </div>
</aside>
`);

/* Indicador de estado del motor: consulta a Python al abrir y cada 15 s.
   Los textos hablan del «motor» (el entorno aislado); Docker solo se nombra cuando hay que actuar. */
const SANDBOX_UI = {
  ok:           {dot:'dot',       txt:'ok',     label:'Motor activo',         detalle:'Entorno aislado · sin internet', ayuda:''},
  sin_imagen:   {dot:'dot amber', txt:'warn',   label:'Motor sin preparar',   detalle:'Falta la imagen del entorno aislado', ayuda:''},
  no_iniciado:  {dot:'dot red',   txt:'no',     label:'Motor inactivo',       detalle:'El entorno aislado está detenido', ayuda:'Abre Docker Desktop'},
  no_instalado: {dot:'dot red',   txt:'no',     label:'Motor no instalado',   detalle:'Se necesita para verificar pruebas', ayuda:'Instala Docker Desktop'},
  // Con la IA simulada no se ejecuta nada en el sandbox: que Docker falte no es un fallo.
  opcional:     {dot:'dot grey',  txt:'neutro', label:'Motor opcional',       detalle:'No se usa con la IA simulada', ayuda:''},
};
let sandboxConsultando = false;
async function actualizarSandbox() {
  // Sin pywebview (HTML abierto en el navegador) se mantiene el estado verde del demo
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.estado_sandbox)) return;
  if (sandboxConsultando) return;
  sandboxConsultando = true;
  try {
    const r = await window.pywebview.api.estado_sandbox();
    // IA simulada y Docker sin responder (o sin imagen): se muestra como opcional, no como error.
    const clave = r && r.simulado && r.estado !== 'ok' ? 'opcional' : r && r.estado;
    const ui = SANDBOX_UI[clave] || SANDBOX_UI.no_iniciado;
    if ($('sbDot')) $('sbDot').className = ui.dot;
    if ($('sbTxt')) { $('sbTxt').textContent = ui.label; $('sbTxt').className = ui.txt; }
    if ($('sbDetalle')) $('sbDetalle').textContent = ui.detalle;
    if ($('sbRow')) $('sbRow').title = ui.label + ' · ' + ((r && r.mensaje) || ui.detalle);
    if ($('sbAyudaTxt')) $('sbAyudaTxt').textContent = ui.ayuda;
    if ($('sbAyuda')) {
      $('sbAyuda').title = (r && r.mensaje) || '';
      $('sbAyuda').style.display = ui.ayuda ? '' : 'none';
    }
  } catch (err) {
    console.error("Error al consultar el estado del sandbox:", err);
  } finally {
    sandboxConsultando = false;
  }
}
function iniciarEstadoSandbox() {
  actualizarSandbox();
  setInterval(actualizarSandbox, 15000);
}

/* Drawer: expandida o plegada. La preferencia es de cada persona y se recuerda en este equipo;
   si el almacenamiento no está disponible, la barra funciona igual (solo no se recuerda). */
const CLAVE_LATERAL = 'qagent.lateral.plegada';
function alternarLateral(plegar){
  const aside = $('lateral');
  const plegada = typeof plegar === 'boolean' ? plegar : !aside.classList.contains('plegada');
  aside.classList.toggle('plegada', plegada);
  const btn = $('btnPlegar');
  btn.setAttribute('aria-expanded', String(!plegada));
  btn.setAttribute('aria-label', plegada ? 'Expandir la barra lateral' : 'Plegar la barra lateral');
  btn.title = (plegada ? 'Expandir' : 'Plegar') + ' la barra lateral (Ctrl+B)';
  try { localStorage.setItem(CLAVE_LATERAL, plegada ? '1' : '0'); } catch (_) { /* sin almacenamiento: no se recuerda */ }
}
function iniciarLateral(){
  let guardada = null;
  try { guardada = localStorage.getItem(CLAVE_LATERAL); } catch (_) { guardada = null; }
  // Sin preferencia guardada: en ventanas estrechas empieza plegada para dejar sitio al contenido.
  const plegada = guardada === null ? window.innerWidth < 1024 : guardada === '1';
  $('lateral').classList.toggle('plegada', plegada);
  $('btnPlegar').setAttribute('aria-expanded', String(!plegada));
  $('btnPlegar').setAttribute('aria-label', plegada ? 'Expandir la barra lateral' : 'Plegar la barra lateral');
  // Plegada solo se ven los íconos: el nombre de cada destino queda como descripción emergente.
  // Los enlaces no tienen href: se hacen alcanzables con Tab y se activan con Enter o Espacio.
  document.querySelectorAll('#lateral .lat-nav a').forEach(a => {
    if(!a.title) a.title = a.textContent.trim();
    a.setAttribute('role', 'link');
    if(!a.classList.contains('off')) a.tabIndex = 0;
    a.addEventListener('keydown', e => {
      if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); a.click(); }
    });
  });
  document.addEventListener('keydown', e => {
    if((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'b'){
      e.preventDefault();
      alternarLateral();
    }
  });
}

function volverAInicio(){
  if (typeof monitorStarted !== 'undefined' && monitorStarted && typeof runDone !== 'undefined' && !runDone) {
    if (!confirm('Hay una corrida de pruebas en ejecución activa. ¿Deseas volver a la pantalla principal?')) {
      return;
    }
  }
  go('welcome');
}

// Resalta la pantalla activa y alterna el menú de inicio / el menú del proyecto. Lo invoca go(v).
function actualizarSidebar(v){
  const home = v==='welcome' || v==='config';
  $('sideHome').classList.toggle('hide', !home);
  $('sideProj').classList.toggle('hide', home);
  $('sideBranch').classList.toggle('hide', home);   // la rama solo tiene sentido con un proyecto abierto
  document.querySelectorAll('#sideHome nav a').forEach(a => {
    a.classList.toggle('on', a.dataset.h===v);
    if(a.dataset.h===v) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  document.querySelectorAll('#views a').forEach(a => {
    a.classList.toggle('on', a.dataset.v===v);
    if(a.dataset.v===v) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
}

function desbloquearVista(v){
  document.querySelectorAll(`#views a[data-v="${v}"]`).forEach(a => {
    a.classList.remove('hide', 'off');
  });
}

function desbloquearTodasLasVistas(){
  document.querySelectorAll('#views a').forEach(a => {
    a.classList.remove('hide', 'off');
  });
}

function reiniciarVistasProyecto(){
  document.querySelectorAll('#views a').forEach(a => {
    const v = a.dataset.v;
    if(v === 'preview' || v === 'tests'){
      a.classList.remove('hide', 'off');
    } else {
      a.classList.add('hide', 'off');
    }
  });
}

// Se llama desde main.js cuando el HTML de la barra lateral ya está montado.
function iniciarSidebar(){
  reiniciarVistasProyecto();
  iniciarLateral();
  document.querySelectorAll('#views a').forEach(a => a.onclick = () => {
    if(a.classList.contains('off') || a.classList.contains('hide')) return;
    if(a.dataset.v==='monitor' && !monitorStarted) { startMonitor(); return; }
    go(a.dataset.v);
  });
  if (window.pywebview && window.pywebview.api) iniciarEstadoSandbox();
  else window.addEventListener('pywebviewready', iniciarEstadoSandbox, {once:true});
}

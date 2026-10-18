// sidebar.js — barra lateral retráctil (drawer): navegación principal, espacio de trabajo y estado del motor
// HTML del componente (se monta en el marcador data-componente="sidebar/sidebar" de index.html)
// Cuatro destinos siempre visibles: Inicio, Proyecto actual, Historial y Configuración. Los pasos de un
// proyecto (Explorar → Resultados) viven en componentes/pasos-proyecto/, arriba de cada pantalla.
// Plegada queda como un riel de íconos; cada enlace lleva title para verse como descripción emergente.
registrarComponente('sidebar/sidebar', `<!-- ======================= BARRA LATERAL ======================= -->
<aside id="lateral" class="lateral" aria-label="Navegación principal">
  <div class="lat-cabecera">
    <div class="logo" role="img" aria-label="QAgent"></div>
    <span class="lat-marca lat-txt">QAgent</span>
    <button type="button" class="lat-plegar" id="btnPlegar" onclick="alternarLateral()" aria-controls="lateral" aria-expanded="true" aria-label="Plegar la barra lateral" title="Plegar la barra lateral (Ctrl+B)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/><path class="lat-flecha" d="m15.5 10-2 2 2 2"/></svg>
    </button>
  </div>

  <nav class="lat-nav" id="latNav" aria-label="Principal">
    <a class="on" data-h="welcome" onclick="volverAInicio()"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 11 12 4l8 7v9H4z"/><path d="M10 20v-5h4v5"/></svg><span class="lat-txt">Inicio</span></a>
    <a class="off" data-h="proyecto" aria-disabled="true" onclick="irAProyectoActual()"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7h6l2 2h10v10H3z"/><path d="m10.5 12.5-1.5 1.5 1.5 1.5M13.5 12.5l1.5 1.5-1.5 1.5"/></svg><span class="lat-txt">Proyecto actual</span></a>
    <a class="off" data-h="history" aria-disabled="true" onclick="irAHistorial()"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg><span class="lat-txt">Historial</span></a>
    <a data-h="config" onclick="go('config')"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg><span class="lat-txt">Configuración</span></a>
  </nav>

  <!-- Espacio de trabajo: solo con un proyecto abierto. La rama (#branchLbl) la leen el informe y la exportación. -->
  <div class="lat-espacio lat-txt hide" id="latEspacio">
    <span class="lat-etiqueta">Espacio de trabajo</span>
    <b class="repoName"></b>
    <span class="lat-detalle">Python · pytest<span id="sideBranch"> · rama <span id="branchLbl">main</span></span></span>
  </div>

  <!-- Estado del motor de ejecución (entorno aislado) -->
  <div class="sidefoot">
    <div class="lat-motor" id="sbRow">
      <span class="lat-motor-ico ok" id="sbDot" aria-hidden="true"></span>
      <div class="lat-motor-texto lat-txt">
        <b id="sbTxt">Motor activo</b>
        <small id="sbDetalle">Entorno aislado · sin internet</small>
        <button type="button" class="lat-motor-ayuda" id="sbAyuda" style="display:none" onclick="go('config')"><span id="sbAyudaTxt"></span></button>
      </div>
    </div>
    <div class="lat-pie">
      <span class="lat-txt">QAgent · Escritorio</span>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9 12 2 2 4-4"/></svg>
    </div>
  </div>
</aside>
`);

/* Indicador de estado del motor: consulta a Python al abrir y cada 15 s.
   Los textos hablan del «motor» (el entorno aislado); Docker solo se nombra cuando hay que actuar.
   Cada estado lleva ícono, color y texto: se entiende sin depender del color. */
const ICO_MOTOR = {
  ok:      '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="m8 12 3 3 5-6"/>',
  pausa:   '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="M10 9v6M14 9v6"/>',
  aviso:   '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  error:   '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="M12 8v5M12 16h.01"/>',
  neutro:  '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="M8 12h8"/>',
};
const SANDBOX_UI = {
  ok:           {ico:'ok',     txt:'ok',     label:'Motor activo',       detalle:'Entorno aislado · sin internet',      ayuda:''},
  sin_imagen:   {ico:'aviso',  txt:'warn',   label:'Motor sin preparar', detalle:'Falta la imagen del entorno aislado', ayuda:''},
  no_iniciado:  {ico:'pausa',  txt:'warn',   label:'Motor inactivo',     detalle:'Inícialo en Configuración',           ayuda:'Abre Docker Desktop'},
  no_instalado: {ico:'error',  txt:'no',     label:'Motor no instalado', detalle:'Se necesita para verificar pruebas',  ayuda:'Instala Docker Desktop'},
  // Con la IA simulada no se ejecuta nada en el sandbox: que Docker falte no es un fallo.
  opcional:     {ico:'neutro', txt:'neutro', label:'Motor opcional',     detalle:'No se usa con la IA simulada',        ayuda:''},
};
function pintarMotor(ui){
  $('sbDot').className = 'lat-motor-ico ' + ui.txt;
  $('sbDot').innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">${ICO_MOTOR[ui.ico]}</svg>`;
  $('sbTxt').textContent = ui.label;
  $('sbDetalle').textContent = ui.detalle;
}
let sandboxConsultando = false;
// Último estado del motor ({clave, mensaje}); también lo muestra la pantalla Configuración.
let ESTADO_MOTOR = null;
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
    ESTADO_MOTOR = {clave: SANDBOX_UI[clave] ? clave : 'no_iniciado', mensaje: r && r.mensaje};
    if (typeof renderMotorConfig === 'function') renderMotorConfig();
    pintarMotor(ui);
    $('sbRow').title = ui.label + ' · ' + ((r && r.mensaje) || ui.detalle);
    $('sbAyudaTxt').textContent = ui.ayuda;
    $('sbAyuda').title = (r && r.mensaje) || '';
    $('sbAyuda').style.display = ui.ayuda ? '' : 'none';
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
  // Los enlaces no tienen href: se hacen alcanzables con Tab y se activan con Enter o Espacio.
  // Plegada solo se ven los íconos: el nombre de cada destino queda como descripción emergente.
  document.querySelectorAll('#latNav a').forEach(a => {
    a.title = a.textContent.trim();
    a.setAttribute('role', 'link');
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

/* Proyecto actual: recuerda en qué paso del proyecto estaba la persona para volver ahí. */
const VISTAS_PROYECTO = ['preview','tests','monitor','exec'];
let vistaProyecto = null;   // null hasta que se abre un proyecto
function irAProyectoActual(){ if(vistaProyecto) go(vistaProyecto); }
function irAHistorial(){ if(vistaProyecto) go('history'); }
function habilitarEnlace(a, si){
  a.classList.toggle('off', !si);
  if(si){ a.removeAttribute('aria-disabled'); a.tabIndex = 0; }
  else { a.setAttribute('aria-disabled', 'true'); a.tabIndex = -1; }
}

function volverAInicio(){
  if (typeof monitorStarted !== 'undefined' && monitorStarted && typeof runDone !== 'undefined' && !runDone) {
    if (!confirm('Hay una corrida de pruebas en ejecución activa. ¿Deseas volver a la pantalla principal?')) {
      return;
    }
  }
  go('welcome');
}

// Resalta el destino activo y habilita Proyecto actual e Historial cuando hay un proyecto. Lo invoca go(v).
function actualizarSidebar(v){
  if(VISTAS_PROYECTO.includes(v)) vistaProyecto = v;
  const activo = VISTAS_PROYECTO.includes(v) || v === 'export' ? 'proyecto' : (v === 'open' || v === 'clone' ? 'welcome' : v);
  document.querySelectorAll('#latNav a').forEach(a => {
    if(a.dataset.h === 'proyecto' || a.dataset.h === 'history') habilitarEnlace(a, !!vistaProyecto);
    a.classList.toggle('on', a.dataset.h === activo);
    if(a.dataset.h === activo) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  $('latEspacio').classList.toggle('hide', !vistaProyecto);
  $('sideBranch').classList.toggle('hide', !$('branchLbl').textContent || $('branchLbl').textContent === '—');
  if(vistaProyecto){
    $('latNav').querySelector('[data-h="proyecto"]').title = 'Proyecto actual';
    $('latNav').querySelector('[data-h="history"]').title = 'Historial';
  } else {
    $('latNav').querySelector('[data-h="proyecto"]').title = 'Abre un proyecto para continuar';
    $('latNav').querySelector('[data-h="history"]').title = 'Abre un proyecto para ver su historial';
  }
}

// Se llama desde main.js cuando el HTML de la barra lateral ya está montado.
function iniciarSidebar(){
  iniciarLateral();
  pintarMotor(SANDBOX_UI.ok);   // estado del demo; la app real lo reemplaza al consultar a Python
  if (window.pywebview && window.pywebview.api) iniciarEstadoSandbox();
  else window.addEventListener('pywebviewready', iniciarEstadoSandbox, {once:true});
}

// puente-python.js — conexión con Python (pywebview): eventos y estado del sandbox
/* ================= Conexión con Python (pywebview) ================= */

// Función para recibir eventos enviados desde Python vía DesktopAPI.emit_event()
window.onPyAgentEvent = function(event) {
  console.log("[Python Event]", event);
  if (event.type === 'log') {
    toast(`Python: ${event.data.message}`);
  } else if (event.type === 'clonado_avance') {
    avanceClonado(event.data);
  } else if (event.type === 'clonado_fin') {
    finClonado(event.data);
  }
};

/* Indicador de estado del sandbox: consulta a Python al abrir y cada 15 s */
const SANDBOX_UI = {
  ok:           {dot:'dot',       txt:'ok',   label:'pyagent-sandbox:base',          ayuda:''},
  sin_imagen:   {dot:'dot amber', txt:'warn', label:'Falta imagen base',     ayuda:''},
  no_iniciado:  {dot:'dot red',   txt:'no',   label:'Sandbox no disponible', ayuda:'Abre Docker Desktop'},
  no_instalado: {dot:'dot red',   txt:'no',   label:'Sandbox no disponible', ayuda:'Instala Docker Desktop'},
};
let sandboxConsultando = false;
async function actualizarSandbox() {
  // Sin pywebview (HTML abierto en el navegador) se mantiene el estado verde del demo
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.estado_sandbox)) return;
  if (sandboxConsultando) return;
  sandboxConsultando = true;
  try {
    const r = await window.pywebview.api.estado_sandbox();
    const ui = SANDBOX_UI[r && r.estado] || SANDBOX_UI.no_iniciado;
    $('sbDot').className = ui.dot;
    $('sbEstado').className = ui.txt;
    $('sbTxt').textContent = ui.label;
    $('sbRow').title = ui === SANDBOX_UI.ok ? '' : (r && r.mensaje) || '';
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
if (window.pywebview && window.pywebview.api) iniciarEstadoSandbox();
else window.addEventListener('pywebviewready', iniciarEstadoSandbox, {once:true});


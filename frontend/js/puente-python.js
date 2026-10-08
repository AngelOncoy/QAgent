// puente-python.js — conexión con Python (pywebview): abrir carpeta y estado del sandbox
/* ================= Conexión con Python (pywebview) ================= */
// HU-01: carpeta real elegida en el diálogo nativo (null = modal simulado del navegador).
let realFolder = null;
const OPEN_HINT_DEMO = 'En la app real se abre el diálogo nativo de Windows/macOS/Linux.';
const escHtml = t => String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Restaura el modal #m-open a su modo simulado (navegador sin pywebview).
function resetOpenModal() {
  realFolder = null; pickedFolder = null;
  ['openLocRow','fsList'].forEach(id => $(id).classList.remove('hide'));
  ['openPathRow','openCountRow','openOther'].forEach(id => $(id).classList.add('hide'));
  document.querySelectorAll('#fsList div').forEach(x => x.classList.remove('sel'));
  $('openHint').textContent = OPEN_HINT_DEMO; $('openHint').className = 'hint';
  $('openOk').disabled = true;
}

// Muestra en #m-open la carpeta real inspeccionada por Python: ruta, N archivos .py y error si lo hay.
function showOpenReal(info) {
  realFolder = info.ok ? info.ruta : null;
  ['openLocRow','fsList'].forEach(id => $(id).classList.add('hide'));
  ['openPathRow','openCountRow','openOther'].forEach(id => $(id).classList.remove('hide'));
  $('openPath').value = info.ruta || '';
  const n = info.cantidad_py || 0;
  $('openCount').textContent = `${n} ${n === 1 ? 'archivo' : 'archivos'} .py` + (info.rama ? ` · rama ${info.rama}` : '');
  $('openHint').textContent = info.ok ? 'Solo se analizarán los .py fuera de tests/, entornos virtuales y carpetas ocultas.' : info.error;
  $('openHint').className = 'hint' + (info.ok ? '' : ' err');
  $('openOk').disabled = !info.ok;
  openModal('m-open');
}

async function handleOpenFolder() {
  if (window.pywebview && window.pywebview.api) {
    try {
      // Diálogo nativo de carpetas (DesktopAPI.select_folder); si se cancela, no pasa nada.
      const folderPath = await window.pywebview.api.select_folder();
      if (!folderPath) return;
      const info = await window.pywebview.api.inspeccionar_carpeta(folderPath);
      showOpenReal(info);
    } catch (err) {
      console.error("Error al abrir la carpeta:", err);
      showOpenReal({ok: false, ruta: '', cantidad_py: 0, error: 'No se pudo revisar la carpeta. Inténtalo de nuevo.'});
    }
  } else {
    // Si abres el HTML en el navegador sin pywebview, mantiene el modal simulado
    resetOpenModal();
    openModal('m-open');
  }
}

// Revalida la carpeta en Python, la registra en recientes y abre la Vista previa (solo si tiene .py).
async function confirmOpenReal() {
  $('openOk').disabled = true;
  try {
    const info = await window.pywebview.api.abrir_proyecto(realFolder);
    if (!info.ok) { showOpenReal(info); return; }
    closeModal(); realFolder = null;
    // Sin repositorio Git no hay rama que mostrar.
    loadProject(info.nombre, 'local', info.ruta, info.rama || '—', info.ruta);
    toast(`Proyecto abierto: <span class="mono">${escHtml(info.ruta)}</span>`);
  } catch (err) {
    console.error("Error al abrir el proyecto:", err);
    showOpenReal({ok: false, ruta: realFolder, cantidad_py: 0, error: 'No se pudo abrir el proyecto. Inténtalo de nuevo.'});
  }
}

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


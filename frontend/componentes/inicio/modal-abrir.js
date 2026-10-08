// modal-abrir.js — modal «Abrir proyecto»: carpeta local elegida con el diálogo nativo (HU-01)
// HTML del componente (se monta en el marcador data-componente="inicio/modal-abrir" de index.html)
registrarComponente('inicio/modal-abrir', `<!-- Abrir proyecto: selector de carpetas del SO (simulado) -->
<div class="overlay" id="m-open"><div class="modal">
  <div class="mhead">Seleccionar carpeta del proyecto<button class="x" onclick="closeModal()">×</button></div>
  <div class="mcontent">
    <div class="frow" id="openLocRow"><label>Ubicación</label><input class="inp" value="E:\\Proyectos" readonly></div>
    <div class="frow hide" id="openPathRow"><label>Carpeta</label><input class="inp" id="openPath" readonly></div>
    <div class="frow hide" id="openCountRow"><label>Contenido</label><span class="mono" id="openCount"></span></div>
    <div class="fs" id="fsList">
      <div data-p="ecommerce-core">📁 ecommerce-core</div>
      <div data-p="banco-pruebas-mvp">📁 banco-pruebas-mvp</div>
      <div data-p="landing-web">📁 landing-web <span class="hint" style="margin:0 0 0 auto">sin archivos .py</span></div>
    </div>
    <div class="hint" id="openHint">En la app real se abre el diálogo nativo de Windows/macOS/Linux.</div>
  </div>
  <div class="mfoot"><button class="btn" onclick="closeModal()">Cancelar</button><button class="btn hide" id="openOther" onclick="handleOpenFolder()">Elegir otra carpeta</button><button class="btn primary" id="openOk" disabled onclick="confirmOpen()">Abrir</button></div>
</div></div>
`);

// HU-01: carpeta real elegida en el diálogo nativo (null = modal simulado del navegador).
let realFolder = null;
let pickedFolder = null;   // carpeta elegida en el selector simulado (navegador sin pywebview)
const OPEN_HINT_DEMO = 'En la app real se abre el diálogo nativo de Windows/macOS/Linux.';

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

// Se llama desde main.js cuando el HTML del modal ya está montado.
function iniciarModalAbrir(){
  document.querySelectorAll('#fsList div').forEach(d => d.onclick = () => {
    document.querySelectorAll('#fsList div').forEach(x=>x.classList.remove('sel')); d.classList.add('sel');
    pickedFolder = d.dataset.p;
    const bad = pickedFolder==='landing-web';
    $('openHint').textContent = bad ? 'Esta carpeta no contiene archivos .py: QAgent solo analiza código Python 3.10+.' : 'Carpeta: E:\\Proyectos\\'+pickedFolder;
    $('openHint').className = 'hint' + (bad?' err':'');
    $('openOk').disabled = bad;
  });
}

function confirmOpen(){
  if (realFolder) { confirmOpenReal(); return; }
  closeModal(); loadProject(pickedFolder,'local','E:\\Proyectos\\'+pickedFolder);
}


// modal-abrir.js — pantalla «Abre tu proyecto»: carpeta local elegida con el diálogo nativo (HU-01)
// HTML del componente (se monta en el marcador data-componente="inicio/modal-abrir" de index.html).
// Antes era un modal; ahora es una pantalla (go('open')) que comparte pestañas con «Clonar URL Git».
// Solo muestra lo que devuelve Python al inspeccionar la carpeta: ruta, archivos .py y rama.
const ICO_ESCUDO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9 12 2 2 4-4"/></svg>';
const ICO_CARPETA = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7h6l2 2h10v10H3z"/></svg>';
const ICO_GIT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="9" r="2.5"/><path d="M6 8.5v7M18 11.5c0 3-4 3-10 5.5"/></svg>';
const ICO_FLECHA = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
const ICO_VOLVER = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>';
const ICO_OK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg>';
const ICO_ERROR = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>';
const ICO_CODIGO = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M6 3h9l4 4v14H6z"/><path d="m10.5 12-2 2 2 2M13.5 12l2 2-2 2"/></svg>';
const ICO_INFO ='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>';

// Pestañas compartidas por Abrir y Clonar: misma posición y aspecto en ambas pantallas.
const pestanasProyecto = activa => `<div class="np-pestanas" role="tablist" aria-label="Forma de abrir el proyecto">
  <button type="button" role="tab" aria-selected="${activa==='open'}" class="${activa==='open'?'on':''}" onclick="irAAbrir()">${ICO_CARPETA}Carpeta local</button>
  <button type="button" role="tab" aria-selected="${activa==='clone'}" class="${activa==='clone'?'on':''}" onclick="irAClonar()">${ICO_GIT}Clonar URL Git</button>
</div>`;
const barraProyecto = titulo => `<header class="ini-barra">
  <nav class="ini-migas" aria-label="Ubicación"><button type="button" class="np-miga" onclick="go('welcome')">Inicio</button><span aria-hidden="true">/</span><span aria-current="page">${titulo}</span></nav>
  <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
</header>`;

registrarComponente('inicio/modal-abrir', `<!-- ===== Abrir proyecto (carpeta local) ===== -->
<section id="s-open" class="scroll hide">
  <div class="welcome np">
    ${barraProyecto('Abrir proyecto')}
    <div class="ini-cuerpo">
      <div class="np-cabecera">
        <div>
          <h1 class="ini-titulo">Abre tu proyecto</h1>
          <p class="np-subtitulo">Elige una carpeta. Primero leeremos el código, sin ejecutarlo.</p>
        </div>
        <button type="button" class="ini-btn ini-btn-principal" id="openOk" disabled onclick="confirmOpen()">${ICO_FLECHA}Analizar proyecto</button>
      </div>
      ${pestanasProyecto('open')}
      <div class="np-rejilla">
        <div class="np-columna">
          <section class="np-tarjeta" aria-labelledby="openSelTitulo">
            <h2 id="openSelTitulo">Carpeta seleccionada</h2>
            <div id="openSel"></div>
            <!-- Solo en el navegador sin pywebview: carpetas de ejemplo en lugar del diálogo nativo -->
            <div class="np-demo hide" id="fsList" role="listbox" aria-label="Carpetas de ejemplo">
              <div role="option" data-p="ecommerce-core">${ICO_CARPETA}ecommerce-core</div>
              <div role="option" data-p="banco-pruebas-mvp">${ICO_CARPETA}banco-pruebas-mvp</div>
              <div role="option" data-p="landing-web">${ICO_CARPETA}landing-web</div>
            </div>
          </section>
          <section class="np-tarjeta hide" id="openContenido" aria-labelledby="openContTitulo">
            <h2 id="openContTitulo">Contenido de la carpeta</h2>
            <dl class="np-datos" id="openCount"></dl>
          </section>
          <div class="np-aviso np-aviso-info">${ICO_INFO}<div><b>Tú decides qué se prueba</b><span>En el siguiente paso podrás excluir carpetas y elegir funciones o endpoints.</span></div></div>
        </div>
        <div class="np-columna">
          <section class="np-tarjeta" id="openReconocido" aria-live="polite"></section>
          <section class="np-tarjeta">
            <h2>Antes de continuar</h2>
            <p class="np-texto">El análisis inicial no ejecuta el proyecto. Las pruebas se verificarán después en un entorno aislado, sin internet.</p>
            <p class="np-confirmacion">${ICO_ESCUDO}Sin cambios en tu código fuente</p>
          </section>
        </div>
      </div>
      <div class="np-pie">
        <button type="button" class="ini-enlace np-volver" onclick="go('welcome')">${ICO_VOLVER}Volver a Inicio</button>
        <span>Solo se abrirá la carpeta elegida.</span>
      </div>
    </div>
  </div>
</section>
`);

// HU-01: carpeta real elegida en el diálogo nativo (null = selector de ejemplo del navegador).
let realFolder = null;
let pickedFolder = null;   // carpeta elegida en el selector de ejemplo (navegador sin pywebview)
let estadoAbrir = null;    // lo que devolvió la inspección: {ok, ruta, cantidad_py, rama, error}
const MSG_INCOMPATIBLE = 'QAgent solo admite proyectos en Python 3.10 o superior, y esta carpeta no tiene archivos .py para analizar.';
// Datos de ejemplo del modo demostración (sin pywebview).
const DEMO_CARPETAS = {
  'ecommerce-core':    {ok:true,  ruta:'E:\\Proyectos\\ecommerce-core',    cantidad_py:12, rama:'main'},
  'banco-pruebas-mvp': {ok:true,  ruta:'E:\\Proyectos\\banco-pruebas-mvp', cantidad_py:9,  rama:'main'},
  'landing-web':       {ok:false, ruta:'E:\\Proyectos\\landing-web',       cantidad_py:0,  rama:null, error:MSG_INCOMPATIBLE},
};
const nombreCarpeta = ruta => String(ruta || '').split(/[\\/]/).filter(Boolean).pop() || '';

function irAAbrir(){
  if (typeof clonando !== 'undefined' && clonando) { toast('Espera a que termine la clonación.'); return; }
  renderAbrir(); go('open');
}

// Pinta la pantalla según estadoAbrir: sin carpeta, carpeta lista o carpeta no compatible.
function renderAbrir(){
  const e = estadoAbrir, demo = !(window.pywebview && window.pywebview.api);
  $('fsList').classList.toggle('hide', !demo);
  document.querySelectorAll('#fsList div').forEach(d => {
    const sel = d.dataset.p === pickedFolder;
    d.classList.toggle('sel', sel); d.setAttribute('aria-selected', String(sel));
  });
  $('openSel').innerHTML = e
    ? `<div class="np-carpeta"><span class="np-icono-carpeta">${ICO_CARPETA}</span><div class="np-carpeta-texto"><b>${escHtml(nombreCarpeta(e.ruta))}</b><span>${escHtml(e.ruta || '')}</span></div>
        ${demo ? '' : '<button type="button" class="ini-btn" onclick="handleOpenFolder()">Cambiar carpeta</button>'}</div>`
    : `<div class="np-sin-carpeta"><p>${demo ? 'Elige una de las carpetas de ejemplo.' : 'Todavía no elegiste una carpeta.'}</p>
        ${demo ? '' : '<button type="button" class="ini-btn" onclick="handleOpenFolder()">' + ICO_CARPETA + 'Elegir carpeta</button>'}</div>`;

  $('openContenido').classList.toggle('hide', !e);
  if(e){
    const n = e.cantidad_py || 0;
    $('openCount').innerHTML = `
      <div><dt>Archivos Python</dt><dd>${n} ${n === 1 ? 'encontrado' : 'encontrados'}</dd></div>
      <div><dt>Control de versiones</dt><dd>${e.rama ? 'Git · rama <span class="np-mono">' + escHtml(e.rama) + '</span>' : 'Sin repositorio Git'}</dd></div>
      <div><dt>No se analizan</dt><dd>Pruebas existentes, entornos virtuales y carpetas ocultas</dd></div>`;
  }

  if(!e){
    $('openReconocido').innerHTML = `<h2>Proyecto reconocido</h2><p class="np-texto">Elige una carpeta para ver qué encontramos.</p>`;
  } else if(e.ok){
    const n = e.cantidad_py || 0;
    $('openReconocido').innerHTML = `<h2>Proyecto reconocido</h2>
      <span class="np-chip np-chip-exito">${ICO_OK}Listo para analizar</span>
      <p class="np-proyecto">${escHtml(nombreCarpeta(e.ruta))}</p>
      <p class="np-lenguaje">${ICO_CODIGO}Python</p>
      <p class="np-meta">${n} ${n === 1 ? 'archivo .py encontrado' : 'archivos .py encontrados'} · lectura completada</p>`;
  } else {
    $('openReconocido').innerHTML = `<h2>Proyecto no compatible</h2>
      <span class="np-chip np-chip-bug">${ICO_ERROR}No se puede analizar</span>
      <p class="np-proyecto">${escHtml(nombreCarpeta(e.ruta))}</p>
      <p class="np-texto">${escHtml(e.error || MSG_INCOMPATIBLE)}</p>
      ${demo ? '' : '<button type="button" class="ini-btn" onclick="handleOpenFolder()">Elegir otra carpeta</button>'}`;
  }
  $('openOk').disabled = !(e && e.ok);
}

// Vuelve la pantalla a «sin carpeta» (se usa al entrar desde Inicio en el modo demostración).
function resetOpenModal() {
  realFolder = null; pickedFolder = null; estadoAbrir = null;
  renderAbrir();
}

// Muestra la carpeta real inspeccionada por Python: ruta, N archivos .py, rama y error si lo hay.
function showOpenReal(info) {
  realFolder = info.ok ? info.ruta : null;
  estadoAbrir = {ok: !!info.ok, ruta: info.ruta || '', cantidad_py: info.cantidad_py || 0, rama: info.rama || null, error: info.error || MSG_INCOMPATIBLE};
  renderAbrir();
  go('open');
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
    // Si abres el HTML en el navegador sin pywebview, se eligen carpetas de ejemplo
    resetOpenModal();
    go('open');
  }
}

// Revalida la carpeta en Python, la registra en recientes y abre la Vista previa (solo si tiene .py).
async function confirmOpenReal() {
  $('openOk').disabled = true;
  try {
    const info = await window.pywebview.api.abrir_proyecto(realFolder);
    if (!info.ok) { showOpenReal(info); return; }
    realFolder = null; estadoAbrir = null;
    if (typeof cargarRecientes === 'function') await cargarRecientes();
    // Sin repositorio Git no hay rama que mostrar.
    loadProject(info.nombre, 'local', info.ruta, info.rama || '—', info.ruta);
    toast(`Proyecto abierto: <span class="mono">${escHtml(info.ruta)}</span>`);
  } catch (err) {
    console.error("Error al abrir el proyecto:", err);
    showOpenReal({ok: false, ruta: realFolder, cantidad_py: 0, error: 'No se pudo abrir el proyecto. Inténtalo de nuevo.'});
  }
}

// Se llama desde main.js cuando el HTML de la pantalla ya está montado.
function iniciarModalAbrir(){
  document.querySelectorAll('#fsList div').forEach(d => {
    d.tabIndex = 0;
    d.onclick = () => {
      pickedFolder = d.dataset.p;
      estadoAbrir = DEMO_CARPETAS[pickedFolder];
      renderAbrir();
    };
    d.addEventListener('keydown', e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); d.click(); } });
  });
  renderAbrir();
}

function confirmOpen(){
  if (realFolder) { confirmOpenReal(); return; }
  if (!pickedFolder || !estadoAbrir || !estadoAbrir.ok) return;
  const carpeta = pickedFolder;
  pickedFolder = null; estadoAbrir = null;
  if (typeof demoRegistrar === 'function') demoRegistrar(carpeta, 'local', 'E:\\Proyectos\\'+carpeta);
  if (typeof cargarRecientes === 'function') cargarRecientes();
  loadProject(carpeta,'local','E:\\Proyectos\\'+carpeta);
}

// inicio.js — pantalla de inicio: proyectos recientes (HU-03)
// HTML del componente (se monta en el marcador data-componente="inicio/inicio" de index.html)
registrarComponente('inicio/inicio', `<!-- ===== 1. BIENVENIDA ===== -->
<section id="s-welcome" class="scroll">
  <div class="welcome">
    <h1>Bienvenido a QAgent</h1>
    <p>Genera y valida pruebas unitarias (pytest) de tu código Python.<br>Abre una carpeta de tu equipo o clona un repositorio Git.</p>
    <div class="actions">
      <button class="action" onclick="handleOpenFolder()">
        <span class="ico"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--blue-400)" stroke-width="1.8"><path d="M3 7h6l2 2h10v10H3z"/></svg></span>
        Abrir proyecto<small>Carpeta local con código Python</small>
      </button>
      <button class="action" onclick="openModal('m-clone')">
        <span class="ico"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--purple-400)" stroke-width="1.8"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="9" r="2.5"/><path d="M6 8.5v7M18 11.5c0 3-4 3-10 5.5"/></svg></span>
        Abrir repositorio<small>Clonar desde una URL Git (HTTPS)</small>
      </button>
    </div>
    <div class="recents hide" id="recents">
      <h3>Proyectos recientes <span class="pill p-grey" id="recCount"></span></h3>
      <div id="recList"></div>
    </div>
  </div>
</section>
`);

// App real: DesktopAPI.listar_recientes / abrir_reciente / quitar_reciente (~/.pyagent/recientes.json).
// Navegador sin pywebview: lista simulada de 11 proyectos; "inventario-api" tiene la carpeta renombrada.
const apiRec = () => (window.pywebview && window.pywebview.api && window.pywebview.api.listar_recientes) ? window.pywebview.api : null;
let DEMO_REC = ['ecommerce-core','banco-pruebas-mvp','inventario-api','tienda-utils','data-cleaner','chat-bot','reportes-pdf','scraper-precios','auth-service','geo-tools','legacy-scripts'].map((n,i) => ({
  nombre:n, origen:i%3===0?'git':'local', ruta:'E:\\Proyectos\\'+n, url:i%3===0?'https://github.com/retail-ai/'+n+'.git':null,
  ultima_apertura:new Date(Date.now()-i*864e5).toISOString(), encontrada:n!=='inventario-api',
  ultima_corrida:{0:'2026-09-25T14:32:00-05:00',1:'2026-09-19T16:40:00-05:00'}[i]||null}));
function demoRegistrar(name, src, where){
  const ruta = src==='git' ? 'E:\\Proyectos\\'+name : where;
  let r = DEMO_REC.find(x => x.ruta===ruta);
  if(!r){ r = {nombre:name, origen:src==='git'?'git':'local', ruta, url:src==='git'?where:null, ultima_corrida:null, encontrada:true}; DEMO_REC.push(r); }
  r.ultima_apertura = new Date().toISOString();
}
const fmtFecha = iso => { const d = new Date(iso), p = n => String(n).padStart(2,'0');
  return `${p(d.getDate())}/${p(d.getMonth()+1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`; };
let RECIENTES = [], demoListo = false;
async function cargarRecientes(){
  const api = apiRec();
  if(!api && !demoListo) return;   // pywebview aún no está listo: se espera 'pywebviewready'
  try {
    const todos = api ? await api.listar_recientes() : DEMO_REC.slice().sort((a,b) => b.ultima_apertura.localeCompare(a.ultima_apertura));
    RECIENTES = todos.slice(0,10);
  } catch (err) { console.error("Error al listar recientes:", err); RECIENTES = []; }
  renderRecientes();
}
function renderRecientes(){
  $('recents').classList.toggle('hide', !RECIENTES.length);
  $('recCount').textContent = RECIENTES.length + (RECIENTES.length===1 ? ' proyecto' : ' proyectos');
  $('recList').innerHTML = RECIENTES.map((r,i) => {
    const git = r.origen==='git', ok = r.encontrada;
    const ini = r.nombre.split(/[-_ .]/).filter(Boolean).slice(0,2).map(x=>x[0]).join('').toUpperCase() || '··';
    return `<div class="proj ${ok?'':'missing'}" ${ok?`onclick="abrirReciente(${i})"`:''}>
      <div class="av rinfo" style="background:var(${git?'--purple-s':'--blue-s'})">${escHtml(ini)}</div>
      <div class="rinfo" style="min-width:0"><div style="font-weight:600">${escHtml(r.nombre)} <span class="pill ${git?'p-purple':'p-blue'}">${git?'Git':'Local'}</span>${ok?'':' <span class="pill p-red">no encontrada</span>'}</div><div class="pth">${escHtml(r.ruta)}</div></div>
      <div class="meta rinfo">${r.ultima_corrida ? 'Última corrida<br>'+fmtFecha(r.ultima_corrida) : 'sin corridas aún'}</div>
      ${ok ? '' : `<button class="btn rm" onclick="event.stopPropagation();quitarReciente(${i})">Quitar de la lista</button>`}</div>`;
  }).join('');
}
async function abrirReciente(i){
  const r = RECIENTES[i]; if(!r) return;
  const api = apiRec();
  let info = {ok:true, nombre:r.nombre, origen:r.origen, url:r.url, ruta:r.ruta, rama:'main'};
  if(api){
    try { info = await api.abrir_reciente(r.ruta); }
    catch (err) { console.error("Error al abrir el reciente:", err); info = {ok:false, error:'No se pudo abrir el proyecto. Inténtalo de nuevo.'}; }
  }
  if(!info.ok){ toast(escHtml(info.error || 'No se pudo abrir el proyecto.')); cargarRecientes(); return; }
  loadProject(info.nombre, info.origen, info.origen==='git' && info.url ? info.url : info.ruta, info.rama || '—', info.ruta);
}
async function quitarReciente(i){
  const r = RECIENTES[i]; if(!r) return;
  try { if(apiRec()) await apiRec().quitar_reciente(r.ruta); else DEMO_REC = DEMO_REC.filter(x => x.ruta!==r.ruta); }
  catch (err) { console.error("Error al quitar el reciente:", err); }
  toast(`"${escHtml(r.nombre)}" se quitó de la lista. La carpeta no se borró.`);
  cargarRecientes();
}

// Se llama desde main.js cuando el HTML del componente ya está montado.
function iniciarInicio(){
  window.addEventListener('pywebviewready', cargarRecientes);
  setTimeout(() => { demoListo = true; if(!apiRec()) cargarRecientes(); }, 500);   // sin pywebview: modo demo
}

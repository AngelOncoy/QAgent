// inicio.js — pantalla de inicio: abrir o clonar un proyecto y proyectos recientes (HU-03)
// HTML del componente (se monta en el marcador data-componente="inicio/inicio" de index.html)
// Íconos en línea con stroke="currentColor": toman el color del texto, que viene de los tokens.
registrarComponente('inicio/inicio', `<!-- ===== 1. INICIO ===== -->
<section id="s-welcome" class="scroll">
  <div class="welcome">
    <header class="ini-barra">
      <nav class="ini-migas" aria-label="Ubicación"><span>Tu espacio</span><span aria-hidden="true">/</span><span aria-current="page">Inicio</span></nav>
      <span class="ini-confianza">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9 12 2 2 4-4"/></svg>
        Tu proyecto permanece en tu equipo
      </span>
    </header>

    <div class="ini-cuerpo">
      <h1 class="ini-titulo">¿Qué proyecto revisamos hoy?</h1>
      <p class="ini-subtitulo">Pruebas fiables, sin ejecutar tu código en tu máquina.</p>

      <section class="ini-hero" aria-labelledby="iniHeroTitulo">
        <div class="ini-hero-texto">
          <p class="ini-antetitulo">Del código a la confianza</p>
          <h2 id="iniHeroTitulo">Encuentra lo que falla.<br>Conserva lo que funciona.</h2>
          <p>QAgent analiza el proyecto, escribe pruebas con IA y las verifica en un entorno aislado, sin internet.</p>
          <div class="ini-acciones">
            <button type="button" class="ini-btn ini-btn-principal" onclick="handleOpenFolder()">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7h6l2 2h10v10H3z"/></svg>
              Abrir carpeta
            </button>
            <button type="button" class="ini-btn" onclick="irAClonar()">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="9" r="2.5"/><path d="M6 8.5v7M18 11.5c0 3-4 3-10 5.5"/></svg>
              Clonar URL Git
            </button>
          </div>
        </div>
        <ul class="ini-garantias">
          <li>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9 12 2 2 4-4"/></svg>
            <div><b>Tu máquina, protegida</b><span>El código solo se ejecuta en el entorno aislado.</span></div>
          </li>
          <li>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M8 12h8"/></svg>
            <div><b>La evidencia no se negocia</b><span>Un posible bug no se oculta debilitando pruebas.</span></div>
          </li>
          <li>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14-5l-2 2M4 13a8 8 0 0 0 14 5l2-2"/><path d="M4 4v4h4M20 20v-4h-4"/></svg>
            <div><b>Sin repetir trabajo</b><span>Si el código no cambió, reutilizamos lo ya hecho.</span></div>
          </li>
        </ul>
      </section>

      <section class="ini-recientes hide" id="recents" aria-labelledby="iniRecTitulo">
        <div class="ini-recientes-cab">
          <h2 id="iniRecTitulo">Proyectos recientes</h2>
          <span class="ini-contador" id="recCount"></span>
        </div>
        <div class="ini-lista" id="recList" role="list"></div>
      </section>

      <footer class="ini-pie">
        <span>Python · Próximamente Java, JavaScript y TypeScript</span>
        <span>Pruebas unitarias y de endpoints de API</span>
      </footer>
    </div>
  </div>
</section>
`);

// App real: DesktopAPI.listar_recientes / abrir_reciente / quitar_reciente (~/.qagent/recientes.json).
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
// Fecha legible: «Hoy, 14:32», «Ayer, 17:10» o «25 sep 2026, 14:32».
const MESES_CORTOS = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
const fmtFecha = iso => {
  const d = new Date(iso), p = n => String(n).padStart(2,'0'), hora = `${p(d.getHours())}:${p(d.getMinutes())}`;
  const dias = Math.round((new Date().setHours(0,0,0,0) - new Date(d).setHours(0,0,0,0)) / 864e5);
  if(dias === 0) return 'Hoy, ' + hora;
  if(dias === 1) return 'Ayer, ' + hora;
  return `${d.getDate()} ${MESES_CORTOS[d.getMonth()]} ${d.getFullYear()}, ${hora}`;
};
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
const ICO_QUITAR = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
const ICO_AVISO = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/></svg>';
function renderRecientes(){
  $('recents').classList.toggle('hide', !RECIENTES.length);
  $('recCount').textContent = RECIENTES.length + (RECIENTES.length===1 ? ' proyecto' : ' proyectos') + ' · En este equipo';
  $('recList').innerHTML = RECIENTES.map((r,i) => {
    const ok = r.encontrada;
    const ini = r.nombre.split(/[-_ .]/).filter(Boolean).slice(0,2).map(x=>x[0]).join('').toUpperCase() || '··';
    const esGit = r.origen === 'git';
    // El origen se distingue con texto e ícono, no con color: el color se reserva a los estados.
    const origen = esGit
      ? `<span class="ini-origen ini-origen-git" title="${escHtml(r.url || 'Repositorio Git')}">Git</span>`
      : '<span class="ini-origen ini-origen-carpeta" title="Carpeta de este equipo">Carpeta local</span>';
    const detalle = ok
      ? `${origen}<span class="ini-ruta">${escHtml(esGit && r.url ? r.url : r.ruta)}</span>`
      : '<span class="ini-ruta ini-ruta-aviso">Puede haberse movido o renombrado. Quítalo de la lista y ábrelo desde su nueva ubicación.</span>';
    const estado = ok
      ? `<span class="ini-etiqueta">Última corrida</span><span class="ini-fecha">${r.ultima_corrida ? fmtFecha(r.ultima_corrida) : 'Sin corridas aún'}</span>`
      : `<span class="ini-chip ini-chip-aviso">${ICO_AVISO}Carpeta no encontrada</span>`;
    return `<div class="ini-proyecto ${ok?'':'missing'}" role="listitem" ${ok?`onclick="abrirReciente(${i})"`:''}>
      <div class="ini-avatar" aria-hidden="true">${escHtml(ini)}</div>
      <div class="ini-proyecto-info">
        <div class="ini-nombre">${escHtml(r.nombre)}</div>
        <div class="ini-detalle">${detalle}</div>
      </div>
      <div class="ini-estado">${estado}</div>
      <div class="ini-proyecto-acciones">
        ${ok ? `<button type="button" class="ini-enlace" onclick="event.stopPropagation();abrirReciente(${i})">Reabrir</button>` : ''}
        <button type="button" class="ini-quitar" onclick="event.stopPropagation();quitarReciente(${i})" aria-label="Quitar ${escHtml(r.nombre)} de la lista">${ICO_QUITAR}<span>Quitar</span></button>
      </div>
    </div>`;
  }).join('');
}
async function abrirReciente(i){
  const r = RECIENTES[i]; if(!r) return;
  const api = apiRec();
  let info = {ok:true, nombre:r.nombre, origen:r.origen, url:r.url, ruta:r.ruta, rama:'main', ultima_corrida:r.ultima_corrida};
  if(api){
    try { info = await api.abrir_reciente(r.ruta); }
    catch (err) { console.error("Error al abrir el reciente:", err); info = {ok:false, error:'No se pudo abrir el proyecto. Inténtalo de nuevo.'}; }
  }
  if(!info.ok){ toast(escHtml(info.error || 'No se pudo abrir el proyecto.')); cargarRecientes(); return; }
  const yaCargoPrueba = !!(info.ya_cargo_prueba || info.tiene_corridas || info.tiene_pruebas || info.ultima_corrida || r.ultima_corrida);
  loadProject(info.nombre, info.origen, info.origen==='git' && info.url ? info.url : info.ruta, info.rama || '—', info.ruta, {
    esReciente: true,
    yaCargoPrueba: yaCargoPrueba,
    ultimaCorrida: info.ultima_corrida || r.ultima_corrida
  });
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
  setTimeout(() => {   // sin pywebview: modo demostración (lista simulada y controles de la demo)
    demoListo = true;
    if(!apiRec()){ cargarRecientes(); $('barraDemo').classList.remove('hide'); }
  }, 500);
}

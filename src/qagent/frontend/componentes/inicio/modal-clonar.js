// modal-clonar.js — pantalla «Clona un proyecto Git»: clonar desde URL Git (HU-02)
// HTML del componente (se monta en el marcador data-componente="inicio/modal-clonar" de index.html).
// Antes era un modal; ahora es una pantalla (go('clone')) que comparte pestañas con «Carpeta local».
// Usa los íconos y las piezas compartidas de modal-abrir.js (se carga antes).
const ICO_ENLACE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>';
const ICO_REINTENTAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>';
const ICO_AVISO_CLON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/></svg>';
const ICO_CIRCULO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/></svg>';
const ICO_GIRANDO = '<svg class="np-girando" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M21 12a9 9 0 1 1-9-9"/></svg>';

registrarComponente('inicio/modal-clonar', `<!-- ===== Clonar proyecto (URL Git, sin GitHub OAuth) ===== -->
<section id="s-clone" class="scroll hide">
  <div class="welcome np">
    ${barraProyecto('Clonar proyecto')}
    <div class="ini-cuerpo">
      <div class="np-cabecera">
        <div>
          <h1 class="ini-titulo">Clona un proyecto Git</h1>
          <p class="np-subtitulo">Trae una copia a tu equipo. El repositorio original no se modifica.</p>
        </div>
        <button type="button" class="ini-btn ini-btn-principal" id="cloneOk" disabled onclick="doClone()"><span id="cloneOkIco">${ICO_GIT}</span><span id="cloneOkTxt">Clonar proyecto</span></button>
      </div>
      ${pestanasProyecto('clone')}
      <div class="np-rejilla">
        <div class="np-columna">
          <section class="np-tarjeta" id="cloneForm" aria-labelledby="cloneFormTitulo">
            <h2 id="cloneFormTitulo">Origen y destino</h2>
            <label class="np-etiqueta" for="url">URL del repositorio</label>
            <div class="np-campo"><input class="np-input" id="url" placeholder="https://github.com/usuario/repositorio.git" autocomplete="off" spellcheck="false" oninput="vUrl()">${ICO_ENLACE}</div>
            <div class="np-ayuda" id="urlHint">Repositorio público por HTTPS (GitHub, GitLab o Bitbucket).</div>

            <label class="np-etiqueta" for="dir">Guardar copia en</label>
            <div class="np-campo-accion field-action">
              <div class="np-campo"><input class="np-input" id="dir" value="" placeholder="Se completa al escribir la URL" spellcheck="false" oninput="dirEditado=true;vUrl()"></div>
              <button type="button" class="ini-btn" id="browseClone" onclick="examinarDestinoClonado()">${ICO_CARPETA}Examinar…</button>
            </div>
            <div class="np-ayuda" id="dirHint">Examinar elige la carpeta donde se guardará; QAgent agrega el nombre del repositorio.</div>

            <details class="np-opciones">
              <summary>Opciones de clonado</summary>
              <label class="np-etiqueta" for="branch">Rama</label>
              <div class="np-campo np-campo-corto"><input class="np-input" id="branch" value="main" spellcheck="false" oninput="vUrl()"></div>
              <div class="np-ayuda np-ayuda-error hide" id="branchHint">Ese nombre de rama no es válido.</div>
              <label class="np-casilla"><input type="checkbox" id="shallow" checked><span>Copia ligera: solo la última versión, más rápida de descargar</span></label>
            </details>
          </section>

          <section class="np-tarjeta hide" id="cloneProg" aria-live="polite">
            <h2 id="cloneTitle">Clonando…</h2>
            <div class="np-progreso-cab"><span class="np-chip np-chip-progreso" id="cloneChip">${ICO_GIRANDO}Descargando</span><span class="np-pct" id="clonePct">0 %</span></div>
            <div class="np-barra"><i id="cloneBar"></i></div>
            <p class="np-texto" id="cloneEstado">Descargando los archivos del repositorio.</p>
            <div class="np-aviso np-aviso-aviso hide" id="cloneErr">${ICO_AVISO_CLON}<div><b>No pudimos completar la clonación</b><span id="cloneErrTxt"></span></div></div>
            <details class="np-detalle">
              <summary>Ver detalle técnico</summary>
              <div class="np-log" id="cloneLog"></div>
            </details>
          </section>
        </div>

        <div class="np-columna">
          <section class="np-tarjeta">
            <h2>Pasos de la clonación</h2>
            <ol class="np-pasos" id="clonePasos">
              <li data-paso="1"><span class="np-paso-ico"></span><div><b>Conectar con el repositorio</b><span class="np-paso-det"></span></div></li>
              <li data-paso="2"><span class="np-paso-ico"></span><div><b>Descargar archivos</b><span class="np-paso-det"></span></div></li>
              <li data-paso="3"><span class="np-paso-ico"></span><div><b>Reconocer el proyecto</b><span class="np-paso-det"></span></div></li>
            </ol>
          </section>
          <section class="np-tarjeta">
            <h2>Después de clonar</h2>
            <p class="np-texto">QAgent reconocerá el proyecto y mostrará qué archivos puedes probar. El análisis inicial no ejecuta el código.</p>
            <p class="np-meta">También puedes abrir una copia local que ya tengas.</p>
            <button type="button" class="ini-enlace np-enlace-icono" onclick="irAAbrir()">${ICO_CARPETA}Usar carpeta local</button>
          </section>
        </div>
      </div>
      <div class="np-pie">
        <button type="button" class="ini-enlace np-volver" id="cloneCancel" onclick="volverDeClonar()">${ICO_VOLVER}Volver a Inicio</button>
      </div>
    </div>
  </div>
</section>
`);

/* Clonar repositorio (HU-02): misma validación que qagent.proyectos.clonador */
const RE_URL_GIT = /^https:\/\/[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+\/[A-Za-z0-9_][A-Za-z0-9._-]*\/[A-Za-z0-9_][A-Za-z0-9._-]*$/;
const RE_RAMA_GIT = /^[A-Za-z0-9_][A-Za-z0-9._\/-]*$/;
const FORMATO_URL = 'https://<sitio>/<usuario>/<repositorio>(.git)';
const AYUDA_URL = 'Repositorio público por HTTPS (GitHub, GitLab o Bitbucket).';
let dirEditado = false, clonando = false, cloneTimer;
const hayPy = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.clonar_repositorio);
const ramaValida = b => RE_RAMA_GIT.test(b) && !/\.\.|\/\/|\/\.|[\/.]$|\.lock$/.test(b);
const nombreRepo = u => u.split('/').pop().replace(/\.git$/,'');
const destinoEnCarpeta = (carpeta, nombre) => carpeta.replace(/[\\/]+$/,'') + (carpeta.includes('\\') ? '\\' : '/') + nombre;

function irAClonar(){ if(!clonando) resetClone(); go('clone'); }
function volverDeClonar(){ if(clonando) return; go('welcome'); }

async function vUrl(){
  const v = $('url').value, b = $('branch').value;
  const ok = RE_URL_GIT.test(v), okB = ramaValida(b);
  $('urlHint').textContent = v && !ok ? 'La URL no es válida. Formato esperado: ' + FORMATO_URL : AYUDA_URL;
  $('urlHint').className = 'np-ayuda' + (v && !ok ? ' np-ayuda-error':'');
  $('branchHint').classList.toggle('hide', okB);
  $('browseClone').disabled = clonando || !ok;
  if(ok && !dirEditado){
    if(hayPy()){
      try { const r = await window.pywebview.api.destino_clonado(v); if(r.ok && !dirEditado && $('url').value===v) $('dir').value = r.destino; }
      catch(err){ console.error('Error al calcular el destino del clonado:', err); }
    } else $('dir').value = 'E:\\Proyectos\\' + nombreRepo(v);
  }
  $('cloneOk').disabled = clonando || !ok || !okB || !$('dir').value.trim();
}
async function examinarDestinoClonado(){
  const url = $('url').value;
  if(!RE_URL_GIT.test(url)) { toastError('Escribe primero una URL válida para conservar el nombre del repositorio.'); return; }
  const api = window.pywebview && window.pywebview.api;
  if(!(api && api.select_folder)) { toastError('El selector de carpetas solo está disponible en la aplicación de escritorio.'); return; }
  const anterior = $('dir').value;
  try {
    const carpetaPadre = await api.select_folder();
    if(!carpetaPadre) return;
    $('dir').value = destinoEnCarpeta(String(carpetaPadre), nombreRepo(url));
    dirEditado = true;
    $('dirHint').textContent = `Se guardará en ${$('dir').value}. Puedes editar la ruta.`;
    vUrl();
  } catch(err) {
    $('dir').value = anterior;
    toastError('No se pudo abrir el selector de carpetas: ' + escHtml(String(err)));
  }
}

/* Estado visual: pasos, chip, porcentaje y botón principal */
const ICO_PASO_CLON = {pendiente: ICO_CIRCULO, actual: ICO_GIRANDO, hecho: ICO_OK, error: ICO_AVISO_CLON};
function pasoClonado(n, estado, detalle){
  const li = document.querySelector(`#clonePasos li[data-paso="${n}"]`);
  li.className = 'np-paso-' + estado;
  li.querySelector('.np-paso-ico').innerHTML = ICO_PASO_CLON[estado];
  li.querySelector('.np-paso-det').textContent = detalle || '';
}
function reiniciarPasosClonado(){
  pasoClonado(1, 'pendiente', 'Comprobar la URL y el acceso');
  pasoClonado(2, 'pendiente', 'Traer los archivos a tu equipo');
  pasoClonado(3, 'pendiente', 'Buscar los archivos que se pueden probar');
}
function chipClonado(tipo, texto){
  const ico = {progreso: ICO_GIRANDO, aviso: ICO_AVISO_CLON, exito: ICO_OK}[tipo];
  $('cloneChip').className = 'np-chip np-chip-' + tipo;
  $('cloneChip').innerHTML = ico + escHtml(texto);
}
function porcentajeClonado(p){
  $('cloneBar').style.width = p + '%';
  $('clonePct').textContent = Math.round(p) + ' %';
}
function botonClonado(reintentar){
  $('cloneOkIco').innerHTML = reintentar ? ICO_REINTENTAR : ICO_GIT;
  $('cloneOkTxt').textContent = reintentar ? 'Reintentar clonación' : 'Clonar proyecto';
}
function bloquearFormularioClonado(si){
  ['url','dir','branch','shallow','browseClone'].forEach(id => { $(id).disabled = si; });
  $('cloneCancel').disabled = si;
}

function resetClone(){
  if(clonando) return;
  $('cloneProg').classList.add('hide'); $('cloneErr').classList.add('hide');
  $('cloneLog').innerHTML=''; porcentajeClonado(0); $('cloneTitle').textContent='Clonando…';
  reiniciarPasosClonado(); botonClonado(false);
  bloquearFormularioClonado(false); vUrl();
}
function logClone(txt){ const l = $('cloneLog'), d = document.createElement('div'); d.textContent = txt; l.appendChild(d); l.scrollTop = l.scrollHeight; }
function doClone(){
  const url = $('url').value, br = $('branch').value, dir = $('dir').value.trim(), shallow = $('shallow').checked;
  $('cloneErr').classList.add('hide'); $('cloneProg').classList.remove('hide'); $('cloneOk').disabled = true;
  $('cloneLog').innerHTML = ''; porcentajeClonado(0); $('cloneTitle').textContent = 'Clonando…';
  $('cloneEstado').textContent = 'Conectando con el repositorio.';
  chipClonado('progreso', 'Conectando'); botonClonado(false);
  reiniciarPasosClonado(); pasoClonado(1, 'actual', 'Comprobando la URL y el acceso');
  logClone(`$ git clone ${shallow?'--depth 1 ':''}--branch ${br} ${url} ${dir}`);
  if(hayPy()){
    clonando = true; bloquearFormularioClonado(true);
    window.pywebview.api.clonar_repositorio(url, br, dir, shallow).catch(err => finClonado({ok:false, error:String(err)}));
    return;
  }
  // Sin pywebview (HTML abierto en el navegador): clonado simulado del demo
  clonando = true; bloquearFormularioClonado(true);
  if(url.toLowerCase().includes('security-audit-skill') || url.toLowerCase().includes('landing-web') || url.toLowerCase().includes('react') || url.toLowerCase().includes('vue')){
    logClone(`Cloning into '${dir}'...`);
    avanceClonado({linea:'Receiving objects:  64% (136/212)', porcentaje:64});
    setTimeout(() => {
      finClonado({ok: false, error: 'QAgent solo admite proyectos en Python 3.10 o superior, y este repositorio no tiene archivos .py para analizar.'});
    }, 500);
    return;
  }
  if (typeof demoRegistrar === 'function') demoRegistrar(nombreRepo(url), 'git', url);
  const steps = [[`Cloning into '${dir}'...`, 10], ['Receiving objects:  64% (136/212)', 64], ['Receiving objects: 100% (212/212), 88.4 KiB, done.', 100]];
  let i = 0;
  cloneTimer = setInterval(() => {
    avanceClonado({linea: steps[i][0], porcentaje: steps[i][1]}); i++;
    if(i===steps.length){ clearInterval(cloneTimer); finClonado({ok:true, destino:dir}); }
  }, 450);
}
function avanceClonado(d){
  if(typeof d.porcentaje === 'number'){
    porcentajeClonado(d.porcentaje);
    pasoClonado(1, 'hecho', 'Repositorio encontrado');
    pasoClonado(2, 'actual', 'Descargando · ' + Math.round(d.porcentaje) + ' %');
    chipClonado('progreso', 'Descargando');
    $('cloneEstado').textContent = 'Descargando los archivos del repositorio.';
  }
  const l = $('cloneLog'), ult = l.lastElementChild;
  // git reescribe la misma línea (\r) mientras avanza: se actualiza en vez de agregar otra
  if(ult && d.linea.includes('%') && ult.textContent.split(':')[0] === d.linea.split(':')[0]) ult.textContent = d.linea;
  else logClone(d.linea);
}
async function finClonado(r){
  clonando = false; bloquearFormularioClonado(false);
  if(!r.ok){
    // Se detiene el avance y se muestra el motivo; la URL y el destino se conservan para reintentar
    clearInterval(cloneTimer);
    const msg = r.error || 'QAgent solo admite proyectos en Python 3.10 o superior.';
    const pct = $('clonePct').textContent;
    const enDescarga = document.querySelector('#clonePasos li[data-paso="2"]').className === 'np-paso-actual';
    if(enDescarga){
      pasoClonado(2, 'error', 'Interrumpido · ' + pct);
      pasoClonado(3, 'pendiente', 'Pendiente de completar la descarga');
    } else {
      pasoClonado(1, 'error', 'No se pudo conectar');
    }
    $('cloneTitle').textContent = 'Clonación interrumpida';
    chipClonado('aviso', 'Clonación interrumpida');
    $('cloneEstado').textContent = enDescarga ? 'La descarga se detuvo antes de terminar.' : 'No se pudo empezar la descarga.';
    $('cloneErrTxt').textContent = msg + ' Revisa la URL y tu conexión, y vuelve a intentarlo; no hace falta elegir otra carpeta.';
    $('cloneErr').classList.remove('hide');
    botonClonado(true);
    vUrl(); return;
  }
  $('cloneTitle').textContent = 'Listo'; porcentajeClonado(100);
  pasoClonado(1, 'hecho', 'Repositorio encontrado');
  pasoClonado(2, 'hecho', 'Descarga completa');
  pasoClonado(3, 'actual', 'Abriendo el proyecto');
  chipClonado('exito', 'Clonación completa');
  $('cloneEstado').textContent = 'El proyecto ya está en tu equipo. Abriéndolo…';
  const url = $('url').value, br = $('branch').value;
  await cargarRecientes();
  setTimeout(() => {
    pasoClonado(3, 'hecho', 'Proyecto listo');
    loadProject(nombreRepo(url), 'git', url, br, r.destino);
    const mensaje = `Repositorio clonado en <span class="mono">${escHtml(r.destino)}</span>`;
    if(r.advertencia) toast(`${mensaje}<br>Advertencia: ${escHtml(r.advertencia)}`, I('alertc','var(--aviso-t)',16), 8000);
    else toast(mensaje);
  }, 600);
}

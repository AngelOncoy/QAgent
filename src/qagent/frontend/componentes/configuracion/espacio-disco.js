// espacio-disco.js — sección «Espacio en disco» de Configuración y modal «Liberar espacio» (issue 267)
// La tarjeta (#cfgEspacio) está en configuracion.js; aquí se pinta con obtener_espacio_disco y se libera con
// liberar_espacio. Toda la lógica (qué ocupa QAgent, qué se borra) vive en Python (sandbox/uso_disco.py):
// esta pantalla solo muestra y pide confirmación.
// El HTML del modal de confirmación está en modal-espacio.js.

let USO_DISCO = null;          // última medición (DesktopAPI.obtener_espacio_disco)
let liberandoEspacio = false;  // mientras se borra no se cierra el modal ni se repite

const hayApiEspacio = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.obtener_espacio_disco);

// «3,2 GB» o «350 MB», igual que los mensajes de Python.
function tamanoTexto(bytes){
  const n = Number(bytes) || 0;
  if(n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(1).replace('.', ',') + ' GB';
  return Math.round(n / 1024 ** 2) + ' MB';
}
const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

// Pasos para que C: recupere el espacio: borrar dentro de Docker no achica docker_data.vhdx.
const PASOS_COMPACTAR = `<details class="esp-compactar">
  <summary>¿Por qué C: no recupera el espacio?</summary>
  <p class="np-meta">Liberar espacio libera lo de dentro de Docker, pero el disco virtual de Docker Desktop (<span class="np-mono">docker_data.vhdx</span>) no se achica solo: C: no recupera el espacio hasta compactarlo. En Windows:</p>
  <ol class="esp-pasos">
    <li>Cierra Docker Desktop.</li>
    <li>Abre PowerShell como administrador y ejecuta <span class="np-mono">wsl --shutdown</span>.</li>
    <li>Ejecuta <span class="np-mono">diskpart</span> y, dentro, estos comandos (cambia la ruta por la de tu equipo; suele ser <span class="np-mono">%LOCALAPPDATA%\\Docker\\wsl\\disk\\docker_data.vhdx</span>):
      <pre class="esp-codigo">select vdisk file="C:\\Users\\&lt;tu usuario&gt;\\AppData\\Local\\Docker\\wsl\\disk\\docker_data.vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit</pre></li>
    <li>Abre Docker Desktop de nuevo.</li>
  </ol>
</details>`;

function fila(nombre, nota, valor, clase = ''){
  return `<div class="esp-fila ${clase}"><dt>${nombre}${nota ? `<span class="np-meta">${nota}</span>` : ''}</dt><dd>${valor}</dd></div>`;
}

function renderEspacioDisco(){
  const caja = $('cfgEspacio');
  if(!caja) return;
  const titulo = '<h2>Espacio en disco</h2>';
  if(!hayApiEspacio()){
    caja.innerHTML = `${titulo}<p class="np-texto">Disponible en la aplicación de escritorio: aquí verás cuánto ocupa QAgent en Docker y podrás liberar espacio.</p>`;
    return;
  }
  const u = USO_DISCO;
  if(!u){
    caja.innerHTML = `${titulo}<span class="np-chip np-chip-progreso">${ICO_GIRANDO}Midiendo…</span>`;
    return;
  }
  const libre = u.libre_bytes == null ? null : u.libre_bytes;
  const pocoLibre = libre != null && u.minimo_bytes != null && libre < u.minimo_bytes;
  const chipLibre = libre == null ? '<span class="np-chip">Espacio libre desconocido</span>'
    : pocoLibre ? `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}Poco espacio libre: ${escHtml(tamanoTexto(libre))} (hacen falta ${escHtml(tamanoTexto(u.minimo_bytes))} para preparar el entorno)</span>`
    : `<span class="np-chip np-chip-exito">${ICO_OK}${escHtml(tamanoTexto(libre))} libres en el disco de Docker</span>`;
  let cuerpo;
  if(u.ok){
    const d = u.derivadas, tope = d.tope_bytes ? ` de ${escHtml(tamanoTexto(d.tope_bytes))} permitidos` : '';
    const r = u.restos;
    const restos = (r.contenedores || r.capas)
      ? `${plural(r.contenedores, 'contenedor', 'contenedores')} y ${plural(r.capas, 'capa', 'capas')} · ${escHtml(tamanoTexto(r.bytes))}`
      : 'Ninguno';
    const cache = u.cache.bytes == null ? 'No disponible' : escHtml(tamanoTexto(u.cache.bytes));
    cuerpo = `<dl class="esp-datos">
      ${fila('Imágenes base', 'se conservan', `${u.bases.cantidad} · ${escHtml(tamanoTexto(u.bases.bytes))}`)}
      ${fila('Imágenes de tus proyectos', 'dependencias ya instaladas; se vuelven a crear', `${d.cantidad} · ${escHtml(tamanoTexto(d.bytes))}${tope}`)}
      ${fila('Restos de construcciones cortadas', '', restos)}
      ${fila('Total de QAgent', 'sin la caché', escHtml(tamanoTexto(u.total_bytes)), 'esp-total')}
      ${fila('Caché de compilación de Docker', 'es de todos tus proyectos, no solo de QAgent', cache)}
    </dl>`;
  } else {
    cuerpo = `<p class="np-texto">${escHtml(u.mensaje || 'No se pudo medir lo que ocupa QAgent en Docker.')}</p>`;
  }
  caja.innerHTML = `${titulo}
    <p class="np-texto">Lo que QAgent guarda en Docker para ejecutar tus pruebas en el entorno aislado.</p>
    ${cuerpo}
    <div class="esp-libre">${chipLibre}</div>
    <div class="esp-acciones">
      <button type="button" class="ini-btn" id="espLiberar" onclick="abrirModalEspacio()" ${u.ok ? '' : 'disabled'}>Liberar espacio</button>
      <button type="button" class="ini-btn" onclick="cargarEspacioDisco()">${ICO_REINTENTAR}Medir de nuevo</button>
    </div>
    ${PASOS_COMPACTAR}`;
}

async function cargarEspacioDisco(){
  if(!hayApiEspacio()){ renderEspacioDisco(); return; }
  USO_DISCO = null; renderEspacioDisco();
  try {
    USO_DISCO = await window.pywebview.api.obtener_espacio_disco();
  } catch (err) {
    console.error('Error al medir el espacio en disco:', err);
    USO_DISCO = {ok:false, mensaje:'No se pudo medir el espacio en disco.'};
  }
  renderEspacioDisco();
}

// Qué se borra, según la medición de Python (la misma que ve la tarjeta).
function listaDeBorrado(u){
  const items = [];
  if(u.derivadas.cantidad) items.push(`${plural(u.derivadas.cantidad, 'imagen', 'imágenes')} de tus proyectos (las dependencias ya instaladas), unos ${tamanoTexto(u.derivadas.bytes)}. La próxima corrida que las necesite las vuelve a crear, con internet.`);
  if(u.restos.contenedores) items.push(`${plural(u.restos.contenedores, 'contenedor sobrante', 'contenedores sobrantes')} de corridas o construcciones interrumpidas.`);
  if(u.restos.capas) items.push(`${plural(u.restos.capas, 'capa', 'capas')} sin etiqueta que dejaron construcciones cortadas (${tamanoTexto(u.restos.bytes)}).`);
  return items;
}

async function abrirModalEspacio(){
  if(!hayApiEspacio()){ toast('Disponible en la aplicación de escritorio.'); return; }
  let u;
  try { u = await window.pywebview.api.obtener_espacio_disco(); }
  catch (err) { console.error('Error al medir el espacio en disco:', err); u = null; }
  if(!u || !u.ok){ toastError(escHtml((u && u.mensaje) || 'No se pudo medir lo que ocupa QAgent en Docker.')); return; }
  USO_DISCO = u; renderEspacioDisco();
  const borra = listaDeBorrado(u);
  $('espBorra').innerHTML = (borra.length ? borra : ['Nada por ahora: QAgent no tiene restos ni imágenes de proyectos que borrar.']).map(t => `<li>${escHtml(t)}</li>`).join('');
  $('espConserva').innerHTML = [
    `Las imágenes base del entorno aislado (${plural(u.bases.cantidad, 'imagen', 'imágenes')}, ${tamanoTexto(u.bases.bytes)}): son lo más lento de volver a descargar.`,
    'La imagen de una corrida en curso (no se puede liberar espacio mientras corre una).',
    'Todo lo que no sea de QAgent: tus otras imágenes, contenedores y volúmenes de Docker.',
    'Tus proyectos, las pruebas guardadas y los resultados.',
  ].map(t => `<li>${escHtml(t)}</li>`).join('');
  // La caché de compilación no se puede separar por dueño: el aviso se muestra siempre y borrarla es opcional.
  const dias = u.cache && u.cache.dias;
  $('espCacheAviso').innerHTML = `<b>Sobre la caché de compilación de Docker:</b> afecta a <b>toda</b> la caché de compilación de Docker, no solo a la de QAgent (también la de tus otros proyectos). Solo se borra la que lleva más de ${escHtml(String(dias || '—'))} días sin usarse y lo único que pasa es que esos <span class="np-mono">docker build</span> tardarán más la próxima vez.`;
  $('espCacheFila').classList.toggle('hide', !dias);
  $('espCache').checked = false;
  $('espCacheTexto').textContent = `Borrar también la caché de compilación de Docker sin usar en más de ${dias} días` + (u.cache.bytes == null ? '' : ` (hasta ${tamanoTexto(u.cache.bytes)})`);
  $('espEstado').className = 'api-estado'; $('espEstado').textContent = '';
  $('espConfirmar').disabled = false; $('espCancelar').disabled = false;
  openModal('m-espacio');
}

function cerrarModalEspacio(){
  if(liberandoEspacio) return;   // no se cierra a mitad del borrado
  closeModal();
}

async function confirmarLiberarEspacio(){
  if(liberandoEspacio || !hayApiEspacio()) return;
  liberandoEspacio = true;
  $('espConfirmar').disabled = true; $('espCancelar').disabled = true;
  $('espEstado').className = 'api-estado'; $('espEstado').textContent = 'Liberando espacio… puede tardar un momento.';
  let r;
  try { r = await window.pywebview.api.liberar_espacio($('espCache').checked); }
  catch (err) { console.error('Error al liberar espacio:', err); r = {ok:false, mensaje:'No se pudo liberar el espacio.'}; }
  liberandoEspacio = false;
  if(r.uso){ USO_DISCO = r.uso; renderEspacioDisco(); }
  if(r.ok){
    closeModal();
    toast(escHtml(r.mensaje));
  } else {
    $('espEstado').className = 'api-estado no';
    $('espEstado').textContent = r.mensaje || 'No se pudo liberar el espacio.';
    $('espConfirmar').disabled = !!r.en_curso; $('espCancelar').disabled = false;
  }
}

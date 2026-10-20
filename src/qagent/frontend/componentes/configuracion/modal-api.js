// modal-api.js — modal «Agregar API» de un agente: proveedor, modelo y API key (HU-30)
// HTML del componente (se monta en el marcador data-componente="configuracion/modal-api" de index.html)
registrarComponente('configuracion/modal-api', `<!-- Agregar o editar la API de un agente -->
<div class="overlay" id="m-api"><div class="modal">
  <div class="mhead"><span id="apiTitulo">Agregar API</span><button class="x" onclick="cerrarModalApi()">×</button></div>
  <div class="mcontent">
    <div class="frow"><label for="apiProveedor">Proveedor</label><select class="inp" id="apiProveedor" onchange="apiEligioProveedor()"></select></div>
    <div class="frow"><label for="apiModelo">Modelo</label><select class="inp" id="apiModelo" onchange="apiEligioModelo()"></select></div>
    <div class="hint warn hide" id="apiTipo" style="margin:0"></div>
    <label class="chk hide" id="apiReusarFila"><input type="checkbox" id="apiReusar" onchange="apiCambioReusar()"> <span id="apiReusarTexto">Mantener la key actual de este agente</span> <span class="mono" id="apiReusarMascara"></span></label>
    <div class="frow" id="apiClaveFila"><label for="apiClave">API key</label><input class="inp" id="apiClave" type="password" autocomplete="off" spellcheck="false" placeholder="Pega aquí tu API key"></div>
    <div class="hint" style="margin:0">Conviene una clave por etapa: se puede repetir, pero las etapas que la comparten comparten su límite de uso. Se guarda solo en tu equipo y nunca se muestra completa.<span id="apiVariable" hidden></span></div>
    <div class="api-estado" id="apiEstado" role="status" aria-live="polite"></div>
  </div>
  <div class="mfoot"><button class="btn" id="apiCancelar" onclick="cerrarModalApi()">Cancelar</button><button class="btn primary" id="apiGuardar" onclick="guardarApi()">Probar y guardar</button></div>
</div></div>
`);

let proveedoresApi = [];   // catálogo (DesktopAPI.listar_proveedores)
let agenteApi = null;      // agente que se está configurando
let probandoApi = false;

const proveedorElegido = () => proveedoresApi.find(p => p.id === $('apiProveedor').value);

async function abrirModalApi(agente){
  if(!hayApiDeRoles()){ toast('Disponible en la aplicación de escritorio.'); return; }
  try {
    proveedoresApi = await window.pywebview.api.listar_proveedores();
  } catch (err) {
    console.error('Error al leer el catálogo de proveedores:', err);
    toastError('No se pudo leer la lista de proveedores.');
    return;
  }
  agenteApi = agente;
  const rol = rolesApi.find(r => r.agente === agente) || {nombre: agente};
  const etapa = (typeof ETAPA !== 'undefined' && ETAPA[agente]) ? ETAPA[agente].t : rol.nombre;
  $('apiTitulo').textContent = `${rol.configurado ? 'Editar' : 'Agregar'} conexión · ${etapa}`;
  $('apiProveedor').innerHTML = proveedoresApi.map(p => `<option value="${escHtml(p.id)}">${escHtml(p.nombre)}${p.genera_texto ? '' : ' — ' + escHtml(p.tipo_nombre)}</option>`).join('');
  // Se parte de la API guardada; si no hay, de la última selección; si no, de la primera de la lista.
  const base = rol.configurado && rol.tiene_clave ? rol : (seleccionApi[agente] || (rol.configurado ? rol : null));
  if(base && proveedoresApi.some(p => p.id === (base.proveedor))) $('apiProveedor').value = base.proveedor;
  apiCambioProveedor(base ? base.modelo : null);
  mostrarEstadoApi('', '');
  openModal('m-api');
}

// Key actual del agente: se puede mantener si sigue con el mismo proveedor (aunque otro
// agente use la misma). La key de otro agente nunca se ofrece.
function claveActualDelAgente(p){
  const rol = rolesApi.find(r => r.agente === agenteApi) || {};
  const sirve = rol.configurado && rol.proveedor === p.id && rol.tiene_clave;
  return sirve ? rol : null;
}

// La lista de modelos depende del proveedor; no se puede escribir un modelo a mano.
function apiCambioProveedor(modeloInicial = null){
  const p = proveedorElegido();
  if(!p) return;
  $('apiModelo').innerHTML = p.modelos.map(m => `<option value="${escHtml(m.id)}">${escHtml(m.nombre)}</option>`).join('');
  if(modeloInicial && p.modelos.some(m => m.id === modeloInicial)) $('apiModelo').value = modeloInicial;
  $('apiVariable').textContent = (p.variables || {})[agenteApi] || '';
  const actual = claveActualDelAgente(p);
  $('apiReusarFila').classList.toggle('hide', !actual);
  $('apiReusarTexto').textContent = actual ? `Mantener la key actual del ${actual.nombre}` : '';
  $('apiReusarMascara').textContent = actual ? `(${actual.clave_enmascarada})` : '';
  $('apiReusar').checked = !!actual;
  $('apiClave').value = '';
  apiCambioReusar();
  apiCambioModelo();
  mostrarEstadoApi('', '');
}

// El usuario cambió proveedor o modelo: queda como última selección aunque cancele.
function guardarSeleccionApi(){
  const p = proveedorElegido();
  if(!p || !agenteApi || !$('apiModelo').value) return;
  recordarSeleccion(agenteApi, {proveedor: p.id, proveedor_nombre: p.nombre, modelo: $('apiModelo').value});
}
function apiEligioProveedor(){ apiCambioProveedor(); guardarSeleccionApi(); }
function apiEligioModelo(){ apiCambioModelo(); guardarSeleccionApi(); }

function apiCambioModelo(){
  const p = proveedorElegido();
  const aviso = $('apiTipo');
  if(p && !p.genera_texto){
    aviso.textContent = `Los modelos de ${p.nombre} son de tipo «${p.tipo_nombre}» y no generan texto: se pueden guardar, pero las llamadas de este agente fallarán durante la corrida.`;
    aviso.classList.remove('hide');
  } else {
    aviso.classList.add('hide');
  }
}

function apiCambioReusar(){
  const reusar = $('apiReusar').checked && !$('apiReusarFila').classList.contains('hide');
  $('apiClaveFila').classList.toggle('hide', reusar);
  if(reusar) $('apiClave').value = '';
}

function mostrarEstadoApi(clase, html){
  $('apiEstado').className = 'api-estado' + (clase ? ' ' + clase : '');
  $('apiEstado').innerHTML = html;
}

function cerrarModalApi(){
  if(probandoApi) return;   // no se cierra a mitad de la prueba de conexión
  $('apiClave').value = '';
  closeModal();
}

async function guardarApi(){
  const p = proveedorElegido();
  if(!p || !agenteApi) return;
  const reusar = $('apiReusar').checked && !!claveActualDelAgente(p);
  const clave = reusar ? '' : $('apiClave').value.trim();
  if(!reusar && !clave){ mostrarEstadoApi('no', `Escribe la API key de ${escHtml(p.nombre)}.`); return; }
  probandoApi = true;
  ['apiGuardar','apiCancelar'].forEach(id => $(id).disabled = true);
  mostrarEstadoApi('', 'Probando la conexión…');
  let r;
  try {
    r = await window.pywebview.api.guardar_api_rol(agenteApi, p.id, $('apiModelo').value, clave || null);
  } catch (err) {
    console.error('Error al guardar la API:', err);
    r = {ok:false, mensaje:'No se pudo completar la prueba de conexión.'};
  } finally {
    probandoApi = false;
    ['apiGuardar','apiCancelar'].forEach(id => $(id).disabled = false);
  }
  if(r.ok){
    $('apiClave').value = '';
    const aviso = r.aviso ? `<div class="hint warn" style="margin:4px 0 0">${escHtml(r.aviso)}</div>` : '';
    mostrarEstadoApi('ok', escHtml(r.mensaje) + aviso);
    recordarSeleccion(agenteApi, null);   // ya está guardada: manda la API real
    rolesActualizados(r.roles);
    // Con aviso se deja más tiempo para leerlo.
    setTimeout(() => { if(!probandoApi && $('apiEstado').classList.contains('ok')) closeModal(); }, r.aviso ? 4000 : 1200);
  } else {
    const detalle = r.detalle ? `<div class="hint" style="margin:4px 0 0">${escHtml(r.detalle)}</div>` : '';
    mostrarEstadoApi('no', `✕ ${escHtml(r.mensaje)} · no se guardó nada.${detalle}`);
  }
}

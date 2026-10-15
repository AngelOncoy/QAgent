// configuracion.js — pantalla «Configuración del sistema»: API de cada agente (HU-30), límites y entorno
// HTML del componente (se monta en el marcador data-componente="configuracion/configuracion" de index.html)
registrarComponente('configuracion/configuracion', `<!-- ===== CONFIGURACIÓN DEL SISTEMA ===== -->
<section id="s-config" class="hide scroll">
  <div class="page">
    <div class="card"><div class="projhead">
      <span class="t">Configuración del sistema</span>
    </div></div>
    <div class="card">
      <h4>Modelo de cada agente</h4>
      <div class="table-scroll"><table class="cfg-roles"><thead><tr><th>Agente</th><th>Proveedor y modelo</th><th>API key</th><th></th></tr></thead><tbody id="cfgAgents"></tbody></table></div>
    </div>
    <details class="card cfg-avanzado">
      <summary>Límites de cada corrida y más información</summary>
      <div class="bd checks" id="cfgLimits"></div>
      <div class="bd checks">
        <div class="c"><span class="i ok">✓</span><div>Al guardar una API se hace una llamada de prueba; si falla, no se guarda nada. Conviene una key distinta por agente: si dos la comparten, también comparten su límite de uso.</div></div>
        <div class="c"><span class="i ok">✓</span><div>Tus claves se guardan en tu carpeta <span class="mono">~/.qagent/</span>, enmascaradas aquí y nunca dentro del sandbox ni del repositorio.</div></div>
        <div class="c"><span class="i ok">✓</span><div>Sandbox: contenedor <span class="mono">qagent-sandbox:base</span>, <b>sin red</b> y sin acceso a los archivos del equipo.</div></div>
        <div class="c"><span class="i ok">✓</span><div>Resultados, specs y pruebas guardadas: <span class="mono">&lt;proyecto&gt;/.qagent/</span></div></div>
        <div class="c"><span class="i ok">✓</span><div>Tipo de cambio para costos: S/ 3.37 por US$.</div></div>
      </div>
    </details>
  </div>
</section>
`);

const COLOR_AGENTE = {planner:'var(--blue-300)', generator:'var(--purple-300)', reviewer:'var(--green-300)'};
// Logo de cada proveedor: SVG propio o PNG de assets/proveedores/. Sin logo, un círculo neutro.
const SVG_LOGO = d => `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const LOGO_PROVEEDOR = {
  anthropic:  `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M13.8 3h-3.5L4 21h3.4l1.2-3.4h6.8l1.2 3.4H20zM9.6 14.6 12 7.6l2.4 7z"/></svg>`,
  gemini:     `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M12 2c.6 5.4 4.6 9.4 10 10-5.4.6-9.4 4.6-10 10-.6-5.4-4.6-9.4-10-10 5.4-.6 9.4-4.6 10-10z"/></svg>`,
  openrouter: SVG_LOGO('<path d="M3 12h5l3-6h6m0 0-2-2m2 2-2 2M8 12l3 6h6m0 0-2-2m2 2-2 2"/>'),
  groq:       SVG_LOGO('<circle cx="12" cy="12" r="8"/><path d="M12 8v4h4"/>'),
  xiaomi:     '<img src="assets/proveedores/xiaomi.png" width="18" height="18" alt="">',
  openai:     '<img src="assets/proveedores/openai.png" width="18" height="18" alt="">',
};
const LOGO_OTRO = SVG_LOGO('<circle cx="12" cy="12" r="8"/>');
// Icono de cada agente (rol), con el color del agente.
const ICONO_AGENTE = {
  planner:   SVG_LOGO('<path d="M9 6h11M9 12h11M9 18h11"/><path d="m3.5 6 1.2 1.2L7 5M3.5 12l1.2 1.2L7 11M3.5 18l1.2 1.2L7 17"/>'),
  generator: SVG_LOGO('<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>'),
  reviewer:  SVG_LOGO('<path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-8 7-10V6z"/><path d="m9 12 2 2 4-4"/>'),
};
let rolesApi = [];          // estado de cada agente (DesktopAPI.obtener_roles)
let eliminarPendiente = null;

const hayApiDeRoles = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.obtener_roles);

function insigniaProveedor(id, nombre){
  const clase = LOGO_PROVEEDOR[id] ? id : 'otro';
  return `<span class="prov-logo prov-${clase}" role="img" aria-label="${escHtml(nombre || id || '')}">${LOGO_PROVEEDOR[id] || LOGO_OTRO}</span>`;
}

// Última selección de proveedor y modelo de cada agente, aunque no se haya guardado la API:
// sobrevive a «Cancelar» y a cerrar el programa (solo es una comodidad de esta ventana).
const CLAVE_SELECCION = 'qagent.seleccionApi';
let seleccionApi = {};
try { seleccionApi = JSON.parse(localStorage.getItem(CLAVE_SELECCION) || '{}') || {}; } catch (_) { seleccionApi = {}; }
function recordarSeleccion(agente, sel){
  if(sel) seleccionApi[agente] = sel; else delete seleccionApi[agente];
  try { localStorage.setItem(CLAVE_SELECCION, JSON.stringify(seleccionApi)); } catch (_) { /* sin almacenamiento: queda en memoria */ }
  pintarRoles();
}

function filaRol(r){
  const boton = `<button class="btn btn-api" onclick="abrirModalApi('${r.agente}')">${r.configurado && r.tiene_clave ? 'Editar' : 'Agregar API'}</button>`;
  const agente = `<div class="cfg-agente"><span class="cfg-ico" style="color:${COLOR_AGENTE[r.agente]}">${ICONO_AGENTE[r.agente] || ''}</span><b style="color:${COLOR_AGENTE[r.agente]}">${escHtml(r.nombre)}</b>${boton}</div>`;
  const avisos = [];
  let modelo, clave, eliminar = '';
  if(r.configurado && r.tiene_clave){
    if(!r.genera_texto) avisos.push(`<div class="hint warn" style="margin:2px 0 0">Modelo de tipo «${escHtml(r.tipo_nombre)}»: no genera texto; las llamadas del ${escHtml(r.nombre)} fallarán.</div>`);
    if((r.clave_repetida_con || []).length) avisos.push(`<div class="hint warn" style="margin:2px 0 0">Usa la misma API key que el ${(r.clave_repetida_con).map(escHtml).join(' y el ')}: comparten el límite de uso del proveedor.</div>`);
    modelo = `<div class="cfg-modelo">${insigniaProveedor(r.proveedor, r.proveedor_nombre)}<div><div class="mono">${escHtml(r.modelo)}</div><div class="sub">${escHtml(r.proveedor_nombre)}</div>${avisos.join('')}</div></div>`;
    clave = `<span class="mono">${escHtml(r.clave_enmascarada)}</span>`;
    eliminar = `<button class="btn" onclick="eliminarApi('${r.agente}')">${eliminarPendiente === r.agente ? 'Confirmar' : 'Eliminar'}</button>`;
  } else {
    // Sin API key se muestra lo último que se eligió (con el logo de su proveedor), o «No seleccionado».
    const sel = seleccionApi[r.agente];
    modelo = sel
      ? `<div class="cfg-modelo">${insigniaProveedor(sel.proveedor, sel.proveedor_nombre)}<div><div class="mono">${escHtml(sel.modelo)}</div><div class="sub">${escHtml(sel.proveedor_nombre)}</div></div></div>`
      : '<span class="cfg-vacio">No seleccionado</span>';
    clave = '<span class="pill p-red">Falta</span>';
  }
  return `<tr><td>${agente}</td><td>${modelo}</td><td>${clave}</td><td style="text-align:right">${eliminar}</td></tr>`;
}

function pintarRoles(){
  $('cfgAgents').innerHTML = rolesApi.map(filaRol).join('');
}

async function cargarRoles(){
  if(!hayApiDeRoles()){
    // Demostración en el navegador: el catálogo y las keys solo existen en la app de escritorio.
    rolesApi = ['planner','generator','reviewer'].map(a => ({agente:a, nombre:a[0].toUpperCase() + a.slice(1), configurado:false}));
    pintarRoles();
    return;
  }
  try {
    rolesApi = await window.pywebview.api.obtener_roles();
  } catch (err) {
    console.error('Error al leer la configuración de los agentes:', err);
    toastError('No se pudo leer la configuración de los agentes.');
    return;
  }
  pintarRoles();
}

// Tras guardar o eliminar: la tabla y el bloqueo de «Iniciar corrida» se ponen al día.
function rolesActualizados(roles){
  if(roles) rolesApi = roles;
  pintarRoles();
  if(typeof verificarEntorno === 'function' && window.pywebview) verificarEntorno();
}

async function eliminarApi(agente){
  if(!hayApiDeRoles()){ toast('Disponible en la aplicación de escritorio.'); return; }
  if(eliminarPendiente !== agente){
    // Primer clic: pide confirmación en el mismo botón durante unos segundos.
    eliminarPendiente = agente; pintarRoles();
    setTimeout(() => { if(eliminarPendiente === agente){ eliminarPendiente = null; pintarRoles(); } }, 4000);
    return;
  }
  eliminarPendiente = null;
  let r;
  try { r = await window.pywebview.api.eliminar_api_rol(agente); }
  catch (err) { console.error('Error al eliminar la API:', err); r = {ok:false, mensaje:'No se pudo eliminar.'}; }
  if(r.ok){ toast(escHtml(r.mensaje)); delete seleccionApi[agente]; try { localStorage.setItem(CLAVE_SELECCION, JSON.stringify(seleccionApi)); } catch (_) {} }
  else toastError(escHtml(r.mensaje));
  rolesActualizados(r.roles);
}

function renderConfig(){
  cargarRoles();
  $('cfgLimits').innerHTML = `
    <div class="c"><span class="i ok">✓</span><div><b>Tope de gasto: S/ ${TOPE_PEN.toFixed(2)} por corrida</b><div class="hint" style="margin:0">La corrida no inicia si el costo estimado lo supera, y se detiene si el gasto real lo alcanza.</div></div></div>
    <div class="c"><span class="i ok">✓</span><div><b>Reintentos: ${MAX_RETRIES} por prueba</b><div class="hint" style="margin:0">Corte anticipado si el mismo error se repite dos veces seguidas.</div></div></div>
    <div class="c"><span class="i ok">✓</span><div><b>Mutation testing: solo en funciones críticas</b><div class="hint" style="margin:0">Nunca sobre el repositorio completo.</div></div></div>
    <div class="c"><span class="i ok">✓</span><div><b>Specs: se reutilizan si la huella del código no cambió</b></div></div>`;
}

// configuracion.js — pantalla «Configuración del sistema»: API de cada agente (HU-30), límites y entorno
// HTML del componente (se monta en el marcador data-componente="configuracion/configuracion" de index.html)
registrarComponente('configuracion/configuracion', `<!-- ===== CONFIGURACIÓN DEL SISTEMA ===== -->
<section id="s-config" class="hide scroll">
  <div class="page">
    <div class="card"><div class="projhead">
      <span class="t">Configuración del sistema</span>
      <span class="pill p-grey">Se guarda en tu carpeta <span class="mono">~/.qagent/</span> · claves solo en <span class="mono">.env</span></span>
    </div></div>
    <div class="card">
      <h4>Modelo de cada agente</h4>
      <div class="table-scroll"><table class="cfg-roles"><thead><tr><th>Agente</th><th>Proveedor y modelo</th><th>API key</th><th></th></tr></thead><tbody id="cfgAgents"></tbody></table></div>
      <div class="hint" style="padding:10px 16px 14px">Cada agente puede usar un proveedor distinto, o el mismo que otro agente. Conviene una API key por agente: si dos agentes comparten la key, también comparten su límite de uso. Al guardar se hace una llamada de prueba con la key y el modelo elegidos; si falla, no se guarda nada. Cada corrida guarda en su registro qué modelos usó.</div>
    </div>
    <div class="grid2 cfg-grid">
      <div class="card"><h4>Límites de cada corrida</h4><div class="bd checks" id="cfgLimits"></div></div>
      <div class="card"><h4>Entorno y datos</h4><div class="bd checks">
        <div class="c"><span class="i ok">✓</span><div>Sandbox: contenedor <span class="mono">qagent-sandbox:base</span>, <b>sin red</b> y sin acceso a los archivos del equipo</div></div>
        <div class="c"><span class="i ok">✓</span><div>Claves de IA: solo en <span class="mono">.env</span> · aquí se ven enmascaradas, nunca se suben al repositorio y nunca entran al sandbox</div></div>
        <div class="c"><span class="i ok">✓</span><div>Resultados, specs y pruebas guardadas: <span class="mono">&lt;proyecto&gt;/.qagent/</span></div></div>
        <div class="c"><span class="i ok">✓</span><div>Tipo de cambio para costos: S/ 3.37 por US$ (carta del proyecto)</div></div>
      </div></div>
    </div>
    <div class="card">
      <h4>Cómo se guarda</h4>
      <div class="bd"><p class="hint" style="margin:0 0 10px">«Agregar API» escribe la key en <span class="mono">~/.qagent/.env</span> (una variable por agente, ej. <span class="mono">GEMINI_API_KEY_PLANNER</span>) y en <span class="mono">~/.qagent/config.local.toml</span> solo el proveedor y el modelo del agente. Eso tiene prioridad sobre los modelos por defecto del equipo (<span class="mono">config.toml</span>, que viaja con el programa y no se modifica). La lista de proveedores y modelos se edita en <span class="mono">src/qagent/llm/proveedores.toml</span>.</p>
<pre class="rcode"># ~/.qagent/config.local.toml
[agentes.planner]
proveedor = "gemini"
modelo = "gemini-2.5-flash"
precio_entrada_usd_m = 0
precio_salida_usd_m = 0

# ~/.qagent/.env (no se sube al repositorio)
# GEMINI_API_KEY_PLANNER=...</pre></div>
    </div>
  </div>
</section>
`);

const COLOR_AGENTE = {planner:'var(--blue-300)', generator:'var(--purple-300)', reviewer:'var(--green-300)'};
const SIGLA_PROVEEDOR = {anthropic:'A', xiaomi:'Mi', openai:'OA', openrouter:'OR', gemini:'G', groq:'GQ'};
let rolesApi = [];          // estado de cada agente (DesktopAPI.obtener_roles)
let eliminarPendiente = null;

const hayApiDeRoles = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.obtener_roles);

// Insignia del proveedor: iniciales sobre su color (tokens --prov-* de tokens.css).
function insigniaProveedor(id){
  const clase = SIGLA_PROVEEDOR[id] ? id : 'otro';
  return `<span class="prov-logo prov-${clase}" aria-hidden="true">${escHtml(SIGLA_PROVEEDOR[id] || '?')}</span>`;
}

function filaRol(r){
  const boton = `<button class="btn btn-api" onclick="abrirModalApi('${r.agente}')">${r.configurado ? 'Editar' : 'Agregar API'}</button>`;
  const agente = `<div class="cfg-agente"><b style="color:${COLOR_AGENTE[r.agente]}">${escHtml(r.nombre)}</b>${boton}</div>`;
  if(!r.configurado){
    return `<tr><td>${agente}</td><td colspan="3"><span class="pill p-amber">Sin configurar</span> <span class="hint" style="margin:0 0 0 6px">No se pueden iniciar corridas hasta configurarlo.</span></td></tr>`;
  }
  const avisos = [];
  if(!r.genera_texto) avisos.push(`<div class="hint warn" style="margin:2px 0 0">Modelo de tipo «${escHtml(r.tipo_nombre)}»: no genera texto; las llamadas del ${escHtml(r.nombre)} fallarán.</div>`);
  if(!r.en_catalogo) avisos.push('<div class="hint warn" style="margin:2px 0 0">Modelo fuera del catálogo (editado a mano).</div>');
  if((r.clave_repetida_con || []).length) avisos.push(`<div class="hint warn" style="margin:2px 0 0">Usa la misma API key que el ${(r.clave_repetida_con).map(escHtml).join(' y el ')}: comparten el límite de uso del proveedor. Si se agota pronto, pulsa «Editar» y pon otra.</div>`);
  if(r.configurado && !r.desde_local) avisos.push('<div class="hint" style="margin:2px 0 0">Modelo por defecto del equipo (config.toml): agrega tu API para usar la tuya.</div>');
  const clave = r.tiene_clave
    ? `<span class="mono">${escHtml(r.clave_enmascarada)}</span><div class="sub">${escHtml(r.variable)}</div>`
    : `<span class="pill p-red">Falta la key</span><div class="sub">${escHtml(r.variable || '')}</div>`;
  const eliminar = eliminarPendiente === r.agente ? 'Confirmar' : 'Eliminar';
  return `<tr><td>${agente}</td>
    <td><div class="cfg-modelo">${insigniaProveedor(r.proveedor)}<div><div class="mono">${escHtml(r.modelo)}</div><div class="sub">${escHtml(r.proveedor_nombre)}</div>${avisos.join('')}</div></div></td>
    <td>${clave}</td>
    <td style="text-align:right"><button class="btn" onclick="eliminarApi('${r.agente}')">${eliminar}</button></td></tr>`;
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
  if(r.ok) toast(escHtml(r.mensaje)); else toastError(escHtml(r.mensaje));
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

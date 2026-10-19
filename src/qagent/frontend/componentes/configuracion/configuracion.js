// configuracion.js — pantalla «Configuración»: conexión de IA por etapa (HU-30), motor, límites y apariencia
// HTML del componente (se monta en el marcador data-componente="configuracion/configuracion" de index.html)
// Cada etapa (analizar, escribir pruebas, verificar) tiene su propio proveedor, modelo y clave: así lo guarda
// el backend. Los íconos compartidos (ICO_*) vienen de inicio/modal-abrir.js y modal-clonar.js.
const ICO_FLECHA_ABAJO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
registrarComponente('configuracion/configuracion', `<!-- ===== CONFIGURACIÓN ===== -->
<section id="s-config" class="hide scroll">
  <div class="welcome cfg">
    <header class="ini-barra">
      <nav class="ini-migas" aria-label="Ubicación"><span>Tu espacio</span><span aria-hidden="true">/</span><span aria-current="page">Configuración</span></nav>
      <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
    </header>
    <div class="ini-cuerpo">
      <div class="np-cabecera">
        <div>
          <h1 class="ini-titulo">Tu entorno, bajo control</h1>
          <p class="np-subtitulo">Conecta la IA, revisa el motor y los límites de cada corrida.</p>
        </div>
        <button type="button" class="ini-btn ini-btn-principal" id="cfgGuardar" disabled onclick="guardarLimites()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>
          Guardar configuración
        </button>
      </div>

      <div class="np-rejilla cfg-rejilla">
        <div class="np-columna">
          <section class="np-tarjeta" aria-labelledby="cfgEtapasTitulo">
            <h2 id="cfgEtapasTitulo">Conexión de IA por etapa</h2>
            <p class="np-texto">Cada etapa puede usar su propio proveedor y modelo. Al guardar se prueba la conexión; si falla, no se guarda nada.</p>
            <div class="cfg-etapas" id="cfgAgents"></div>
            <p class="np-meta">Tus claves se guardan solo en tu equipo. Aquí se ven enmascaradas y nunca entran al entorno aislado ni a tu proyecto. Si dos etapas usan la misma clave, comparten su límite de uso.</p>
          </section>

          <section class="np-tarjeta" aria-labelledby="cfgLimitesTitulo">
            <h2 id="cfgLimitesTitulo">Límites de verificación</h2>
            <div class="cfg-limites">
              <div class="cfg-campo">
                <label class="np-etiqueta" for="cfgIntentos">Máximo de intentos</label>
                <div class="np-campo cfg-select"><select class="np-input" id="cfgIntentos" onchange="limitesCambiaron()"></select>${ICO_FLECHA_ABAJO}</div>
                <span class="np-meta" id="cfgIntentosAyuda">Entre 1 y 3 por función</span>
              </div>
              <div class="cfg-campo">
                <label class="np-etiqueta" for="cfgTiempo">Tiempo máximo por prueba</label>
                <div class="np-campo cfg-select"><select class="np-input" id="cfgTiempo" disabled title="Lo define el equipo para todas las corridas"></select>${ICO_FLECHA_ABAJO}</div>
                <span class="np-meta">Si se supera, verás «Tiempo agotado». Lo define el equipo.</span>
              </div>
            </div>
            <span class="np-meta cfg-estado-guardado" id="cfgLimitesEstado" role="status" aria-live="polite"></span>
          </section>
        </div>

        <div class="np-columna">
          <section class="np-tarjeta" id="cfgMotor" aria-live="polite"></section>

          <section class="np-tarjeta" aria-labelledby="cfgAparienciaTitulo">
            <h2 id="cfgAparienciaTitulo">Apariencia</h2>
            <div class="cfg-temas" role="radiogroup" aria-labelledby="cfgAparienciaTitulo">
              <button type="button" class="cfg-tema cfg-tema-oscuro on" id="temaOscuro" role="radio" aria-checked="true" onclick="elegirTema('oscuro')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg>
                <span>Oscuro</span>
              </button>
              <button type="button" class="cfg-tema cfg-tema-claro" id="temaClaro" role="radio" aria-checked="false" onclick="elegirTema('claro')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
                <span>Claro</span>
              </button>
            </div>
            <p class="np-meta" id="cfgTemaAyuda">Grafito sobre superficie clara en modo claro, oscuro por defecto.</p>
          </section>

          <div class="np-aviso np-aviso-info">${ICO_INFO}<div><b>El criterio no cambia</b><span>La IA no puede debilitar una prueba para ocultar un posible bug, sin importar el modelo elegido.</span></div></div>
        </div>
      </div>
    </div>
  </div>
</section>
`);

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
// Nombre de cada etapa para personas (los agentes internos no se nombran en la interfaz).
const ETAPA = {
  planner:   {t:'Analizando',          d:'Lee el código y decide qué casos probar.'},
  generator: {t:'Escribiendo pruebas', d:'Escribe la prueba de cada función o endpoint.'},
  reviewer:  {t:'Verificando',         d:'Revisa los resultados en el entorno aislado.'},
};
let rolesApi = [];          // estado de cada etapa (DesktopAPI.obtener_roles)
let eliminarPendiente = null;

const hayApiDeRoles = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.obtener_roles);

function insigniaProveedor(id, nombre){
  const clase = LOGO_PROVEEDOR[id] ? id : 'otro';
  return `<span class="prov-logo prov-${clase}" role="img" aria-label="${escHtml(nombre || id || '')}">${LOGO_PROVEEDOR[id] || LOGO_OTRO}</span>`;
}

// Última selección de proveedor y modelo de cada etapa, aunque no se haya guardado la API:
// sobrevive a «Cancelar» y a cerrar el programa (solo es una comodidad de esta ventana).
const CLAVE_SELECCION = 'qagent.seleccionApi';
let seleccionApi = {};
try { seleccionApi = JSON.parse(localStorage.getItem(CLAVE_SELECCION) || '{}') || {}; } catch (_) { seleccionApi = {}; }
function recordarSeleccion(agente, sel){
  if(sel) seleccionApi[agente] = sel; else delete seleccionApi[agente];
  try { localStorage.setItem(CLAVE_SELECCION, JSON.stringify(seleccionApi)); } catch (_) { /* sin almacenamiento: queda en memoria */ }
  pintarRoles();
}

// Una etapa: nombre, proveedor y modelo, estado de la clave y acciones.
function filaRol(r){
  const etapa = ETAPA[r.agente] || {t: r.nombre, d: ''};
  const conectada = r.configurado && r.tiene_clave;
  const avisos = [];
  let modelo, estado, eliminar = '';
  if(conectada){
    if(!r.genera_texto) avisos.push(`<span class="cfg-aviso">Este modelo es de tipo «${escHtml(r.tipo_nombre)}» y no genera texto: la etapa fallará durante la corrida.</span>`);
    if((r.clave_repetida_con || []).length) avisos.push(`<span class="cfg-aviso">Comparte la clave con ${(r.clave_repetida_con).map(n => escHtml((ETAPA[String(n).toLowerCase()] || {t:n}).t)).join(' y ')}: comparten su límite de uso.</span>`);
    modelo = `<div class="cfg-modelo">${insigniaProveedor(r.proveedor, r.proveedor_nombre)}<div><b>${escHtml(r.modelo)}</b><span class="np-meta">${escHtml(r.proveedor_nombre)} · <span class="np-mono">${escHtml(r.clave_enmascarada)}</span></span></div></div>`;
    estado = `<span class="np-chip np-chip-exito">${ICO_OK}Conectada</span>`;
    eliminar = `<button type="button" class="ini-enlace cfg-quitar" onclick="eliminarApi('${r.agente}')">${eliminarPendiente === r.agente ? 'Confirmar' : 'Quitar'}</button>`;
  } else {
    // Sin clave se muestra lo último que se eligió (con el logo de su proveedor), o «No seleccionado».
    const sel = seleccionApi[r.agente];
    modelo = sel
      ? `<div class="cfg-modelo">${insigniaProveedor(sel.proveedor, sel.proveedor_nombre)}<div><b>${escHtml(sel.modelo)}</b><span class="np-meta">${escHtml(sel.proveedor_nombre)}</span></div></div>`
      : '<span class="cfg-vacio">No seleccionado</span>';
    estado = `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}Falta la clave</span>`;
  }
  const boton = `<button type="button" class="ini-btn" onclick="abrirModalApi('${r.agente}')">${r.configurado && r.tiene_clave ? 'Editar' : 'Agregar API'}</button>`;
  return `<div class="cfg-etapa">
    <div class="cfg-etapa-nombre"><b>${etapa.t}</b><span class="np-meta">${etapa.d}</span></div>
    <div class="cfg-etapa-modelo">${modelo}${avisos.join('')}</div>
    <div class="cfg-etapa-estado">${estado}</div>
    <div class="cfg-etapa-acciones">${boton}${eliminar}</div>
  </div>`;
}

function pintarRoles(){
  $('cfgAgents').innerHTML = rolesApi.map(filaRol).join('');
}

async function cargarRoles(){
  if(!hayApiDeRoles()){
    // Demostración en el navegador: el catálogo y las claves solo existen en la app de escritorio.
    rolesApi = ['planner','generator','reviewer'].map(a => ({agente:a, nombre:a[0].toUpperCase() + a.slice(1), configurado:false}));
    pintarRoles();
    return;
  }
  try {
    rolesApi = await window.pywebview.api.obtener_roles();
  } catch (err) {
    console.error('Error al leer la configuración de las etapas:', err);
    toastError('No se pudo leer la conexión de IA de cada etapa.');
    return;
  }
  pintarRoles();
}

// Tras guardar o quitar: las etapas y el bloqueo de «Iniciar prueba» se ponen al día.
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
  catch (err) { console.error('Error al eliminar la API:', err); r = {ok:false, mensaje:'No se pudo quitar.'}; }
  if(r.ok){ toast(escHtml(r.mensaje)); delete seleccionApi[agente]; try { localStorage.setItem(CLAVE_SELECCION, JSON.stringify(seleccionApi)); } catch (_) {} }
  else toastError(escHtml(r.mensaje));
  rolesActualizados(r.roles);
}

/* Motor de ejecución: estado real (estado_sandbox, que consulta la barra lateral) y qué hacer.
   QAgent no inicia Docker por su cuenta: se explica cómo y se puede volver a comprobar. */
const PASOS_MOTOR = {
  no_iniciado:  ['Abre Docker Desktop en tu equipo.', 'Espera a que indique que está en ejecución.', 'Pulsa «Comprobar de nuevo».'],
  no_instalado: ['Instala Docker Desktop desde su sitio oficial.', 'Ábrelo y espera a que esté en ejecución.', 'Pulsa «Comprobar de nuevo».'],
};
function renderMotorConfig(){
  if(!$('cfgMotor')) return;
  const demo = !(window.pywebview && window.pywebview.api && window.pywebview.api.estado_sandbox);
  const m = typeof ESTADO_MOTOR !== 'undefined' ? ESTADO_MOTOR : null;
  const clave = demo ? 'ok' : (m ? m.clave : null);
  const ui = clave ? SANDBOX_UI[clave] : null;
  const chip = !ui ? `<span class="np-chip np-chip-progreso">${ICO_GIRANDO}Comprobando…</span>`
    : clave === 'ok' ? `<span class="np-chip np-chip-exito">${ICO_OK}${ui.label}</span>`
    : clave === 'opcional' ? `<span class="np-chip">${ui.label}</span>`
    : clave === 'no_instalado' ? `<span class="np-chip np-chip-bug">${ICO_ERROR}${ui.label}</span>`
    : `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}${ui.label}</span>`;
  const texto = !ui ? 'Revisando el entorno aislado.'
    : clave === 'ok' ? 'El entorno aislado está listo: las pruebas se ejecutan sin internet y sin acceso a tu equipo.'
    : clave === 'opcional' ? 'Con la IA simulada no se ejecuta nada en el entorno aislado.'
    : (m && m.mensaje) || ui.detalle;
  const pasos = PASOS_MOTOR[clave];
  $('cfgMotor').innerHTML = `<h2>Motor de ejecución</h2>${chip}
    <p class="np-texto">${escHtml(texto)}</p>
    ${pasos ? `<ol class="cfg-pasos-motor">${pasos.map(p => `<li>${p}</li>`).join('')}</ol>` : ''}
    ${demo ? '' : `<button type="button" class="ini-btn" onclick="comprobarMotor()">${ICO_REINTENTAR}Comprobar de nuevo</button>`}`;
}
async function comprobarMotor(){
  ESTADO_MOTOR = null; renderMotorConfig();
  await actualizarSandbox();
  if(typeof verificarEntorno === 'function') verificarEntorno();
}

/* Límites de verificación (obtener_limites / guardar_limites). Los intentos por función se
   guardan en la configuración de este equipo; el tiempo máximo por prueba lo define el equipo
   de QAgent y solo se muestra. Preparar lee LIMITES para «Hasta N intentos por función». */
let LIMITES = {max_intentos: 3, intentos_min: 1, intentos_max: 3, timeout_s: 120};
const hayApiLimites = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.obtener_limites);
async function cargarLimites(){
  if(hayApiLimites()){
    try {
      const r = await window.pywebview.api.obtener_limites();
      if(r && r.ok) LIMITES = r;
      else if(r) $('cfgLimitesEstado').textContent = r.mensaje;
    } catch (err) { console.error('Error al leer los límites:', err); }
  }
  pintarLimites();
}
function pintarLimites(){
  const {max_intentos, intentos_min, intentos_max, timeout_s} = LIMITES;
  const opciones = [];
  for(let n = intentos_min; n <= intentos_max; n++) opciones.push(`<option value="${n}" ${n === max_intentos ? 'selected' : ''}>${n}</option>`);
  $('cfgIntentos').innerHTML = opciones.join('');
  $('cfgIntentosAyuda').textContent = `Entre ${intentos_min} y ${intentos_max} por función`;
  $('cfgTiempo').innerHTML = `<option selected>${timeout_s} segundos</option>`;
  $('cfgGuardar').disabled = true;
}
function limitesCambiaron(){
  $('cfgGuardar').disabled = Number($('cfgIntentos').value) === LIMITES.max_intentos;
  $('cfgLimitesEstado').textContent = '';
}
async function guardarLimites(){
  const valor = Number($('cfgIntentos').value);
  if(!hayApiLimites()){ toast('Disponible en la aplicación de escritorio.'); return; }
  $('cfgGuardar').disabled = true;
  let r;
  try { r = await window.pywebview.api.guardar_limites(valor); }
  catch (err) { console.error('Error al guardar los límites:', err); r = {ok:false, mensaje:'No se pudo guardar la configuración.'}; }
  if(r.limites && r.limites.ok) LIMITES = r.limites;
  pintarLimites();
  $('cfgLimitesEstado').textContent = r.mensaje || '';
  if(r.ok) toast(escHtml(r.mensaje)); else toastError(escHtml(r.mensaje));
  if(typeof calc === 'function') { try { calc(); } catch (_) { /* sin proyecto abierto */ } }
}
window.addEventListener('pywebviewready', cargarLimites, {once:true});

/* Apariencia / Tema (obtener_tema / guardar_tema).
   Guarda en ~/.qagent/config.local.toml y aplica data-theme="claro" / data-tema="claro" en <html> */
let temaActual = 'oscuro';
try { temaActual = localStorage.getItem('qagent.tema') || 'oscuro'; } catch (_) {}

function aplicarTema(tema){
  temaActual = (tema === 'claro') ? 'claro' : 'oscuro';
  if(temaActual === 'claro'){
    document.documentElement.setAttribute('data-theme', 'claro');
    document.documentElement.setAttribute('data-tema', 'claro');
  } else {
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.removeAttribute('data-tema');
  }
  try { localStorage.setItem('qagent.tema', temaActual); } catch (_) {}
  pintarTema();
}

function pintarTema(){
  const oscuroBtn = $('temaOscuro');
  const claroBtn = $('temaClaro');
  if(oscuroBtn && claroBtn){
    const esClaro = temaActual === 'claro';
    oscuroBtn.classList.toggle('on', !esClaro);
    oscuroBtn.setAttribute('aria-checked', String(!esClaro));
    claroBtn.classList.toggle('on', esClaro);
    claroBtn.setAttribute('aria-checked', String(esClaro));
  }
}

async function cargarTema(){
  if(window.pywebview && window.pywebview.api && window.pywebview.api.obtener_tema){
    try {
      const r = await window.pywebview.api.obtener_tema();
      if(r && r.ok && r.tema){
        aplicarTema(r.tema);
        return;
      }
    } catch (err) { console.error('Error al leer el tema:', err); }
  }
  pintarTema();
}

async function elegirTema(tema){
  aplicarTema(tema);
  if(window.pywebview && window.pywebview.api && window.pywebview.api.guardar_tema){
    try {
      const r = await window.pywebview.api.guardar_tema(tema);
      if(r && r.ok) toast(escHtml(r.mensaje || `Apariencia: tema ${tema}.`));
    } catch (err) {
      console.error('Error al guardar el tema:', err);
    }
  }
}
window.addEventListener('pywebviewready', cargarTema, {once:true});
aplicarTema(temaActual);

function renderConfig(){
  cargarRoles();
  renderMotorConfig();
  cargarLimites();
  cargarTema();
}

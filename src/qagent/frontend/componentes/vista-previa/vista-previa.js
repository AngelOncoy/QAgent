// vista-previa.js — pantalla «Explorar»: elige qué probar a partir del análisis del proyecto (sin ejecutarlo)
// HTML del componente (se monta en el marcador data-componente="vista-previa/vista-previa" de index.html)
// Cifras del proyecto, carpetas incluidas, tabla de funciones y endpoints con buscador, y avisos.
// Los íconos (ICO_*) vienen de inicio/modal-abrir.js, que se carga antes.
const ICO_BUSCAR = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/></svg>';
const ICO_AVISO_EXP = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/></svg>';
registrarComponente('vista-previa/vista-previa', `<!-- ===== 2. EXPLORAR ===== -->
<section id="s-preview" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <header class="ini-barra">
    <nav class="ini-migas" aria-label="Ubicación"><span class="repoName"></span><span aria-hidden="true">/</span><span aria-current="page">Exploración</span></nav>
    <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
  </header>
  <div class="scroll"><div class="page exp">

    <div class="np-cabecera">
      <div>
        <h1 class="ini-titulo">Elige qué quieres probar</h1>
        <p class="np-subtitulo"><span class="repoName"></span> · Python · pytest<span class="hide" id="projRama"> · rama <span class="brLbl"></span></span> · Análisis sin ejecutar el proyecto</p>
      </div>
      <button type="button" class="ini-btn ini-btn-principal" id="toTests" onclick="go('tests')">${ICO_FLECHA}<span id="toTestsTxt">Preparar selección</span></button>
    </div>

    <!-- Cifras del proyecto -->
    <div class="exp-cifras">
      <div class="exp-cifra"><span class="exp-cifra-etq">Archivos</span><b id="resumenModulos">0</b><span class="exp-cifra-sub" id="resumenArchivosSub"></span></div>
      <div class="exp-cifra"><span class="exp-cifra-etq">Funciones</span><b id="resumenFunciones">0</b><span class="exp-cifra-sub" id="resumenFuncionesSub"></span></div>
      <div class="exp-cifra"><span class="exp-cifra-etq">Endpoints API</span><b id="resumenEndpoints">0</b><span class="exp-cifra-sub" id="resumenEndpointsSub"></span></div>
    </div>

    <div class="exp-rejilla">
      <!-- Carpetas incluidas -->
      <section class="np-tarjeta exp-carpetas" aria-labelledby="expCarpetasTitulo">
        <h2 id="expCarpetasTitulo">Carpetas incluidas</h2>
        <div class="tree" id="tree"></div>
        <p class="exp-nota">Las dependencias y pruebas existentes no se incluyen en la selección.</p>
      </section>

      <!-- Funciones y endpoints -->
      <section class="exp-objetivos" aria-label="Funciones y endpoints">
        <div class="exp-herramientas">
          <label class="exp-todo"><input type="checkbox" class="exp-caja" id="expTodo" onchange="seleccionarTodosObjetivos(this.checked)"><span><span id="expTodoTxt">Seleccionar todas las funciones</span> (<span id="expTodoN">0</span>)</span></label>
          <span class="exp-contador" id="fnCount"></span>
        </div>
        <div class="exp-filtros">
          <label class="np-campo exp-buscar"><span class="exp-buscar-ico">${ICO_BUSCAR}</span><input class="np-input" id="expBuscar" type="search" placeholder="Buscar función, endpoint o archivo" autocomplete="off" spellcheck="false" oninput="buscarObjetivos(this.value)" aria-label="Buscar función, endpoint o archivo"></label>
          <div class="obj-switch" role="tablist" aria-label="Tipo de objetivo">
            <button type="button" id="tabFns" class="obj-tab on" role="tab" aria-selected="true" aria-controls="vistaFns" onclick="cambiarVistaObjetivos('funciones')">Funciones (<span id="tabFnsN">0</span>)</button>
            <button type="button" id="tabEps" class="obj-tab" role="tab" aria-selected="false" aria-controls="vistaEps" onclick="cambiarVistaObjetivos('endpoints')">Endpoints (<span id="tabEpsN">0</span>)</button>
          </div>
        </div>

        <div id="vistaFns" class="obj-vista">
          <div class="table-scroll fn-scroll"><table class="fn-table">
            <thead><tr>
              <th class="col-incl"><span class="vh">Incluir</span></th>
              <th>Función / endpoint</th>
              <th>Complejidad</th>
              <th>Desde la última vez</th>
              <th class="col-prof">Profundizar</th>
            </tr></thead>
            <tbody id="fnTable"></tbody>
          </table></div>
        </div>
        <div id="vistaEps" class="obj-vista hide">
          <div class="table-scroll ep-scroll"><table class="ep-table">
            <thead><tr>
              <th class="col-incl"><span class="vh">Incluir</span></th>
              <th>Función / endpoint</th>
              <th>Complejidad</th>
              <th>Desde la última vez</th>
              <th class="col-prof">Profundizar</th>
            </tr></thead>
            <tbody id="endpointTable"></tbody>
          </table></div>
        </div>
        <p class="exp-pie"><span id="expMostrando"></span><span id="footMsg"></span><span id="expCambios"></span></p>
      </section>
    </div>

    <!-- Archivos que no se pudieron leer -->
    <div class="np-aviso np-aviso-aviso exp-errores hide" id="expErrores">${ICO_AVISO_EXP}<div><b id="expErroresTitulo"></b><div id="expErroresLista"></div></div></div>

  </div></div>
  <div id="tipFlotante" class="tip-flotante" role="tooltip" hidden></div>
</section>
`);

let PROYECTO_RESUMEN = null;
let PROYECTO_ERRORES = [];
// Vista de objetivos activa: 'funciones' (por defecto) o 'endpoints' (issue #66).
let VISTA_OBJETIVOS = 'funciones';
let BUSQUEDA = '';   // texto del buscador de la tabla, en minúsculas

// Al cargar otro proyecto, la tabla vuelve a Funciones y sin búsqueda.
function reiniciarVistaExplorar() {
  VISTA_OBJETIVOS = 'funciones';
  BUSQUEDA = '';
  $('expBuscar').value = '';
}

function aplicarResumenDemo() {
  reiniciarVistaExplorar();
  const modValidos = MODULES.filter(m => !m.error);
  const fns = modValidos.flatMap(m => m.fns);
  const total = fns.length;
  const totalEndpoints = modValidos.flatMap(m => m.endpoints || []).length;
  const sinDoc = fns.filter(f => !f.doc).length;
  const sinTipos = fns.filter(f => !f.typed).length;
  const conAlguna = fns.filter(f => !f.doc || !f.typed).length;
  PROYECTO_RESUMEN = {
    total_modulos: modValidos.length,
    total_funciones_publicas: total,
    total_endpoints: totalEndpoints,
    total_errores: MODULES.filter(m => m.error).length,
    inconsistencias: {
      sin_docstring: { cantidad: sinDoc, porcentaje: total ? +(sinDoc / total * 100).toFixed(1) : 0 },
      sin_tipos: { cantidad: sinTipos, porcentaje: total ? +(sinTipos / total * 100).toFixed(1) : 0 },
      con_alguna: { cantidad: conAlguna, porcentaje: total ? +(conAlguna / total * 100).toFixed(1) : 0 }
    }
  };
  PROYECTO_ERRORES = MODULES.filter(m => m.error).map(m => m.error);
  actualizarResumenUI(PROYECTO_RESUMEN, PROYECTO_ERRORES);
}

// Cifras de la cabecera. Archivos = los que se pudieron leer más los que no; la selección
// (funciones y endpoints elegidos) la completa renderFns() cada vez que cambia.
function actualizarResumenUI(resumen, errores = []) {
  if (!resumen) return;
  const legibles = resumen.total_modulos ?? 0;
  const conError = resumen.total_errores ?? (errores ? errores.length : 0);
  $('resumenModulos').textContent = legibles + conError;
  $('resumenArchivosSub').textContent = conError
    ? `${legibles} ${legibles === 1 ? 'legible' : 'legibles'} · ${conError} ${conError === 1 ? 'requiere' : 'requieren'} atención`
    : `${legibles} ${legibles === 1 ? 'legible' : 'legibles'}`;
  $('resumenFunciones').textContent = resumen.total_funciones_publicas ?? 0;
  $('resumenEndpoints').textContent = resumen.total_endpoints ?? 0;
}

function cargarDatosVistaPrevia(res) {
  if (!res || !res.ok) return;
  reiniciarVistaExplorar();
  PROYECTO_RESUMEN = res.resumen;
  PROYECTO_ERRORES = res.errores || [];

  const modulosAST = (res.modulos || []).map(m => {
    const fns = (m.funciones || []).map(f => ({
      n: f.nombre,
      sig: f.firma || '()',
      typed: f.tipada ? 1 : 0,
      doc: f.docstring ? 1 : 0,
      br: f.ramas || 0,
      crit: f.critica_propuesta ?? ((f.ramas || 0) > 0),
      inc: true,
      linea: f.linea
    }));
    const endpoints = (m.endpoints || []).map(e => {
      const decisiones = normalizarDecisiones(e.ramas);
      const resuelto = e.resuelta !== false;
      return ({
      objetivo: resuelto ? (e.objetivo || '') : '',
      metodo: e.metodo || null,
      ruta: resuelto ? (e.ruta || null) : null,
      manejador: e.manejador || '',
      response_model: e.response_model || null,
      status_code: e.status_code ?? 200,
      status_code_declarado: !!e.status_code_declarado,
      excepciones_http: (e.excepciones_http || []).map(x => ({ ...x })),
      dependencias: (e.dependencias || []).map(d => d.funcion).filter(Boolean),
      // issue 114: solo se sabe si tiene docstring cuando el análisis trae el dato.
      doc: 'docstring' in e ? (e.docstring ? 1 : 0) : null,
      br: decisiones,
      crit: e.critica_propuesta ?? ((decisiones ?? 0) > 0),
      inc: resuelto,
      resuelta: resuelto
      });
    });
    const tieneObjetivos = fns.length > 0 || endpoints.length > 0;
    return {
      path: m.ruta,
      sel: tieneObjetivos,
      fns: fns,
      endpoints: endpoints,
      conRamas: m.funciones_con_ramas ?? fns.filter(f => f.br > 0).length,
      huella: m.huella
    };
  });

  const modulosErr = (res.errores || []).map(e => ({
    path: e.ruta,
    sel: false,
    error: e,
    fns: [],
    conRamas: 0
  }));

  MODULES = [...modulosAST, ...modulosErr];
  actualizarResumenUI(res.resumen, res.errores);
}

// La selección vive dentro de .qagent/ y se identifica por la ruta del proyecto. Los
// objetivos nuevos quedan seleccionados por defecto; los eliminados simplemente no se aplican.
function instantaneaSeleccionObjetivos(){
  return {version:1, modulos:MODULES.filter(m=>!m.error).map(m=>({
    ruta:m.path, incluido:!!m.sel,
    funciones:(m.fns || []).map(f=>({nombre:f.n, incluido:!!f.inc, critico:!!f.crit})),
    endpoints:(m.endpoints || []).map(e=>({objetivo:e.objetivo, incluido:!!e.inc, critico:!!e.crit}))
  }))};
}
let temporizadorGuardarSeleccion = null;
function guardarSeleccionExplorar(){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.guardar_seleccion_objetivos || !projectPath) return;
  clearTimeout(temporizadorGuardarSeleccion);
  temporizadorGuardarSeleccion = setTimeout(() => {
    api.guardar_seleccion_objetivos(projectPath, instantaneaSeleccionObjetivos()).catch(err => console.warn('No se pudo guardar la selección:', err));
  }, 120);
}
async function restaurarSeleccionExplorar(){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.obtener_seleccion_objetivos || !projectPath) return;
  try {
    const respuesta = await api.obtener_seleccion_objetivos(projectPath);
    const seleccion = respuesta && respuesta.seleccion;
    if(!seleccion || !Array.isArray(seleccion.modulos)) return;
    const porRuta = new Map(seleccion.modulos.map(m => [m.ruta, m]));
    MODULES.filter(m=>!m.error).forEach(m => {
      const guardado = porRuta.get(m.path);
      if(!guardado) return;
      m.sel = !!guardado.incluido;
      const funciones = new Map((guardado.funciones || []).map(f => [f.nombre, f]));
      (m.fns || []).forEach(f => { const previo=funciones.get(f.n); if(previo){ f.inc=!!previo.incluido; f.crit=!!previo.critico; } });
      const endpoints = new Map((guardado.endpoints || []).map(e => [e.objetivo, e]));
      (m.endpoints || []).forEach(e => { const previo=endpoints.get(e.objetivo); if(previo){ e.inc=!!previo.incluido; e.crit=!!previo.critico; } });
    });
  } catch(err) {
    console.warn('No se pudo recuperar la selección:', err);
  }
}

/* ---------------- Vista previa ---------------- */
async function loadProject(name, src, where, br='main', ruta='', opciones = {}){
  if(!apiRec()) demoRegistrar(name, src, where);
  document.querySelectorAll('.repoName').forEach(e=>e.textContent=name);
  document.querySelectorAll('.repoLbl').forEach(e=>e.textContent = src==='git' ? where.replace('https://','').replace(/\.git$/,'') : where);
  document.querySelectorAll('.brLbl').forEach(e=>e.textContent=br); $('branchLbl').textContent = br;
  $('projRama').classList.toggle('hide', !br || br === '—');   // sin repositorio Git no hay rama que mostrar
  monitorStarted = false;
  verificarEntorno();  // Docker, Git, config.toml y .env al abrir un proyecto (EN-06)
  projectPath = ruta ? ruta : (src==='git' ? 'E:\\Proyectos\\' + name : where);

  if (window.pywebview && window.pywebview.api && (window.pywebview.api.obtener_vista_previa || window.pywebview.api.analizar_proyecto)) {
    // Aplicación real: solo se muestran datos del análisis; si falla, se avisa (nunca se inventan módulos).
    try {
      const fn = window.pywebview.api.obtener_vista_previa || window.pywebview.api.analizar_proyecto;
      const res = await fn(projectPath);
      if (res && res.ok && res.resumen && res.resumen.total_modulos > 0) {
        cargarDatosVistaPrevia(res);
      } else {
        vaciarVistaPrevia();
        const msgIncompatible = 'No es posible cargar/abrir el proyecto por incompatibilidad de lenguaje: QAgent solo admite proyectos en Python 3.10+.';
        toastError(escHtml((res && res.error) || msgIncompatible));
        go('welcome');
        return;
      }
    } catch (err) {
      console.error("Error al obtener la vista previa por AST:", err);
      vaciarVistaPrevia();
      toastError('No se pudo analizar el proyecto. Inténtalo de nuevo.');
      go('welcome');
      return;
    }
  } else {
    aplicarResumenDemo();   // modo demostración (navegador, sin Python)
  }
  await restaurarSeleccionExplorar();
  const esReciente = !!(opciones && opciones.esReciente);
  const corridaPrevia = await hayCorridaPrevia(projectPath || ruta);
  PRUEBAS_REPETIBLES = await pruebasRepetibles(ruta);
  let yaCargoPrueba = !!((opciones && opciones.yaCargoPrueba) || (esReciente && corridaPrevia));
  // issue 139: «Volver a correr las guardadas» necesita pruebas guardadas, no basta con que
  // haya corridas (una corrida interrumpida o sin aprobadas no deja nada que repetir).
  HAS_PRIOR_RUN = corridaPrevia;

  renderTree();   // termina en calc(), que también dibuja la configuración de pruebas

  // issue 139: en la app, solo se salta a Resultados si de verdad hay resultados que mostrar.
  const enApp = !!(window.pywebview && window.pywebview.api);
  if (esReciente && yaCargoPrueba && enApp) {
    ejecucionReal = null;
    try {
      if (typeof cargarEjecucionReal === 'function') await cargarEjecucionReal(null, false, {silencioso: true});
    } catch (err) {
      console.warn("No se pudo pre-cargar ejecución:", err);
    }
    yaCargoPrueba = !!ejecucionReal;
  }

  if (esReciente && yaCargoPrueba) {
    if (typeof desbloquearTodasLasVistas === 'function') {
      desbloquearTodasLasVistas();
    } else {
      document.querySelectorAll('#views a').forEach(a => a.classList.remove('hide', 'off'));
    }
    monitorStarted = true;
    runDone = true;
    // En la app, Resultados ya se cargó arriba (lista y, por su cuenta, la evidencia).
    go('exec');
  } else {
    ejecucionReal = null;
    reporteReal = null;
    if (typeof reiniciarVistasProyecto === 'function') reiniciarVistasProyecto();
    else document.querySelectorAll('#views a[data-v=exec],#views a[data-v=monitor]').forEach(a=>a.classList.add('hide','off'));
    go('preview');
  }
}

// Sin análisis (fallo en la app real): lista vacía y contadores en cero, sin datos de ejemplo.
function vaciarVistaPrevia() {
  MODULES = [];
  reiniciarVistaExplorar();
  PROYECTO_RESUMEN = null;
  PROYECTO_ERRORES = [];
  actualizarResumenUI({ total_modulos: 0, total_funciones_publicas: 0, total_errores: 0 });
}

// Regresión requiere al menos una prueba aprobada persistida, no solo una corrida.
// #70: funciones con prueba guardada que hoy se puede repetir, como "modulo::objetivo".
// Sin pywebview (demostración) devuelve null y la configuración cuenta todas las marcadas.
async function pruebasRepetibles(ruta) {
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.pruebas_repetibles)) return null;
  try {
    const lista = await window.pywebview.api.pruebas_repetibles(ruta);
    return new Set((lista || []).map(o => o.modulo + '::' + o.objetivo));
  } catch (err) {
    console.error("Error al consultar las pruebas guardadas:", err);
    return new Set();
  }
}

async function hayCorridaPrevia(ruta) {
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.tiene_pruebas_aprobadas)) return true;
  try {
    return !!(await window.pywebview.api.tiene_pruebas_aprobadas(ruta));
  } catch (err) {
    console.error("Error al consultar las corridas previas:", err);
    return false;
  }
}

/* Estado del entorno (EN-06): config.toml, .env, Docker y Git.
   Sin pywebview (HTML abierto en el navegador) es una demostración y no se bloquea nada. */
let entornoListo = !(window.pywebview), entornoMotivo = 'Verificando el entorno…';
// Último resultado de verificar_entorno (EN-06): lo usan las «Comprobaciones previas» de Preparar.
let ENTORNO_VERIFICADO = null;
const ENV_NOMBRES = {config:'Configuración (config.toml)', claves:'Claves de IA (.env)', docker:'Docker y sandbox', git:'Git'};
// La tarjeta de entorno salió de Explorar (pasa a «Comprobaciones previas» de Preparar): si sus
// elementos no están en la página, solo se actualiza el estado que bloquea el inicio de la corrida.
async function verificarEntorno() {
  if (!$('envIcono')) return verificarEntornoSinPanel();
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.verificar_entorno)) {
    $('envIcono').textContent = '·'; $('envIcono').className = '';
    $('envTitulo').textContent = 'Modo demostración';
    $('envSub').textContent = 'El entorno (configuración, claves de IA, Docker y Git) solo se verifica en la aplicación de escritorio.';
    $('envReintentar').classList.add('hide'); $('envDet').classList.add('hide');
    return;
  }
  $('envReintentar').classList.remove('hide'); $('envDet').classList.remove('hide');
  let r;
  try {
    r = await window.pywebview.api.verificar_entorno();
  } catch (err) {
    console.error("Error al verificar el entorno:", err);
    r = {listo: false, mensaje: 'No se pudo verificar el entorno. Reinicia la aplicación.', problemas: [], comprobaciones: []};
  }
  entornoListo = !!r.listo;
  entornoMotivo = r.listo ? '' : 'Entorno no listo: ' + r.mensaje;
  $('envIcono').textContent = r.listo ? '✓' : '✕';
  $('envIcono').className = r.listo ? 'ok' : 'no';
  $('envTitulo').textContent = (r.listo ? 'Entorno listo' : 'Entorno no listo') + (r.simulado ? ' · IA simulada' : '');
  const dockerOpcional = (r.comprobaciones || []).some(c => c.id === 'docker' && c.opcional);
  $('envSub').textContent = r.listo
    ? (r.simulado ? 'IA simulada activa: 0 tokens (US$ 0). ' + (dockerOpcional ? 'Docker no hace falta; configuración y Git verificados.' : 'Configuración, Docker y Git verificados.')
                  : 'Configuración, claves de IA, Docker y Git verificados.')
    : (r.problemas.length ? 'Hay ' + r.problemas.length + ' problema(s). Corrígelos y pulsa Reintentar.' : r.mensaje);
  const nombres = r.simulado ? {...ENV_NOMBRES, claves:'IA simulada (EN-11)'} : ENV_NOMBRES;
  $('envChecks').innerHTML = (r.comprobaciones || []).map(c =>
    `<div class="c"><span class="i ${c.ok ? 'ok' : 'no'}">${c.ok ? '✓' : '✕'}</span><div><b>${escHtml(nombres[c.id] || c.id)}</b><div class="hint" style="margin:2px 0 0">${escHtml(c.mensaje)}</div></div></div>`).join('');
  $('envDet').open = !r.listo;  // si falla, el detalle se muestra abierto
  actualizarSandbox();  // el indicador de la barra lateral se pone al día con el mismo resultado
  try { calc(); } catch (err) { $('toPlan').disabled = !entornoListo; }
}
async function verificarEntornoSinPanel() {
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.verificar_entorno)) return;
  let r;
  try {
    r = await window.pywebview.api.verificar_entorno();
  } catch (err) {
    console.error("Error al verificar el entorno:", err);
    r = {listo: false, mensaje: 'No se pudo verificar el entorno. Reinicia la aplicación.'};
  }
  ENTORNO_VERIFICADO = r;
  entornoListo = !!r.listo;
  entornoMotivo = r.listo ? '' : 'Entorno no listo: ' + r.mensaje;
  actualizarSandbox();
  try { calc(); } catch (err) { $('toPlan').disabled = !entornoListo; }
}

// Tooltips accesibles de las cabeceras (issue #65): flotan sobre la tabla, sin recortarse ni
// agrandarla. Se muestran con el mouse (mouseenter) y con el teclado (focus).
function mostrarTooltip(el){
  const tip = $('tipFlotante');
  const texto = el && el.getAttribute('data-tip');
  if(!tip || !texto) return;
  tip.textContent = texto;
  tip.hidden = false;
  const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
  let left = r.left + r.width / 2 - t.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - t.width - 8));
  let top = r.bottom + 8;
  if(top + t.height > window.innerHeight - 8) top = r.top - t.height - 8;
  tip.style.left = left + 'px';
  tip.style.top = Math.max(8, top) + 'px';
}
function ocultarTooltip(){ const tip = $('tipFlotante'); if(tip) tip.hidden = true; }
function iniciarTooltips(){
  document.querySelectorAll('#s-preview .info').forEach(el => {
    el.addEventListener('mouseenter', () => mostrarTooltip(el));
    el.addEventListener('mouseleave', ocultarTooltip);
    el.addEventListener('focus', () => mostrarTooltip(el));
    el.addEventListener('blur', ocultarTooltip);
  });
  // issue 114: la etiqueta «Sin docstring» aparece en filas que se vuelven a pintar y en otras
  // pantallas (En curso, Resultados). El tooltip pasa al body y se delega en el documento.
  const tip = $('tipFlotante');
  if(tip) document.body.appendChild(tip);
  const etiqueta = ev => ev.target && ev.target.closest ? ev.target.closest('.etq-sin-doc') : null;
  document.addEventListener('mouseover', ev => { const el = etiqueta(ev); if(el) mostrarTooltip(el); });
  document.addEventListener('mouseout', ev => { if(etiqueta(ev)) ocultarTooltip(); });
  document.addEventListener('focusin', ev => { const el = etiqueta(ev); if(el) mostrarTooltip(el); });
  document.addEventListener('focusout', ev => { if(etiqueta(ev)) ocultarTooltip(); });
  document.addEventListener('keydown', ev => { if(ev.key === 'Escape') ocultarTooltip(); });
}

// Se llama desde main.js cuando el HTML del componente ya está montado.
function iniciarVistaPrevia(){
  iniciarTooltips();
  if (window.pywebview && window.pywebview.api) verificarEntorno();
  else window.addEventListener('pywebviewready', verificarEntorno, {once:true});
}
/* ---------------- Carpetas incluidas ----------------
   Árbol de carpetas sacado de las rutas de los archivos legibles (no se inventan carpetas).
   Marcar una carpeta incluye todos sus archivos; si solo algunos están incluidos, la casilla
   queda indeterminada. Los archivos que no se pudieron leer van al aviso inferior. */
const ICO_CARPETA_ARBOL = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 7h6l2 2h10v10H3z"/></svg>';
function carpetasDelProyecto(){
  const dirs = new Set();
  MODULES.forEach(m => {
    if(m.error) return;
    const partes = m.path.split('/');
    for(let i = 1; i < partes.length; i++) dirs.add(partes.slice(0, i).join('/') + '/');
  });
  return [...dirs].sort();
}
const modulosDeCarpeta = dir => MODULES.filter(m => moduloTieneObjetivos(m) && m.path.startsWith(dir));
function renderTree(){
  const proyecto = (document.querySelector('.ini-migas .repoName') || {}).textContent || 'Proyecto';
  let h = `<label class="row raiz"><input type="checkbox" class="exp-caja" id="selectAllModules" onchange="seleccionarTodosModulos(this.checked)">${ICO_CARPETA_ARBOL}<span class="mono">${escHtml(proyecto)}</span></label>`;
  carpetasDelProyecto().forEach(dir => {
    const partes = dir.split('/').filter(Boolean);
    const habilitada = modulosDeCarpeta(dir).length > 0;
    h += `<label class="row ${habilitada ? '' : 'no-targets'}" style="--nivel:${partes.length}" ${habilitada ? '' : 'title="sin objetivos analizables"'}><input type="checkbox" class="exp-caja exp-carpeta" data-dir="${escHtml(dir)}" ${habilitada ? '' : 'disabled'} onchange="seleccionarCarpeta(this.dataset.dir, this.checked)">${ICO_CARPETA_ARBOL}<span class="mono">${escHtml(partes[partes.length - 1])}</span></label>`;
  });
  // Siempre fuera de la selección: las pruebas existentes y la carpeta de QAgent.
  ['tests', '.qagent'].forEach(n => {
    h += `<div class="row ign" style="--nivel:1"><input type="checkbox" class="exp-caja" disabled aria-label="${n} no se incluye">${ICO_CARPETA_ARBOL}<span class="mono">${n}</span></div>`;
  });
  $('tree').innerHTML = h;
  sincronizarCarpetas();
  renderErroresLectura();
  actualizarSeleccionTodos();
  renderFns();
}
// La propiedad `indeterminate` no se puede fijar por atributo HTML: se aplica al DOM.
function sincronizarCarpetas(){
  document.querySelectorAll('#tree .exp-carpeta').forEach(chk => {
    const mods = modulosDeCarpeta(chk.dataset.dir);
    const sel = mods.filter(m => m.sel).length;
    chk.checked = mods.length > 0 && sel === mods.length;
    chk.indeterminate = sel > 0 && sel < mods.length;
  });
}
function seleccionarCarpeta(dir, seleccionado){
  modulosDeCarpeta(dir).forEach(m => { m.sel = !!seleccionado; });
  renderTree();
  guardarSeleccionExplorar();
}

// Aviso de archivos que no se pudieron leer, con el motivo de cada uno.
function renderErroresLectura(){
  const conError = MODULES.filter(m => m.error);
  $('expErrores').classList.toggle('hide', !conError.length);
  if(!conError.length) return;
  $('expErroresTitulo').textContent = conError.length === 1 ? '1 archivo no se pudo leer' : `${conError.length} archivos no se pudieron leer`;
  $('expErroresLista').innerHTML = conError.map(m =>
    `<span><span class="mono">${escHtml(m.path)}</span> no se pudo analizar: Error de sintaxis${m.error.linea ? ' en la línea ' + m.error.linea : ''} (${escHtml(m.error.mensaje || m.error.tipo || 'SyntaxError')}). Corrígelo o exclúyelo; el resto del proyecto se puede probar igual.</span>`
  ).join('');
}

/* ---------------- Búsqueda y columnas ---------------- */
// Filtra funciones y endpoints por nombre, ruta o archivo. No cambia la selección.
function buscarObjetivos(texto){
  BUSQUEDA = String(texto || '').trim().toLowerCase();
  renderFns();
}
const coincide = (...campos) => !BUSQUEDA || campos.some(c => String(c || '').toLowerCase().includes(BUSQUEDA));

// Complejidad: según las decisiones (if, bucles, excepciones) que encontró el análisis.
function textoComplejidad(br){
  const n = normalizarDecisiones(br);
  if(n === null) return '<span class="exp-sub">—</span>';
  const tip = n === 1 ? '1 decisión (if, bucle o excepción)' : `${n} decisiones (if, bucles o excepciones)`;
  // Como la maqueta, dos valores: hasta 2 decisiones es «Simple»; desde 3, «Muchas ramas».
  if(n < 3) return `<span title="${tip}">Simple</span>`;
  return `<span class="exp-aviso" title="${tip}">Muchas ramas</span>`;
}
// Desde la última vez: sale del estado del plan de pruebas guardado de cada archivo.
// Si no hay datos (el backend aún no lo informa), se muestra un guion: nunca se supone.
function textoDesdeUltimaVez(m){
  const sp = SPEC_STATUS[m.path];
  if(sp === 'reuse') return '<span class="exp-exito">Sin cambios desde la última vez</span><span class="exp-sub">Se reutiliza</span>';
  if(sp === 'stale') return '<span class="exp-cambio">Cambió</span>';
  return '<span class="exp-sub" title="No hay datos de una corrida anterior para este archivo">—</span>';
}

// Las decisiones son un conteo AST: solo un entero no negativo es válido. La ausencia
// legítima se conserva como null y se representa con un guion; nunca se inventa un cero.
function normalizarDecisiones(valor){
  return typeof valor === 'number' && Number.isFinite(valor) && Number.isInteger(valor) && valor >= 0
    ? valor
    : null;
}
function textoDecisiones(valor){
  const n = normalizarDecisiones(valor);
  return n === null ? '—' : String(n);
}


// Un endpoint solo es analizable si su ruta se pudo resolver: sin objetivo ("GET /ruta")
// no hay nada que probar. Nunca se inventa una ruta.
function endpointElegible(e){ return !!e.objetivo; }
function endpointsElegibles(m){ return (m.endpoints || []).filter(endpointElegible); }
function endpointsIncluidos(m){ return endpointsElegibles(m).filter(e => e.inc); }

// Totales detectados (no seleccionados): el selector muestra lo que se encontró, no lo elegido.
function totalFuncionesDetectadas(){
  return MODULES.filter(m => !m.error).flatMap(m => m.fns || []).length;
}
function totalEndpointsDetectados(){
  return MODULES.filter(m => !m.error).flatMap(m => m.endpoints || []).length;
}

// Selector Funciones/Endpoints: cuenta los detectados, deshabilita la opción sin objetivos y
// conserva la vista elegida al cambiar de pestaña.
function cambiarVistaObjetivos(cual){
  if(cual === 'funciones' && totalFuncionesDetectadas() === 0) return;
  if(cual === 'endpoints' && totalEndpointsDetectados() === 0) return;
  VISTA_OBJETIVOS = cual;
  aplicarVistaObjetivos();
  renderFns();   // «Seleccionar todo» y «Mostrando» dependen de la vista activa
}
function aplicarVistaObjetivos(){
  const esFns = VISTA_OBJETIVOS === 'funciones';
  $('vistaFns').classList.toggle('hide', !esFns);
  $('vistaEps').classList.toggle('hide', esFns);
  $('tabFns').classList.toggle('on', esFns); $('tabFns').setAttribute('aria-selected', String(esFns));
  $('tabEps').classList.toggle('on', !esFns); $('tabEps').setAttribute('aria-selected', String(!esFns));
}
function actualizarSelectorObjetivos(){
  const nFns = totalFuncionesDetectadas(), nEps = totalEndpointsDetectados();
  // Si la vista activa se quedó sin objetivos, se muestra la otra (solo si tiene).
  if(VISTA_OBJETIVOS === 'funciones' && nFns === 0 && nEps > 0) VISTA_OBJETIVOS = 'endpoints';
  else if(VISTA_OBJETIVOS === 'endpoints' && nEps === 0 && nFns > 0) VISTA_OBJETIVOS = 'funciones';
  $('tabFnsN').textContent = nFns;
  $('tabEpsN').textContent = nEps;
  $('tabFns').disabled = nFns === 0;
  $('tabFns').title = nFns === 0 ? 'No se detectaron funciones en el proyecto' : '';
  $('tabFns').setAttribute('aria-disabled', String(nFns === 0));
  $('tabEps').disabled = nEps === 0;
  $('tabEps').title = nEps === 0 ? 'No se detectaron endpoints en el proyecto' : '';
  $('tabEps').setAttribute('aria-disabled', String(nEps === 0));
  aplicarVistaObjetivos();
}

/* ---------------- Tabla de funciones y endpoints ----------------
   Lista plana, como la demo: una fila por función o endpoint de las carpetas incluidas, con
   su archivo debajo del nombre. La columna Profundizar solo se ve si se activa esa opción. */
let MOSTRAR_PROFUNDIZAR = false;
function mostrarProfundizar(si){
  MOSTRAR_PROFUNDIZAR = !!si;
  $('s-preview').classList.toggle('con-profundizar', MOSTRAR_PROFUNDIZAR);
}
const filasFunciones = () => MODULES.flatMap((m, mi) =>
  m.sel && moduloTieneObjetivos(m) ? (m.fns || []).map((f, fi) => ({m, mi, f, fi})) : []);
const filasEndpoints = () => MODULES.flatMap((m, mi) =>
  m.sel && moduloTieneObjetivos(m) ? (m.endpoints || []).map((e, ei) => ({m, mi, e, ei})) : []);
const funcionVisible = r => coincide(r.f.n, r.m.path);
const endpointVisible = r => coincide(r.e.objetivo, r.e.ruta, r.e.manejador, r.m.path);

function renderEndpoints(){
  const filas = filasEndpoints().filter(endpointVisible);
  $('endpointTable').innerHTML = filas.map(({m, mi, e, ei}) => {
    const elegible = endpointElegible(e);
    const nombreEp = escHtml(e.objetivo || e.manejador || '');
    // Detalle del contrato del endpoint, como descripción emergente del nombre.
    const estado = (e.status_code === null || e.status_code === undefined) ? '—' : e.status_code;
    const respuesta = e.response_model ? escHtml(e.response_model) : '—';
    const errores = e.excepciones_http || [];
    const codigos = errores.map(x => x.status_code).filter(c => c !== undefined && c !== null);
    const tipErr = errores.length ? `Errores HTTP: ${codigos.join(', ') || errores.length}` : 'Sin errores HTTP identificados';
    const simula = (e.dependencias && e.dependencias.length) ? 'Simula: ' + e.dependencias.join(', ') : 'Sin Depends';
    const detalle = `Función ${e.manejador ? escHtml(e.manejador) : '—'} · Estado ${estado}${e.status_code_declarado ? '' : ' (por defecto)'} · Respuesta ${respuesta} · ${tipErr} · ${escHtml(simula)}`;
    return `<tr class="${elegible ? '' : 'ep-no-resuelta'}">
      <td class="col-incl"><input type="checkbox" class="exp-caja" aria-label="Incluir endpoint: ${nombreEp}" ${e.inc && elegible ? 'checked' : ''} ${elegible ? '' : 'disabled'} title="${elegible ? '' : 'Ruta no disponible: no se puede probar'}" onchange="toggleEndpoint(${mi},${ei})"></td>
      <td class="fn" title="${detalle}"><span class="endpoint-method">${e.metodo ? escHtml(e.metodo) : 'SIN MÉTODO'}</span> <span class="endpoint-route">${e.ruta ? escHtml(e.ruta) : 'Ruta no disponible'}</span>${tieneDocstring(e) === false ? etiquetaSinDocstring('endpoint') : ''}${elegible ? '' : '<span class="etq-sin-doc etq-no-resuelta" data-tip="Ruta sin resolver: no se podrá probar (su prefijo final no se conoce sin ejecutar la app)" role="note" aria-label="Ruta sin resolver. No se podrá probar">Ruta sin resolver</span>'}<div class="sub">${escHtml(m.path)}</div></td>
      <td>${textoComplejidad(e.br)}</td>
      <td>${textoDesdeUltimaVez(m)}</td>
      <td class="col-prof"><input type="checkbox" class="exp-caja" aria-label="Profundizar: ${nombreEp}" ${e.crit && elegible ? 'checked' : ''} ${elegible ? '' : 'disabled'} title="${elegible ? 'Profundizar: solicita un análisis más exhaustivo del endpoint. Se aplica si activas Profundizar en la configuración de pruebas.' : 'Ruta no disponible: no se puede probar'}" onchange="toggleEndpointCrit(${mi},${ei})"></td>
    </tr>`;
  }).join('') || `<tr><td colspan="5" class="exp-vacio">${BUSQUEDA ? 'Ningún endpoint coincide con la búsqueda.' : 'No se detectaron endpoints en el proyecto.'}</td></tr>`;
}

function renderFns(){
  const fns = filasFunciones(), eps = filasEndpoints();
  const fnsVis = fns.filter(funcionVisible);
  $('fnTable').innerHTML = fnsVis.map(({m, mi, f, fi}) => `<tr>
      <td class="col-incl"><input type="checkbox" class="exp-caja" aria-label="Incluir función: ${escHtml(f.n)}" ${f.inc ? 'checked' : ''} onchange="toggle(${mi},${fi},'inc')"></td>
      <td class="fn" title="${escHtml(f.n + f.sig)}">${escHtml(f.n)}${tieneDocstring(f) === false ? etiquetaSinDocstring('funcion') : ''}<div class="sub">${escHtml(m.path)}</div></td>
      <td>${textoComplejidad(f.br)}</td>
      <td>${textoDesdeUltimaVez(m)}</td>
      <td class="col-prof"><input type="checkbox" class="exp-caja" aria-label="Profundizar: ${escHtml(f.n)}" ${f.crit ? 'checked' : ''} title="Profundizar: solicita un análisis más exhaustivo de la función. Se aplica si activas Profundizar en la configuración de pruebas." onchange="toggle(${mi},${fi},'crit')"></td>
    </tr>`).join('') || `<tr><td colspan="5" class="exp-vacio">${BUSQUEDA ? 'Ninguna función coincide con la búsqueda.' : 'No hay funciones en las carpetas incluidas.'}</td></tr>`;
  renderEndpoints();
  actualizarSelectorObjetivos();

  // Cifras de la selección (cabecera y contador de la tabla).
  const fnsSel = fns.filter(r => r.f.inc).length;
  const epsSel = eps.filter(r => endpointElegible(r.e) && r.e.inc).length;
  const total = fnsSel + epsSel;
  $('fnCount').textContent = `${total} ${total === 1 ? 'seleccionada' : 'seleccionadas'}`;
  $('resumenFuncionesSub').textContent = `${fnsSel} ${fnsSel === 1 ? 'seleccionada' : 'seleccionadas'}`;
  $('resumenEndpointsSub').textContent = `${epsSel} ${epsSel === 1 ? 'seleccionado' : 'seleccionados'}`;

  // El selector tiene alcance explícito por tipo y nunca cambia el otro tipo de objetivo.
  const esFns = VISTA_OBJETIVOS === 'funciones';
  const vistaTodas = esFns ? fns : eps;
  const vistaVisibles = esFns ? fnsVis : eps.filter(endpointVisible);
  const marcables = esFns ? vistaTodas.map(r => r.f) : vistaTodas.map(r => r.e).filter(endpointElegible);
  const marcadas = marcables.filter(o => o.inc).length;
  $('expTodoTxt').textContent = esFns ? 'Seleccionar todas las funciones' : 'Seleccionar todos los endpoints';
  $('expTodoN').textContent = marcables.length;
  $('expTodo').disabled = marcables.length === 0;
  $('expTodo').checked = marcables.length > 0 && marcadas === marcables.length;
  $('expTodo').indeterminate = marcadas > 0 && marcadas < marcables.length;
  $('expMostrando').textContent = `Mostrando ${vistaVisibles.length} de ${vistaTodas.length}`;
  const sinCambios = vistaVisibles.filter(r => SPEC_STATUS[r.m.path] === 'reuse').length;
  const cambiaron = vistaVisibles.filter(r => SPEC_STATUS[r.m.path] === 'stale').length;
  $('expCambios').textContent = (sinCambios || cambiaron) ? ` · ${sinCambios} sin cambios, ${cambiaron} cambiaron` : '';
  calc();
}

// El alcance es el tipo activo completo. La búsqueda solo filtra la tabla, no cambia la selección.
function seleccionarTodosObjetivos(seleccionado){
  if(VISTA_OBJETIVOS === 'funciones') filasFunciones().forEach(r => { r.f.inc = !!seleccionado; });
  else filasEndpoints().filter(r => endpointElegible(r.e)).forEach(r => { r.e.inc = !!seleccionado; });
  renderFns();
  guardarSeleccionExplorar();
}

// Incluir una función o un endpoint no cambia las carpetas incluidas; Profundizar no altera Incluir.
function toggle(mi,fi,k){
  const m = MODULES[mi];
  m.fns[fi][k] = !m.fns[fi][k];
  renderFns();
  guardarSeleccionExplorar();
}
function toggleEndpoint(indice, ei){
  const m = MODULES[indice];
  if(!m || m.error) return;
  const e = (m.endpoints || [])[ei];
  if(!e || !endpointElegible(e)) return;
  e.inc = !e.inc;
  renderFns();
  guardarSeleccionExplorar();
}
// Profundizar de un endpoint (#74): como en funciones, no altera Incluir.
function toggleEndpointCrit(indice, ei){
  const m = MODULES[indice];
  const e = m && !m.error ? (m.endpoints || [])[ei] : null;
  if(!e || !endpointElegible(e)) return;
  e.crit = !e.crit;
  renderFns();
  guardarSeleccionExplorar();
}

function moduloTieneObjetivos(m){
  return !m.error && ((m.fns || []).length > 0 || (m.endpoints || []).length > 0);
}
function seleccionarTodosModulos(seleccionado){
  MODULES.forEach(m => { m.sel = moduloTieneObjetivos(m) && seleccionado; });
  renderTree();
  guardarSeleccionExplorar();
}
function actualizarSeleccionTodos(){
  const control = $('selectAllModules');
  if (!control) return;
  const habilitados = MODULES.filter(moduloTieneObjetivos);
  const seleccionados = habilitados.filter(m => m.sel).length;
  control.disabled = habilitados.length === 0;
  control.checked = habilitados.length > 0 && seleccionados === habilitados.length;
  control.indeterminate = seleccionados > 0 && seleccionados < habilitados.length;
}
// `criticas` (HU-06, #74): funciones y endpoints incluidos y marcados en Profundizar; llegan al
// contrato como critical.
// Los tipos de prueba de Preparar (Unitarias / Endpoints API) dejan fuera un grupo entero.
function obtenerSeleccionObjetivos(){
  const conFns = eleccionPruebas.unitarias !== false, conEps = eleccionPruebas.endpoints !== false;
  return MODULES.filter(m => m.sel && moduloTieneObjetivos(m)).map(m => ({
    ruta: m.path,
    funciones: conFns ? (m.fns || []).filter(f => f.inc).map(f => f.n) : [],
    endpoints: conEps ? (m.endpoints || []).filter(e => endpointElegible(e) && e.inc).map(e => e.objetivo) : [],
    criticas: (conFns ? (m.fns || []).filter(f => f.inc && f.crit).map(f => f.n) : [])
      .concat(conEps ? (m.endpoints || []).filter(e => endpointElegible(e) && e.inc && e.crit).map(e => e.objetivo) : [])
  })).filter(m => m.funciones.length || m.endpoints.length);
}

// Pie de la vista previa (alcance): lo invoca calc() porque depende de la selección actual.
function renderPieVistaPrevia(fns, noDoc, endpoints=[]){
  let m1 = '', b1 = false;
  const total = fns.length + endpoints.length;
  const seleccion = `Selección: ${fns.length} ${fns.length === 1 ? 'función' : 'funciones'} + ${endpoints.length} ${endpoints.length === 1 ? 'endpoint' : 'endpoints'}`;
  if(!total){ m1 = ' · Selecciona al menos una función o un endpoint para continuar.'; b1 = true; }
  else m1 = ` · ${seleccion}`;
  $('footMsg').innerHTML = m1; $('toTests').disabled = b1;
  $('toTestsTxt').textContent = total ? `Preparar ${total} ${total === 1 ? 'seleccionada' : 'seleccionadas'}` : 'Preparar selección';
}

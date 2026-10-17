// vista-previa.js — pantalla de vista previa del proyecto: resumen del análisis, árbol de módulos y tabla de funciones
// HTML del componente (se monta en el marcador data-componente="vista-previa/vista-previa" de index.html)
registrarComponente('vista-previa/vista-previa', `<!-- ===== 2. VISTA PREVIA Y CONFIGURACIÓN ===== -->
<section id="s-preview" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <div class="topbar">
    <div class="chip"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h6l2 2h10v10H3z"/></svg><b>repo:</b> <span class="repoLbl"></span></div>
    <div class="stepper">
      <span class="done"><b>✓</b>Proyecto</span><span class="chev">›</span>
      <span class="on"><b>2</b>Vista previa</span><span class="chev">›</span>
      <span><b>3</b>Configuración de pruebas</span><span class="chev">›</span>
      <span><b>4</b>Ejecución</span>
    </div>
  </div>
  <div class="scroll"><div class="page">

    <!-- Datos del proyecto -->
    <div class="card"><div class="projhead">
      <span class="t repoName"></span>
      <span class="pill p-purple hide" id="projRama">Git · rama <span class="brLbl"></span></span>
      <span class="pill p-grey" id="projFnsResumen"></span>
    </div></div>

    <!-- Resumen del proyecto (análisis estático AST — HU-04 / EN-02) -->
    <div class="card" id="cardResumen">
      <h4>Resumen del proyecto <span class="pill p-blue">Análisis AST (EN-02)</span></h4>
      <div class="bd" style="display:flex;gap:24px;flex-wrap:wrap;align-items:center" id="resumenContenido">
        <div><div class="hint" style="margin:0;text-transform:uppercase;font-size:10px;color:var(--dim)">Módulos encontrados</div><b class="mono" style="font-size:18px" id="resumenModulos">0</b></div>
        <div><div class="hint" style="margin:0;text-transform:uppercase;font-size:10px;color:var(--dim)">Funciones públicas</div><b class="mono" style="font-size:18px" id="resumenFunciones">0</b></div>
        <div><div class="hint" style="margin:0;text-transform:uppercase;font-size:10px;color:var(--dim)">Endpoints FastAPI</div><b class="mono" style="font-size:18px" id="resumenEndpoints">0</b></div>
        <div><div class="hint" style="margin:0;text-transform:uppercase;font-size:10px;color:var(--dim)">Errores (no analizables)</div><b class="mono" style="font-size:18px" id="resumenErrores">0</b></div>
        <div style="margin-left:auto;display:flex;gap:10px;flex-wrap:wrap;align-items:center">
          <span class="pill p-amber" id="resumenSinDoc" title="el valor esperado no tendrá fuente (oráculo débil)"></span>
          <span class="pill p-grey" id="resumenSinTipos"></span>
          <span class="pill p-grey" id="resumenConAlguna"></span>
        </div>
      </div>
    </div>

    <!-- Árbol + funciones -->
    <div class="grid2">
      <div class="card">
        <h4>Árbol del proyecto <span class="pill p-grey" id="modCount"></span><label class="select-all"><input type="checkbox" id="selectAllModules" onchange="seleccionarTodosModulos(this.checked)"> Seleccionar todos</label></h4>
        <div class="bd tree" id="tree"></div>
        <div class="hint" style="padding:0 16px 14px">Solo se analizan los módulos marcados. Menos módulos = menos tokens del Planner.</div>
      </div>
      <div class="card">
        <div class="objs-head">
          <h4>Objetivos detectados <span class="pill p-blue">Análisis AST (EN-02)</span></h4>
          <div class="obj-switch" role="tablist" aria-label="Tipo de objetivo">
            <button type="button" id="tabFns" class="obj-tab on" role="tab" aria-selected="true" aria-controls="vistaFns" onclick="cambiarVistaObjetivos('funciones')">Funciones (<span id="tabFnsN">0</span>) <span class="warn hide" id="tabFnsWarn" title="Hay funciones Mejorables o Inciertas">⚠</span></button>
            <button type="button" id="tabEps" class="obj-tab" role="tab" aria-selected="false" aria-controls="vistaEps" onclick="cambiarVistaObjetivos('endpoints')">Endpoints (<span id="tabEpsN">0</span>) <span class="warn hide" id="tabEpsWarn" title="Hay endpoints Mejorables o Inciertos">⚠</span></button>
          </div>
        </div>
        <div id="vistaFns" class="obj-vista">
          <div class="table-scroll fn-scroll"><table class="fn-table">
            <thead><tr>
              <th>Función <span class="info" tabindex="0" role="button" aria-label="Nombre de la función encontrada en el archivo Python." data-tip="Nombre de la función encontrada en el archivo Python.">ⓘ</span></th>
              <th>Calidad <span class="info" tabindex="0" role="button" aria-label="Indica si QAgent tiene suficiente información para saber qué resultado debería producir la función." data-tip="Indica si QAgent tiene suficiente información para saber qué resultado debería producir la función.">ⓘ</span></th>
              <th>Tipos declarados <span class="info" tabindex="0" role="button" aria-label="Indica si la función declara los tipos de datos que recibe y devuelve." data-tip="Indica si la función declara los tipos de datos que recibe y devuelve.">ⓘ</span></th>
              <th>Docstring <span class="info" tabindex="0" role="button" aria-label="Es la descripción de la función y ayuda a determinar el resultado esperado." data-tip="Es la descripción de la función y ayuda a determinar el resultado esperado.">ⓘ</span></th>
              <th>Condicionales <span class="info" tabindex="0" role="button" aria-label="Muestra cuántas estructuras condicionales se detectaron. Más condicionales pueden requerir más casos de prueba." data-tip="Muestra cuántas estructuras condicionales se detectaron. Más condicionales pueden requerir más casos de prueba.">ⓘ</span></th>
              <th>Profundizar <span class="info" tabindex="0" role="button" aria-label="Solicita un análisis más exhaustivo de la función. Puede requerir más tiempo de ejecución." data-tip="Solicita un análisis más exhaustivo de la función. Puede requerir más tiempo de ejecución.">ⓘ</span></th>
              <th>Incluir <span class="info" tabindex="0" role="button" aria-label="Permite seleccionar si esta función formará parte del análisis." data-tip="Permite seleccionar si esta función formará parte del análisis.">ⓘ</span></th>
            </tr></thead>
            <tbody id="fnTable"></tbody>
          </table></div>
          <div class="hint obj-hint">Funciones agrupadas por archivo. <span id="fnCount"></span></div>
        </div>
        <div id="vistaEps" class="obj-vista hide">
          <div class="table-scroll ep-scroll"><table class="ep-table">
            <thead><tr>
              <th>Endpoint <span class="info" tabindex="0" role="button" aria-label="Método HTTP y ruta del endpoint detectado en el proyecto." data-tip="Método HTTP y ruta del endpoint detectado en el proyecto.">ⓘ</span></th>
              <th>Calidad <span class="info" tabindex="0" role="button" aria-label="Indica si QAgent tiene suficiente información (modelo de respuesta y estado declarado) para probar el endpoint." data-tip="Indica si QAgent tiene suficiente información (modelo de respuesta y estado declarado) para probar el endpoint.">ⓘ</span></th>
              <th>Estado <span class="info" tabindex="0" role="button" aria-label="Código HTTP que devolverá el endpoint. En gris si es el 200 por defecto, no declarado." data-tip="Código HTTP que devolverá el endpoint. En gris si es el 200 por defecto, no declarado.">ⓘ</span></th>
              <th>Respuesta <span class="info" tabindex="0" role="button" aria-label="Modelo de datos que devuelve el endpoint, si está declarado." data-tip="Modelo de datos que devuelve el endpoint, si está declarado.">ⓘ</span></th>
              <th>Errores <span class="info" tabindex="0" role="button" aria-label="Cantidad de errores HTTP (HTTPException) que el endpoint puede lanzar." data-tip="Cantidad de errores HTTP (HTTPException) que el endpoint puede lanzar.">ⓘ</span></th>
              <th>Simula <span class="info" tabindex="0" role="button" aria-label="Dependencias de Depends() que QAgent simula al probar el endpoint." data-tip="Dependencias de Depends() que QAgent simula al probar el endpoint.">ⓘ</span></th>
              <th>Incluir <span class="info" tabindex="0" role="button" aria-label="Permite seleccionar si este endpoint formará parte de la corrida." data-tip="Permite seleccionar si este endpoint formará parte de la corrida.">ⓘ</span></th>
            </tr></thead>
            <tbody id="endpointTable"></tbody>
          </table></div>
          <div class="hint obj-hint">Endpoints agrupados por archivo.</div>
        </div>
        <div class="legend">
          <span><b>Calidad</b>: Lista (tipos y docstring) · Mejorable (sin tipos) · Incierto (sin docstring) — semáforo del oráculo, no de la ejecución.</span>
          <span><b>Calidad (endpoints)</b>: Lista (modelo de respuesta y estado declarado) · Mejorable (solo uno) · Incierto (ninguno).</span>
          <span>★ Profundizar = ≥ 1 condicional (propuesta por AST, editable)</span>
          <span class="warn">⚠ Sin docstring: el valor esperado no tendrá fuente; la prueba puede copiar el comportamiento actual</span>
        </div>
      </div>
    </div>

    <!-- Entorno (EN-06): config.toml, .env, Docker y Git -->
    <div class="card">
        <h4>Entorno</h4>
        <div class="bd">
          <div class="envok"><span id="envIcono" class="ok" style="font-size:18px">…</span><div><b id="envTitulo">Verificando entorno…</b><div class="hint" id="envSub" style="margin:2px 0 0">Configuración, claves de IA, Docker y Git.</div></div><button type="button" class="btn" id="envReintentar" style="margin-left:auto" onclick="verificarEntorno()">Reintentar</button></div>
          <details class="envdet" id="envDet"><summary>Ver detalle</summary>
            <div class="checks" id="envChecks" style="margin-top:8px"></div>
            <div class="hint">Si algo falla, aquí aparece qué hacer. Ej.: "Docker no está abierto: inícialo y vuelve a intentar" o "Falta una clave de IA: contacta al equipo". Las claves nunca se muestran.</div>
          </details>
        </div>
      </div>

  </div></div>
  <div id="tipFlotante" class="tip-flotante" role="tooltip" hidden></div>
  <div class="footbar">
    <span class="msg" id="footMsg"></span>
    <button class="btn" style="margin-left:auto" onclick="go('welcome')">Cancelar</button>
    <button class="btn primary" id="toTests" onclick="go('tests')">Continuar: configuración de pruebas →</button>
  </div>
</section>
`);

let PROYECTO_RESUMEN = null;
let PROYECTO_ERRORES = [];
// Estado de plegado por archivo elegido por el usuario (ruta -> true/false).
// Sin entrada aquí, el archivo se despliega solo si tiene funciones "por revisar" (issue #65).
let ARCHIVOS_ABIERTOS = {};
// Plegado independiente de la tabla de endpoints (issue #66): cambiar de vista no debe
// alterar el plegado ni la selección de la otra vista.
let ARCHIVOS_ABIERTOS_EP = {};
// Vista de objetivos activa: 'funciones' (por defecto) o 'endpoints' (issue #66).
let VISTA_OBJETIVOS = 'funciones';

function reiniciarPlegadoArchivos() {
  ARCHIVOS_ABIERTOS = {};
  ARCHIVOS_ABIERTOS_EP = {};
  VISTA_OBJETIVOS = 'funciones';
}

function aplicarResumenDemo() {
  reiniciarPlegadoArchivos();
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

function actualizarResumenUI(resumen, errores = []) {
  if (!resumen) return;
  if ($('resumenModulos')) $('resumenModulos').textContent = resumen.total_modulos ?? 0;
  if ($('resumenFunciones')) $('resumenFunciones').textContent = resumen.total_funciones_publicas ?? 0;
  if ($('resumenEndpoints')) $('resumenEndpoints').textContent = resumen.total_endpoints ?? 0;
  if ($('resumenErrores')) $('resumenErrores').textContent = resumen.total_errores ?? (errores ? errores.length : 0);
  
  const sd = resumen.inconsistencias?.sin_docstring || { cantidad: 0, porcentaje: 0 };
  const st = resumen.inconsistencias?.sin_tipos || { cantidad: 0, porcentaje: 0 };
  const ca = resumen.inconsistencias?.con_alguna || { cantidad: 0, porcentaje: 0 };
  
  if ($('resumenSinDoc')) {
    $('resumenSinDoc').textContent = `⚠ ${sd.cantidad} sin docstring (${sd.porcentaje}%)`;
    $('resumenSinDoc').className = sd.cantidad > 0 ? 'pill p-amber' : 'pill p-grey';
  }
  if ($('resumenSinTipos')) {
    $('resumenSinTipos').textContent = `${st.cantidad} sin tipos (${st.porcentaje}%)`;
    $('resumenSinTipos').className = st.cantidad > 0 ? 'pill p-amber' : 'pill p-grey';
  }
  if ($('resumenConAlguna')) {
    $('resumenConAlguna').textContent = `${ca.cantidad} con inconsistencias (${ca.porcentaje}%)`;
  }
  if ($('projFnsResumen')) {
    $('projFnsResumen').textContent = `${resumen.total_modulos} módulos .py · ${resumen.total_funciones_publicas} funciones · ${resumen.total_endpoints ?? 0} endpoints`;
  }
}

function cargarDatosVistaPrevia(res) {
  if (!res || !res.ok) return;
  reiniciarPlegadoArchivos();
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
    const endpoints = (m.endpoints || []).map(e => ({
      objetivo: e.objetivo || '',
      metodo: e.metodo || null,
      ruta: e.ruta || null,
      manejador: e.manejador || '',
      response_model: e.response_model || null,
      status_code: e.status_code ?? 200,
      status_code_declarado: !!e.status_code_declarado,
      excepciones_http: (e.excepciones_http || []).map(x => ({ ...x })),
      dependencias: (e.dependencias || []).map(d => d.funcion).filter(Boolean),
      inc: true
    }));
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

/* ---------------- Vista previa ---------------- */
async function loadProject(name, src, where, br='main', ruta=''){
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
  HAS_PRIOR_RUN = await hayCorridaPrevia(ruta);
  ejecucionReal = null;
  reporteReal = null;
  if (typeof reiniciarVistasProyecto === 'function') reiniciarVistasProyecto();
  else document.querySelectorAll('#views a[data-v=exec],#views a[data-v=report],#views a[data-v=monitor],#views a[data-v=history]').forEach(a=>a.classList.add('hide','off'));

  renderTree();   // termina en calc(), que también dibuja la configuración de pruebas
  go('preview');
}

// Sin análisis (fallo en la app real): lista vacía y contadores en cero, sin datos de ejemplo.
function vaciarVistaPrevia() {
  MODULES = [];
  reiniciarPlegadoArchivos();
  PROYECTO_RESUMEN = null;
  PROYECTO_ERRORES = [];
  actualizarResumenUI({ total_modulos: 0, total_funciones_publicas: 0, total_errores: 0 });
}

// Regresión requiere al menos una prueba aprobada persistida, no solo una corrida.
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
const ENV_NOMBRES = {config:'Configuración (config.toml)', claves:'Claves de IA (.env)', docker:'Docker y sandbox', git:'Git'};
async function verificarEntorno() {
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
}

// Se llama desde main.js cuando el HTML del componente ya está montado.
function iniciarVistaPrevia(){
  iniciarTooltips();
  if (window.pywebview && window.pywebview.api) verificarEntorno();
  else window.addEventListener('pywebviewready', verificarEntorno, {once:true});
}
function renderTree(){
  let h = '';
  const dirsVistos = new Set();
  MODULES.forEach((m, i) => {
    const partes = m.path.split('/');
    if (partes.length > 1) {
      const dir = partes.slice(0, -1).join('/') + '/';
      if (!dirsVistos.has(dir)) {
        dirsVistos.add(dir);
        h += `<div class="row dir">📁 ${escHtml(dir)}</div>`;
      }
    }
    const nombreArchivo = partes[partes.length - 1];
    if (m.error) {
      h += `<div class="row ind" style="color:var(--red-t)"><span class="mono">📄 ${escHtml(nombreArchivo)}</span><span class="pill p-red" style="margin-left:auto">no se pudo analizar</span></div>`;
    } else {
      const fnConRamas = (m.fns || []).filter(f => f.br > 0).length;
      const tieneObjetivos = moduloTieneObjetivos(m);
      if (!tieneObjetivos) m.sel = false;
      h += `<div class="row ind ${tieneObjetivos ? '' : 'no-targets'}"><input type="checkbox" ${m.sel ? 'checked' : ''} ${tieneObjetivos ? '' : 'disabled'} onchange="cambiarSeleccionModulo(${i},this.checked)"> <span class="mono">${escHtml(nombreArchivo)}</span><span class="n" title="${fnConRamas} funciones con ramas">${m.fns.length} fn · ${(m.endpoints || []).length} ep</span>${tieneObjetivos ? '' : '<span class="no-targets-note">sin objetivos analizables</span>'}</div>`;
    }
  });
  h += '<div class="row dir ign">📁 tests/ <span class="n">ignorado</span></div>';
  h += '<div class="row dir ign">📁 .qagent/ <span class="n">ignorado</span></div>';
  $('tree').innerHTML = h;
  actualizarSeleccionTodos();
  renderFns();
}
/* Calidad (issue #65): semáforo del oráculo construido solo en el frontend a partir de
   los campos existentes (typed/tipada y doc/docstring). No depende del backend ni de la
   ejecución real de las pruebas.
     - Incierto  : docstring === false (prioridad, aunque existan tipos declarados)
     - Lista     : tipada === true && docstring === true
     - Mejorable : tipada === false && docstring === true */
const CALIDAD_TEXTO = {lista:'Lista', mejorable:'Mejorable', incierto:'Incierto'};
function calidadFuncion(f){
  if(!f.doc) return 'incierto';
  if(f.typed) return 'lista';
  return 'mejorable';
}
function funcionPorRevisar(f){ return calidadFuncion(f) !== 'lista'; }
function contarPorRevisar(m){ return (m.fns || []).filter(funcionPorRevisar).length; }

/* Calidad de endpoints (issue #66): semáforo calculado solo en el frontend a partir de los
   campos que ya entrega el analizador. No se infiere nada: un 200 por defecto no es lo mismo
   que un 200 declarado explícitamente, así que se usa status_code_declarado, no el número.
     - Lista     : declara modelo de respuesta Y código de estado
     - Mejorable : declara solo uno de los dos
     - Incierto  : no declara ninguno */
function calidadEndpoint(e){
  const tieneRespuesta = !!(e.response_model && String(e.response_model).trim());
  const tieneEstado = !!e.status_code_declarado;
  if(tieneRespuesta && tieneEstado) return 'lista';
  if(tieneRespuesta || tieneEstado) return 'mejorable';
  return 'incierto';
}
function endpointPorRevisar(e){ return calidadEndpoint(e) !== 'lista'; }
function contarEndpointsPorRevisar(m){ return (m.endpoints || []).filter(endpointPorRevisar).length; }

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
function totalFuncionesPorRevisar(){
  return MODULES.filter(m => !m.error).flatMap(m => m.fns || []).filter(funcionPorRevisar).length;
}
function totalEndpointsPorRevisar(){
  return MODULES.filter(m => !m.error).flatMap(m => m.endpoints || []).filter(endpointPorRevisar).length;
}

// Selector Funciones/Endpoints: cuenta los detectados, deshabilita la opción sin objetivos,
// avisa si hay objetivos por revisar y conserva la vista elegida al cambiar de pestaña.
function cambiarVistaObjetivos(cual){
  if(cual === 'funciones' && totalFuncionesDetectadas() === 0) return;
  if(cual === 'endpoints' && totalEndpointsDetectados() === 0) return;
  VISTA_OBJETIVOS = cual;
  aplicarVistaObjetivos();
}
function aplicarVistaObjetivos(){
  const esFns = VISTA_OBJETIVOS === 'funciones';
  if($('vistaFns')) $('vistaFns').classList.toggle('hide', !esFns);
  if($('vistaEps')) $('vistaEps').classList.toggle('hide', esFns);
  if($('tabFns')){ $('tabFns').classList.toggle('on', esFns); $('tabFns').setAttribute('aria-selected', String(esFns)); }
  if($('tabEps')){ $('tabEps').classList.toggle('on', !esFns); $('tabEps').setAttribute('aria-selected', String(!esFns)); }
}
function actualizarSelectorObjetivos(){
  const nFns = totalFuncionesDetectadas(), nEps = totalEndpointsDetectados();
  // Si la vista activa se quedó sin objetivos, se muestra la otra (solo si tiene).
  if(VISTA_OBJETIVOS === 'funciones' && nFns === 0 && nEps > 0) VISTA_OBJETIVOS = 'endpoints';
  else if(VISTA_OBJETIVOS === 'endpoints' && nEps === 0 && nFns > 0) VISTA_OBJETIVOS = 'funciones';
  if($('tabFnsN')) $('tabFnsN').textContent = nFns;
  if($('tabEpsN')) $('tabEpsN').textContent = nEps;
  if($('tabFnsWarn')) $('tabFnsWarn').classList.toggle('hide', !(nFns > 0 && totalFuncionesPorRevisar() > 0));
  if($('tabEpsWarn')) $('tabEpsWarn').classList.toggle('hide', !(nEps > 0 && totalEndpointsPorRevisar() > 0));
  if($('tabFns')){
    $('tabFns').disabled = nFns === 0;
    $('tabFns').title = nFns === 0 ? 'No se detectaron funciones en el proyecto' : '';
    $('tabFns').setAttribute('aria-disabled', String(nFns === 0));
  }
  if($('tabEps')){
    $('tabEps').disabled = nEps === 0;
    $('tabEps').title = nEps === 0 ? 'No se detectaron endpoints en el proyecto' : '';
    $('tabEps').setAttribute('aria-disabled', String(nEps === 0));
  }
  aplicarVistaObjetivos();
}

// Plegado por archivo: estado elegido por el usuario si existe; si no, desplegado solo
// cuando el archivo tiene al menos una función por revisar (regla de la issue #65).
function archivoAbierto(m){
  if(Object.prototype.hasOwnProperty.call(ARCHIVOS_ABIERTOS, m.path)) return !!ARCHIVOS_ABIERTOS[m.path];
  return contarPorRevisar(m) > 0;
}
function toggleArchivo(indice){
  const m = MODULES[indice];
  if(!m || m.error) return;
  ARCHIVOS_ABIERTOS[m.path] = !archivoAbierto(m);
  renderFns();  // el plegado no toca la selección de módulos ni funciones
}

// Plegado de endpoints por archivo (issue #66): usa un mapa propio, así abrir o cerrar
// un archivo en una vista no cambia la otra. Sin entrada, se abre si tiene endpoints por revisar.
function endpointAbierto(m){
  if(Object.prototype.hasOwnProperty.call(ARCHIVOS_ABIERTOS_EP, m.path)) return !!ARCHIVOS_ABIERTOS_EP[m.path];
  return contarEndpointsPorRevisar(m) > 0;
}
function toggleArchivoEndpoints(indice){
  const m = MODULES[indice];
  if(!m || m.error) return;
  ARCHIVOS_ABIERTOS_EP[m.path] = !endpointAbierto(m);
  renderEndpoints();  // el plegado no toca la selección
}

// Casilla "Incluir" del archivo en la tabla de endpoints: marca/desmarca sus endpoints
// analizables. Los no resueltos quedan fuera siempre. No cambia "Profundizar" ni las funciones.
function seleccionarEndpointsArchivo(indice, seleccionado){
  const m = MODULES[indice];
  if(!m || m.error) return;
  endpointsElegibles(m).forEach(e => { e.inc = !!seleccionado; });
  m.sel = !!seleccionado || (m.fns || []).some(f => f.inc);
  renderTree();
}

// Incluir un endpoint individual mantiene el módulo activo de forma coherente.
function toggleEndpoint(indice, ei){
  const m = MODULES[indice];
  if(!m || m.error) return;
  const e = (m.endpoints || [])[ei];
  if(!e || !endpointElegible(e)) return;
  e.inc = !e.inc;
  m.sel = moduloConSeleccion(m);
  renderTree();
}

// Un módulo está marcado si tiene alguna función o algún endpoint analizable incluido.
function moduloConSeleccion(m){
  return (m.fns || []).some(f => f.inc) || endpointsIncluidos(m).length > 0;
}

// La propiedad `indeterminate` no se puede fijar por atributo HTML: se aplica al DOM.
function sincronizarCheckboxesArchivoEndpoints(){
  document.querySelectorAll('#endpointTable .file-check').forEach(chk => {
    const m = MODULES[Number(chk.dataset.mi)];
    if(!m) return;
    const elegibles = endpointsElegibles(m);
    const inc = elegibles.filter(e => e.inc).length;
    chk.checked = elegibles.length > 0 && inc === elegibles.length;
    chk.indeterminate = inc > 0 && inc < elegibles.length;
  });
}

/* Tabla de endpoints (issue #66): mismas 7 columnas en todas las filas, agrupadas por
   archivo con encabezado plegable y "Incluir" por archivo y por endpoint. No inventa
   datos: si el backend no entrega un campo, se muestra "—". */
function renderEndpoints(){
  let h = '';
  MODULES.forEach((m, mi) => {
    if(m.error){
      h += `<tr><td colspan="7" style="background:var(--panel2);color:var(--red-t);font-family:var(--mono);font-size:11px;padding:9px 12px">
        <b>📄 ${escHtml(m.path)}</b> <span class="pill p-red" style="margin-left:8px">no se pudo analizar</span>
        <div class="sub" style="color:var(--red-t);margin-top:3px">
          Error de sintaxis (${escHtml(m.error.tipo || 'SyntaxError')}${m.error.linea ? ' en línea ' + m.error.linea : ''}): ${escHtml(m.error.mensaje || 'Error al analizar archivo')}
        </div>
      </td></tr>`;
      return;
    }

    const eps = m.endpoints || [];
    if(!eps.length) return;  // la tabla de endpoints solo lista archivos con endpoints
    const abierto = endpointAbierto(m);
    const porRevisar = contarEndpointsPorRevisar(m);
    const elegibles = endpointsElegibles(m);
    const inc = elegibles.filter(e => e.inc).length;
    const todosInc = !!m.sel && elegibles.length > 0 && inc === elegibles.length;

    h += `<tr class="file-row"><td colspan="7"><div class="file-head">
      <button type="button" class="file-toggle" aria-expanded="${abierto}" onclick="toggleArchivoEndpoints(${mi})" title="${abierto ? 'Ocultar endpoints' : 'Mostrar endpoints'}">${abierto ? '▾' : '▸'}</button>
      <span class="file-icon" aria-hidden="true">📄</span>
      <span class="file-path mono">${escHtml(m.path)}</span>
      <span class="file-count">${eps.length} ${eps.length === 1 ? 'endpoint' : 'endpoints'} · ${porRevisar} por revisar</span>
      <label class="file-incl"><input type="checkbox" class="file-check" data-mi="${mi}" ${todosInc ? 'checked' : ''} ${elegibles.length > 0 ? '' : 'disabled'} onchange="seleccionarEndpointsArchivo(${mi},this.checked)"> Incluir</label>
    </div></td></tr>`;

    if(!abierto) return;

    eps.forEach((e, ei) => {
      const cal = calidadEndpoint(e);
      const elegible = endpointElegible(e);
      const estado = (e.status_code === null || e.status_code === undefined) ? '—' : e.status_code;
      const respuesta = e.response_model ? escHtml(e.response_model) : '—';
      const errores = e.excepciones_http || [];
      const codigos = errores.map(x => x.status_code).filter(c => c !== undefined && c !== null);
      const tipErr = errores.length ? `Errores HTTP: ${codigos.join(', ') || errores.length}` : 'Sin errores HTTP identificados';
      const simula = (e.dependencias && e.dependencias.length)
        ? e.dependencias.map(d => `<span class="pill p-grey">${escHtml(d)}</span>`).join(' ')
        : '<span class="hint">Sin Depends</span>';
      const incluir = `<input type="checkbox" aria-label="Incluir endpoint: ${escHtml(e.objetivo || e.manejador || '')}" ${e.inc ? 'checked' : ''} ${elegible ? '' : 'disabled'} title="${elegible ? '' : 'Ruta no disponible: no se puede probar'}" onchange="toggleEndpoint(${mi},${ei})">`;
      h += `<tr class="${elegible ? '' : 'ep-no-resuelta'}">
        <td class="fn"><span class="endpoint-method">${e.metodo ? escHtml(e.metodo) : 'SIN MÉTODO'}</span> <span class="endpoint-route">${e.ruta ? escHtml(e.ruta) : 'Ruta no disponible'}</span><div class="sub">${e.manejador ? escHtml(e.manejador) : '—'}</div></td>
        <td><span class="pill calidad-${cal}">${CALIDAD_TEXTO[cal]}</span></td>
        <td class="${e.status_code_declarado ? '' : 'muted'}"><span class="mono">${estado}</span></td>
        <td class="mono">${respuesta}</td>
        <td class="mono" title="${escHtml(tipErr)}">${errores.length}</td>
        <td>${simula}</td>
        <td>${incluir}</td>
      </tr>`;
    });
  });
  $('endpointTable').innerHTML = h || '<tr><td colspan="7" class="hint">No se detectaron endpoints en el proyecto.</td></tr>';
  sincronizarCheckboxesArchivoEndpoints();
}

function renderFns(){
  const sel = MODULES.filter(m => m.sel && !m.error && moduloTieneObjetivos(m));
  const totalFns = sel.flatMap(m => m.fns).length;
  const totalEndpointsIncluidos = sel.flatMap(m => endpointsIncluidos(m)).length;
  const totalObjetivos = sel.flatMap(m => m.fns.filter(f => f.inc)).length + totalEndpointsIncluidos;
  $('modCount').textContent = `${sel.length} ${sel.length === 1 ? 'módulo' : 'módulos'} · ${totalObjetivos} objetivos`;
  $('fnCount').textContent = totalFns + ' incluidas';
  let h = '';

  MODULES.forEach((m, mi) => {
    if (m.error) {
      h += `<tr><td colspan="7" style="background:var(--panel2);color:var(--red-t);font-family:var(--mono);font-size:11px;padding:9px 12px">
        <b>📄 ${escHtml(m.path)}</b> <span class="pill p-red" style="margin-left:8px">no se pudo analizar</span>
        <div class="sub" style="color:var(--red-t);margin-top:3px">
          Error de sintaxis (${escHtml(m.error.tipo || 'SyntaxError')}${m.error.linea ? ' en línea ' + m.error.linea : ''}): ${escHtml(m.error.mensaje || 'Error al analizar archivo')}
        </div>
      </td></tr>`;
      return;
    }

    const fns = m.fns || [];
    const tieneObjetivos = moduloTieneObjetivos(m);
    if (!tieneObjetivos) m.sel = false;
    const abierto = archivoAbierto(m);
    const porRevisar = contarPorRevisar(m);
    const incFns = fns.filter(f => f.inc).length;
    // El encabezado refleja la inclusión del archivo: marcado si todas sus funciones están
    // incluidas, indeterminado si solo algunas y desmarcado si ninguna.
    const todosInc = !!m.sel && (fns.length > 0 ? incFns === fns.length : true);

    // Estado de spec existente (se conservan las etiquetas ya usadas)
    const sp = SPEC_STATUS[m.path];
    const spTag = sp === 'reuse'
      ? '<span class="pill p-green">♻ Vigente · Planner se omite</span>'
      : sp === 'stale'
        ? '<span class="pill p-amber">↻ Cambió · spec se regenera</span>'
        : '<span class="pill p-grey">Sin spec previo</span>';
    const revisarTag = `<span class="pill ${porRevisar > 0 ? 'p-amber' : 'p-grey'}">${porRevisar} por revisar</span>`;

    h += `<tr class="file-row"><td colspan="7"><div class="file-head ${tieneObjetivos ? '' : 'no-targets'}">
      <button type="button" class="file-toggle" aria-expanded="${abierto}" onclick="toggleArchivo(${mi})" title="${abierto ? 'Ocultar funciones' : 'Mostrar funciones'}">${abierto ? '▾' : '▸'}</button>
      <span class="file-icon" aria-hidden="true">📄</span>
      <span class="file-path mono">${escHtml(m.path)}</span>
      <span class="file-count">${fns.length} ${fns.length === 1 ? 'función' : 'funciones'}</span>
      ${revisarTag}${tieneObjetivos ? spTag : ''}
      <label class="file-incl"><input type="checkbox" class="file-check" data-mi="${mi}" ${todosInc ? 'checked' : ''} ${tieneObjetivos ? '' : 'disabled'} onchange="seleccionarArchivo(${mi},this.checked)"> Incluir</label>
      ${tieneObjetivos ? '' : '<span class="no-targets-note">sin objetivos analizables</span>'}
    </div></td></tr>`;

    if (!abierto) return;

    fns.forEach((f, fi) => {
      const cal = calidadFuncion(f);
      const docHtml = f.doc
        ? '<span class="ok" title="Tiene descripción">✓</span>'
        : '<span class="warn" title="el valor esperado no tendrá fuente (oráculo débil)">✗</span>';
      const tipadoHtml = f.typed ? '<span class="ok" title="Declara los tipos que recibe y devuelve">✓</span>' : '<span class="no" title="No declara los tipos">✗</span>';
      h += `<tr>
        <td class="fn">${escHtml(f.n)}<div class="sub">${escHtml(f.sig)}</div></td>
        <td><span class="pill calidad-${cal}">${CALIDAD_TEXTO[cal]}</span></td>
        <td class="${f.typed ? 'ok' : 'no'}">${tipadoHtml}</td>
        <td class="${f.doc ? 'ok' : 'warn'}">${docHtml}</td>
        <td class="mono">${f.br}</td>
        <td><button type="button" class="star ${f.crit ? 'on' : ''}" aria-label="Profundizar: ${escHtml(f.n)}" aria-pressed="${f.crit ? 'true' : 'false'}" title="Profundizar: solicita un análisis más exhaustivo de la función. Se aplica si activas Profundizar en la configuración de pruebas." onclick="toggle(${mi},${fi},'crit')">${f.crit ? '★' : '☆'}</button></td>
        <td><input type="checkbox" aria-label="Incluir función: ${escHtml(f.n)}" ${f.inc ? 'checked' : ''} onchange="toggle(${mi},${fi},'inc')"></td>
      </tr>`;
    });
  });

  $('fnTable').innerHTML = h || '<tr><td colspan="7" class="hint">No hay archivos analizables.</td></tr>';
  sincronizarCheckboxesArchivo();
  renderEndpoints();
  actualizarSelectorObjetivos();
  calc();
}

// La propiedad `indeterminate` no se puede fijar por atributo HTML: se aplica al DOM.
function sincronizarCheckboxesArchivo(){
  document.querySelectorAll('#fnTable .file-check').forEach(chk => {
    const m = MODULES[Number(chk.dataset.mi)];
    if(!m) return;
    const fns = m.fns || [];
    const activo = !!m.sel;
    const incFns = fns.filter(f => f.inc).length;
    chk.checked = activo && (fns.length > 0 ? incFns === fns.length : true);
    chk.indeterminate = activo && fns.length > 0 && incFns > 0 && incFns < fns.length;
  });
}

// Casilla "Incluir" del encabezado del archivo: marca/desmarca todas sus funciones.
// No cambia "Profundizar". Mantiene el módulo seleccionado de forma coherente.
function seleccionarArchivo(indice, seleccionado){
  const m = MODULES[indice];
  if(!m || m.error || !moduloTieneObjetivos(m)) return;
  (m.fns || []).forEach(f => { f.inc = !!seleccionado; });
  m.sel = !!seleccionado || endpointsIncluidos(m).length > 0;
  renderTree();
}

function toggle(mi,fi,k){
  const m = MODULES[mi];
  m.fns[fi][k] = !m.fns[fi][k];
  // Incluir una función individual mantiene el módulo activo; Profundizar no altera Incluir.
  if(k === 'inc' && moduloTieneObjetivos(m)){
    m.sel = moduloConSeleccion(m);
  }
  renderTree();
}

function moduloTieneObjetivos(m){
  return !m.error && ((m.fns || []).length > 0 || (m.endpoints || []).length > 0);
}
function cambiarSeleccionModulo(indice, seleccionado){
  const modulo = MODULES[indice];
  modulo.sel = moduloTieneObjetivos(modulo) && seleccionado;
  actualizarSeleccionTodos();
  renderFns();
}
function seleccionarTodosModulos(seleccionado){
  MODULES.forEach(m => { m.sel = moduloTieneObjetivos(m) && seleccionado; });
  renderTree();
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
// `criticas` (HU-06): funciones incluidas y marcadas en Profundizar; llegan al contrato como critical.
function obtenerSeleccionObjetivos(){
  return MODULES.filter(m => m.sel && moduloTieneObjetivos(m)).map(m => ({
    ruta: m.path,
    funciones: (m.fns || []).filter(f => f.inc).map(f => f.n),
    endpoints: (m.endpoints || []).filter(e => endpointElegible(e) && e.inc).map(e => e.objetivo),
    criticas: (m.fns || []).filter(f => f.inc && f.crit).map(f => f.n)
  })).filter(m => m.funciones.length || m.endpoints.length);
}

// Pie de la vista previa (alcance): lo invoca calc() porque depende de la selección actual.
function renderPieVistaPrevia(fns, noDoc, endpoints=[]){
  let m1 = '', b1 = false;
  const total = fns.length + endpoints.length;
  if(!total){ m1 = 'Selecciona al menos un objetivo analizable.'; b1 = true; }
  else if(noDoc){ m1 = `<span class="warn">⚠ ${noDoc} función(es) sin docstring: se generarán, pero con oráculo débil (se marcará en el informe).</span>`; }
  else m1 = `${total} objetivos seleccionados (${fns.length} funciones · ${endpoints.length} endpoints) · siguiente paso: elegir el perfil de pruebas.`;
  $('footMsg').innerHTML = m1; $('toTests').disabled = b1;
}

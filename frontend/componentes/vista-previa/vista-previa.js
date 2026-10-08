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
        <h4>Árbol del proyecto <span class="pill p-grey" id="modCount"></span></h4>
        <div class="bd tree" id="tree"></div>
        <div class="hint" style="padding:0 16px 14px">Solo se analizan los módulos marcados. Menos módulos = menos tokens del Planner.</div>
      </div>
      <div class="card">
        <h4>Funciones detectadas (AST) <span class="pill p-grey" id="fnCount"></span></h4>
        <table>
          <thead><tr><th>Función</th><th>Tipada</th><th>Docstring</th><th>Ramas</th><th title="Crítica: se le aplica mutation testing en el perfil Profundo">Crítica</th><th>Incluir</th></tr></thead>
          <tbody id="fnTable"></tbody>
        </table>
        <div class="legend">
          <span>★ Crítica = ≥ 1 rama if/else o try/except (propuesta por AST, editable)</span>
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
  <div class="footbar">
    <span class="msg" id="footMsg"></span>
    <button class="btn" style="margin-left:auto" onclick="go('welcome')">Cancelar</button>
    <button class="btn primary" id="toTests" onclick="go('tests')">Continuar: configuración de pruebas →</button>
  </div>
</section>
`);

let PROYECTO_RESUMEN = null;
let PROYECTO_ERRORES = [];

function aplicarResumenDemo() {
  const modValidos = MODULES.filter(m => !m.error);
  const fns = modValidos.flatMap(m => m.fns);
  const total = fns.length;
  const sinDoc = fns.filter(f => !f.doc).length;
  const sinTipos = fns.filter(f => !f.typed).length;
  const conAlguna = fns.filter(f => !f.doc || !f.typed).length;
  PROYECTO_RESUMEN = {
    total_modulos: modValidos.length,
    total_funciones_publicas: total,
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
    $('projFnsResumen').textContent = `${resumen.total_modulos} módulos .py · ${resumen.total_funciones_publicas} funciones públicas`;
  }
}

function cargarDatosVistaPrevia(res) {
  if (!res || !res.ok) return;
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
    return {
      path: m.ruta,
      sel: true,
      fns: fns,
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
      if (res && res.ok) {
        cargarDatosVistaPrevia(res);
      } else {
        vaciarVistaPrevia();
        toastError(escHtml((res && res.error) || 'No se pudo analizar el proyecto.'));
      }
    } catch (err) {
      console.error("Error al obtener la vista previa por AST:", err);
      vaciarVistaPrevia();
      toastError('No se pudo analizar el proyecto. Inténtalo de nuevo.');
    }
  } else {
    aplicarResumenDemo();   // modo demostración (navegador, sin Python)
  }
  HAS_PRIOR_RUN = await hayCorridaPrevia(ruta);

  renderTree();
  renderProfiles();
  go('preview');
}

// Sin análisis (fallo en la app real): lista vacía y contadores en cero, sin datos de ejemplo.
function vaciarVistaPrevia() {
  MODULES = [];
  PROYECTO_RESUMEN = null;
  PROYECTO_ERRORES = [];
  actualizarResumenUI({ total_modulos: 0, total_funciones_publicas: 0, total_errores: 0 });
}

// El perfil Regresión solo tiene sentido si el proyecto ya tuvo una corrida: es un dato real
// (~/.pyagent/recientes.json). En la demostración se simula que sí la hubo.
async function hayCorridaPrevia(ruta) {
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.listar_recientes)) return true;
  try {
    const lista = await window.pywebview.api.listar_recientes();
    const r = lista.find(x => x.ruta === ruta);
    return !!(r && r.ultima_corrida);
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

// Se llama desde main.js cuando el HTML del componente ya está montado.
function iniciarVistaPrevia(){
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
      h += `<div class="row ind"><input type="checkbox" ${m.sel ? 'checked' : ''} onchange="MODULES[${i}].sel=this.checked;renderFns()"> <span class="mono">${escHtml(nombreArchivo)}</span><span class="n" title="${fnConRamas} funciones con ramas">${m.fns.length} fn</span></div>`;
    }
  });
  h += '<div class="row dir ign">📁 tests/ <span class="n">ignorado</span></div>';
  h += '<div class="row dir ign">📁 .pyagent/ <span class="n">ignorado</span></div>';
  $('tree').innerHTML = h;
  renderFns();
}
function renderFns(){
  const sel = MODULES.filter(m => m.sel && !m.error);
  const totalFns = sel.flatMap(m => m.fns).length;
  $('modCount').textContent = sel.length + (sel.length === 1 ? ' módulo' : ' módulos');
  $('fnCount').textContent = totalFns + ' incluidas';
  let h = '';
  
  MODULES.forEach((m, mi) => {
    if (m.error) {
      h += `<tr><td colspan="6" style="background:var(--panel2);color:var(--red-t);font-family:var(--mono);font-size:11px;padding:9px 12px">
        <b>📄 ${escHtml(m.path)}</b> <span class="pill p-red" style="margin-left:8px">no se pudo analizar</span>
        <div class="sub" style="color:var(--red-t);margin-top:3px">
          Error de sintaxis (${escHtml(m.error.tipo || 'SyntaxError')}${m.error.linea ? ' en línea ' + m.error.linea : ''}): ${escHtml(m.error.mensaje || 'Error al analizar archivo')}
        </div>
      </td></tr>`;
      return;
    }
    if (!m.sel) return;
    
    const sp = SPEC_STATUS[m.path];
    const spTag = sp === 'reuse' 
      ? '<span class="pill p-green" style="margin-left:8px">♻ spec vigente · Planner se omite</span>' 
      : sp === 'stale' 
        ? '<span class="pill p-amber" style="margin-left:8px">↻ código cambió · spec se regenera</span>' 
        : '<span class="pill p-grey" style="margin-left:8px">sin spec previo</span>';
    const conRamasCount = (m.fns || []).filter(f => f.br > 0).length;
    const ramasTag = `<span class="pill p-grey" style="margin-left:6px" title="${conRamasCount} funciones con ramas">${conRamasCount} con ramas</span>`;
    
    h += `<tr><td colspan="6" style="background:var(--panel2);font-family:var(--mono);font-size:11px;color:var(--mut)"><b>${escHtml(m.path)}</b>${ramasTag}${spTag}</td></tr>`;
    m.fns.forEach((f, fi) => {
      const docHtml = f.doc 
        ? '<span class="ok">✓</span>' 
        : '<span class="warn" title="el valor esperado no tendrá fuente (oráculo débil)">⚠ falta</span>';
      const tipadoHtml = f.typed ? '<span class="ok">✓</span>' : '<span class="no">✗</span>';
      h += `<tr>
        <td class="fn">${escHtml(f.n)}<div class="sub">${escHtml(f.sig)}</div></td>
        <td class="${f.typed ? 'ok' : 'no'}">${tipadoHtml}</td>
        <td class="${f.doc ? 'ok' : 'warn'}" ${f.doc ? '' : 'title="el valor esperado no tendrá fuente (oráculo débil)"'}>${docHtml}</td>
        <td class="mono">${f.br}</td>
        <td><button class="star ${f.crit ? 'on' : ''}" onclick="toggle(${mi},${fi},'crit')">${f.crit ? '★' : '☆'}</button></td>
        <td><input type="checkbox" ${f.inc ? 'checked' : ''} onchange="toggle(${mi},${fi},'inc')"></td>
      </tr>`;
    });
  });
  
  $('fnTable').innerHTML = h || '<tr><td colspan="6" class="hint">Selecciona al menos un módulo.</td></tr>';
  calc();
}
function toggle(mi,fi,k){ MODULES[mi].fns[fi][k] = !MODULES[mi].fns[fi][k]; renderFns(); }

// Pie de la vista previa (alcance): lo invoca calc() porque depende de la selección actual.
function renderPieVistaPrevia(fns, noDoc){
  let m1 = '', b1 = false;
  if(!fns.length){ m1 = 'Selecciona al menos una función.'; b1 = true; }
  else if(noDoc){ m1 = `<span class="warn">⚠ ${noDoc} función(es) sin docstring: se generarán, pero con oráculo débil (se marcará en el informe).</span>`; }
  else m1 = `${fns.length} funciones seleccionadas · siguiente paso: elegir el perfil de pruebas.`;
  $('footMsg').innerHTML = m1; $('toTests').disabled = b1;
}

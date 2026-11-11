// config-pruebas.js — pantalla «Preparar»: qué hacer, tipos de prueba, críticas y comprobaciones previas
// HTML del componente (se monta en el marcador data-componente="config-pruebas/config-pruebas" de index.html)
// Cuatro formas de correr (#69, #70 y issue 133): generar pruebas nuevas, revisión rápida (Humo), volver a correr
// las guardadas o analizar a fondo las críticas. Esta última activa la columna Profundizar de Explorar.
// Los íconos (ICO_*) vienen de inicio/modal-abrir.js, que se carga antes.
const ICO_INICIAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M7 5v14l11-7z"/></svg>';
const ICO_AJUSTES = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>';
const ICO_CANDADO = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
const ICO_PAUSA_PREP = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/></svg>';

registrarComponente('config-pruebas/config-pruebas', `<!-- ===== 3. PREPARAR ===== -->
<section id="s-tests" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <header class="ini-barra">
    <nav class="ini-migas" aria-label="Ubicación"><span class="repoName"></span><span aria-hidden="true">/</span><span aria-current="page">Preparar prueba</span></nav>
    <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
  </header>
  <div class="scroll"><div class="page prep">

    <div class="np-cabecera">
      <div>
        <h1 class="ini-titulo" id="prepTitulo">Prepara una corrida fiable</h1>
        <p class="np-subtitulo" id="prepSub"></p>
      </div>
      <button type="button" class="ini-btn ini-btn-principal" id="toPlan" onclick="accionPrincipalPreparar()"><span id="toPlanIco">${ICO_INICIAR}</span><span id="toPlanTxt">Iniciar prueba</span></button>
    </div>

    <div class="np-aviso np-aviso-info prep-estado" id="prepBloqueo" aria-live="polite">${ICO_AVISO_CLON}<div><b id="prepBloqueoTitulo">Configuración lista</b><span id="prepBloqueoTxt"></span></div></div>

    <div class="prep-cajas-barra">
      <div class="obj-switch" id="prepCajas" role="tablist" aria-label="Tipo de caja de las pruebas" onkeydown="teclasCajas(event)"></div>
      <p class="np-meta" id="prepCajaAyuda" aria-live="polite"></p>
    </div>
    <div class="np-aviso np-aviso-info hide" id="prepCajaVacia" aria-live="polite">${ICO_INFO}<div><b>Todavía no hay pruebas de este tipo</b><span>Aquí irán las que se agreguen a esta caja, como la integración entre funciones (caja gris), que está en camino. Mientras tanto, mira «Todas».</span></div></div>

    <div class="prep-rejilla" id="prepContenidoCajas" role="tabpanel">
      <div class="np-columna">
        <section class="np-tarjeta prep-modo-tarjeta" aria-labelledby="prepModoTitulo">
          <h2 id="prepModoTitulo">¿Qué quieres hacer?</h2>
          <div class="prep-modos" id="cfgModo" role="radiogroup" aria-labelledby="prepModoTitulo"></div>
        </section>

        <div class="prep-fila">
          <section class="np-tarjeta" data-caja-grupo aria-labelledby="prepTiposTitulo">
            <h2 id="prepTiposTitulo">Tipos de prueba</h2>
            <div class="prep-lista" id="prepTipos"></div>
          </section>
          <section class="np-tarjeta" data-caja="blanca" aria-labelledby="prepCritTitulo">
            <h2 id="prepCritTitulo">Funciones críticas</h2>
            <div class="prep-lista" id="prepCriticas"></div>
          </section>
        </div>

        <div class="np-aviso np-aviso-info" id="prepFortaleza" data-caja="blanca">${ICO_INFO}<div><b>Fortaleza de las pruebas</b><span id="prepFortalezaTxt"></span></div></div>
      </div>

      <div class="np-columna">
        <!-- issue 266 (I6): lo que no hace falta para iniciar (arquitectura y E2E, con su propio botón)
             queda plegado. Las pestañas por caja (issue 246) lo siguen filtrando y lo abren al elegir su caja. -->
        <details class="np-opciones prep-avanzado" id="prepAvanzado" data-caja-grupo>
          <summary>Opciones avanzadas: arquitectura y E2E de humo</summary>
          <p class="np-meta">Son opcionales y no hacen falta para iniciar la prueba. Cada una se ejecuta por separado, con su botón.</p>
        <section class="np-tarjeta prep-arquitectura" data-caja="blanca" aria-labelledby="prepArquitecturaTitulo">
          <h2 id="prepArquitecturaTitulo">Reglas de arquitectura</h2>
          <p class="np-meta">La detección de ciclos está activa siempre. Puedes declarar una dependencia prohibida; se analiza en Docker, sin IA ni red.</p>
          <div class="prep-arq-campos">
            <div class="prep-arq-campo"><label class="np-etiqueta" for="prepArqDesde">Desde la capa o módulo</label><div class="np-campo"><input class="np-input" id="prepArqDesde" placeholder="dominio" autocomplete="off"></div></div>
            <div class="prep-arq-campo"><label class="np-etiqueta" for="prepArqHacia">No puede depender de</label><div class="np-campo"><input class="np-input" id="prepArqHacia" placeholder="interfaz" autocomplete="off"></div></div>
          </div>
          <div class="prep-arq-acciones">
            <button type="button" class="ini-btn" onclick="guardarReglaArquitectura()">Guardar regla</button>
            <button type="button" class="ini-btn ini-btn-principal" id="prepArqVerificar" onclick="verificarReglasArquitectura()">Verificar arquitectura</button>
          </div>
          <ul class="np-meta prep-arq-lista" id="prepArqReglas"></ul>
          <div class="np-aviso np-aviso-info hide" id="prepArqResultado" aria-live="polite"></div>
        </section>
        <section class="np-tarjeta prep-arquitectura" data-caja="negra" aria-labelledby="prepE2ETitulo">
          <h2 id="prepE2ETitulo">E2E de humo con Playwright</h2>
          <p class="np-meta" id="prepE2ECompatibilidad">Detecta páginas Express o Vite y las visita en Chromium headless. Solo se ejecuta al pulsar el botón; no usa IA ni red externa.</p>
          <div class="prep-arq-acciones">
            <button type="button" class="ini-btn" id="prepE2EDetectar" onclick="detectarRutasE2E()">Ver rutas</button>
            <button type="button" class="ini-btn ini-btn-principal" id="prepE2EEjecutar" onclick="ejecutarE2E()">Ejecutar E2E</button>
          </div>
          <div class="np-aviso np-aviso-info hide" id="prepE2EResultado" aria-live="polite"></div>
        </section>
        </details>
        <section class="np-tarjeta" id="prepComprobaciones" aria-live="polite"></section>
        <section class="np-tarjeta" id="prepLimites"></section>
        <p class="np-meta">Si una prueba revela un posible bug, conservaremos el criterio original. No la debilitamos para hacerla pasar.</p>
      </div>
    </div>

  </div></div>
</section>
`);

let reglasArquitecturaCargadasPara = '';
let reglasArquitecturaDeclaradas = [];
function mostrarReglasArquitectura(){
  const lista = $('prepArqReglas');
  if (!lista) return;
  lista.innerHTML = reglasArquitecturaDeclaradas.length
    ? reglasArquitecturaDeclaradas.map(r => `<li><code>${escHtml(r.desde)}</code> no depende de <code>${escHtml(r.hacia)}</code></li>`).join('')
    : '<li>Sin restricciones de capas declaradas.</li>';
}
async function cargarReglasArquitectura(){
  if (!projectPath || reglasArquitecturaCargadasPara === projectPath) return;
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.obtener_reglas_arquitectura) return;
  try {
    const r = await api.obtener_reglas_arquitectura(projectPath);
    if (!r || !r.ok) return;
    reglasArquitecturaDeclaradas = (r.reglas || []).filter(x => x.origen !== 'universal');
    const personalizada = reglasArquitecturaDeclaradas.find(x => x.tipo === 'dependencia_prohibida');
    if (personalizada) {
      $('prepArqDesde').value = personalizada.desde || '';
      $('prepArqHacia').value = personalizada.hacia || '';
    }
    mostrarReglasArquitectura();
    reglasArquitecturaCargadasPara = projectPath;
  } catch (err) { console.warn('No se pudieron cargar las reglas de arquitectura:', err); }
}
async function guardarReglaArquitectura(){
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.guardar_reglas_arquitectura) return;
  const desde = $('prepArqDesde').value.trim(), hacia = $('prepArqHacia').value.trim();
  if (!desde || !hacia) { toastError('Indica las dos capas o módulos de la regla.'); return; }
  const existe = reglasArquitecturaDeclaradas.some(r => r.desde === desde && r.hacia === hacia);
  if (!existe) {
    let numero = reglasArquitecturaDeclaradas.length + 1;
    while (reglasArquitecturaDeclaradas.some(r => r.id === `capas-${String(numero).padStart(3, '0')}`)) numero++;
    reglasArquitecturaDeclaradas.push({id:`capas-${String(numero).padStart(3, '0')}`, tipo:'dependencia_prohibida', nombre:`${desde} no debe depender de ${hacia}`, origen:'usuario', confirmada:true, desde, hacia});
  }
  const documento = {version:'1', reglas:reglasArquitecturaDeclaradas};
  const r = await api.guardar_reglas_arquitectura(projectPath, documento);
  if (!r || !r.ok) { toastError(escHtml((r && r.motivo) || 'No se pudo guardar la regla.')); return; }
  mostrarReglasArquitectura();
  toast('Regla de arquitectura guardada.');
}
async function verificarReglasArquitectura(){
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.verificar_arquitectura) return;
  const boton = $('prepArqVerificar'), salida = $('prepArqResultado');
  boton.disabled = true; boton.textContent = 'Verificando…';
  salida.classList.remove('hide'); salida.innerHTML = `${ICO_GIRANDO}<div><b>Analizando dependencias en Docker</b><span>Sin acceso a red y sin consumo de tokens.</span></div>`;
  try {
    const r = await api.verificar_arquitectura(projectPath);
    if (!r || !r.ok) throw new Error((r && r.motivo) || 'No se pudo verificar la arquitectura.');
    renderResultadoArquitectura(r);
  } catch (err) {
    salida.innerHTML = `${ICO_ERROR}<div><b>No se completó la verificación</b><span>${escHtml(String(err.message || err))}</span></div>`;
  } finally { boton.disabled = false; boton.textContent = 'Verificar arquitectura'; }
}
function renderResultadoArquitectura(r){
  const salida = $('prepArqResultado');
  const incumplen = (r.reglas || []).filter(x => x.estado === 'incumple').length;
  const sinVeredicto = (r.reglas || []).filter(x => x.estado === 'sin_veredicto').length;
  const detalle = (r.reglas || []).map(regla => {
    const ubicaciones = (regla.hallazgos || []).map(h => `${escHtml(h.desde)} → ${escHtml(h.hacia)} · ${escHtml(h.archivo || 'ubicación no disponible')}${h.linea ? `:${h.linea}` : ''}`).join('; ');
    return `<li><b>${escHtml(regla.nombre)}</b>: ${escHtml(regla.estado)}${ubicaciones ? ` — ${ubicaciones}` : ''}</li>`;
  }).join('');
  salida.classList.remove('hide');
  salida.innerHTML = `${incumplen ? ICO_ERROR : sinVeredicto ? ICO_AVISO_CLON : ICO_OK}<div><b>${incumplen ? `${incumplen} reglas incumplidas` : sinVeredicto ? 'Verificación sin veredicto completo' : 'Arquitectura conforme'}</b><span>Corrida ${escHtml(r.run_id)} · ${(r.reglas || []).length} reglas registradas.</span><ul>${detalle}</ul><button type="button" class="ini-btn" onclick="exportarInformeArquitectura('${escHtml(r.run_id)}')">Exportar PDF</button></div>`;
}
async function abrirResultadoArquitectura(runId){
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.obtener_resultado_arquitectura) return;
  const r = await api.obtener_resultado_arquitectura(projectPath, runId);
  if (!r || !r.ok) { toastError(escHtml((r && r.motivo) || 'No se pudo abrir la verificación.')); return; }
  go('tests');
  renderResultadoArquitectura(r);
}
async function exportarInformeArquitectura(runId){
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.exportar_informe_arquitectura) return;
  const r = await api.exportar_informe_arquitectura(projectPath, runId, 'pdf');
  if (!r || !r.ok) { toastError(escHtml((r && r.motivo) || 'No se pudo exportar el informe.')); return; }
  toast(`Informe guardado en ${r.ruta}`);
}

function renderCompatibilidadPruebas(){
  const noCompatible = typeof PROYECTO_E2E_DISPONIBLE !== 'undefined' && PROYECTO_E2E_DISPONIBLE === false;
  for (const id of ['prepE2EDetectar', 'prepE2EEjecutar']) {
    const boton = $(id);
    if (boton) {
      boton.disabled = noCompatible;
      boton.title = noCompatible ? 'El adaptador de este proyecto no ofrece E2E con Playwright.' : '';
    }
  }
  const texto = $('prepE2ECompatibilidad');
  if (texto) texto.textContent = noCompatible
    ? 'E2E con Playwright no está disponible para este proyecto. Actualmente admite aplicaciones JavaScript/TypeScript compatibles con Express o Vite. Las pruebas unitarias, de endpoints y de arquitectura se revisan por separado.'
    : 'Detecta páginas Express o Vite y las visita en Chromium headless. Solo se ejecuta al pulsar el botón; no usa IA ni red externa.';
  return !noCompatible;
}

async function detectarRutasE2E(){
  if (!renderCompatibilidadPruebas()) return;
  const api = window.pywebview && window.pywebview.api;
  const salida = $('prepE2EResultado');
  if (!api || !api.detectar_e2e) return;
  salida.classList.remove('hide');
  salida.innerHTML = `${ICO_GIRANDO}<div><b>Detectando rutas estáticas</b><span>No se inicia la aplicación.</span></div>`;
  const r = await api.detectar_e2e(projectPath);
  if (!r || !r.ok) { salida.innerHTML = `${ICO_AVISO_CLON}<div><b>E2E no disponible</b><span>${escHtml((r && r.motivo) || 'No se detectaron rutas compatibles.')}</span></div>`; return; }
  const items = (r.routes || []).map(route => `<li><code>${escHtml(route.path)}</code> · ${route.eligible ? 'lista' : escHtml(route.reason || 'sin veredicto')} · ${escHtml(route.source)}</li>`).join('');
  salida.innerHTML = `${ICO_INFO}<div><b>${(r.routes || []).length} rutas detectadas</b><span>${escHtml(r.framework)} · comando estructurado: ${escHtml((r.start_command || []).join(' '))}</span><ul>${items}</ul></div>`;
}

async function ejecutarE2E(){
  if (!renderCompatibilidadPruebas()) return;
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.ejecutar_e2e) return;
  const boton = $('prepE2EEjecutar'), salida = $('prepE2EResultado');
  if (!window.confirm('Se preparará la imagen pesada de Playwright si aún no existe y se iniciará la aplicación dentro de Docker, sin red externa. ¿Continuar?')) return;
  boton.disabled = true; boton.textContent = 'Ejecutando…';
  salida.classList.remove('hide');
  salida.innerHTML = `${ICO_GIRANDO}<div><b>Iniciando app y Chromium en Docker</b><span>La primera ejecución puede construir la imagen bajo demanda.</span></div>`;
  try {
    const r = await api.ejecutar_e2e(projectPath);
    if (!r || !r.ok) throw new Error((r && r.motivo) || 'No se pudo ejecutar E2E.');
    renderResultadoE2E(r);
  } catch (error) {
    salida.innerHTML = `${ICO_ERROR}<div><b>No se completó el humo E2E</b><span>${escHtml(String(error.message || error))}</span></div>`;
  } finally { boton.disabled = false; boton.textContent = 'Ejecutar E2E'; }
}

function renderResultadoE2E(r){
  const salida = $('prepE2EResultado');
  const rows = (r.routes || []).map(route => `<li><code>${escHtml(route.path)}</code> · ${escHtml(route.status)} · HTTP ${route.http_status === null ? '—' : route.http_status}${route.reason ? ` · ${escHtml(route.reason)}` : ''}${route.screenshot ? ` · captura ${escHtml(route.screenshot)}` : ''}</li>`).join('');
  salida.classList.remove('hide');
  salida.innerHTML = `${r.status === 'cumple' ? ICO_OK : r.status === 'falla' ? ICO_ERROR : ICO_AVISO_CLON}<div><b>Humo E2E: ${escHtml(r.status)}</b><span>Corrida ${escHtml(r.run_id)} · ${(r.summary || {}).passed || 0} pasan · ${(r.summary || {}).failed || 0} fallan · ${(r.summary || {}).no_verdict || 0} sin veredicto · 0 tokens.</span><ul>${rows}</ul><button type="button" class="ini-btn" onclick="exportarInformeE2E('${escHtml(r.run_id)}')">Exportar HTML</button></div>`;
}

async function abrirResultadoE2E(runId){
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.obtener_resultado_e2e) return;
  const r = await api.obtener_resultado_e2e(projectPath, runId);
  if (!r || !r.ok) { toastError(escHtml((r && r.motivo) || 'No se pudo abrir la corrida E2E.')); return; }
  go('tests'); renderResultadoE2E(r);
}

async function exportarInformeE2E(runId){
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.exportar_informe_e2e) return;
  const r = await api.exportar_informe_e2e(projectPath, runId, 'html');
  if (!r || !r.ok) { toastError(escHtml((r && r.motivo) || 'No se pudo exportar el informe E2E.')); return; }
  toast(`Informe E2E guardado en ${escHtml(r.path)}`);
}

// #69: la elección de la pantalla se traduce al perfil que recibe start_run (humo, std, deep o reg, #70).
// Sin críticas marcadas no hay nada que analizar a fondo: se corre como Estándar.
// issue 133: la revisión rápida es la estrategia Humo (un caso normal por objetivo, #75); se combina con
// Unitarias y Endpoints API igual que Estándar. Solo se usa si el usuario la elige.
function perfilDeEleccion({modo, profundizarRepetir = false}, prioritarias, repetibles = 0){
  if (modo === 'humo') return 'humo';
  if (modo === 'repetir') return profundizarRepetir && repetibles > 0 ? 'reg_deep' : 'reg';
  if (modo === 'fondo') return prioritarias > 0 ? 'deep' : 'std';
  return 'std';
}

// Issue 150: solo funciones incluidas y marcadas cuya prueba guardada sigue vigente.
// El backend calcula PRUEBAS_REPETIBLES con la misma política que usa la regresión,
// incluido el descarte de pruebas triviales de TypeError de la issue 149.
function criticasRepetibles(){
  if (!(PRUEBAS_REPETIBLES instanceof Set) || eleccionPruebas.unitarias === false) return 0;
  return MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m))
    .flatMap(m=>(m.fns || []).filter(f=>f.inc && f.crit)
      .map(f=>PRUEBAS_REPETIBLES.has(m.path + '::' + f.n)))
    .filter(Boolean).length;
}

// Objetivos que entran en la corrida: lo incluido en Explorar, según los tipos de prueba elegidos.
function estFor(k){
  const p = PROFILES.find(x=>x.k===k);
  const mods = MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m));
  const fns = eleccionPruebas.unitarias === false ? [] : mods.flatMap(m=>m.fns).filter(f=>f.inc);
  const endpoints = eleccionPruebas.endpoints === false ? [] : mods.flatMap(m=>(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc));
  const objetivos = mods.flatMap(m=>[
    ...(eleccionPruebas.unitarias === false ? [] : m.fns.filter(f=>f.inc)),
    ...integracionesIncluidas(m),
    ...(eleccionPruebas.endpoints === false ? [] : (m.endpoints || []).filter(e=>endpointElegible(e) && e.inc))
  ].map(objetivo=>({...objetivo, reuse: SPEC_STATUS[m.path]==='reuse'})));
  const reused = k==='reg' ? 0 : objetivos.filter(objetivo=>objetivo.reuse).length;
  const total = objetivos.length;
  const et = {P: (total - reused) * p.tok * EST_SPLIT.P, G: total * p.tok * EST_SPLIT.G, R: total * p.tok * EST_SPLIT.R};
  // issue 275: la inferencia es un segundo paso del Planner solo para las funciones sin docstring; se estima aparte.
  const inferidas = INFERIR_SIN_DOCSTRING && k!=='reg' && eleccionPruebas.unitarias !== false
    ? mods.filter(m=>SPEC_STATUS[m.path]!=='reuse').flatMap(m=>m.fns).filter(f=>f.inc && f.inferible).length : 0;
  const tokInferidas = Math.round(inferidas * p.tok * EST_SPLIT.P);
  const tok = Math.round(et.P + et.G + et.R) + tokInferidas;
  return {p, fns, endpoints, total, reused, tok, inferidas, tokInferidas, time: Math.max(1, Math.round(total * p.t))};
}
// issue 275: la persona activa o apaga la inferencia y la revisión; se recalcula la estimación.
function elegirInferencia(cambio){
  if ('inferir' in cambio) INFERIR_SIN_DOCSTRING = !!cambio.inferir;
  if ('revisar' in cambio) REVISAR_INFERIDOS = !!cambio.revisar;
  calc();
}

// #74: «4 funciones y 2 endpoints críticos» según lo marcado en Profundizar.
function textoPrioritarias(fns, eps){
  if (!eps) return `${fns} ${fns===1 ? 'función crítica' : 'funciones críticas'}`;
  const ep = `${eps} ${eps===1 ? 'endpoint' : 'endpoints'}`;
  if (!fns) return `${ep} ${eps===1 ? 'crítico' : 'críticos'}`;
  return `${fns} ${fns===1 ? 'función' : 'funciones'} y ${ep} críticos`;
}
function elegirPruebas(cambio){
  if (cambio.modo && cambio.modo !== 'repetir') cambio = {...cambio, profundizarRepetir:false};
  eleccionPruebas = {...eleccionPruebas, ...cambio};
  calc();
  if (typeof desbloquearVista === 'function') desbloquearVista('monitor');
}
// Uso de IA estimado de la corrida completa, en palabras
function usoIA(tok){
  if (!tok) return 'sin IA';
  return tok < 50000 ? 'bajo' : tok < 200000 ? 'medio' : 'alto';
}

/* ---------- ¿Qué quieres hacer? ---------- */
// `cajas`: en qué pestañas por tipo de caja se ofrece cada opción (issue 246, docs/arquitectura.md §10.2).
// Estándar y Humo usan solo la especificación (caja negra en funciones, gris en endpoints); Regresión vuelve a
// correr esas pruebas y puede medir su fortaleza (caja blanca); el análisis a fondo es la capa de caja blanca.
const MODOS_PREPARAR = [
  {k:'nuevas',  cajas:['negra','gris'],          t:'Generar pruebas nuevas',     d:'Crear casos para lo que cambió y reutilizar lo que sigue igual.'},
  {k:'humo',    cajas:['negra','gris'],          t:'Revisión rápida (humo)',     d:'Un caso normal por función o endpoint para confirmar que responde. Útil como primera revisión.',
    tip:'Prueba de humo: un solo caso normal por objetivo. No busca valores límite ni errores y no exige cubrir las ramas.'},
  {k:'repetir', cajas:['negra','gris','blanca'], t:'Volver a correr las guardadas', d:'Regresión: comprueba que los cambios no rompieron lo que antes funcionaba. No usa IA.',
    tip:'Regresión: volver a correr las pruebas guardadas para comprobar que los cambios no rompieron lo que antes funcionaba.'},
  {k:'fondo',   cajas:['blanca'],         t:'Análisis a fondo de críticas', d:'Busca casos límite y mide la fortaleza de las pruebas. Tarda más.'},
];
function renderRegresionProfunda(repetibles){
  const datosListos = PRUEBAS_REPETIBLES instanceof Set;
  const deshabilitada = !HAS_PRIOR_RUN || !datosListos || repetibles === 0;
  const motivo = !HAS_PRIOR_RUN
    ? 'Disponible cuando haya pruebas aprobadas y guardadas de este proyecto.'
    : !datosListos
      ? 'No se pudo confirmar si las pruebas guardadas siguen vigentes. Vuelve a abrir el proyecto para comprobarlo.'
      : repetibles === 0
        ? 'Ninguna función crítica seleccionada tiene una prueba guardada válida.'
        : `${repetibles} ${repetibles === 1 ? 'función crítica elegible' : 'funciones críticas elegibles'}.`;
  const marcada = eleccionPruebas.profundizarRepetir === true && !deshabilitada;
  return `<label class="prep-reg-deep ${deshabilitada ? 'dis' : ''}" title="${escHtml(motivo)}">
    <input type="checkbox" class="exp-caja" id="prepRegDeep" ${marcada ? 'checked' : ''} ${deshabilitada ? 'disabled' : ''}
      aria-describedby="prepRegDeepDesc" onchange="elegirPruebas({profundizarRepetir:this.checked})">
    <span><b>Medir la fortaleza de las críticas</b>
      <span class="prep-desc" id="prepRegDeepDesc">Repite las pruebas guardadas y utiliza análisis de mutación para evaluar la fortaleza de las pruebas críticas. No consume tokens de IA, pero puede tardar más.</span>
      <span class="prep-desc">${escHtml(motivo)}</span></span>
  </label>`;
}

function renderModosPreparar(repetibles = criticasRepetibles()){
  const {modo} = eleccionPruebas;
  // issue 246: cada pestaña ofrece solo las opciones que tocan ese tipo de caja; lo elegido no cambia.
  const ofrecidas = MODOS_PREPARAR.filter(o => cajaActiva === 'todas' || o.cajas.includes(cajaActiva));
  const elegidaOculta = MODOS_PREPARAR.find(o => o.k === modo && !ofrecidas.includes(o));
  const nota = elegidaOculta
    ? `<p class="prep-desc prep-modo-oculto">Tienes elegida «${elegidaOculta.t}», que está en otra pestaña. Mira «Todas» para verla.</p>` : '';
  $('cfgModo').innerHTML = ofrecidas.map(o => {
    const bloqueado = o.k === 'repetir' && !HAS_PRIOR_RUN;
    const opcion = `<button type="button" role="radio" class="prep-modo ${modo===o.k?'on':''}" aria-checked="${modo===o.k}"
      ${bloqueado ? 'disabled title="Requiere una corrida previa de este proyecto"' : (o.tip ? `title="${o.tip}"` : '')} onclick="elegirPruebas({modo:'${o.k}'})">
      <span class="prep-radio" aria-hidden="true"></span>
      <span><b>${o.t}</b><span class="prep-desc">${bloqueado ? 'Disponible cuando haya pruebas aprobadas y guardadas de este proyecto.' : o.d}</span></span>
    </button>`;
    return `<div class="prep-modo-grupo ${modo===o.k?'on':''}">${opcion}${o.k === 'repetir' ? renderRegresionProfunda(repetibles) : ''}</div>`;
  }).join('') + nota;
}

/* ---------- Tipos de prueba y funciones críticas ---------- */
function renderTiposPrueba(){
  const mods = MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m));
  const nFns = mods.flatMap(m=>m.fns).filter(f=>f.inc).length;
  const nEps = mods.flatMap(m=>(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc)).length;
  // issue 245: cadenas de funciones que se pueden probar juntas (las incluidas en Explorar).
  const nInt = mods.flatMap(m=>(m.integraciones || []).filter(i=>(m.fns || []).some(f=>f.n===i.n && f.inc))).length;
  // issue 246: cada tipo declara su caja (data-caja) para las pestañas de Preparar.
  const fila = (clave, titulo, n, singular, plural, caja) => `<label class="prep-casilla ${n ? '' : 'dis'}" data-caja="${caja}">
      <input type="checkbox" class="exp-caja" ${eleccionPruebas[clave] === true && n ? 'checked' : ''} ${n ? '' : 'disabled'} onchange="elegirPruebas({${clave}:this.checked})">
      <span><b>${titulo}</b><span class="prep-desc">${n} ${n === 1 ? singular : plural}</span></span>
    </label>`;
  // issue 275 (ADR-015): funciones sin docstring que QAgent puede inferir (solo Python) entre las unitarias elegidas.
  const nInferibles = eleccionPruebas.unitarias === true ? mods.flatMap(m=>m.fns).filter(f=>f.inc && f.inferible).length : 0;
  const tokInferidas = nInferibles && INFERIR_SIN_DOCSTRING ? (estFor(profile==='reg_deep' ? 'reg' : profile).tokInferidas || 0) : 0;
  const filaInferencia = !mods.some(m=>m.fns.some(f=>f.inferible)) ? '' : `<label class="prep-casilla ${nInferibles ? '' : 'dis'}" data-caja="negra">
      <input type="checkbox" class="exp-caja" ${INFERIR_SIN_DOCSTRING && nInferibles ? 'checked' : ''} ${nInferibles ? '' : 'disabled'} onchange="elegirInferencia({inferir:this.checked})">
      <span><b>Inferir funciones sin docstring</b><span class="prep-desc">${nInferibles ? `${nInferibles} ${nInferibles === 1 ? 'función sin docstring' : 'funciones sin docstring'}: QAgent deduce su resultado leyendo su código y su uso, sin ejecutarlo. Son pruebas de regresión, sin contrato documentado.${tokInferidas ? ` Estimación aparte: ~${tokInferidas.toLocaleString('es-PE')} tokens más.` : ''}` : 'Elige Unitarias con funciones sin docstring para usarla.'}</span></span>
    </label>
    <label class="prep-casilla ${nInferibles && INFERIR_SIN_DOCSTRING ? '' : 'dis'}" data-caja="negra">
      <input type="checkbox" class="exp-caja" ${REVISAR_INFERIDOS && nInferibles && INFERIR_SIN_DOCSTRING ? 'checked' : ''} ${nInferibles && INFERIR_SIN_DOCSTRING ? '' : 'disabled'} onchange="elegirInferencia({revisar:this.checked})">
      <span><b>Revisar contratos inferidos</b><span class="prep-desc">Antes de generar las pruebas, la corrida se detiene para que aceptes o descartes lo que se infirió de cada función.</span></span>
    </label>`;
  $('prepTipos').innerHTML = fila('unitarias', 'Unitarias', nFns, 'función seleccionada', 'funciones seleccionadas', 'negra')
    + filaInferencia
    + fila('endpoints', 'Endpoints API', nEps, 'endpoint seleccionado', 'endpoints seleccionados', 'gris')
    + (mods.some(m=>(m.integraciones || []).length)
      ? fila('integracion', 'Integración interna', nInt, 'cadena de funciones', 'cadenas de funciones', 'negra')
      : '');
}
// Críticas: funciones y endpoints incluidos y marcados en Profundizar. Se muestran tres; el resto
// se ve y se edita en la columna Profundizar de Explorar (visible con «Análisis a fondo»).
function renderCriticas(){
  const criticas = [];
  MODULES.forEach((m, mi) => {
    if(!m.sel || m.error || !moduloTieneObjetivos(m)) return;
    (m.fns || []).forEach((f, fi) => { if(f.inc && f.crit) criticas.push({n:f.n, fn:`toggle(${mi},${fi},'crit')`}); });
    (m.endpoints || []).forEach((e, ei) => { if(endpointElegible(e) && e.inc && e.crit) criticas.push({n:e.objetivo, fn:`toggleEndpointCrit(${mi},${ei})`}); });
  });
  $('prepCritTitulo').textContent = `Funciones críticas · ${criticas.length}`;
  // issue 133: con Humo no hay análisis a fondo; la mutación necesita la prueba completa (arquitectura §10.3).
  const humo = eleccionPruebas.modo === 'humo';
  $('prepFortaleza').classList.toggle('prep-no-aplica', humo);
  $('prepFortalezaTxt').textContent = humo
    ? 'No se mide en la revisión rápida: con un solo caso por objetivo casi todos los errores introducidos pasarían inadvertidos.'
    : 'Mide si las pruebas detectan errores introducidos a propósito. Solo se mide en las funciones que marques como críticas.';
  if (humo) {
    $('prepCriticas').innerHTML = criticas.slice(0, 3).map(c => `<label class="prep-casilla dis">
        <input type="checkbox" class="exp-caja" checked disabled aria-label="Crítica: ${escHtml(c.n)}"><span class="np-mono">${escHtml(c.n)}</span>
      </label>`).join('')
      + '<p class="prep-desc">No aplica en la revisión rápida. Las críticas se analizan a fondo con «Análisis a fondo de críticas».</p>';
    return;
  }
  const visibles = criticas.slice(0, 3), resto = criticas.length - visibles.length;
  const enlace = resto > 0 ? `Ver y editar las otras ${resto} ${resto === 1 ? 'crítica' : 'críticas'}` : (criticas.length ? 'Editar en Explorar' : 'Marcar críticas en Explorar');
  $('prepCriticas').innerHTML = (visibles.map(c => `<label class="prep-casilla">
      <input type="checkbox" class="exp-caja" checked aria-label="Crítica: ${escHtml(c.n)}" onchange="${c.fn}"><span class="np-mono">${escHtml(c.n)}</span>
    </label>`).join('') || '<p class="prep-desc">Todavía no hay funciones críticas marcadas.</p>')
    + (eleccionPruebas.modo !== 'fondo' && criticas.length ? '<p class="prep-desc">Se analizan a fondo al elegir «Análisis a fondo de críticas».</p>' : '')
    + `<button type="button" class="ini-enlace prep-enlace" onclick="irACriticas()">${enlace}</button>`;
}
// Para marcar o revisar críticas hace falta la columna Profundizar de Explorar.
function irACriticas(){
  if (eleccionPruebas.modo !== 'fondo') elegirPruebas({modo:'fondo'});
  go('preview');
}

/* ---------- Pestañas por tipo de caja (issue 246) ----------
   Agrupa lo que se puede probar según cuánto se mira por dentro: caja negra (solo el comportamiento
   visible), caja blanca (el código y su estructura) y caja gris (una mezcla). Es solo una vista: cambiar
   de pestaña oculta o muestra tarjetas (las marcadas con data-caja) y nunca cambia lo elegido. */
const CAJAS = [
  {k:'todas',  t:'Todas',       d:'Todos los tipos de prueba juntos.'},
  {k:'negra',  t:'Caja negra',  d:'Se diseñan solo con lo que el código promete (nombre, firma y documentación), sin mirar cómo está escrito.'},
  {k:'blanca', t:'Caja blanca', d:'Se lee el código para medir si las pruebas detectan errores (mutación) o para revisar su estructura.'},
  {k:'gris',   t:'Caja gris',   d:'Mezcla de ambas: el código guía qué casos probar, pero el resultado esperado sale de lo que se declara.'},
];
let cajaActiva = 'todas';

// Cada tipo declara su caja con data-caja, como define docs/arquitectura.md §10.2:
//  · negra: funciones (solo nombre, firma y docstring) y E2E de humo (se prueba desde fuera);
//  · gris: endpoints (el código del manejador guía los casos; el resultado esperado sale de la ruta declarada);
//  · blanca: la mutación de las críticas y las reglas de arquitectura (leen el código).
// Las pestañas solo filtran qué se ve: no cuentan ni eligen nada.
function renderCajas(){
  const barra = $('prepCajas');
  if (!barra) return;
  barra.innerHTML = CAJAS.map(c => {
    const on = c.k === cajaActiva;
    return `<button type="button" id="prepCaja-${c.k}" class="obj-tab ${on ? 'on' : ''}" role="tab" aria-selected="${on}"
      aria-controls="prepContenidoCajas" tabindex="${on ? 0 : -1}" title="${escHtml(c.d)}"
      onclick="elegirCaja('${c.k}')">${c.t}</button>`;
  }).join('');
  $('prepContenidoCajas').setAttribute('aria-labelledby', 'prepCaja-' + cajaActiva);
  $('prepCajaAyuda').textContent = (CAJAS.find(c => c.k === cajaActiva) || CAJAS[0]).d;
}
function aplicarCaja(){
  const panel = $('prepContenidoCajas');
  if (!panel) return;
  panel.querySelectorAll('[data-caja]').forEach(el => el.classList.toggle('hide', cajaActiva !== 'todas' && el.dataset.caja !== cajaActiva));
  // Una tarjeta que agrupa varios tipos (Tipos de prueba) se oculta si ninguno se ve.
  panel.querySelectorAll('[data-caja-grupo]').forEach(g => g.classList.toggle('hide', !g.querySelector('[data-caja]:not(.hide)')));
  // issue 266 (I6): en «Todas» lo avanzado sigue plegado; al elegir una caja con algo avanzado, se abre.
  const avanzado = $('prepAvanzado');
  if (avanzado && cajaActiva !== 'todas' && !avanzado.classList.contains('hide')) avanzado.open = true;
  $('prepCajaVacia').classList.toggle('hide', !!panel.querySelector('[data-caja]:not(.hide)'));
  renderCajas();
}
function elegirCaja(k, enfocar = false){
  if (!CAJAS.some(c => c.k === k)) return;
  cajaActiva = k;
  renderModosPreparar();   // «¿Qué quieres hacer?» ofrece solo lo que toca esta caja
  aplicarCaja();
  if (enfocar && $('prepCaja-' + k)) $('prepCaja-' + k).focus();
}
// Teclado de las pestañas: flechas, Inicio y Fin.
function teclasCajas(ev){
  const i = CAJAS.findIndex(c => c.k === cajaActiva);
  const destino = {ArrowRight:(i + 1) % CAJAS.length, ArrowLeft:(i + CAJAS.length - 1) % CAJAS.length, Home:0, End:CAJAS.length - 1}[ev.key];
  if (destino === undefined) return;
  ev.preventDefault();
  elegirCaja(CAJAS[destino].k, true);
}

/* ---------- Comprobaciones previas ----------
   Salen de la verificación real del entorno (EN-06: configuración, claves, Docker y Git) y de la
   selección. Sin pywebview es una demostración: todo se muestra como listo. */
// Lo incluido en Explorar, sin aplicar los tipos de prueba (lo usan el pie de Explorar y las comprobaciones).
function seleccionExplorar(){
  const mods = MODULES.filter(m=>m.sel && !m.error && moduloTieneObjetivos(m));
  return {
    fns: mods.flatMap(m=>m.fns).filter(f=>f.inc),
    endpoints: mods.flatMap(m=>(m.endpoints || []).filter(e=>endpointElegible(e) && e.inc)),
  };
}
const algunTipoElegido = () => eleccionPruebas.unitarias === true || eleccionPruebas.endpoints === true || eleccionPruebas.integracion === true;

function comprobacionesPrevias(total, reused){
  const lista = [];
  const r = typeof ENTORNO_VERIFICADO !== 'undefined' ? ENTORNO_VERIFICADO : null;
  const demo = !(window.pywebview && window.pywebview.api);
  const porId = id => r && (r.comprobaciones || []).find(c => c.id === id);
  if (demo) {
    lista.push({ok:true, t:'IA conectada', d:'Modo demostración'});
    lista.push({ok:true, t:'Motor activo', d:'Entorno aislado · sin internet'});
  } else if (!r) {
    lista.push({ok:null, t:'Verificando el entorno…', d:'IA, motor y configuración'});
  } else {
    const ia = porId('claves'), motor = porId('docker'), conf = porId('config'), git = porId('git');
    if (ia) lista.push(ia.ok ? {ok:true, t:'IA conectada', d: r.simulado ? 'IA simulada · sin consumo de tokens' : 'Proveedor configurado'}
                             : {ok:false, t:'Conecta tu proveedor de IA', d:ia.mensaje, a:'Configurar IA'});
    if (motor) lista.push(motor.ok ? {ok:true, t:'Motor activo', d:'Entorno aislado · sin internet'}
                         : motor.opcional ? {ok:true, t:'Motor opcional', d:'No se usa con la IA simulada'}
                         : {ok:false, pausa:true, t:'Inicia el motor', d:motor.mensaje, a:'Ir al motor'});
    if (conf && !conf.ok) lista.push({ok:false, t:'Revisa la configuración', d:conf.mensaje, a:'Abrir Configuración'});
    if (git && !git.ok) lista.push({ok:false, t:'Git no disponible', d:git.mensaje, a:'Abrir Configuración'});
  }
  const exp = seleccionExplorar(), enExplorar = exp.fns.length + exp.endpoints.length;
  if (!enExplorar) lista.push({ok:false, t:'Elige qué probar', d:'No hay funciones ni endpoints seleccionados.', a:'Ir a Explorar', explorar:true});
  else if (!algunTipoElegido()) lista.push({ok:false, t:'Elige un tipo de prueba', d:'Marca Unitarias, Endpoints API o ambas.', tipos:true});
  else if (!total) lista.push({ok:false, t:'Elige qué probar', d:'El tipo de prueba elegido no tiene nada seleccionado.', a:'Ir a Explorar', explorar:true});
  else lista.push({ok:true, t:'Selección válida', d:`${total} ${total === 1 ? 'función o endpoint' : 'funciones y endpoints'}`});
  if (reused) lista.push({ok:true, t:'Trabajo reutilizable', d:`${reused} sin cambios desde la última vez`});
  return lista;
}
function renderComprobaciones(lista){
  const pendientes = lista.filter(c => c.ok === false).length;
  const ico = c => c.ok === null ? ICO_GIRANDO : c.ok ? ICO_OK : c.pausa ? ICO_PAUSA_PREP : ICO_ERROR;
  const clase = c => c.ok === null ? 'progreso' : c.ok ? 'exito' : c.pausa ? 'aviso' : 'bug';
  $('prepComprobaciones').innerHTML = `<h2>${pendientes ? 'Comprobaciones previas' : 'Todo listo para empezar'}</h2>
    ${pendientes ? `<span class="np-chip np-chip-aviso">${ICO_AVISO_CLON}${pendientes} ${pendientes === 1 ? 'pendiente' : 'pendientes'} de resolver</span>`
                 : `<span class="np-chip np-chip-exito">${ICO_OK}Comprobaciones completas</span>`}
    <ul class="prep-checks">${lista.map(c => `<li class="prep-check-${clase(c)}">
      <span class="prep-check-ico">${ico(c)}</span>
      <div><b>${escHtml(c.t)}</b><span class="prep-desc">${escHtml(c.d || '')}</span>
        ${c.a ? `<button type="button" class="ini-enlace prep-enlace" onclick="${c.explorar ? "go('preview')" : "go('config')"}">${c.a}</button>` : ''}</div>
    </li>`).join('')}</ul>`;
  return pendientes;
}

/* ---------- Límites de la corrida / Inicio no disponible ---------- */
// Intentos y tiempo máximo vigentes (los carga Configuración con obtener_limites).
function textoLimites(){
  const lim = typeof LIMITES !== 'undefined' ? LIMITES : {max_intentos: 3, timeout_s: 120};
  const n = lim.max_intentos;
  const tok = lim.max_tokens_por_corrida ? ` · presupuesto máx. ${Number(lim.max_tokens_por_corrida).toLocaleString('es-PE')} tokens` : '';
  return `Hasta ${n} ${n === 1 ? 'intento' : 'intentos'} por función · tiempo máximo ${lim.timeout_s} s por prueba${tok}`;
}
function renderDetallesCorrida(e, bloqueado, prioritarias, epsPrioritarios = 0){
  const {p, reused, tok} = e;
  if (bloqueado) {
    $('prepLimites').innerHTML = `<h2>Inicio no disponible</h2>
      <button type="button" class="ini-btn" disabled>${ICO_CANDADO}Iniciar prueba</button>
      <p class="np-meta">Se habilitará cuando todo esté listo. No perderás tus opciones.</p>`;
    return;
  }
  const filas = [
    textoLimites(),
    `Uso de IA estimado: <b>${usoIA(tok)}</b>${tok ? ` · ~${tok.toLocaleString('es-PE')} tokens` : ''}`,
    `Duración aproximada: <b>${p.duracion}</b> · ~${e.time} min`,
    reused ? `${reused} sin cambios: se reutiliza el trabajo anterior.` : '',
    e.inferidas ? `Contratos inferidos: ${e.inferidas} ${e.inferidas === 1 ? 'función sin docstring' : 'funciones sin docstring'} (~${e.tokInferidas.toLocaleString('es-PE')} tokens incluidos). Son pruebas de regresión, sin contrato documentado${REVISAR_INFERIDOS ? '; podrás revisarlas antes de generar' : ''}.` : '',
    profile==='humo' ? 'Revisión rápida: un caso normal por función o endpoint. No se exige cubrir las ramas.' : '',
    profile==='deep' ? `Análisis a fondo en ${textoPrioritarias(prioritarias - epsPrioritarios, epsPrioritarios)}: comprueba con mutación si las pruebas detectan errores. No usa tokens, pero tarda más.` : '',
    profile==='reg' ? 'Solo se vuelven a correr pruebas guardadas: no se usa IA.' : '',
    profile==='reg_deep' ? 'Se vuelven a correr las pruebas guardadas y se mide con mutación la fortaleza de las críticas. No se usa IA, pero puede tardar más.' : '',
    profile!=='reg' && profile!=='reg_deep' ? 'Los tokens se mostrarán en vivo y por función.' : '',
  ];
  $('prepLimites').innerHTML = `<h2>Límites de esta corrida</h2>
    <div class="prep-limites" id="cfgDetalles">${filas.filter(Boolean).map(f => `<p>${f}</p>`).join('')}</div>
    <button type="button" class="ini-enlace prep-enlace" onclick="go('config')">Ajustar en Configuración</button>`;
}

// Si lo único que falta son los tipos de prueba de esta pantalla (issue 266).
function destinoBloqueoPrevio(lista){
  const pend = lista.filter(c => c.ok === false);
  return pend.length && pend.every(c => c.tipos) ? 'tipos' : null;
}

// Botón principal: inicia la corrida si todo está listo; si no, lleva a resolver lo pendiente.
let destinoBloqueo = null;
const NUMEROS = ['', 'una', 'dos', 'tres', 'cuatro', 'cinco', 'seis'];
function accionPrincipalPreparar(){
  if (destinoBloqueo === 'tipos') {
    const primera = document.querySelector('#prepTipos input:not(:disabled)');
    if (primera) { primera.scrollIntoView({block:'center', behavior:'smooth'}); primera.focus(); }
    return;
  }
  if (destinoBloqueo) { go(destinoBloqueo); return; }
  startMonitor();
}

function calc(){
  renderCompatibilidadPruebas();
  cargarReglasArquitectura();
  if (eleccionPruebas.modo === 'repetir' && !HAS_PRIOR_RUN) eleccionPruebas.modo = 'nuevas';
  // La columna Profundizar de Explorar solo se ve con «Análisis a fondo de críticas».
  if (typeof mostrarProfundizar === 'function') mostrarProfundizar(eleccionPruebas.modo === 'fondo');
  // #74: los endpoints marcados también cuentan como críticos.
  const estStd = estFor('std');
  const epsPrioritarios = estStd.endpoints.filter(e=>e.crit).length;
  const prioritarias = estStd.fns.filter(f=>f.crit).length + epsPrioritarios;
  const repetibles = criticasRepetibles();
  if (!repetibles && eleccionPruebas.profundizarRepetir) eleccionPruebas = {...eleccionPruebas, profundizarRepetir:false};
  profile = perfilDeEleccion(eleccionPruebas, prioritarias, repetibles);
  const e = estFor(profile==='reg_deep' ? 'reg' : profile), {fns, endpoints, total, tok, reused} = e;
  runEstimate = {tok};
  const exp = seleccionExplorar();   // el pie de Explorar cuenta su selección, sin los tipos de Preparar
  renderPieVistaPrevia(exp.fns, exp.fns.filter(f=>!f.doc).length, exp.endpoints);

  renderModosPreparar(repetibles);
  renderTiposPrueba();
  renderCriticas();
  aplicarCaja();   // issue 246: las pestañas por tipo de caja solo muestran u ocultan
  const lista = comprobacionesPrevias(total, reused);
  const pendientes = renderComprobaciones(lista);
  const verificando = lista.some(c => c.ok === null);
  const bloqueado = !verificando && (!entornoListo || !total || pendientes > 0);

  // Cabecera: título, resumen y botón principal según el estado.
  const resumen = `${total} ${total === 1 ? 'seleccionada' : 'seleccionadas'} · ${fns.length} ${fns.length === 1 ? 'función' : 'funciones'} y ${endpoints.length} ${endpoints.length === 1 ? 'endpoint' : 'endpoints'} · ${PROYECTO_NOMBRE_LENGUAJE}`;
  $('prepSub').textContent = bloqueado ? 'Resuelve estos puntos antes de empezar.' : resumen;
  $('prepTitulo').textContent = verificando ? 'Comprobando tu entorno…'
    : !bloqueado ? 'Prepara una corrida fiable'
    : destinoBloqueoPrevio(lista) === 'tipos' ? 'Elige qué tipos de prueba hacer'   // issue 266: dice qué falta, no «una comprobación»
    : pendientes <= 1 ? 'Falta una comprobación' : `Faltan ${NUMEROS[pendientes] || pendientes} comprobaciones`;
  // El botón principal lleva a resolver lo pendiente: Explorar, los tipos de esta pantalla o Configuración.
  const pend = lista.filter(c => c.ok === false);
  destinoBloqueo = !bloqueado ? null
    : pend.length && pend.every(c => c.explorar) ? 'preview'
    : pend.length && pend.every(c => c.tipos) ? 'tipos'
    : 'config';
  $('toPlanIco').innerHTML = bloqueado ? ICO_AJUSTES : ICO_INICIAR;
  $('toPlanTxt').textContent = !bloqueado ? 'Iniciar prueba'
    : {preview:'Volver a Explorar', tipos:'Elegir tipo de prueba', config:'Resolver en Configuración'}[destinoBloqueo];
  $('toPlan').disabled = verificando;
  const problemas = lista.filter(c => c.ok === false).map(c => c.t.toLowerCase());
  $('prepBloqueo').classList.toggle('np-aviso-aviso', bloqueado);
  $('prepBloqueo').classList.toggle('np-aviso-info', !bloqueado);
  $('prepBloqueoTitulo').textContent = bloqueado ? 'Todavía no podemos iniciar la prueba' : 'Configuración lista';
  $('prepBloqueoTxt').textContent = bloqueado
    ? (problemas.length ? `Falta: ${problemas.join(', ')}.` : entornoMotivo)
    : 'La selección de objetivos se conserva en este proyecto. Puedes ajustar las opciones o iniciar la corrida.';

  renderDetallesCorrida(e, bloqueado, prioritarias, epsPrioritarios);
}

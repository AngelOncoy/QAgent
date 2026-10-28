// exportar.js — pantalla «Exportar informe» («Comparte la evidencia»): formato, qué incluir y dónde guardarlo
// HTML del componente (se monta en el marcador data-componente="exportar/exportar" de index.html)
// El informe lo genera Python (DesktopAPI.exportar_informe) a partir de la corrida que se ve en Resultados.
// Los íconos compartidos (ICO_*) vienen de inicio/modal-abrir.js y ejecucion/ejecucion.js.
const ICO_DOCUMENTO = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/></svg>';

registrarComponente('exportar/exportar', `<!-- ===== EXPORTAR INFORME ===== -->
<section id="s-export" class="hide" style="display:flex;flex-direction:column;flex:1;min-height:0">
  <header class="ini-barra">
    <nav class="ini-migas" aria-label="Ubicación"><span class="repoName"></span><span aria-hidden="true">/</span><span aria-current="page">Exportar informe</span></nav>
    <span class="ini-confianza">${ICO_ESCUDO}Tu proyecto permanece en tu equipo</span>
  </header>
  <div class="scroll"><div class="page xpo">

    <div class="np-cabecera">
      <div>
        <h1 class="ini-titulo">Comparte la evidencia</h1>
        <p class="np-subtitulo" id="xpoSub"></p>
      </div>
      <div class="xpo-acciones">
        <button type="button" class="ini-btn" onclick="go('exec')">${ICO_VOLVER}Volver a resultados</button>
        <button type="button" class="ini-btn ini-btn-principal" id="xpoExportar" onclick="doExport()">${ICO_DESCARGAR}<span>Exportar informe</span></button>
      </div>
    </div>

    <div class="np-rejilla xpo-rejilla">
      <div class="np-columna">
        <section class="np-tarjeta" aria-labelledby="xpoFormatoTitulo">
          <h2 id="xpoFormatoTitulo">Formato del informe</h2>
          <div class="xpo-formatos" id="xpoFormatos" role="radiogroup" aria-labelledby="xpoFormatoTitulo"></div>
        </section>

        <section class="np-tarjeta" aria-labelledby="xpoIncluirTitulo">
          <h2 id="xpoIncluirTitulo">Qué incluir</h2>
          <div class="xpo-incluir">
            <label class="prep-casilla xpo-fijo" title="El resumen va siempre"><input type="checkbox" class="exp-caja" checked disabled><span><b>Resumen, metas y prioridades</b></span></label>
            <label class="prep-casilla"><input type="checkbox" class="exp-caja" id="expDetail" checked onchange="renderExport()"><span><b>Resultados por función</b></span></label>
            <label class="prep-casilla"><input type="checkbox" class="exp-caja" id="expCode" checked onchange="renderExport()"><span><b>Pruebas generadas</b></span></label>
            <label class="prep-casilla"><input type="checkbox" class="exp-caja" id="expContract" checked onchange="renderExport()"><span><b>Casos esperados y ejecutados</b></span></label>
            <label class="prep-casilla"><input type="checkbox" class="exp-caja" id="expTrace" onchange="renderExport()"><span><b>Detalle técnico completo</b><span class="prep-desc">Salida de las pruebas y datos del entorno aislado</span></span></label>
          </div>
          <p class="np-meta">El informe no incluye la clave del proveedor de IA ni archivos privados del proyecto.</p>
        </section>

        <section class="np-tarjeta" aria-labelledby="xpoUbicacionTitulo">
          <h2 id="xpoUbicacionTitulo">Ubicación elegida</h2>
          <div class="xpo-campo">
            <span class="xpo-etiqueta" id="xpoCarpetaEtq">Guardar informe en</span>
            <div class="xpo-ruta">
              <span class="xpo-ruta-texto" id="expPath" aria-labelledby="xpoCarpetaEtq"></span>
              <button type="button" class="xpo-ruta-btn" id="expChangeBtn" onclick="cambiarCarpetaExportar()" title="Elegir otra carpeta" aria-label="Elegir otra carpeta">${ICO_CARPETA}</button>
            </div>
            <button type="button" class="ini-enlace xpo-restaurar hide" id="xpoRestaurar" onclick="restaurarCarpetaExportar()">Usar la carpeta de resultados de la corrida</button>
          </div>
          <div class="xpo-campo">
            <span class="xpo-etiqueta" id="xpoNombreEtq">Nombre del archivo</span>
            <div class="xpo-ruta"><span class="xpo-ruta-texto np-mono" id="expName" aria-labelledby="xpoNombreEtq"></span><span class="xpo-ruta-ico">${ICO_DOCUMENTO}</span></div>
          </div>
        </section>
      </div>

      <div class="np-columna">
        <section class="np-tarjeta" aria-labelledby="xpoContieneTitulo">
          <h2 id="xpoContieneTitulo">Este informe contiene</h2>
          <div id="xpoContiene" class="xpo-contiene"></div>
        </section>
        <section class="np-tarjeta hide" id="xpoHecho" aria-live="polite"></section>
      </div>
    </div>

    <div class="np-aviso xpo-aviso-exito hide" id="xpoAviso" role="status"></div>
  </div></div>
</section>
`);

/* ---------------- Estado de la pantalla ---------------- */
const FORMATOS_EXPORTAR = [
  {f:'html', t:'HTML interactivo', d:'Filtros y navegación'},
  {f:'pdf',  t:'PDF',              d:'Documento para compartir'},
  {f:'md',   t:'Markdown',         d:'Texto para documentación'},
  {f:'json', t:'Datos JSON',       d:'Resultados estructurados'},
];
const NOMBRE_FORMATO = Object.fromEntries(FORMATOS_EXPORTAR.map(x => [x.f, x.t]));
let expFmt = 'pdf';
let expCustomDir = null;       // carpeta elegida con el diálogo nativo; null = carpeta de la corrida
let expCarpetaCorrida = '';    // ruta real de la carpeta por defecto (solo para el título emergente)
let expHecho = null;           // última exportación: {formato, nombre, ruta, carpetaCorrida, demo}

function runIdExportar(){
  return (typeof reporteReal !== 'undefined' && reporteReal && reporteReal.run_id) ? reporteReal.run_id
    : (typeof ejecucionReal !== 'undefined' && ejecucionReal && ejecucionReal.run_id) ? ejecucionReal.run_id : RUN_ID;
}

function proyectoBaseExportar(){
  if (typeof reporteReal !== 'undefined' && reporteReal && reporteReal.proyecto) return reporteReal.proyecto;
  return projectPath;
}

function nombreArchivoExportar(f){
  const id = runIdExportar();
  return {pdf:`informe_${id}.pdf`, md:`informe_${id}.md`, json:`results_${id}.json`, html:`informe_${id}.html`}[f] || `informe_${id}.pdf`;
}

function opcionesExportar(){
  return {
    detalle: $('expDetail').checked,
    trazas: $('expTrace').checked,
    codigo: $('expCode').checked,
    contratos: $('expContract').checked,
  };
}

// Desde Resultados («Exportar informe»): abre la pantalla con la corrida que se está viendo.
async function openExport(){
  expCustomDir = null;
  expHecho = null;
  expCarpetaCorrida = '';
  go('export');
  const api = window.pywebview && window.pywebview.api;
  if (api && api.carpeta_corrida) {
    try {
      expCarpetaCorrida = (await api.carpeta_corrida(proyectoBaseExportar(), runIdExportar())) || '';
      renderExport();
    } catch (_) {}
  }
}

function setFmt(f){
  expFmt = f;
  renderExport();
}

async function cambiarCarpetaExportar(){
  const api = window.pywebview && window.pywebview.api;
  if (api && api.select_folder) {
    try {
      const carpeta = await api.select_folder();
      if (!carpeta) return;
      expCustomDir = carpeta;
      renderExport();
    } catch (err) {
      toastError('No se pudo seleccionar la carpeta: ' + escHtml(String(err)));
    }
    return;
  }
  toast('En la aplicación de escritorio se abre el diálogo para elegir la carpeta.');
}

function restaurarCarpetaExportar(){
  expCustomDir = null;
  renderExport();
}

async function abrirCarpetaCorrida(){
  const api = window.pywebview && window.pywebview.api;
  if (api && api.abrir_carpeta_corrida) {
    try {
      const r = await api.abrir_carpeta_corrida(proyectoBaseExportar(), runIdExportar());
      if (!r || !r.ok) toastError(escHtml((r && r.motivo) || 'No se pudo abrir la carpeta de resultados.'));
    } catch (err) {
      toastError('No se pudo abrir la carpeta: ' + escHtml(String(err)));
    }
    return;
  }
  toast('En la aplicación de escritorio se abre la carpeta de resultados de la corrida.');
}

/* ---------------- Exportar ---------------- */
async function doExport(){
  const nombre = nombreArchivoExportar(expFmt);
  const api = window.pywebview && window.pywebview.api;
  if (api && api.exportar_informe) {
    const btn = $('xpoExportar');
    btn.disabled = true;
    try {
      const r = await api.exportar_informe(
        proyectoBaseExportar(),
        runIdExportar(),
        expFmt,
        opcionesExportar(),
        expCustomDir
      );
      if (!r || !r.ok) {
        toastError(escHtml((r && r.motivo) || 'No se pudo exportar el informe.'));
        return;
      }
      expHecho = {formato: expFmt, nombre: r.nombre || nombre, ruta: r.ruta, carpetaCorrida: !expCustomDir, demo: false};
      toast(`Informe guardado en <span class="mono">${escHtml(r.ruta)}</span>`);
    } catch (err) {
      toastError('Error al exportar el informe: ' + escHtml(String(err)));
      return;
    } finally {
      btn.disabled = false;
      renderExport();
    }
    return;
  }
  // Demostración en el navegador: no hay Python que genere el archivo.
  expHecho = {formato: expFmt, nombre, ruta: nombre, carpetaCorrida: !expCustomDir, demo: true};
  renderExport();
}

/* ---------------- Renderizado ---------------- */
function renderExport(){
  const v = typeof ejecucionReal !== 'undefined' ? ejecucionReal : null;
  // issue 139: en la app, sin corrida no hay nada que exportar; la demo es solo del navegador.
  const todos = v ? elementosReales(v) : (enAppEscritorio() ? [] : elementosDemo());
  const n = k => todos.filter(e => e.bandeja === k).length;
  const total = todos.length, pasaron = n('paso'), bugs = n('bug');
  const proyecto = document.querySelector('#s-export .repoName') ? document.querySelector('#s-export .repoName').textContent : '';
  const fecha = v && v.fecha ? new Date(v.fecha).toLocaleString('es-PE', {day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'}) : '';
  $('xpoSub').textContent = [proyecto, fecha ? 'Corrida del ' + fecha : 'Última corrida', 'Python'].filter(Boolean).join(' · ');

  // Formato: cuatro tarjetas tipo radio.
  $('xpoFormatos').innerHTML = FORMATOS_EXPORTAR.map(x => `
    <button type="button" class="xpo-formato ${expFmt === x.f ? 'on' : ''}" data-f="${x.f}" role="radio" aria-checked="${expFmt === x.f}" onclick="setFmt('${x.f}')">
      <span class="prep-radio" aria-hidden="true"></span><b>${x.t}</b><span class="prep-desc">${x.d}</span>
    </button>`).join('');
  // En JSON van los datos; el código y las trazas solo si se marcan.
  const detalle = $('expDetail').checked;
  ['expCode', 'expContract', 'expTrace'].forEach(id => {
    $(id).disabled = !detalle;
    $(id).closest('label').classList.toggle('dis', !detalle);
  });

  // Ubicación: la carpeta de resultados de la corrida o la que se eligió.
  const ruta = $('expPath');
  ruta.textContent = expCustomDir ? String(expCustomDir).replace(/[\\/]+$/, '') : 'Carpeta de resultados de la corrida';
  ruta.title = expCustomDir ? String(expCustomDir) : expCarpetaCorrida;
  $('xpoRestaurar').classList.toggle('hide', !expCustomDir);
  $('expName').textContent = nombreArchivoExportar(expFmt);

  // Resumen de lo que lleva el informe (nunca costos).
  const k = v ? v.indicadores : null;
  const cobertura = k ? k.cobertura.lineas : (total ? todos.reduce((s, e) => s + (Number(e.cobLineas) || 0), 0) / total : null);
  const tokens = k ? k.costo.tokens_total : null;
  // Mismo criterio que el título de Resultados (estadoGeneral, en ejecucion.js).
  const estado = estadoGeneral(todos, v);
  const icoChip = {bug: ICO_ERROR, aviso: ICO_AVISO_CLON, exito: ICO_OK}[estado.tipo];
  const chip = `<span class="np-chip np-chip-${estado.tipo}">${icoChip}${escHtml(estado.corto)}</span>`;
  const resumen = BANDEJAS.map(b => [n(b.k), b.t.toLowerCase()]).filter(([c]) => c).map(([c, t]) => `${c} ${t}`).join(' · ');
  $('xpoContiene').innerHTML = `${chip}
    <b class="xpo-proyecto">${escHtml(proyecto || 'Proyecto')}</b>
    ${fecha ? `<span class="np-meta">${escHtml(fecha)}</span>` : ''}
    <dl class="xpo-cifras">
      <div><dt>Pasaron</dt><dd>${pasaron} / ${total}</dd></div>
      <div><dt>Funciones y endpoints</dt><dd>${total}</dd></div>
      <div><dt title="Porcentaje de líneas del código que ejecutaron las pruebas">Cobertura ⓘ</dt><dd>${pctTexto(cobertura)}</dd></div>
      <div><dt>Tokens de la corrida</dt><dd>${tokens === null || tokens === undefined ? '—' : Number(tokens).toLocaleString('es-PE')}</dd></div>
    </dl>
    <p class="np-meta">${escHtml(resumen)}</p>
    <p class="np-meta">Cobertura: líneas del código que ejecutaron las pruebas.</p>`;

  // Exportación completada: tarjeta lateral, aviso y el botón principal pasa a «Exportar de nuevo».
  $('xpoExportar').querySelector('span').textContent = expHecho ? 'Exportar de nuevo' : 'Exportar informe';
  $('xpoHecho').classList.toggle('hide', !expHecho);
  $('xpoAviso').classList.toggle('hide', !expHecho);
  if (!expHecho) return;
  const hora = new Date().toLocaleTimeString('es-PE', {hour:'2-digit', minute:'2-digit'});
  $('xpoHecho').innerHTML = `<h2>Exportación completada</h2>
    <div class="xpo-hecho"><span class="xpo-hecho-ico">${ICO_OK}</span><b>${expHecho.demo ? 'Informe listo (demostración)' : 'Informe guardado'}</b></div>
    <span class="np-meta">${NOMBRE_FORMATO[expHecho.formato] || ''} · ${hora}</span>
    ${expHecho.carpetaCorrida ? `<button type="button" class="ini-btn" onclick="abrirCarpetaCorrida()">${ICO_CARPETA}Abrir carpeta de resultados</button>`
      : '<span class="np-meta">La carpeta elegida se abrió al guardar.</span>'}`;
  $('xpoAviso').innerHTML = `${ICO_OK}<div><b>Informe exportado correctamente</b>
    <span>${expHecho.demo ? 'En la aplicación de escritorio, ' + escHtml(expHecho.nombre) + ' se guarda en la ubicación elegida.'
      : '<code class="np-mono">' + escHtml(expHecho.nombre) + '</code> ya está en la ubicación elegida.'}</span></div>`;
}

// modal-revision-inferidos.js — revisión opcional de los contratos inferidos (issue 275, ADR-015)
// Python envía el evento `revision_inferidos` con una propuesta por función sin docstring y la corrida espera;
// aquí la persona acepta o descarta cada una y `responder_revision_inferidos` la reanuda.
// HTML del componente (se monta en el marcador data-componente="revision/modal-revision-inferidos" de index.html)
registrarComponente('revision/modal-revision-inferidos', `<!-- Revisar contratos inferidos -->
<div class="overlay" id="m-revision" onclick="event.stopImmediatePropagation()"><div class="modal">
  <div class="mhead"><span>Revisar contratos inferidos</span></div>
  <div class="mcontent">
    <p class="esp-subtitulo">Estas funciones no tienen docstring. QAgent dedujo lo esperado leyendo su código y su uso, sin ejecutarlo. Acepta las que reflejan lo que quieres; las demás se omiten. Las pruebas aceptadas son de regresión, sin contrato documentado.</p>
    <div id="revLista"></div>
    <div class="api-estado" id="revEstado" role="status" aria-live="polite"></div>
  </div>
  <div class="mfoot"><button class="btn" onclick="marcarRevisionInferidos(false)">Descartar todas</button><button class="btn" onclick="marcarRevisionInferidos(true)">Aceptar todas</button><button class="btn primary" id="revContinuar" onclick="enviarRevisionInferidos()">Continuar</button></div>
</div></div>
`);

// Propuestas recibidas de Python: [{modulo, objetivo, firma, casos:[{id, descripcion, entrada, valor_esperado, excepcion, evidencia}]}]
let REVISION_INFERIDOS = [];

function textoCasoInferido(c){
  const entrada = JSON.stringify(c.entrada ?? {});
  const resultado = 'excepcion' in c ? `lanza ${c.excepcion}` : `devuelve ${JSON.stringify(c.valor_esperado)}`;
  return `${c.descripcion ? c.descripcion + ': ' : ''}con ${entrada} ${resultado}`;
}

function abrirRevisionInferidos(datos){
  REVISION_INFERIDOS = (datos && datos.propuestas) || [];
  $('revLista').innerHTML = REVISION_INFERIDOS.map((p, i) => `<div class="prep-casilla">
      <input type="checkbox" class="exp-caja" id="rev${i}" checked aria-labelledby="revNombre${i}">
      <span><b id="revNombre${i}">${escHtml(p.objetivo)}</b> <span class="np-mono">${escHtml(p.firma || '')}</span>
        <span class="prep-desc">${escHtml(p.modulo)}</span>
        <ul class="esp-lista">${(p.casos || []).map(c => `<li>${escHtml(textoCasoInferido(c))}
          <span class="prep-desc">Se basó en: ${(c.evidencia || []).map(x => `<code>${escHtml(x)}</code>`).join(', ') || '—'}</span></li>`).join('')}</ul>
      </span>
    </div>`).join('');
  $('revEstado').className = 'api-estado'; $('revEstado').textContent = '';
  $('revContinuar').disabled = false;
  openModal('m-revision');
}

function marcarRevisionInferidos(valor){
  REVISION_INFERIDOS.forEach((_, i) => { $('rev' + i).checked = valor; });
}

async function enviarRevisionInferidos(){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.responder_revision_inferidos) return;
  const aceptados = REVISION_INFERIDOS.filter((_, i) => $('rev' + i).checked).map(p => p.objetivo);
  $('revContinuar').disabled = true;
  try {
    const r = await api.responder_revision_inferidos(aceptados);
    if(r && r.ok){ closeModal(); return; }
    $('revEstado').className = 'api-estado err';
    $('revEstado').textContent = (r && r.mensaje) || 'No se pudo enviar la revisión.';
  } catch (err) {
    console.error('Error al enviar la revisión de contratos inferidos:', err);
    $('revEstado').className = 'api-estado err';
    $('revEstado').textContent = 'No se pudo enviar la revisión.';
  }
  $('revContinuar').disabled = false;
}

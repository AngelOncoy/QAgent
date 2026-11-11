// modal-espacio.js — modal «Liberar espacio» de Configuración: lista lo que se borra y lo que se conserva (issue 267)
// La lógica (abrirModalEspacio, confirmarLiberarEspacio…) está en espacio-disco.js.
// HTML del componente (se monta en el marcador data-componente="configuracion/modal-espacio" de index.html)
registrarComponente('configuracion/modal-espacio', `<!-- Confirmar «Liberar espacio» -->
<div class="overlay" id="m-espacio"><div class="modal">
  <div class="mhead"><span>Liberar espacio</span><button class="x" onclick="cerrarModalEspacio()" aria-label="Cerrar">×</button></div>
  <div class="mcontent">
    <p class="esp-subtitulo">Se borrará lo que QAgent puede volver a crear en su próxima corrida:</p>
    <ul class="esp-lista" id="espBorra"></ul>
    <p class="esp-subtitulo">Se conserva:</p>
    <ul class="esp-lista" id="espConserva"></ul>
    <div class="hint warn" id="espCacheAviso" style="margin:0"></div>
    <label class="chk hide" id="espCacheFila"><input type="checkbox" id="espCache"> <span id="espCacheTexto"></span></label>
    <div class="api-estado" id="espEstado" role="status" aria-live="polite"></div>
  </div>
  <div class="mfoot"><button class="btn" id="espCancelar" onclick="cerrarModalEspacio()">Cancelar</button><button class="btn primary" id="espConfirmar" onclick="confirmarLiberarEspacio()">Borrar y liberar</button></div>
</div></div>
`);

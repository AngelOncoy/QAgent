// navegacion.js — navegación entre pantallas y apertura/cierre de modales
/* ---------------- Navegación ---------------- */
function go(v){
  ['welcome','open','clone','preview','tests','monitor','exec','report','history','config'].forEach(s => $('s-'+s).classList.toggle('hide', s!==v));
  $('runTop').classList.toggle('hide', !['monitor','report'].includes(v));   // Pruebas (exec) ya tiene su propia cabecera
  if(v==='exec') renderExec();
  if(v==='report') renderReport();
  if(v==='history') renderHistory();
  if(v==='welcome') cargarRecientes();
  if(v==='config') renderConfig();
  actualizarSidebar(v);
  actualizarPasos(v);
}

/* ---------------- Modales ---------------- */
function openModal(id){ $(id).classList.add('show'); }
function closeModal(){
  document.querySelectorAll('.overlay').forEach(o=>o.classList.remove('show')); }
// Se llama desde main.js cuando todos los modales ya están montados.
function iniciarModales(){
  document.querySelectorAll('.overlay').forEach(o => o.addEventListener('click', e => { if(e.target===o) closeModal(); }));
}


// navegacion.js — navegación entre pantallas y modales genéricos
/* ---------------- Navegación ---------------- */
function go(v){
  ['welcome','preview','tests','monitor','exec','report','history','config'].forEach(s => $('s-'+s).classList.toggle('hide', s!==v));
  $('runTop').classList.toggle('hide', !['monitor','exec','report'].includes(v));
  if(v==='exec') renderExec();
  if(v==='report') renderReport();
  if(v==='history') renderHistory();
  if(v==='welcome') cargarRecientes();
  if(v==='config') renderConfig();
  const home = v==='welcome' || v==='config';
  $('sideHome').classList.toggle('hide', !home);
  $('sideProj').classList.toggle('hide', home);
  document.querySelectorAll('#sideHome nav a').forEach(a => a.classList.toggle('on', a.dataset.h===v));
  document.querySelectorAll('#views a').forEach(a => {
    a.classList.toggle('on', a.dataset.v===v);
    const pill = a.querySelector('.pill');
    if(pill) pill.className = a.dataset.v===v ? 'pill p-green' : 'pill p-grey';
  });
}
document.querySelectorAll('#views a').forEach(a => a.onclick = () => {
  if(a.classList.contains('off')) return;
  if(a.dataset.v==='monitor' && !monitorStarted) return;
  go(a.dataset.v);
});

/* ---------------- Modales ---------------- */
function openModal(id){ $(id).classList.add('show'); }
function closeModal(){ if(clonando) return; // no se cierra a mitad de un clonado
  document.querySelectorAll('.overlay').forEach(o=>o.classList.remove('show')); clearInterval(cloneTimer); resetClone(); }
document.querySelectorAll('.overlay').forEach(o => o.addEventListener('click', e => { if(e.target===o) closeModal(); }));

let pickedFolder = null;
document.querySelectorAll('#fsList div').forEach(d => d.onclick = () => {
  document.querySelectorAll('#fsList div').forEach(x=>x.classList.remove('sel')); d.classList.add('sel');
  pickedFolder = d.dataset.p;
  const bad = pickedFolder==='landing-web';
  $('openHint').textContent = bad ? 'Esta carpeta no contiene archivos .py: PyAgent solo analiza código Python 3.10+.' : 'Carpeta: E:\\Proyectos\\'+pickedFolder;
  $('openHint').className = 'hint' + (bad?' err':'');
  $('openOk').disabled = bad;
});
function confirmOpen(){
  if (realFolder) { confirmOpenReal(); return; }
  closeModal(); loadProject(pickedFolder,'local','E:\\Proyectos\\'+pickedFolder);
}


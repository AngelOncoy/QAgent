// clonar.js — modal de clonar repositorio (HU-02)
/* Clonar repositorio (HU-02): misma validación que pyagent.app.clonador */
const RE_URL_GIT = /^https:\/\/[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+\/[A-Za-z0-9_][A-Za-z0-9._-]*\/[A-Za-z0-9_][A-Za-z0-9._-]*$/;
const RE_RAMA_GIT = /^[A-Za-z0-9_][A-Za-z0-9._\/-]*$/;
const FORMATO_URL = 'https://<sitio>/<usuario>/<repositorio>(.git)';
let dirEditado = false, clonando = false, cloneTimer;
const hayPy = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.clonar_repositorio);
const ramaValida = b => RE_RAMA_GIT.test(b) && !/\.\.|\/\/|\/\.|[\/.]$|\.lock$/.test(b);
const nombreRepo = u => u.split('/').pop().replace(/\.git$/,'');
async function vUrl(){
  const v = $('url').value, b = $('branch').value;
  const ok = RE_URL_GIT.test(v), okB = ramaValida(b);
  $('urlHint').textContent = v && !ok ? 'URL no válida. Formato esperado: ' + FORMATO_URL : 'Repositorio público por HTTPS (GitHub, GitLab, Bitbucket).';
  $('urlHint').className = 'hint' + (v && !ok ? ' err':'');
  $('branchHint').classList.toggle('hide', okB);
  if(ok && !dirEditado){
    if(hayPy()){
      try { const r = await window.pywebview.api.destino_clonado(v); if(r.ok && !dirEditado && $('url').value===v) $('dir').value = r.destino; }
      catch(err){ console.error('Error al calcular el destino del clonado:', err); }
    } else $('dir').value = 'E:\\Proyectos\\' + nombreRepo(v);
  }
  $('cloneOk').disabled = clonando || !ok || !okB || !$('dir').value.trim();
}
function resetClone(){
  if(clonando) return;
  $('cloneForm').classList.remove('hide'); $('cloneProg').classList.add('hide'); $('cloneErr').classList.add('hide');
  $('cloneLog').innerHTML=''; $('cloneBar').style.width='0'; $('cloneTitle').textContent='Clonando…';
  $('cloneCancel').disabled = false; vUrl();
}
function logClone(txt){ const l = $('cloneLog'), d = document.createElement('div'); d.textContent = txt; l.appendChild(d); l.scrollTop = l.scrollHeight; }
function doClone(){
  const url = $('url').value, br = $('branch').value, dir = $('dir').value.trim(), shallow = $('shallow').checked;
  $('cloneForm').classList.add('hide'); $('cloneErr').classList.add('hide'); $('cloneProg').classList.remove('hide'); $('cloneOk').disabled = true;
  $('cloneLog').innerHTML = ''; $('cloneBar').style.width = '0'; $('cloneTitle').textContent = 'Clonando…';
  logClone(`$ git clone ${shallow?'--depth 1 ':''}--branch ${br} ${url} ${dir}`);
  if(hayPy()){
    clonando = true; $('cloneCancel').disabled = true;
    window.pywebview.api.clonar_repositorio(url, br, dir, shallow).catch(err => finClonado({ok:false, error:String(err)}));
    return;
  }
  // Sin pywebview (HTML abierto en el navegador): clonado simulado del demo
  const steps = [`Cloning into '${dir}'...`, 'Receiving objects: 100% (212/212), 88.4 KiB, done.', 'Resolving deltas: 100% (31/31), done.'];
  let i = 0;
  cloneTimer = setInterval(() => {
    logClone(steps[i]); $('cloneBar').style.width = ((i+1)/steps.length*100)+'%'; i++;
    if(i===steps.length){ clearInterval(cloneTimer); finClonado({ok:true, destino:dir}); }
  }, 450);
}
function avanceClonado(d){
  if(typeof d.porcentaje === 'number') $('cloneBar').style.width = d.porcentaje + '%';
  const l = $('cloneLog'), ult = l.lastElementChild;
  // git reescribe la misma línea (\r) mientras avanza: se actualiza en vez de agregar otra
  if(ult && d.linea.includes('%') && ult.textContent.split(':')[0] === d.linea.split(':')[0]) ult.textContent = d.linea;
  else logClone(d.linea);
}
function finClonado(r){
  clonando = false; $('cloneCancel').disabled = false;
  if(!r.ok){
    // Se muestra el motivo junto al formulario para corregir y reintentar
    $('cloneErrTxt').textContent = r.error || 'Error desconocido al clonar.';
    $('cloneErr').classList.remove('hide'); $('cloneForm').classList.remove('hide'); $('cloneProg').classList.add('hide');
    vUrl(); return;
  }
  $('cloneTitle').textContent = 'Listo'; $('cloneBar').style.width = '100%';
  const url = $('url').value, br = $('branch').value;
  setTimeout(() => { closeModal(); loadProject(nombreRepo(url), 'git', url, br, r.destino); toast(`Repositorio clonado en <span class="mono">${r.destino}</span>`); }, 600);
}


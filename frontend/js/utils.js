// utils.js — utilidades compartidas por todos los componentes
const $ = id => document.getElementById(id);
const escHtml = t => String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Avisos emergentes (usan #toast de index.html)
function toast(html, icono = I('checkc','var(--emerald-400)',16), ms = 5200){ const t = $('toast'); t.innerHTML = icono + '<span>' + html + '</span>'; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(()=>t.classList.remove('show'), ms); }
function toastError(html){ toast(html, I('alertc','var(--red-400)',16), 8000); }

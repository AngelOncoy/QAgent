// utils.js — utilidades compartidas por todos los componentes
const $ = id => document.getElementById(id);
const escHtml = t => String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

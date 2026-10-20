// utils.js — utilidades compartidas por todos los componentes
const $ = id => document.getElementById(id);
const escHtml = t => String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Avisos emergentes (usan #toast de index.html)
function toast(html, icono = I('checkc','var(--exito-t)',16), ms = 5200){ const t = $('toast'); t.innerHTML = icono + '<span>' + html + '</span>'; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(()=>t.classList.remove('show'), ms); }
function toastError(html){ toast(html, I('alertc','var(--bug-t)',16), 8000); }
/* Etiqueta «Sin docstring» (issue 114): informa una característica del código, no es un error ni
   cambia la selección. El dato sale del análisis AST de Explorar (MODULES): `doc` es 1 o 0;
   si no se conoce (por ejemplo, un endpoint sin el dato), no se muestra nada: nunca se supone. */
const TIP_SIN_DOCSTRING = {
  funcion: 'Esta función no tiene docstring. Se puede probar igual, pero el valor esperado solo saldrá de su firma y sus tipos: las pruebas tendrán menos información.',
  endpoint: 'Este endpoint no tiene docstring. Se puede probar igual: el valor esperado saldrá de lo declarado en la ruta (response_model, status_code y modelos).',
};
// true si tiene docstring, false si no tiene y null si el análisis no lo informa.
function tieneDocstring(objeto){
  if(!objeto || objeto.doc === null || objeto.doc === undefined) return null;
  return !!objeto.doc;
}
// Busca el objetivo analizado por archivo y nombre (función) u objetivo (endpoint, «GET /ruta»).
function docstringDeObjetivo(modulo, nombre){
  const m = (typeof MODULES !== 'undefined' ? MODULES : []).find(x => !x.error && x.path === modulo);
  if(!m || !nombre) return null;
  const clave = String(nombre).replace(/\(\)$/, '');
  const obj = (m.fns || []).find(f => f.n === clave) || (m.endpoints || []).find(e => e.objetivo === clave);
  return tieneDocstring(obj);
}
// `enfocable: false` dentro de un elemento que ya recibe el foco (una opción de lista).
function etiquetaSinDocstring(tipo = 'funcion', {enfocable = true} = {}){
  const tip = TIP_SIN_DOCSTRING[tipo] || TIP_SIN_DOCSTRING.funcion;
  return `<span class="etq-sin-doc" data-tip="${escHtml(tip)}" ${enfocable ? 'tabindex="0" ' : ''}role="note" aria-label="Sin docstring. ${escHtml(tip)}">Sin docstring</span>`;
}

function download(name, content, type){
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], {type}));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

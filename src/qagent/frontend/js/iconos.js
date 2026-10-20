// iconos.js — catálogo de íconos SVG, utilidades de pintado y escape de HTML
const IC = {
  checkc:'<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>', check:'<path d="m5 12 5 5 9-10"/>', x:'<path d="M6 6l12 12M18 6 6 18"/>',
  xc:'<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  shieldA:'<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="M12 8v5M12 16h.01"/>',
  shieldX:'<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9.5 9.5 5 5M14.5 9.5l-5 5"/>',
  shieldC:'<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9 12 2 2 4-4"/>', shield:'<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/>',
  refresh:'<path d="M20 11a8 8 0 0 0-14-5l-2 2M4 13a8 8 0 0 0 14 5l2-2"/><path d="M4 4v4h4M20 20v-4h-4"/>', clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  merge:'<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="12" r="2"/><path d="M6 8v8M8 6c6 0 8 2 8 6"/>',
  coins:'<circle cx="9" cy="9" r="6"/><path d="M15.5 9.5a6 6 0 1 1-6 6"/>',
  dna:'<path d="M5 3c0 6 14 6 14 12M19 3c0 6-14 6-14 12M5 21c0-3 3-4.5 7-6M19 21c0-3-3-4.5-7-6M8 7h8M8 17h8"/>',
  target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>', warn:'<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  alertc:'<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>', filter:'<path d="M3 5h18l-7 8v6l-4-2v-4z"/>', term:'<path d="m4 7 5 5-5 5M12 19h8"/>',
  code:'<path d="m9 8-4 4 4 4M15 8l4 4-4 4"/>', file:'<path d="M6 3h9l4 4v14H6z"/><path d="m10 12-2 2 2 2M14 12l2 2-2 2"/>',
  chevR:'<path d="m9 6 6 6-6 6"/>', chevD:'<path d="m6 9 6 6 6-6"/>', chevU:'<path d="m6 15 6-6 6 6"/>',
  award:'<circle cx="12" cy="9" r="6"/><path d="m8.5 14-1.5 7 5-3 5 3-1.5-7"/>', bug:'<rect x="8" y="6" width="8" height="14" rx="4"/><path d="M12 6V3M8 11H4M20 11h-4M8 16H4M20 16h-4M9 3l1 3M15 3l-1 3"/>',
  download:'<path d="M12 4v11M7 10l5 5 5-5M4 20h16"/>', folder:'<path d="M3 7h6l2 2h10v10H3z"/>',
};
const I = (k,c='currentColor',sz=14,cls='') => `<svg class="${cls}" width="${sz}" height="${sz}" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${IC[k]}</svg>`;
function paintIcons(root=document){ root.querySelectorAll('.ico[data-i]').forEach(e => e.innerHTML = I(e.dataset.i, e.dataset.c, 15)); }
const esc = t => String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

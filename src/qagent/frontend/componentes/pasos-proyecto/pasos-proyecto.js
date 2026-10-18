// pasos-proyecto.js — pasos de un proyecto abierto: Explorar → Preparar → En curso → Resultados
// HTML del componente (se monta en el marcador data-componente="pasos-proyecto/pasos-proyecto" de index.html)
// Se muestra arriba de las pantallas del proyecto. Un paso bloqueado (clase off/hide) se ve, pero no se puede abrir:
// los demás componentes lo desbloquean con desbloquearVista() a medida que avanza la corrida.
registrarComponente('pasos-proyecto/pasos-proyecto', `<!-- ===== Pasos del proyecto ===== -->
<nav id="views" class="pasos hide" aria-label="Pasos del proyecto">
  <a data-v="preview"><span class="paso-ico"></span><span>Explorar</span></a>
  <a data-v="tests"><span class="paso-ico"></span><span>Preparar</span></a>
  <a data-v="monitor" class="hide off"><span class="paso-ico"></span><span>En curso</span></a>
  <a data-v="exec" class="hide off"><span class="paso-ico"></span><span>Resultados</span></a>
</nav>
`);

const PASOS_PROYECTO = ['preview','tests','monitor','exec'];
// Íconos de estado: pendiente (círculo), actual (círculo con punto) y hecho (círculo con verificación).
const ICO_PASO = {
  pendiente: '<circle cx="12" cy="12" r="8"/>',
  actual:    '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none"/>',
  hecho:     '<circle cx="12" cy="12" r="8"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
};

// Muestra los pasos solo en las pantallas del proyecto y marca el actual. Lo invoca go(v).
function actualizarPasos(v){
  const enProyecto = PASOS_PROYECTO.includes(v);
  $('views').classList.toggle('hide', !enProyecto);
  if(!enProyecto) return;
  colocarPasos(v);
  const actual = PASOS_PROYECTO.indexOf(v);
  document.querySelectorAll('#views a').forEach(a => {
    const i = PASOS_PROYECTO.indexOf(a.dataset.v);
    const bloqueado = a.classList.contains('off') || a.classList.contains('hide');
    const estado = i === actual ? 'actual' : (i < actual && !bloqueado ? 'hecho' : 'pendiente');
    a.classList.toggle('on', i === actual);
    a.classList.toggle('hecho', estado === 'hecho');
    if(i === actual) a.setAttribute('aria-current', 'step'); else a.removeAttribute('aria-current');
    if(bloqueado){ a.setAttribute('aria-disabled', 'true'); a.tabIndex = -1; }
    else { a.removeAttribute('aria-disabled'); a.tabIndex = 0; }
    a.querySelector('.paso-ico').innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">${ICO_PASO[estado]}</svg>`;
  });
}
// Como la maqueta, los pasos van debajo del título de la pantalla (barra → título → pasos).
// Las pantallas aún sin migrar no tienen esa cabecera: ahí quedan arriba, como antes.
function colocarPasos(v){
  const nav = $('views'), pantalla = $('s-' + v);
  const cabecera = pantalla && pantalla.querySelector('.np-cabecera');
  if(cabecera){ if(cabecera.nextElementSibling !== nav) cabecera.after(nav); nav.classList.add('en-pantalla'); }
  else { const main = document.querySelector('main'); if(main.firstElementChild !== nav) main.prepend(nav); nav.classList.remove('en-pantalla'); }
}
function repintarPasos(){
  const visible = PASOS_PROYECTO.find(v => !$('s-'+v).classList.contains('hide'));
  if(visible) actualizarPasos(visible);
}

function desbloquearVista(v){
  document.querySelectorAll(`#views a[data-v="${v}"]`).forEach(a => {
    a.classList.remove('hide', 'off');
  });
  repintarPasos();
}

function desbloquearTodasLasVistas(){
  document.querySelectorAll('#views a').forEach(a => {
    a.classList.remove('hide', 'off');
  });
  repintarPasos();
}

function reiniciarVistasProyecto(){
  document.querySelectorAll('#views a').forEach(a => {
    const v = a.dataset.v;
    if(v === 'preview' || v === 'tests'){
      a.classList.remove('hide', 'off');
    } else {
      a.classList.add('hide', 'off');
    }
  });
  repintarPasos();
}

// Se llama desde main.js cuando el HTML de los pasos ya está montado.
function iniciarPasos(){
  reiniciarVistasProyecto();
  document.querySelectorAll('#views a').forEach(a => {
    a.setAttribute('role', 'link');
    a.onclick = () => {
      if(a.classList.contains('off') || a.classList.contains('hide')) return;
      if(a.dataset.v==='monitor' && !monitorStarted) { startMonitor(); return; }
      go(a.dataset.v);
    };
    a.addEventListener('keydown', e => {
      if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); a.click(); }
    });
  });
}

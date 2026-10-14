// cargador.js — monta los componentes: cada <div data-componente="carpeta/nombre"> de index.html
// se reemplaza por el HTML que ese componente registró con registrarComponente().
const COMPONENTES = {};
function registrarComponente(ruta, html){ COMPONENTES[ruta] = html; }
function montarComponentes(){
  document.querySelectorAll('[data-componente]').forEach(el => {
    const html = COMPONENTES[el.dataset.componente];
    if(html === undefined) throw new Error(`Componente no registrado: ${el.dataset.componente}`);
    el.insertAdjacentHTML('beforebegin', html);
    el.remove();
  });
}

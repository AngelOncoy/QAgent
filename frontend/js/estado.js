// estado.js — estado compartido y datos simulados de demostración
const $ = id => document.getElementById(id);
/* ---------------- Datos simulados del repositorio ---------------- */
let MODULES = [
  {path:'services/pricing.py', sel:true, fns:[
    {n:'calculate_discount', sig:'(cart_total: float, coupon_code: str | None, user_tier: str) -> float', typed:1, doc:1, br:4},
    {n:'apply_coupon', sig:'(total: float, code: str) -> float', typed:1, doc:0, br:2},
    {n:'round_price', sig:'(value: float) -> float', typed:1, doc:1, br:0}]},
  {path:'services/inventory.py', sel:true, fns:[
    {n:'reserve_stock_atomic', sig:'(sku: str, quantity: int, order_id: str, timeout_secs: int) -> bool', typed:1, doc:1, br:4},
    {n:'release_stock', sig:'(sku: str, qty: int) -> None', typed:1, doc:1, br:1},
    {n:'check_low_stock_alerts', sig:'(threshold_ratio: float) -> List[StockAlert]', typed:1, doc:1, br:2},
    {n:'bulk_reserve', sig:'(items)', typed:0, doc:0, br:2},
    {n:'restock', sig:'(sku: str, qty: int) -> int', typed:1, doc:1, br:1}]},
  {path:'services/cart.py', sel:true, fns:[
    {n:'calculate_tax_breakdown', sig:'(subtotal: float, state_code: str, is_exempt: bool) -> TaxReport', typed:1, doc:1, br:5},
    {n:'apply_bulk_promotion', sig:'(items: List[CartItem], category_id: int) -> CartSummary', typed:1, doc:1, br:3},
    {n:'remove_item', sig:'(cart: Cart, sku: str) -> Cart', typed:1, doc:1, br:1},
    {n:'cart_total', sig:'(cart: Cart) -> float', typed:1, doc:1, br:0}]},
  {path:'services/discounts.py', sel:true, fns:[
    {n:'compute_loyalty_multiplier', sig:'(orders_count: int, registered_months: int) -> float', typed:1, doc:1, br:4},
    {n:'is_eligible', sig:'(customer: Customer) -> bool', typed:1, doc:1, br:2}]},
  {path:'services/payments.py', sel:true, fns:[
    {n:'validate_credit_card_token', sig:'(token: str, gateway_id: str) -> GatewayAuthResponse', typed:1, doc:1, br:3},
    {n:'refund_charge_idempotent', sig:'(payment_id: str, amount_cents: int, idempotency_key: str) -> RefundResult', typed:1, doc:1, br:2}]},
  {path:'services/shipping.py', sel:true, fns:[
    {n:'estimate_delivery_window', sig:'(zip_code: str, warehouse_id: str, express: bool) -> DeliveryWindow', typed:1, doc:1, br:3}]},
  {path:'utils/format.py', sel:false, fns:[
    {n:'money', sig:'(value: float) -> str', typed:1, doc:1, br:0},
    {n:'slugify', sig:'(text: str) -> str', typed:1, doc:0, br:1}]},
];
const IN_RUN = ['calculate_discount','reserve_stock_atomic','check_low_stock_alerts','calculate_tax_breakdown','apply_bulk_promotion','compute_loyalty_multiplier','validate_credit_card_token','refund_charge_idempotent','estimate_delivery_window'];
const NOT_CRIT = ['calculate_tax_breakdown','estimate_delivery_window','check_low_stock_alerts'];
MODULES.forEach(m => m.fns.forEach(f => {f.crit = f.br>0 && !NOT_CRIT.includes(f.n); f.inc = IN_RUN.includes(f.n);}));

// Priorizar módulos por funciones con ramas (Criterio 7)
function priorizarModulos(lista) {
  return lista.slice().sort((a, b) => {
    if (a.error && !b.error) return 1;
    if (!a.error && b.error) return -1;
    const rA = (a.fns || []).filter(f => f.br > 0).length;
    const rB = (b.fns || []).filter(f => f.br > 0).length;
    if (rB !== rA) return rB - rA;
    const tA = (a.fns || []).reduce((s, f) => s + (f.br || 0), 0);
    const tB = (b.fns || []).reduce((s, f) => s + (f.br || 0), 0);
    if (tB !== tA) return tB - tA;
    return (a.path || '').localeCompare(b.path || '');
  });
}
MODULES = priorizarModulos(MODULES);

let PROYECTO_RESUMEN = null;
let PROYECTO_ERRORES = [];

function aplicarResumenDemo() {
  const modValidos = MODULES.filter(m => !m.error);
  const fns = modValidos.flatMap(m => m.fns);
  const total = fns.length;
  const sinDoc = fns.filter(f => !f.doc).length;
  const sinTipos = fns.filter(f => !f.typed).length;
  const conAlguna = fns.filter(f => !f.doc || !f.typed).length;
  PROYECTO_RESUMEN = {
    total_modulos: modValidos.length,
    total_funciones_publicas: total,
    total_errores: MODULES.filter(m => m.error).length,
    inconsistencias: {
      sin_docstring: { cantidad: sinDoc, porcentaje: total ? +(sinDoc / total * 100).toFixed(1) : 0 },
      sin_tipos: { cantidad: sinTipos, porcentaje: total ? +(sinTipos / total * 100).toFixed(1) : 0 },
      con_alguna: { cantidad: conAlguna, porcentaje: total ? +(conAlguna / total * 100).toFixed(1) : 0 }
    }
  };
  PROYECTO_ERRORES = MODULES.filter(m => m.error).map(m => m.error);
  actualizarResumenUI(PROYECTO_RESUMEN, PROYECTO_ERRORES);
}

function actualizarResumenUI(resumen, errores = []) {
  if (!resumen) return;
  if ($('resumenModulos')) $('resumenModulos').textContent = resumen.total_modulos ?? 0;
  if ($('resumenFunciones')) $('resumenFunciones').textContent = resumen.total_funciones_publicas ?? 0;
  if ($('resumenErrores')) $('resumenErrores').textContent = resumen.total_errores ?? (errores ? errores.length : 0);
  
  const sd = resumen.inconsistencias?.sin_docstring || { cantidad: 0, porcentaje: 0 };
  const st = resumen.inconsistencias?.sin_tipos || { cantidad: 0, porcentaje: 0 };
  const ca = resumen.inconsistencias?.con_alguna || { cantidad: 0, porcentaje: 0 };
  
  if ($('resumenSinDoc')) {
    $('resumenSinDoc').textContent = `⚠ ${sd.cantidad} sin docstring (${sd.porcentaje}%)`;
    $('resumenSinDoc').className = sd.cantidad > 0 ? 'pill p-amber' : 'pill p-grey';
  }
  if ($('resumenSinTipos')) {
    $('resumenSinTipos').textContent = `${st.cantidad} sin tipos (${st.porcentaje}%)`;
    $('resumenSinTipos').className = st.cantidad > 0 ? 'pill p-amber' : 'pill p-grey';
  }
  if ($('resumenConAlguna')) {
    $('resumenConAlguna').textContent = `${ca.cantidad} con inconsistencias (${ca.porcentaje}%)`;
  }
  if ($('projFnsResumen')) {
    $('projFnsResumen').textContent = `${resumen.total_modulos} módulos .py · ${resumen.total_funciones_publicas} funciones públicas`;
  }
}

function cargarDatosVistaPrevia(res) {
  if (!res || !res.ok) return;
  PROYECTO_RESUMEN = res.resumen;
  PROYECTO_ERRORES = res.errores || [];

  const modulosAST = (res.modulos || []).map(m => {
    const fns = (m.funciones || []).map(f => ({
      n: f.nombre,
      sig: f.firma || '()',
      typed: f.tipada ? 1 : 0,
      doc: f.docstring ? 1 : 0,
      br: f.ramas || 0,
      crit: f.critica_propuesta ?? ((f.ramas || 0) > 0),
      inc: true,
      linea: f.linea
    }));
    return {
      path: m.ruta,
      sel: true,
      fns: fns,
      conRamas: m.funciones_con_ramas ?? fns.filter(f => f.br > 0).length,
      huella: m.huella
    };
  });

  const modulosErr = (res.errores || []).map(e => ({
    path: e.ruta,
    sel: false,
    error: e,
    fns: [],
    conRamas: 0
  }));

  MODULES = [...modulosAST, ...modulosErr];
  actualizarResumenUI(res.resumen, res.errores);
}

const PROFILES = [
  {k:'humo', n:'Humo', d:'1 caso feliz por función: ¿se importa y corre con una entrada válida?', tok:4000, t:0.3, m:['Pass Rate'], pill:'p-grey'},
  {k:'std', n:'Estándar', d:'Casos felices, valores límite y excepciones, derivados del docstring.', tok:12000, t:0.9, m:['Pass Rate','Cobertura','Iteraciones'], pill:'p-blue'},
  {k:'deep', n:'Profundo', d:'Estándar + mutation testing (mutmut) solo sobre funciones críticas.', tok:14000, t:1.2, m:['Todo lo anterior','Mutation Score'], pill:'p-purple'},
  {k:'reg', n:'Regresión', d:'Vuelve a ejecutar las pruebas ya aprobadas y guardadas, sin llamar a ninguna IA. Las funciones cuyo código cambió quedan marcadas para una corrida nueva.', tok:0, t:0.2, m:['Pass Rate','Cobertura vs. anterior'], pill:'p-green'},
];
const HAS_PRIOR_RUN = true; // simula corridas previas de este proyecto (ver Historial)
// Estado de los specs guardados en .pyagent/specs/: 'reuse' = el código no cambió (huella igual), 'stale' = cambió → se regenera
const SPEC_STATUS = {'services/pricing.py':'reuse','services/inventory.py':'reuse','services/payments.py':'reuse','services/shipping.py':'reuse','services/cart.py':'stale','services/discounts.py':'stale'};
const PLANNER_SHARE = 0.28;   // parte del costo por función que corresponde al Planner (se ahorra al reutilizar el spec)
let profile = 'deep';
let runEstimate = {tok:0, pen:0}, projectPath = 'E:\\Proyectos\\ecommerce-core';


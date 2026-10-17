// estado.js — estado compartido y datos simulados de demostración
/* ---------------- Datos simulados del repositorio ---------------- */
let MODULES = [
  {path:'services/pricing.py', sel:true, fns:[
    {n:'calculate_discount', sig:'(cart_total: float, coupon_code: str | None, user_tier: str) -> float', typed:1, doc:1, br:4},
    {n:'apply_coupon', sig:'(total: float, code: str) -> float', typed:1, doc:0, br:2},
    {n:'round_price', sig:'(value: float) -> float', typed:1, doc:1, br:0}],
    endpoints:[
      {objetivo:'GET /precios/{sku}', metodo:'GET', ruta:'/precios/{sku}', resuelta:true, manejador:'obtener_precio', response_model:'PrecioOut', status_code:200, status_code_declarado:true, excepciones_http:[{status_code:404, detalle:'SKU inexistente', linea:12}], dependencias:['get_precio_service']},
      {objetivo:'POST /precios', metodo:'POST', ruta:'/precios', resuelta:true, manejador:'crear_precio', response_model:null, status_code:200, status_code_declarado:false, excepciones_http:[], dependencias:[]}]},
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
    {n:'cart_total', sig:'(cart: Cart) -> float', typed:1, doc:1, br:0}],
    endpoints:[
      {objetivo:'GET /carrito', metodo:'GET', ruta:'/carrito', resuelta:true, manejador:'ver_carrito', response_model:'CartSummary', status_code:200, status_code_declarado:false, excepciones_http:[], dependencias:['usuario_actual']},
      {objetivo:'POST /carrito/items', metodo:'POST', ruta:'/carrito/items', resuelta:true, manejador:'agregar_item', response_model:'CartSummary', status_code:201, status_code_declarado:true, excepciones_http:[{status_code:400, detalle:'Datos inválidos', linea:22},{status_code:409, detalle:'Sin stock', linea:27}], dependencias:['usuario_actual','get_cart_service']},
      {objetivo:'DELETE /carrito/items/{sku}', metodo:'DELETE', ruta:'/carrito/items/{sku}', resuelta:true, manejador:'quitar_item', response_model:null, status_code:204, status_code_declarado:true, excepciones_http:[{status_code:404, detalle:'Ítem inexistente', linea:40}], dependencias:['usuario_actual']}]},
  {path:'services/discounts.py', sel:true, fns:[
    {n:'compute_loyalty_multiplier', sig:'(orders_count: int, registered_months: int) -> float', typed:1, doc:1, br:4},
    {n:'is_eligible', sig:'(customer: Customer) -> bool', typed:1, doc:1, br:2}]},
  {path:'services/payments.py', sel:true, fns:[
    {n:'validate_credit_card_token', sig:'(token: str, gateway_id: str) -> GatewayAuthResponse', typed:1, doc:1, br:3},
    {n:'refund_charge_idempotent', sig:'(payment_id: str, amount_cents: int, idempotency_key: str) -> RefundResult', typed:1, doc:1, br:2}],
    endpoints:[
      {objetivo:'POST /pagos/{id}/reembolso', metodo:'POST', ruta:'/pagos/{id}/reembolso', resuelta:true, manejador:'reembolsar', response_model:'RefundResult', status_code:200, status_code_declarado:true, excepciones_http:[{status_code:402, detalle:'Pago no reembolsable', linea:31}], dependencias:['get_payments_service','usuario_actual']},
      {objetivo:null, metodo:'GET', ruta:null, resuelta:false, manejador:'listar_pagos', response_model:null, status_code:200, status_code_declarado:false, excepciones_http:[], dependencias:[]}]},
  {path:'services/shipping.py', sel:true, fns:[
    {n:'estimate_delivery_window', sig:'(zip_code: str, warehouse_id: str, express: bool) -> DeliveryWindow', typed:1, doc:1, br:3}]},
  {path:'utils/format.py', sel:false, fns:[
    {n:'money', sig:'(value: float) -> str', typed:1, doc:1, br:0},
    {n:'slugify', sig:'(text: str) -> str', typed:1, doc:0, br:1}]},
];
const IN_RUN = ['calculate_discount','reserve_stock_atomic','check_low_stock_alerts','calculate_tax_breakdown','apply_bulk_promotion','compute_loyalty_multiplier','validate_credit_card_token','refund_charge_idempotent','estimate_delivery_window'];
const NOT_CRIT = ['calculate_tax_breakdown','estimate_delivery_window','check_low_stock_alerts'];
MODULES.forEach(m => m.fns.forEach(f => {f.crit = f.br>0 && !NOT_CRIT.includes(f.n); f.inc = IN_RUN.includes(f.n);}));
// Endpoints de demostración (issue #66): solo se incluyen los que tienen ruta resuelta.
MODULES.forEach(m => (m.endpoints || []).forEach(e => { e.inc = e.objetivo !== null && e.objetivo !== ''; }));

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


// Perfiles de análisis (#69): la pantalla muestra Humo y Estándar como tipos de prueba,
// Profundo como la casilla Profundizar dentro de Estándar y Regresión como «Repetir pruebas guardadas».
// `descripcion` se muestra en cada opción; `duracion` (rápida, media o larga), en «Detalles de la corrida».
// Solo Profundo lleva `tipo_caja`: es la única capa de caja blanca (HU-31, ajustada por #69).
const PROFILES = [
  {k:'humo', n:'Humo', duracion:'rápida', descripcion:'Confirma que cada función o endpoint responde con un caso normal. Útil para una primera revisión rápida.', tok:4000, t:0.3},
  {k:'std', n:'Estándar', duracion:'media', descripcion:'Prueba entradas válidas, inválidas y valores límite, y compara con lo que la función o el endpoint debe devolver.', tok:12000, t:0.9},
  {k:'deep', n:'Profundizar', tipo_caja:'blanca', duracion:'larga', descripcion:'Recorre cada decisión y comprueba que las pruebas detectan errores (mutación). Tarda más.', tok:14000, t:1.2},
  {k:'reg', n:'Repetir pruebas guardadas', duracion:'media', descripcion:'Vuelve a ejecutar las pruebas ya aprobadas y guardadas en .qagent/ para confirmar que los cambios recientes no rompieron lo que ya funcionaba.', tok:0, t:0.2},
];
// Texto de la insignia del tipo de caja
const TIPO_CAJA = {blanca:'Caja blanca'};
// #70: Set de "modulo::objetivo" con prueba guardada repetible; null en la demostración.
let PRUEBAS_REPETIBLES = null;
let HAS_PRIOR_RUN = true;   // ¿el proyecto abierto ya tuvo una corrida? (dato real en la app; simulado en la demostración)
// Estado de los specs guardados en .qagent/specs/: 'reuse' = el código no cambió (huella igual), 'stale' = cambió → se regenera
const SPEC_STATUS = {'services/pricing.py':'reuse','services/inventory.py':'reuse','services/payments.py':'reuse','services/shipping.py':'reuse','services/cart.py':'stale','services/discounts.py':'stale'};
let profile = 'deep';
// Elección de la configuración de pruebas (#69): qué hacer, tipo de prueba y si se profundiza.
// `profile` se deriva de ella con perfilDeEleccion() (config-pruebas.js).
let eleccionPruebas = {modo:'nuevas', tipo:'std', profundizar:true};
let runEstimate = {tok:0}, projectPath = 'E:\\Proyectos\\ecommerce-core';


// Versión de QAgent: la entrega Python (la misma de `qagent --version`, sale de pyproject.toml).
// Abierta en el navegador, sin Python, es la demostración: se muestra «demo», nunca un número inventado.
let VERSION_QAGENT = null;
function textoVersion(){ return VERSION_QAGENT ? 'v' + VERSION_QAGENT : 'demo'; }
function cargarVersion(){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.obtener_version) return;
  api.obtener_version().then(v => {
    VERSION_QAGENT = v;
    document.querySelectorAll('.ver').forEach(e => { e.textContent = textoVersion(); });
  });
}
window.addEventListener('pywebviewready', cargarVersion);

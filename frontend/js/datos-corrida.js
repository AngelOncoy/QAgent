// datos-corrida.js — datos únicos de la corrida (alimentan Monitor, Ejecución e Informe), métricas y catálogo de estados
/* ================= DATOS ÚNICOS DE LA CORRIDA (alimentan Monitor, Ejecución y Reporte) ================= */
const RUN_ID = '8841-B', RUN_DATE = '25/09/2026 14:32';
const FX = 3.37;   // tipo de cambio de la carta del proyecto
// Configuración fija definida por el equipo en config.toml (el usuario no la edita). Precios: EJEMPLO, reemplazar por los reales.
const AGENTS_CFG = {
  P:{name:'Planner',   model:'Modelo de contexto amplio', price:5.00, why:'Lee el módulo completo, sus tipos y su documentación para armar el contrato.'},
  G:{name:'Generator', model:'Modelo económico',          price:0.60, why:'Tarea acotada: escribe la prueba a partir del contrato.'},
  R:{name:'Reviewer',  model:'Modelo económico',          price:0.60, why:'Clasifica fallos y valida aserciones; ejecutar las pruebas no usa IA.'},
};
const TOPE_PEN = 5.00, MAX_RETRIES = 3;
const EST_SPLIT = {P:0.28, G:0.52, R:0.20};   // reparto típico por función cuando el Planner sí trabaja
const agentCost = t => (t.P*AGENTS_CFG.P.price + t.G*AGENTS_CFG.G.price + t.R*AGENTS_CFG.R.price)/1e6;   // US$
const META = {pass:[70,80], lines:60, iter:2, ms:60};  // metas de la carta del proyecto
const AGENT_SPLIT = {P:9, G:66, R:25};   // P bajo: 4 de 6 módulos reutilizaron su spec (Planner omitido)

const RUN = [
 {id:'fn_1', module:'services/pricing.py', name:'calculate_discount', methodTag:'AST', critical:true, status:'passed', iterations:1, time:'124ms', tokens:12400,
  lines_cov:100, branch_cov:95, mutation_score:92, badge:'CASO NORMAL & LÍMITE', bv:'blue',
  signature:'def calculate_discount(cart_total: float, coupon_code: Optional[str] = None, user_tier: str = "standard") -> float',
  contract:{funcion:'calculate_discount', firma:'(cart_total: float, coupon_code: Optional[str] = None, user_tier: str = "standard") -> float', tipos:{cart_total:'float (>0)', coupon_code:'str | None', user_tier:'Literal["standard", "gold", "vip"]'}, docstring:'Calcula el descuento aplicable considerando cupón estacional y nivel de lealtad.', comportamiento_esperado:['Si cart_total < 0 debe lanzar ValueError("El total no puede ser negativo")','VIP recibe un 15% automático sobre el remanente post-cupón','Cupón "SUMMER20" descuenta 20% flat topeado a $50','Tope estricto: la deducción acumulada total no puede exceder el 40%'], contexto_acotado:['config.DISCOUNT_LIMIT = 0.40','services.users.TierManager']},
  logs:['$ docker run --rm --network none pyagent-sandbox:base pytest tests/test_pricing.py -v --cov --cov-branch','[sandbox-init] cgroup v2 (cpu=1, mem=256mb) · network=none','test_calculate_discount_normal_vip PASSED','test_calculate_discount_coupon_cap PASSED','test_calculate_discount_negative_raises PASSED','Coverage: lines=100% branches=95% | mutmut: 23/25 mutantes eliminados (92%)'],
  cmp:{original:'assert res == 15.0   # VIP 15%\nassert res == 50.0   # tope del cupón\npytest.raises(ValueError)', modified:'assert res == 15.0\nassert res == 50.0\npytest.raises(ValueError)', state:'clean'},
  diag:null, trace:null,
  code:`import pytest
from services.pricing import calculate_discount

def test_calculate_discount_normal_vip():
    # Arrange & Act: Usuario VIP sin cupón
    total = 100.0
    res = calculate_discount(total, coupon_code=None, user_tier="vip")
    # Assert
    assert res == 15.0  # 15% directo sobre el monto

def test_calculate_discount_coupon_cap():
    # Cupón SUMMER20 con límite superior de $50
    total = 500.0
    res = calculate_discount(total, coupon_code="SUMMER20", user_tier="standard")
    assert res == 50.0  # 20% de 500 = 100 -> fijado al cap de 50

def test_calculate_discount_negative_raises():
    # Caso borde: Entrada con saldo negativo debe rechazar
    with pytest.raises(ValueError, match="El total no puede ser negativo"):
        calculate_discount(-10.0)`},
 {id:'fn_3', module:'services/inventory.py', name:'reserve_stock_atomic', methodTag:'AUDIT', critical:true, status:'rejected_laundering', iterations:3, time:'240ms', tokens:21800,
  lines_cov:68, branch_cov:55, mutation_score:30, badge:'CASO CONCURRENTE & LÍMITE', bv:'rose',
  signature:'def reserve_stock_atomic(sku: str, quantity: int, order_id: str, timeout_secs: int = 300) -> bool',
  contract:{funcion:'reserve_stock_atomic', firma:'(sku: str, quantity: int, order_id: str, timeout_secs: int = 300) -> bool', tipos:{sku:'str', quantity:'int (>0)', order_id:'str', timeout_secs:'int'}, docstring:'Bloquea unidades en Redis mediante un lock distribuido Redlock atómico.', comportamiento_esperado:['Si el stock disponible < quantity, debe arrojar InsufficientStockError','Debe adquirir lock atómico Redlock con TTL especificado','En caso de timeout o concurrencia, liberar lock parcial y retornar False'], contexto_acotado:['redis.asyncio','exceptions.InsufficientStockError','services.distributed_lock']},
  logs:['[sandbox-init] network=none · fixture: fakeredis (mock de Redis en memoria)','Iter 1: test_reserve_stock_insufficient_stock FAILED [lock.is_acquired() is False]','ANALYSIS [Reviewer]: AST diff check triggered on assertions','DIFF: - assert lock.is_acquired() is True  [Iter 1 - FAILED]','DIFF: + assert res is not None            [Iter 2 - WEAKENED]','SECURITY REJECTION: Assertion laundering detected! Generator relaxed assertion to force pass.','Iter 3: misma relajación (hash del diff repetido) -> ciclo detenido','Reviewer Verdict: REJECT_TEST -> requiere revisión humana'],
  cmp:{original:'assert lock.is_acquired() is True\nassert inventory.get_locked_state(sku) == "HELD"', modified:'assert res is not None  # <- Relajación deliberada detectada', state:'relaxed'},
  diag:'Reviewer Security Alert [Iteraciones 2 y 3]: se detectó relajación deliberada de aserciones ("Assertion Laundering"). En la iteración 1 falló "assert lock.is_acquired() is True". En lugar de corregir el fixture del lock, el Generator reemplazó la validación por "assert res is not None". La iteración 3 repitió la misma relajación: se detuvo el ciclo y la prueba queda RECHAZADA para revisión humana.',
  trace:`Reviewer Security Alert [Iteraciones 2 y 3]:
Se detectó relajación deliberada de aserciones ("Assertion Laundering / Assertion Neutralization").
Diff detectado en AST del test:
- Iteración 1: assert lock.is_acquired() is True and inventory.get_locked_state(sku) == "HELD"
+ Iteración 2: assert res is not None  # <-- Generador evadió la aserción estricta del lock
+ Iteración 3: assert res is not None  # <-- misma relajación (hash del diff repetido)

Acción del Reviewer: Rechazo de la prueba. Se conserva la versión de la Iter 1 como referencia y se marca para revisión humana.`,
  code:`# INTENTOS 2 y 3 - RECHAZADOS POR REVIEWER (ASSERTION LAUNDERING)
import pytest
from services.inventory import reserve_stock_atomic

def test_reserve_stock_insufficient_stock():
    # ADVERTENCIA: El Generator eliminó la comprobación del lock para forzar el paso!
    res = reserve_stock_atomic("SKU-998", quantity=1000, order_id="ORD-101")
    # Aserción original requerida (Iter 1): assert lock.is_acquired() is True
    assert res is not None  # <-- INCOMPATIBLE CON CONTRATO: Detectado por Reviewer Anti-Laundering`},
 {id:'fn_4', module:'services/payments.py', name:'validate_credit_card_token', methodTag:'PYTEST', critical:true, status:'stuck', iterations:3, time:'510ms', tokens:27600,
  lines_cov:52, branch_cov:40, mutation_score:25, badge:'CASO DE ERROR (GATEWAY)', bv:'rose',
  signature:'def validate_credit_card_token(token: str, gateway_id: str) -> GatewayAuthResponse',
  contract:{funcion:'validate_credit_card_token', firma:'(token: str, gateway_id: str) -> GatewayAuthResponse', tipos:{token:'str (JWT PCI-DSS format)', gateway_id:'str'}, docstring:'Verifica la validez y firma criptográfica del token ante la pasarela bancaria.', comportamiento_esperado:['Valida regex estricto de token token_pci_\\w{24}','Lanza InvalidTokenSignature si la clave pública expira o falla mTLS','Retorna GatewayAuthResponse con status="AUTHORIZED"'], contexto_acotado:['security.pci_crypto','gateways.stripe','config.MTLS_CERTS']},
  logs:['$ docker run --rm --network none pyagent-sandbox:base pytest tests/test_payments.py -v','Iter 1: ERROR ConnectionRefusedError: 127.0.0.1:8443 (sin red en el sandbox)','Iter 2: ERROR ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]','Iter 3: ERROR ConnectionRefusedError: 127.0.0.1:8443','Max retries exceeded (3/3). Test execution terminated.'],
  cmp:{original:'with pytest.raises(InvalidTokenSignature)', modified:'with pytest.raises(InvalidTokenSignature)', state:'clean'},
  diag:'Estancado tras 3/3 intentos: la función abre una conexión real con la pasarela (puerto 8443) y el sandbox se ejecuta sin red por diseño. En ningún intento el Generator creó un mock de gateways.stripe. Requiere intervención humana: agregar un fixture que simule la pasarela.',
  trace:`SandboxExecutionError [Estancado tras 3/3 intentos]:
ConnectionRefusedError: [Errno 111] Connection refused (127.0.0.1:8443)
Traceback (most recent call last):
  File "tests/test_payments.py", line 9, in test_validate_token_expired
    validate_credit_card_token(token, gateway_id="stripe_v3")
  File "/app/services/payments.py", line 45, in validate_credit_card_token
    sock.connect(("127.0.0.1", 8443))
ConnectionRefusedError: [Errno 111] Connection refused
Estado: la prueba necesita un mock de gateways.stripe; el sandbox no tiene red (aislamiento hermético).`,
  code:`import pytest
from services.payments import validate_credit_card_token
from exceptions import InvalidTokenSignature

def test_validate_token_expired():
    token = "token_pci_expired_0019283921029384"
    # Falló tras 3/3 intentos: la prueba no simula la pasarela y el sandbox no tiene red
    with pytest.raises(InvalidTokenSignature):
        validate_credit_card_token(token, gateway_id="stripe_v3")`},
 {id:'fn_5', module:'services/discounts.py', name:'compute_loyalty_multiplier', methodTag:'AST', critical:true, status:'low_mutation', iterations:1, time:'95ms', tokens:11900,
  lines_cov:98, branch_cov:92, mutation_score:38, badge:'CASO LÍMITE (UMBRALES)', bv:'amber',
  signature:'def compute_loyalty_multiplier(orders_count: int, registered_months: int) -> float',
  contract:{funcion:'compute_loyalty_multiplier', firma:'(orders_count: int, registered_months: int) -> float', tipos:{orders_count:'int (>=0)', registered_months:'int (>=0)'}, docstring:'Calcula el coeficiente multiplicador para puntos de fidelidad según antigüedad y volumen de compras.', comportamiento_esperado:['Si registered_months >= 12 y orders_count >= 5 -> multiplicador exacto 1.5x','Si registered_months >= 6 -> multiplicador exacto 1.2x','En cualquier otro caso retorna 1.0x baseline invariable'], contexto_acotado:['services.loyalty.Rules']},
  logs:['test_compute_loyalty_basic PASSED','Coverage: lines=98% branches=92%','$ mutmut run --paths-to-mutate services/discounts.py  (solo función crítica)','MUTATION WARNING: 5 de 8 mutantes sobrevivieron (score 38%)'],
  cmp:{original:'assert res == 1.5   # contrato: multiplicador exacto 1.5x', modified:'assert res > 1.0', state:'weak'},
  diag:'Brecha cobertura vs. mutantes: cobertura de línea 98% pero Mutation Score 38%. La aserción "assert res > 1.0" no fija el valor exacto que exige el contrato (1.5). El guardrail de reparación no lo detecta porque no hubo reparación: lo detecta mutmut.',
  trace:`Mutation Analysis Warning [Brecha Cobertura vs Mutantes]:
Cobertura de línea: 98% (Alta) | Mutation Score: 38% (3 de 8 mutantes eliminados).
Mutantes sobrevivientes (5), entre ellos:
  - Mutante #1: services/discounts.py:14 (Reemplazo de '>=' por '>') -> Test NO falló en valor de frontera 12 meses.
  - Mutante #2: services/discounts.py:18 (Mutación de constante 1.5 a 1.0) -> Sobrevivió por aserción débil (assert res > 1.0 en lugar de assert res == 1.5).
  - Mutante #3: Negación de branch de antigüedad.
Se solicita al agente Generator generar pruebas de límite estricto.`,
  code:`import pytest
from services.discounts import compute_loyalty_multiplier

def test_compute_loyalty_basic():
    # Cobertura de línea alcanzada pero aserción laxa:
    res = compute_loyalty_multiplier(orders_count=6, registered_months=14)
    # Aserción débil que permite a mutantes sobrevivir (debió ser: assert res == 1.5)
    assert res > 1.0`},
 {id:'fn_2', module:'services/cart.py', name:'apply_bulk_promotion', methodTag:'PYTEST', critical:true, status:'rejected_oracle', iterations:2, time:'188ms', tokens:18200,
  lines_cov:94, branch_cov:88, mutation_score:40, badge:'CASO LÍMITE (3x2)', bv:'amber',
  signature:'def apply_bulk_promotion(items: List[CartItem], category_id: int) -> CartSummary',
  contract:{funcion:'apply_bulk_promotion', firma:'(items: List[CartItem], category_id: int) -> CartSummary', tipos:{items:'List[CartItem]', category_id:'int'}, docstring:'Aplica 3x2 en items de la misma categoría especificada.', comportamiento_esperado:['Agrupa por category_id y descuenta la unidad más barata cada 3 items','Carritos vacíos devuelven CartSummary con discount=0 y items_count=0','No altera precios unitarios de productos fuera de la categoría'], contexto_acotado:['models.CartItem','models.CartSummary']},
  logs:['$ docker run --rm --network none pyagent-sandbox:base pytest tests/test_cart_promo.py -v','Iter 1: test_apply_bulk_promotion_six_items FAILED [expected 20.0, got 10.0]','Iter 2: test_apply_bulk_promotion_six_items PASSED','ORACLE CHECK [Reviewer]: literal 10.0 no es trazable al contrato (esperado 20.0)','Reviewer Verdict: REJECT_TEST -> se reporta POSIBLE DEFECTO en el código fuente'],
  cmp:{original:'assert summary.total_discount == 20.0   # 6 items -> 2 unidades gratis', modified:'assert summary.total_discount == 10.0   # <- copiado del resultado real', state:'oracle'},
  diag:'Oráculo alterado [Iteración 2/3]: el valor esperado 10.0 no proviene del contrato. Según "descuenta la unidad más barata cada 3 items", 6 items de $10 deben dar 20.0. El Generator copió el resultado actual de la función para que la prueba pase. Se rechaza la prueba y se reporta un POSIBLE DEFECTO en services/cart.py::apply_bulk_promotion (solo aplica la promoción al primer grupo de 3).',
  trace:`Oracle Traceability Check [Iteración 2/3]:
- Iteración 1: assert summary.total_discount == 20.0   -> FAILED (la función devolvió 10.0)
+ Iteración 2: assert summary.total_discount == 10.0   -> PASSED
Literal 10.0 sin origen en planner_contract.comportamiento_esperado.
Regla aplicada: el valor esperado solo puede provenir del contrato (firma, tipos, docstring), nunca del resultado de ejecutar el código.

Acción del Reviewer: Rechazo de la prueba y corte del ciclo (reintentar no corrige un defecto del código).
Hallazgo: POSIBLE DEFECTO en services/cart.py::apply_bulk_promotion — la promoción 3x2 solo se aplica al primer grupo.`,
  code:`# INTENTO 2 - RECHAZADO POR REVIEWER (ORÁCULO ALTERADO)
import pytest
from services.cart import apply_bulk_promotion
from models import CartItem

def test_apply_bulk_promotion_six_items():
    # Contrato: "descuenta la unidad más barata cada 3 items" -> 6 items = 2 unidades gratis
    items = [CartItem(id=i, category_id=5, price=10.0) for i in range(6)]
    summary = apply_bulk_promotion(items, category_id=5)
    # Iter 1 esperaba 20.0 (contrato) y falló: la función devolvió 10.0
    assert summary.total_discount == 10.0  # <-- Iter 2: valor copiado del resultado real`},
 {id:'fn_6', module:'services/cart.py', name:'calculate_tax_breakdown', methodTag:'AUDIT', critical:false, status:'passed', iterations:1, time:'110ms', tokens:11600,
  lines_cov:100, branch_cov:100, mutation_score:null, badge:'CASO NORMAL & EXENTO', bv:'blue',
  signature:'def calculate_tax_breakdown(subtotal: float, state_code: str, is_exempt: bool = False) -> TaxReport',
  contract:{funcion:'calculate_tax_breakdown', firma:'(subtotal: float, state_code: str, is_exempt: bool = False) -> TaxReport', tipos:{subtotal:'float', state_code:'str (2 chars)', is_exempt:'bool'}, docstring:'Desglosa impuestos estatales y municipales aplicables.', comportamiento_esperado:['Si is_exempt=True, total_tax siempre es 0.00','Valida código de estado ISO-3166-2','Calcula tasas específicas para NY (8.875%), CA (7.25%), TX (6.25%)'], contexto_acotado:['geo.taxes','models.TaxReport']},
  logs:['test_tax_exempt_customer PASSED [tax=0.00]','test_tax_california_rate PASSED [rate=7.25% exact]','Coverage: lines=100% branches=100%','mutmut: no aplica (función no marcada como crítica)'],
  cmp:{original:'assert rep.total_tax == 0.0\nassert rep.total_tax == 7.25', modified:'assert rep.total_tax == 0.0\nassert rep.total_tax == 7.25', state:'clean'}, diag:null, trace:null,
  code:`import pytest
from services.cart import calculate_tax_breakdown

def test_tax_exempt_customer():
    rep = calculate_tax_breakdown(subtotal=150.0, state_code="CA", is_exempt=True)
    assert rep.total_tax == 0.0
    assert rep.effective_rate == 0.0

def test_tax_california_rate():
    rep = calculate_tax_breakdown(subtotal=100.0, state_code="CA", is_exempt=False)
    assert rep.total_tax == 7.25`},
 {id:'fn_7', module:'services/shipping.py', name:'estimate_delivery_window', methodTag:'AST', critical:false, status:'passed', iterations:1, time:'142ms', tokens:12100,
  lines_cov:96, branch_cov:90, mutation_score:null, badge:'CASOS LÍMITE', bv:'blue',
  signature:'def estimate_delivery_window(zip_code: str, warehouse_id: str, express: bool = False) -> DeliveryWindow',
  contract:{funcion:'estimate_delivery_window', firma:'(zip_code: str, warehouse_id: str, express: bool = False) -> DeliveryWindow', tipos:{zip_code:'str', warehouse_id:'str', express:'bool'}, docstring:'Calcula rango estimado de entrega en días hábiles.', comportamiento_esperado:['Excluye fines de semana y feriados en el cálculo','Modo express garantiza entrega en 24-48 horas dentro del radio','Lanza UnsupportedZoneError para códigos postales fuera de cobertura'], contexto_acotado:['logistics.carriers','models.DeliveryWindow']},
  logs:['test_estimate_delivery_express PASSED','Coverage: lines=96% branches=90%','mutmut: no aplica (función no marcada como crítica)'],
  cmp:{original:'assert win.max_days <= 2\nassert win.is_guaranteed is True', modified:'assert win.max_days <= 2\nassert win.is_guaranteed is True', state:'clean'}, diag:null, trace:null,
  code:`import pytest
from services.shipping import estimate_delivery_window

def test_estimate_delivery_express():
    win = estimate_delivery_window("90210", warehouse_id="WH-LA-01", express=True)
    assert win.max_days <= 2
    assert win.is_guaranteed is True`},
 {id:'fn_8', module:'services/payments.py', name:'refund_charge_idempotent', methodTag:'PYTEST', critical:true, status:'passed', iterations:2, time:'290ms', tokens:16300,
  lines_cov:100, branch_cov:94, mutation_score:95, badge:'CASO LÍMITE (IDEMPOTENCIA)', bv:'blue',
  signature:'def refund_charge_idempotent(payment_id: str, amount_cents: int, idempotency_key: str) -> RefundResult',
  contract:{funcion:'refund_charge_idempotent', firma:'(payment_id: str, amount_cents: int, idempotency_key: str) -> RefundResult', tipos:{payment_id:'str', amount_cents:'int (>0)', idempotency_key:'str'}, docstring:'Reembolsa saldo con salvaguarda de idempotencia contra cobros dobles.', comportamiento_esperado:['Rechaza montos <= 0 con InvalidAmountException','Si la clave de idempotencia ya fue procesada, retorna el resultado previo sin re-llamar al procesador','Actualiza el ledger contable atómicamente'], contexto_acotado:['ledger.accounting','gateways.stripe']},
  logs:['Iter 1: ERROR ImportError: cannot import name "RefundResult" (causa: importación)','Iter 2: test_refund_duplicate_idempotency_key_does_not_double_charge PASSED','Idempotency check PASSED: la segunda llamada devolvió el resultado en caché','mutmut: 19 de 20 mutantes eliminados (95%)'],
  cmp:{original:'assert r1.refund_id == r2.refund_id\nassert r2.was_cached is True', modified:'assert r1.refund_id == r2.refund_id\nassert r2.was_cached is True', state:'clean'}, diag:null, trace:null,
  code:`import pytest
from services.payments import refund_charge_idempotent

def test_refund_duplicate_idempotency_key_does_not_double_charge():
    key = "idem_key_unique_8823"
    r1 = refund_charge_idempotent("pay_123", 4500, idempotency_key=key)
    r2 = refund_charge_idempotent("pay_123", 4500, idempotency_key=key)
    assert r1.refund_id == r2.refund_id
    assert r2.was_cached is True`},
 {id:'fn_9', module:'services/inventory.py', name:'check_low_stock_alerts', methodTag:'AUDIT', critical:false, status:'passed', iterations:1, time:'135ms', tokens:10600,
  lines_cov:92, branch_cov:85, mutation_score:null, badge:'LOTE DE ALERTAS', bv:'blue',
  signature:'def check_low_stock_alerts(threshold_ratio: float = 0.15) -> List[StockAlert]',
  contract:{funcion:'check_low_stock_alerts', firma:'(threshold_ratio: float = 0.15) -> List[StockAlert]', tipos:{threshold_ratio:'float (0.01 .. 0.50)'}, docstring:'Escanea el catálogo de existencias y despacha notificaciones para reposición.', comportamiento_esperado:['Filtra productos donde current_stock / safety_stock <= threshold_ratio','Ignora productos marcados como descontinuados'], contexto_acotado:['models.StockAlert','services.notifications']},
  logs:['test_check_low_stock_filters_discontinued PASSED','Coverage: lines=92% branches=85%','mutmut: no aplica (función no marcada como crítica)'],
  cmp:{original:'assert alert.is_discontinued is False\nassert alert.urgency in ["HIGH", "CRITICAL"]', modified:'assert alert.is_discontinued is False\nassert alert.urgency in ["HIGH", "CRITICAL"]', state:'clean'}, diag:null, trace:null,
  code:`import pytest
from services.inventory import check_low_stock_alerts

def test_check_low_stock_filters_discontinued():
    alerts = check_low_stock_alerts(threshold_ratio=0.20)
    for alert in alerts:
        assert alert.is_discontinued is False
        assert alert.urgency in ["HIGH", "CRITICAL"]`},
];
// Los 5 controles se DERIVAN de los datos (así ninguna vista puede contradecir a otra)
RUN.forEach(f => f.checks = {
  syntax: true,
  sandbox: f.status !== 'stuck',
  assertions_intact: !['rejected_laundering','rejected_oracle'].includes(f.status),
  cov_met: f.lines_cov >= 60 && f.branch_cov >= 60,
  ms_met: f.critical ? f.mutation_score >= META.ms : null,
});
const ranOK = f => f.status==='passed' || f.status==='low_mutation';   // la suite corrió sin error
function metrics(){
  const n = RUN.length, ok = RUN.filter(ranOK).length, crit = RUN.filter(f=>f.critical);
  const avg = k => RUN.reduce((s,f)=>s+f[k],0)/n;
  const tokens = RUN.reduce((s,f)=>s+f.tokens,0);
  const agentTok = {P:tokens*AGENT_SPLIT.P/100, G:tokens*AGENT_SPLIT.G/100, R:tokens*AGENT_SPLIT.R/100};
  const agentUsd = {P:agentTok.P*AGENTS_CFG.P.price/1e6, G:agentTok.G*AGENTS_CFG.G.price/1e6, R:agentTok.R*AGENTS_CFG.R.price/1e6};
  const usd = agentUsd.P + agentUsd.G + agentUsd.R;
  return { n, ok, pass: ok/n*100, lines: avg('lines_cov'), branch: avg('branch_cov'), iter: avg('iterations'),
    tokens, usd, pen: usd*FX, agentTok, agentUsd, crit: crit.length, ms: crit.reduce((s,f)=>s+f.mutation_score,0)/crit.length,
    gaps: crit.filter(f => f.lines_cov - f.mutation_score >= 40).length,
    green: RUN.filter(f=>f.status==='passed').length, alerts: RUN.filter(f=>f.status!=='passed').length,
    critical_incidents: RUN.filter(f=>['rejected_laundering','rejected_oracle','stuck'].includes(f.status)).length,
    bugs: RUN.filter(f=>f.status==='rejected_oracle').length };
}
const pct = (v,d=0) => v.toFixed(d) + '%';
const kfmt = t => (t/1000).toFixed(1) + 'k';

/* Estados: un solo catálogo para colores, etiquetas e íconos en todas las vistas */
const ST = {
  passed:{c:'#10b981', exec:['checkc','#34d399','s-pass','check','APROBADO'], rep:'APROBADO', repCls:'rs-ok', repIco:'check', mb:'background:#10b981;color:#020617', filter:'Aprobados'},
  low_mutation:{c:'#f97316', exec:['warn','#fb923c','s-mut','dna','BRECHA MUTACIÓN'], rep:'ALERTA: BRECHA MUTANTES', repCls:'rs-mut', repIco:'dna', mb:'background:#f97316;color:#020617', filter:'Brecha mutación'},
  rejected_oracle:{c:'#d946ef', exec:['bug','#e879f9','s-orc','bug','ORÁCULO ALTERADO'], rep:'RECHAZADO: ORÁCULO ALTERADO', repCls:'rs-orc', repIco:'bug', mb:'background:#d946ef;color:#fff', filter:'Oráculo alterado'},
  rejected_laundering:{c:'#f43f5e', exec:['shieldA','#fb7185','s-rej','shieldX','RECHAZADO REVIEWER'], rep:'RECHAZADO: ASSERTION LAUNDERING', repCls:'rs-rej', repIco:'shieldX', mb:'background:#f43f5e;color:#fff', filter:'Rechazado laundering'},
  stuck:{c:'#f59e0b', exec:['xc','#f43f5e','s-stk','refresh','ESTANCADO (3/3)'], rep:'ESTANCADO (3/3 INTENTOS)', repCls:'rs-stk', repIco:'alertc', mb:'background:#f59e0b;color:#020617', filter:'Estancados 3/3'},
};

function hl(code){
  return code.split('\n').map(line => {
    let com = '', i = -1, q = null;
    for(let k=0;k<line.length;k++){ const ch=line[k]; if(q){ if(ch===q) q=null; } else if(ch==='"'||ch==="'") q=ch; else if(ch==='#'){ i=k; break; } }
    if(i>=0){ com = line.slice(i); line = line.slice(0,i); }
    let h = esc(line)
      .replace(/(")(.*?)\1/g, m => `<span class="syn-str">${m}</span>`)
      .replace(/^(\s*)(@[\w.]+)/, '$1<span class="syn-dec">$2</span>')
      .replace(/\b(import|from|def|with|as|assert|for|in|is|return|True|False|None|not|lambda|class)\b(?![^<]*>)/g, '<span class="syn-kw">$1</span>')
      .replace(/(<span class="syn-kw">def<\/span>\s+)(\w+)/, '$1<span class="syn-fn">$2</span>')
      .replace(/(?<![\w#-])(\d+\.?\d*)(?![^<]*>)/g, '<span class="syn-num">$1</span>');
    return h + (com ? `<span class="syn-com">${esc(com)}</span>` : '');
  }).join('\n');
}


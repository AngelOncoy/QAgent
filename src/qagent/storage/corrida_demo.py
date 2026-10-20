"""Datos simulados de la corrida #8841-B para demostración y exportación en escritorio (HU-22).

Cuando la aplicación de escritorio corre en modo demostración (sin Docker activo),
materializa `.qagent/runs/8841-B/results.json`, `detalle.json` y `run.json` con los
mismos datos que muestra la pantalla para que `exportar_informe` genere archivos reales
(`.pdf`, `.md` y `.json`) a partir de `results.json`.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.contracts import ContratoInvalido
from qagent.storage.registro import ARCHIVO_DETALLE, CARPETA_RUNS
from qagent.storage.vista_ejecucion import ARCHIVO, ResultadosNoDisponibles

CORRIDA_DEMO_ID = "8841-B"
_RUN_ID_VALIDACION = "20260925-143200-8841"
_FECHA_DEMO = "2026-09-25T14:32:00-05:00"

_FUNCIONES_DEMO: tuple[dict[str, Any], ...] = (
    {
        "modulo": "services/pricing.py",
        "funcion": "calculate_discount",
        "critical": True,
        "decision": "accept",
        "motivo_estancado": None,
        "laundering_detectado": False,
        "duracion_s": 0.124,
        "paso": True,
        "lineas": 100.0,
        "ramas": 95.0,
        "iteraciones": 1,
        "tokens": (1116, 8184, 3100),  # 12400 total
        "mutation_score": 92.0,
        "contrato": {
            "funcion": "calculate_discount",
            "firma": '(cart_total: float, coupon_code: Optional[str] = None, user_tier: str = "standard") -> float',
            "tipos": {
                "cart_total": "float (>0)",
                "coupon_code": "str | None",
                "user_tier": 'Literal["standard", "gold", "vip"]',
            },
            "docstring": "Calcula el descuento aplicable considerando cupón estacional y nivel de lealtad.",
            "comportamiento_esperado": [
                'Si cart_total < 0 debe lanzar ValueError("El total no puede ser negativo")',
                "VIP recibe un 15% automático sobre el remanente post-cupón",
                'Cupón "SUMMER20" descuenta 20% flat topeado a $50',
                "Tope estricto: la deducción acumulada total no puede exceder el 40%",
            ],
            "contexto_acotado": [
                "config.DISCOUNT_LIMIT = 0.40",
                "services.users.TierManager",
            ],
        },
        "traza": None,
        "codigo": (
            "import pytest\n"
            "from services.pricing import calculate_discount\n\n"
            "def test_calculate_discount_normal_vip():\n"
            "    total = 100.0\n"
            '    res = calculate_discount(total, coupon_code=None, user_tier="vip")\n'
            "    assert res == 15.0\n\n"
            "def test_calculate_discount_coupon_cap():\n"
            "    total = 500.0\n"
            '    res = calculate_discount(total, coupon_code="SUMMER20", user_tier="standard")\n'
            "    assert res == 50.0\n\n"
            "def test_calculate_discount_negative_raises():\n"
            '    with pytest.raises(ValueError, match="El total no puede ser negativo"):\n'
            "        calculate_discount(-10.0)"
        ),
    },
    {
        "modulo": "services/inventory.py",
        "funcion": "reserve_stock_atomic",
        "critical": True,
        "decision": "stalled",
        "motivo_estancado": "error_repetido",
        "laundering_detectado": True,
        "duracion_s": 0.240,
        "paso": False,
        "lineas": 68.0,
        "ramas": 55.0,
        "iteraciones": 3,
        "tokens": (1962, 14388, 5450),  # 21800 total
        "mutation_score": 30.0,
        "contrato": {
            "funcion": "reserve_stock_atomic",
            "firma": "(sku: str, quantity: int, order_id: str, timeout_secs: int = 300) -> bool",
            "tipos": {
                "sku": "str",
                "quantity": "int (>0)",
                "order_id": "str",
                "timeout_secs": "int",
            },
            "docstring": "Bloquea unidades en Redis mediante un lock distribuido Redlock atómico.",
            "comportamiento_esperado": [
                "Si el stock disponible < quantity, debe arrojar InsufficientStockError",
                "Debe adquirir lock atómico Redlock con TTL especificado",
                "En caso de timeout o concurrencia, liberar lock parcial y retornar False",
            ],
            "contexto_acotado": [
                "redis.asyncio",
                "exceptions.InsufficientStockError",
                "services.distributed_lock",
            ],
        },
        "traza": (
            "Reviewer Security Alert [Iteraciones 2 y 3]:\n"
            'Se detectó relajación deliberada de aserciones ("Assertion Laundering / Assertion Neutralization").\n'
            "Diff detectado en AST del test:\n"
            '- Iteración 1: assert lock.is_acquired() is True and inventory.get_locked_state(sku) == "HELD"\n'
            "+ Iteración 2: assert res is not None  # <-- Generador evadió la aserción estricta del lock\n"
            "+ Iteración 3: assert res is not None  # <-- misma relajación (hash del diff repetido)\n\n"
            "Acción del Reviewer: Rechazo de la prueba. Se conserva la versión de la Iter 1 como referencia y se marca para revisión humana."
        ),
        "codigo": (
            "# INTENTOS 2 y 3 - RECHAZADOS POR REVIEWER (ASSERTION LAUNDERING)\n"
            "import pytest\n"
            "from services.inventory import reserve_stock_atomic\n\n"
            "def test_reserve_stock_insufficient_stock():\n"
            '    res = reserve_stock_atomic("SKU-998", quantity=1000, order_id="ORD-101")\n'
            "    assert res is not None"
        ),
    },
    {
        "modulo": "services/payments.py",
        "funcion": "validate_credit_card_token",
        "critical": True,
        "decision": "stalled",
        "motivo_estancado": "limite_intentos",
        "laundering_detectado": False,
        "duracion_s": 0.510,
        "paso": False,
        "lineas": 52.0,
        "ramas": 40.0,
        "iteraciones": 3,
        "tokens": (2484, 18216, 6900),  # 27600 total
        "mutation_score": 25.0,
        "contrato": {
            "funcion": "validate_credit_card_token",
            "firma": "(token: str, gateway_id: str) -> GatewayAuthResponse",
            "tipos": {"token": "str (JWT PCI-DSS format)", "gateway_id": "str"},
            "docstring": "Verifica la validez y firma criptográfica del token ante la pasarela bancaria.",
            "comportamiento_esperado": [
                "Valida regex estricto de token token_pci_\\w{24}",
                "Lanza InvalidTokenSignature si la clave pública expira o falla mTLS",
                'Retorna GatewayAuthResponse con status="AUTHORIZED"',
            ],
            "contexto_acotado": [
                "security.pci_crypto",
                "gateways.stripe",
                "config.MTLS_CERTS",
            ],
        },
        "traza": (
            "SandboxExecutionError [Estancado tras 3/3 intentos]:\n"
            "ConnectionRefusedError: [Errno 111] Connection refused (127.0.0.1:8443)\n"
            "Traceback (most recent call last):\n"
            '  File "tests/test_payments.py", line 9, in test_validate_token_expired\n'
            '    validate_credit_card_token(token, gateway_id="stripe_v3")\n'
            '  File "/app/services/payments.py", line 45, in validate_credit_card_token\n'
            '    sock.connect(("127.0.0.1", 8443))\n'
            "ConnectionRefusedError: [Errno 111] Connection refused\n"
            "Estado: la prueba necesita un mock de gateways.stripe; el sandbox no tiene red (aislamiento hermético)."
        ),
        "codigo": (
            "import pytest\n"
            "from services.payments import validate_credit_card_token\n"
            "from exceptions import InvalidTokenSignature\n\n"
            "def test_validate_token_expired():\n"
            '    token = "token_pci_expired_0019283921029384"\n'
            "    with pytest.raises(InvalidTokenSignature):\n"
            '        validate_credit_card_token(token, gateway_id="stripe_v3")'
        ),
    },
    {
        "modulo": "services/discounts.py",
        "funcion": "compute_loyalty_multiplier",
        "critical": True,
        "decision": "accept",
        "motivo_estancado": None,
        "laundering_detectado": False,
        "duracion_s": 0.095,
        "paso": True,
        "lineas": 98.0,
        "ramas": 92.0,
        "iteraciones": 1,
        "tokens": (1071, 7854, 2975),  # 11900 total
        "mutation_score": 38.0,
        "contrato": {
            "funcion": "compute_loyalty_multiplier",
            "firma": "(orders_count: int, registered_months: int) -> float",
            "tipos": {"orders_count": "int (>=0)", "registered_months": "int (>=0)"},
            "docstring": "Calcula el coeficiente multiplicador para puntos de fidelidad según antigüedad y volumen de compras.",
            "comportamiento_esperado": [
                "Si registered_months >= 12 y orders_count >= 5 -> multiplicador exacto 1.5x",
                "Si registered_months >= 6 -> multiplicador exacto 1.2x",
                "En cualquier otro caso retorna 1.0x baseline invariable",
            ],
            "contexto_acotado": ["services.loyalty.Rules"],
        },
        "traza": (
            "Mutation Analysis Warning [Brecha Cobertura vs Mutantes]:\n"
            "Cobertura de línea: 98% (Alta) | Mutation Score: 38% (3 de 8 mutantes eliminados).\n"
            "Mutantes sobrevivientes (5), entre ellos:\n"
            "  - Mutante #1: services/discounts.py:14 (Reemplazo de '>=' por '>') -> Test NO falló en valor de frontera 12 meses.\n"
            "  - Mutante #2: services/discounts.py:18 (Mutación de constante 1.5 a 1.0) -> Sobrevivió por aserción débil (assert res > 1.0 en lugar de assert res == 1.5).\n"
            "  - Mutante #3: Negación de branch de antigüedad.\n"
            "Se solicita al agente Generator generar pruebas de límite estricto."
        ),
        "codigo": (
            "import pytest\n"
            "from services.discounts import compute_loyalty_multiplier\n\n"
            "def test_compute_loyalty_basic():\n"
            "    res = compute_loyalty_multiplier(orders_count=6, registered_months=14)\n"
            "    assert res > 1.0"
        ),
    },
    {
        "modulo": "services/cart.py",
        "funcion": "apply_bulk_promotion",
        "critical": True,
        "decision": "bug_detectado",
        "motivo_estancado": None,
        "laundering_detectado": False,
        "duracion_s": 0.188,
        "paso": False,
        "lineas": 94.0,
        "ramas": 88.0,
        "iteraciones": 2,
        "tokens": (1638, 12012, 4550),  # 18200 total
        "mutation_score": 40.0,
        "contrato": {
            "funcion": "apply_bulk_promotion",
            "firma": "(items: List[CartItem], category_id: int) -> CartSummary",
            "tipos": {"items": "List[CartItem]", "category_id": "int"},
            "docstring": "Aplica 3x2 en items de la misma categoría especificada.",
            "comportamiento_esperado": [
                "Agrupa por category_id y descuenta la unidad más barata cada 3 items",
                "Carritos vacíos devuelven CartSummary con discount=0 y items_count=0",
                "No altera precios unitarios de productos fuera de la categoría",
            ],
            "contexto_acotado": ["models.CartItem", "models.CartSummary"],
        },
        "traza": (
            "Oracle Traceability Check [Iteración 2/3]:\n"
            "- Iteración 1: assert summary.total_discount == 20.0   -> FAILED (la función devolvió 10.0)\n"
            "+ Iteración 2: assert summary.total_discount == 10.0   -> PASSED\n"
            "Literal 10.0 sin origen en planner_contract.comportamiento_esperado.\n"
            "Regla aplicada: el valor esperado solo puede provenir del contrato (firma, tipos, docstring), nunca del resultado de ejecutar el código.\n\n"
            "Acción del Reviewer: Rechazo de la prueba y corte del ciclo (reintentar no corrige un defecto del código).\n"
            "Hallazgo: POSIBLE DEFECTO en services/cart.py::apply_bulk_promotion — la promoción 3x2 solo se aplica al primer grupo."
        ),
        "codigo": (
            "# INTENTO 2 - RECHAZADO POR REVIEWER (ORÁCULO ALTERADO)\n"
            "import pytest\n"
            "from services.cart import apply_bulk_promotion\n"
            "from models import CartItem\n\n"
            "def test_apply_bulk_promotion_six_items():\n"
            "    items = [CartItem(id=i, category_id=5, price=10.0) for i in range(6)]\n"
            "    summary = apply_bulk_promotion(items, category_id=5)\n"
            "    assert summary.total_discount == 10.0"
        ),
    },
    {
        "modulo": "services/cart.py",
        "funcion": "calculate_tax_breakdown",
        "critical": False,
        "decision": "accept",
        "motivo_estancado": None,
        "laundering_detectado": False,
        "duracion_s": 0.110,
        "paso": True,
        "lineas": 100.0,
        "ramas": 100.0,
        "iteraciones": 1,
        "tokens": (1044, 7656, 2900),  # 11600 total
        "mutation_score": None,
        "contrato": {
            "funcion": "calculate_tax_breakdown",
            "firma": "(subtotal: float, state_code: str, is_exempt: bool = False) -> TaxReport",
            "tipos": {
                "subtotal": "float",
                "state_code": "str (2 chars)",
                "is_exempt": "bool",
            },
            "docstring": "Desglosa impuestos estatales y municipales aplicables.",
            "comportamiento_esperado": [
                "Si is_exempt=True, total_tax siempre es 0.00",
                "Valida código de estado ISO-3166-2",
                "Calcula tasas específicas para NY (8.875%), CA (7.25%), TX (6.25%)",
            ],
            "contexto_acotado": ["geo.taxes", "models.TaxReport"],
        },
        "traza": None,
        "codigo": (
            "import pytest\n"
            "from services.cart import calculate_tax_breakdown\n\n"
            "def test_tax_exempt_customer():\n"
            '    rep = calculate_tax_breakdown(subtotal=150.0, state_code="CA", is_exempt=True)\n'
            "    assert rep.total_tax == 0.0\n"
            "    assert rep.effective_rate == 0.0\n\n"
            "def test_tax_california_rate():\n"
            '    rep = calculate_tax_breakdown(subtotal=100.0, state_code="CA", is_exempt=False)\n'
            "    assert rep.total_tax == 7.25"
        ),
    },
    {
        "modulo": "services/shipping.py",
        "funcion": "estimate_delivery_window",
        "critical": False,
        "decision": "accept",
        "motivo_estancado": None,
        "laundering_detectado": False,
        "duracion_s": 0.142,
        "paso": True,
        "lineas": 96.0,
        "ramas": 90.0,
        "iteraciones": 1,
        "tokens": (1089, 7986, 3025),  # 12100 total
        "mutation_score": None,
        "contrato": {
            "funcion": "estimate_delivery_window",
            "firma": "(zip_code: str, warehouse_id: str, express: bool = False) -> DeliveryWindow",
            "tipos": {"zip_code": "str", "warehouse_id": "str", "express": "bool"},
            "docstring": "Calcula rango estimado de entrega en días hábiles.",
            "comportamiento_esperado": [
                "Excluye fines de semana y feriados en el cálculo",
                "Modo express garantiza entrega en 24-48 horas dentro del radio",
                "Lanza UnsupportedZoneError para códigos postales fuera de cobertura",
            ],
            "contexto_acotado": ["logistics.carriers", "models.DeliveryWindow"],
        },
        "traza": None,
        "codigo": (
            "import pytest\n"
            "from services.shipping import estimate_delivery_window\n\n"
            "def test_estimate_delivery_express():\n"
            '    win = estimate_delivery_window("90210", warehouse_id="WH-LA-01", express=True)\n'
            "    assert win.max_days <= 2\n"
            "    assert win.is_guaranteed is True"
        ),
    },
    {
        "modulo": "services/payments.py",
        "funcion": "refund_charge_idempotent",
        "critical": True,
        "decision": "accept",
        "motivo_estancado": None,
        "laundering_detectado": False,
        "duracion_s": 0.290,
        "paso": True,
        "lineas": 100.0,
        "ramas": 94.0,
        "iteraciones": 2,
        "tokens": (1467, 10758, 4075),  # 16300 total
        "mutation_score": 95.0,
        "contrato": {
            "funcion": "refund_charge_idempotent",
            "firma": "(payment_id: str, amount_cents: int, idempotency_key: str) -> RefundResult",
            "tipos": {
                "payment_id": "str",
                "amount_cents": "int (>0)",
                "idempotency_key": "str",
            },
            "docstring": "Reembolsa saldo con salvaguarda de idempotencia contra cobros dobles.",
            "comportamiento_esperado": [
                "Rechaza montos <= 0 con InvalidAmountException",
                "Si la clave de idempotencia ya fue procesada, retorna el resultado previo sin re-llamar al procesador",
                "Actualiza el ledger contable atómicamente",
            ],
            "contexto_acotado": ["ledger.accounting", "gateways.stripe"],
        },
        "traza": None,
        "codigo": (
            "import pytest\n"
            "from services.payments import refund_charge_idempotent\n\n"
            "def test_refund_duplicate_idempotency_key_does_not_double_charge():\n"
            '    key = "idem_key_unique_8823"\n'
            '    r1 = refund_charge_idempotent("pay_123", 4500, idempotency_key=key)\n'
            '    r2 = refund_charge_idempotent("pay_123", 4500, idempotency_key=key)\n'
            "    assert r1.refund_id == r2.refund_id\n"
            "    assert r2.was_cached is True"
        ),
    },
    {
        "modulo": "services/inventory.py",
        "funcion": "check_low_stock_alerts",
        "critical": False,
        "decision": "accept",
        "motivo_estancado": None,
        "laundering_detectado": False,
        "duracion_s": 0.135,
        "paso": True,
        "lineas": 92.0,
        "ramas": 85.0,
        "iteraciones": 1,
        "tokens": (954, 6996, 2650),  # 10600 total
        "mutation_score": None,
        "contrato": {
            "funcion": "check_low_stock_alerts",
            "firma": "(threshold_ratio: float = 0.15) -> List[StockAlert]",
            "tipos": {"threshold_ratio": "float (0.01 .. 0.50)"},
            "docstring": "Escanea el catálogo de existencias y despacha notificaciones para reposición.",
            "comportamiento_esperado": [
                "Filtra productos donde current_stock / safety_stock <= threshold_ratio",
                "Ignora productos marcados como descontinuados",
            ],
            "contexto_acotado": ["models.StockAlert", "services.notifications"],
        },
        "traza": None,
        "codigo": (
            "import pytest\n"
            "from services.inventory import check_low_stock_alerts\n\n"
            "def test_check_low_stock_filters_discontinued():\n"
            "    alerts = check_low_stock_alerts(threshold_ratio=0.20)\n"
            "    for alert in alerts:\n"
            "        assert alert.is_discontinued is False\n"
            '        assert alert.urgency in ["HIGH", "CRITICAL"]'
        ),
    },
)

_SPECS_DEMO: tuple[dict[str, str], ...] = (
    {
        "modulo": "services/pricing.py",
        "huella": "1" * 64,
        "run_origen": "20260920-100000-8730",
        "estado": "reutilizado",
    },
    {
        "modulo": "services/inventory.py",
        "huella": "2" * 64,
        "run_origen": "20260920-100000-8730",
        "estado": "reutilizado",
    },
    {
        "modulo": "services/payments.py",
        "huella": "3" * 64,
        "run_origen": "20260920-100000-8730",
        "estado": "reutilizado",
    },
    {
        "modulo": "services/shipping.py",
        "huella": "4" * 64,
        "run_origen": "20260920-100000-8730",
        "estado": "reutilizado",
    },
    {
        "modulo": "services/cart.py",
        "huella": "5" * 64,
        "run_origen": _RUN_ID_VALIDACION,
        "estado": "regenerado",
    },
    {
        "modulo": "services/discounts.py",
        "huella": "6" * 64,
        "run_origen": _RUN_ID_VALIDACION,
        "estado": "regenerado",
    },
)


_ENTORNO_DEMO: dict[str, Any] = {
    "imagen": "qagent-sandbox:base",
    "comando": "pytest -v --cov=services --cov-branch --cov-report=json",
    "plataforma": "Linux x86_64 (Docker)",
    "python": "3.10.12",
    "pytest": "8.2.2",
    "limites": {
        "cpus": 1.0,
        "memoria": "512 MB",
        "timeout_s": 60.0,
    },
}


def _construir_intentos_demo(
    f: dict[str, Any], entorno: dict[str, Any]
) -> list[dict[str, Any]]:
    fn = f["funcion"]
    if fn == "calculate_discount":
        return [
            {
                "intento": 1,
                "decision": "accept",
                "estado_sandbox": "ok",
                "tipo_fallo": None,
                "laundering_detectado": False,
                "feedback": "Prueba aprobada en sandbox Docker (3 casos pasaron, 100% líneas, 95% ramas).",
                "hash_error": None,
                "cobertura": {"lineas": 100.0, "ramas": 95.0},
                "ejecucion": {
                    "exit_code": 0,
                    "duracion_s": 0.124,
                    "timeout": False,
                    "oom": False,
                    "salida": (
                        "tests/test_pricing.py::test_calculate_discount_normal_vip PASSED [33%]\n"
                        "tests/test_pricing.py::test_calculate_discount_coupon_cap PASSED [66%]\n"
                        "tests/test_pricing.py::test_calculate_discount_negative_raises PASSED [100%]\n"
                        "3 passed in 0.12s"
                    ),
                    "totales": {
                        "total": 3,
                        "pasaron": 3,
                        "fallaron": 0,
                        "errores": 0,
                        "omitidos": 0,
                    },
                    "casos": [
                        {
                            "nombre": "test_calculate_discount_normal_vip",
                            "resultado": "paso",
                            "duracion_s": 0.04,
                            "archivo": "tests/test_pricing.py",
                            "linea": 6,
                        },
                        {
                            "nombre": "test_calculate_discount_coupon_cap",
                            "resultado": "paso",
                            "duracion_s": 0.04,
                            "archivo": "tests/test_pricing.py",
                            "linea": 11,
                        },
                        {
                            "nombre": "test_calculate_discount_negative_raises",
                            "resultado": "paso",
                            "duracion_s": 0.04,
                            "archivo": "tests/test_pricing.py",
                            "linea": 16,
                        },
                    ],
                    "lineas_sin_cubrir": [],
                    "entorno": copy.deepcopy(entorno),
                },
            }
        ]
    if fn == "reserve_stock_atomic":
        return [
            {
                "intento": 1,
                "decision": "retry",
                "estado_sandbox": "fallo",
                "tipo_fallo": "error_test",
                "laundering_detectado": False,
                "feedback": "AssertionError: lock no fue adquirido en Redis (assert lock.is_acquired() is True).",
                "hash_error": "a1b2c3d4",
                "cobertura": {"lineas": 68.0, "ramas": 55.0},
                "ejecucion": {
                    "exit_code": 1,
                    "duracion_s": 0.08,
                    "timeout": False,
                    "oom": False,
                    "salida": "FAILED tests/test_inventory.py::test_reserve_stock_atomic - AssertionError: assert False is True",
                    "totales": {
                        "total": 2,
                        "pasaron": 1,
                        "fallaron": 1,
                        "errores": 0,
                        "omitidos": 0,
                    },
                    "casos": [
                        {
                            "nombre": "test_reserve_stock_atomic",
                            "resultado": "fallo",
                            "duracion_s": 0.05,
                            "archivo": "tests/test_inventory.py",
                            "linea": 12,
                            "codigo": "assert lock.is_acquired() is True",
                            "mensaje": "AssertionError: lock no fue adquirido en Redis",
                            "tipo_error": "AssertionError",
                            "esperado": "True",
                            "obtenido": "False",
                            "pila": [
                                {
                                    "archivo": "tests/test_inventory.py",
                                    "linea": 12,
                                    "detalle": "test_reserve_stock_atomic()",
                                    "codigo": "assert lock.is_acquired() is True",
                                }
                            ],
                        },
                        {
                            "nombre": "test_reserve_stock_insufficient",
                            "resultado": "paso",
                            "duracion_s": 0.03,
                            "archivo": "tests/test_inventory.py",
                            "linea": 20,
                        },
                    ],
                    "lineas_sin_cubrir": [28, 29, 30],
                    "entorno": copy.deepcopy(entorno),
                },
            },
            {
                "intento": 2,
                "decision": "retry",
                "estado_sandbox": "ok",
                "tipo_fallo": "error_test",
                "laundering_detectado": True,
                "feedback": "Reviewer Security Alert [Intento 2]: Se detectó relajación deliberada de aserciones ('Assertion Laundering'). El generador cambió 'assert lock.is_acquired() is True' por 'assert res is not None'. Se rechaza la prueba.",
                "hash_error": "d4e5f6a1",
                "cobertura": {"lineas": 68.0, "ramas": 55.0},
                "ejecucion": None,
            },
            {
                "intento": 3,
                "decision": "stalled",
                "estado_sandbox": "ok",
                "tipo_fallo": "error_test",
                "laundering_detectado": True,
                "feedback": "Reviewer Security Alert [Intento 3]: Misma relajación de aserciones detectada (hash repetido). Estancado por error repetido tras 3 intentos. Prueba rechazada formalmente.",
                "hash_error": "d4e5f6a1",
                "cobertura": {"lineas": 68.0, "ramas": 55.0},
                "ejecucion": None,
            },
        ]
    if fn == "validate_credit_card_token":
        return [
            {
                "intento": 1,
                "decision": "retry",
                "estado_sandbox": "fallo",
                "tipo_fallo": "error_test",
                "laundering_detectado": False,
                "feedback": "ConnectionRefusedError: [Errno 111] Connection refused (127.0.0.1:8443). El código intenta conectar a red real.",
                "hash_error": "11223344",
                "cobertura": {"lineas": 52.0, "ramas": 40.0},
                "ejecucion": {
                    "exit_code": 1,
                    "duracion_s": 0.17,
                    "timeout": False,
                    "oom": False,
                    "salida": "FAILED tests/test_payments.py::test_validate_token_expired - ConnectionRefusedError: [Errno 111] Connection refused",
                    "totales": {
                        "total": 1,
                        "pasaron": 0,
                        "fallaron": 1,
                        "errores": 0,
                        "omitidos": 0,
                    },
                    "casos": [
                        {
                            "nombre": "test_validate_token_expired",
                            "resultado": "fallo",
                            "duracion_s": 0.17,
                            "archivo": "tests/test_payments.py",
                            "linea": 9,
                            "codigo": "validate_credit_card_token(token, gateway_id='stripe_v3')",
                            "mensaje": "ConnectionRefusedError: [Errno 111] Connection refused",
                            "tipo_error": "ConnectionRefusedError",
                            "esperado": "InvalidTokenSignature",
                            "obtenido": "ConnectionRefusedError",
                            "pila": [
                                {
                                    "archivo": "tests/test_payments.py",
                                    "linea": 9,
                                    "detalle": "test_validate_token_expired()",
                                    "codigo": "validate_credit_card_token(token, gateway_id='stripe_v3')",
                                }
                            ],
                        }
                    ],
                    "lineas_sin_cubrir": [48, 49, 50, 51],
                    "entorno": copy.deepcopy(entorno),
                },
            },
            {
                "intento": 2,
                "decision": "retry",
                "estado_sandbox": "fallo",
                "tipo_fallo": "error_test",
                "laundering_detectado": False,
                "feedback": "ConnectionRefusedError reiterado: se requiere mock de gateways.stripe.",
                "hash_error": "55667788",
                "cobertura": {"lineas": 52.0, "ramas": 40.0},
                "ejecucion": None,
            },
            {
                "intento": 3,
                "decision": "stalled",
                "estado_sandbox": "fallo",
                "tipo_fallo": "error_test",
                "laundering_detectado": False,
                "feedback": "Límite de intentos alcanzado (3/3). La prueba requiere simulación de socket/mTLS; el sandbox no tiene red (--network none).",
                "hash_error": "99aabbcc",
                "cobertura": {"lineas": 52.0, "ramas": 40.0},
                "ejecucion": None,
            },
        ]
    if fn == "compute_loyalty_multiplier":
        return [
            {
                "intento": 1,
                "decision": "accept",
                "estado_sandbox": "ok",
                "tipo_fallo": None,
                "laundering_detectado": False,
                "feedback": "Prueba aprobada en sandbox (1 caso pasó, 98% líneas, 92% ramas). Advertencia de Mutation Testing: Mutation Score bajo (38%).",
                "hash_error": None,
                "cobertura": {"lineas": 98.0, "ramas": 92.0},
                "ejecucion": {
                    "exit_code": 0,
                    "duracion_s": 0.095,
                    "timeout": False,
                    "oom": False,
                    "salida": "tests/test_discounts.py::test_compute_loyalty_basic PASSED\n1 passed in 0.09s",
                    "totales": {
                        "total": 1,
                        "pasaron": 1,
                        "fallaron": 0,
                        "errores": 0,
                        "omitidos": 0,
                    },
                    "casos": [
                        {
                            "nombre": "test_compute_loyalty_basic",
                            "resultado": "paso",
                            "duracion_s": 0.095,
                            "archivo": "tests/test_discounts.py",
                            "linea": 5,
                        }
                    ],
                    "lineas_sin_cubrir": [14],
                    "entorno": copy.deepcopy(entorno),
                },
            }
        ]
    if fn == "apply_bulk_promotion":
        return [
            {
                "intento": 1,
                "decision": "retry",
                "estado_sandbox": "fallo",
                "tipo_fallo": "bug_codigo",
                "laundering_detectado": False,
                "feedback": "Oracle Traceability Check [Intento 1]: assert summary.total_discount == 20.0 -> FAILED (la función devolvió 10.0 en lugar de 20.0).",
                "hash_error": "c1d2e3f4",
                "cobertura": {"lineas": 94.0, "ramas": 88.0},
                "ejecucion": {
                    "exit_code": 1,
                    "duracion_s": 0.09,
                    "timeout": False,
                    "oom": False,
                    "salida": "FAILED tests/test_cart.py::test_apply_bulk_promotion_six_items - AssertionError: assert 10.0 == 20.0",
                    "totales": {
                        "total": 2,
                        "pasaron": 1,
                        "fallaron": 1,
                        "errores": 0,
                        "omitidos": 0,
                    },
                    "casos": [
                        {
                            "nombre": "test_apply_bulk_promotion_six_items",
                            "resultado": "fallo",
                            "duracion_s": 0.06,
                            "archivo": "tests/test_cart.py",
                            "linea": 15,
                            "codigo": "assert summary.total_discount == 20.0",
                            "mensaje": "AssertionError: la función devolvió 10.0 pero el contrato exige 20.0",
                            "tipo_error": "AssertionError",
                            "esperado": "20.0",
                            "obtenido": "10.0",
                            "pila": [
                                {
                                    "archivo": "tests/test_cart.py",
                                    "linea": 15,
                                    "detalle": "test_apply_bulk_promotion_six_items()",
                                    "codigo": "assert summary.total_discount == 20.0",
                                }
                            ],
                        },
                        {
                            "nombre": "test_apply_bulk_promotion_empty",
                            "resultado": "paso",
                            "duracion_s": 0.03,
                            "archivo": "tests/test_cart.py",
                            "linea": 22,
                        },
                    ],
                    "lineas_sin_cubrir": [],
                    "entorno": copy.deepcopy(entorno),
                },
            },
            {
                "intento": 2,
                "decision": "bug_detectado",
                "estado_sandbox": "ok",
                "tipo_fallo": "bug_codigo",
                "laundering_detectado": False,
                "feedback": "Oracle Traceability Alert [Intento 2]: El Generador cambió el valor esperado a 10.0 para hacer pasar el test. Regla violada: el valor esperado solo proviene del contrato, no de la ejecución. Veredicto: BUG DETECTADO en services/cart.py::apply_bulk_promotion.",
                "hash_error": "f4e3d2c1",
                "cobertura": {"lineas": 94.0, "ramas": 88.0},
                "ejecucion": None,
            },
        ]
    if fn == "refund_charge_idempotent":
        return [
            {
                "intento": 1,
                "decision": "retry",
                "estado_sandbox": "fallo",
                "tipo_fallo": "error_test",
                "laundering_detectado": False,
                "feedback": "KeyError: 'idempotency_key' faltante en mock de pasarela Stripe.",
                "hash_error": "aa11bb22",
                "cobertura": {"lineas": 85.0, "ramas": 75.0},
                "ejecucion": None,
            },
            {
                "intento": 2,
                "decision": "accept",
                "estado_sandbox": "ok",
                "tipo_fallo": None,
                "laundering_detectado": False,
                "feedback": "Prueba aprobada en sandbox con mock idempotente (100% líneas, 94% ramas).",
                "hash_error": None,
                "cobertura": {"lineas": 100.0, "ramas": 94.0},
                "ejecucion": {
                    "exit_code": 0,
                    "duracion_s": 0.290,
                    "timeout": False,
                    "oom": False,
                    "salida": "tests/test_payments.py::test_refund_duplicate_idempotency_key_does_not_double_charge PASSED",
                    "totales": {
                        "total": 1,
                        "pasaron": 1,
                        "fallaron": 0,
                        "errores": 0,
                        "omitidos": 0,
                    },
                    "casos": [
                        {
                            "nombre": "test_refund_duplicate_idempotency_key_does_not_double_charge",
                            "resultado": "paso",
                            "duracion_s": 0.290,
                            "archivo": "tests/test_payments.py",
                            "linea": 5,
                        }
                    ],
                    "lineas_sin_cubrir": [],
                    "entorno": copy.deepcopy(entorno),
                },
            },
        ]
    return [
        {
            "intento": 1,
            "decision": "accept",
            "estado_sandbox": "ok",
            "tipo_fallo": None,
            "laundering_detectado": False,
            "feedback": f"Prueba aprobada en sandbox ({f['lineas']:g}% líneas, {f['ramas']:g}% ramas).",
            "hash_error": None,
            "cobertura": {"lineas": f["lineas"], "ramas": f["ramas"]},
            "ejecucion": {
                "exit_code": 0,
                "duracion_s": f["duracion_s"],
                "timeout": False,
                "oom": False,
                "salida": f"tests/test_{fn}.py PASSED in {f['duracion_s']:.2f}s",
                "totales": {
                    "total": 1,
                    "pasaron": 1,
                    "fallaron": 0,
                    "errores": 0,
                    "omitidos": 0,
                },
                "casos": [
                    {
                        "nombre": f"test_{fn}_basico",
                        "resultado": "paso",
                        "duracion_s": f["duracion_s"],
                        "archivo": f"tests/test_{fn}.py",
                        "linea": 5,
                    }
                ],
                "lineas_sin_cubrir": [],
                "entorno": copy.deepcopy(entorno),
            },
        }
    ]


def construir_archivos_demo(
    raiz_proyecto: str | Path, run_id: str = CORRIDA_DEMO_ID
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Construye los diccionarios `results.json`, `detalle.json` y `run.json` de la demo."""
    proyecto = str(Path(raiz_proyecto).resolve())
    objetivos = []
    funciones_detalle = []
    totales_casos = {
        "total": 0,
        "pasaron": 0,
        "fallaron": 0,
        "errores": 0,
        "omitidos": 0,
    }

    for f in _FUNCIONES_DEMO:
        tok_p, tok_g, tok_r = f["tokens"]
        ms = f["mutation_score"]
        objetivos.append(
            {
                "modulo": f["modulo"],
                "funcion": f["funcion"],
                "critical": f["critical"],
                "decision": f["decision"],
                "motivo_estancado": f["motivo_estancado"],
                "laundering_detectado": f["laundering_detectado"],
                "duracion_s": f["duracion_s"],
                "controles": {
                    "sintaxis": True,
                    "sandbox": not (
                        f["decision"] == "stalled" and not f["laundering_detectado"]
                    ),
                    "aserciones": not f["laundering_detectado"]
                    and f["decision"] != "bug_detectado",
                    "cobertura": f["lineas"] >= 60.0 and f["ramas"] >= 60.0,
                    "mutation": (ms >= 60.0)
                    if (f["critical"] and ms is not None)
                    else None,
                },
                "metricas": {
                    "paso": f["paso"],
                    "cobertura_lineas": f["lineas"],
                    "cobertura_ramas": f["ramas"],
                    "iteraciones": f["iteraciones"],
                    "tokens_por_agente": {
                        "planner": {"prompt_tokens": tok_p, "completion_tokens": 0},
                        "generator": {"prompt_tokens": tok_g, "completion_tokens": 0},
                        "reviewer": {"prompt_tokens": tok_r, "completion_tokens": 0},
                    },
                    "mutation_score": ms,
                },
            }
        )
        intentos = _construir_intentos_demo(f, _ENTORNO_DEMO)
        for i in intentos:
            ej = i.get("ejecucion")
            if ej and ej.get("totales"):
                t = ej["totales"]
                for k in totales_casos:
                    totales_casos[k] += t.get(k, 0)
                break
        funciones_detalle.append(
            {
                "modulo": f["modulo"],
                "funcion": f["funcion"],
                "contrato": copy.deepcopy(f["contrato"]),
                "codigo": f["codigo"],
                "traza": f["traza"],
                "intentos": intentos,
            }
        )

    results: dict[str, Any] = {
        "version": "1",
        "tipo": "results",
        "run_id": run_id,
        "fecha": _FECHA_DEMO,
        "proyecto": proyecto,
        "perfil": "deep",
        "rama": "main",
        "modelos": {
            "planner": {
                "proveedor": "Anthropic",
                "modelo": "Modelo de contexto amplio",
                "precio_entrada_usd_m": 5.0,
                "precio_salida_usd_m": 5.0,
            },
            "generator": {
                "proveedor": "Xiaomi",
                "modelo": "Modelo económico",
                "precio_entrada_usd_m": 0.6,
                "precio_salida_usd_m": 0.6,
            },
            "reviewer": {
                "proveedor": "OpenAI",
                "modelo": "Modelo económico",
                "precio_entrada_usd_m": 0.6,
                "precio_salida_usd_m": 0.6,
            },
        },
        "estado_final": "fin",
        "motivo_fallo": None,
        "es_simulado": True,
        "objetivos": objetivos,
        "resumen": {
            "total_funciones": 9,
            "aceptadas": 6,
            "bugs_detectados": 1,
            "stalled": 2,
            "sin_veredicto": 0,
            "pass_rate": 66.7,
            "cobertura_lineas_promedio": 88.9,
            "cobertura_ramas_promedio": 82.1,
            "iteraciones_promedio": 1.67,
            "costo_total_usd": 0.14193,
            "por_agente": {
                "planner": {
                    "prompt_tokens": 12825,
                    "completion_tokens": 0,
                    "costo_usd": 0.064125,
                    "llamadas": 2,
                },
                "generator": {
                    "prompt_tokens": 94050,
                    "completion_tokens": 0,
                    "costo_usd": 0.05643,
                    "llamadas": 15,
                },
                "reviewer": {
                    "prompt_tokens": 35625,
                    "completion_tokens": 0,
                    "costo_usd": 0.021375,
                    "llamadas": 15,
                },
            },
            "metas": {
                "pass_rate_min": 70.0,
                "cobertura_lineas_min": 60.0,
                "iteraciones_promedio_max": 2.0,
                "tope_por_corrida_usd": 1.48,
            },
        },
    }

    copia_validacion = {**results, "run_id": _RUN_ID_VALIDACION}
    contracts.validar(contracts.RUN_LOG, copia_validacion)

    detalle: dict[str, Any] = {
        "version": "1",
        "tipo": "detalle",
        "run_id": run_id,
        "entorno": copy.deepcopy(_ENTORNO_DEMO),
        "totales_casos": totales_casos,
        "funciones": funciones_detalle,
    }
    contracts.validar(contracts.DETALLE, detalle)
    run_meta: dict[str, Any] = {
        "run_id": run_id,
        "inicio": _FECHA_DEMO,
        "fin": _FECHA_DEMO,
        "tipos_prueba": ["funcion"],
        "imagen_docker": None,
        "estado": "fin",
        "resumen": {"pasaron": 6, "fallaron": 3},
        "specs": [dict(s) for s in _SPECS_DEMO],
    }
    return results, detalle, run_meta


def asegurar_corrida_demo(
    raiz_proyecto: str | Path, run_id: str = CORRIDA_DEMO_ID
) -> Path:
    """Garantiza que exista `.qagent/runs/<run_id>/results.json` y `detalle.json`."""
    carpeta = Path(raiz_proyecto) / CARPETA_RUNS / Path(run_id).name
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_results = carpeta / ARCHIVO
    ruta_detalle = carpeta / ARCHIVO_DETALLE
    ruta_run = carpeta / "run.json"

    results, detalle, run_meta = construir_archivos_demo(raiz_proyecto, run_id=run_id)

    necesita_detalle = not ruta_detalle.is_file()
    if not necesita_detalle:
        try:
            d_existente = json.loads(ruta_detalle.read_text(encoding="utf-8"))
            if not d_existente.get("entorno") or not d_existente.get("totales_casos"):
                necesita_detalle = True
        except (OSError, json.JSONDecodeError):
            necesita_detalle = True

    if not ruta_results.is_file():
        _escribir_json_atomico(ruta_results, results)
    if necesita_detalle:
        _escribir_json_atomico(ruta_detalle, detalle)
    if not ruta_run.is_file():
        _escribir_json_atomico(ruta_run, run_meta)
    return carpeta


def leer_results_demo(
    raiz_proyecto: str | Path, run_id: str = CORRIDA_DEMO_ID
) -> dict[str, Any]:
    """Asegura y lee el `results.json` de la corrida de demostración `#8841-B`."""
    carpeta = asegurar_corrida_demo(raiz_proyecto, run_id=run_id)
    ruta = carpeta / ARCHIVO
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        copia = {**datos, "run_id": _RUN_ID_VALIDACION}
        contracts.validar(contracts.RUN_LOG, copia)
    except (OSError, json.JSONDecodeError, ContratoInvalido) as error:
        raise ResultadosNoDisponibles(f"{ruta} no es válido: {error}") from error
    if datos.get("tipo") != "results":
        raise ResultadosNoDisponibles(f"{ruta} no es un archivo de resultados.")
    return datos


def _escribir_json_atomico(ruta: Path, datos: dict[str, Any]) -> None:
    descriptor, temporal = tempfile.mkstemp(
        prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, indent=2, ensure_ascii=False)
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise

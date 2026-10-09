"""Pruebas de detección de Assertion Laundering (HU-16).

Sin IA, sin Docker, sin red. Solo AST.

Criterios de aceptación y casos cubiertos:
1. Par con laundering (== valor pasa a is not None) y par sin laundering (Criterio 5).
2. Valor esperado cambiado (ej. == 20 pasa a == 21).
3. Tautologías (assert x == x, assert True, assert 1 == 1).
4. try/except que suprime fallos o aserciones sin relanzar.
5. skip / xfail decorador o llamada directa.
6. raises más amplio (ValueError pasa a Exception / BaseException).
7. Corrección del falso positivo al reordenar aserciones.
"""

from __future__ import annotations

import pytest

from pyagent.analysis.laundering import (
    RIGOR,
    comparar_aserciones,
    extraer_aserciones,
)

# =========================================================================== #
# Datos simulados: pares antes/después
# =========================================================================== #

# ─── Caso 1 (laundering): eq → is not None (Criterio 5 obligatorio) ───
ANTES_EQ = """\
def test_descuento():
    assert calcular_descuento(100, 50) == 50.0
"""

DESPUES_IS_NOT_NONE = """\
def test_descuento():
    assert calcular_descuento(100, 50) is not None
"""

# ─── Caso 2 (sin laundering): mismas aserciones (Criterio 5 obligatorio) ───
ANTES_Y_DESPUES_IGUALES = """\
def test_descuento():
    assert calcular_descuento(100, 50) == 50.0
"""

# ─── Caso 3 (laundering): baja de cantidad ───
ANTES_TRES_ASSERTS = """\
def test_multiples():
    assert a == 1
    assert b == 2
    assert c == 3
"""

DESPUES_UN_ASSERT = """\
def test_multiples():
    assert a == 1
"""

# ─── Caso 4 (sin laundering): se agregan aserciones ───
ANTES_UN_ASSERT = """\
def test_basico():
    assert resultado == 42
"""

DESPUES_TRES_ASSERTS = """\
def test_basico():
    assert resultado == 42
    assert tipo == "entero"
    assert resultado > 0
"""

# ─── Caso 5 (laundering): pytest.raises desaparece ───
ANTES_RAISES = """\
def test_error():
    with pytest.raises(ValueError):
        calcular_descuento(-100, 50)
"""

DESPUES_SIN_RAISES = """\
def test_error():
    assert calcular_descuento(100, 50) is not None
"""

# ─── Caso 6 (laundering): valor esperado cambiado ───
ANTES_VALOR_ORIGINAL = """\
def test_valor():
    assert f(1) == 20
"""

DESPUES_VALOR_ALTERADO = """\
def test_valor():
    assert f(1) == 21
"""

# ─── Caso 7 (laundering): eq → in ───
ANTES_EQ_STR = """\
def test_clasificar():
    assert clasificar(18) == "menor"
"""

DESPUES_IN_LISTA = """\
def test_clasificar():
    assert clasificar(18) in ["menor", "adulto"]
"""

# ─── Caso 8 (sin laundering): pytest.raises se mantiene ───
ANTES_RAISES_MANTIENE = """\
def test_negativo():
    with pytest.raises(ValueError):
        calcular_descuento(-1, 50)
"""

DESPUES_RAISES_MANTIENE = """\
def test_negativo():
    with pytest.raises(ValueError):
        calcular_descuento(-1, 50)
"""

# ─── Caso 9 (laundering): eq → true (assert expr sin comparador) ───
ANTES_EQ_LEN = """\
def test_longitud():
    assert len(lista) == 3
"""

DESPUES_SOLO_ASSERT = """\
def test_longitud():
    assert lista
"""

# ─── Caso 10 (sin laundering): true → eq (se fortalece) ───
ANTES_TRUE = """\
def test_existe():
    assert resultado
"""

DESPUES_EQ_VALOR = """\
def test_existe():
    assert resultado == 42
"""

# ─── Caso 11 (laundering): múltiples aserciones, una se debilita ───
ANTES_MULTI_EQ = """\
def test_triple():
    assert a == 1
    assert b == 2
    assert c == 3
"""

DESPUES_MULTI_DEBIL = """\
def test_triple():
    assert a == 1
    assert b is not None
    assert c == 3
"""

# ─── Caso 12 (sin laundering): ne se mantiene ───
ANTES_NE = """\
def test_no_cero():
    assert resultado != 0
"""

DESPUES_NE = """\
def test_no_cero():
    assert resultado != 0
"""

# ─── Caso 13 (laundering): not in → is not None ───
ANTES_NOT_IN = """\
def test_sin_error():
    assert "error" not in respuesta
"""

DESPUES_IS_NOT_NONE_2 = """\
def test_sin_error():
    assert respuesta is not None
"""

# ─── Caso 14 (sin laundering): sin aserciones en ambos ───
ANTES_VACIO = """\
def test_nada():
    pass
"""

DESPUES_VACIO = """\
def test_nada():
    pass
"""

# ─── Reordenamiento sin laundering (falso positivo resuelto) ───
ANTES_ORDEN_A_B = """\
def test_orden():
    assert a == 1
    assert b == 2
"""

DESPUES_ORDEN_B_A = """\
def test_orden():
    assert b == 2
    assert a == 1
"""

# ─── Tautologías ───
ANTES_CONTRATO_REAL = """\
def test_proceso():
    res = calcular(10)
    assert res == 100
"""

DESPUES_TAUTO_RES_EQ_RES = """\
def test_proceso():
    res = calcular(10)
    assert res == res
"""

DESPUES_TAUTO_ASSERT_TRUE = """\
def test_proceso():
    calcular(10)
    assert True
"""

DESPUES_TAUTO_ASSERT_1_EQ_1 = """\
def test_proceso():
    calcular(10)
    assert 1 == 1
"""

# ─── try/except que silencia ───
DESPUES_TRY_EXCEPT_ASSERTION_ERROR = """\
def test_proceso():
    try:
        assert calcular(10) == 100
    except AssertionError:
        pass
"""

DESPUES_TRY_EXCEPT_EXCEPTION_SWALLOWED = """\
def test_proceso():
    try:
        calcular(10)
    except Exception:
        pass
"""

DESPUES_TRY_EXCEPT_CON_RAISE = """\
def test_proceso():
    try:
        res = calcular(10)
    except ValueError:
        raise
    assert res == 100
"""

# ─── skip / xfail ───
DESPUES_DECORADOR_SKIP = """\
@pytest.mark.skip(reason="no pasa")
def test_proceso():
    assert calcular(10) == 100
"""

DESPUES_LLAMADA_PYTEST_SKIP = """\
def test_proceso():
    pytest.skip("omitir")
    assert calcular(10) == 100
"""

DESPUES_DECORADOR_XFAIL = """\
@pytest.mark.xfail(reason="bug conocido")
def test_proceso():
    assert calcular(10) == 100
"""

# ─── raises más amplio ───
ANTES_RAISES_VALUE_ERROR = """\
def test_error():
    with pytest.raises(ValueError):
        calcular(-10)
"""

DESPUES_RAISES_EXCEPTION = """\
def test_error():
    with pytest.raises(Exception):
        calcular(-10)
"""

DESPUES_RAISES_BASE_EXCEPTION = """\
def test_error():
    with pytest.raises(BaseException):
        calcular(-10)
"""

ANTES_RAISES_KEY_ERROR = """\
def test_error():
    with pytest.raises(KeyError):
        buscar("no_existe")
"""

DESPUES_RAISES_LOOKUP_ERROR = """\
def test_error():
    with pytest.raises(LookupError):
        buscar("no_existe")
"""


# =========================================================================== #
# Evidencia de aceptación — Criterio 5 de HU-16 y casos ampliados
# =========================================================================== #


class TestLaunderingDetectado:
    """Pares donde se espera que se detecte Assertion Laundering."""

    def test_caso1_eq_a_is_not_none(self) -> None:
        """== valor pasa a is not None → laundering (Criterio 5 obligatorio)."""
        resultado = comparar_aserciones(ANTES_EQ, DESPUES_IS_NOT_NONE)
        assert resultado.es_laundering is True
        assert len(resultado.diferencias) >= 1
        assert "Rigor debilitado" in resultado.diferencias[0].motivo

    def test_caso3_baja_cantidad(self) -> None:
        """3 asserts → 1 assert → laundering por reducción de cantidad."""
        resultado = comparar_aserciones(ANTES_TRES_ASSERTS, DESPUES_UN_ASSERT)
        assert resultado.es_laundering is True
        assert len(resultado.aserciones_contrato) == 3
        assert len(resultado.aserciones_sintetizadas) == 1

    def test_caso5_raises_desaparece(self) -> None:
        """pytest.raises desaparece y se reemplaza por is not None → laundering."""
        resultado = comparar_aserciones(ANTES_RAISES, DESPUES_SIN_RAISES)
        assert resultado.es_laundering is True
        assert any(d.contrato.tipo == "raises" for d in resultado.diferencias)

    def test_caso6_valor_esperado_cambiado(self) -> None:
        """== 20 pasa a == 21 → laundering por valor esperado cambiado."""
        resultado = comparar_aserciones(ANTES_VALOR_ORIGINAL, DESPUES_VALOR_ALTERADO)
        assert resultado.es_laundering is True
        assert any("Valor esperado cambiado" in d.motivo for d in resultado.diferencias)

    def test_caso7_eq_a_in(self) -> None:
        """== valor pasa a in lista → laundering (rigor 9 → 6)."""
        resultado = comparar_aserciones(ANTES_EQ_STR, DESPUES_IN_LISTA)
        assert resultado.es_laundering is True

    def test_caso9_eq_a_true(self) -> None:
        """== valor pasa a assert expr (booleano) → laundering (rigor 9 → 1)."""
        resultado = comparar_aserciones(ANTES_EQ_LEN, DESPUES_SOLO_ASSERT)
        assert resultado.es_laundering is True

    def test_caso11_multi_una_debilitada(self) -> None:
        """3 asserts iguales, pero la segunda baja de eq a is_not_none → laundering."""
        resultado = comparar_aserciones(ANTES_MULTI_EQ, DESPUES_MULTI_DEBIL)
        assert resultado.es_laundering is True

    def test_caso13_not_in_a_is_not_none(self) -> None:
        """not in pasa a is not None → laundering (rigor 7 → 3)."""
        resultado = comparar_aserciones(ANTES_NOT_IN, DESPUES_IS_NOT_NONE_2)
        assert resultado.es_laundering is True


class TestCasosEspecialesReunion:
    """Casos nuevos solicitados en la reunión del 9 de octubre."""

    def test_tautologia_res_eq_res(self) -> None:
        """assert res == res es una tautología → detecta laundering."""
        resultado = comparar_aserciones(ANTES_CONTRATO_REAL, DESPUES_TAUTO_RES_EQ_RES)
        assert resultado.es_laundering is True
        assert any("Tautología" in d.motivo for d in resultado.diferencias)

    def test_tautologia_assert_true(self) -> None:
        """assert True es una tautología → detecta laundering."""
        resultado = comparar_aserciones(ANTES_CONTRATO_REAL, DESPUES_TAUTO_ASSERT_TRUE)
        assert resultado.es_laundering is True
        assert any("Tautología" in d.motivo for d in resultado.diferencias)

    def test_tautologia_assert_1_eq_1(self) -> None:
        """assert 1 == 1 es una tautología constante → detecta laundering."""
        resultado = comparar_aserciones(ANTES_CONTRATO_REAL, DESPUES_TAUTO_ASSERT_1_EQ_1)
        assert resultado.es_laundering is True
        assert any("Tautología" in d.motivo for d in resultado.diferencias)

    def test_try_except_suprime_assertion_error(self) -> None:
        """try/except que captura AssertionError con pass → detecta laundering."""
        resultado = comparar_aserciones(
            ANTES_CONTRATO_REAL, DESPUES_TRY_EXCEPT_ASSERTION_ERROR
        )
        assert resultado.es_laundering is True
        assert any("try/except" in d.motivo for d in resultado.diferencias)

    def test_try_except_suprime_exception(self) -> None:
        """try/except que captura Exception general con pass → detecta laundering."""
        resultado = comparar_aserciones(
            ANTES_CONTRATO_REAL, DESPUES_TRY_EXCEPT_EXCEPTION_SWALLOWED
        )
        assert resultado.es_laundering is True
        assert any("try/except" in d.motivo for d in resultado.diferencias)

    def test_try_except_con_raise_no_es_laundering(self) -> None:
        """try/except que relanza la excepción con raise → permitido."""
        resultado = comparar_aserciones(
            ANTES_CONTRATO_REAL, DESPUES_TRY_EXCEPT_CON_RAISE
        )
        assert resultado.es_laundering is False

    def test_skip_decorador_detecta_laundering(self) -> None:
        """Decorador @pytest.mark.skip evasivo → detecta laundering."""
        resultado = comparar_aserciones(ANTES_CONTRATO_REAL, DESPUES_DECORADOR_SKIP)
        assert resultado.es_laundering is True
        assert any("skip" in d.motivo.lower() for d in resultado.diferencias)

    def test_skip_llamada_detecta_laundering(self) -> None:
        """Llamada directa pytest.skip() → detecta laundering."""
        resultado = comparar_aserciones(ANTES_CONTRATO_REAL, DESPUES_LLAMADA_PYTEST_SKIP)
        assert resultado.es_laundering is True
        assert any("skip" in d.motivo.lower() for d in resultado.diferencias)

    def test_xfail_decorador_detecta_laundering(self) -> None:
        """Decorador @pytest.mark.xfail evasivo → detecta laundering."""
        resultado = comparar_aserciones(ANTES_CONTRATO_REAL, DESPUES_DECORADOR_XFAIL)
        assert resultado.es_laundering is True
        assert any("xfail" in d.motivo.lower() for d in resultado.diferencias)

    def test_raises_mas_amplio_valueerror_a_exception(self) -> None:
        """pytest.raises(ValueError) pasa a pytest.raises(Exception) → detecta laundering."""
        resultado = comparar_aserciones(
            ANTES_RAISES_VALUE_ERROR, DESPUES_RAISES_EXCEPTION
        )
        assert resultado.es_laundering is True
        assert any("ampliado" in d.motivo for d in resultado.diferencias)

    def test_raises_mas_amplio_valueerror_a_base_exception(self) -> None:
        """pytest.raises(ValueError) pasa a pytest.raises(BaseException) → detecta laundering."""
        resultado = comparar_aserciones(
            ANTES_RAISES_VALUE_ERROR, DESPUES_RAISES_BASE_EXCEPTION
        )
        assert resultado.es_laundering is True
        assert any("ampliado" in d.motivo for d in resultado.diferencias)

    def test_raises_mas_amplio_keyerror_a_lookuperror(self) -> None:
        """pytest.raises(KeyError) pasa a pytest.raises(LookupError) → detecta laundering."""
        resultado = comparar_aserciones(
            ANTES_RAISES_KEY_ERROR, DESPUES_RAISES_LOOKUP_ERROR
        )
        assert resultado.es_laundering is True
        assert any("ampliado" in d.motivo for d in resultado.diferencias)


class TestSinLaundering:
    """Pares donde NO se debe detectar Assertion Laundering."""

    def test_caso2_mismas_aserciones(self) -> None:
        """Mismas aserciones antes y después → sin laundering (Criterio 5 obligatorio)."""
        resultado = comparar_aserciones(ANTES_Y_DESPUES_IGUALES, ANTES_Y_DESPUES_IGUALES)
        assert resultado.es_laundering is False
        assert len(resultado.diferencias) == 0

    def test_caso4_se_agregan_aserciones(self) -> None:
        """1 assert → 3 asserts (más cobertura) → sin laundering."""
        resultado = comparar_aserciones(ANTES_UN_ASSERT, DESPUES_TRES_ASSERTS)
        assert resultado.es_laundering is False

    def test_caso8_raises_se_mantiene(self) -> None:
        """pytest.raises se mantiene con la misma excepción → sin laundering."""
        resultado = comparar_aserciones(ANTES_RAISES_MANTIENE, DESPUES_RAISES_MANTIENE)
        assert resultado.es_laundering is False

    def test_caso10_true_a_eq_se_fortalece(self) -> None:
        """assert expr → assert expr == 42 → sin laundering (rigor sube)."""
        resultado = comparar_aserciones(ANTES_TRUE, DESPUES_EQ_VALOR)
        assert resultado.es_laundering is False

    def test_caso12_ne_se_mantiene(self) -> None:
        """!= se mantiene idéntico → sin laundering."""
        resultado = comparar_aserciones(ANTES_NE, DESPUES_NE)
        assert resultado.es_laundering is False

    def test_caso14_sin_aserciones_ambos(self) -> None:
        """Sin aserciones en ambos → sin laundering."""
        resultado = comparar_aserciones(ANTES_VACIO, DESPUES_VACIO)
        assert resultado.es_laundering is False

    def test_reordenar_aserciones_no_es_falso_positivo(self) -> None:
        """Reordenar aserciones legítimas no causa falso positivo."""
        resultado = comparar_aserciones(ANTES_ORDEN_A_B, DESPUES_ORDEN_B_A)
        assert resultado.es_laundering is False
        assert len(resultado.diferencias) == 0


# =========================================================================== #
# Extracción de patrones de aserción
# =========================================================================== #


@pytest.mark.parametrize(
    ("codigo", "tipo_esperado", "valor_esperado"),
    [
        ("assert x == 1", "eq", "1"),
        ("assert x != 0", "ne", "0"),
        ("assert x in [1, 2]", "in", "[1, 2]"),
        ("assert x not in [3]", "not_in", "[3]"),
        ("assert x is True", "is", "True"),
        ("assert x is not False", "is_not", "False"),
        ("assert x is None", "is_none", None),
        ("assert x is not None", "is_not_none", None),
        ("assert x", "true", None),
        ("assert not x", "false", None),
    ],
    ids=[
        "eq", "ne", "in", "not_in", "is", "is_not",
        "is_none", "is_not_none", "true", "false",
    ],
)
def test_extraccion_clasifica_tipo_correctamente(
    codigo: str, tipo_esperado: str, valor_esperado: str | None
) -> None:
    """Cada patrón de aserción se clasifica en el tipo correcto."""
    aserciones = extraer_aserciones(codigo)
    assert len(aserciones) == 1
    assert aserciones[0].tipo == tipo_esperado
    assert aserciones[0].valor == valor_esperado


def test_extraccion_pytest_raises() -> None:
    """pytest.raises se extrae como tipo 'raises' con la excepción como valor."""
    codigo = """\
import pytest

def test_error():
    with pytest.raises(ValueError):
        funcion(-1)
"""
    aserciones = extraer_aserciones(codigo)
    assert len(aserciones) == 1
    assert aserciones[0].tipo == "raises"
    assert aserciones[0].valor == "ValueError"


# =========================================================================== #
# Validaciones adicionales
# =========================================================================== #


def test_resumen_muestra_comparacion_contrato_vs_sintetizada() -> None:
    """El resumen contiene las etiquetas 'Aserción de contrato' y 'Aserción sintetizada'."""
    resultado = comparar_aserciones(ANTES_EQ, DESPUES_IS_NOT_NONE)
    assert "Aserción de contrato" in resultado.resumen
    assert "Aserción sintetizada" in resultado.resumen
    assert "LAUNDERING" in resultado.resumen


def test_resumen_sin_laundering_muestra_ok() -> None:
    """Cuando no hay laundering el resumen indica que todo está bien."""
    resultado = comparar_aserciones(ANTES_Y_DESPUES_IGUALES, ANTES_Y_DESPUES_IGUALES)
    assert "Sin laundering" in resultado.resumen


def test_jerarquia_rigor_es_coherente() -> None:
    """Cada tipo definido en RIGOR tiene un valor entero positivo."""
    assert all(isinstance(v, int) and v > 0 for v in RIGOR.values())
    assert RIGOR["raises"] > RIGOR["eq"] > RIGOR["in"] > RIGOR["is_not_none"] > RIGOR["true"]


def test_modulo_no_importa_llm() -> None:
    """El módulo laundering.py no depende de pyagent.llm (Criterio 4)."""
    import inspect

    import pyagent.analysis.laundering as modulo

    codigo_fuente = inspect.getsource(modulo)
    assert "pyagent.llm" not in codigo_fuente
    assert "LLMClient" not in codigo_fuente
    assert "FakeLLM" not in codigo_fuente

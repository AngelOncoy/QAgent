"""Pruebas de detección de Assertion Laundering (HU-16).

Sin IA, sin Docker, sin red.  Solo AST.

Criterio 5 de aceptación:
    Un test pytest con al menos un par antes/después con laundering
    (== valor pasa a is not None) y otro sin laundering clasifica
    cada par correctamente.
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

# ─── Caso 1 (laundering): eq → is not None (criterio 5 obligatorio) ───

ANTES_EQ = """\
def test_descuento():
    assert calcular_descuento(100, 50) == 50.0
"""

DESPUES_IS_NOT_NONE = """\
def test_descuento():
    assert calcular_descuento(100, 50) is not None
"""

# ─── Caso 2 (sin laundering): mismas aserciones (criterio 5 obligatorio) ───

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

# ─── Caso 6 (sin laundering): valor cambia pero tipo igual ───

ANTES_EQ_2 = """\
def test_valor():
    assert f(1) == 2
"""

DESPUES_EQ_3 = """\
def test_valor():
    assert f(1) == 3
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


# =========================================================================== #
# Evidencia de aceptación — Criterio 5 de HU-16
# =========================================================================== #


class TestLaunderingDetectado:
    """Pares donde se espera que se detecte Assertion Laundering."""

    def test_caso1_eq_a_is_not_none(self) -> None:
        """== valor pasa a is not None → laundering (criterio 5 obligatorio)."""
        resultado = comparar_aserciones(ANTES_EQ, DESPUES_IS_NOT_NONE)
        assert resultado.es_laundering is True
        assert len(resultado.diferencias) >= 1
        assert resultado.aserciones_contrato[0].tipo == "eq"
        assert resultado.aserciones_sintetizadas[0].tipo == "is_not_none"
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
        # La raises (rigor 10) fue reemplazada por is_not_none (rigor 3)
        assert any(d.contrato.tipo == "raises" for d in resultado.diferencias)

    def test_caso7_eq_a_in(self) -> None:
        """== valor pasa a in lista → laundering (rigor 9 → 6)."""
        resultado = comparar_aserciones(ANTES_EQ_STR, DESPUES_IN_LISTA)
        assert resultado.es_laundering is True
        assert resultado.aserciones_contrato[0].tipo == "eq"
        assert resultado.aserciones_sintetizadas[0].tipo == "in"

    def test_caso9_eq_a_true(self) -> None:
        """== valor pasa a assert expr (booleano) → laundering (rigor 9 → 1)."""
        resultado = comparar_aserciones(ANTES_EQ_LEN, DESPUES_SOLO_ASSERT)
        assert resultado.es_laundering is True
        assert resultado.aserciones_contrato[0].tipo == "eq"
        assert resultado.aserciones_sintetizadas[0].tipo == "true"

    def test_caso11_multi_una_debilitada(self) -> None:
        """3 asserts iguales, pero la segunda baja de eq a is_not_none → laundering."""
        resultado = comparar_aserciones(ANTES_MULTI_EQ, DESPUES_MULTI_DEBIL)
        assert resultado.es_laundering is True
        assert len(resultado.aserciones_contrato) == 3
        assert len(resultado.aserciones_sintetizadas) == 3
        # Solo la segunda aserción debería estar en diferencias
        assert len(resultado.diferencias) == 1
        assert resultado.diferencias[0].contrato.tipo == "eq"
        assert resultado.diferencias[0].sintetizada.tipo == "is_not_none"

    def test_caso13_not_in_a_is_not_none(self) -> None:
        """not in pasa a is not None → laundering (rigor 7 → 3)."""
        resultado = comparar_aserciones(ANTES_NOT_IN, DESPUES_IS_NOT_NONE_2)
        assert resultado.es_laundering is True
        assert resultado.aserciones_contrato[0].tipo == "not_in"
        assert resultado.aserciones_sintetizadas[0].tipo == "is_not_none"


class TestSinLaundering:
    """Pares donde NO se debe detectar Assertion Laundering."""

    def test_caso2_mismas_aserciones(self) -> None:
        """Mismas aserciones antes y después → sin laundering (criterio 5 obligatorio)."""
        resultado = comparar_aserciones(ANTES_Y_DESPUES_IGUALES, ANTES_Y_DESPUES_IGUALES)
        assert resultado.es_laundering is False
        assert len(resultado.diferencias) == 0

    def test_caso4_se_agregan_aserciones(self) -> None:
        """1 assert → 3 asserts (más cobertura) → sin laundering."""
        resultado = comparar_aserciones(ANTES_UN_ASSERT, DESPUES_TRES_ASSERTS)
        assert resultado.es_laundering is False
        assert len(resultado.aserciones_sintetizadas) > len(resultado.aserciones_contrato)

    def test_caso6_valor_cambia_tipo_igual(self) -> None:
        """== 2 pasa a == 3 → sin laundering (eq sigue siendo eq)."""
        resultado = comparar_aserciones(ANTES_EQ_2, DESPUES_EQ_3)
        assert resultado.es_laundering is False
        assert resultado.aserciones_contrato[0].tipo == "eq"
        assert resultado.aserciones_sintetizadas[0].tipo == "eq"

    def test_caso8_raises_se_mantiene(self) -> None:
        """pytest.raises se mantiene → sin laundering."""
        resultado = comparar_aserciones(ANTES_RAISES_MANTIENE, DESPUES_RAISES_MANTIENE)
        assert resultado.es_laundering is False
        assert resultado.aserciones_contrato[0].tipo == "raises"
        assert resultado.aserciones_sintetizadas[0].tipo == "raises"

    def test_caso10_true_a_eq_se_fortalece(self) -> None:
        """assert expr → assert expr == 42 → sin laundering (rigor sube)."""
        resultado = comparar_aserciones(ANTES_TRUE, DESPUES_EQ_VALOR)
        assert resultado.es_laundering is False
        assert resultado.aserciones_contrato[0].tipo == "true"
        assert resultado.aserciones_sintetizadas[0].tipo == "eq"

    def test_caso12_ne_se_mantiene(self) -> None:
        """!= se mantiene → sin laundering."""
        resultado = comparar_aserciones(ANTES_NE, DESPUES_NE)
        assert resultado.es_laundering is False

    def test_caso14_sin_aserciones_ambos(self) -> None:
        """Sin aserciones en ambos → sin laundering (no hay degradación)."""
        resultado = comparar_aserciones(ANTES_VACIO, DESPUES_VACIO)
        assert resultado.es_laundering is False
        assert len(resultado.aserciones_contrato) == 0
        assert len(resultado.aserciones_sintetizadas) == 0


# =========================================================================== #
# Caso 15: extracción correcta de todos los tipos de aserción
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
# Validaciones del resumen y la tabla comparativa (criterio 3)
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


# =========================================================================== #
# Validación de la jerarquía de rigor
# =========================================================================== #


def test_jerarquia_rigor_es_coherente() -> None:
    """Cada tipo definido en RIGOR tiene un valor entero positivo."""
    assert all(isinstance(v, int) and v > 0 for v in RIGOR.values())
    # raises es el más estricto, true/false el menos
    assert RIGOR["raises"] > RIGOR["eq"] > RIGOR["in"] > RIGOR["is_not_none"] > RIGOR["true"]


# =========================================================================== #
# Criterio 4: sin llamadas a IA
# =========================================================================== #


def test_modulo_no_importa_llm() -> None:
    """El módulo laundering.py no depende de pyagent.llm (criterio 4)."""
    import inspect

    import pyagent.analysis.laundering as modulo

    codigo_fuente = inspect.getsource(modulo)
    assert "pyagent.llm" not in codigo_fuente
    assert "LLMClient" not in codigo_fuente
    assert "FakeLLM" not in codigo_fuente

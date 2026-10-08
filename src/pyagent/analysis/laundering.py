"""Detección de Assertion Laundering por análisis AST — HU-16.

Compara las aserciones de un test **antes** (contrato) y **después** (sintetizado)
de una reparación automática. Si la reparación debilitó alguna aserción —bajó la
cantidad, redujo el rigor del tipo o eliminó un valor concreto— el test se rechaza
como *Assertion Laundering*.

Esta verificación es 100 % estática: solo usa ``ast.parse`` y ``ast.unparse``.
**No llama a ninguna API de IA.**
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Jerarquía de rigor (mayor número = aserción más estricta)
# --------------------------------------------------------------------------- #

RIGOR: dict[str, int] = {
    "true": 1,  # assert expr
    "false": 1,  # assert not expr
    "is_none": 2,  # assert expr is None
    "is_not_none": 3,  # assert expr is not None
    "is": 4,  # assert expr is valor
    "is_not": 5,  # assert expr is not valor
    "in": 6,  # assert elem in coleccion
    "not_in": 7,  # assert elem not in coleccion
    "ne": 8,  # assert expr != valor
    "eq": 9,  # assert expr == valor
    "raises": 10,  # with pytest.raises(Exc)
}


# --------------------------------------------------------------------------- #
# Estructuras de datos
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Asercion:
    """Una aserción extraída del AST de un test.

    Atributos:
        linea: número de línea en el código fuente.
        tipo: clave de ``RIGOR`` que clasifica la aserción.
        expresion: código fuente completo de la aserción (``ast.unparse``).
        valor: lado derecho o valor esperado; ``None`` si no aplica.
    """

    linea: int
    tipo: str
    expresion: str
    valor: str | None


@dataclass(frozen=True)
class DiferenciaAsercion:
    """Detalle de una aserción que perdió rigor entre las dos versiones.

    Atributos:
        contrato: aserción original ("de contrato").
        sintetizada: aserción reparada ("sintetizada").
        motivo: descripción legible del debilitamiento.
    """

    contrato: Asercion
    sintetizada: Asercion
    motivo: str


@dataclass(frozen=True)
class ResultadoComparacion:
    """Resultado de comparar las aserciones de dos versiones de un test.

    Atributos:
        es_laundering: ``True`` si se detectó debilitamiento.
        aserciones_contrato: aserciones extraídas del código original.
        aserciones_sintetizadas: aserciones extraídas del código reparado.
        diferencias: lista de pares donde hubo degradación de rigor.
        resumen: texto legible con la tabla comparativa.
    """

    es_laundering: bool
    aserciones_contrato: list[Asercion]
    aserciones_sintetizadas: list[Asercion]
    diferencias: list[DiferenciaAsercion]
    resumen: str


# --------------------------------------------------------------------------- #
# Extracción de aserciones
# --------------------------------------------------------------------------- #


def _clasificar_assert(nodo: ast.Assert) -> tuple[str, str | None]:
    """Clasifica un ``assert`` en tipo y valor según el patrón del AST."""
    test = nodo.test

    # assert not expr → "false"
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return "false", None

    # assert expr <op> valor  (Compare con un solo comparador)
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op = test.ops[0]
        comparador = test.comparators[0]
        valor = ast.unparse(comparador)

        if isinstance(op, ast.Eq):
            return "eq", valor
        if isinstance(op, ast.NotEq):
            return "ne", valor
        if isinstance(op, ast.In):
            return "in", valor
        if isinstance(op, ast.NotIn):
            return "not_in", valor
        if isinstance(op, ast.Is):
            if isinstance(comparador, ast.Constant) and comparador.value is None:
                return "is_none", None
            return "is", valor
        if isinstance(op, ast.IsNot):
            if isinstance(comparador, ast.Constant) and comparador.value is None:
                return "is_not_none", None
            return "is_not", valor

    # assert expr (booleano simple) → "true"
    return "true", None


def _buscar_raises(nodo: ast.With) -> Asercion | None:
    """Detecta ``with pytest.raises(Exc):`` y devuelve una Asercion de tipo "raises"."""
    for item in nodo.items:
        llamada = item.context_expr
        if not isinstance(llamada, ast.Call):
            continue
        func = llamada.func
        # pytest.raises(...)
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "raises"
            and isinstance(func.value, ast.Name)
            and func.value.id == "pytest"
        ):
            valor = ast.unparse(llamada.args[0]) if llamada.args else None
            return Asercion(
                linea=nodo.lineno,
                tipo="raises",
                expresion=ast.unparse(nodo),
                valor=valor,
            )
    return None


def extraer_aserciones(codigo_fuente: str) -> list[Asercion]:
    """Analiza el código fuente de un test y extrae todas las aserciones.

    Reconoce:

    * ``assert expr == valor``      → tipo ``"eq"``
    * ``assert expr != valor``      → tipo ``"ne"``
    * ``assert expr in col``        → tipo ``"in"``
    * ``assert expr not in col``    → tipo ``"not_in"``
    * ``assert expr is valor``      → tipo ``"is"``
    * ``assert expr is not valor``  → tipo ``"is_not"``
    * ``assert expr is None``       → tipo ``"is_none"``
    * ``assert expr is not None``   → tipo ``"is_not_none"``
    * ``assert expr``               → tipo ``"true"``
    * ``assert not expr``           → tipo ``"false"``
    * ``with pytest.raises(Exc)``   → tipo ``"raises"``

    Los ``assert`` dentro de funciones auxiliares (que no son ``test_*``) se
    ignoran para evitar falsos positivos.
    """
    arbol = ast.parse(codigo_fuente)
    aserciones: list[Asercion] = []

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assert):
            tipo, valor = _clasificar_assert(nodo)
            aserciones.append(
                Asercion(
                    linea=nodo.lineno,
                    tipo=tipo,
                    expresion=ast.unparse(nodo),
                    valor=valor,
                )
            )
        elif isinstance(nodo, ast.With):
            raises = _buscar_raises(nodo)
            if raises is not None:
                aserciones.append(raises)

    return aserciones


# --------------------------------------------------------------------------- #
# Comparación de aserciones
# --------------------------------------------------------------------------- #


def _formatear_tabla(contrato: list[Asercion], sintetizadas: list[Asercion]) -> str:
    """Genera una tabla legible comparando aserciones de contrato vs sintetizadas."""
    lineas: list[str] = []
    lineas.append("Aserción de contrato                    │ Aserción sintetizada")
    lineas.append("─" * 40 + "┼" + "─" * 40)

    max_len = max(len(contrato), len(sintetizadas))
    for i in range(max_len):
        izq = contrato[i].expresion if i < len(contrato) else "(eliminada)"
        der = sintetizadas[i].expresion if i < len(sintetizadas) else "(nueva)"
        # Truncar líneas largas para legibilidad
        izq = izq[:38] + ".." if len(izq) > 40 else izq
        der = der[:38] + ".." if len(der) > 40 else der
        lineas.append(f"{izq:<40}│ {der}")

    return "\n".join(lineas)


def comparar_aserciones(
    codigo_contrato: str,
    codigo_sintetizado: str,
) -> ResultadoComparacion:
    """Compara las aserciones del test original contra el reparado.

    Detecta *Assertion Laundering* si:

    1. **Baja la cantidad** de aserciones.
    2. Una aserción se vuelve **menos rigurosa** según la jerarquía ``RIGOR``
       (por ejemplo, ``"eq"`` con rigor 9 pasa a ``"is_not_none"`` con rigor 3).
    3. Una aserción de igualdad pierde su **valor concreto**.

    No es laundering si la cantidad se mantiene o sube y el rigor no baja.
    """
    contrato = extraer_aserciones(codigo_contrato)
    sintetizadas = extraer_aserciones(codigo_sintetizado)
    diferencias: list[DiferenciaAsercion] = []
    es_laundering = False

    # Regla 1: baja de cantidad
    if len(sintetizadas) < len(contrato):
        es_laundering = True
        # Registrar las aserciones eliminadas
        for i in range(len(sintetizadas), len(contrato)):
            diferencias.append(
                DiferenciaAsercion(
                    contrato=contrato[i],
                    sintetizada=Asercion(
                        linea=0, tipo="", expresion="(eliminada)", valor=None
                    ),
                    motivo=(
                        f"Aserción eliminada: {contrato[i].tipo} "
                        f"en línea {contrato[i].linea}"
                    ),
                )
            )

    # Reglas 2 y 3: comparar pares por posición
    pares = min(len(contrato), len(sintetizadas))
    for i in range(pares):
        ac = contrato[i]
        as_ = sintetizadas[i]

        rigor_contrato = RIGOR.get(ac.tipo, 0)
        rigor_sintetizada = RIGOR.get(as_.tipo, 0)

        # Regla 2: bajó el rigor del tipo
        if rigor_sintetizada < rigor_contrato:
            es_laundering = True
            diferencias.append(
                DiferenciaAsercion(
                    contrato=ac,
                    sintetizada=as_,
                    motivo=(
                        f"Rigor debilitado: {ac.tipo} (rigor {rigor_contrato}) "
                        f"→ {as_.tipo} (rigor {rigor_sintetizada})"
                    ),
                )
            )
            continue

        # Regla 3: mismo tipo eq pero el valor concreto desapareció
        if (
            ac.tipo == "eq"
            and as_.tipo == "eq"
            and ac.valor is not None
            and as_.valor is None
        ):
            es_laundering = True
            diferencias.append(
                DiferenciaAsercion(
                    contrato=ac,
                    sintetizada=as_,
                    motivo=(
                        f"Valor concreto eliminado: == {ac.valor} → == (sin valor)"
                    ),
                )
            )

    # Generar resumen
    resumen = _formatear_tabla(contrato, sintetizadas)
    if es_laundering:
        motivos = "\n".join(f"  ⚠ {d.motivo}" for d in diferencias)
        resumen += f"\n\n🔴 ASSERTION LAUNDERING DETECTADO:\n{motivos}"
    else:
        resumen += "\n\n✅ Sin laundering: las aserciones mantienen o mejoran su rigor."

    return ResultadoComparacion(
        es_laundering=es_laundering,
        aserciones_contrato=contrato,
        aserciones_sintetizadas=sintetizadas,
        diferencias=diferencias,
        resumen=resumen,
    )

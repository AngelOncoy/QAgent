"""Detección de Assertion Laundering por análisis AST — HU-16.

Compara las aserciones de un test **antes** (contrato) y **después** (sintetizado)
de una reparación automática. Si la reparación debilitó alguna aserción —bajó la
cantidad, redujo el rigor del tipo, cambió o eliminó el valor esperado, introdujo
tautologías, suprimió fallos con try/except, evadió la prueba con skip/xfail,
o amplió el tipo de excepción en pytest.raises— el test se rechaza como
*Assertion Laundering*.

Corrige además falsos positivos por reordenamiento de aserciones emparejando por
sujeto de prueba antes de comparar.

Esta verificación es 100 % estática: solo usa ``ast.parse`` y ``ast.unparse``.
**No llama a ninguna API de IA.**
"""

from __future__ import annotations

import ast
import builtins
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
        sujeto: expresión evaluada (lado izquierdo o cuerpo bajo prueba).
    """

    linea: int
    tipo: str
    expresion: str
    valor: str | None
    sujeto: str = ""


@dataclass(frozen=True)
class DiferenciaAsercion:
    """Detalle de una aserción que perdió rigor o fue alterada entre versiones.

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
        es_laundering: ``True`` si se detectó debilitamiento o evasión.
        aserciones_contrato: aserciones extraídas del código original.
        aserciones_sintetizadas: aserciones extraídas del código reparado.
        diferencias: lista de pares donde hubo degradación o alteración.
        resumen: texto legible con la tabla comparativa.
    """

    es_laundering: bool
    aserciones_contrato: list[Asercion]
    aserciones_sintetizadas: list[Asercion]
    diferencias: list[DiferenciaAsercion]
    resumen: str


# --------------------------------------------------------------------------- #
# Extracción de aserciones y patrones
# --------------------------------------------------------------------------- #


def _clasificar_assert(nodo: ast.Assert) -> tuple[str, str | None, str]:
    """Clasifica un ``assert`` en (tipo, valor, sujeto) según el patrón del AST."""
    test = nodo.test

    # assert not expr → "false"
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        sujeto = ast.unparse(test.operand).strip()
        return "false", None, sujeto

    # assert expr <op> valor (Compare con un solo operador)
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op = test.ops[0]
        comparador = test.comparators[0]
        sujeto = ast.unparse(test.left).strip()
        valor = ast.unparse(comparador).strip()

        if isinstance(op, ast.Eq):
            return "eq", valor, sujeto
        if isinstance(op, ast.NotEq):
            return "ne", valor, sujeto
        if isinstance(op, ast.In):
            return "in", valor, sujeto
        if isinstance(op, ast.NotIn):
            return "not_in", valor, sujeto
        if isinstance(op, ast.Is):
            if isinstance(comparador, ast.Constant) and comparador.value is None:
                return "is_none", None, sujeto
            return "is", valor, sujeto
        if isinstance(op, ast.IsNot):
            if isinstance(comparador, ast.Constant) and comparador.value is None:
                return "is_not_none", None, sujeto
            return "is_not", valor, sujeto

    # assert expr (booleano simple) → "true"
    sujeto = ast.unparse(test).strip()
    return "true", None, sujeto


def _buscar_raises(nodo: ast.With) -> Asercion | None:
    """Detecta ``with pytest.raises(Exc):`` y devuelve una Asercion de tipo 'raises'."""
    for item in nodo.items:
        llamada = item.context_expr
        if not isinstance(llamada, ast.Call):
            continue
        func = llamada.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "raises"
            and isinstance(func.value, ast.Name)
            and func.value.id == "pytest"
        ):
            valor = ast.unparse(llamada.args[0]).strip() if llamada.args else None
            sujeto = "; ".join(ast.unparse(s).strip() for s in nodo.body)
            return Asercion(
                linea=nodo.lineno,
                tipo="raises",
                expresion=ast.unparse(nodo),
                valor=valor,
                sujeto=sujeto,
            )
    return None


def extraer_aserciones(codigo_fuente: str) -> list[Asercion]:
    """Analiza el código fuente de un test y extrae todas las aserciones."""
    arbol = ast.parse(codigo_fuente)
    aserciones: list[Asercion] = []

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assert):
            tipo, valor, sujeto = _clasificar_assert(nodo)
            aserciones.append(
                Asercion(
                    linea=nodo.lineno,
                    tipo=tipo,
                    expresion=ast.unparse(nodo),
                    valor=valor,
                    sujeto=sujeto,
                )
            )
        elif isinstance(nodo, ast.With):
            raises = _buscar_raises(nodo)
            if raises is not None:
                aserciones.append(raises)

    return aserciones


# --------------------------------------------------------------------------- #
# Detección de casos especiales: Tautologías, try/except y skip/xfail
# --------------------------------------------------------------------------- #


def _es_tautologia(nodo: ast.Assert) -> tuple[bool, str]:
    """Determina si un assert es una tautología (siempre verdadero)."""
    test = nodo.test

    # 1. assert True
    if isinstance(test, ast.Constant) and test.value is True:
        return True, "assert True es siempre verdadero"

    # 2. assert <constante no vacía> (ej. assert 1, assert "ok")
    if isinstance(test, ast.Constant) and bool(test.value) is True:
        return True, f"Aserción de constante verdadera ({ast.unparse(test)})"

    # 3. assert not False, assert not 0
    if (
        isinstance(test, ast.UnaryOp)
        and isinstance(test.op, ast.Not)
        and isinstance(test.operand, ast.Constant)
        and bool(test.operand.value) is False
    ):
        return True, f"assert not {ast.unparse(test.operand)} es siempre verdadero"

    # 4. Compare LHS == RHS, LHS is RHS, LHS <= RHS, LHS >= RHS
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op = test.ops[0]
        if isinstance(op, (ast.Eq, ast.Is, ast.LtE, ast.GtE)):
            izq = ast.unparse(test.left).strip()
            der = ast.unparse(test.comparators[0]).strip()
            if izq == der:
                return (
                    True,
                    f"Comparación tautológica de una expresión consigo misma ({izq} == {der})",
                )

        # 5. Membresía tautológica: assert x in [x]
        if isinstance(op, ast.In):
            izq = ast.unparse(test.left).strip()
            comp = test.comparators[0]
            if isinstance(comp, (ast.List, ast.Tuple, ast.Set)):
                elts = [ast.unparse(e).strip() for e in comp.elts]
                if all(e == izq for e in elts) and elts:
                    return True, f"Membresía tautológica: {izq} in [{', '.join(elts)}]"

    return False, ""


def _detectar_try_except_silencioso(arbol: ast.AST) -> list[str]:
    """Detecta bloques try/except que capturan y suprimen excepciones o aserciones."""
    motivos: list[str] = []
    peligrosas = {"AssertionError", "Exception", "BaseException"}

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Try):
            for handler in nodo.handlers:
                nombre_exc = None
                if handler.type is None:
                    nombre_exc = "except general"
                elif isinstance(handler.type, ast.Name):
                    nombre_exc = handler.type.id
                elif isinstance(handler.type, ast.Attribute):
                    nombre_exc = handler.type.attr

                es_peligrosa = handler.type is None or nombre_exc in peligrosas
                if es_peligrosa:
                    relanza = False
                    for sub in ast.walk(handler):
                        if isinstance(sub, ast.Raise):
                            relanza = True
                            break
                        if isinstance(sub, ast.Call):
                            llamada = ast.unparse(sub.func)
                            if "pytest.fail" in llamada:
                                relanza = True
                                break

                    if not relanza:
                        motivo = (
                            f"try/except en línea {handler.lineno} suprime "
                            f"'{nombre_exc or 'excepción'}' sin relanzar ni fallar"
                        )
                        motivos.append(motivo)

    return motivos


def _detectar_skip_xfail(arbol: ast.AST) -> list[str]:
    """Detecta evasión de pruebas mediante decoradores o llamadas a skip/xfail."""
    motivos: list[str] = []
    evasiones = {"skip", "skipif", "xfail"}

    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in nodo.decorator_list:
                texto = ast.unparse(deco)
                for ev in evasiones:
                    if f"pytest.mark.{ev}" in texto or f"@{ev}" in texto:
                        motivos.append(
                            f"Prueba evadida con decorador '@{texto}' en función '{nodo.name}'"
                        )
                        break
        if isinstance(nodo, ast.Call):
            func_txt = ast.unparse(nodo.func)
            if func_txt in ("pytest.skip", "pytest.xfail"):
                motivos.append(f"Prueba evadida con llamada directa a '{func_txt}()'")

    return motivos


def _es_raises_mas_amplio(especifica: str | None, candidata: str | None) -> bool:
    """Verifica si `candidata` es una excepción más amplia / genérica que `especifica`."""
    if not especifica or not candidata or especifica == candidata:
        return False

    if candidata in ("Exception", "BaseException"):
        return not (candidata == "Exception" and especifica == "BaseException")

    cls_esp = getattr(builtins, especifica, None)
    cls_cand = getattr(builtins, candidata, None)
    if (
        isinstance(cls_esp, type)
        and isinstance(cls_cand, type)
        and issubclass(cls_esp, BaseException)
        and issubclass(cls_cand, BaseException)
    ):
        return issubclass(cls_esp, cls_cand)

    return False


# --------------------------------------------------------------------------- #
# Emparejamiento y comparación de aserciones
# --------------------------------------------------------------------------- #


def _emparejar_aserciones(
    contrato: list[Asercion], sintetizadas: list[Asercion]
) -> list[tuple[Asercion | None, Asercion | None]]:
    """Empareja aserciones evitando falsos positivos por reordenamiento."""
    pares: list[tuple[Asercion | None, Asercion | None]] = []
    pc = list(contrato)
    ps = list(sintetizadas)

    # Paso 1: Coincidencias exactas (sujeto, tipo, valor)
    for ac in list(pc):
        for as_ in list(ps):
            if ac.sujeto == as_.sujeto and ac.tipo == as_.tipo and ac.valor == as_.valor:
                pares.append((ac, as_))
                pc.remove(ac)
                ps.remove(as_)
                break

    # Paso 2: Coincidencias por sujeto (mismo sujeto, diferente tipo o valor)
    for ac in list(pc):
        for as_ in list(ps):
            if ac.sujeto and ac.sujeto == as_.sujeto:
                pares.append((ac, as_))
                pc.remove(ac)
                ps.remove(as_)
                break

    # Paso 3: Emparejar restantes por orden posicional
    while pc and ps:
        pares.append((pc.pop(0), ps.pop(0)))

    # Paso 4: Huérfanos
    for ac in pc:
        pares.append((ac, None))
    for as_ in ps:
        pares.append((None, as_))

    return pares


def _formatear_tabla(pares: list[tuple[Asercion | None, Asercion | None]]) -> str:
    """Genera una tabla legible comparando aserciones de contrato vs sintetizadas."""
    lineas: list[str] = []
    lineas.append("Aserción de contrato                    │ Aserción sintetizada")
    lineas.append("─" * 40 + "┼" + "─" * 40)

    for ac, as_ in pares:
        izq = ac.expresion if ac is not None else "(nueva)"
        der = as_.expresion if as_ is not None else "(eliminada)"
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
    2. Una aserción se vuelve **menos rigurosa** según la jerarquía ``RIGOR``.
    3. Una aserción de igualdad pierde o **cambia su valor esperado**.
    4. Se introduce una **tautología** (aserción que siempre es verdadera).
    5. Se introducen bloques **try/except que suprimen fallos**.
    6. Se evade la prueba con decoradores o llamadas a **skip / xfail**.
    7. Se **amplía la excepción** en ``pytest.raises()`` (e.g. ValueError → Exception).

    Corrige además falsos positivos por reordenamiento emparejando por sujeto.
    """
    contrato = extraer_aserciones(codigo_contrato)
    sintetizadas = extraer_aserciones(codigo_sintetizado)
    diferencias: list[DiferenciaAsercion] = []
    es_laundering = False

    arbol_sint = ast.parse(codigo_sintetizado)
    arbol_cont = ast.parse(codigo_contrato)

    # 1. Detección de skip / xfail
    skips_cont = set(_detectar_skip_xfail(arbol_cont))
    skips_sint = _detectar_skip_xfail(arbol_sint)
    for ev in skips_sint:
        if ev not in skips_cont:
            es_laundering = True
            diferencias.append(
                DiferenciaAsercion(
                    contrato=Asercion(0, "", "(prueba activa)", None),
                    sintetizada=Asercion(0, "skip_xfail", ev, None),
                    motivo=ev,
                )
            )

    # 2. Detección de try/except que silencia fallos
    tries_cont = set(_detectar_try_except_silencioso(arbol_cont))
    tries_sint = _detectar_try_except_silencioso(arbol_sint)
    for tr in tries_sint:
        if tr not in tries_cont:
            es_laundering = True
            diferencias.append(
                DiferenciaAsercion(
                    contrato=Asercion(0, "", "(sin try/except silenciador)", None),
                    sintetizada=Asercion(0, "try_except", tr, None),
                    motivo=tr,
                )
            )

    # 3. Detección de tautologías en el código sintetizado
    for nodo in ast.walk(arbol_sint):
        if isinstance(nodo, ast.Assert):
            es_tauto, motivo_tauto = _es_tautologia(nodo)
            if es_tauto:
                es_laundering = True
                diferencias.append(
                    DiferenciaAsercion(
                        contrato=Asercion(0, "", "(aserción estricta de contrato)", None),
                        sintetizada=Asercion(
                            nodo.lineno, "tautologia", ast.unparse(nodo), None
                        ),
                        motivo=f"Tautología detectada: {motivo_tauto}",
                    )
                )

    # 4. Regla de cantidad
    if len(sintetizadas) < len(contrato):
        es_laundering = True

    # Emparejamiento inteligente de aserciones
    pares = _emparejar_aserciones(contrato, sintetizadas)

    for ac, as_ in pares:
        if ac is not None and as_ is None:
            diferencias.append(
                DiferenciaAsercion(
                    contrato=ac,
                    sintetizada=Asercion(0, "", "(eliminada)", None),
                    motivo=f"Aserción eliminada: {ac.tipo} en línea {ac.linea}",
                )
            )
            continue

        if ac is None or as_ is None:
            continue

        # Regla de raises más amplio
        if (
            ac.tipo == "raises"
            and as_.tipo == "raises"
            and _es_raises_mas_amplio(ac.valor, as_.valor)
        ):
            es_laundering = True
            diferencias.append(
                DiferenciaAsercion(
                    contrato=ac,
                    sintetizada=as_,
                    motivo=(
                        f"pytest.raises ampliado: se esperaba '{ac.valor}', "
                        f"pero se amplió a '{as_.valor}'"
                    ),
                )
            )
            continue

        rigor_contrato = RIGOR.get(ac.tipo, 0)
        rigor_sintetizada = RIGOR.get(as_.tipo, 0)

        # Regla de rigor debilitado
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

        # Regla de valor esperado cambiado en igualdad (==)
        if ac.tipo == "eq" and as_.tipo == "eq":
            if ac.valor is not None and as_.valor is None:
                es_laundering = True
                diferencias.append(
                    DiferenciaAsercion(
                        contrato=ac,
                        sintetizada=as_,
                        motivo=f"Valor concreto eliminado: == {ac.valor} → == (sin valor)",
                    )
                )
            elif (
                ac.valor is not None
                and as_.valor is not None
                and ac.valor != as_.valor
            ):
                es_laundering = True
                diferencias.append(
                    DiferenciaAsercion(
                        contrato=ac,
                        sintetizada=as_,
                        motivo=(
                            f"Valor esperado cambiado: se esperaba == {ac.valor}, "
                            f"pero se cambió a == {as_.valor}"
                        ),
                    )
                )
            continue

        # Regla de valor esperado cambiado en 'is' o 'is_not'
        if ac.tipo in ("is", "is_not") and as_.tipo == ac.tipo:
            if (
                ac.valor is not None
                and as_.valor is not None
                and ac.valor != as_.valor
            ):
                es_laundering = True
                diferencias.append(
                    DiferenciaAsercion(
                        contrato=ac,
                        sintetizada=as_,
                        motivo=(
                            f"Valor esperado cambiado: se esperaba {ac.tipo} {ac.valor}, "
                            f"pero se cambió a {as_.tipo} {as_.valor}"
                        ),
                    )
                )
            continue

        # Regla de colección esperada cambiada en 'in' o 'not_in'
        if ac.tipo in ("in", "not_in") and as_.tipo == ac.tipo:
            if (
                ac.valor is not None
                and as_.valor is not None
                and ac.valor != as_.valor
            ):
                es_laundering = True
                diferencias.append(
                    DiferenciaAsercion(
                        contrato=ac,
                        sintetizada=as_,
                        motivo=(
                            f"Colección esperada cambiada en '{ac.tipo}': se esperaba {ac.valor}, "
                            f"pero se cambió a {as_.valor}"
                        ),
                    )
                )
            continue

    # Generar resumen
    resumen = _formatear_tabla(pares)
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

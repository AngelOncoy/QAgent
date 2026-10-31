"""Oráculo estático Java: vincula cada aserción al caso del Planner (#184).

Es conservador: rechaza construcciones no demostrables, sin evaluar Java ni
consultar IA. La compilación y la ejecución real corresponden al sandbox #182.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from tree_sitter import Node

from qagent.lenguajes.java_aserciones import (
    NO_LITERAL,
    AsercionJava,
    analizar_junit,
    argumentos,
    literal,
    nodos,
    resolver,
    texto,
)
from qagent.lenguajes.treesitter import obtener_parser


def validar_java(
    contrato: dict[str, Any], codigo: str, contexto: dict[str, Any] | None = None
) -> str | None:
    """Comprueba JUnit real, entradas, esperado/excepción y Mockito de constructor.

    Con contexto verifica también paquete, clase y constructores de la fuente.
    Cada aserción debe corresponder a un caso del contrato y cada caso necesita
    una comprobación. No acepta helpers, control de flujo ni aserciones ajenas.
    """
    try:
        analisis = analizar_junit(codigo)
        problema = _validar(contrato, analisis, contexto)
    except (SyntaxError, ValueError, RecursionError, KeyError, TypeError) as error:
        problema = str(error) or "no se pudo demostrar el oráculo del test Java."
    return "Oráculo inválido: " + problema if problema else None


def _validar(contrato, analisis, contexto):
    if analisis.evasiones:
        return analisis.evasiones[0]
    if not analisis.aserciones:
        return "el test no contiene aserciones JUnit verificables."
    if any(n.type == "field_declaration" for n in nodos(analisis.raiz)):
        return "usa variables locales estables; los campos de la prueba no son oráculos demostrables."
    clase, metodo = contrato["objetivo"].rsplit(".", 1)
    clase_test = "_".join(clase.split(".")) + "Test"
    clases = [n for n in analisis.raiz.named_children if n.type == "class_declaration"]
    if len(clases) != 1 or texto(clases[0].child_by_field_name("name")) != clase_test:
        return f"se requiere la clase de prueba {clase_test}."
    if contexto is not None:
        paquete = next(
            (
                texto(n.named_children[-1])
                for n in analisis.raiz.named_children
                if n.type == "package_declaration"
            ),
            "",
        )
        if paquete != contexto["paquete"]:
            return "el paquete de la prueba no coincide con la fuente."
        problema = _imports_coherentes(analisis.raiz, contexto, contrato)
        if problema:
            return problema
    for prueba in analisis.pruebas:
        if not any(a.prueba == prueba for a in analisis.aserciones):
            return f"el método {prueba} no comprueba ningún caso."
    if len(analisis.aserciones) != len(contrato["casos"]):
        return "debe haber una aserción del contrato por caso, sin aserciones ajenas o tautologías."
    parametros, es_static, retorno = _firma(contrato["firma"])
    disponibles = list(analisis.aserciones)
    usados: set[int] = set()
    for caso in contrato["casos"]:
        entrada = caso.get("entrada")
        if isinstance(entrada, dict):
            if set(entrada) != set(parametros):
                return f"las entradas del caso {caso['id']} no corresponden a su firma."
            esperados = [entrada[p] for p in parametros]
        elif isinstance(entrada, list):
            esperados = entrada
        elif entrada is None and not parametros:
            esperados = []
        else:
            return f"las entradas del caso {caso['id']} no son verificables."
        encontrada = None
        for indice, asercion in enumerate(disponibles):
            llamada = _llamada(asercion)
            if llamada is None or texto(llamada.child_by_field_name("name")) != metodo:
                continue
            receptor = llamada.child_by_field_name("object")
            if receptor is None:
                continue
            nombres = {clase}
            if contexto is not None and contexto["paquete"]:
                nombres.add(contexto["paquete"] + "." + clase)
            if es_static:
                if (
                    texto(receptor) not in nombres
                    or texto(receptor).split(".")[0] in asercion.alias
                ):
                    continue
            else:
                receptor = resolver(receptor, asercion.alias)
                if (
                    receptor.type != "object_creation_expression"
                    or texto(receptor.child_by_field_name("type")) not in nombres
                ):
                    continue
                if contexto is not None:
                    problema, mocks = _constructor(receptor, asercion.alias, contexto)
                    if problema:
                        return problema
                    usados.update(mocks)
            args = argumentos(llamada)
            if len(args) != len(esperados) or not all(
                _igual(literal(a, asercion.alias), e) for a, e in zip(args, esperados)
            ):
                continue
            if not _comprueba(asercion, caso, retorno):
                continue
            encontrada = indice
            break
        if encontrada is None:
            return f"el caso '{caso['id']}' no comprueba sus entradas y valor esperado o excepción sobre el método real."
        disponibles.pop(encontrada)
    if contexto is not None:
        problema = _mockito(analisis.raiz, analisis.aserciones, usados)
        if problema:
            return problema
    problema = _instrucciones(analisis, usados)
    if problema:
        return problema
    return None


def _instrucciones(analisis, mocks: set[int]) -> str | None:
    """Exige instrucciones directas: no permite código ajeno que fabrique un fallo."""
    pruebas = {}
    for asercion in analisis.aserciones:
        pruebas.setdefault(asercion.prueba, []).append(asercion)
    for metodo in (n for n in nodos(analisis.raiz) if n.type == "method_declaration"):
        aserciones = pruebas.get(texto(metodo.child_by_field_name("name")), [])
        alias = aserciones[0].alias if aserciones else {}
        llamadas = {
            _llamada(a).start_byte for a in aserciones if _llamada(a) is not None
        }
        receptores = {
            resolver(_llamada(a).child_by_field_name("object"), alias).start_byte
            for a in aserciones
            if _llamada(a) is not None
            and _llamada(a).child_by_field_name("object") is not None
        }
        lambdas = {
            resolver(a.actual, alias).start_byte
            for a in aserciones
            if a.tipo in {"excepcion", "excepcion_exacta"}
        }
        verificaciones = {a.actual.parent.parent.start_byte for a in aserciones}
        cuerpo = metodo.child_by_field_name("body")
        if cuerpo is None:
            continue
        for instruccion in cuerpo.named_children:
            if instruccion.type in {"line_comment", "block_comment"}:
                continue
            if instruccion.type == "local_variable_declaration":
                for variable in (
                    v
                    for v in instruccion.named_children
                    if v.type == "variable_declarator"
                ):
                    valor = variable.child_by_field_name("value")
                    if valor is None:
                        return "las variables locales deben tener un valor verificable."
                    valor = resolver(valor, alias)
                    if (
                        literal(valor, alias) is not NO_LITERAL
                        or valor.start_byte
                        in llamadas | receptores | mocks | lambdas | verificaciones
                    ):
                        continue
                    return "una variable local ejecuta una operación ajena al caso o al constructor declarado."
                continue
            if (
                instruccion.type == "expression_statement"
                and len(instruccion.named_children) == 1
            ):
                llamada = instruccion.named_children[0]
                if llamada.start_byte in verificaciones:
                    continue
                receptor = llamada.child_by_field_name("object")
                if (
                    llamada.type == "method_invocation"
                    and texto(llamada.child_by_field_name("name"))
                    in {"thenReturn", "thenThrow"}
                    and receptor is not None
                    and receptor.type == "method_invocation"
                    and texto(receptor.child_by_field_name("name")) == "when"
                ) and all(
                    literal(a, alias) is not NO_LITERAL or a.type == "class_literal"
                    for a in argumentos(llamada)
                ):
                    continue
            return "la prueba contiene una instrucción ajena a las comprobaciones y mocks del contrato."
    return None


def _firma(firma: str) -> tuple[list[str], bool, str]:
    """Lee los nombres de parámetros y static de la firma, sin compilarla."""
    raiz = (
        obtener_parser("java")
        .parse(("class Contexto { " + firma + " {} }").encode("utf-8"))
        .root_node
    )
    if raiz.has_error:
        raise ValueError("La firma Java del contrato no es verificable.")
    metodo = next(n for n in nodos(raiz) if n.type == "method_declaration")
    parametros = metodo.child_by_field_name("parameters")
    nombres = []
    for parametro in parametros.named_children:
        nombre = parametro.child_by_field_name("name")
        if parametro.type != "formal_parameter" or nombre is None:
            raise ValueError(
                "Este guardrail necesita parámetros fijos; no admite varargs."
            )
        nombres.append(texto(nombre))
    modificadores = next(
        (n for n in metodo.named_children if n.type == "modifiers"), None
    )
    return (
        nombres,
        modificadores is not None
        and any(h.type == "static" for h in modificadores.children),
        texto(metodo.child_by_field_name("type")),
    )


def _llamada(asercion: AsercionJava) -> Node | None:
    """Exige una llamada directa o una lambda de assertThrows que solo la invoque."""
    actual = resolver(asercion.actual, asercion.alias)
    if asercion.tipo in {"excepcion", "excepcion_exacta"}:
        if actual.type != "lambda_expression":
            return None
        parametros = actual.child_by_field_name("parameters")
        if (
            parametros is None
            or parametros.type != "formal_parameters"
            or parametros.named_children
        ):
            return None
        actual = actual.child_by_field_name("body")
        if actual is not None and actual.type == "block":
            hijos = [
                h
                for h in actual.named_children
                if h.type not in {"line_comment", "block_comment"}
            ]
            if (
                len(hijos) != 1
                or hijos[0].type != "expression_statement"
                or len(hijos[0].named_children) != 1
            ):
                return None
            actual = hijos[0].named_children[0]
    return actual if actual is not None and actual.type == "method_invocation" else None


def _comprueba(asercion: AsercionJava, caso: dict[str, Any], retorno: str) -> bool:
    """Verifica el literal esperado o la clase exacta de excepción del contrato."""
    if not _argumentos_asercion_validos(asercion):
        return False
    if "excepcion" in caso:
        return (
            asercion.tipo == "excepcion"
            and asercion.valor is not None
            and asercion.valor.type == "class_literal"
            and texto(asercion.valor).removesuffix(".class").removeprefix("java.lang.")
            == caso["excepcion"].removeprefix("java.lang.")
        )
    esperado = caso.get("valor_esperado", NO_LITERAL)
    if not _tipo_comparacion(asercion, esperado, retorno):
        return False
    if asercion.tipo in {"igualdad", "array"}:
        if not _igual(literal(asercion.valor, asercion.alias), esperado):
            return False
        if asercion.delta is not None:
            delta = literal(asercion.delta, asercion.alias)
            return (
                not isinstance(esperado, bool)
                and isinstance(esperado, (int, float))
                and retorno.rsplit(".", 1)[-1] in {"double", "float", "Double", "Float"}
                and isinstance(delta, Decimal)
                and Decimal(0)
                <= delta
                <= max(Decimal(1), abs(Decimal(str(esperado)))) * Decimal("0.000001")
            )
        return True
    if asercion.tipo == "booleano" and isinstance(esperado, bool):
        return asercion.esperado == ("bool:True" if esperado else "bool:False")
    return asercion.tipo == "nulo" and esperado is None


def _tipo_comparacion(asercion: AsercionJava, esperado: Any, retorno: str) -> bool:
    """Evita igualdad de identidad de arrays, char/String y coerciones de enteros."""
    valor = (
        resolver(asercion.valor, asercion.alias) if asercion.valor is not None else None
    )
    simple = re.sub(r"<.*>", "", retorno).rsplit(".", 1)[-1]
    if isinstance(esperado, list):
        if retorno.endswith("[]"):
            return (
                asercion.tipo == "array"
                and valor is not None
                and valor.type == "array_creation_expression"
            )
        return (
            asercion.tipo == "igualdad"
            and valor is not None
            and valor.type == "method_invocation"
            and simple == "List"
        )
    if asercion.tipo == "array":
        return False
    if isinstance(esperado, str):
        return valor is not None and (
            valor.type == "character_literal"
            if simple in {"char", "Character"}
            else valor.type == "string_literal"
            if simple == "String"
            else False
        )
    if (
        isinstance(esperado, (int, float))
        and not isinstance(esperado, bool)
        and simple
        in {"byte", "short", "int", "long", "Byte", "Short", "Integer", "Long"}
    ):
        if valor is None:
            return False
        if valor.type == "unary_expression":
            valor = valor.child_by_field_name("operand")
        return (
            valor is not None
            and valor.type.endswith("integer_literal")
            and asercion.delta is None
        )
    if isinstance(esperado, bool):
        return simple in {"boolean", "Boolean"}
    if isinstance(esperado, (int, float)):
        return simple in {"double", "float", "Double", "Float"}
    if esperado is None:
        return simple not in {
            "byte",
            "short",
            "int",
            "long",
            "float",
            "double",
            "char",
            "boolean",
            "void",
        }
    return False


def _argumentos_asercion_validos(asercion: AsercionJava) -> bool:
    """No permite proveedores de mensajes ni argumentos extra que ejecuten código."""
    invocacion = asercion.actual.parent.parent
    args = argumentos(invocacion)
    base = (
        2
        if asercion.tipo
        in {"igualdad", "array", "distinto", "excepcion", "excepcion_exacta"}
        else 1
    )
    extras = args[base:]
    if not extras:
        return len(args) == base
    valores = [literal(a, asercion.alias) for a in extras]
    if asercion.tipo in {"igualdad", "array"} and isinstance(valores[0], Decimal):
        return len(valores) == 1 or len(valores) == 2 and isinstance(valores[1], str)
    return len(valores) == 1 and isinstance(valores[0], str)


def _igual(valor: Any, esperado: Any) -> bool:
    """Igualdad de datos del contrato, separando booleanos, números, nulos y listas."""
    if valor is NO_LITERAL or esperado is NO_LITERAL:
        return False
    if isinstance(esperado, bool):
        return type(valor) is bool and valor == esperado
    if isinstance(esperado, (int, float)):
        return isinstance(valor, Decimal) and valor == Decimal(str(esperado))
    if isinstance(esperado, list):
        return (
            isinstance(valor, list)
            and len(valor) == len(esperado)
            and all(_igual(v, e) for v, e in zip(valor, esperado))
        )
    return type(valor) is type(esperado) and valor == esperado


def _constructor(
    nodo: Node, alias: dict[str, Node], contexto: dict[str, Any]
) -> tuple[str | None, set[int]]:
    """Acepta el constructor real y mocks de sus dependencias en el orden declarado."""
    args = argumentos(nodo)
    if not args and (
        contexto["constructor_implicito"]
        or any(not c["parametros"] for c in contexto["constructores"])
    ):
        return None, set()
    for constructor in contexto["constructores"]:
        parametros = constructor["parametros"]
        if len(parametros) != len(args):
            continue
        usados = set()
        valido = True
        for argumento, parametro in zip(args, parametros):
            valor = resolver(argumento, alias)
            tipo = re.sub(r"<.*>", "", parametro["tipo"]).strip()
            simple = tipo.rsplit(".", 1)[-1]
            if simple in {
                "byte",
                "short",
                "int",
                "long",
                "float",
                "double",
                "boolean",
                "char",
                "String",
                "List",
                "Map",
                "Set",
                "Collection",
            }:
                valido = False
                break
            opciones = argumentos(valor) if valor.type == "method_invocation" else []
            nombres = {tipo}
            nombres.update(
                i.removeprefix("import ").removesuffix(";").strip()
                for i in contexto["imports"]
                if i.strip().endswith("." + simple + ";")
                and not i.strip().startswith("import static ")
            )
            if (
                texto(valor.child_by_field_name("name")) != "mock"
                or len(opciones) != 1
                or opciones[0].type != "class_literal"
                or texto(opciones[0]).removesuffix(".class") not in nombres
            ):
                valido = False
                break
            usados.add(valor.start_byte)
        if valido:
            return None, usados
    return (
        "el constructor debe ser accesible y sus mocks corresponder solo a dependencias declaradas; no se inventan valores de construcción.",
        set(),
    )


def _imports_coherentes(
    raiz: Node, contexto: dict[str, Any], contrato: dict[str, Any]
) -> str | None:
    """Impide sustituir el objetivo o su dependencia por un homónimo de otro paquete."""
    origen = {}
    for entrada in contexto["imports"]:
        nombre = entrada.replace(" ", "").removeprefix("import").removesuffix(";")
        if not nombre.startswith("static") and not nombre.endswith(".*"):
            origen[nombre.rsplit(".", 1)[-1]] = nombre
    clase = contexto["clase"].split(".")[0]
    origen[clase] = (contexto["paquete"] + "." if contexto["paquete"] else "") + clase
    criticos = {clase}
    for constructor in contexto["constructores"]:
        for parametro in constructor["parametros"]:
            tipo = re.sub(r"<.*>", "", parametro["tipo"]).strip()
            simple = tipo.rsplit(".", 1)[-1]
            criticos.add(simple)
            origen.setdefault(
                simple,
                tipo
                if "." in tipo
                else (contexto["paquete"] + "." if contexto["paquete"] else "")
                + simple,
            )
    conocidos = {
        "Exception",
        "RuntimeException",
        "IllegalArgumentException",
        "IllegalStateException",
        "NullPointerException",
        "ArithmeticException",
        "IndexOutOfBoundsException",
        "UnsupportedOperationException",
        "AssertionError",
    }
    for caso in contrato["casos"]:
        tipo = caso.get("excepcion")
        if tipo:
            simple = tipo.rsplit(".", 1)[-1]
            criticos.add(simple)
            origen.setdefault(
                simple,
                tipo
                if "." in tipo
                else "java.lang." + tipo
                if tipo in conocidos
                else (contexto["paquete"] + "." if contexto["paquete"] else "") + tipo,
            )
    for nodo in raiz.named_children:
        if nodo.type != "import_declaration":
            continue
        nombre = texto(nodo).replace(" ", "").removeprefix("import").removesuffix(";")
        if (
            not nombre.startswith("static")
            and nombre.rsplit(".", 1)[-1] in criticos
            and nombre != origen[nombre.rsplit(".", 1)[-1]]
        ):
            return "un import sustituye el objetivo, dependencia o excepción por un tipo de otro paquete."
    return None


def _mockito(
    raiz: Node, aserciones: list[AsercionJava], usados: set[int]
) -> str | None:
    """Rechaza mocks del objetivo, spies y stubs que no pertenecen a dependencias."""
    imports = [
        texto(n).replace(" ", "")
        for n in raiz.named_children
        if n.type == "import_declaration"
    ]
    llamadas = [n for n in nodos(raiz) if n.type == "method_invocation"]
    aliases = [a.alias for a in aserciones]
    for llamada in llamadas:
        nombre = texto(llamada.child_by_field_name("name"))
        if nombre in {
            "spy",
            "mockStatic",
            "mockConstruction",
            "doReturn",
            "doThrow",
            "doAnswer",
            "verify",
            "lenient",
        }:
            return f"Mockito {nombre} no está permitido para sustituir o alterar el objetivo."
        if nombre == "mock":
            receptor = texto(llamada.child_by_field_name("object"))
            valido = (
                receptor == "org.mockito.Mockito"
                or receptor == "Mockito"
                and any(i == "importorg.mockito.Mockito;" for i in imports)
                or not receptor
                and any(
                    i
                    in {
                        "importstaticorg.mockito.Mockito.mock;",
                        "importstaticorg.mockito.Mockito.*;",
                    }
                    for i in imports
                )
            )
            if not valido or llamada.start_byte not in usados:
                return "cada mock debe provenir de Mockito y utilizarse exclusivamente como dependencia del constructor real."
        if nombre == "when":
            receptor = texto(llamada.child_by_field_name("object"))
            proveedor = (
                receptor == "org.mockito.Mockito"
                or receptor == "Mockito"
                and "importorg.mockito.Mockito;" in imports
                or not receptor
                and any(
                    i
                    in {
                        "importstaticorg.mockito.Mockito.when;",
                        "importstaticorg.mockito.Mockito.*;",
                    }
                    for i in imports
                )
            )
            if not proveedor:
                return "el stub debe utilizar Mockito sobre una dependencia declarada."
            args = argumentos(llamada)
            if len(args) != 1 or args[0].type != "method_invocation":
                return "el stub de Mockito no apunta a un método de dependencia."
            objeto = args[0].child_by_field_name("object")
            if objeto is None or not any(
                resolver(objeto, alias).start_byte in usados for alias in aliases
            ):
                return "no se permite sustituir el método probado mediante un stub."
    return None

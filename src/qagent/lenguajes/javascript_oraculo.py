"""Registro de evidencias y oráculos ``oracle.v1`` de JavaScript y TypeScript (#176).

El analizador construye, por función, el **registro confiable** que pide EN-18
(``docs/contratos/oraculos-js-ts.md``): cada evidencia cita el JSDoc o el tipo de
TypeScript del que sale, con su archivo y su línea. Solo tres fuentes fijan una
expectativa concreta:

* un ``@example`` con la llamada y su resultado: ``sumar(2, 3) // => 5`` o
  ``dividir(1, 0) // throws RangeError``;
* un ``@throws {Tipo} condición``: la excepción (la entrada la propone el modelo
  a partir de la condición documentada);
* un tipo de retorno literal (``: 'ok'``, ``@returns {42}``): todo caso lo devuelve.

Lo demás (``@returns`` en prosa, uniones de literales, ``number``) se registra como
evidencia que **no** basta: el caso queda ``insuficiente`` y se descarta. Así una
función sin JSDoc ni tipos verificables no recibe casos. Nada se ejecuta.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import math
import re
from typing import Any

from tree_sitter import Node

from qagent import contracts
from qagent.contracts import ContratoInvalido
from qagent.lenguajes.treesitter import obtener_parser

#: ``// => 5``, ``//=> 5``, ``// → 5``, ``// returns 5``, ``// devuelve 5``.
_RESULTADO = re.compile(
    r"^(?P<llamada>.+?)\s*;?\s*//\s*(?:=>|→|returns?\b|devuelve\b|retorna\b)\s*"
    r"(?P<resultado>.+?)\s*;?\s*$",
    re.IGNORECASE,
)
#: ``// throws RangeError``, ``// => throws {RangeError}``, ``// lanza TypeError``.
_LANZA = re.compile(
    r"^(?P<llamada>.+?)\s*;?\s*//\s*(?:=>\s*)?(?:throws|lanza|arroja)\s+"
    r"\{?(?P<excepcion>[A-Za-z_$][\w$.]*)\}?",
    re.IGNORECASE,
)
_LITERAL_TIPO = re.compile(
    r"""^(?:'[^'\\]*'|"[^"\\]*"|-?\d+(?:\.\d+)?|true|false|null)$"""
)
_ID_INVALIDO = re.compile(r"[^A-Za-z0-9._:-]")
#: Lo que devuelve :func:`literal` cuando la expresión no tiene un valor JSON.
NO_REPRESENTABLE = object()


# --- Valores JSON de literales JS ----------------------------------------------------


def _numero(texto: str) -> Any:
    texto = texto.replace("_", "")
    try:
        return int(texto, 0)
    except ValueError:
        pass
    try:
        valor = float(texto)
    except ValueError:
        return NO_REPRESENTABLE
    return valor if math.isfinite(valor) else NO_REPRESENTABLE


def _cadena(nodo: Node) -> Any:
    partes = []
    for hijo in nodo.named_children:
        if hijo.type == "string_fragment":
            partes.append(hijo.text.decode("utf-8"))
        elif hijo.type == "escape_sequence":
            partes.append(codecs.decode(hijo.text.decode("utf-8"), "unicode_escape"))
        else:  # ${…} de una plantilla: no es un literal
            return NO_REPRESENTABLE
    return "".join(partes)


def literal(nodo: Node | None) -> Any:
    """Valor JSON de un literal JS; ``NO_REPRESENTABLE`` si no lo es.

    Admite números (también hexadecimales, ``-x`` y ``1_000``), cadenas y plantillas
    sin ``${}``, ``true``/``false``/``null``, arreglos y objetos de literales.
    ``undefined``, ``NaN``, ``Infinity`` y cualquier expresión no tienen valor JSON.
    """
    if nodo is None:
        return NO_REPRESENTABLE
    tipo = nodo.type
    if tipo == "parenthesized_expression" and nodo.named_children:
        return literal(nodo.named_children[0])
    if tipo == "number":
        return _numero(nodo.text.decode("utf-8"))
    if tipo in {"string", "template_string"}:
        return _cadena(nodo)
    if tipo in {"true", "false"}:
        return tipo == "true"
    if tipo == "null":
        return None
    if tipo == "unary_expression":
        operador = nodo.child_by_field_name("operator")
        valor = literal(nodo.child_by_field_name("argument"))
        es_numero = isinstance(valor, (int, float)) and not isinstance(valor, bool)
        if es_numero and operador is not None and operador.text in {b"-", b"+"}:
            return -valor if operador.text == b"-" else valor
        return NO_REPRESENTABLE
    if tipo == "array":
        valores = [literal(h) for h in nodo.named_children if h.type != "comment"]
        return NO_REPRESENTABLE if NO_REPRESENTABLE in valores else valores
    if tipo == "object":
        objeto = {}
        for par in nodo.named_children:
            if par.type == "comment":
                continue
            if par.type != "pair":
                return NO_REPRESENTABLE
            clave = par.child_by_field_name("key")
            nombre = (
                _cadena(clave)
                if clave is not None and clave.type == "string"
                else clave.text.decode("utf-8")
                if clave is not None and clave.type in {"property_identifier", "number"}
                else NO_REPRESENTABLE
            )
            valor = literal(par.child_by_field_name("value"))
            if NO_REPRESENTABLE in (nombre, valor):
                return NO_REPRESENTABLE
            objeto[nombre] = valor
        return objeto
    return NO_REPRESENTABLE


def _expresion(texto: str) -> Node | None:
    """Única expresión de ``texto`` parseada con la gramática de JS, o None."""
    raiz = obtener_parser("javascript").parse(texto.encode("utf-8")).root_node
    if raiz.has_error or len(raiz.named_children) != 1:
        return None
    sentencia = raiz.named_children[0]
    if sentencia.type != "expression_statement" or not sentencia.named_children:
        return None
    expresion = sentencia.named_children[0]
    if expresion.type == "await_expression" and expresion.named_children:
        expresion = expresion.named_children[0]
    return expresion


def normalizar(valor: Any) -> Any:
    """En JS ``5`` y ``5.0`` son el mismo número: los enteros flotantes pasan a ``int``."""
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, list):
        return [normalizar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: normalizar(v) for k, v in valor.items()}
    return valor


def _json(valor: Any) -> str:
    return json.dumps(normalizar(valor), sort_keys=True, ensure_ascii=False)


# --- Tipos ----------------------------------------------------------------------------


def _sin_promesa(tipo: str) -> str:
    coincidencia = re.fullmatch(r"\s*Promise\s*<(.+)>\s*", tipo)
    return coincidencia[1].strip() if coincidencia else tipo.strip()


def _partes_union(tipo: str) -> list[str]:
    """Miembros de una unión de primer nivel (sin partir genéricos ni literales)."""
    partes, actual, profundidad, comilla = [], "", 0, None
    for caracter in tipo:
        if comilla:
            comilla = None if caracter == comilla else comilla
        elif caracter in "'\"":
            comilla = caracter
        elif caracter in "<([{":
            profundidad += 1
        elif caracter in ">)]}":
            profundidad -= 1
        elif caracter == "|" and profundidad == 0:
            partes.append(actual.strip())
            actual = ""
            continue
        actual += caracter
    partes.append(actual.strip())
    return [p for p in partes if p]


def _valor_de_tipo_literal(tipo: str) -> Any:
    return literal(_expresion(tipo)) if _LITERAL_TIPO.match(tipo) else NO_REPRESENTABLE


def compatible(tipo: str | None, valor: Any) -> bool:
    """Si ``valor`` (JSON) puede ser de ``tipo`` (TypeScript o JSDoc).

    Es un filtro de incompatibilidades evidentes, no un verificador de tipos: un tipo
    del usuario, genérico o ``any`` acepta cualquier valor JSON.
    """
    if not tipo:
        return True
    tipo = _sin_promesa(tipo)
    miembros = _partes_union(tipo)
    if len(miembros) > 1:
        return any(compatible(m, valor) for m in miembros)
    tipo = tipo.strip()
    if tipo.startswith("(") and tipo.endswith(")"):
        return compatible(tipo[1:-1], valor)
    if _LITERAL_TIPO.match(tipo):
        return _json(_valor_de_tipo_literal(tipo)) == _json(valor)
    lista = re.fullmatch(r"(.+)\[\]|(?:Readonly)?Array<(.+)>", tipo)
    if lista:
        interno = lista[1] or lista[2]
        return isinstance(valor, list) and all(compatible(interno, v) for v in valor)
    basico = tipo.lower()
    if basico == "number":
        return isinstance(valor, (int, float)) and not isinstance(valor, bool)
    if basico == "string":
        return isinstance(valor, str)
    if basico == "boolean":
        return isinstance(valor, bool)
    if basico == "null":
        return valor is None
    return basico not in {"void", "undefined", "never"}


# --- Registro de evidencias -----------------------------------------------------------


def _id(*partes: str) -> str:
    """Id válido para ``oracle.v1`` (letras, dígitos y ``._:-``; hasta 128)."""
    texto = _ID_INVALIDO.sub("_", ":".join(partes))
    if len(texto) > 120:
        texto = texto[:100] + ":" + hashlib.sha256(texto.encode()).hexdigest()[:16]
    return texto


def _evidencia(
    id_: str,
    fuente: str,
    caracter: str,
    modulo: str,
    linea: int,
    referencia: str,
    fragmento: str,
    linea_fin: int | None = None,
) -> dict[str, Any]:
    ubicacion: dict[str, Any] = {"archivo": modulo, "linea_inicio": linea}
    if linea_fin is not None and linea_fin > linea:
        ubicacion["linea_fin"] = linea_fin
    return {
        "id": id_,
        "fuente": fuente,
        "caracter": caracter,
        "ubicacion": ubicacion,
        "referencia": referencia,
        "fragmento": fragmento.strip() or referencia,
    }


def _llamada(texto: str, nombre_corto: str) -> list[Any] | None:
    """Argumentos JSON de ``texto`` si es una llamada a la función; None si no."""
    expresion = _expresion(texto)
    if expresion is None or expresion.type != "call_expression":
        return None
    llamado = expresion.child_by_field_name("function")
    if llamado is None:
        return None
    if llamado.type == "member_expression":
        llamado = llamado.child_by_field_name("property")
    if nombre_corto != "default" and (
        llamado is None or llamado.text.decode("utf-8") != nombre_corto
    ):
        return None
    lista = expresion.child_by_field_name("arguments")
    argumentos = [
        literal(h) for h in (lista.named_children if lista is not None else [])
    ]
    return None if NO_REPRESENTABLE in argumentos else argumentos


def _ejemplos(
    funcion: dict[str, Any], modulo: str, tipo_retorno: str | None
) -> dict[str, dict[str, Any]]:
    """Una entrada por línea de ``@example`` con llamada y resultado literal."""
    nombre = funcion["nombre"]
    corto = nombre.rsplit(".", 1)[-1]
    registro: dict[str, dict[str, Any]] = {}
    for ejemplo in (funcion.get("jsdoc") or {}).get("ejemplos", []):
        for desplazamiento, fila in enumerate(ejemplo["texto"].splitlines()):
            fila = fila.strip()
            linea = ejemplo["linea"] + desplazamiento
            lanza = _LANZA.match(fila)
            resultado = None if lanza else _RESULTADO.match(fila)
            coincidencia = lanza or resultado
            if not coincidencia:
                continue
            argumentos = _llamada(coincidencia["llamada"], corto)
            if argumentos is None:
                continue
            id_ = _id("jsdoc", nombre, "ejemplo", str(len(registro) + 1))
            entrada: dict[str, Any] = {"entrada_documentada": argumentos}
            caracter = "comportamiento"
            if lanza:
                entrada["excepcion_documentada"] = lanza["excepcion"]
            else:
                valor = literal(_expresion(resultado["resultado"]))
                if valor is NO_REPRESENTABLE:
                    continue
                if compatible(tipo_retorno, valor):
                    entrada["valor_documentado"] = normalizar(valor)
                else:
                    caracter = "contradictoria"
            entrada["evidencia"] = _evidencia(
                id_, "jsdoc", caracter, modulo, linea, "@example", fila
            )
            registro[id_] = entrada
    _marcar_contradicciones(registro)
    return registro


def _marcar_contradicciones(registro: dict[str, dict[str, Any]]) -> None:
    """Dos ejemplos con la misma entrada y distinto resultado se contradicen.

    No se elige uno: ambos pasan a ``contradictoria`` y dejan de fijar un valor.
    """
    por_entrada: dict[str, list[dict[str, Any]]] = {}
    for entrada in registro.values():
        por_entrada.setdefault(_json(entrada["entrada_documentada"]), []).append(
            entrada
        )
    for grupo in por_entrada.values():
        resultados = {
            _json(
                e.get(
                    "valor_documentado", {"excepcion": e.get("excepcion_documentada")}
                )
            )
            for e in grupo
        }
        if len(resultados) < 2:
            continue
        for entrada in grupo:
            entrada.pop("valor_documentado", None)
            entrada.pop("excepcion_documentada", None)
            entrada["evidencia"]["caracter"] = "contradictoria"


def registro_de_evidencias(funcion: dict[str, Any], modulo: str) -> dict[str, Any]:
    """Registro confiable de la función: ``{id: {"evidencia", …documentado}}``.

    Lo arma el analizador desde el JSDoc y los tipos de la función (``funcion`` es
    la descripción de :func:`javascript_estructura.describir`). Es el que recibe
    :func:`qagent.contracts.validar_oraculo_js_ts`.
    """
    nombre = funcion["nombre"]
    jsdoc = funcion.get("jsdoc") or {}
    retorno_doc = jsdoc.get("retorno") or {}
    tipo_retorno = funcion.get("retorno") or retorno_doc.get("tipo")
    registro = _ejemplos(funcion, modulo, tipo_retorno)

    for numero, excepcion in enumerate(jsdoc.get("excepciones", []), start=1):
        tipo = excepcion.get("tipo")
        id_ = _id("jsdoc", nombre, "throws", str(numero))
        fragmento = f"@throws {{{tipo}}} {excepcion['descripcion']}".strip()
        concreta = bool(tipo) and bool(excepcion["descripcion"].strip())
        registro[id_] = {
            "evidencia": _evidencia(
                id_,
                "jsdoc",
                "comportamiento" if concreta else "descripcion_generica",
                modulo,
                excepcion["linea"],
                "@throws",
                fragmento,
            )
        }
        if concreta:
            registro[id_]["excepcion_documentada"] = tipo

    if retorno_doc:
        id_ = _id("jsdoc", nombre, "returns")
        descripcion = retorno_doc.get("descripcion", "")
        registro[id_] = {
            "evidencia": _evidencia(
                id_,
                "jsdoc",
                "comportamiento" if descripcion.strip() else "descripcion_generica",
                modulo,
                retorno_doc["linea"],
                "@returns",
                f"@returns {{{retorno_doc.get('tipo') or ''}}} {descripcion}",
            )
        }

    tipo_ts = funcion.get("retorno")
    fuente, tipo = (
        ("typescript", tipo_ts) if tipo_ts else ("jsdoc", retorno_doc.get("tipo"))
    )
    if tipo:
        tipo = _sin_promesa(tipo)
        miembros = _partes_union(tipo)
        valor = _valor_de_tipo_literal(tipo) if len(miembros) == 1 else NO_REPRESENTABLE
        if valor is not NO_REPRESENTABLE:
            caracter = "tipo_literal"
        elif all(_LITERAL_TIPO.match(m) for m in miembros):
            caracter = "tipo_union_literal"
        else:
            caracter = "tipo_general"
        id_ = _id(fuente, nombre, "retorno")
        linea = funcion["linea"] if fuente == "typescript" else retorno_doc["linea"]
        registro[id_] = {
            "evidencia": _evidencia(
                id_, fuente, caracter, modulo, linea, "tipo de retorno", tipo
            )
        }
        if valor is not NO_REPRESENTABLE:
            registro[id_]["valor_documentado"] = normalizar(valor)
    return registro


# --- Oráculo de un caso ---------------------------------------------------------------


def posicionales(funcion: dict[str, Any], entrada: Any) -> list[Any] | None:
    """Argumentos en orden de la entrada del caso; None si no encaja con la firma.

    Acepta una lista posicional o un objeto por nombre de parámetro (los opcionales
    pueden faltar al final). El resto (``...xs``) recibe una lista que se expande.
    """
    parametros = funcion.get("parametros") or []
    if entrada is None:
        entrada = []
    if isinstance(entrada, list):
        return entrada
    if not isinstance(entrada, dict):
        return None
    nombres = [p["nombre"].removeprefix("...") for p in parametros]
    if set(entrada) - set(nombres):
        return None
    argumentos: list[Any] = []
    faltantes = False
    for parametro, nombre in zip(parametros, nombres):
        if nombre not in entrada:
            if not (parametro.get("opcional") or parametro["nombre"].startswith("...")):
                return None
            faltantes = True
            continue
        if faltantes:
            return None  # no se puede saltar un opcional y pasar el siguiente
        valor = entrada[nombre]
        if parametro["nombre"].startswith("..."):
            if not isinstance(valor, list):
                return None
            argumentos.extend(valor)
        else:
            argumentos.append(valor)
    return argumentos


#: Fuente de la evidencia -> ``origen`` del caso en ``planner_contract.v3``.
ORIGEN_DE_FUENTE = {"jsdoc": "docstring", "typescript": "tipo"}


def _elegir(
    registro: dict[str, dict[str, Any]], caso: dict[str, Any], argumentos: list[Any]
) -> tuple[str, dict[str, Any]] | None:
    """La evidencia que respalda el caso, de la más concreta a la menos concreta."""
    clave = _json(argumentos)
    excepcion = "excepcion" in caso
    ejemplos = [
        (i, e)
        for i, e in registro.items()
        if "entrada_documentada" in e and _json(e["entrada_documentada"]) == clave
    ]
    for identificador, entrada in ejemplos:
        if excepcion == ("excepcion_documentada" in entrada) or (
            entrada["evidencia"]["caracter"] == "contradictoria"
        ):
            return identificador, entrada
    if excepcion:
        lanzadas = [
            (i, e)
            for i, e in registro.items()
            if "excepcion_documentada" in e and "entrada_documentada" not in e
        ]
        lanzadas.sort(
            key=lambda par: par[1]["excepcion_documentada"] != caso["excepcion"]
        )
        if lanzadas:  # otra excepción documentada: la validación dirá que no coincide
            return lanzadas[0]
    literales = [
        (i, e)
        for i, e in registro.items()
        if e["evidencia"]["caracter"] == "tipo_literal"
    ]
    if literales and not excepcion:
        return literales[0]
    if ejemplos:
        return ejemplos[0]
    generales = [
        (i, e)
        for i, e in registro.items()
        if "entrada_documentada" not in e and "excepcion_documentada" not in e
    ]
    return generales[0] if generales else None


def oraculo_del_caso(
    lenguaje: str, modulo: str, funcion: dict[str, Any], caso: dict[str, Any]
) -> tuple[dict[str, Any], str | None]:
    """El ``oracle.v1`` de un caso del Planner y, si no es verificable, por qué.

    Es determinista: el mismo análisis y el mismo caso dan el mismo oráculo, así la
    generación (parte 2 de EP-11a) puede recalcularlo sin guardarlo aparte. El valor
    o la excepción del caso deben coincidir exactamente con lo documentado
    (:func:`qagent.contracts.validar_oraculo_js_ts`); si no, el caso se descarta.
    """
    registro = funcion.get("evidencias") or {}
    base: dict[str, Any] = {
        "version": "1",
        "lenguaje": lenguaje,
        "modulo": modulo,
        "objetivo": funcion["nombre"],
        "firma": funcion.get("firma") or funcion["nombre"],
        "entrada": caso.get("entrada"),
        "comprobacion": "excepcion" if "excepcion" in caso else "igualdad",
    }
    argumentos = posicionales(funcion, caso.get("entrada"))
    elegida = _elegir(registro, caso, argumentos) if argumentos is not None else None
    if elegida is None:
        motivo = (
            "sin resultado esperado verificable: la función no tiene JSDoc ni tipos "
            "que documenten ese valor o esa excepción"
        )
        return {**base, "estado_evidencia": "sin_procedencia", "motivo": motivo}, motivo

    _, entrada = elegida
    evidencia = entrada["evidencia"]
    if evidencia["caracter"] == "contradictoria":
        motivo = f"la documentación se contradice ({evidencia['fragmento']})"
        return {
            **base,
            "estado_evidencia": "contradictoria",
            "motivo": motivo,
            "evidencia": evidencia,
        }, motivo

    documenta = "excepcion_documentada" if "excepcion" in caso else "valor_documentado"
    if documenta not in entrada:
        motivo = (
            "sin resultado esperado verificable: "
            f"{evidencia['referencia']} no documenta un valor concreto para esa entrada"
            if "excepcion" not in caso
            else "sin resultado esperado verificable: ninguna etiqueta @throws ni "
            "@example documenta esa excepción"
        )
        return {
            **base,
            "estado_evidencia": "insuficiente",
            "motivo": motivo,
            "evidencia": evidencia,
        }, motivo

    oraculo = {**base, "estado_evidencia": "verificable", "evidencia": evidencia}
    if "excepcion" in caso:
        oraculo["excepcion_esperada"] = caso["excepcion"]
    else:
        oraculo["valor_esperado"] = normalizar(caso.get("valor_esperado"))
    try:
        contracts.validar_oraculo_js_ts(oraculo, registro)
    except ContratoInvalido as error:
        motivo = "oráculo no verificable: " + "; ".join(error.errores)
        return {
            **base,
            "estado_evidencia": "insuficiente",
            "motivo": motivo,
            "evidencia": evidencia,
        }, motivo
    origen = ORIGEN_DE_FUENTE.get(evidencia["fuente"])
    if caso.get("origen") != origen:
        return oraculo, (
            f"el caso declara origen {caso.get('origen')!r}, pero su evidencia es "
            f"{evidencia['fuente']} (origen {origen!r})"
        )
    return oraculo, None

"""Declaraciones Spring MVC mediante tree-sitter, sin ejecutar Java (#183).

Solo reconoce anotaciones de Spring importadas o con nombre cualificado. Las
rutas calculadas y los estados dinámicos quedan sin resolver; nunca se consulta
el cuerpo del controlador para deducir una respuesta esperada.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tree_sitter import Node

_WEB = "org.springframework.web.bind.annotation."
_CONTROLLER = "org.springframework.stereotype.Controller"
_VERBOS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}
_ESTADOS = {
    "OK": 200,
    "CREATED": 201,
    "ACCEPTED": 202,
    "NO_CONTENT": 204,
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "UNPROCESSABLE_ENTITY": 422,
    "INTERNAL_SERVER_ERROR": 500,
}


def _texto(nodo: Node | None) -> str:
    """Devuelve texto literal del nodo, sin evaluar constantes Java."""
    return nodo.text.decode("utf-8") if nodo is not None else ""


def _atributos(anotacion: Node) -> dict[str, Node]:
    """Separa atributos nombrados y el argumento abreviado value de una anotación."""
    argumentos = anotacion.child_by_field_name("arguments")
    resultado = {}
    for hijo in argumentos.named_children if argumentos is not None else []:
        if hijo.type == "element_value_pair":
            resultado[_texto(hijo.child_by_field_name("key"))] = (
                hijo.child_by_field_name("value")
            )
        else:
            resultado["value"] = hijo
    return resultado


def _literales(nodo: Node | None) -> list[str] | None:
    """Lee strings o arrays de strings; None indica una expresión no resoluble."""
    if nodo is None:
        return [""]
    if nodo.type == "string_literal":
        try:
            valor = json.loads(_texto(nodo))
        except (ValueError, TypeError):
            return None
        return [valor] if isinstance(valor, str) else None
    if nodo.type == "element_value_array_initializer":
        valores = [_literales(h) for h in nodo.named_children]
        return (
            [v for grupo in valores for v in grupo]
            if all(g is not None for g in valores)
            else None
        )
    return None


def extraer_endpoints(
    raiz: Node, funciones: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Extrae rutas, parámetros y respuestas declaradas de controladores Spring.

    El resultado usa objetivo HTTP, manejador Clase.metodo y firma del análisis
    Java común. Un @Controller de vistas no se interpreta como un cuerpo REST.
    Las anotaciones ajenas con el mismo nombre no se consideran Spring.
    """
    imports = {
        _texto(h).removeprefix("import ").removesuffix(";").strip()
        for h in raiz.named_children
        if h.type == "import_declaration"
    }
    paquete = next(
        (
            _texto(h).removeprefix("package ").removesuffix(";").strip()
            for h in raiz.named_children
            if h.type == "package_declaration"
        ),
        "",
    )

    def anotaciones(nodo: Node) -> dict[str, Node]:
        modificadores = next(
            (h for h in nodo.named_children if h.type == "modifiers"), None
        )
        resultado = {}
        for h in modificadores.named_children if modificadores is not None else []:
            if h.type not in {"annotation", "marker_annotation"}:
                continue
            nombre = _texto(h.child_by_field_name("name"))
            corto = nombre.rsplit(".", 1)[-1]
            esperado = _CONTROLLER if corto == "Controller" else _WEB + corto
            if nombre == esperado or (
                nombre == corto
                and (
                    esperado in imports or esperado.rsplit(".", 1)[0] + ".*" in imports
                )
            ):
                resultado[corto] = h
        return resultado

    por_nombre = {f["nombre"]: f for f in funciones}
    resultado = []
    for clase in raiz.named_children:
        if clase.type != "class_declaration":
            continue
        ac = anotaciones(clase)
        if not {"RestController", "Controller"} & ac.keys():
            continue
        nombre = _texto(clase.child_by_field_name("name"))
        mapping = _atributos(ac["RequestMapping"]) if "RequestMapping" in ac else {}
        prefijos = _literales(mapping.get("path", mapping.get("value")))
        cuerpo = clase.child_by_field_name("body")
        dependencias = _dependencias(clase, imports, paquete)
        for metodo in cuerpo.named_children if cuerpo is not None else []:
            if metodo.type != "method_declaration":
                continue
            manejador = nombre + "." + _texto(metodo.child_by_field_name("name"))
            funcion = por_nombre.get(manejador)
            if funcion is None:
                continue
            am = anotaciones(metodo)
            mapeos = [n for n in (*_VERBOS, "RequestMapping") if n in am]
            if not mapeos:
                continue
            atributos = _atributos(am[mapeos[0]])
            rutas = _literales(atributos.get("path", atributos.get("value")))
            verbos = (
                [_VERBOS[mapeos[0]]]
                if mapeos[0] in _VERBOS
                else _metodos(atributos.get("method", mapping.get("method")))
            )
            estado = am.get("ResponseStatus", ac.get("ResponseStatus"))
            status = _estado(estado) if estado is not None else None
            parametros = []
            for parametro in metodo.child_by_field_name("parameters").named_children:
                if parametro.type != "formal_parameter":
                    continue
                ap = anotaciones(parametro)
                vinculacion = next(
                    (
                        a
                        for a in (
                            "PathVariable",
                            "RequestParam",
                            "RequestBody",
                            "RequestHeader",
                        )
                        if a in ap
                    ),
                    None,
                )
                args = _atributos(ap[vinculacion]) if vinculacion else {}
                alias = _literales(args.get("name", args.get("value")))
                parametros.append(
                    {
                        "nombre": _texto(parametro.child_by_field_name("name")),
                        "tipo": _texto(parametro.child_by_field_name("type")),
                        "vinculacion": vinculacion,
                        "alias": alias[0]
                        if alias and alias[0]
                        else _texto(parametro.child_by_field_name("name")),
                        "requerido": _texto(args.get("required")) != "false",
                        "por_defecto": _literales(args["defaultValue"])
                        if "defaultValue" in args
                        else None,
                        "anotaciones": [
                            _texto(h)
                            for h in parametro.named_children
                            if h.type == "modifiers"
                        ],
                    }
                )
            resuelta = (
                prefijos is not None
                and rutas is not None
                and verbos is not None
                and len(mapeos) == 1
                and not any(
                    "${" in p or "#{" in p for p in (prefijos or []) + (rutas or [])
                )
            )
            for prefijo in prefijos or [""]:
                for ruta in rutas or [""]:
                    completa = "/" + "/".join(
                        p.strip("/") for p in (prefijo, ruta) if p.strip("/")
                    )
                    for verbo in verbos or ["?"]:
                        resultado.append(
                            {
                                "objetivo": verbo + " " + completa,
                                "metodo": verbo,
                                "ruta": completa,
                                "resuelta": resuelta,
                                "manejador": manejador,
                                "clase": nombre,
                                "paquete": paquete,
                                "dependencias": dependencias or [],
                                "dependencias_resueltas": dependencias is not None,
                                "firma": funcion["firma"],
                                "linea": funcion["linea"],
                                "critical": funcion["critical"],
                                "parametros": parametros,
                                "retorno": funcion["retorno"],
                                "javadoc": funcion["javadoc"],
                                "status_code": status,
                                "estado_explicito": estado is not None,
                                "cuerpo_respuesta": "RestController" in ac
                                or "ResponseBody" in ac
                                or "ResponseBody" in am,
                                "produces": _literales(atributos["produces"])
                                if "produces" in atributos
                                else None,
                                "consumes": _literales(atributos["consumes"])
                                if "consumes" in atributos
                                else None,
                                "restricciones_mapping": {
                                    k: _texto(v)
                                    for k, v in {**mapping, **atributos}.items()
                                    if k in {"params", "headers"}
                                },
                            }
                        )
    return resultado


def _dependencias(
    clase: Node, imports: set[str], paquete: str
) -> list[dict[str, str]] | None:
    """Lee dependencias de constructor único o campos Autowired, sin instanciarlas.

    Solo representa tipos nominales sin genéricos. Los constructores ambiguos y
    los tipos no representables se rechazan antes de generar pruebas.
    """
    cuerpo = clase.child_by_field_name("body")
    if cuerpo is None:
        return []
    constructores = [
        h for h in cuerpo.named_children if h.type == "constructor_declaration"
    ]
    candidatos = []
    if len(constructores) == 1:
        candidatos = list(
            constructores[0].child_by_field_name("parameters").named_children
        )
    elif len(constructores) > 1:
        return None
    resultado = {}
    for parametro in candidatos:
        if parametro.type != "formal_parameter":
            return None
        resultado[_texto(parametro.child_by_field_name("name"))] = _texto(
            parametro.child_by_field_name("type")
        )
    for campo in cuerpo.named_children:
        if campo.type != "field_declaration":
            continue
        mods = next((h for h in campo.named_children if h.type == "modifiers"), None)
        nombres = (
            [
                _texto(h.child_by_field_name("name"))
                for h in mods.named_children
                if h.type in {"annotation", "marker_annotation"}
            ]
            if mods
            else []
        )
        autowired = "org.springframework.beans.factory.annotation.Autowired"
        if not any(
            n == autowired
            or (
                n == "Autowired"
                and (
                    autowired in imports
                    or autowired.rsplit(".", 1)[0] + ".*" in imports
                )
            )
            for n in nombres
        ):
            continue
        for declarador in campo.named_children:
            if declarador.type == "variable_declarator":
                resultado[_texto(declarador.child_by_field_name("name"))] = _texto(
                    campo.child_by_field_name("type")
                )
    dependencias = []
    for nombre, tipo in sorted(resultado.items()):
        if not re.fullmatch(
            r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", tipo
        ) or tipo in {
            "byte",
            "short",
            "int",
            "long",
            "float",
            "double",
            "boolean",
            "char",
            "String",
        }:
            return None
        if "." not in tipo:
            tipo = next(
                (i for i in imports if i.endswith("." + tipo)),
                (paquete + "." if paquete else "") + tipo,
            )
        dependencias.append({"funcion": nombre, "reemplazo": tipo})
    if len({d["reemplazo"] for d in dependencias}) != len(dependencias):
        return None
    return dependencias


def _metodos(nodo: Node | None) -> list[str] | None:
    """Resuelve RequestMethod explícito; sin restricción conserva todos los verbos."""
    if nodo is None:
        return ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"]
    nodos = (
        nodo.named_children
        if nodo.type == "element_value_array_initializer"
        else [nodo]
    )
    valores = [_texto(n).rsplit(".", 1)[-1] for n in nodos]
    return (
        valores
        if valores
        and all(
            v in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"}
            for v in valores
        )
        else None
    )


def _estado(anotacion: Node) -> int | None:
    """Lee un HttpStatus conocido o un entero explícito, sin inspeccionar retornos."""
    args = _atributos(anotacion)
    valor = _texto(args.get("code", args.get("value")))
    if valor.isdigit():
        numero = int(valor)
        return numero if 100 <= numero <= 599 else None
    return _ESTADOS.get(valor.rsplit(".", 1)[-1])

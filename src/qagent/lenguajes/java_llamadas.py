"""Mapa estático de llamadas Java a métodos públicos del proyecto (#181).

No compila, importa ni ejecuta fuentes. Resuelve declaraciones e imports explícitos;
la herencia, el despacho dinámico y los tipos inferidos requieren otro análisis.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from tree_sitter import Node

from qagent.lenguajes.java_estructura import nodos_del_cuerpo

_TIPOS_CLASE = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    }
)


@dataclass
class _Clase:
    """Declaración conocida: módulo, nombre, paquete, métodos y campos propios."""

    modulo: str
    nombre: str
    paquete: str
    nodo: Node
    metodos: dict[str, list[Node]]
    campos: dict[str, str]

    @property
    def calificado(self) -> str:
        """Nombre del tipo que distingue paquetes y clases anidadas."""
        return f"{self.paquete}.{self.nombre}" if self.paquete else self.nombre


def agregar_llamadas(modulos: list[dict[str, Any]], arboles: dict[str, Node]) -> None:
    """Añade llama_a con el formato común ruta/Clase.java::Clase.metodo.

    Solo incluye métodos públicos analizados y destinos inequívocos. Resuelve
    llamadas propias, this, clases del mismo paquete, imports explícitos normales
    y estáticos, y receptores con tipo declarado en parámetros, variables o campos.
    No incluye recursión directa, APIs externas, referencias ::, imports comodín,
    tipos var, super, ni llamadas encadenadas con tipo desconocido. Los destinos
    sobrecargados se omiten: no se elige una firma por conjetura.
    """
    clases: dict[tuple[str, str], _Clase] = {}
    por_tipo: dict[str, list[_Clase]] = defaultdict(list)
    objetivos = {(m["ruta"], f["nombre"]): f for m in modulos for f in m["funciones"]}
    for modulo in modulos:
        ruta = modulo["ruta"]
        raiz = arboles[ruta]
        paquete = next(
            (
                n.named_children[-1].text.decode("utf-8")
                for n in raiz.named_children
                if n.type == "package_declaration"
            ),
            "",
        )
        for nombre, nodo in _clases(raiz):
            cuerpo = nodo.child_by_field_name("body")
            metodos: dict[str, list[Node]] = defaultdict(list)
            campos = {}
            if cuerpo is not None:
                for miembro in cuerpo.named_children:
                    if miembro.type == "method_declaration":
                        metodos[_texto(miembro.child_by_field_name("name"))].append(
                            miembro
                        )
                    elif miembro.type in {"field_declaration", "constant_declaration"}:
                        campos.update(_variables(miembro))
            parametros = nodo.child_by_field_name("parameters")
            if parametros is not None:  # Componentes de un record.
                campos.update(_parametros(parametros))
            clase = _Clase(ruta, nombre, paquete, nodo, dict(metodos), campos)
            clases[(ruta, nombre)] = clase
            por_tipo[clase.calificado].append(clase)
    for modulo in modulos:
        imports, estaticos = _imports(arboles[modulo["ruta"]])
        for funcion in modulo["funciones"]:
            clase = clases[(modulo["ruta"], funcion["clase"])]
            declaraciones = clase.metodos[funcion["nombre"].rsplit(".", 1)[-1]]
            funcion["llama_a"] = []
            if len(declaraciones) != 1:
                continue
            metodo = declaraciones[0]
            imports_metodo = {
                **imports,
                **{n: [] for n in _tipos_ocultos(clase.nodo, metodo)},
            }
            nodos = list(nodos_del_cuerpo(metodo))
            variables = dict(clase.campos)
            variables.update(_parametros(metodo.child_by_field_name("parameters")))
            for nodo in nodos:
                if nodo.type == "local_variable_declaration":
                    variables.update(_variables(nodo))
                elif nodo.type in {
                    "enhanced_for_statement",
                    "catch_formal_parameter",
                    "resource",
                }:
                    nombre = nodo.child_by_field_name("name")
                    if nombre is not None:
                        variables[_texto(nombre)] = _texto(
                            nodo.child_by_field_name("type")
                        )
            encontrados = set()
            for llamada in (n for n in nodos if n.type == "method_invocation"):
                nombre = _texto(llamada.child_by_field_name("name"))
                objeto = _texto(llamada.child_by_field_name("object"))
                destino = _destino(
                    clase,
                    objeto,
                    nombre,
                    variables,
                    imports_metodo,
                    estaticos,
                    por_tipo,
                )
                if destino is None:
                    continue
                if len(por_tipo[destino.calificado]) != 1:
                    continue
                candidatos = destino.metodos.get(nombre, [])
                clave = (destino.modulo, destino.nombre + "." + nombre)
                if (
                    len(candidatos) != 1
                    or clave not in objetivos
                    or clave == (modulo["ruta"], funcion["nombre"])
                ):
                    continue
                if not _aridad_correcta(candidatos[0], llamada):
                    continue
                # Un receptor escrito como tipo requiere un método static.
                por_instancia = (
                    objeto in {"", "this"}
                    or objeto in variables
                    or objeto.startswith("this.")
                )
                if not por_instancia and not objetivos[clave]["es_static"]:
                    continue
                if (
                    not objeto
                    and destino is not clase
                    and not objetivos[clave]["es_static"]
                ):
                    continue
                encontrados.add(f"{clave[0]}::{clave[1]}")
            funcion["llama_a"] = sorted(encontrados)


def _clases(contenedor: Node, prefijo: str = "") -> list[tuple[str, Node]]:
    """Lista clases declaradas, sin entrar en métodos ni ámbitos locales."""
    resultado = []
    for nodo in contenedor.named_children:
        if nodo.type not in _TIPOS_CLASE:
            continue
        nombre = prefijo + _texto(nodo.child_by_field_name("name"))
        resultado.append((nombre, nodo))
        cuerpo = nodo.child_by_field_name("body")
        if cuerpo is not None:
            resultado.extend(_clases(cuerpo, nombre + "."))
    return resultado


def _texto(nodo: Node | None) -> str:
    """Texto literal UTF-8 o cadena vacía si el campo no existe."""
    return nodo.text.decode("utf-8") if nodo is not None else ""


def _variables(nodo: Node) -> dict[str, str]:
    """Nombres y tipo escrito de campos o variables, incluidas declaraciones múltiples."""
    tipo = _texto(nodo.child_by_field_name("type"))
    return {
        _texto(h.child_by_field_name("name")): tipo
        + ("[]" if h.child_by_field_name("dimensions") is not None else "")
        for h in nodo.named_children
        if h.type == "variable_declarator"
    }


def _parametros(nodo: Node | None) -> dict[str, str]:
    """Nombres y tipos de parámetros; también bloquea receptores varargs desconocidos."""
    if nodo is None:
        return {}
    resultado = {}
    for parametro in nodo.named_children:
        nombre = parametro.child_by_field_name("name")
        tipo = parametro.child_by_field_name("type")
        if parametro.type == "spread_parameter":
            declarador = next(
                (
                    h
                    for h in parametro.named_children
                    if h.type == "variable_declarator"
                ),
                None,
            )
            nombre = (
                declarador.child_by_field_name("name")
                if declarador is not None
                else None
            )
            tipo = None  # Un array no es una instancia de su tipo de elemento.
        if nombre is not None:
            sufijo = (
                "[]" if parametro.child_by_field_name("dimensions") is not None else ""
            )
            resultado[_texto(nombre)] = _texto(tipo) + sufijo
    return resultado


def _imports(raiz: Node) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Lee imports explícitos del AST; conserva colisiones para omitir ambigüedades."""
    tipos: dict[str, list[str]] = defaultdict(list)
    estaticos: dict[str, list[str]] = defaultdict(list)
    for nodo in raiz.named_children:
        if nodo.type != "import_declaration":
            continue
        partes = re.fullmatch(r"import\s+(static\s+)?([\w.$]+)\s*;", _texto(nodo))
        if partes:
            calificado = partes[2]
            if partes[1]:
                clase, _, metodo = calificado.rpartition(".")
                estaticos[metodo].append(clase)
            else:
                tipos[calificado.rsplit(".", 1)[-1]].append(calificado)
    return dict(tipos), dict(estaticos)


def _tipo(
    nombre: str,
    clase: _Clase,
    imports: dict[str, list[str]],
    indice: dict[str, list[_Clase]],
) -> _Clase | None:
    """Resuelve un tipo escrito; no busca por nombre simple en todo el proyecto."""
    if "[" in nombre or "]" in nombre:
        return None
    nombre = nombre.split("<", 1)[0].strip()
    if not re.fullmatch(r"[\w$]+(?:\.[\w$]+)*", nombre):
        return None
    primero, _, resto = nombre.partition(".")
    if primero in imports:
        opciones = [n + ("." + resto if resto else "") for n in imports[primero]]
    else:
        opciones = [f"{clase.paquete}.{nombre}" if clase.paquete else nombre]
        if "." in nombre:
            opciones.append(nombre)
    if primero not in imports and (
        nombre == clase.nombre or nombre == clase.nombre.rsplit(".", 1)[-1]
    ):
        opciones.append(clase.calificado)
    candidatas = {id(c): c for o in set(opciones) for c in indice.get(o, [])}
    return next(iter(candidatas.values())) if len(candidatas) == 1 else None


def _destino(
    clase: _Clase,
    objeto: str,
    nombre: str,
    variables: dict[str, str],
    imports: dict[str, list[str]],
    estaticos: dict[str, list[str]],
    indice: dict[str, list[_Clase]],
) -> _Clase | None:
    """Identifica el tipo declarado del receptor; las variables ocultan nombres de tipos."""
    if objeto in {"", "this"}:
        if clase.nodo.child_by_field_name("superclass") is not None:
            return None  # No se conocen las posibles sobrecargas heredadas.
        if nombre in clase.metodos:
            return clase
        if objeto or len(estaticos.get(nombre, [])) != 1:
            return None
        candidatos = indice.get(estaticos[nombre][0], [])
        return candidatos[0] if len(candidatos) == 1 else None
    if objeto.startswith("this."):
        return _tipo(clase.campos.get(objeto[5:], ""), clase, imports, indice)
    if objeto in variables:
        return _tipo(variables[objeto], clase, imports, indice)
    if objeto.split(".", 1)[0] in variables:
        return None
    if objeto == "super":
        return None
    return _tipo(objeto, clase, imports, indice)


def _tipos_ocultos(clase: Node, metodo: Node) -> set[str]:
    """Tipos locales y parámetros genéricos que ocultan imports del método."""
    resultado = set()
    for nodo in (clase, metodo):
        parametros = nodo.child_by_field_name("type_parameters")
        if parametros is not None:
            for parametro in parametros.named_children:
                nombre = next(
                    (
                        h
                        for h in parametro.named_children
                        if h.type == "type_identifier"
                    ),
                    None,
                )
                if nombre is not None:
                    resultado.add(_texto(nombre))
    cuerpo = metodo.child_by_field_name("body")
    pendientes = list(cuerpo.named_children) if cuerpo is not None else []
    while pendientes:
        nodo = pendientes.pop()
        if nodo.type in _TIPOS_CLASE:
            resultado.add(_texto(nodo.child_by_field_name("name")))
        elif nodo.type not in {"class_body", "lambda_expression"}:
            pendientes.extend(nodo.named_children)
    return resultado


def _aridad_correcta(metodo: Node, llamada: Node) -> bool:
    """Descarta llamadas cuya cantidad de argumentos no encaja; no infiere tipos."""
    parametros = metodo.child_by_field_name("parameters")
    argumentos = llamada.child_by_field_name("arguments")
    if parametros is None or argumentos is None:
        return False
    declarados = [
        p
        for p in parametros.named_children
        if p.type in {"formal_parameter", "spread_parameter"}
    ]
    recibidos = len(argumentos.named_children)
    return (
        recibidos >= len(declarados) - 1
        if declarados and declarados[-1].type == "spread_parameter"
        else recibidos == len(declarados)
    )

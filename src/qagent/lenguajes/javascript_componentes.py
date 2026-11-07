"""Componentes React de JavaScript y TypeScript: detección y props tipadas (#171).

Todo es estático con tree-sitter (ADR-009): nunca se importa, transpila ni renderiza
el código del usuario. El framework de interfaz sale de ``package.json``
(``dependencies`` y ``devDependencies``); un componente es una función exportada con
nombre en PascalCase cuyo cuerpo devuelve JSX. Sus props salen del tipo de
TypeScript (``interface`` o ``type`` del mismo archivo, tipo en línea o
``React.FC<Props>``) o del JSDoc (``@param {string} props.etiqueta``). El oráculo de
las pruebas son esos tipos y el JSDoc, nunca lo que el componente renderiza.

Fuera de este alcance (quedan como funciones o se ignoran): componentes de clase,
componentes envueltos en ``memo``/``forwardRef``, props importadas de otro archivo y
``propTypes``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tree_sitter import Node

from qagent.lenguajes.javascript_estructura import (
    Exportada,
    contar_ramas,
    desglosar_jsdoc,
    firma,
    jsdoc_de,
    nodos_del_cuerpo,
)

#: Framework de componentes que QAgent prueba con Testing Library.
FRAMEWORK_REACT = "react"
#: Frameworks de interfaz detectables sin soporte: paquete → nombre para personas.
FRAMEWORKS_NO_SOPORTADOS = {
    "@angular/core": "Angular",
    "astro": "Astro",
    "vue": "Vue",
    "svelte": "Svelte",
    "solid-js": "Solid",
    "preact": "Preact",
}
#: Texto que el informe muestra cuando el framework de interfaz no tiene soporte.
AVISO_NO_SOPORTADOS = "componentes no soportados"
#: Motivo de un componente que no recibe prueba (CA5).
MOTIVO_SIN_ORACULO = (
    "sin resultado esperado verificable: el componente no declara props tipadas "
    "ni JSDoc"
)

_JSX = frozenset({"jsx_element", "jsx_self_closing_element"})
_PASCAL = re.compile(r"^[A-Z][A-Za-z0-9_$]*$")
_EVENTO = re.compile(r"^on[A-Z]")
_TIPOS_COMPONENTE = re.compile(
    r"^(?:React\.)?(?:FC|FunctionComponent|VFC|ComponentProps)\s*<", re.DOTALL
)


def _texto(nodo: Node | None) -> str | None:
    return nodo.text.decode("utf-8") if nodo is not None else None


# --- Framework desde package.json -----------------------------------------------------


def dependencias_de_package(raiz: str | Path) -> dict[str, Any]:
    """``dependencies`` y ``devDependencies`` de ``package.json``; vacío si no se lee."""
    try:
        paquete = json.loads((Path(raiz) / "package.json").read_text("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(paquete, dict):
        return {}
    dependencias: dict[str, Any] = {}
    for clave in ("dependencies", "devDependencies"):
        seccion = paquete.get(clave)
        if isinstance(seccion, dict):
            dependencias.update(seccion)
    return dependencias


def detectar_framework_ui(raiz: str | Path) -> dict[str, Any] | None:
    """Framework de interfaz declarado en ``package.json``, o None si no hay ninguno.

    Devuelve ``{"framework", "nombre", "soportado", "aviso"}``. React tiene soporte;
    los demás frameworks conocidos (Angular, Astro, Vue…) se informan con
    :data:`AVISO_NO_SOPORTADOS` y solo se prueban sus archivos de lógica.
    """
    dependencias = dependencias_de_package(raiz)
    if FRAMEWORK_REACT in dependencias:
        return {
            "framework": FRAMEWORK_REACT,
            "nombre": "React",
            "soportado": True,
            "aviso": None,
        }
    for paquete, nombre in FRAMEWORKS_NO_SOPORTADOS.items():
        if paquete in dependencias:
            return {
                "framework": paquete,
                "nombre": nombre,
                "soportado": False,
                "aviso": AVISO_NO_SOPORTADOS,
            }
    return None


# --- Componentes ----------------------------------------------------------------------


def devuelve_jsx(funcion: Node) -> bool:
    """Si el cuerpo propio de la función contiene JSX (sin contar funciones anidadas)."""
    return any(nodo.type in _JSX for nodo in nodos_del_cuerpo(funcion))


def es_componente(exportada: Exportada) -> bool:
    """Función exportada en PascalCase que devuelve JSX; los métodos no cuentan."""
    nombre = exportada.nombre
    return (
        exportada.clase is None
        and bool(_PASCAL.match(nombre if nombre != "default" else ""))
        and exportada.nodo.type != "method_definition"
        and devuelve_jsx(exportada.nodo)
    )


def tipos_locales(raiz: Node) -> dict[str, Node]:
    """``interface X {…}`` y ``type X = {…}`` de primer nivel: nombre → cuerpo."""
    tipos: dict[str, Node] = {}
    for sentencia in raiz.named_children:
        declaracion = sentencia
        if sentencia.type == "export_statement":
            declaracion = sentencia.child_by_field_name("declaration")
            if declaracion is None:
                continue
        if declaracion.type == "interface_declaration":
            cuerpo = declaracion.child_by_field_name("body")
        elif declaracion.type == "type_alias_declaration":
            cuerpo = declaracion.child_by_field_name("value")
        else:
            continue
        nombre = _texto(declaracion.child_by_field_name("name"))
        if nombre and cuerpo is not None:
            tipos.setdefault(nombre, cuerpo)
    return tipos


def _primer_parametro(funcion: Node) -> Node | None:
    lista = funcion.child_by_field_name("parameters")
    if lista is None:
        return funcion.child_by_field_name("parameter")
    hijos = [h for h in lista.named_children if h.type != "comment"]
    return hijos[0] if hijos else None


def _anotacion_del_declarador(funcion: Node) -> Node | None:
    """``React.FC<Props>`` de ``const X: React.FC<Props> = (…) => …``: el argumento."""
    declarador = funcion.parent
    if declarador is None or declarador.type != "variable_declarator":
        return None
    anotacion = declarador.child_by_field_name("type")
    tipo = (
        anotacion.named_children[0] if anotacion and anotacion.named_children else None
    )
    if tipo is None or tipo.type != "generic_type":
        return None
    if not _TIPOS_COMPONENTE.match(_texto(tipo) or ""):
        return None
    argumentos = next(
        (h for h in tipo.named_children if h.type == "type_arguments"), None
    )
    return (
        argumentos.named_children[0]
        if argumentos and argumentos.named_children
        else None
    )


def _cuerpo_de_tipo(tipo: Node | None, locales: dict[str, Node]) -> Node | None:
    """Cuerpo con las propiedades: tipo en línea o ``interface``/``type`` local."""
    if tipo is None:
        return None
    if tipo.type in {"object_type", "interface_body"}:
        return tipo
    if tipo.type == "type_identifier":
        cuerpo = locales.get(_texto(tipo) or "")
        return (
            cuerpo
            if cuerpo is not None
            and cuerpo.type
            in {
                "object_type",
                "interface_body",
            }
            else None
        )
    return None


def _defectos(patron: Node | None) -> dict[str, str]:
    """Valores por defecto de ``{ a = 1, b }`` en la desestructuración de las props."""
    if patron is None or patron.type != "object_pattern":
        return {}
    defectos = {}
    for hijo in patron.named_children:
        if hijo.type == "object_assignment_pattern":
            izquierda = hijo.child_by_field_name("left")
            derecha = hijo.child_by_field_name("right")
            if izquierda is not None and derecha is not None:
                defectos[_texto(izquierda) or ""] = _texto(derecha) or ""
    return defectos


def _props_typescript(cuerpo: Node, defectos: dict[str, str]) -> list[dict[str, Any]]:
    props = []
    anterior: Node | None = None
    for miembro in cuerpo.named_children:
        if miembro.type != "property_signature":
            anterior = miembro
            continue
        nombre = _texto(miembro.child_by_field_name("name")) or ""
        anotacion = miembro.child_by_field_name("type")
        tipo = (
            _texto(anotacion.named_children[0])
            if anotacion and anotacion.named_children
            else None
        )
        descripcion = None
        if (
            anterior is not None
            and anterior.type == "comment"
            and (_texto(anterior) or "").startswith("/**")
        ):
            descripcion = (desglosar_jsdoc(_texto(anterior)) or {}).get("descripcion")
        props.append(
            {
                "nombre": nombre,
                "tipo": tipo,
                "opcional": any(h.type == "?" for h in miembro.children)
                or nombre in defectos,
                "por_defecto": defectos.get(nombre),
                "descripcion": descripcion or "",
                "evento": bool(_EVENTO.match(nombre))
                and anotacion is not None
                and bool(anotacion.named_children)
                and anotacion.named_children[0].type == "function_type",
            }
        )
        anterior = miembro
    return props


def _props_jsdoc(
    jsdoc: dict[str, Any] | None, defectos: dict[str, str]
) -> list[dict[str, Any]]:
    """``@param {T} props.x`` (o ``param0.x``): una prop por cada etiqueta con punto."""
    props = []
    for nombre_completo, datos in ((jsdoc or {}).get("parametros") or {}).items():
        if "." not in nombre_completo:
            continue
        nombre = nombre_completo.rsplit(".", 1)[-1]
        tipo = datos.get("tipo")
        defecto = datos.get("por_defecto") or defectos.get(nombre)
        props.append(
            {
                "nombre": nombre,
                "tipo": tipo,
                "opcional": bool(datos.get("opcional")) or defecto is not None,
                "por_defecto": defecto,
                "descripcion": datos.get("descripcion") or "",
                "evento": bool(_EVENTO.match(nombre))
                and bool(tipo)
                and ("=>" in tipo or tipo.strip().lower() == "function"),
            }
        )
    return props


def describir_componente(
    exportada: Exportada, locales: dict[str, Node]
) -> dict[str, Any]:
    """Descripción JSON de un componente: firma, JSDoc, props tipadas y si es verificable.

    ``props_tipadas`` exige al menos una prop y el tipo de cada una (de TypeScript o de
    JSDoc). ``verificable`` es ``props_tipadas`` o un JSDoc presente: un componente
    sin ninguno de los dos no recibe prueba (:data:`MOTIVO_SIN_ORACULO`).
    """
    nodo = exportada.nodo
    comentario = jsdoc_de(exportada.ancla)
    jsdoc = desglosar_jsdoc(*comentario) if comentario else None
    parametro = _primer_parametro(nodo)
    patron = parametro
    anotacion = None
    if parametro is not None and parametro.type in {
        "required_parameter",
        "optional_parameter",
    }:
        patron = parametro.child_by_field_name("pattern")
        tipo_parametro = parametro.child_by_field_name("type")
        if tipo_parametro is not None and tipo_parametro.named_children:
            anotacion = tipo_parametro.named_children[0]
    if patron is not None and patron.type == "assignment_pattern":
        patron = patron.child_by_field_name("left")
    defectos = _defectos(patron)
    cuerpo = _cuerpo_de_tipo(anotacion or _anotacion_del_declarador(nodo), locales)
    if cuerpo is not None:
        props, origen = _props_typescript(cuerpo, defectos), "typescript"
    else:
        props = _props_jsdoc(jsdoc, defectos)
        origen = "jsdoc" if props else None
    props_tipadas = bool(props) and all(p["tipo"] for p in props)
    ramas = contar_ramas(nodo)
    return {
        "nombre": exportada.nombre,
        "linea": nodo.start_point.row + 1,
        "firma": firma(exportada.nombre, nodo),
        "exportacion": exportada.exportacion,
        "docstring": comentario[0] if comentario else None,
        "jsdoc": jsdoc,
        "props": props,
        "origen_props": origen,
        "props_tipadas": props_tipadas,
        "eventos": [p["nombre"] for p in props if p["evento"]],
        "verificable": props_tipadas or jsdoc is not None,
        "ramas": ramas,
    }


def separar_componentes(
    raiz: Node, exportadas: list[Exportada]
) -> tuple[list[Exportada], list[dict[str, Any]]]:
    """Divide las exportadas en funciones de lógica y componentes descritos."""
    locales = tipos_locales(raiz)
    funciones: list[Exportada] = []
    componentes: list[dict[str, Any]] = []
    for exportada in exportadas:
        if es_componente(exportada):
            componentes.append(describir_componente(exportada, locales))
        else:
            funciones.append(exportada)
    return funciones, componentes

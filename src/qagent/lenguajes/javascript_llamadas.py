"""Mapa estático de llamadas JS/TS a funciones exportadas del proyecto (#176).

No transpila, importa ni ejecuta fuentes. Resuelve por nombre las llamadas a
funciones del mismo módulo, a imports ESM y a ``require`` relativos (con alias,
espacios de nombres e índices de carpeta) y ``this.metodo()`` dentro de una clase.
Los paquetes de ``node_modules``, el despacho dinámico y los tipos inferidos
quedan fuera. El formato es el de Python: ``ruta/del/modulo.ts::funcion``.
"""

from __future__ import annotations

import posixpath
from typing import Any

from tree_sitter import Node

from qagent.lenguajes.javascript_estructura import (
    Exportada,
    declaraciones_locales,
    exportadas,
)

#: Orden de prueba al resolver ``./modulo`` sin extensión, como hacen TS y bundlers.
_EXTENSIONES = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".jsx")
#: En TS con ESM se importa ``./util.js`` aunque el archivo sea ``util.ts``.
_EQUIVALENTES_TS = {
    ".js": (".ts", ".tsx"),
    ".jsx": (".tsx",),
    ".mjs": (".mts",),
    ".cjs": (".cts",),
}

#: Un enlace del módulo: ("funcion", ruta, nombre) o ("modulo", ruta, "").
Enlace = tuple[str, str, str]


def _texto(nodo: Node | None) -> str:
    return nodo.text.decode("utf-8") if nodo is not None else ""


def _clave(nodo: Node) -> tuple[int, int]:
    return nodo.start_byte, nodo.end_byte


def resolver_modulo(origen: str, especificador: str, rutas: set[str]) -> str | None:
    """Ruta del módulo del proyecto que importa ``origen``; None si no es relativo.

    Prueba el archivo tal cual, su equivalente TS (``.js`` -> ``.ts``), las
    extensiones conocidas y ``index`` dentro de la carpeta. Nunca sale de la raíz.
    """
    if not especificador.startswith("."):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(origen), especificador))
    if base == ".." or base.startswith("../"):
        return None
    raiz, extension = posixpath.splitext(base)
    candidatos = [base]
    candidatos += [raiz + e for e in _EQUIVALENTES_TS.get(extension, ())]
    candidatos += [base + e for e in _EXTENSIONES]
    candidatos += [f"{base}/index{e}" for e in _EXTENSIONES]
    return next((c for c in candidatos if c in rutas), None)


def _cadena(nodo: Node | None) -> str | None:
    """Contenido de un literal de cadena (sin comillas); None si no es literal."""
    if nodo is None or nodo.type != "string":
        return None
    return "".join(_texto(h) for h in nodo.named_children)


def _requerido(valor: Node | None) -> str | None:
    """Especificador de ``require('./x')``; None si ``valor`` no es esa llamada."""
    if valor is None or valor.type != "call_expression":
        return None
    if _texto(valor.child_by_field_name("function")) != "require":
        return None
    argumentos = valor.child_by_field_name("arguments")
    hijos = argumentos.named_children if argumentos is not None else []
    return _cadena(hijos[0]) if len(hijos) == 1 else None


class _Proyecto:
    """Exportaciones de cada módulo y enlaces de nombres de cada archivo."""

    def __init__(self, arboles: dict[str, Node]) -> None:
        self.rutas = set(arboles)
        self.exportadas: dict[str, list[Exportada]] = {
            ruta: exportadas(raiz) for ruta, raiz in arboles.items()
        }
        self.enlaces = {
            ruta: self._enlaces(ruta, raiz) for ruta, raiz in arboles.items()
        }

    def _publicas(self, ruta: str) -> set[str]:
        return {e.nombre for e in self.exportadas[ruta]}

    def _por_defecto(self, ruta: str) -> str | None:
        """La función que entrega ``import x from`` o ``require`` del módulo entero."""
        return next(
            (
                e.nombre
                for e in self.exportadas[ruta]
                if e.exportacion in {"default", "commonjs_modulo"}
            ),
            None,
        )

    def _enlaces(self, ruta: str, raiz: Node) -> dict[str, Enlace]:
        enlaces: dict[str, Enlace] = {}
        nombre_de_nodo = {_clave(e.nodo): e.nombre for e in self.exportadas[ruta]}
        for local, (nodo, _) in declaraciones_locales(raiz).items():
            if _clave(nodo) in nombre_de_nodo:
                enlaces[local] = ("funcion", ruta, nombre_de_nodo[_clave(nodo)])
        for sentencia in raiz.named_children:
            if sentencia.type == "import_statement":
                self._enlaces_import(ruta, sentencia, enlaces)
            elif sentencia.type in {"lexical_declaration", "variable_declaration"}:
                for declarador in sentencia.named_children:
                    if declarador.type == "variable_declarator":
                        self._enlaces_require(ruta, declarador, enlaces)
        return enlaces

    def _enlaces_import(
        self, ruta: str, sentencia: Node, enlaces: dict[str, Enlace]
    ) -> None:
        destino = resolver_modulo(
            ruta, _cadena(sentencia.child_by_field_name("source")) or "", self.rutas
        )
        if destino is None:
            return
        clausula = next(
            (h for h in sentencia.named_children if h.type == "import_clause"), None
        )
        for parte in clausula.named_children if clausula is not None else []:
            if parte.type == "identifier":
                defecto = self._por_defecto(destino)
                if defecto is not None:
                    enlaces[_texto(parte)] = ("funcion", destino, defecto)
            elif parte.type == "namespace_import":
                nombre = next(
                    (h for h in parte.named_children if h.type == "identifier"), None
                )
                if nombre is not None:
                    enlaces[_texto(nombre)] = ("modulo", destino, "")
            elif parte.type == "named_imports":
                for especificador in parte.named_children:
                    if especificador.type != "import_specifier":
                        continue
                    original = _texto(especificador.child_by_field_name("name"))
                    alias = (
                        _texto(especificador.child_by_field_name("alias")) or original
                    )
                    enlaces[alias] = ("funcion", destino, original)

    def _enlaces_require(
        self, ruta: str, declarador: Node, enlaces: dict[str, Enlace]
    ) -> None:
        especificador = _requerido(declarador.child_by_field_name("value"))
        destino = resolver_modulo(ruta, especificador or "", self.rutas)
        if destino is None:
            return
        patron = declarador.child_by_field_name("name")
        if patron is None:
            return
        if patron.type == "identifier":
            enlaces[_texto(patron)] = ("modulo", destino, "")
        elif patron.type == "object_pattern":
            for propiedad in patron.named_children:
                if propiedad.type == "shorthand_property_identifier_pattern":
                    enlaces[_texto(propiedad)] = ("funcion", destino, _texto(propiedad))
                elif propiedad.type == "pair_pattern":
                    clave = _texto(propiedad.child_by_field_name("key"))
                    valor = propiedad.child_by_field_name("value")
                    if valor is not None and valor.type == "identifier":
                        enlaces[_texto(valor)] = ("funcion", destino, clave)

    def destino(self, ruta: str, exportada: Exportada, llamado: Node) -> str | None:
        """``ruta::nombre`` de una función exportada que invoca ``llamado``, o None."""
        enlaces = self.enlaces[ruta]
        if llamado.type == "identifier":
            enlace = enlaces.get(_texto(llamado))
            if enlace is None:
                return None
            tipo, modulo, nombre = enlace
            if tipo == "modulo":  # const calcular = require('./calcular'); calcular()
                nombre = self._por_defecto(modulo) or ""
            return self._si_publica(modulo, nombre)
        if llamado.type != "member_expression":
            return None
        objeto = llamado.child_by_field_name("object")
        propiedad = _texto(llamado.child_by_field_name("property"))
        if objeto is not None and objeto.type == "this" and exportada.clase:
            return self._si_publica(ruta, f"{exportada.clase}.{propiedad}")
        enlace = enlaces.get(_texto(objeto))
        if enlace is not None and enlace[0] == "modulo":
            return self._si_publica(enlace[1], propiedad)
        if enlace is not None and enlace[0] == "funcion":  # Clase.estatico()
            return self._si_publica(enlace[1], f"{enlace[2]}.{propiedad}")
        if _texto(objeto) in {e.clase for e in self.exportadas[ruta] if e.clase}:
            return self._si_publica(ruta, f"{_texto(objeto)}.{propiedad}")
        return None

    def _si_publica(self, modulo: str, nombre: str) -> str | None:
        return f"{modulo}::{nombre}" if nombre in self._publicas(modulo) else None


def _llamadas(funcion: Node) -> list[Node]:
    """Lo invocado en el cuerpo, también dentro de callbacks (``xs.map(x => f(x))``).

    A diferencia de las ramas, las llamadas de una función anidada sí cuentan: el
    callback corre como parte de la función y el Generator debe poder simularlas.
    """
    cuerpo = funcion.child_by_field_name("body")
    pendientes = [cuerpo] if cuerpo is not None else []
    llamados = []
    while pendientes:
        nodo = pendientes.pop()
        if nodo.type == "call_expression":
            llamado = nodo.child_by_field_name("function")
            if llamado is not None:
                llamados.append(llamado)
        pendientes.extend(nodo.named_children)
    return llamados


def agregar_llamadas(modulos: list[dict[str, Any]], arboles: dict[str, Node]) -> None:
    """Agrega ``llama_a`` (ordenado, sin la propia función) a cada función analizada."""
    proyecto = _Proyecto(arboles)
    for modulo in modulos:
        ruta = modulo["ruta"]
        por_nombre = {e.nombre: e for e in proyecto.exportadas[ruta]}
        for funcion in modulo["funciones"]:
            exportada = por_nombre[funcion["nombre"]]
            propia = f"{ruta}::{funcion['nombre']}"
            destinos = {
                proyecto.destino(ruta, exportada, llamado)
                for llamado in _llamadas(exportada.nodo)
            }
            funcion["llama_a"] = sorted(d for d in destinos if d and d != propia)

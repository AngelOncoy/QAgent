"""Capacidades y representación JSON compartidas de colecciones Java (#300)."""

from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass
from typing import Any

ESCALARES = frozenset(
    {
        "String",
        "Boolean",
        "Byte",
        "Short",
        "Integer",
        "Long",
        "Character",
        "Float",
        "Double",
    }
)
FAMILIAS = {
    "List": "java.util.List",
    "Set": "java.util.Set",
    "Collection": "java.util.Collection",
    "Iterable": "java.lang.Iterable",
}
ENTEROS = {
    "Byte": (-128, 127),
    "Short": (-32768, 32767),
    "Integer": (-(2**31), 2**31 - 1),
    "Long": (-(2**63), 2**63 - 1),
}


@dataclass(frozen=True)
class TipoValor:
    """Tipo nominal cerrado; un elemento no resuelto no justifica igualdad."""

    nombre: str
    elemento: TipoValor | None = None


@dataclass(frozen=True)
class ConjuntoLiteral:
    """Valor estático de una fábrica Set, separado de arrays y listas ordenadas."""

    elementos: tuple[Any, ...]


def tipo_coleccion(tipo: str) -> TipoValor | None:
    """Reconoce un parámetro genérico, sin wildcards, tipos crudos ni homónimos."""
    compacto = re.sub(r"\s+", "", tipo)
    if len(compacto) > 512:
        return None

    def leer(t: str, profundidad: int = 0) -> TipoValor | None:
        if profundidad > 8:
            return None
        simple = t.removeprefix("java.lang.")
        if simple in ESCALARES:
            return TipoValor(simple)
        m = re.fullmatch(r"([\w.]+)<(.+)>", t)
        if not m:
            return None
        nombre = m[1].rsplit(".", 1)[-1]
        if nombre not in FAMILIAS or m[1] not in {nombre, FAMILIAS[nombre]}:
            return None
        hijo = leer(m[2], profundidad + 1)
        return TipoValor(nombre, hijo) if hijo else None

    resultado = leer(compacto)
    if not resultado or resultado.elemento is None:
        return None

    def seguros(t: TipoValor, iteracion: bool = False) -> bool:
        if t.elemento is None:
            return True
        if t.nombre in {"Collection", "Iterable"}:
            return False
        if iteracion and t.nombre == "Set":
            return False
        return seguros(t.elemento, iteracion)

    return (
        resultado
        if seguros(resultado.elemento, resultado.nombre in {"Collection", "Iterable"})
        else None
    )


def es_tipo_coleccion(tipo: str) -> bool:
    """Incluye nombres rechazados para no caer en el filtro permisivo legado."""
    return bool(
        re.search(
            r"(?:^|[.<])(?:List|Set|Collection|Iterable|Map|SortedSet|NavigableSet|Queue|Deque)(?:<|$)",
            re.sub(r"\s+", "", tipo),
        )
    )


def clave_valor(tipo: TipoValor, valor: Any) -> Any:
    """Igualdad Java de los valores admitidos; Set ignora orden, List lo conserva."""
    if valor is None:
        return ("null",)
    if tipo.elemento is not None:
        hijos = [clave_valor(tipo.elemento, v) for v in valor]
        return (
            tipo.nombre,
            tuple(sorted(hijos, key=repr)) if tipo.nombre == "Set" else tuple(hijos),
        )
    if tipo.nombre in {"Float", "Double"}:
        return (
            tipo.nombre,
            struct.pack(">f" if tipo.nombre == "Float" else ">d", float(valor)),
        )
    return (tipo.nombre, valor)


def compatible_coleccion(tipo: str, valor: Any) -> bool:
    """Comprueba datos JSON y duplicados sin normalizar ni modificar el contrato."""
    modelo = tipo_coleccion(tipo)
    if modelo is None:
        return False

    def compatible(t: TipoValor, v: Any) -> bool:
        if v is None:
            return True
        if t.elemento is not None:
            if not isinstance(v, list) or not all(compatible(t.elemento, e) for e in v):
                return False
            if t.nombre == "Set":
                claves = [clave_valor(t.elemento, e) for e in v]
                return len(claves) == len(set(claves))
            return True
        if t.nombre == "String":
            return isinstance(v, str) and not any(0xD800 <= ord(c) <= 0xDFFF for c in v)
        if t.nombre == "Character":
            return (
                isinstance(v, str)
                and len(v) == 1
                and ord(v) <= 0xFFFF
                and not 0xD800 <= ord(v) <= 0xDFFF
            )
        if t.nombre == "Boolean":
            return type(v) is bool
        if t.nombre in ENTEROS:
            minimo, maximo = ENTEROS[t.nombre]
            return type(v) is int and minimo <= v <= maximo
        if t.nombre in {"Float", "Double"}:
            if type(v) not in {int, float}:
                return False
            try:
                numero = float(v)
                if not math.isfinite(numero) or (
                    numero == 0 and math.copysign(1, numero) < 0
                ):
                    return False  # El subconjunto no equipara ceros con signo en colecciones.
                convertido = struct.unpack(
                    ">f" if t.nombre == "Float" else ">d",
                    struct.pack(">f" if t.nombre == "Float" else ">d", numero),
                )[0]
                return math.isfinite(convertido) and (convertido != 0 or numero == 0)
            except (OverflowError, ValueError):
                return False
        return False

    return compatible(modelo, valor)


def expresion_coleccion(tipo: str, valor: Any) -> str:
    """Escribe una forma verificable desde el contrato; nunca deduce un esperado."""
    modelo = tipo_coleccion(tipo)
    if modelo is None or not compatible_coleccion(tipo, valor):
        raise ValueError(
            "Colección Java no representable por la matriz de capacidades."
        )

    def escribir(t: TipoValor, v: Any) -> str:
        if v is None:
            return "null"
        if t.elemento is not None:
            elementos = [escribir(t.elemento, e) for e in v]
            if not elementos:
                return (
                    "java.util.Set.of()" if t.nombre == "Set" else "java.util.List.of()"
                )
            if any(e is None for e in v):
                if len(v) == 1:
                    return (
                        "java.util.Collections.singleton"
                        if t.nombre == "Set"
                        else "java.util.Collections.singletonList"
                    ) + "(null)"
                lista = "java.util.Arrays.asList(" + ", ".join(elementos) + ")"
                return (
                    "new java.util.HashSet<>(" + lista + ")"
                    if t.nombre == "Set"
                    else lista
                )
            fabrica = "Set" if t.nombre == "Set" else "List"
            return "java.util." + fabrica + ".of(" + ", ".join(elementos) + ")"
        if t.nombre == "String":
            return json.dumps(v, ensure_ascii=True)
        if t.nombre == "Character":
            escapes = {
                "\n": "\\n",
                "\r": "\\r",
                "\t": "\\t",
                "\b": "\\b",
                "\f": "\\f",
                "'": "\\'",
                "\\": "\\\\",
            }
            interior = escapes.get(v, v)
            if v not in escapes and (ord(v) < 32 or 127 <= ord(v) < 160):
                interior = f"\\u{ord(v):04x}"
            return "'" + interior + "'"
        if t.nombre == "Boolean":
            return "true" if v else "false"
        if t.nombre in {"Byte", "Short"}:
            return "(" + t.nombre.lower() + ")" + str(v)
        if t.nombre == "Long":
            return str(v) + "L"
        if t.nombre in {"Float", "Double"}:
            return str(v) + ("f" if t.nombre == "Float" else "d")
        return str(v)

    return escribir(modelo, valor)


def reglas_colecciones() -> str:
    """Una misma matriz declarada en prompts de planificación y generación."""
    return (
        "Colecciones verificables: List<T> (JSON array ordenado, duplicados permitidos, assertEquals); "
        "Set<T> (JSON array sin duplicados semánticos, sin orden, assertEquals con Set); "
        "Collection<T>/Iterable<T> (JSON array en orden de iteración documentado, assertIterableEquals con List). "
        "T: String, Boolean, Byte, Short, Integer, Long, Character, Float o Double de java.lang, "
        "o List/Set anidados; Collection/Iterable admiten anidación de List, no Set. "
        "No Map, tipos crudos, wildcards, arrays u objetos arbitrarios dentro de colecciones; "
        "no números no finitos ni cero flotante negativo. null de colección se representa como JSON null "
        "y assertNull directo. Elementos null se permiten con Arrays.asList, singletonList o "
        "HashSet(Arrays.asList), nunca List.of/Set.of con null. Vacíos usan List.of()/Set.of(). "
        "No inventes orden ni dedupliques o cambies el valor JSON. Usa sufijos L/f/d, casts byte/short "
        "acotados o literales char para conservar el tipo del elemento. "
    )

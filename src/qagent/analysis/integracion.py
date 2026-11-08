"""Cadenas de funciones para las pruebas de integración interna (#245, ADR-014).

Dado el análisis estático de un proyecto Python (``analizar_proyecto``), elige las
funciones **raíz** que llaman a otras funciones del mismo proyecto y arma su cadena:
la raíz más las funciones internas que se ejecutarán de verdad en la prueba. Todo es
estático (tree-sitter), sin ejecutar nada del usuario y sin gastar tokens.

Qué se simula y qué no (ADR-014, 4.3):

* una función interna **pura** (sin entrada/salida, red, base de datos, reloj ni azar)
  entra en la cadena y se llama de verdad;
* una función interna **de efecto** no entra: la prueba la simula, igual que los
  efectos de la propia raíz;
* ante la duda se trata como de efecto, nunca al revés.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter import Node

from qagent.analysis import arbol_ts
from qagent.analysis.arbol_ts import campo, definicion, es_funcion, nombre, sentencias, texto

#: Módulos cuyo uso hace que una función sea «de efecto»: red, base de datos, sistema
#: de archivos, subprocesos, hora y azar. Si dudamos de un módulo, va aquí.
MODULOS_DE_EFECTO = frozenset(
    {
        "requests", "httpx", "urllib", "urllib3", "aiohttp", "socket", "http",
        "smtplib", "ftplib", "sqlite3", "sqlalchemy", "psycopg2", "pymongo", "redis",
        "boto3", "subprocess", "os", "shutil", "pathlib", "tempfile", "time",
        "datetime", "random", "secrets", "uuid",
    }
)  # fmt: skip

#: Funciones integradas de Python con efecto.
FUNCIONES_DE_EFECTO = frozenset({"open", "input"})


@dataclass(frozen=True)
class Cadena:
    """Una raíz y las funciones internas que se ejecutan de verdad junto con ella."""

    modulo: str
    raiz: str
    #: Raíz primero y luego las internas puras, en el orden en que se descubren.
    funciones: tuple[str, ...]
    #: Módulo de cada función de ``funciones``.
    modulos: dict[str, str] = field(default_factory=dict, hash=False)
    #: Funciones internas de efecto que la prueba debe simular (``ruta.py::nombre``).
    a_simular: tuple[str, ...] = ()
    #: Módulos de efecto que usa la propia raíz y que también se simulan.
    efectos_raiz: tuple[str, ...] = ()
    #: True si la cadena real era mayor que el límite y se recortó.
    recortada: bool = False


Lector = Callable[[str], "str | None"]


def lector_de_proyecto(raiz: str | Path) -> Lector:
    """Lee el texto de un módulo relativo a ``raiz``; ``None`` si no se puede."""
    base = Path(raiz)

    def leer(ruta: str) -> str | None:
        try:
            return (base / ruta).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    return leer


def efectos_de(fuente: str, funcion: str) -> tuple[str, ...]:
    """Módulos de efecto que usa ``funcion`` en ``fuente`` (vacío = pura).

    Un nombre importado de un módulo de efecto que aparece en el cuerpo, o una llamada
    a ``open``/``input``, cuentan como efecto.
    """
    arbol = arbol_ts.parsear(fuente)
    enlazados: dict[str, str] = {}
    for nodo in arbol_ts.recorrer(arbol.root_node):
        imp = arbol_ts.importacion(nodo)
        if imp is None or imp.nivel:
            continue
        if imp.desde:
            raiz = (imp.modulo or "").split(".")[0]
            if raiz in MODULOS_DE_EFECTO:
                for nombre_importado, alias in imp.nombres:
                    enlazados[alias or nombre_importado] = raiz
        else:
            for nombre_importado, alias in imp.nombres:
                raiz = nombre_importado.split(".")[0]
                if raiz in MODULOS_DE_EFECTO:
                    enlazados[alias or raiz] = raiz
    nodo_funcion = next(
        (
            definicion(n)
            for n in sentencias(arbol.root_node)
            if es_funcion(n) and nombre(n) == funcion
        ),
        None,
    )
    if nodo_funcion is None:
        return ()
    usados: set[str] = set()
    for nodo in arbol_ts.recorrer(nodo_funcion):
        if nodo.type != "identifier":
            continue
        identificador = texto(nodo)
        if identificador in enlazados:
            usados.add(enlazados[identificador])
        elif identificador in FUNCIONES_DE_EFECTO and _es_llamada(nodo):
            usados.add("builtins")
    return tuple(sorted(usados))


def _es_llamada(nodo: Node) -> bool:
    padre = nodo.parent
    return (
        padre is not None
        and padre.type == "call"
        and campo(padre, "function") == nodo
    )


def _indice(modulos: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (m["ruta"], f["nombre"]): f for m in modulos for f in m.get("funciones", [])
    }


def construir_cadena(
    modulos: list[dict[str, Any]],
    ruta: str,
    funcion: str,
    leer: Lector,
    *,
    profundidad_max: int = 2,
    max_funciones: int = 4,
) -> Cadena | None:
    """Cadena de ``funcion`` (en el módulo ``ruta``), o None si no es candidata.

    Es candidata si llama a al menos una función interna **pura**: si todas las
    internas son de efecto no queda nada que integrar y el tipo no se ofrece.
    """
    indice = _indice(modulos)
    raiz = indice.get((ruta, funcion))
    if raiz is None or not raiz.get("llama_a"):
        return None
    fuentes: dict[str, str | None] = {}

    def efectos(ruta_modulo: str, nombre_funcion: str) -> tuple[str, ...]:
        if ruta_modulo not in fuentes:
            fuentes[ruta_modulo] = leer(ruta_modulo)
        fuente = fuentes[ruta_modulo]
        if fuente is None:  # ante la duda, de efecto
            return ("desconocido",)
        return efectos_de(fuente, nombre_funcion)

    funciones = [funcion]
    ubicacion = {funcion: ruta}
    a_simular: list[str] = []
    recortada = False
    vistas = {(ruta, funcion)}
    nivel = [(ruta, funcion)]
    for _ in range(profundidad_max):
        siguiente: list[tuple[str, str]] = []
        for ruta_actual, nombre_actual in nivel:
            for destino in indice[(ruta_actual, nombre_actual)].get("llama_a", []):
                ruta_dest, _, nombre_dest = destino.partition("::")
                clave = (ruta_dest, nombre_dest)
                if clave in vistas or clave not in indice:
                    continue
                vistas.add(clave)
                if efectos(ruta_dest, nombre_dest) or nombre_dest in ubicacion:
                    a_simular.append(destino)  # de efecto o con el nombre repetido
                elif len(funciones) >= max_funciones:
                    recortada = True
                else:
                    funciones.append(nombre_dest)
                    ubicacion[nombre_dest] = ruta_dest
                    siguiente.append(clave)
        nivel = siguiente
    if any(indice[c].get("llama_a") for c in nivel):  # quedó más profundidad sin seguir
        recortada = True
    if len(funciones) < 2:
        return None
    return Cadena(
        modulo=ruta,
        raiz=funcion,
        funciones=tuple(funciones),
        modulos=ubicacion,
        a_simular=tuple(a_simular),
        efectos_raiz=efectos(ruta, funcion),
        recortada=recortada,
    )


def candidatas(
    modulos: list[dict[str, Any]],
    leer: Lector,
    *,
    profundidad_max: int = 2,
    max_funciones: int = 4,
) -> list[Cadena]:
    """Cadenas de todas las funciones candidatas, en el orden del análisis."""
    resultado = []
    for modulo in modulos:
        for funcion in modulo.get("funciones", []):
            cadena = construir_cadena(
                modulos,
                modulo["ruta"],
                funcion["nombre"],
                leer,
                profundidad_max=profundidad_max,
                max_funciones=max_funciones,
            )
            if cadena is not None:
                resultado.append(cadena)
    return resultado

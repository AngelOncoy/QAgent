"""Aísla el cuerpo de los manejadores FastAPI para que mutmut pueda mutarlos (#74).

mutmut 3 no muta funciones decoradas: copiar un `@app.post(...)` para su trampolín
registraría la ruta dos veces. Por eso, solo en la copia del proyecto que usa el sandbox,
cada manejador pedido se reescribe así (sin ejecutar nada, solo con tree-sitter):

    @app.post("/pedidos")                    # línea en blanco
    def crear(pedido: Pedido, db=Depends(get_db)):
        ...                                  # def _qagent_manejador_crear(...): mismo cuerpo

    @app.post("/pedidos")                    # envoltorio insertado tras el cuerpo, con
    def crear(pedido: Pedido, db=Depends(get_db)):  # la misma firma y decoradores
        return _qagent_manejador_crear(pedido, db)

La función aislada conserva el cuerpo exacto, sin decorador, y es lo único que se pide a
mutmut: no se mutan las dependencias (`Depends`), que en la prueba
están reemplazadas, ni los modelos Pydantic ni el resto del módulo. El envoltorio
conserva la firma, los decoradores y el orden de registro de las rutas, así que FastAPI
ve el mismo endpoint y las pruebas con `TestClient` no cambian.
"""

from __future__ import annotations

import re

from tree_sitter import Node, Tree

from qagent.analysis import arbol_ts, texto_ts
from qagent.analysis.arbol_ts import KWARGS, POSICIONAL, POSICIONAL_SOLO, SOLO_NOMBRE

#: Prefijo de la función que recibe el cuerpo del manejador en la copia del sandbox.
PREFIJO_AISLADO = "_qagent_manejador_"


def nombre_aislado(manejador: str) -> str:
    """Nombre de la función sin decorador que recibe el cuerpo de `manejador`."""
    return PREFIJO_AISLADO + manejador


def motivo_no_aislable(fuente: str, manejador: str) -> str | None:
    """Explica por qué no se puede aislar `manejador`, o None si se puede."""
    try:
        nodo = _manejadores_de(_parsear(fuente)).get(manejador)
    except (SyntaxError, ValueError):
        return "El módulo no se pudo analizar."
    if nodo is None:
        return f"No se encontró el manejador {manejador} al nivel del módulo."
    if not arbol_ts.decoradores(nodo):
        return f"{manejador} no tiene el decorador de la ruta."
    if arbol_ts.es_async(nodo) and _tiene_yield(nodo):
        return f"{manejador} es un generador asíncrono; no se puede aislar."
    return None


def aislar_manejadores(fuente: str, manejadores: list[str]) -> str:
    """Reescribe `fuente` con el cuerpo de cada manejador en su función aislada.

    Args:
        fuente: código del módulo del usuario.
        manejadores: nombres de los manejadores a aislar (todos deben ser aislables,
            ver `motivo_no_aislable`).

    Returns:
        El código reescrito. Cada función aislada conserva el texto de su cuerpo, así que
        la línea de un cambio relativa a su `def` más la línea del `def` original ubica
        el sobreviviente en el archivo del usuario.

    Raises:
        ValueError: si algún manejador no se puede aislar.
    """
    for manejador in manejadores:
        motivo = motivo_no_aislable(fuente, manejador)
        if motivo:
            raise ValueError(motivo)
    nodos = _manejadores_de(_parsear(fuente))
    lineas = fuente.splitlines(keepends=True)
    # De abajo hacia arriba: insertar un envoltorio no corre las líneas de los de arriba.
    elegidos = {nodos[m].id: nodos[m] for m in manejadores}.values()
    for nodo in sorted(elegidos, key=arbol_ts.linea, reverse=True):
        linea_def = arbol_ts.linea(nodo)
        nombre = arbol_ts.nombre(nodo)
        primera = min(arbol_ts.linea(d) for d in arbol_ts.nodos_decorador(nodo))
        for indice in range(primera - 1, linea_def - 1):
            lineas[indice] = "\n"
        lineas[linea_def - 1] = re.sub(
            rf"\bdef\s+{re.escape(nombre)}\b",
            f"def {nombre_aislado(nombre)}",
            lineas[linea_def - 1],
            count=1,
        )
        final = arbol_ts.linea_fin(nodo)
        if not lineas[final - 1].endswith("\n"):
            lineas[final - 1] += "\n"
        lineas.insert(final, _envoltorio(nodo))
    return "".join(lineas)


def _parsear(fuente: str) -> Tree:
    """Árbol del módulo. Lanza ``SyntaxError`` si el código no es válido."""
    arbol = arbol_ts.parsear(fuente)
    arbol_ts.validar(arbol, fuente)
    return arbol


def _manejadores_de(arbol: Tree) -> dict[str, Node]:
    return {
        arbol_ts.nombre(nodo): arbol_ts.definicion(nodo)
        for nodo in arbol_ts.sentencias(arbol.root_node)
        if arbol_ts.es_funcion(nodo)
    }


def _envoltorio(nodo: Node) -> str:
    """El endpoint original: mismos decoradores y firma; delega en la función aislada."""
    lista = arbol_ts.parametros(nodo.child_by_field_name("parameters"))
    # Orden de la firma: posicionales, *args, solo por nombre y **kwargs.
    llamada = []
    for parametro in lista:
        if parametro.clase in (POSICIONAL_SOLO, POSICIONAL):
            llamada.append(parametro.nombre)
        elif parametro.clase == SOLO_NOMBRE:
            llamada.append(f"{parametro.nombre}={parametro.nombre}")
        elif parametro.clase == KWARGS:
            llamada.append(f"**{parametro.nombre}")
        else:
            llamada.append(f"*{parametro.nombre}")
    es_async = arbol_ts.es_async(nodo)
    nombre = arbol_ts.nombre(nodo)
    retorno_nodo = nodo.child_by_field_name("return_type")
    retorno = f" -> {texto_ts.expresion(retorno_nodo)}" if retorno_nodo else ""
    decoradores = "".join(
        f"@{texto_ts.expresion(d)}\n" for d in arbol_ts.decoradores(nodo)
    )
    return (
        f"\n\n{decoradores}"
        f"{'async ' if es_async else ''}def {nombre}({texto_ts.argumentos(lista)})"
        f"{retorno}:\n"
        f"    return {'await ' if es_async else ''}"
        f"{nombre_aislado(nombre)}({', '.join(llamada)})\n"
    )


def _tiene_yield(nodo: Node) -> bool:
    """Si la función tiene ``yield`` propio (no de funciones, clases o lambdas internas)."""
    pendientes = list(arbol_ts.hijos(nodo))
    pendientes.extend(arbol_ts.nodos_decorador(nodo))
    while pendientes:
        actual = pendientes.pop()
        if actual.type == "yield":
            return True
        if actual.type not in arbol_ts.NODOS_DEFINICION and actual.type != "lambda":
            pendientes.extend(arbol_ts.hijos(actual))
    return False

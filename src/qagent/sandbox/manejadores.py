"""Aísla el cuerpo de los manejadores FastAPI para que mutmut pueda mutarlos (#74).

mutmut 3 no muta funciones decoradas: copiar un `@app.post(...)` para su trampolín
registraría la ruta dos veces. Por eso, solo en la copia del proyecto que usa el sandbox,
cada manejador pedido se reescribe así (sin ejecutar nada, solo con `ast`):

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

import ast
import re

#: Prefijo de la función que recibe el cuerpo del manejador en la copia del sandbox.
PREFIJO_AISLADO = "_qagent_manejador_"


def nombre_aislado(manejador: str) -> str:
    """Nombre de la función sin decorador que recibe el cuerpo de `manejador`."""
    return PREFIJO_AISLADO + manejador


def motivo_no_aislable(fuente: str, manejador: str) -> str | None:
    """Explica por qué no se puede aislar `manejador`, o None si se puede."""
    try:
        nodo = _manejadores_de(ast.parse(fuente)).get(manejador)
    except (SyntaxError, ValueError):
        return "El módulo no se pudo analizar."
    if nodo is None:
        return f"No se encontró el manejador {manejador} al nivel del módulo."
    if not nodo.decorator_list:
        return f"{manejador} no tiene el decorador de la ruta."
    if isinstance(nodo, ast.AsyncFunctionDef) and _tiene_yield(nodo):
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
    nodos = _manejadores_de(ast.parse(fuente))
    lineas = fuente.splitlines(keepends=True)
    # De abajo hacia arriba: insertar un envoltorio no corre las líneas de los de arriba.
    for nodo in sorted(
        {nodos[m] for m in manejadores}, key=lambda n: n.lineno, reverse=True
    ):
        primera = min(d.lineno for d in nodo.decorator_list)
        for indice in range(primera - 1, nodo.lineno - 1):
            lineas[indice] = "\n"
        lineas[nodo.lineno - 1] = re.sub(
            rf"\bdef\s+{re.escape(nodo.name)}\b",
            f"def {nombre_aislado(nodo.name)}",
            lineas[nodo.lineno - 1],
            count=1,
        )
        final = nodo.end_lineno or nodo.lineno
        if not lineas[final - 1].endswith("\n"):
            lineas[final - 1] += "\n"
        lineas.insert(final, _envoltorio(nodo))
    return "".join(lineas)


def _manejadores_de(
    arbol: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        nodo.name: nodo
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _envoltorio(nodo: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """El endpoint original: mismos decoradores y firma; delega en la función aislada."""
    argumentos = nodo.args
    llamada = [a.arg for a in [*argumentos.posonlyargs, *argumentos.args]]
    if argumentos.vararg:
        llamada.append(f"*{argumentos.vararg.arg}")
    llamada += [f"{a.arg}={a.arg}" for a in argumentos.kwonlyargs]
    if argumentos.kwarg:
        llamada.append(f"**{argumentos.kwarg.arg}")
    es_async = isinstance(nodo, ast.AsyncFunctionDef)
    retorno = f" -> {ast.unparse(nodo.returns)}" if nodo.returns else ""
    decoradores = "".join(f"@{ast.unparse(d)}\n" for d in nodo.decorator_list)
    return (
        f"\n\n{decoradores}"
        f"{'async ' if es_async else ''}def {nodo.name}({ast.unparse(argumentos)})"
        f"{retorno}:\n"
        f"    return {'await ' if es_async else ''}"
        f"{nombre_aislado(nodo.name)}({', '.join(llamada)})\n"
    )


def _tiene_yield(nodo: ast.AST) -> bool:
    pendientes = list(ast.iter_child_nodes(nodo))
    while pendientes:
        actual = pendientes.pop()
        if isinstance(actual, (ast.Yield, ast.YieldFrom)):
            return True
        if not isinstance(
            actual, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            pendientes.extend(ast.iter_child_nodes(actual))
    return False

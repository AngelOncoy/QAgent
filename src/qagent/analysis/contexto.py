"""Contexto estático de una función para el Generator (solo `ast`, nunca se importa).

El Generator recibe el contrato del Planner, pero sin ver el módulo no sabe qué
importar ni qué simular: por ejemplo, que `decode_token` usa `Config.JWT_SECRET_KEY`
y `pyjwt`, o que PyJWT no está instalado en el sandbox. Este módulo junta, leyendo el
archivo con `ast`, lo mínimo para escribir un test que se pueda ejecutar:

- los `import` del módulo;
- los nombres globales del módulo que usa la función (a simular con `mock.patch`);
- el código de la función;
- los paquetes del `requirements.txt` del proyecto (los que tendrá el sandbox).

El valor esperado de cada caso **no** sale de aquí: sigue saliendo del contrato
(firma, tipos y docstring), y el Reviewer rechaza cualquier aserción que se aparte.
"""

from __future__ import annotations

import ast
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

#: Topes para no inflar el prompt (tokens) con módulos o funciones enormes.
MAX_IMPORTS = 40
MAX_CARACTERES_CODIGO = 6000
MAX_PAQUETES = 40
#: Lo que siempre trae la imagen base del sandbox (src/qagent/sandbox/Dockerfile).
PAQUETES_BASE = ("pytest", "pytest-cov", "coverage", "mutmut", "httpx")


@dataclass(frozen=True)
class ContextoFuncion:
    """Lo que el Generator necesita saber del módulo para escribir el test.

    Atributos:
        imports: sentencias `import` / `from ... import` del módulo, en orden.
        globales_usados: nombres definidos o importados en el módulo que la función
            usa (candidatos a simular).
        codigo: código fuente de la función (recortado si es muy largo).
        paquetes: paquetes que instala el sandbox según `requirements.txt`; vacío si
            el proyecto no tiene ese archivo.
    """

    imports: list[str] = field(default_factory=list)
    globales_usados: list[str] = field(default_factory=list)
    codigo: str = ""
    paquetes: list[str] = field(default_factory=list)


def contexto_de_funcion(
    raiz: str | Path, modulo: str, nombre: str
) -> ContextoFuncion | None:
    """Contexto de la función `nombre` del archivo `modulo` (relativo a `raiz`).

    Returns:
        El contexto, o None si el archivo no se puede leer, no es Python válido o la
        función no está en el nivel superior del módulo. Nunca lanza excepciones:
        sin contexto, el Generator trabaja solo con el contrato, como antes.
    """
    ruta = Path(raiz) / modulo
    try:
        with tokenize.open(ruta) as archivo:  # respeta BOM y cookie de codificación
            fuente = archivo.read()
        arbol = ast.parse(fuente, filename=modulo)
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
        return None
    funcion = next(
        (
            nodo
            for nodo in arbol.body
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
            and nodo.name == nombre
        ),
        None,
    )
    if funcion is None:
        return None
    codigo = ast.get_source_segment(fuente, funcion) or ast.unparse(funcion)
    if len(codigo) > MAX_CARACTERES_CODIGO:
        codigo = codigo[:MAX_CARACTERES_CODIGO] + "\n# […recortado…]"
    return ContextoFuncion(
        imports=_imports(arbol)[:MAX_IMPORTS],
        globales_usados=_globales_usados(arbol, funcion),
        codigo=codigo,
        paquetes=paquetes_del_sandbox(raiz),
    )


def paquetes_del_sandbox(raiz: str | Path) -> list[str]:
    """Paquetes del `requirements.txt` de la raíz (sin comentarios ni opciones de pip)."""
    try:
        lineas = (Path(raiz) / "requirements.txt").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    paquetes: list[str] = []
    for linea in lineas.splitlines():
        texto = linea.split("#", 1)[0].strip()
        if texto and not texto.startswith("-"):
            paquetes.append(texto)
    return paquetes[:MAX_PAQUETES]


def _imports(arbol: ast.Module) -> list[str]:
    return [
        ast.unparse(nodo)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.Import, ast.ImportFrom))
        and _es_de_nivel_modulo(arbol, nodo)
    ]


def _es_de_nivel_modulo(arbol: ast.Module, nodo: ast.AST) -> bool:
    """Import del módulo: en el cuerpo o dentro de un `try`/`if` de primer nivel."""
    for sentencia in arbol.body:
        if sentencia is nodo:
            return True
        if isinstance(sentencia, (ast.Try, ast.If)) and any(
            hijo is nodo for hijo in ast.walk(sentencia)
        ):
            return True
    return False


def _nombres_del_modulo(arbol: ast.Module) -> set[str]:
    """Nombres que el módulo define o importa en su nivel superior."""
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if not _es_de_nivel_modulo(arbol, nodo):
            continue
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            for alias in nodo.names:
                nombres.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres.add(nodo.name)
        elif isinstance(nodo, (ast.Assign, ast.AnnAssign)):
            objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
            for objetivo in objetivos:
                nombres.update(
                    n.id for n in ast.walk(objetivo) if isinstance(n, ast.Name)
                )
    return nombres


def _globales_usados(
    arbol: ast.Module, funcion: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[str]:
    del_modulo = _nombres_del_modulo(arbol) - {funcion.name}
    usados = {
        nodo.id
        for nodo in ast.walk(funcion)
        if isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Load)
    }
    return sorted(usados & del_modulo)

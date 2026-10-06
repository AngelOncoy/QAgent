"""Analizador estático (AST) del proyecto — EN-02.

Extrae la estructura del código Python de un proyecto **sin ejecutarlo**:
solo usa ``ast.parse`` (nunca ``import``, ``exec`` ni ``eval``), de acuerdo con
la regla de AGENTS.md. Alimenta al Planner y a las historias HU-04, HU-06,
HU-16 y HU-24.

Qué analiza:
    * Módulos ``.py`` del proyecto, con rutas relativas en formato POSIX.
    * Funciones públicas definidas a nivel de módulo (``def`` y ``async def``).
      Las funciones privadas (prefijo ``_``) se ignoran. Los métodos de clases
      y las funciones anidadas quedan fuera de este alcance.

Qué ignora:
    * Carpetas ``tests/``, ``.pyagent/`` y cualquier carpeta que empiece con
      punto (``.git``, ``.venv``, ``.idea``...), además de ``__pycache__``,
      ``venv``, ``node_modules``, ``site-packages``, ``mutants`` y ``*.egg-info``.

Definiciones:
    * **Ramas** de una función: cantidad de puntos de decisión propios
      (``if``/``elif``, expresión ternaria, ``for``, ``while``, cada ``except``,
      cada ``case`` de ``match`` y cada condición ``if`` de una comprensión).
      No se cuentan las ramas de funciones o clases anidadas.
    * **Tipada**: todos los parámetros y el retorno tienen anotación.
    * **Huella** (SHA-256) de un módulo: hash del texto fuente completo (código
      y docstrings) con saltos de línea normalizados a ``\\n``. Si cambia el
      código o su documentación, cambia la huella (HU-24).

Los archivos que no se pueden analizar (error de sintaxis, codificación
inválida, etc.) se reportan en ``errores`` y **no detienen** el análisis.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
import tokenize
from pathlib import Path
from typing import Any

DIRECTORIOS_IGNORADOS = frozenset(
    {"tests", "__pycache__", "venv", "node_modules", "site-packages", "mutants"}
)

_NODOS_RAMA = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.match_case,
)
_NODOS_ANIDADOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_ERRORES_LECTURA = (SyntaxError, ValueError, RecursionError, OSError)


def _es_ignorado(nombre_directorio: str) -> bool:
    """Indica si una carpeta debe omitirse del análisis."""
    return (
        nombre_directorio.startswith(".")
        or nombre_directorio in DIRECTORIOS_IGNORADOS
        or nombre_directorio.endswith(".egg-info")
    )


def listar_archivos_py(raiz: Path) -> list[Path]:
    """Lista los ``.py`` del proyecto, ordenados por ruta relativa.

    Es el único criterio de qué archivos se analizan: poda las carpetas
    ignoradas y no entra en carpetas que son enlaces simbólicos. Lo reutiliza
    la HU-01 para validar una carpeta antes de abrirla.
    """
    encontrados: list[Path] = []
    for directorio, subdirectorios, archivos in os.walk(raiz):
        subdirectorios[:] = [d for d in subdirectorios if not _es_ignorado(d)]
        encontrados.extend(Path(directorio) / a for a in archivos if a.endswith(".py"))
    return sorted(encontrados, key=lambda p: p.relative_to(raiz).as_posix())


def contar_ramas(funcion: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Cuenta los puntos de decisión propios de una función.

    No desciende a funciones ni clases anidadas: sus ramas no son de ``funcion``.
    """
    total = 0
    pendientes: list[ast.AST] = list(funcion.body)
    while pendientes:
        nodo = pendientes.pop()
        if isinstance(nodo, _NODOS_ANIDADOS):
            continue
        if isinstance(nodo, _NODOS_RAMA):
            total += 1
        elif isinstance(nodo, ast.comprehension):
            total += len(nodo.ifs)
        pendientes.extend(ast.iter_child_nodes(nodo))
    return total


def _texto(nodo: ast.AST | None) -> str | None:
    """Devuelve el código fuente de un nodo, o ``None`` si no existe."""
    return None if nodo is None else ast.unparse(nodo)


def _parametro(
    nombre: str, anotacion: ast.expr | None, por_defecto: ast.expr | None
) -> dict[str, Any]:
    return {
        "nombre": nombre,
        "tipo": _texto(anotacion),
        "por_defecto": _texto(por_defecto),
    }


def _extraer_parametros(argumentos: ast.arguments) -> list[dict[str, Any]]:
    """Extrae nombre, tipo y valor por defecto de cada parámetro, en orden."""
    posicionales = [*argumentos.posonlyargs, *argumentos.args]
    faltantes = len(posicionales) - len(argumentos.defaults)
    defaults: list[ast.expr | None] = [None] * faltantes + list(argumentos.defaults)

    parametros = [
        _parametro(a.arg, a.annotation, d) for a, d in zip(posicionales, defaults)
    ]
    if argumentos.vararg:
        va = argumentos.vararg
        parametros.append(_parametro("*" + va.arg, va.annotation, None))
    parametros.extend(
        _parametro(a.arg, a.annotation, d)
        for a, d in zip(argumentos.kwonlyargs, argumentos.kw_defaults)
    )
    if argumentos.kwarg:
        kw = argumentos.kwarg
        parametros.append(_parametro("**" + kw.arg, kw.annotation, None))
    return parametros


def _extraer_funcion(
    nodo: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, Any]:
    """Convierte una función del AST en su descripción JSON."""
    parametros = _extraer_parametros(nodo.args)
    retorno = _texto(nodo.returns)
    firma = f"({ast.unparse(nodo.args)})"
    if retorno is not None:
        firma += f" -> {retorno}"
    docstring = (ast.get_docstring(nodo) or "").strip() or None
    return {
        "nombre": nodo.name,
        "linea": nodo.lineno,
        "firma": firma,
        "parametros": parametros,
        "retorno": retorno,
        "docstring": docstring,
        "ramas": contar_ramas(nodo),
        "tipada": retorno is not None and all(p["tipo"] for p in parametros),
        "es_async": isinstance(nodo, ast.AsyncFunctionDef),
    }


def _funciones_publicas(arbol: ast.Module) -> list[dict[str, Any]]:
    return [
        _extraer_funcion(nodo)
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not nodo.name.startswith("_")
    ]


def calcular_huella(fuente: str) -> str:
    """SHA-256 (hex) del texto fuente de un módulo, con saltos de línea ``\\n``."""
    normalizado = fuente.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


def _analizar_modulo(ruta: Path, relativa: str) -> dict[str, Any]:
    """Analiza un archivo. Lanza las excepciones de lectura o de sintaxis."""
    with tokenize.open(ruta) as archivo:  # respeta BOM y cookie de codificación
        fuente = archivo.read()
    arbol = ast.parse(fuente, filename=relativa)
    return {
        "ruta": relativa,
        "huella": calcular_huella(fuente),
        "funciones": _funciones_publicas(arbol),
    }


def _error(relativa: str, causa: Exception) -> dict[str, Any]:
    """Describe por qué un archivo no se pudo analizar."""
    es_sintaxis = isinstance(causa, SyntaxError)
    return {
        "ruta": relativa,
        "tipo": type(causa).__name__,
        "linea": causa.lineno if es_sintaxis else None,
        "mensaje": causa.msg if es_sintaxis else str(causa),
    }


def _conteo(cantidad: int, total: int) -> dict[str, Any]:
    porcentaje = round(cantidad / total * 100, 1) if total else 0.0
    return {"cantidad": cantidad, "porcentaje": porcentaje}


def _resumen(
    modulos: list[dict[str, Any]], errores: list[dict[str, Any]]
) -> dict[str, Any]:
    funciones = [f for m in modulos for f in m["funciones"]]
    total = len(funciones)
    sin_docstring = sum(1 for f in funciones if f["docstring"] is None)
    sin_tipos = sum(1 for f in funciones if not f["tipada"])
    con_alguna = sum(1 for f in funciones if f["docstring"] is None or not f["tipada"])
    return {
        "total_modulos": len(modulos),
        "total_funciones_publicas": total,
        "total_errores": len(errores),
        "inconsistencias": {
            "sin_docstring": _conteo(sin_docstring, total),
            "sin_tipos": _conteo(sin_tipos, total),
            "con_alguna": _conteo(con_alguna, total),
        },
    }


def analizar_proyecto(raiz: str | os.PathLike[str]) -> dict[str, Any]:
    """Analiza estáticamente todos los módulos Python bajo ``raiz``.

    Devuelve un diccionario serializable a JSON con tres claves:

    * ``modulos``: por módulo, ``ruta``, ``huella`` y ``funciones`` públicas
      (``nombre``, ``linea``, ``firma``, ``parametros``, ``retorno``,
      ``docstring``, ``ramas``, ``tipada``, ``es_async``).
    * ``errores``: archivos no analizables (``ruta``, ``tipo``, ``linea``,
      ``mensaje``). No detienen el análisis del resto.
    * ``resumen``: totales de módulos, funciones públicas y errores, más las
      inconsistencias (sin docstring, sin tipos, con alguna de las dos) con su
      porcentaje sobre el total de funciones públicas.

    Raises:
        NotADirectoryError: si ``raiz`` no es una carpeta existente.
    """
    carpeta = Path(raiz)
    if not carpeta.is_dir():
        raise NotADirectoryError(f"No es una carpeta: {carpeta}")

    modulos: list[dict[str, Any]] = []
    errores: list[dict[str, Any]] = []
    for ruta in listar_archivos_py(carpeta):
        relativa = ruta.relative_to(carpeta).as_posix()
        try:
            modulos.append(_analizar_modulo(ruta, relativa))
        except _ERRORES_LECTURA as causa:
            errores.append(_error(relativa, causa))

    return {
        "modulos": modulos,
        "errores": errores,
        "resumen": _resumen(modulos, errores),
    }


def analizar_proyecto_json(raiz: str | os.PathLike[str], indent: int | None = 2) -> str:
    """Igual que :func:`analizar_proyecto`, pero devuelve el JSON como texto."""
    return json.dumps(analizar_proyecto(raiz), ensure_ascii=False, indent=indent)


def main(argumentos: list[str] | None = None) -> int:
    """Punto de entrada de línea de comandos: imprime el JSON del análisis."""
    argumentos = sys.argv[1:] if argumentos is None else argumentos
    if len(argumentos) != 1:
        print("Uso: python -m pyagent.analysis <carpeta-del-proyecto>", file=sys.stderr)
        return 2
    try:
        texto = analizar_proyecto_json(argumentos[0])
    except NotADirectoryError as error:
        print(error, file=sys.stderr)
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # consolas de Windows (cp1252)
    print(texto)
    return 0

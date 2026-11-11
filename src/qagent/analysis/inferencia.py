"""Contexto estático para inferir el contrato de una función sin docstring (#275, ADR-015).

Cuando una función no tiene docstring ni tipos que determinen su resultado, el Planner
la omitiría. Con la inferencia activa, el Planner recibe de este módulo lo que se puede
saber **leyendo** el proyecto, sin importarlo ni ejecutarlo (tree-sitter, 0 tokens):

- el **cuerpo** de la función;
- las **dependencias** hacia abajo (firma y docstring de lo que usa, ADR-012);
- los **llamadores** hacia arriba: quién la llama y con qué argumentos (índice inverso
  de ``llama_a``);
- los **tests existentes** del repositorio que la mencionan.

Cada fuente tiene una referencia (``cuerpo``, ``dependencia:<símbolo>``,
``llamador:<ruta>::<función>``, ``test_existente:<ruta>::<test>``). Un caso inferido tiene
que citar al menos una de ellas, y solo valen las que este módulo entregó
(:meth:`ContextoInferencia.referencias`): así la inferencia siempre es trazable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qagent.analysis import arbol_ts
from qagent.analysis.arbol_ts import texto
from qagent.analysis.contexto import contexto_de_funcion
from qagent.analysis.grafo_imports import construir_grafo_dependencias

#: Topes para no inflar el prompt (tokens).
MAX_LLAMADORES = 3
MAX_TESTS = 3
MAX_DEPENDENCIAS = 8
MAX_ARCHIVOS_DE_PRUEBA = 300
MAX_BYTES_ARCHIVO = 200_000
MAX_CARACTERES_TEST = 1200
MAX_LINEAS_LLAMADA = 3

REF_CUERPO = "cuerpo"
PREFIJOS_EVIDENCIA = ("dependencia:", "llamador:", "test_existente:")

_DIRECTORIOS_SIN_TESTS = frozenset(
    {"__pycache__", "venv", "env", "node_modules", "site-packages", "build", "dist"}
)


@dataclass(frozen=True)
class ContextoInferencia:
    """Lo que se sabe, sin ejecutar nada, de una función sin contrato documentado."""

    modulo: str
    nombre: str
    codigo: str
    #: Líneas ``símbolo(firma): docstring`` de las dependencias directas.
    dependencias: tuple[str, ...] = ()
    #: ``(ruta::función, fragmento de la llamada)`` de quien la usa.
    llamadores: tuple[tuple[str, str], ...] = ()
    #: ``(ruta::test, código del test)`` de los tests existentes que la mencionan.
    tests: tuple[tuple[str, str], ...] = ()
    #: Nombres de las dependencias, para la referencia ``dependencia:<símbolo>``.
    simbolos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def referencias(self) -> frozenset[str]:
        """Las únicas referencias que un caso inferido puede citar como evidencia."""
        refs = {REF_CUERPO}
        refs.update(f"dependencia:{s}" for s in self.simbolos)
        refs.update(f"llamador:{ref}" for ref, _ in self.llamadores)
        refs.update(f"test_existente:{ref}" for ref, _ in self.tests)
        return frozenset(refs)

    def a_dict(self) -> dict[str, Any]:
        """Forma serializable que viaja en el prompt del Planner."""
        return {
            "nombre": self.nombre,
            "codigo": self.codigo,
            "dependencias": list(self.dependencias),
            "llamadores": [{"ref": r, "fragmento": f} for r, f in self.llamadores],
            "tests_existentes": [{"ref": r, "codigo": c} for r, c in self.tests],
            "referencias": sorted(self.referencias),
        }


def motivo_evidencia(evidencia: Any, permitidas: frozenset[str]) -> str | None:
    """Por qué la evidencia de un caso inferido no vale; None si respalda el caso."""
    if not isinstance(evidencia, list) or not evidencia:
        return "un caso inferido necesita al menos una fuente de evidencia"
    desconocidas = [
        e for e in evidencia if not isinstance(e, str) or e not in permitidas
    ]
    if desconocidas:
        return "la evidencia cita fuentes que no se entregaron: " + ", ".join(
            repr(e) for e in desconocidas[:3]
        )
    return None


# --------------------------------------------------------------------------- #
# Índice de llamadores
# --------------------------------------------------------------------------- #
def indice_llamadores(modulos: list[dict[str, Any]]) -> dict[str, list[str]]:
    """``ruta::función`` → quién la llama, invirtiendo ``llama_a`` de todo el proyecto."""
    indice: dict[str, list[str]] = {}
    for modulo in modulos:
        for funcion in modulo.get("funciones", []):
            origen = f"{modulo['ruta']}::{funcion['nombre']}"
            for destino in funcion.get("llama_a") or []:
                if origen not in indice.setdefault(destino, []):
                    indice[destino].append(origen)
    return indice


# --------------------------------------------------------------------------- #
# Tests existentes
# --------------------------------------------------------------------------- #
def _archivos_de_prueba(raiz: Path) -> list[Path]:
    """``test_*.py`` y ``*_test.py`` del proyecto (las carpetas ocultas se saltan)."""
    encontrados: list[Path] = []
    for carpeta, subcarpetas, archivos in os.walk(raiz, followlinks=False):
        subcarpetas[:] = sorted(
            d
            for d in subcarpetas
            if not d.startswith(".")
            and d not in _DIRECTORIOS_SIN_TESTS
            and not d.endswith(".egg-info")
        )
        for archivo in sorted(archivos):
            if archivo.endswith(".py") and (
                archivo.startswith("test_") or archivo.endswith("_test.py")
            ):
                encontrados.append(Path(carpeta) / archivo)
        if len(encontrados) >= MAX_ARCHIVOS_DE_PRUEBA:
            break
    return encontrados[:MAX_ARCHIVOS_DE_PRUEBA]


def indice_de_tests(raiz: str | Path) -> dict[str, list[tuple[str, str]]]:
    """Nombre mencionado → ``(ruta::test, código)`` de los tests que lo usan."""
    base = Path(raiz)
    indice: dict[str, list[tuple[str, str]]] = {}
    for archivo in _archivos_de_prueba(base):
        try:
            if archivo.stat().st_size > MAX_BYTES_ARCHIVO:
                continue
            fuente = archivo.read_text(encoding="utf-8")
            arbol = arbol_ts.parsear(fuente)
            arbol_ts.validar(arbol, fuente, archivo.name)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
            continue
        relativa = archivo.relative_to(base).as_posix()
        for nodo in arbol_ts.recorrer(arbol.root_node):
            if nodo.type != "function_definition":
                continue
            nombre_test = arbol_ts.nombre(nodo)
            if not nombre_test.startswith("test"):
                continue
            codigo = texto(nodo)[:MAX_CARACTERES_TEST]
            referencia = (f"{relativa}::{nombre_test}", codigo)
            mencionados = {
                texto(n) for n in arbol_ts.recorrer(nodo) if n.type == "identifier"
            }
            for mencionado in mencionados:
                indice.setdefault(mencionado, []).append(referencia)
    return indice


# --------------------------------------------------------------------------- #
# Proveedor
# --------------------------------------------------------------------------- #
class ProveedorInferencia:
    """Arma el :class:`ContextoInferencia` de cada función, con índices perezosos."""

    def __init__(
        self,
        raiz: str | Path,
        modulos: list[dict[str, Any]],
        max_caracteres: int = 6000,
    ) -> None:
        self.raiz = Path(raiz)
        self.modulos = modulos
        self.max_caracteres = max_caracteres
        self._llamadores: dict[str, list[str]] | None = None
        self._tests: dict[str, list[tuple[str, str]]] | None = None

    def contexto(self, modulo: str, nombre: str) -> ContextoInferencia | None:
        """Contexto de ``nombre`` en ``modulo``; None si no se puede leer el código."""
        base = contexto_de_funcion(self.raiz, modulo, nombre)
        if base is None or not base.codigo.strip():
            return None
        tope = self.max_caracteres
        dependencias, simbolos = self._dependencias(modulo, nombre, tope // 4)
        return ContextoInferencia(
            modulo=modulo,
            nombre=nombre,
            codigo=base.codigo[:tope],
            dependencias=dependencias,
            llamadores=self._llamadores_de(modulo, nombre, tope // 4),
            tests=self._tests_de(nombre, tope // 3),
            simbolos=simbolos,
        )

    def _dependencias(
        self, modulo: str, nombre: str, tope: int
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        try:
            grafo = construir_grafo_dependencias(self.raiz, modulo, nombre)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return (), ()
        lineas: list[str] = []
        simbolos: list[str] = []
        usado = 0
        for simbolo in grafo.simbolos_directos[:MAX_DEPENDENCIAS]:
            resumen = (simbolo.docstring or "").strip().splitlines()
            linea = f"{simbolo.nombre}{simbolo.firma}" + (
                f": {resumen[0]}" if resumen else ""
            )
            if usado + len(linea) > tope:
                break
            usado += len(linea)
            lineas.append(linea)
            simbolos.append(simbolo.nombre)
        return tuple(lineas), tuple(simbolos)

    def _llamadores_de(
        self, modulo: str, nombre: str, tope: int
    ) -> tuple[tuple[str, str], ...]:
        if self._llamadores is None:
            self._llamadores = indice_llamadores(self.modulos)
        resultado: list[tuple[str, str]] = []
        usado = 0
        for referencia in self._llamadores.get(f"{modulo}::{nombre}", [])[
            :MAX_LLAMADORES
        ]:
            fragmento = self._fragmento_de_llamada(referencia, nombre)
            if not fragmento or usado + len(fragmento) > tope:
                continue
            usado += len(fragmento)
            resultado.append((referencia, fragmento))
        return tuple(resultado)

    def _fragmento_de_llamada(self, referencia: str, nombre: str) -> str:
        """Cabecera del llamador y las líneas donde llama a ``nombre``."""
        ruta, _, funcion = referencia.partition("::")
        contexto = contexto_de_funcion(self.raiz, ruta, funcion)
        if contexto is None:
            return ""
        lineas = contexto.codigo.splitlines()
        llamadas = [linea.strip() for linea in lineas[1:] if f"{nombre}(" in linea][
            :MAX_LINEAS_LLAMADA
        ]
        if not llamadas:
            return ""
        return "\n".join([lineas[0].strip(), *llamadas])

    def _tests_de(self, nombre: str, tope: int) -> tuple[tuple[str, str], ...]:
        if self._tests is None:
            self._tests = indice_de_tests(self.raiz)
        resultado: list[tuple[str, str]] = []
        usado = 0
        for referencia, codigo in self._tests.get(nombre, [])[:MAX_TESTS]:
            if usado + len(codigo) > tope:
                continue
            usado += len(codigo)
            resultado.append((referencia, codigo))
        return tuple(resultado)

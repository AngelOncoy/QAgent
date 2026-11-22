"""AST y declaraciones Java reutilizables solo durante una corrida (#308)."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tree_sitter import Node, Tree

from qagent.lenguajes.treesitter import obtener_parser
from qagent.recursos import RegistroRecursos, medir, sesion_recursos

MAX_ENTRADAS = 32
MAX_BYTES = 4_000_000
_ACTUAL: ContextVar[_CacheJava | None] = ContextVar("qagent_java_cache", default=None)


@dataclass(frozen=True)
class ArbolLectura:
    """Mantiene vivo el árbol original y expone solo su raíz de lectura.

    No usa Tree.copy(): su combinación con Node.text produjo un fallo nativo
    en Windows/tree-sitter 0.24 durante la validación. Se retiene el original;
    ningún consumidor edita árboles compartidos.
    """

    _arbol: Tree

    @property
    def root_node(self) -> Node:
        """Raíz nueva de la misma fuente inmutable, conservando su propietario."""
        return self._arbol.root_node


def _calcular(datos: bytes) -> tuple[ArbolLectura, list[dict], list[dict]]:
    from qagent.lenguajes.java import _declaraciones

    with medir("java_parseos"):
        arbol = obtener_parser("java").parse(datos)
    if arbol.root_node.has_error:
        return ArbolLectura(arbol), [], []
    with medir("java_declaraciones"):
        clases, funciones = _declaraciones(arbol.root_node)
    return ArbolLectura(arbol), clases, funciones


class _CacheJava:
    def __init__(self, registro: RegistroRecursos) -> None:
        self.registro = registro
        self.lock = threading.RLock()
        self.entradas: OrderedDict[str, tuple[Any, int]] = OrderedDict()
        self.bytes = 0
        self.pico = 0
        self.cerrado = False

    def analizar(self, datos: bytes) -> tuple[ArbolLectura, list[dict], list[dict]]:
        # Lock por sesión: una misma fuente no se calcula dos veces concurrentemente.
        with self.lock:
            clave = hashlib.sha256(datos).hexdigest()
            if not self.cerrado and clave in self.entradas:
                valor, _ = self.entradas[clave]
                self.entradas.move_to_end(clave)
                self.registro.registrar("java_cache_aciertos")
            else:
                valor = _calcular(datos)
                peso = len(datos) + len(
                    json.dumps(valor[1:], ensure_ascii=False).encode("utf-8")
                )
                if not self.cerrado and peso <= MAX_BYTES:
                    while self.entradas and (
                        len(self.entradas) >= MAX_ENTRADAS
                        or self.bytes + peso > MAX_BYTES
                    ):
                        _, (_, anterior) = self.entradas.popitem(last=False)
                        self.bytes -= anterior
                        self.registro.registrar("java_cache_expulsiones")
                    self.entradas[clave] = (valor, peso)
                    self.bytes += peso
                    self.pico = max(self.pico, self.bytes)
                elif not self.cerrado:
                    self.registro.registrar("java_cache_fuentes_no_retenidas")
            # Las declaraciones sí se modifican (llama_a); el AST solo se lee.
            return valor[0], copy.deepcopy(valor[1]), copy.deepcopy(valor[2])

    def cerrar(self) -> None:
        with self.lock:
            self.cerrado = True
            self.entradas.clear()
            self.bytes = 0
            self.registro.fijar(
                "cache_java",
                {
                    "limite_entradas": MAX_ENTRADAS,
                    "limite_payload_bytes": MAX_BYTES,
                    "pico_payload_bytes": self.pico,
                    "entradas_al_cierre": 0,
                    "payload_al_cierre_bytes": 0,
                    "incluye_memoria_nativa_ast": False,
                },
            )


def analizar_fuente(fuente: str) -> tuple[ArbolLectura, list[dict], list[dict]]:
    """Reutiliza por contenido actual; jamás almacena contratos ni veredictos."""
    datos = (
        fuente.removeprefix("\ufeff")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .encode("utf-8")
    )
    cache = _ACTUAL.get()
    return cache.analizar(datos) if cache is not None else _calcular(datos)


@contextmanager
def sesion_java(
    raiz: Path, cancelado: Callable[[], bool] | None = None
) -> Iterator[RegistroRecursos]:
    """Caché efímera y acotada; no cambia selección, inferencia ni caché persistente."""
    with sesion_recursos(cancelado) as registro:
        cache = _CacheJava(registro)
        token = _ACTUAL.set(cache)
        try:
            yield registro
        finally:
            cache.cerrar()
            _ACTUAL.reset(token)

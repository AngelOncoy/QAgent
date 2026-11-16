"""Contexto Java estático y acotado para regresión inferida (#292, ADR-018)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tree_sitter import Node

from qagent.analysis.inferencia import ContextoInferencia, indice_llamadores
from qagent.lenguajes.treesitter import obtener_parser

MAX_ARCHIVOS = 300
MAX_BYTES_ARCHIVO = 200_000
MAX_BYTES_TOTAL = 4_000_000
MAX_FUENTES = 3
_CLASES = {
    "class_declaration",
    "interface_declaration",
    "record_declaration",
    "enum_declaration",
}
_IGNORADOS = {"target", "build", "dist", "node_modules", "venv", "env", "__pycache__"}
_NO_DETERMINISTAS = {
    "System.currentTimeMillis",
    "System.nanoTime",
    "System.getenv",
    "System.getProperty",
    "Math.random",
    "Instant.now",
    "LocalDate.now",
    "LocalDateTime.now",
    "OffsetDateTime.now",
    "ZonedDateTime.now",
    "UUID.randomUUID",
}


def _texto(nodo: Node | None) -> str:
    return nodo.text.decode("utf-8") if nodo else ""


def _recorrer(nodo: Node):
    yield nodo
    for hijo in nodo.named_children:
        yield from _recorrer(hijo)


def _metodos(raiz: Node, prefijo: str = "") -> dict[str, Node]:
    """Identifica métodos por clase, sin entrar en cuerpos ni elegir sobrecargas."""
    resultado: dict[str, Node] = {}
    repetidos: set[str] = set()
    for clase in raiz.named_children:
        if clase.type not in _CLASES:
            continue
        nombre = prefijo + _texto(clase.child_by_field_name("name"))
        cuerpo = clase.child_by_field_name("body")
        if cuerpo is None:
            continue
        resultado.update(_metodos(cuerpo, nombre + "."))
        for metodo in cuerpo.named_children:
            if metodo.type != "method_declaration":
                continue
            clave = nombre + "." + _texto(metodo.child_by_field_name("name"))
            if clave in resultado:
                repetidos.add(clave)
            resultado[clave] = metodo
    return {n: m for n, m in resultado.items() if n not in repetidos}


class ProveedorInferenciaJava:
    """Lee fuentes y pruebas con índices perezosos, sin compilar ni ejecutar Java."""

    def __init__(
        self,
        raiz: str | os.PathLike[str],
        modulos: list[dict[str, Any]],
        max_caracteres: int = 6000,
    ) -> None:
        self.raiz = Path(raiz).resolve()
        self.max_caracteres = max(0, max_caracteres)
        self.funciones = {
            (m["ruta"], f["nombre"]): f for m in modulos for f in m.get("funciones", [])
        }
        self.llamadores = indice_llamadores(modulos)
        self._archivos: dict[str, Node | None] = {}
        self._bytes = 0
        self._tests: list[tuple[str, Node]] | None = None

    def _leer(self, relativa: str) -> Node | None:
        if relativa in self._archivos:
            return self._archivos[relativa]
        if len(self._archivos) >= MAX_ARCHIVOS or self._bytes >= MAX_BYTES_TOTAL:
            return None
        self._archivos[relativa] = None
        try:
            ruta = self.raiz / relativa
            if ruta.suffix != ".java" or not ruta.resolve().is_relative_to(self.raiz):
                return None
            if any(p.is_symlink() for p in (ruta, *ruta.parents) if p != self.raiz):
                return None
            disponible = min(MAX_BYTES_ARCHIVO, MAX_BYTES_TOTAL - self._bytes)
            with ruta.open("rb") as archivo:
                contenido = archivo.read(disponible + 1)
            self._bytes += len(contenido)
            if len(contenido) > disponible:
                return None
            fuente = (
                contenido.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            )
            raiz = obtener_parser("java").parse(fuente.encode("utf-8")).root_node
            if raiz.has_error:
                return None
            self._archivos[relativa] = raiz
            return raiz
        except (OSError, ValueError, UnicodeError, RecursionError):
            return None

    def _metodo(self, modulo: str, nombre: str) -> Node | None:
        raiz = self._leer(modulo)
        return _metodos(raiz).get(nombre) if raiz is not None else None

    def contexto(self, modulo: str, nombre: str) -> ContextoInferencia | None:
        """Entrega evidencia de un objetivo analizado; omite cuerpos ausentes o excesivos."""
        try:
            return self._contexto(modulo, nombre)
        except (OSError, ValueError, RecursionError):
            return None

    def _contexto(self, modulo: str, nombre: str) -> ContextoInferencia | None:
        funcion = self.funciones.get((modulo, nombre))
        if not funcion or funcion.get("docstring"):
            return None
        metodo = self._metodo(modulo, nombre)
        if metodo is None or metodo.child_by_field_name("body") is None:
            return None
        codigo = _texto(metodo)
        if len(codigo) > self.max_caracteres:
            return None
        raiz = self._leer(modulo)
        imports_estaticos = {
            _texto(n).removeprefix("import static ").removesuffix(";").strip()
            for n in raiz.named_children
            if n.type == "import_declaration" and _texto(n).startswith("import static ")
        }
        for nodo in _recorrer(metodo):
            if nodo.type == "method_invocation":
                objeto = _texto(nodo.child_by_field_name("object"))
                nombre_llamada = _texto(nodo.child_by_field_name("name"))
                llamada = objeto + "." + nombre_llamada
                importada_no_determinista = not objeto and any(
                    (
                        i.endswith("." + c)
                        or (
                            i.endswith(".*")
                            and i[:-1].endswith(c.rsplit(".", 1)[0] + ".")
                        )
                    )
                    and nombre_llamada == c.rsplit(".", 1)[1]
                    for i in imports_estaticos
                    for c in _NO_DETERMINISTAS
                )
                if (
                    llamada in _NO_DETERMINISTAS
                    or any(llamada.endswith("." + c) for c in _NO_DETERMINISTAS)
                    or importada_no_determinista
                ):
                    return None
            if nodo.type == "object_creation_expression" and _texto(
                nodo.child_by_field_name("type")
            ).rsplit(".", 1)[-1] in {
                "Random",
                "SecureRandom",
                "Socket",
                "URL",
                "FileInputStream",
                "FileOutputStream",
                "ProcessBuilder",
            }:
                return None
        dependencias, simbolos = [], []
        for referencia in (funcion.get("llama_a") or [])[:8]:
            ruta, _, objetivo = referencia.partition("::")
            destino = self.funciones.get((ruta, objetivo))
            if destino:
                resumen = f"{referencia}: {destino.get('firma', '')} {destino.get('docstring') or ''}"
                if len(resumen) <= 1000:
                    dependencias.append(resumen)
                    simbolos.append(referencia)
        llamadores = []
        for referencia in self.llamadores.get(f"{modulo}::{nombre}", [])[:MAX_FUENTES]:
            ruta, _, objetivo = referencia.partition("::")
            nodo = self._metodo(ruta, objetivo)
            if nodo is not None and len(_texto(nodo)) <= 1500:
                llamadores.append((referencia, _texto(nodo)))
        tests = self._tests_de(modulo, nombre)
        while True:
            contexto = ContextoInferencia(
                modulo,
                nombre,
                codigo,
                tuple(dependencias),
                tuple(llamadores),
                tuple(tests),
                tuple(simbolos),
            )
            if (
                len(json.dumps(contexto.a_dict(), ensure_ascii=False))
                <= self.max_caracteres
            ):
                return contexto
            if tests:
                tests.pop()
            elif llamadores:
                llamadores.pop()
            elif dependencias:
                dependencias.pop()
                simbolos.pop()
            else:
                return None

    def _cargar_tests(self) -> list[tuple[str, Node]]:
        if self._tests is not None:
            return self._tests
        self._tests = []
        examinados = 0
        for carpeta, subcarpetas, archivos in os.walk(self.raiz, followlinks=False):
            subcarpetas[:] = sorted(
                d
                for d in subcarpetas
                if not d.startswith(".")
                and d not in _IGNORADOS
                and not (Path(carpeta) / d).is_symlink()
            )
            for nombre in sorted(archivos):
                if not nombre.endswith(".java"):
                    continue
                relativa = (Path(carpeta) / nombre).relative_to(self.raiz).as_posix()
                if "/src/test/java/" not in "/" + relativa:
                    continue
                examinados += 1
                if examinados > MAX_ARCHIVOS or self._bytes >= MAX_BYTES_TOTAL:
                    return self._tests
                raiz = self._leer(relativa)
                if raiz is not None:
                    self._tests.append((relativa, raiz))
        return self._tests

    def _tests_de(self, modulo: str, objetivo: str) -> list[tuple[str, str]]:
        fuente = self._leer(modulo)
        paquete = next(
            (
                _texto(n.named_children[-1])
                for n in fuente.named_children
                if n.type == "package_declaration"
            ),
            "",
        )
        clase, metodo = objetivo.rsplit(".", 1)
        completo = paquete + "." + clase if paquete else clase
        resultado = []
        for ruta, raiz in self._cargar_tests():
            imports = [
                _texto(n).removeprefix("import ").removesuffix(";").strip()
                for n in raiz.named_children
                if n.type == "import_declaration"
            ]
            paquete_test = next(
                (
                    _texto(n.named_children[-1])
                    for n in raiz.named_children
                    if n.type == "package_declaration"
                ),
                "",
            )
            importadas = [
                i
                for i in imports
                if not i.startswith("static ") and i.rsplit(".", 1)[-1] == clase
            ]
            clase_visible = clase == clase.split(".")[0] and (
                completo in imports or (paquete == paquete_test and not importadas)
            )
            estatico = any(
                i in {f"static {completo}.{metodo}", f"static {completo}.*"}
                for i in imports
            )
            metodos_test = _metodos(raiz)
            estatico = estatico and not any(
                n.rsplit(".", 1)[-1] == metodo for n in metodos_test
            )
            for nombre, nodo in metodos_test.items():
                modificadores = next(
                    (n for n in nodo.named_children if n.type == "modifiers"), None
                )
                if modificadores is None or not any(
                    _texto(n.child_by_field_name("name")).rsplit(".", 1)[-1]
                    in {"Test", "ParameterizedTest", "RepeatedTest"}
                    for n in modificadores.named_children
                    if n.type in {"annotation", "marker_annotation"}
                ):
                    continue
                invoca = False
                variables: dict[str, str | None] = {}
                for declaracion in _recorrer(nodo):
                    if declaracion.type != "local_variable_declaration":
                        continue
                    tipo = _texto(declaracion.child_by_field_name("type"))
                    for variable in declaracion.named_children:
                        if variable.type == "variable_declarator":
                            clave = _texto(variable.child_by_field_name("name"))
                            variables[clave] = None if clave in variables else tipo
                for llamada in _recorrer(nodo):
                    if (
                        llamada.type != "method_invocation"
                        or _texto(llamada.child_by_field_name("name")) != metodo
                    ):
                        continue
                    objeto = llamada.child_by_field_name("object")
                    receptor = _texto(objeto)
                    if receptor in variables:
                        receptor = variables[receptor]
                    elif (
                        objeto is not None
                        and objeto.type == "object_creation_expression"
                    ):
                        receptor = _texto(objeto.child_by_field_name("type"))
                    if (
                        receptor == completo
                        or (clase_visible and receptor == clase)
                        or (estatico and objeto is None)
                    ):
                        invoca = True
                if invoca and len(_texto(nodo)) <= 1500:
                    resultado.append((f"{ruta}::{nombre}", _texto(nodo)))
                    if len(resultado) >= MAX_FUENTES:
                        return resultado
        return resultado

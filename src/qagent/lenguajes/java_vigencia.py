"""Claves conservadoras de reutilización Java por contexto estático (#307)."""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from qagent.lenguajes.java_sesion import analizar_fuente

VERSION = "1"
MAX_ARCHIVOS = 300
MAX_BYTES_ARCHIVO = 200_000
MAX_BYTES_TOTAL = 4_000_000
IGNORADOS = {"target", "build", "dist", "node_modules", "venv", "env", "__pycache__"}
TIPOS = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
}


def digest(valor: Any) -> str:
    """SHA-256 de datos deterministas; no almacena cuerpos ni secretos."""
    return hashlib.sha256(
        json.dumps(
            valor, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _datos(valor: Any) -> dict[str, Any]:
    return asdict(valor) if is_dataclass(valor) else {}


def _inventario(raiz: Path) -> tuple[dict[str, str], dict[str, bytes]]:
    fuentes, entorno = {}, {}
    total = 0
    for carpeta, dirs, archivos in os.walk(raiz, followlinks=False):
        permitidos = [d for d in dirs if not d.startswith(".") and d not in IGNORADOS]
        if any((Path(carpeta) / d).is_symlink() for d in permitidos):
            raise ValueError("Contexto Java con enlaces no demostrables")
        dirs[:] = sorted(permitidos)
        for nombre in sorted(archivos):
            ruta = Path(carpeta) / nombre
            relativa = ruta.relative_to(raiz).as_posix()
            recurso = "/resources/" in "/" + relativa
            if not (nombre.endswith(".java") or nombre == "pom.xml" or recurso):
                continue
            if ruta.is_symlink() or len(fuentes) + len(entorno) >= MAX_ARCHIVOS:
                raise ValueError("Contexto Java no acotado")
            with ruta.open("rb") as archivo:
                contenido = archivo.read(MAX_BYTES_ARCHIVO + 1)
            total += len(contenido)
            if len(contenido) > MAX_BYTES_ARCHIVO or total > MAX_BYTES_TOTAL:
                raise ValueError("Contexto Java excede límites de lectura")
            if nombre.endswith(".java"):
                fuentes[relativa] = (
                    contenido.decode("utf-8-sig")
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                )
            else:
                entorno[relativa] = contenido
    for nombre in (".mvn/maven.config", ".mvn/jvm.config"):
        ruta = raiz / nombre
        if ruta.exists():
            if ruta.is_symlink() or ruta.parent.is_symlink():
                raise ValueError("Configuración Maven enlazada")
            with ruta.open("rb") as archivo:
                contenido = archivo.read(MAX_BYTES_ARCHIVO + 1)
            if len(contenido) > MAX_BYTES_ARCHIVO:
                raise ValueError("Configuración Maven excesiva")
            total += len(contenido)
            if total > MAX_BYTES_TOTAL or len(fuentes) + len(entorno) >= MAX_ARCHIVOS:
                raise ValueError("Contexto Maven excede límites de lectura")
            entorno[nombre] = contenido
    return fuentes, entorno


def _grafo(fuentes: dict[str, str]) -> dict[str, set[str]]:
    tipos = defaultdict(set)
    nombres, paquetes, comodines = {}, {}, {}
    dinamicos = set()
    for ruta, fuente in fuentes.items():
        arbol, _, _ = analizar_fuente(fuente)
        if arbol.root_node.has_error:
            raise ValueError("Fuente de evidencia Java inválida")
        pendientes, identificadores = [arbol.root_node], set()
        paquetes[ruta] = ""
        comodines[ruta] = []
        while pendientes:
            nodo = pendientes.pop()
            if nodo.type in TIPOS:
                tipos[nodo.child_by_field_name("name").text.decode()].add(ruta)
            if nodo.type in {"identifier", "type_identifier"}:
                identificadores.add(nodo.text.decode())
            if nodo.type == "package_declaration":
                paquetes[ruta] = nodo.named_children[-1].text.decode()
            if nodo.type == "import_declaration" and "*" in nodo.text.decode():
                escrito = (
                    nodo.text.decode()
                    .removeprefix("import")
                    .strip()
                    .removeprefix("static")
                    .strip()
                    .removesuffix(";")
                )
                comodines[ruta].append(escrito.removesuffix(".*"))
            if nodo.type == "method_invocation" and nodo.child_by_field_name(
                "name"
            ).text.decode() in {
                "forName",
                "loadClass",
                "getMethod",
                "getDeclaredMethod",
                "invoke",
                "load",
            }:
                dinamicos.add(ruta)
            pendientes.extend(nodo.named_children)
        nombres[ruta] = identificadores
    grafo = {ruta: set() for ruta in fuentes}
    for ruta, ids in nombres.items():
        destinos = set().union(*(tipos.get(i, set()) for i in ids)) if ids else set()
        for prefijo in comodines[ruta]:
            destinos.update(r for r, paquete in paquetes.items() if paquete == prefijo)
        if ruta in dinamicos:
            destinos.update(fuentes)
        for destino in destinos - {ruta}:
            grafo[ruta].add(destino)
            grafo[destino].add(ruta)
    return grafo


def _componente(
    grafo: dict[str, set[str]], inicio: str, permitidos: set[str]
) -> set[str]:
    pendientes, vistos = [inicio], set()
    while pendientes:
        ruta = pendientes.pop()
        if ruta in vistos or ruta not in permitidos:
            continue
        vistos.add(ruta)
        pendientes.extend(grafo[ruta] - vistos)
    return vistos


def claves(
    raiz: Path,
    modulos: list[dict[str, Any]],
    configuracion: Any = None,
    imagen: str | None = None,
    *,
    inferir: bool | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Snapshot de contexto completo; un límite/lectura incierta deshabilita el caché."""
    try:
        if configuracion is None:
            from qagent.config import cargar_configuracion

            configuracion = cargar_configuracion(simulado=True).config
        fuentes, archivos_entorno = _inventario(raiz)
        grafo = _grafo(fuentes)
        produccion = {
            r
            for r in fuentes
            if "/src/test/" not in "/" + r and "test" not in Path(r).parts
        }
        hashes = {r: hashlib.sha256(c.encode()).hexdigest() for r, c in fuentes.items()}
        if any(hashes.get(m["ruta"]) != m["huella"] for m in modulos):
            return {}  # La evidencia cambió después del análisis; no certificarla.
        paquete = Path(__file__).parents[1]
        receta = [
            paquete / "sandbox/Dockerfile.java",
            paquete / "sandbox/maven.py",
            *sorted((paquete / "sandbox/java").rglob("*")),
            *sorted(Path(__file__).parent.glob("java*.py")),
        ]
        entorno = digest(
            {
                "proyecto": {
                    r: hashlib.sha256(c).hexdigest()
                    for r, c in archivos_entorno.items()
                },
                "receta": {
                    p.relative_to(paquete).as_posix(): hashlib.sha256(
                        p.read_bytes()
                    ).hexdigest()
                    for p in receta
                    if p.is_file()
                },
            }
        )
        politica = _datos(getattr(configuracion, "inferencia", None))
        if inferir is not None:
            politica["activa"] = inferir
        limites = getattr(configuracion, "limites_sandbox", None)
        ejecucion = _datos(limites("java") if callable(limites) else None)
        mutacion = _datos(getattr(configuracion, "mutacion", None))
        resultado, componentes = {}, {}
        for modulo in modulos:
            ruta = modulo["ruta"]
            if ruta not in produccion or hashes[ruta] != modulo["huella"]:
                continue
            for objetivo in [
                *modulo.get("funciones", []),
                *modulo.get("endpoints", []),
            ]:
                nombre = objetivo.get("objetivo") or objetivo.get("nombre")
                inferido = not objetivo.get("docstring") and "objetivo" not in objetivo
                k = (ruta, inferido)
                if k not in componentes:
                    relacionadas = _componente(
                        grafo, ruta, set(fuentes) if inferido else produccion
                    )
                    componentes[k] = {r: hashes[r] for r in sorted(relacionadas)}
                spec = digest(
                    [
                        VERSION,
                        "spec",
                        nombre,
                        componentes[k],
                        entorno,
                        politica if inferido else {},
                    ]
                )
                pruebas = digest([VERSION, "pruebas", spec, ejecucion])
                resultado[(ruta, nombre)] = {
                    "version": VERSION,
                    "spec": spec,
                    "pruebas": pruebas,
                    "mutacion": digest([VERSION, "mutacion", pruebas, mutacion]),
                    "entorno": imagen,
                }
        return resultado
    except (OSError, UnicodeError, ValueError, RecursionError):
        return {}

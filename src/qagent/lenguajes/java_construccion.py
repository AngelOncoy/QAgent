"""Construcción Maven previa a IA: copia fija, Docker offline y cache por inputs (#305)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

from qagent.almacenamiento import AlmacenProyecto, ErrorAlmacen
from qagent.almacenamiento.disco import escribir_json_atomico, leer_json_objeto
from qagent.lenguajes.base import ResultadoConstruccion
from qagent.sandbox.cliente import obtener_cliente
from qagent.sandbox.ejecucion import copiar_proyecto, ejecutar_en_sandbox
from qagent.sandbox.maven import inspeccionar, separar_fuente
from qagent.sandbox.modelos import (
    ErrorConstruccionImagen,
    LimitesSandbox,
    ResultadoSandbox,
)
from qagent.storage.diagnostico_entorno import sanear_diagnostico

POLITICA = "java-construccion-v1"
ENTORNO = {"MAVEN_SKIP_RC": "true"}


class _Cancelada(Exception):
    """Cancelación durante la toma de inputs, anterior a ejecutar Maven."""


def comando_construccion(raiz: Path, modulos: list[str]) -> list[str]:
    """Compila producción de los módulos seleccionados y su reactor, sin tests."""
    proyecto = inspeccionar(raiz)
    declarados = {
        PurePosixPath(d.ruta).parent.as_posix() for d in proyecto.descriptores
    }
    seleccionados = sorted({separar_fuente(m)[0] or "." for m in modulos})
    if not seleccionados or any(m not in declarados for m in seleccionados):
        raise ValueError("La selección no pertenece a módulos Maven declarados.")
    reactor = any(d.modulos for d in proyecto.descriptores)
    return [
        "mvn",
        "--offline",
        "--batch-mode",
        "--no-transfer-progress",
        "-Dmaven.repo.local=/opt/qagent/m2",
        "-f",
        "/work/proyecto/pom.xml",
        *(["-pl", ",".join(seleccionados), "-am"] if reactor else []),
        "-DskipTests=true",
        "-Dmaven.test.skip=true",
        "-DskipITs=true",
        "clean",
        "compile",
    ]


def huella_construccion(
    copia: Path,
    imagen_id: str,
    comando: list[str],
    cancelado: Callable[[], bool] | None = None,
    *,
    entorno: dict[str, Any] | None = None,
) -> str:
    """SHA-256 de inputs de una copia fija, selección, política e imagen inmutable."""
    proyecto = inspeccionar(copia)
    salidas = {
        (PurePosixPath(d.ruta).parent / "target").as_posix()
        for d in proyecto.descriptores
    }
    digest = hashlib.sha256(
        json.dumps(
            [POLITICA, imagen_id, comando, ENTORNO, entorno], sort_keys=True
        ).encode("utf-8")
    )

    def cabecera(tipo: bytes, ruta: str, tamano: int = 0) -> None:
        if cancelado is not None and cancelado():
            raise _Cancelada()
        nombre = ruta.encode("utf-8")
        digest.update(
            tipo + len(nombre).to_bytes(8, "big") + nombre + tamano.to_bytes(8, "big")
        )

    for carpeta, directorios, archivos in os.walk(copia, followlinks=False):
        for nombre in sorted([*directorios, *archivos]):
            archivo = Path(carpeta) / nombre
            relativa = archivo.relative_to(copia).as_posix()
            if relativa in salidas:
                if nombre in directorios:
                    directorios.remove(nombre)
                continue
            if archivo.is_symlink():
                destino = os.readlink(archivo).encode("utf-8")
                cabecera(b"L", relativa, len(destino))
                digest.update(destino)
            elif archivo.is_dir():
                cabecera(b"D", relativa)
            else:
                cabecera(b"F", relativa, archivo.stat().st_size)
                with archivo.open("rb") as entrada:
                    while bloque := entrada.read(1_048_576):
                        if cancelado is not None and cancelado():
                            raise _Cancelada()
                        digest.update(bloque)
        directorios.sort()
    return digest.hexdigest()


def clasificar_construccion(salida: ResultadoSandbox) -> ResultadoConstruccion:
    """Distingue causas técnicas mediante reglas; un error no se convierte en bug."""
    bruto = salida.stdout[-262_144:] + "\n" + salida.stderr[-262_144:]
    log = sanear_diagnostico(bruto)
    if salida.cancelado:
        return ResultadoConstruccion(
            "cancelado",
            "cancelado",
            "Construcción Java cancelada antes de usar IA.",
            log,
        )
    if salida.timed_out:
        return ResultadoConstruccion(
            "timeout",
            "timeout",
            "La construcción Java agotó el tiempo; no se llamó a la IA.",
            log,
        )
    if salida.oom_killed:
        return ResultadoConstruccion(
            "fallido",
            "recursos",
            "Docker agotó la memoria al comprobar Java; no se llamó a la IA.",
            log,
        )
    if salida.exit_code == 0:
        return ResultadoConstruccion(
            "aprobado",
            "aprobado",
            "Construcción Java comprobada en Docker offline antes de usar IA.",
            log,
        )
    texto = log.lower()
    if any(
        p in texto
        for p in (
            "in offline mode",
            "could not resolve dependencies",
            "could not find artifact",
            "has not been downloaded",
            "pluginresolutionexception",
            "dependencyresolutionexception",
            "non-resolvable parent pom",
        )
    ):
        categoria, mensaje = (
            "dependencias",
            "Faltan dependencias o plugins en el entorno offline; revisa la preparación de la imagen.",
        )
    elif any(
        p in texto
        for p in (
            "unsupported class file",
            "unsupportedclassversionerror",
            "invalid target release",
            "class file has wrong version",
            "invalid flag: --release",
            "no compiler is provided in this environment",
            "nosuchfielderror",
            "no matching toolchains",
            "inaccessibleobjectexception",
            "nosuchmethoderror",
            "illegalaccesserror",
        )
    ) or re.search(
        r"(?:release version[^\n]*not supported|(?:source|target) option[^\n]*(?:not supported|no longer supported))",
        texto,
    ):
        categoria, mensaje = (
            "incompatibilidad_herramienta",
            "El JDK o las herramientas declaradas no son compatibles con esta construcción.",
        )
    elif any(
        p in texto
        for p in (
            "malformed pom",
            "non-parseable pom",
            "unrecognised tag",
            "unknown lifecycle",
            "unknown packaging",
            "not available in the reactor",
            "could not find the selected project",
            "invalid plugin descriptor",
        )
    ):
        categoria, mensaje = (
            "configuracion",
            "La configuración Maven no permite construir los módulos seleccionados.",
        )
    elif any(
        p in texto
        for p in (
            "compilation failure",
            "compilation error",
            "cannot find symbol",
            "incompatible types",
            "';' expected",
            "reached end of file",
            "illegal start of",
        )
    ):
        categoria, mensaje = (
            "compilacion",
            "Las fuentes de producción no compilan con la configuración declarada.",
        )
    else:
        categoria, mensaje = (
            "tecnico",
            "La construcción Java falló; consulta el diagnóstico sin atribuirlo a una prueba generada.",
        )
    return ResultadoConstruccion(
        "fallido", categoria, mensaje + " No se llamó a la IA.", log
    )


def comprobar_construccion(
    raiz: Path,
    imagen: str,
    modulos: list[str],
    limites: LimitesSandbox,
    cancelado: Callable[[], bool] | None = None,
    *,
    cliente: Any = None,
    ejecutor: Callable[..., ResultadoSandbox] | None = None,
) -> ResultadoConstruccion:
    """Comprueba una copia del proyecto sin modificar POM, fuentes ni tests originales."""
    inicio = time.monotonic()
    huella = imagen_id = None
    comando: list[str] = []
    contexto: dict[str, Any] = {}
    try:
        if cancelado is not None and cancelado():
            raise _Cancelada()
        cliente = cliente or obtener_cliente()
        info = cliente.info()
        contexto = {
            "docker": {
                k: info.get(k)
                for k in ("OSType", "Architecture", "NCPU", "ServerVersion")
            },
            "limites": asdict(limites),
        }
        imagen_id = cliente.images.get(imagen).id
        if not isinstance(imagen_id, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", imagen_id
        ):
            raise ValueError("Docker no proporcionó el ID inmutable de la imagen Java.")
        with tempfile.TemporaryDirectory(prefix="qagent-construccion-") as temporal:
            carpeta = Path(temporal)
            copia = copiar_proyecto(raiz, carpeta / "proyecto")
            comando = comando_construccion(copia, modulos)
            huella = huella_construccion(
                copia, imagen_id, comando, cancelado, entorno=contexto
            )
            cache = raiz / ".qagent/cache/construccion_java" / (huella + ".json")
            try:
                guardado = leer_json_objeto(cache)
            except (ErrorAlmacen, OSError, ValueError):
                guardado = {}
            if (
                guardado.get("politica") == POLITICA
                and guardado.get("huella") == huella
                and guardado.get("imagen_id") == imagen_id
                and guardado.get("comando") == comando
                and guardado.get("entorno") == contexto
                and guardado.get("estado") == "aprobado"
                and guardado.get("categoria") == "aprobado"
            ):
                if cancelado is not None and cancelado():
                    raise _Cancelada()
                return ResultadoConstruccion(
                    "aprobado",
                    "aprobado",
                    "Construcción Java vigente: se reutiliza la comprobación por entradas e imagen.",
                    huella=huella,
                    imagen_id=imagen_id,
                    comando=comando,
                    reutilizado=True,
                    entorno=contexto,
                    duracion_s=round(time.monotonic() - inicio, 3),
                )
            pruebas = carpeta / "pruebas"
            pruebas.mkdir()
            salida = (ejecutor or ejecutar_en_sandbox)(
                imagen_id,
                comando,
                copia,
                pruebas,
                limites,
                entorno=ENTORNO,
                cliente=cliente,
                cancelado=cancelado,
            )
            resultado = clasificar_construccion(salida)
            if cancelado is not None and cancelado():
                resultado = ResultadoConstruccion(
                    "cancelado",
                    "cancelado",
                    "Construcción Java cancelada antes de usar IA.",
                    resultado.log,
                )
            resultado.huella, resultado.imagen_id = huella, imagen_id
            resultado.comando = comando
            resultado.entorno = contexto
            resultado.duracion_s = round(time.monotonic() - inicio, 3)
            if resultado.aprobado:
                try:
                    AlmacenProyecto(raiz).inicializar()
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    escribir_json_atomico(
                        cache, {"politica": POLITICA, **resultado.metadatos()}
                    )
                except (ErrorAlmacen, OSError):
                    resultado.log += (
                        "\nNo se pudo guardar la reutilización de esta comprobación."
                    )
            return resultado
    except _Cancelada:
        resultado = ResultadoConstruccion(
            "cancelado", "cancelado", "Construcción Java cancelada antes de usar IA."
        )
    except Exception as error:  # noqa: BLE001 — un fallo técnico bloquea la IA
        log = sanear_diagnostico(str(error))
        categoria = (
            "configuracion"
            if isinstance(error, (ValueError, ErrorConstruccionImagen))
            else "tecnico"
        )
        resultado = ResultadoConstruccion(
            "fallido",
            categoria,
            "No se pudo comprobar la construcción Java; no se llamó a la IA.",
            log,
        )
    resultado.huella, resultado.imagen_id = huella, imagen_id
    resultado.comando = comando
    resultado.entorno = contexto
    resultado.duracion_s = round(time.monotonic() - inicio, 3)
    return resultado

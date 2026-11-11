"""Cuánto ocupa QAgent en Docker y «Liberar espacio» (#267, Capa 3).

Es la parte de lógica de la sección «Espacio en disco» de Configuración: `medir_uso` dice
cuánto ocupan las imágenes base, las derivadas, los restos de construcciones cortadas y la
caché de compilación, y cuánto espacio libre queda; `liberar_espacio` borra lo que se puede
reconstruir. La interfaz (`app/desktop.py`) solo llama a estas funciones.

Qué hace y qué no hace `liberar_espacio`:

- Borra los contenedores de corridas interrumpidas y de construcciones cortadas, las capas
  sin etiqueta de QAgent y **todas** las imágenes derivadas (`req-`, `node-`, `java-`,
  `browser-`): se reconstruyen en la próxima corrida que las necesite.
- Conserva las imágenes base, la de una corrida en curso (las usadas o creadas hace menos de
  1 h no se tocan) y todo lo que no sea de QAgent.
- La caché de compilación de Docker solo se poda si la persona lo pide (`incluir_cache`).
  No admite labels, así que alcanza la de todos sus `docker build`, no solo la de QAgent; la
  interfaz lo dice en la confirmación. Se poda la que lleva más de `cache_antiguedad_dias`.

Nada de esto lanza excepciones: sin Docker devuelve `{"ok": False, "mensaje": ...}`.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import escribir_json_atomico
from qagent.config.disco import LimitesDisco, leer_limites_disco
from qagent.sandbox import espacio, limpieza
from qagent.sandbox.modelos import ETIQUETA_CONSTRUCCION, ETIQUETA_CONTENEDOR

registro = logging.getLogger(__name__)

#: Medir y borrar puede tardar más que el ping del arranque: lo pide una persona.
TIMEOUT_DOCKER_S = 30
MENSAJE_SIN_DOCKER = (
    "Docker no responde. Ábrelo, espera a que termine de arrancar y vuelve a intentar."
)


def medir_uso(
    cliente: Any = None,
    ruta_usos: Path | None = None,
    limites: LimitesDisco | None = None,
    libre: Callable[[], int | None] | None = None,
    ahora: float | None = None,
) -> dict:
    """Cuánto ocupa QAgent en Docker y cuánto espacio libre queda.

    El espacio libre del disco se mide aunque Docker no responda.

    Returns:
        `{"ok", "libre_bytes", "minimo_bytes", "bases": {"cantidad", "bytes"},
        "derivadas": {"cantidad", "bytes", "tope_bytes"},
        "restos": {"contenedores", "capas", "bytes"},
        "cache": {"bytes", "dias"}, "total_bytes"}`. Con `ok` False (Docker no responde)
        solo trae `mensaje`, `libre_bytes` y `minimo_bytes`.
    """
    limites = limites or leer_limites_disco()
    medido = {
        "libre_bytes": _libre(libre),
        "minimo_bytes": limites.espacio_libre_minimo_bytes,
    }
    cliente_propio, cliente = _conectar(cliente)
    if cliente is None:
        return {"ok": False, "mensaje": MENSAJE_SIN_DOCKER, **medido}
    try:
        ahora = limpieza.time.time() if ahora is None else ahora
        usos = limpieza.leer_usos(ruta_usos or limpieza.RUTA_USOS)
        derivadas, bases = limpieza.listar_derivadas(cliente, usos, ahora)
        restos = _restos(cliente, ahora)
        bytes_bases = sum(b for b, _capas in bases)
        bytes_derivadas = sum(d["bytes"] for d in derivadas)
        return {
            "ok": True,
            **medido,
            "bases": {"cantidad": len(bases), "bytes": bytes_bases},
            "derivadas": {
                "cantidad": len(derivadas),
                "bytes": bytes_derivadas,
                "tope_bytes": limites.tope_imagenes_derivadas_bytes,
            },
            "restos": restos,
            "cache": {
                "bytes": _bytes_cache(cliente),
                "dias": limites.cache_antiguedad_dias,
            },
            "total_bytes": bytes_bases + bytes_derivadas + restos["bytes"],
        }
    except Exception as exc:  # noqa: BLE001 — medir nunca rompe la pantalla
        registro.warning("No se pudo medir lo que ocupa QAgent en Docker: %s", exc)
        return {"ok": False, "mensaje": MENSAJE_SIN_DOCKER, **medido}
    finally:
        _cerrar(cliente_propio, cliente)


def liberar_espacio(
    cliente: Any = None,
    ruta_usos: Path | None = None,
    limites: LimitesDisco | None = None,
    incluir_cache: bool = False,
    ahora: float | None = None,
) -> dict:
    """Borra lo que se puede reconstruir y conserva las imágenes base.

    Args:
        cliente: cliente Docker (por defecto se conecta).
        ruta_usos: archivo con el último uso de cada imagen derivada.
        limites: límites de `[disco]`; si es None se leen de config.toml.
        incluir_cache: también poda la caché de compilación de Docker sin usar en más de
            `cache_antiguedad_dias`. Es la de TODOS los `docker build`, no solo la de QAgent.
        ahora: segundos desde la época (para las pruebas).

    Returns:
        `{"ok", "mensaje", "contenedores", "construcciones", "capas", "imagenes",
        "cache_bytes", "liberado_bytes"}`; con `ok` False, solo `mensaje`.
    """
    limites = limites or leer_limites_disco()
    ruta_usos = ruta_usos or limpieza.RUTA_USOS
    cliente_propio, cliente = _conectar(cliente)
    if cliente is None:
        return {"ok": False, "mensaje": MENSAJE_SIN_DOCKER}
    try:
        return _liberar(cliente, ruta_usos, limites, incluir_cache, ahora)
    except Exception as exc:  # noqa: BLE001 — no se rompe la pantalla por un fallo de Docker
        registro.warning("No se pudo liberar el espacio: %s", exc)
        return {"ok": False, "mensaje": MENSAJE_SIN_DOCKER}
    finally:
        _cerrar(cliente_propio, cliente)


def _liberar(
    cliente: Any,
    ruta_usos: Path,
    limites: LimitesDisco,
    incluir_cache: bool,
    ahora: float | None,
) -> dict:
    ahora = limpieza.time.time() if ahora is None else ahora
    usos = limpieza.leer_usos(ruta_usos)
    intentar = limpieza._intentar
    contenedores = intentar(
        "contenedores huérfanos",
        lambda: limpieza.eliminar_contenedores_huerfanos(cliente, ahora),
        0,
    )
    construcciones = intentar(
        "contenedores de construcción",
        lambda: limpieza.eliminar_contenedores_construccion(cliente, ahora),
        0,
    )
    capas, capas_bytes = intentar(
        "capas sin etiqueta",
        lambda: limpieza.eliminar_capas_sin_etiqueta(cliente),
        (0, 0),
    )
    derivadas = intentar(
        "imágenes derivadas",
        lambda: limpieza.listar_derivadas(cliente, usos, ahora)[0],
        [],
    )
    # Tope -1: se borran todas las derivadas salvo las protegidas (usadas hace < 1 h).
    imagenes = intentar(
        "imágenes derivadas",
        lambda: limpieza.aplicar_tope_imagenes(cliente, usos, -1, ahora),
        [],
    )
    imagenes_bytes = sum(
        d["bytes"] for d in derivadas if set(d["etiquetas"]) <= set(imagenes)
    )
    cache_bytes = 0
    if incluir_cache and limites.cache_antiguedad_dias is not None:
        dias = limites.cache_antiguedad_dias
        cache_bytes = intentar(
            "caché de compilación",
            lambda: limpieza.podar_cache_compilacion(cliente, dias),
            0,
        )
    if imagenes:
        with contextlib.suppress(OSError):
            escribir_json_atomico(
                ruta_usos, {k: v for k, v in usos.items() if k not in imagenes}
            )
    liberado = capas_bytes + imagenes_bytes + cache_bytes
    return {
        "ok": True,
        "mensaje": _mensaje(liberado, contenedores + construcciones, capas, imagenes),
        "contenedores": contenedores,
        "construcciones": construcciones,
        "capas": capas,
        "imagenes": imagenes,
        "cache_bytes": cache_bytes,
        "liberado_bytes": liberado,
    }


def _mensaje(liberado: int, contenedores: int, capas: int, imagenes: list[str]) -> str:
    if not (liberado or contenedores or capas or imagenes):
        return "No había nada que borrar: QAgent no tenía restos ni imágenes reconstruibles."
    partes = []
    if imagenes:
        partes.append(f"{len(imagenes)} imagen(es) de proyectos")
    if contenedores:
        partes.append(f"{contenedores} contenedor(es) sobrante(s)")
    if capas:
        partes.append(f"{capas} capa(s) sin etiqueta")
    detalle = f" Se borró: {', '.join(partes)}." if partes else ""
    return (
        f"Se liberaron {espacio.texto_tamano(liberado)} dentro de Docker.{detalle} "
        "Para recuperar ese espacio en tu disco hay que compactar el disco de Docker."
    )


def _restos(cliente: Any, ahora: float) -> dict:
    """Contenedores y capas que dejaron corridas y construcciones cortadas (lo que se borraría)."""
    contenedores = 0
    for etiqueta, es_resto in (
        (ETIQUETA_CONTENEDOR, limpieza.es_contenedor_huerfano),
        (ETIQUETA_CONSTRUCCION, limpieza.es_contenedor_construccion_cortado),
    ):
        filtro = {"label": limpieza._filtro_label(etiqueta)}
        contenedores += sum(
            1
            for c in cliente.containers.list(all=True, filters=filtro)
            if es_resto(c, ahora)
        )
    limite = ahora - limpieza.ANTIGUEDAD_CONSTRUCCION_S
    capas = [
        i
        for i in cliente.images.list(
            filters={
                "dangling": True,
                "label": limpieza._filtro_label(ETIQUETA_CONSTRUCCION),
            }
        )
        if (limpieza._segundos(i.attrs.get("Created")) or 0) <= limite
    ]
    return {
        "contenedores": contenedores,
        "capas": len(capas),
        "bytes": sum(limpieza._entero(i.attrs.get("Size")) for i in capas),
    }


def _bytes_cache(cliente: Any) -> int | None:
    """Tamaño de la caché de compilación de Docker (de todos los builds), o None si no se sabe."""
    try:
        entradas = cliente.df().get("BuildCache") or []
        return sum(limpieza._entero(e.get("Size")) for e in entradas)
    except Exception:  # noqa: BLE001 — Docker sin BuildKit o sin ese dato
        return None


def _libre(libre: Callable[[], int | None] | None) -> int | None:
    try:
        return (libre or espacio.espacio_libre_bytes)()
    except Exception:  # noqa: BLE001
        return None


def _conectar(cliente: Any) -> tuple[bool, Any]:
    """`(propio, cliente)`; el cliente es None si Docker no responde."""
    if cliente is not None:
        return False, cliente
    try:
        import docker

        nuevo = docker.from_env(timeout=TIMEOUT_DOCKER_S)
        nuevo.ping()
        return True, nuevo
    except Exception:  # noqa: BLE001
        return False, None


def _cerrar(propio: bool, cliente: Any) -> None:
    if propio and cliente is not None:
        with contextlib.suppress(Exception):
            cliente.close()

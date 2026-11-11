"""Limpieza de lo que el sandbox deja en Docker (#267): huérfanos, capas e imágenes.

Cada ejecución borra su contenedor al terminar (`ejecucion._eliminar`), pero si la app se
cierra de golpe a mitad de una corrida ese paso no llega a correr y el contenedor queda.
Lo mismo pasa con una construcción de imagen cortada (cancelada, app cerrada, Docker
caído): queda su contenedor intermedio, con capas, a veces de varios GB (un `pip install`).
Además, `preparar_imagen` guarda una imagen `qagent-sandbox:req-<hash>` por cada
requirements.txt distinto (y `node-`, `java-` y `browser-`, #169); sirve de caché, pero
cada una ocupa cientos de MB o varios GB.

`limpiar_al_iniciar` (la automática) hace, al abrir la app y al terminar cada corrida:

1. borra los contenedores de corridas interrumpidas (label `ETIQUETA_CONTENEDOR`);
2. borra los contenedores de construcciones cortadas (label `ETIQUETA_CONSTRUCCION`);
3. borra las capas sin etiqueta que dejaron esas construcciones (mismo label);
4. borra las imágenes derivadas sin uso en `DIAS_SIN_USO` días;
5. aplica el tope de espacio de las imágenes derivadas (`[disco]` de config.toml).

Solo se borra lo que lleva un label de QAgent o el repositorio `qagent-sandbox`: el usuario
tiene otras imágenes, contenedores y volúmenes en el mismo Docker. Nunca toca las imágenes
base y nunca lanza excepciones.

La caché de compilación de Docker NO se poda aquí: no admite labels, así que podarla
alcanzaría también la de los `docker build` del usuario. Solo se poda cuando la persona lo
pide y lo confirma (`liberar_espacio`, botón «Liberar espacio» de Configuración).
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
from collections.abc import Callable, Collection
from datetime import datetime
from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import escribir_json_atomico
from qagent.config.disco import LimitesDisco, leer_limites_disco
from qagent.sandbox.modelos import (
    ETIQUETA_CONSTRUCCION,
    ETIQUETA_CONTENEDOR,
    REPOSITORIO,
)
from qagent.usuario import carpeta_usuario

registro = logging.getLogger(__name__)

#: Último uso de cada imagen `req-` (segundos desde la época), en `~/.qagent/`.
RUTA_USOS = carpeta_usuario() / "imagenes_sandbox.json"
#: Prefijo del tag de las imágenes derivadas por requirements.txt.
PREFIJO_REQ = "req-"
#: Prefijos de todas las imágenes derivadas por proyecto: Python, Node, Java y navegador (#169).
PREFIJOS_DERIVADAS = (PREFIJO_REQ, "node-", "java-", "browser-")
#: Una imagen `req-` sin usar durante este tiempo se borra (se reconstruye si vuelve a hacer falta).
DIAS_SIN_USO = 30
#: Un contenedor del sandbox que sigue corriendo se considera huérfano pasado este tiempo.
#: Ninguna ejecución dura tanto (el timeout por defecto es de 120 s); el margen evita
#: borrar el contenedor de otra ventana de QAgent que esté corriendo pruebas.
ANTIGUEDAD_HUERFANO_S = 60 * 60
TIMEOUT_DOCKER_S = 10
#: Una capa o contenedor de construcción más reciente que esto puede ser de un build en
#: curso (otra ventana de QAgent): no se toca.
ANTIGUEDAD_CONSTRUCCION_S = ANTIGUEDAD_HUERFANO_S

_NANOSEGUNDOS = re.compile(r"(\.\d{1,6})\d*")


def leer_usos(ruta: Path | None = None) -> dict[str, float]:
    """Último uso de cada imagen derivada; vacío si el archivo no existe o está dañado."""
    ruta = ruta or RUTA_USOS
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {
        str(k): float(v)
        for k, v in datos.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def registrar_uso(
    imagen: str, ruta: Path | None = None, ahora: float | None = None
) -> None:
    """Anota que una corrida usó `imagen`. Cuenta para toda imagen derivada (`PREFIJOS_DERIVADAS`).

    No lanza excepciones: si no se puede escribir, la imagen solo pierde su fecha de uso.
    """
    if not _es_imagen_req(imagen):
        return
    ruta = ruta or RUTA_USOS
    usos = leer_usos(ruta)
    usos[imagen] = time.time() if ahora is None else ahora
    try:
        escribir_json_atomico(ruta, usos)
    except OSError as exc:
        registro.warning("No se pudo anotar el uso de la imagen %s: %s", imagen, exc)


def es_contenedor_huerfano(contenedor: Any, ahora: float) -> bool:
    """True si un contenedor del sandbox es de una corrida interrumpida.

    Los detenidos lo son; uno que sigue corriendo solo pasado `ANTIGUEDAD_HUERFANO_S`.
    """
    if contenedor.status != "running":
        return True
    creado = _segundos(contenedor.attrs.get("Created"))
    return creado is not None and ahora - creado >= ANTIGUEDAD_HUERFANO_S


def es_contenedor_construccion_cortado(contenedor: Any, ahora: float) -> bool:
    """True si un contenedor de construcción lleva más de `ANTIGUEDAD_CONSTRUCCION_S`."""
    creado = _segundos(contenedor.attrs.get("Created"))
    return creado is not None and ahora - creado >= ANTIGUEDAD_CONSTRUCCION_S


def eliminar_contenedores_huerfanos(cliente: Any, ahora: float | None = None) -> int:
    """Borra los contenedores del sandbox que quedaron de una corrida interrumpida.

    Se borran los detenidos y los que siguen corriendo desde hace más de
    `ANTIGUEDAD_HUERFANO_S`. Solo se buscan los que llevan `ETIQUETA_CONTENEDOR`.

    Returns:
        Cuántos contenedores se borraron.
    """
    ahora = time.time() if ahora is None else ahora
    filtro = {"label": [f"{k}={v}" for k, v in ETIQUETA_CONTENEDOR.items()]}
    borrados = 0
    for contenedor in cliente.containers.list(all=True, filters=filtro):
        if not es_contenedor_huerfano(contenedor, ahora):
            continue
        try:
            contenedor.remove(force=True)
            borrados += 1
        except Exception as exc:  # noqa: BLE001 — uno que no se borra no detiene los demás
            registro.warning(
                "No se pudo borrar el contenedor %s: %s", contenedor.id, exc
            )
    return borrados


def eliminar_imagenes_sin_uso(
    cliente: Any, usos: dict[str, float], ahora: float | None = None
) -> list[str]:
    """Borra las imágenes `req-` que no se usan desde hace más de `DIAS_SIN_USO` días.

    El último uso sale de `usos`; si una imagen no aparece, cuenta su fecha de creación.
    Una imagen que está usando un contenedor no se borra (Docker lo rechaza).

    Returns:
        Etiquetas de las imágenes borradas.
    """
    ahora = time.time() if ahora is None else ahora
    limite = ahora - DIAS_SIN_USO * 24 * 60 * 60
    borradas = []
    for imagen in cliente.images.list(name=REPOSITORIO):
        for etiqueta in imagen.tags:
            if not _es_imagen_req(etiqueta):
                continue
            ultimo = usos.get(etiqueta, _segundos(imagen.attrs.get("Created")))
            if ultimo is None or ultimo > limite:
                continue
            try:
                cliente.images.remove(etiqueta)
                borradas.append(etiqueta)
            except Exception as exc:  # noqa: BLE001 — en uso o ya borrada: se intenta la próxima vez
                registro.warning("No se pudo borrar la imagen %s: %s", etiqueta, exc)
    return borradas


def eliminar_contenedores_construccion(cliente: Any, ahora: float | None = None) -> int:
    """Borra los contenedores intermedios que dejó una construcción de imagen cortada.

    Una construcción cortada (cancelada, app cerrada, Docker caído) deja su contenedor de
    build, con las capas de lo que alcanzó a instalar (en la prueba real de #267, 6,26 GB
    de un `pip install`). Se buscan por `ETIQUETA_CONSTRUCCION`. Los de menos de
    `ANTIGUEDAD_CONSTRUCCION_S` no se tocan, estén como estén: pueden ser de un build que
    otra ventana de QAgent está haciendo ahora mismo.

    Returns:
        Cuántos contenedores se borraron.
    """
    ahora = time.time() if ahora is None else ahora
    filtro = {"label": _filtro_label(ETIQUETA_CONSTRUCCION)}
    borrados = 0
    for contenedor in cliente.containers.list(all=True, filters=filtro):
        if not es_contenedor_construccion_cortado(contenedor, ahora):
            continue
        try:
            contenedor.remove(force=True)
            borrados += 1
        except Exception as exc:  # noqa: BLE001 — uno que no se borra no detiene los demás
            registro.warning(
                "No se pudo borrar el contenedor de construcción %s: %s",
                contenedor.id,
                exc,
            )
    return borrados


def eliminar_capas_sin_etiqueta(cliente: Any) -> tuple[int, int]:
    """Borra las capas sin nombre que dejaron las construcciones de QAgent.

    Solo las imágenes sin tag (`dangling`) con `ETIQUETA_CONSTRUCCION` y de más de
    `ANTIGUEDAD_CONSTRUCCION_S`: Docker no toca una capa que use un contenedor, ni las
    intermedias de un build en curso por ser recientes. Las imágenes sin label (del usuario
    o construidas antes de #267) no se tocan.

    Returns:
        `(capas borradas, bytes liberados)`.
    """
    resultado = cliente.images.prune(
        filters={
            "dangling": True,
            "label": _filtro_label(ETIQUETA_CONSTRUCCION),
            "until": f"{ANTIGUEDAD_CONSTRUCCION_S // 60}m",
        }
    )
    resultado = resultado if isinstance(resultado, dict) else {}
    return len(resultado.get("ImagesDeleted") or []), _entero(
        resultado.get("SpaceReclaimed")
    )


def podar_cache_compilacion(cliente: Any, dias: float) -> int:
    """Poda la caché de compilación de Docker que lleva más de `dias` sin usarse.

    La caché de compilación (BuildKit) no admite labels: no se puede saber de quién es cada
    entrada, así que se poda solo por antigüedad y **alcanza también la caché de los
    `docker build` del usuario**. Por eso no forma parte de la limpieza automática: solo
    se llama desde `liberar_espacio`, tras la confirmación de la persona. Es caché pura: si
    hace falta se reconstruye. No toca imágenes, contenedores ni volúmenes.

    Returns:
        Bytes liberados.
    """
    resultado = cliente.api.prune_builds(filters={"until": f"{int(dias * 24)}h"})
    return _entero(
        resultado.get("SpaceReclaimed") if isinstance(resultado, dict) else 0
    )


def aplicar_tope_imagenes(
    cliente: Any,
    usos: dict[str, float],
    tope_bytes: int,
    ahora: float | None = None,
    protegidas: Collection[str] = (),
) -> list[str]:
    """Borra las imágenes derivadas menos usadas hasta que ocupen menos de `tope_bytes`.

    Cuentan las imágenes `req-`, `node-`, `java-` y `browser-` (`PREFIJOS_DERIVADAS`).
    El espacio de cada una es el suyo propio, sin las capas de la imagen base que comparte
    (de lo contrario el tope se agotaría con la base). Nunca se borran: las imágenes base,
    las de `protegidas` (la de la corrida en curso) ni las que se usaron o crearon hace
    menos de `ANTIGUEDAD_HUERFANO_S`, que pueden ser de otra corrida. Una imagen que Docker
    no deja borrar (la usa un contenedor) se salta y se sigue con la siguiente.

    Returns:
        Etiquetas de las imágenes borradas, de la menos usada a la más usada.
    """
    candidatas = listar_derivadas(cliente, usos, ahora, protegidas)[0]
    total = sum(c["bytes"] for c in candidatas)
    borradas: list[str] = []
    for candidata in sorted(candidatas, key=lambda c: c["ultimo"]):
        if total <= tope_bytes:
            break
        if candidata["protegida"]:
            continue
        quitadas = []
        for etiqueta in candidata["etiquetas"]:
            try:
                cliente.images.remove(etiqueta)
                quitadas.append(etiqueta)
            except Exception as exc:  # noqa: BLE001 — en uso o ya borrada: se salta
                registro.warning("No se pudo borrar la imagen %s: %s", etiqueta, exc)
        borradas += quitadas
        if len(quitadas) == len(candidata["etiquetas"]):
            total -= candidata["bytes"]
    return borradas


def listar_derivadas(
    cliente: Any,
    usos: dict[str, float],
    ahora: float | None = None,
    protegidas: Collection[str] = (),
) -> tuple[list[dict], list[tuple[int, list[str]]]]:
    """Las imágenes derivadas de QAgent y las bases, con su espacio, último uso y protección.

    Returns:
        `(derivadas, bases)`. Cada derivada es `{"etiquetas", "bytes", "ultimo", "protegida"}`
        (`bytes` es solo lo propio, sin la base que comparte; `protegida` si es de
        `protegidas` o se usó o creó hace menos de `ANTIGUEDAD_HUERFANO_S`). Cada base es
        `(bytes de la imagen, capas)`.
    """
    ahora = time.time() if ahora is None else ahora
    imagenes = list(cliente.images.list(name=REPOSITORIO))
    bases = [
        (_entero(i.attrs.get("Size")), _capas(cliente, i))
        for i in imagenes
        if i.tags and not any(_es_imagen_req(t) for t in i.tags)
    ]
    derivadas = []
    for imagen in imagenes:
        etiquetas = [t for t in imagen.tags if _es_imagen_req(t)]
        if not etiquetas:
            continue
        creada = _segundos(imagen.attrs.get("Created")) or 0.0
        ultimo = max(usos.get(t, creada) for t in etiquetas)
        derivadas.append(
            {
                "etiquetas": etiquetas,
                "bytes": _tamano_propio(cliente, imagen, bases),
                "ultimo": ultimo,
                "protegida": any(t in protegidas for t in etiquetas)
                or ultimo > ahora - ANTIGUEDAD_HUERFANO_S,
            }
        )
    return derivadas, bases


def limpiar_al_iniciar(
    cliente: Any = None,
    ruta_usos: Path | None = None,
    limites: LimitesDisco | None = None,
    protegidas: Collection[str] = (),
) -> dict:
    """Limpia lo que el sandbox dejó en Docker. Pensada para el arranque y el fin de cada corrida.

    Si Docker no está instalado o no responde, no hace nada. Si Docker responde, ningún
    paso puede impedir los demás: cada uno que falla se anota en el registro y se sigue.

    Args:
        cliente: cliente Docker (por defecto se conecta con un timeout corto).
        ruta_usos: archivo con el último uso de cada imagen derivada.
        limites: límites de `[disco]`; si es None se leen de config.toml.
        protegidas: imágenes derivadas que no se pueden borrar (la de la corrida en curso).

    Returns:
        `{"contenedores", "construcciones", "capas", "capas_bytes", "imagenes",
        "imagenes_tope"}`, o `{}` si Docker no respondió. `imagenes` son las
        derivadas borradas (por falta de uso o por el tope); `imagenes_tope`, solo las
        borradas por el tope.
    """
    propio = cliente is None
    ruta_usos = ruta_usos or RUTA_USOS
    try:
        if propio:
            import docker

            cliente = docker.from_env(timeout=TIMEOUT_DOCKER_S)
            cliente.ping()
        resultado = {"contenedores": eliminar_contenedores_huerfanos(cliente)}
        resultado.update(_limpiar_el_resto(cliente, ruta_usos, limites, protegidas))
    except Exception:  # noqa: BLE001 — sin Docker no hay nada que limpiar
        return {}
    finally:
        if propio and cliente is not None:
            with contextlib.suppress(Exception):
                cliente.close()
    borradas = resultado["imagenes"]
    if borradas:
        usos = leer_usos(ruta_usos)
        with contextlib.suppress(OSError):
            escribir_json_atomico(
                ruta_usos, {k: v for k, v in usos.items() if k not in borradas}
            )
    return resultado


def _limpiar_el_resto(
    cliente: Any,
    ruta_usos: Path,
    limites: LimitesDisco | None,
    protegidas: Collection[str],
) -> dict:
    """Los pasos 2 a 5 de `limpiar_al_iniciar`; cada uno falla sin detener los demás."""
    limites = limites or leer_limites_disco()
    usos = leer_usos(ruta_usos)
    construcciones = _intentar(
        "contenedores de construcción",
        lambda: eliminar_contenedores_construccion(cliente),
        0,
    )
    capas, capas_bytes = _intentar(
        "capas sin etiqueta", lambda: eliminar_capas_sin_etiqueta(cliente), (0, 0)
    )
    imagenes = _intentar(
        "imágenes sin uso", lambda: eliminar_imagenes_sin_uso(cliente, usos), []
    )
    tope = limites.tope_imagenes_derivadas_bytes
    imagenes_tope: list[str] = []
    if tope is not None:
        imagenes_tope = _intentar(
            "tope de imágenes",
            lambda: aplicar_tope_imagenes(
                cliente,
                {k: v for k, v in usos.items() if k not in imagenes},
                tope,
                protegidas=protegidas,
            ),
            [],
        )
    return {
        "construcciones": construcciones,
        "capas": capas,
        "capas_bytes": capas_bytes,
        "imagenes": [*imagenes, *imagenes_tope],
        "imagenes_tope": imagenes_tope,
    }


def _intentar(nombre: str, paso: Callable[[], Any], defecto: Any) -> Any:
    """Corre un paso de la limpieza; si falla lo anota y devuelve `defecto`."""
    try:
        return paso()
    except Exception as exc:  # noqa: BLE001 — un paso que falla no detiene los demás
        registro.warning("Limpieza del sandbox: falló el paso «%s»: %s", nombre, exc)
        return defecto


def _filtro_label(etiqueta: dict[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in etiqueta.items()]


def _entero(valor: Any) -> int:
    return (
        int(valor)
        if isinstance(valor, (int, float)) and not isinstance(valor, bool)
        else 0
    )


def _capas(cliente: Any, imagen: Any) -> list[str]:
    """Capas (`RootFS.Layers`) de una imagen; el listado de Docker no las trae, se inspecciona."""
    rootfs = imagen.attrs.get("RootFS")
    if not isinstance(rootfs, dict):
        try:
            rootfs = cliente.images.get(imagen.id).attrs.get("RootFS")
        except Exception:  # noqa: BLE001 — sin capas se cuenta la imagen entera
            return []
    capas = rootfs.get("Layers") if isinstance(rootfs, dict) else None
    return [str(c) for c in capas] if isinstance(capas, list) else []


def _tamano_propio(
    cliente: Any, imagen: Any, bases: list[tuple[int, list[str]]]
) -> int:
    """Bytes que la imagen ocupa aparte de los de su imagen base (que comparte con las demás)."""
    total = _entero(imagen.attrs.get("Size"))
    capas = _capas(cliente, imagen)
    comunes = [
        tamano
        for tamano, capas_base in bases
        if capas_base and capas[: len(capas_base)] == capas_base
    ]
    return max(total - max(comunes, default=0), 0)


def _es_imagen_req(etiqueta: str) -> bool:
    """True si la etiqueta es una imagen derivada (`req-…`, `node-…`, `java-…` o `browser-…`)."""
    return any(
        etiqueta.startswith(f"{REPOSITORIO}:{prefijo}")
        for prefijo in PREFIJOS_DERIVADAS
    )


def _segundos(fecha: Any) -> float | None:
    """Convierte una fecha de Docker a segundos.

    Docker la da como texto («2026-10-18T10:00:00.123456789Z») al inspeccionar y como
    segundos desde la época en el listado de imágenes.
    """
    if isinstance(fecha, (int, float)) and not isinstance(fecha, bool):
        return float(fecha)
    if not isinstance(fecha, str):
        return None
    # Docker da nanosegundos; datetime solo acepta hasta microsegundos.
    texto = _NANOSEGUNDOS.sub(r"\1", fecha.strip()).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(texto).timestamp()
    except ValueError:
        return None

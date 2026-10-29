"""Paso 1 del sandbox (con red): imagen base e imagen derivada por proyecto.

Cada lenguaje tiene su imagen base (#169): `qagent-sandbox:base` para Python,
`qagent-sandbox:node` para JavaScript y TypeScript y `qagent-sandbox:java` para Java.
El adaptador del lenguaje dice cuál usa (`entorno_sandbox().imagen`) y aquí está su
receta: el Dockerfile y cómo se instalan las dependencias del proyecto (pip, `npm ci`,
`mvn dependency:go-offline` o el equivalente de Gradle) en una imagen derivada. Solo
esa construcción tiene red; la imagen derivada se reutiliza mientras no cambien los
archivos de dependencias. La imagen de un lenguaje se construye solo cuando un proyecto
de ese lenguaje la pide.

Construir una imagen puede tardar muchos minutos (por ejemplo, un requirements.txt con
torch u opencv). Si se pasa `avanzar`, el log de Docker se lee en streaming y cada paso
útil se traduce a un texto para personas («Descargando torch (821.0 MB)») que la corrida
reenvía al Monitor. Sin `avanzar`, la construcción es la de siempre (`images.build`).
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker
from docker.errors import APIError, BuildError, ImageNotFound

from qagent.sandbox.cliente import obtener_cliente
from qagent.sandbox.modelos import (
    IMAGEN_BASE,
    IMAGEN_JAVA,
    IMAGEN_NODE,
    REPOSITORIO,
    ConstruccionCancelada,
    ErrorConstruccionImagen,
    ImagenNoEncontrada,
)

registro = logging.getLogger(__name__)

#: Recibe un texto para personas con el paso actual de la construcción.
Avance = Callable[[str], None]

_CARPETA = Path(__file__).parent
DOCKERFILE_BASE = _CARPETA / "Dockerfile"
DOCKERFILE_NODE = _CARPETA / "Dockerfile.node"
DOCKERFILE_JAVA = _CARPETA / "Dockerfile.java"
#: Proyecto de calentamiento y script de Gradle que usa la imagen de Java.
RECURSOS_JAVA = _CARPETA / "java"

DOCKERFILE_DERIVADO = f"""\
FROM {IMAGEN_BASE}
USER root
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
USER sandbox
"""

#: Textos de cada fase (los ve la persona en el Monitor).
AVISO_BASE = (
    "Construyendo el entorno aislado base: solo la primera vez en este equipo "
    "y necesita internet"
)
AVISO_DEPENDENCIAS = (
    "Instalando las dependencias del proyecto (requirements.txt): la primera vez "
    "puede tardar varios minutos"
)
AVISO_CONSTRUYENDO = "Construyendo la imagen Docker del proyecto"
AVISO_DEPENDENCIAS_LISTAS = (
    "Dependencias instaladas; Docker continúa preparando la imagen"
)
AVISO_GUARDANDO = "Guardando la imagen Docker para reutilizarla en próximas corridas"
AVISO_LISTO = "Dependencias instaladas en el entorno aislado"

_COLECTANDO = re.compile(r"^Collecting\s+([A-Za-z0-9][A-Za-z0-9_.\-]*)")
_DESCARGANDO = re.compile(r"^Downloading\s+(\S+?)(?:\s+\(([^)]+)\))?\s*$")
_INSTALANDO = re.compile(r"^Installing collected packages:\s*(.+)$")
_INSTALADO = re.compile(r"^Successfully installed\b")
# npm («added 57 packages in 3s»), Maven y Gradle al terminar de bajar dependencias.
_NPM_INSTALADO = re.compile(r"^added\s+(\d+)\s+packages?\b")
_BUILD_EXITOSO = re.compile(r"^(?:\[INFO\]\s+)?BUILD SUCCESS(?:FUL)?\b")

_CARPETA_DEPENDENCIAS = "/tmp/qagent-deps"


@dataclass(frozen=True)
class Dependencias:
    """Cómo se instalan en la imagen derivada las dependencias de un tipo de proyecto.

    Atributos:
        nombre: texto para personas («package-lock.json», «pom.xml»...).
        obligatorios: el proyecto usa esta forma si tiene al menos uno de estos archivos.
        opcionales: archivos que se copian también si existen (lockfiles, settings).
        dockerfile: arma el Dockerfile derivado a partir de los archivos presentes.
    """

    nombre: str
    obligatorios: tuple[str, ...]
    opcionales: tuple[str, ...]
    dockerfile: Callable[[str, list[str]], str]


@dataclass(frozen=True)
class RecetaImagen:
    """Receta de una imagen base del sandbox y de sus imágenes derivadas.

    Atributos:
        imagen: etiqueta de la imagen base (la que pide el adaptador).
        dockerfile: Dockerfile de la imagen base.
        recursos: carpetas que se copian al contexto de build junto al Dockerfile.
        prefijo: prefijo de la etiqueta de las imágenes derivadas (`req-`, `node-`...).
        dependencias: formas de instalar las dependencias, en orden de preferencia.
    """

    imagen: str
    dockerfile: Path
    recursos: tuple[Path, ...]
    prefijo: str
    dependencias: tuple[Dependencias, ...]


def _dockerfile_pip(base: str, archivos: list[str]) -> str:
    """Dockerfile derivado de Python (el de siempre)."""
    return DOCKERFILE_DERIVADO


def _copiar(archivos: list[str]) -> str:
    """Una línea COPY por archivo, conservando su ruta relativa."""
    return "".join(
        f"COPY {archivo} {_CARPETA_DEPENDENCIAS}/{archivo}\n" for archivo in archivos
    )


def _dockerfile_npm(base: str, archivos: list[str]) -> str:
    """Dependencias de Node en `/work/node_modules` (fuera del montaje del proyecto).

    Con `package-lock.json` se usa `npm ci` (versiones exactas); sin él, `npm install`
    sin escribir lockfile.
    """
    instalar = (
        "npm ci" if "package-lock.json" in archivos else "npm install --no-package-lock"
    )
    return (
        f"FROM {base}\n"
        "USER root\n"
        f"{_copiar(archivos)}"
        f"RUN cd {_CARPETA_DEPENDENCIAS} && {instalar} --no-audit --no-fund \\\n"
        f"    && mv node_modules /work/node_modules \\\n"
        f"    && cd / && rm -rf {_CARPETA_DEPENDENCIAS} && npm cache clean --force\n"
        "USER sandbox\n"
    )


def _dockerfile_maven(base: str, archivos: list[str]) -> str:
    """Dependencias y plugins de Maven en el repositorio local de la imagen."""
    return (
        f"FROM {base}\n"
        "USER root\n"
        f"{_copiar(archivos)}"
        f"RUN cd {_CARPETA_DEPENDENCIAS} && MAVEN_OPTS= mvn dependency:go-offline \\\n"
        f"    && cd / && rm -rf {_CARPETA_DEPENDENCIAS}\n"
        "USER sandbox\n"
    )


def _dockerfile_gradle(base: str, archivos: list[str]) -> str:
    """Dependencias de Gradle en una caché de solo lectura (`GRADLE_RO_DEP_CACHE`).

    Gradle no tiene `go-offline`: `java/resolver.gradle` resuelve todas las
    configuraciones. La caché se copia sin sus archivos de bloqueo, como pide Gradle.
    """
    return (
        f"FROM {base}\n"
        "USER root\n"
        f"{_copiar(archivos)}"
        f"RUN cd {_CARPETA_DEPENDENCIAS} \\\n"
        "    && GRADLE_USER_HOME=/tmp/qagent-gradle gradle --quiet \\\n"
        "       --init-script /opt/qagent/java/resolver.gradle qagentResolverDependencias \\\n"
        "    && cp -r /tmp/qagent-gradle/caches/modules-2 /opt/qagent/gradle-ro/ \\\n"
        "    && find /opt/qagent/gradle-ro -name '*.lock' -delete \\\n"
        "    && rm -f /opt/qagent/gradle-ro/modules-2/gc.properties \\\n"
        f"    && cd / && rm -rf {_CARPETA_DEPENDENCIAS} /tmp/qagent-gradle\n"
        "USER sandbox\n"
    )


RECETAS: dict[str, RecetaImagen] = {
    IMAGEN_BASE: RecetaImagen(
        imagen=IMAGEN_BASE,
        dockerfile=DOCKERFILE_BASE,
        recursos=(),
        prefijo="req-",
        dependencias=(
            Dependencias(
                "requirements.txt", ("requirements.txt",), (), _dockerfile_pip
            ),
        ),
    ),
    IMAGEN_NODE: RecetaImagen(
        imagen=IMAGEN_NODE,
        dockerfile=DOCKERFILE_NODE,
        recursos=(),
        prefijo="node-",
        dependencias=(
            Dependencias(
                "package.json",
                ("package.json",),
                ("package-lock.json",),
                _dockerfile_npm,
            ),
        ),
    ),
    IMAGEN_JAVA: RecetaImagen(
        imagen=IMAGEN_JAVA,
        dockerfile=DOCKERFILE_JAVA,
        recursos=(RECURSOS_JAVA,),
        prefijo="java-",
        dependencias=(
            Dependencias("pom.xml", ("pom.xml",), (), _dockerfile_maven),
            Dependencias(
                "build.gradle",
                ("build.gradle", "build.gradle.kts"),
                (
                    "settings.gradle",
                    "settings.gradle.kts",
                    "gradle.properties",
                    "gradle/libs.versions.toml",
                ),
                _dockerfile_gradle,
            ),
        ),
    ),
}


def receta_de(imagen: str) -> RecetaImagen:
    """Receta de una imagen base del sandbox.

    Raises:
        ValueError: si la imagen no es una imagen base conocida.
    """
    try:
        return RECETAS[imagen]
    except KeyError:
        conocidas = ", ".join(RECETAS)
        raise ValueError(
            f"'{imagen}' no es una imagen base del sandbox ({conocidas})."
        ) from None


def construir_imagen_base(
    cliente: docker.DockerClient | None = None,
    avanzar: Avance | None = None,
    imagen: str = IMAGEN_BASE,
) -> str:
    """Construye una imagen base del sandbox a partir de su Dockerfile.

    El contexto de build es una carpeta temporal que solo contiene el Dockerfile y los
    recursos de la receta (nunca el proyecto del usuario).

    Args:
        cliente: cliente Docker; si es None se crea uno con `obtener_cliente()`.
        avanzar: recibe el avance de la construcción en textos para personas.
        imagen: imagen base que pide el adaptador (`entorno_sandbox().imagen`).

    Returns:
        Etiqueta de la imagen base.

    Raises:
        ValueError: si `imagen` no es una imagen base conocida.
        ErrorConstruccionImagen: si la construcción falla.
    """
    receta = receta_de(imagen)
    cliente = cliente or obtener_cliente()
    _avisar(avanzar, AVISO_BASE)
    contexto = Path(tempfile.mkdtemp(prefix="qagent-base-"))
    try:
        shutil.copyfile(receta.dockerfile, contexto / "Dockerfile")
        for recurso in receta.recursos:
            shutil.copytree(recurso, contexto / recurso.name)
        _construir(
            cliente,
            contexto,
            receta.imagen,
            "No se pudo construir la imagen base",
            avanzar,
        )
    finally:
        shutil.rmtree(contexto, ignore_errors=True)
    return receta.imagen


def etiqueta_para_requirements(contenido: bytes) -> str:
    """Devuelve la etiqueta de la imagen derivada según el hash del requirements.txt.

    Args:
        contenido: bytes del archivo requirements.txt.

    Returns:
        Etiqueta con la forma `qagent-sandbox:req-<sha256[:12]>`.
    """
    return f"{REPOSITORIO}:req-{hashlib.sha256(contenido).hexdigest()[:12]}"


def etiqueta_para_dependencias(prefijo: str, archivos: Mapping[str, bytes]) -> str:
    """Etiqueta de una imagen derivada según sus archivos de dependencias.

    El hash cubre el nombre y el contenido de cada archivo: si cambia uno, cambia la
    etiqueta y la imagen se vuelve a construir. Con solo un requirements.txt da la
    misma etiqueta que `etiqueta_para_requirements` (las imágenes ya construidas
    siguen sirviendo).

    Args:
        prefijo: prefijo de la receta (`req-`, `node-`, `java-`).
        archivos: ruta relativa → contenido de cada archivo copiado.

    Returns:
        Etiqueta con la forma `qagent-sandbox:<prefijo><sha256[:12]>`.
    """
    if prefijo == "req-" and list(archivos) == ["requirements.txt"]:
        return etiqueta_para_requirements(archivos["requirements.txt"])
    huella = hashlib.sha256()
    for nombre in sorted(archivos):
        huella.update(nombre.encode("utf-8") + b"\0" + archivos[nombre] + b"\0")
    return f"{REPOSITORIO}:{prefijo}{huella.hexdigest()[:12]}"


def preparar_imagen(
    ruta_proyecto: str | Path,
    cliente: docker.DockerClient | None = None,
    avanzar: Avance | None = None,
    imagen: str = IMAGEN_BASE,
) -> str:
    """Prepara la imagen con las dependencias del proyecto (paso 1, con red).

    Si el proyecto tiene archivos de dependencias de su lenguaje (requirements.txt,
    package.json, pom.xml, build.gradle), construye (o reutiliza) una imagen derivada
    de la base que los instala. El contexto de build solo contiene esos archivos: nunca
    el código del proyecto ni su `.env`. Si la imagen ya existe no se construye nada ni
    se informa avance.

    Args:
        ruta_proyecto: carpeta raíz del proyecto del usuario.
        cliente: cliente Docker; si es None se crea uno con `obtener_cliente()`.
        avanzar: recibe el avance de la construcción en textos para personas.
        imagen: imagen base que pide el adaptador (`entorno_sandbox().imagen`).

    Returns:
        Etiqueta de la imagen a usar en el paso 2.

    Raises:
        ValueError: si `imagen` no es una imagen base conocida.
        ImagenNoEncontrada: si no existe la imagen base.
        ErrorConstruccionImagen: si falla la instalación de dependencias.
    """
    receta = receta_de(imagen)
    cliente = cliente or obtener_cliente()
    if not _imagen_existe(cliente, receta.imagen):
        raise ImagenNoEncontrada(
            f"No existe la imagen base '{receta.imagen}'. "
            "Constrúyela con construir_imagen_base()."
        )

    encontrada = _buscar_dependencias(Path(ruta_proyecto).resolve(), receta)
    if encontrada is None:
        return receta.imagen
    forma, archivos = encontrada

    etiqueta = etiqueta_para_dependencias(receta.prefijo, archivos)
    if _imagen_existe(cliente, etiqueta):
        return etiqueta

    _avisar(avanzar, AVISO_CONSTRUYENDO)
    _avisar(avanzar, aviso_dependencias(forma.nombre))
    contexto = Path(tempfile.mkdtemp(prefix="qagent-req-"))
    try:
        for nombre, contenido in archivos.items():
            destino = contexto / nombre
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(contenido)
        (contexto / "Dockerfile").write_text(
            forma.dockerfile(receta.imagen, list(archivos)), encoding="utf-8"
        )
        _construir(
            cliente,
            contexto,
            etiqueta,
            f"No se pudieron instalar las dependencias del {forma.nombre} del proyecto",
            avanzar,
        )
    finally:
        shutil.rmtree(contexto, ignore_errors=True)
    _avisar(avanzar, AVISO_LISTO)
    return etiqueta


def asegurar_imagen(
    ruta_proyecto: str | Path,
    imagen: str = IMAGEN_BASE,
    cliente: docker.DockerClient | None = None,
    avanzar: Avance | None = None,
) -> str:
    """`preparar_imagen`, construyendo antes la imagen base si todavía no existe.

    Así la imagen de un lenguaje solo se construye la primera vez que un proyecto de
    ese lenguaje la necesita (una vez por PC; necesita internet).
    """
    cliente = cliente or obtener_cliente()
    try:
        return preparar_imagen(ruta_proyecto, cliente, avanzar, imagen)
    except ImagenNoEncontrada:
        construir_imagen_base(cliente, avanzar, imagen)
        return preparar_imagen(ruta_proyecto, cliente, avanzar, imagen)


def aviso_dependencias(nombre: str) -> str:
    """Texto del Monitor mientras se instalan las dependencias de `nombre`."""
    return (
        f"Instalando las dependencias del proyecto ({nombre}): la primera vez "
        "puede tardar varios minutos"
    )


def _buscar_dependencias(
    raiz: Path, receta: RecetaImagen
) -> tuple[Dependencias, dict[str, bytes]] | None:
    """Primera forma de la receta cuyos archivos obligatorios tiene el proyecto."""
    for forma in receta.dependencias:
        if not any((raiz / nombre).is_file() for nombre in forma.obligatorios):
            continue
        archivos = {
            nombre: (raiz / nombre).read_bytes()
            for nombre in (*forma.obligatorios, *forma.opcionales)
            if (raiz / nombre).is_file()
        }
        return forma, archivos
    return None


def describir_linea(linea: str) -> str | None:
    """Traduce una línea del log de construcción a un texto para personas.

    Se informan los pasos útiles de pip, el final de npm, Maven y Gradle y las fases
    de construcción/guardado de Docker; rutas, hashes y advertencias sin acción para
    la persona devuelven None.

    Args:
        linea: una línea del log de `docker build`.

    Returns:
        Texto como «Descargando torch (821.0 MB)», o None si la línea no aporta.
    """
    texto = linea.strip()
    if coincidencia := _DESCARGANDO.match(texto):
        archivo = coincidencia.group(1).rstrip("/").rsplit("/", 1)[-1]
        nombre = re.split(r"-\d", archivo, maxsplit=1)[0]
        tamano = coincidencia.group(2)
        return f"Descargando {nombre}" + (f" ({tamano})" if tamano else "")
    if coincidencia := _COLECTANDO.match(texto):
        return f"Preparando {coincidencia.group(1)}"
    if coincidencia := _INSTALANDO.match(texto):
        paquetes = [p for p in coincidencia.group(1).split(",") if p.strip()]
        cantidad = len(paquetes)
        return f"Instalando {cantidad} {'paquete' if cantidad == 1 else 'paquetes'}"
    if coincidencia := _NPM_INSTALADO.match(texto):
        cantidad = int(coincidencia.group(1))
        return f"Instalados {cantidad} {'paquete' if cantidad == 1 else 'paquetes'}"
    if _INSTALADO.match(texto) or _BUILD_EXITOSO.match(texto):
        return AVISO_DEPENDENCIAS_LISTAS
    texto_minusculas = texto.lower()
    if any(
        marca in texto_minusculas
        for marca in (
            "exporting to image",
            "exporting layers",
            "writing image sha256:",
            "successfully built ",
            "successfully tagged ",
        )
    ):
        return AVISO_GUARDANDO
    return None


def _imagen_existe(cliente: docker.DockerClient, etiqueta: str) -> bool:
    """Indica si la imagen existe localmente."""
    try:
        cliente.images.get(etiqueta)
    except ImageNotFound:
        return False
    return True


def _construir(
    cliente: docker.DockerClient,
    contexto: Path,
    etiqueta: str,
    mensaje: str,
    avanzar: Avance | None = None,
) -> None:
    """Construye una imagen y traduce los errores de Docker a `ErrorConstruccionImagen`.

    Con `avanzar`, lee el log en streaming (API de bajo nivel) para informar el avance.
    """
    if avanzar is not None:
        _construir_con_avance(cliente, contexto, etiqueta, mensaje, avanzar)
        return
    try:
        cliente.images.build(path=str(contexto), tag=etiqueta, rm=True, forcerm=True)
    except BuildError as exc:
        raise ErrorConstruccionImagen(
            f"{mensaje}: {exc.msg}", _texto_log(exc.build_log)
        ) from exc
    except APIError as exc:
        raise ErrorConstruccionImagen(f"{mensaje}: {exc.explanation}") from exc


def _construir_con_avance(
    cliente: docker.DockerClient,
    contexto: Path,
    etiqueta: str,
    mensaje: str,
    avanzar: Avance,
) -> None:
    """`docker build` leyendo el log a medida que llega; cada paso útil va a `avanzar`."""
    log: list[str] = []
    partes = None
    try:
        partes = cliente.api.build(
            path=str(contexto), tag=etiqueta, rm=True, forcerm=True, decode=True
        )
        for parte in partes:
            if parte.get("error"):
                log.append(str(parte["error"]))
                raise ErrorConstruccionImagen(
                    f"{mensaje}: {str(parte['error']).strip()}", "".join(log)
                )
            texto = parte.get("stream")
            if not texto:
                continue
            log.append(texto)
            for linea in texto.splitlines():
                descripcion = describir_linea(linea)
                if descripcion:
                    _avisar(avanzar, descripcion)
    except ConstruccionCancelada:
        # #148: cerrar el log corta la conexión con Docker en vez de esperar el final.
        cerrar = getattr(partes, "close", None)
        if cerrar is not None:
            cerrar()
        raise
    except APIError as exc:
        raise ErrorConstruccionImagen(
            f"{mensaje}: {exc.explanation}", "".join(log)
        ) from exc


def _avisar(avanzar: Avance | None, texto: str) -> None:
    """Informa el avance sin dejar que un fallo de quien escucha corte la construcción."""
    if avanzar is None:
        return
    try:
        avanzar(texto)
    except ConstruccionCancelada:
        raise
    except Exception:  # noqa: BLE001 - el avance es solo informativo
        registro.warning(
            "No se pudo informar el avance de la construcción.", exc_info=True
        )


def _texto_log(build_log: Iterable[dict[str, Any]]) -> str:
    """Une las líneas del log de build de Docker en un solo texto."""
    partes = []
    for entrada in build_log:
        texto = entrada.get("stream") or entrada.get("error") or ""
        partes.append(texto)
    return "".join(partes)

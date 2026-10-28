"""Librerías del sistema que necesitan las dependencias del proyecto (issue 142).

`pip` instala los paquetes de Python, pero muchos enlazan librerías nativas del sistema
(`opencv-python` necesita `libGL.so.1`, `soundfile` necesita `libsndfile.so.1`...) que
la imagen `python:3.11-slim` no trae. Si falta una, el entorno parece listo pero las
pruebas fallan al importar.

Sobre la imagen de dependencias (`req-<hash>`, de `preparar_imagen`) se construye una
imagen final que comprueba el entorno: importa las dependencias instaladas
(`verificar_entorno.py`) y guarda las librerías que faltan. Las que están en la tabla se
instalan con `apt-get` y se vuelve a comprobar, hasta `MAX_RONDAS`. Las que no se pueden
resolver se devuelven para avisarlas antes de gastar tokens.

La imagen final se llama `req-<hash>-sis<versión>`: la versión cambia con la tabla y el
script, así que cambiar cualquiera de los dos la reconstruye (sin reinstalar `pip`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qagent.sandbox.imagen import Avance, _avisar, _construir, _imagen_existe
from qagent.sandbox.modelos import IMAGEN_BASE, ErrorConstruccionImagen

registro = logging.getLogger(__name__)

#: Librería compartida → paquete de Debian 13 (trixie), la base de `python:3.11-slim`.
#: En trixie varios paquetes llevan el sufijo `t64` (por ejemplo, `libglib2.0-0t64`):
#: los nombres anteriores ya no existen.
TABLA_LIBRERIAS: dict[str, str] = {
    "libGL.so.1": "libgl1",
    "libEGL.so.1": "libegl1",
    "libglib-2.0.so.0": "libglib2.0-0t64",
    "libgthread-2.0.so.0": "libglib2.0-0t64",
    "libgobject-2.0.so.0": "libglib2.0-0t64",
    "libSM.so.6": "libsm6",
    "libICE.so.6": "libice6",
    "libXext.so.6": "libxext6",
    "libXrender.so.1": "libxrender1",
    "libX11.so.6": "libx11-6",
    "libxcb.so.1": "libxcb1",
    "libgomp.so.1": "libgomp1",
    "libsndfile.so.1": "libsndfile1",
    "libzbar.so.0": "libzbar0t64",
    "libmagic.so.1": "libmagic1t64",
    "libcairo.so.2": "libcairo2",
    "libpq.so.5": "libpq5",
    "libjpeg.so.62": "libjpeg62-turbo",
    "libpng16.so.16": "libpng16-16t64",
    "libfontconfig.so.1": "libfontconfig1",
    "libfreetype.so.6": "libfreetype6",
    "libportaudio.so.2": "libportaudio2",
    "libasound.so.2": "libasound2t64",
}

#: Consejos por paquete de Python cuando una librería no se pudo resolver.
SUGERENCIAS: dict[str, str] = {
    "opencv-python": "si no necesitas ventanas, usa opencv-python-headless, que no "
    "requiere librerías gráficas",
    "opencv-contrib-python": "si no necesitas ventanas, usa "
    "opencv-contrib-python-headless, que no requiere librerías gráficas",
}

SCRIPT = Path(__file__).with_name("verificar_entorno.py")
RUTA_INFORME = "/opt/qagent/entorno.json"
#: Lo que se guarda si la comprobación misma falla: sin faltantes conocidas.
_INFORME_VACIO = '{"version": 1, "revisados": 0, "faltantes": [], "error": true}'
MAX_RONDAS = 3

AVISO_COMPROBANDO = (
    "Comprobando que las dependencias del proyecto se pueden importar en el entorno "
    "aislado"
)
AVISO_LISTAS = "Librerías del sistema listas en el entorno aislado"
#: Inicio del aviso que nombra los paquetes que se instalan en cada ronda.
AVISO_INSTALANDO = "Instalando librerías del sistema que necesitan las dependencias"
#: Así empieza el aviso de una librería sin resolver (el Monitor lo destaca).
PREFIJO_FALTANTE = "Falta la librería del sistema"


def _version() -> str:
    """Huella de la tabla y del script: si cambian, la imagen final se reconstruye."""
    contenido = (
        json.dumps(TABLA_LIBRERIAS, sort_keys=True).encode() + SCRIPT.read_bytes()
    )
    return hashlib.sha256(contenido).hexdigest()[:8]


VERSION_LIBRERIAS = _version()


@dataclass
class EntornoVerificado:
    """Imagen lista para las pruebas y las librerías del sistema que no se resolvieron."""

    imagen: str
    faltantes: list[dict[str, Any]] = field(default_factory=list)


def etiqueta_final(imagen_dependencias: str) -> str:
    """`qagent-sandbox:req-<hash>` → `qagent-sandbox:req-<hash>-sis<versión>`."""
    return f"{imagen_dependencias}-sis{VERSION_LIBRERIAS}"


def _sin_version(libreria: str) -> str:
    """`libGL.so.1` → `libGL.so`, para reconocer otra versión de la misma librería."""
    return re.sub(r"\.so(?:\.[0-9]+)*$", ".so", libreria)


_POR_NOMBRE = {_sin_version(lib): paquete for lib, paquete in TABLA_LIBRERIAS.items()}


def paquete_del_sistema(libreria: str) -> str | None:
    """El paquete de Debian que instala la librería, o None si no está en la tabla."""
    return TABLA_LIBRERIAS.get(libreria) or _POR_NOMBRE.get(_sin_version(libreria))


def paquetes_para(faltantes: list[dict[str, Any]]) -> set[str]:
    """Paquetes del sistema que resuelven las librerías faltantes conocidas."""
    paquetes = (paquete_del_sistema(f["libreria"]) for f in faltantes)
    return {p for p in paquetes if p}


def dockerfile_final(imagen_dependencias: str, paquetes: set[str]) -> str:
    """Dockerfile de la imagen final: paquetes del sistema y comprobación del entorno.

    Los paquetes salen de la tabla (nunca del proyecto). Cada uno se instala por
    separado: si uno no existe, los demás siguen y la comprobación lo informa.
    """
    lineas = [f"FROM {imagen_dependencias}", "USER root"]
    if paquetes:
        lista = " ".join(sorted(paquetes))
        lineas.append(
            "RUN apt-get update"
            f" && for p in {lista}; do"
            ' apt-get install -y --no-install-recommends "$p"'
            ' || echo "QAgent: no se pudo instalar $p"; done'
            " && rm -rf /var/lib/apt/lists/*"
        )
    lineas += [
        f"COPY {SCRIPT.name} /opt/qagent/{SCRIPT.name}",
        (
            f"RUN python /opt/qagent/{SCRIPT.name} {RUTA_INFORME}"
            f" || echo '{_INFORME_VACIO}' > {RUTA_INFORME}"
        ),
        "USER sandbox",
    ]
    return "\n".join(lineas) + "\n"


def asegurar_librerias_sistema(
    imagen_dependencias: str,
    cliente: Any,
    avanzar: Avance | None = None,
) -> EntornoVerificado:
    """Devuelve la imagen final del proyecto, con las librerías del sistema resueltas.

    Si la imagen final ya existe, solo lee su informe. La imagen base (proyecto sin
    requirements.txt) no se comprueba: solo trae las herramientas de prueba.

    Nunca impide la corrida: si no se puede construir o leer, devuelve la imagen de
    dependencias sin faltantes y deja un aviso en el registro.
    """
    if imagen_dependencias == IMAGEN_BASE:
        return EntornoVerificado(imagen_dependencias)
    final = etiqueta_final(imagen_dependencias)
    try:
        if not _imagen_existe(cliente, final):
            _construir_con_rondas(cliente, imagen_dependencias, final, avanzar)
        informe = leer_informe(cliente, final)
    except ErrorConstruccionImagen as error:
        registro.warning(
            "No se pudo comprobar el entorno de %s: %s", imagen_dependencias, error
        )
        return EntornoVerificado(imagen_dependencias)
    return EntornoVerificado(final, describir_faltantes(informe.get("faltantes") or []))


def _construir_con_rondas(
    cliente: Any, imagen_dependencias: str, final: str, avanzar: Avance | None
) -> None:
    """Construye la imagen final y agrega paquetes del sistema hasta que no falte nada
    conocido (o se acaben las rondas). Si una ronda con paquetes falla, queda la anterior.
    """
    _avisar(avanzar, AVISO_COMPROBANDO)
    paquetes: set[str] = set()
    for ronda in range(MAX_RONDAS):
        try:
            _construir_final(cliente, imagen_dependencias, final, paquetes)
        except ErrorConstruccionImagen:
            if ronda == 0:
                raise
            registro.warning("No se pudieron instalar %s", ", ".join(sorted(paquetes)))
            break
        nuevos = paquetes_para(leer_informe(cliente, final).get("faltantes") or [])
        nuevos -= paquetes
        if not nuevos:
            break
        paquetes |= nuevos
        _avisar(
            avanzar,
            f"{AVISO_INSTALANDO}: " + ", ".join(sorted(nuevos)),
        )
    if paquetes:
        _avisar(avanzar, AVISO_LISTAS)


def _construir_final(
    cliente: Any, imagen_dependencias: str, final: str, paquetes: set[str]
) -> None:
    contexto = Path(tempfile.mkdtemp(prefix="qagent-sis-"))
    try:
        shutil.copyfile(SCRIPT, contexto / SCRIPT.name)
        (contexto / "Dockerfile").write_text(
            dockerfile_final(imagen_dependencias, paquetes), encoding="utf-8"
        )
        _construir(
            cliente,
            contexto,
            final,
            "No se pudo comprobar el entorno aislado del proyecto",
        )
    finally:
        shutil.rmtree(contexto, ignore_errors=True)


def leer_informe(cliente: Any, imagen: str) -> dict[str, Any]:
    """Lee el informe de la comprobación guardado en la imagen (sin red).

    Un informe ilegible cuenta como «sin faltantes»: no es motivo para frenar la corrida.
    """
    try:
        salida = cliente.containers.run(
            imagen,
            ["cat", RUTA_INFORME],
            network_mode="none",
            remove=True,
        )
        texto = salida.decode("utf-8") if isinstance(salida, bytes) else str(salida)
        informe = json.loads(texto)
    except Exception as error:  # noqa: BLE001 — el informe es solo informativo
        registro.warning(
            "No se pudo leer el informe del entorno de %s: %s", imagen, error
        )
        return {"faltantes": []}
    return informe if isinstance(informe, dict) else {"faltantes": []}


def describir_faltantes(faltantes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada librería faltante con su paquete del sistema y un mensaje para personas."""
    descritas = []
    for faltante in faltantes:
        libreria = str(faltante.get("libreria") or "")
        if not libreria:
            continue
        paquetes_python = [str(p) for p in faltante.get("paquetes_python") or []]
        modulos = [str(m) for m in faltante.get("modulos") or []]
        paquete = paquete_del_sistema(libreria)
        descritas.append(
            {
                "libreria": libreria,
                "modulos": modulos,
                "paquetes_python": paquetes_python,
                "paquete_sistema": paquete,
                "mensaje": mensaje_faltante(
                    libreria, modulos, paquetes_python, paquete
                ),
            }
        )
    return descritas


def mensaje_faltante(
    libreria: str,
    modulos: list[str],
    paquetes_python: list[str],
    paquete_sistema: str | None,
) -> str:
    """«Falta la librería del sistema libfoo.so.1, que necesita foo…» para el Monitor."""
    quien = ", ".join(paquetes_python) or ", ".join(modulos) or "una dependencia"
    causa = (
        f"no se pudo instalar el paquete {paquete_sistema}"
        if paquete_sistema
        else "QAgent no sabe qué paquete del sistema la instala"
    )
    texto = (
        f"{PREFIJO_FALTANTE} {libreria}, que necesita {quien} ({causa}). "
        f"El código que importa {', '.join(modulos) or quien} no se podrá probar en el "
        "entorno aislado."
    )
    consejos = [SUGERENCIAS[p] for p in paquetes_python if p in SUGERENCIAS]
    if consejos:
        texto += " Sugerencia: " + "; ".join(consejos) + "."
    return texto

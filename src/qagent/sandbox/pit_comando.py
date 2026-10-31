"""Construcción del comando PIT acotado; no ejecuta procesos ni modifica POM (#180)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from qagent.lenguajes.base import ComandoSandbox

IDENTIFICADOR = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*\Z")
POM_TEMPORAL = "/work/proyecto/.qagent-pit.xml"
DIRECTORIO_INFORME = "/out/pit"


def comando_pit(modulo: str, funciones: list[str]) -> ComandoSandbox:
    """Construye un comando Maven offline limitado a una clase y sus métodos.

    Args:
        modulo: ruta Maven/Gradle estándar src/main/java/paquete/Clase.java.
            En esta primera etapa no se admiten proyectos multimódulo ni clases
            anidadas. La ejecución deberá contrastar el paquete con la fuente.
        funciones: objetivos Clase.metodo, sin comodines, ya seleccionados como
            críticos y aprobados por el orquestador. Una lista vacía es un error.

    Returns:
        ComandoSandbox con argumentos separados, sin shell. targetClasses usa
        una coincidencia exacta y excludedMethods una expresión regular que
        excluye todo nombre no seleccionado, incluidos constructores. PIT admite
        regex con prefijo ~. Las sobrecargas deben rechazarse antes de ejecutar:
        el filtro estándar de PIT distingue nombres, no firmas.

        El comando requiere que la fase de ejecución prepare .qagent-pit.xml
        dentro de la copia aislada. Esta función no crea archivos, no ejecuta
        Maven y no sobrescribe la configuración existente del proyecto.

    Raises:
        ValueError: si la ruta o los objetivos no permiten un alcance inequívoco.
    """
    ruta = PurePosixPath(modulo.replace("\\", "/"))
    partes = ruta.parts
    if (
        ruta.is_absolute()
        or ".." in partes
        or partes[:3] != ("src", "main", "java")
        or ruta.suffix != ".java"
        or not all(IDENTIFICADOR.fullmatch(p) for p in (*partes[3:-1], ruta.stem))
    ):
        raise ValueError(
            "Se requiere src/main/java/paquete/Clase.java sin recorridos relativos."
        )
    if not funciones:
        raise ValueError("No hay métodos críticos seleccionados; no se ejecutará PIT.")
    metodos: set[str] = set()
    for objetivo in funciones:
        segmentos = objetivo.split(".")
        if (
            len(segmentos) != 2
            or segmentos[0] != ruta.stem
            or not IDENTIFICADOR.fullmatch(segmentos[1])
            or segmentos[1] == ruta.stem
        ):
            raise ValueError(
                "Cada objetivo debe ser Clase.metodo de la fuente seleccionada."
            )
        metodos.add(segmentos[1])
    clase = ".".join((*partes[3:-1], ruta.stem))
    filtro_clase = "~^" + re.escape(clase) + "$"
    alternativas = "|".join(re.escape(m) for m in sorted(metodos))
    filtro_exclusion = "~^(?!(?:" + alternativas + ")$).*$"
    return ComandoSandbox(
        [
            "mvn",
            "--offline",
            "--batch-mode",
            "--no-transfer-progress",
            "-Dmaven.repo.local=/opt/qagent/m2",
            "-f",
            POM_TEMPORAL,
            "test-compile",
            f"org.pitest:pitest-maven:{_version_pit()}:mutationCoverage",
            f"-DtargetClasses={filtro_clase}",
            f"-DexcludedMethods={filtro_exclusion}",
            "-DoutputFormats=XML",
            "-DtimestampedReports=false",
            f"-DreportsDirectory={DIRECTORIO_INFORME}",
            "-Dthreads=1",
        ]
    )


def _version_pit() -> str:
    """Lee la versión fijada en la receta del sandbox Java, sin duplicar la fuente."""
    pom = Path(__file__).parent / "java" / "calentamiento" / "pom.xml"
    raiz = ET.fromstring(pom.read_text(encoding="utf-8"))
    version = raiz.findtext("{*}properties/{*}pitest.version")
    if version is None or not re.fullmatch(r"\d+(?:\.\d+)+", version):
        raise ValueError("La receta del sandbox no declara una versión PIT válida.")
    return version

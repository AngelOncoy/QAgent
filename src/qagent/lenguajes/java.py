"""Adaptador de Java (EN-17): por ahora solo detecta.

Punto de partida del responsable de Java. El análisis, el comando de JUnit 5, el
entorno del sandbox y la lectura de resultados lanzan ``NoImplementado`` hasta
que se implementen (ver ``README.md`` de este paquete). El parser que se use
para el análisis estático sigue la decisión de SPK-04.
"""

from __future__ import annotations

from qagent.lenguajes.base import AdaptadorEnDesarrollo


class JavaAdapter(AdaptadorEnDesarrollo):
    """Java con JUnit 5; endpoints Spring."""

    lenguaje = "java"
    extensiones = (".java",)
    marcadores = ("pom.xml", "build.gradle", "build.gradle.kts")
    frameworks_pruebas = ("junit5",)
    frameworks_app = ("spring",)

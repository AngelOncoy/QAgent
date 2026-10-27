"""Registro de adaptadores y detección del lenguaje de un proyecto (EN-17).

El registro es el único punto donde los componentes compartidos obtienen un
adaptador: por nombre de lenguaje (:meth:`Registro.adaptador_para`), por la carpeta
del proyecto (:meth:`Registro.detectar`) o por un contrato del Planner
(:meth:`Registro.adaptador_de_contrato`, que acepta v2 y v3).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.analysis.analyzer import DIRECTORIOS_IGNORADOS
from qagent.lenguajes.base import Deteccion, LanguageAdapter

#: Carpetas que no se recorren al detectar: las del analizador de Python más las
#: de compilación de JS/TS y Java.
CARPETAS_IGNORADAS = DIRECTORIOS_IGNORADOS | {
    "target",
    "build",
    "dist",
    "out",
    "coverage",
}
#: Tope de archivos que se miran al detectar, para no recorrer repositorios enormes.
MAX_ARCHIVOS_DETECCION = 20_000


def listar_archivos(raiz: str | os.PathLike[str]) -> list[str]:
    """Rutas relativas (POSIX) de los archivos del proyecto, sin carpetas ignoradas.

    No sigue enlaces simbólicos ni entra en carpetas ocultas.

    Raises:
        NotADirectoryError: si ``raiz`` no es una carpeta.
    """
    carpeta = Path(raiz)
    if not carpeta.is_dir():
        raise NotADirectoryError(f"No es una carpeta: {carpeta}")
    encontrados: list[str] = []
    for directorio, subdirectorios, archivos in os.walk(carpeta):
        subdirectorios[:] = [
            d
            for d in subdirectorios
            if not d.startswith(".")
            and d not in CARPETAS_IGNORADAS
            and not d.endswith(".egg-info")
        ]
        base = Path(directorio).relative_to(carpeta)
        for nombre in archivos:
            encontrados.append((base / nombre).as_posix())
            if len(encontrados) >= MAX_ARCHIVOS_DETECCION:
                return sorted(encontrados)
    return sorted(encontrados)


class Registro:
    """Adaptadores disponibles, uno por lenguaje."""

    def __init__(self, adaptadores: Iterable[LanguageAdapter] = ()) -> None:
        self._adaptadores: dict[str, LanguageAdapter] = {}
        for adaptador in adaptadores:
            self.registrar(adaptador)

    def registrar(self, adaptador: LanguageAdapter, reemplazar: bool = False) -> None:
        """Agrega un adaptador, comprobando que coincida con los contratos.

        Raises:
            ValueError: si el lenguaje o sus frameworks no existen en los contratos,
                o si el lenguaje ya está registrado y ``reemplazar`` es falso.
        """
        _verificar(adaptador)
        if adaptador.lenguaje in self._adaptadores and not reemplazar:
            raise ValueError(f"Ya hay un adaptador para {adaptador.lenguaje}.")
        self._adaptadores[adaptador.lenguaje] = adaptador

    @property
    def lenguajes(self) -> tuple[str, ...]:
        """Lenguajes registrados, en orden de registro."""
        return tuple(self._adaptadores)

    def adaptador_para(self, lenguaje: str) -> LanguageAdapter:
        """Adaptador de un lenguaje.

        Raises:
            KeyError: si no hay adaptador para ese lenguaje.
        """
        try:
            return self._adaptadores[lenguaje]
        except KeyError:
            opciones = ", ".join(self._adaptadores) or "ninguno"
            raise KeyError(
                f"No hay adaptador para '{lenguaje}'. Registrados: {opciones}"
            ) from None

    def adaptador_de_contrato(self, contrato: dict[str, Any]) -> LanguageAdapter:
        """Adaptador del lenguaje de un ``planner_contract`` (v2 = Python).

        Raises:
            ContratoInvalido: si el contrato no cumple su versión.
            KeyError: si no hay adaptador para su lenguaje.
        """
        return self.adaptador_para(contracts.normalizar_planner(contrato)["lenguaje"])

    def detectar_en(self, archivos: Sequence[str]) -> list[Deteccion]:
        """Detecta los lenguajes de una lista de rutas relativas (pura, sin disco).

        Returns:
            Las detecciones con su ``confianza``, de la más a la menos probable.
            Vacía si ningún lenguaje registrado tiene indicios.
        """
        detecciones = [
            d
            for a in self._adaptadores.values()
            if (d := a.detectar(archivos)) is not None
        ]
        fuentes = sum(d.archivos for d in detecciones)
        con_confianza = [
            replace(d, confianza=d.archivos / fuentes if fuentes else 0.0)
            for d in detecciones
        ]
        return sorted(
            con_confianza,
            key=lambda d: (-d.confianza, -len(d.marcadores), d.lenguaje),
        )

    def detectar(self, raiz: str | os.PathLike[str]) -> list[Deteccion]:
        """Detecta los lenguajes de un proyecto en disco (ver :meth:`detectar_en`)."""
        return self.detectar_en(listar_archivos(raiz))

    def lenguaje_principal(self, raiz: str | os.PathLike[str]) -> str | None:
        """Lenguaje con más archivos fuente del proyecto, o ``None`` si no hay."""
        detecciones = [d for d in self.detectar(raiz) if d.archivos]
        return detecciones[0].lenguaje if detecciones else None


def _verificar(adaptador: LanguageAdapter) -> None:
    lenguaje = getattr(adaptador, "lenguaje", None)
    if lenguaje not in contracts.LENGUAJES:
        raise ValueError(
            f"Lenguaje '{lenguaje}' desconocido en los contratos "
            f"({', '.join(contracts.LENGUAJES)})."
        )
    if not adaptador.extensiones or not all(
        e.startswith(".") for e in adaptador.extensiones
    ):
        raise ValueError(f"{lenguaje}: las extensiones deben empezar con punto.")
    validos = contracts.FRAMEWORKS_PRUEBAS[lenguaje]
    if not adaptador.frameworks_pruebas or not set(adaptador.frameworks_pruebas) <= set(
        validos
    ):
        raise ValueError(
            f"{lenguaje}: frameworks de pruebas {adaptador.frameworks_pruebas} "
            f"fuera del contrato ({', '.join(validos)})."
        )
    if not set(adaptador.frameworks_app) <= set(contracts.FRAMEWORKS_APP[lenguaje]):
        raise ValueError(
            f"{lenguaje}: frameworks web {adaptador.frameworks_app} fuera del contrato."
        )

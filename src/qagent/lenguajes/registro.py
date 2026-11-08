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


class LenguajeNoSoportado(RuntimeError):
    """El proyecto es de un lenguaje cuyo adaptador todavía no permite corridas."""

    def __init__(self, lenguaje: str, nombre: str, soportados: Sequence[str]) -> None:
        self.lenguaje = lenguaje
        lista = ", ".join(soportados) or "ninguno"
        super().__init__(
            f"QAgent aún no puede probar proyectos en {nombre}: su soporte está en "
            f"desarrollo. Por ahora se admiten proyectos en {lista}."
        )


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

    def adaptador_del_proyecto(
        self, raiz: str | os.PathLike[str], predeterminado: str
    ) -> LanguageAdapter:
        """Adaptador con el que se corre el proyecto en ``raiz`` (#168).

        Es el del lenguaje con más archivos fuente entre los que tienen adaptador
        completo. Si hay más de uno, un adaptador con ``marcadores_si_mixto``
        (JavaScript y TypeScript) solo se elige con uno de ellos en la raíz: un
        proyecto de Python con algo de JavaScript (una carpeta ``static/``) se sigue
        probando como Python. Sin archivos fuente de ningún lenguaje se usa
        ``predeterminado``.

        Raises:
            LenguajeNoSoportado: si el proyecto solo tiene lenguajes cuyo adaptador
                todavía no permite corridas.
        """
        detecciones = [d for d in self.detectar(raiz) if d.archivos]
        completos = [
            a for d in detecciones if (a := self.adaptador_para(d.lenguaje)).completo
        ]
        for adaptador in completos:
            mixto = any(a.lenguaje != adaptador.lenguaje for a in completos)
            if (
                mixto
                and adaptador.marcadores_si_mixto
                and not any(
                    (Path(raiz) / m).is_file() for m in adaptador.marcadores_si_mixto
                )
            ):
                continue
            return adaptador
        if completos:
            return completos[0]
        if detecciones:
            principal = self.adaptador_para(detecciones[0].lenguaje)
            soportados = [
                a.nombre_visible for a in self._adaptadores.values() if a.completo
            ]
            raise LenguajeNoSoportado(
                principal.lenguaje, principal.nombre_visible, soportados
            )
        return self.adaptador_para(predeterminado)

    def fuera_de_la_corrida(
        self, raiz: str | os.PathLike[str], adaptador: LanguageAdapter
    ) -> list[dict[str, Any]]:
        """Archivos de un lenguaje hermano que la corrida de ``adaptador`` no prueba.

        Un proyecto con ``.js`` y ``.ts`` se corre con un solo adaptador: el del
        lenguaje con más archivos. Los del otro quedan fuera y aquí se cuentan para
        avisarlo, en lugar de omitirlos en silencio.

        Returns:
            Una entrada por lenguaje omitido con ``lenguaje``, ``nombre``,
            ``archivos`` (cantidad), ``rutas`` y ``mensaje`` para personas.
        """
        if not adaptador.lenguajes_hermanos:
            return []
        archivos = listar_archivos(raiz)
        omitidos = []
        for lenguaje in adaptador.lenguajes_hermanos:
            if lenguaje == adaptador.lenguaje or lenguaje not in self._adaptadores:
                continue
            hermano = self.adaptador_para(lenguaje)
            rutas = sorted(a for a in archivos if hermano.es_fuente(a))
            if not rutas:
                continue
            cantidad = len(rutas)
            sujeto = (
                f"1 archivo de {hermano.nombre_visible} no se prueba"
                if cantidad == 1
                else f"{cantidad} archivos de {hermano.nombre_visible} no se prueban"
            )
            omitidos.append(
                {
                    "lenguaje": hermano.lenguaje,
                    "nombre": hermano.nombre_visible,
                    "archivos": cantidad,
                    "rutas": rutas,
                    "mensaje": (
                        f"{sujeto} en esta corrida: QAgent prueba un lenguaje por "
                        f"corrida y este proyecto se prueba como "
                        f"{adaptador.nombre_visible}, que tiene más archivos."
                    ),
                }
            )
        return omitidos

    def adaptador_e2e_del_proyecto(
        self, raiz: str | os.PathLike[str]
    ) -> LanguageAdapter:
        """Devuelve el adaptador principal si admite humo E2E determinista.

        Esta selección no convierte un adaptador en completo ni habilita las
        corridas de Planner/Generator/Reviewer. Solo permite abrir el proyecto,
        analizarlo estáticamente y acceder al flujo separado de #186.

        Raises:
            LenguajeNoSoportado: si hay fuentes, pero su adaptador no admite E2E.
            LookupError: si no se detectaron fuentes de ningún lenguaje.
        """
        detecciones = [d for d in self.detectar(raiz) if d.archivos]
        if not detecciones:
            raise LookupError("No se detectaron fuentes para humo E2E.")
        principal = self.adaptador_para(detecciones[0].lenguaje)
        if principal.e2e_humo_disponible:
            return principal
        soportados = [
            a.nombre_visible
            for a in self._adaptadores.values()
            if a.e2e_humo_disponible
        ]
        raise LenguajeNoSoportado(
            principal.lenguaje, principal.nombre_visible, soportados
        )


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
    tipos = (*adaptador.tipos_prueba, *adaptador.tipos_prueba_previstos)
    if not set(tipos) <= set(contracts.TIPOS_PRUEBA_RECOMENDABLES):
        raise ValueError(
            f"{lenguaje}: tipos de prueba {tipos} fuera del contrato "
            f"({', '.join(contracts.TIPOS_PRUEBA_RECOMENDABLES)})."
        )
    if adaptador.tipos_prueba and not adaptador.completo:
        raise ValueError(
            f"{lenguaje}: un adaptador en desarrollo no puede declarar tipos de "
            "prueba operativos (ADR-011)."
        )

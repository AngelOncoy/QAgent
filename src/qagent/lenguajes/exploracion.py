"""Exploración determinista de archivos y detección de truncamiento (ADR-008).

Proporciona un recorrido reproducible del sistema de archivos para proyectos
grandes, respetando exclusiones, enlaces simbólicos seguros y límites de
procesamiento. Identifica si la exploración quedó completa, truncada o parcial,
y permite continuar el recorrido por módulos o carpetas específicas sin duplicados.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from qagent.analysis.analyzer import DIRECTORIOS_IGNORADOS

#: Carpetas que no se recorren al detectar: analizador de Python más compilación JS/TS/Java.
CARPETAS_IGNORADAS = DIRECTORIOS_IGNORADOS | {
    "target",
    "build",
    "dist",
    "out",
    "coverage",
}

#: Scripts de medición empírica que no forman parte del código a probar.
ARCHIVOS_IGNORADOS = frozenset(
    {
        "medir_orquestador_spk03.py",
    }
)

#: Tope de archivos que se exploran para no agotar recursos en repositorios gigantes.
MAX_ARCHIVOS_DETECCION = 20_000

# Estados propuestos de exploración
ESTADO_COMPLETO = "completo"
ESTADO_TRUNCADO = "truncado"
ESTADO_PARCIAL_ERROR = "parcial_error"
ESTADO_CANCELADO = "cancelado"
ESTADOS_VALIDOS = (
    ESTADO_COMPLETO,
    ESTADO_TRUNCADO,
    ESTADO_PARCIAL_ERROR,
    ESTADO_CANCELADO,
)


def _es_directorio_ignorado(nombre: str) -> bool:
    """Indica si una carpeta debe ignorarse durante el recorrido."""
    return (
        nombre.startswith(".")
        or nombre in CARPETAS_IGNORADAS
        or nombre.endswith(".egg-info")
    )


def _es_archivo_ignorado(nombre: str) -> bool:
    """Indica si un archivo debe ignorarse."""
    return nombre in ARCHIVOS_IGNORADOS


@dataclass(frozen=True)
class ResultadoExploracion:
    """Metadatos y rutas de la exploración determinista de un repositorio.

    Atributos:
        archivos: rutas relativas normalizadas (POSIX) ordenadas y sin duplicados.
        estado: 'completo', 'truncado', 'parcial_error' o 'cancelado'.
        total_procesados: cantidad total de archivos incluidos en ``archivos``.
        limite: tope de archivos configurado (por defecto 20.000).
        limite_alcanzado: True si se alcanzó el límite y existen archivos pendientes.
        carpetas_pendientes: rutas relativas (POSIX) de carpetas pendientes de analizar.
        carpetas_exploradas: rutas relativas (POSIX) de carpetas analizadas en esta corrida.
        errores: lista de incidencias de lectura con su ruta y mensaje.
    """

    archivos: tuple[str, ...]
    estado: str
    total_procesados: int
    limite: int = MAX_ARCHIVOS_DETECCION
    limite_alcanzado: bool = False
    carpetas_pendientes: tuple[str, ...] = ()
    carpetas_exploradas: tuple[str, ...] = ()
    errores: tuple[dict[str, str], ...] = ()

    @property
    def completo(self) -> bool:
        """Indica si el recorrido fue exhaustivo y sin errores."""
        return self.estado == ESTADO_COMPLETO

    @property
    def truncado(self) -> bool:
        """Indica si se alcanzó el límite y existen archivos pendientes."""
        return self.estado == ESTADO_TRUNCADO

    @property
    def incompleto(self) -> bool:
        """Indica si el recorrido no cubrió la totalidad del repositorio."""
        return self.estado != ESTADO_COMPLETO

    def consolidar(self, otro: ResultadoExploracion) -> ResultadoExploracion:
        """Consolida dos resultados de exploración sin duplicar archivos.

        Combina las rutas encontradas, actualiza las carpetas exploradas y
        descarta de las pendientes aquellas carpetas que ya hayan sido analizadas.
        """
        archivos_consolidados = tuple(sorted(set(self.archivos) | set(otro.archivos)))
        exploradas_set = set(self.carpetas_exploradas) | set(otro.carpetas_exploradas)
        carpetas_exploradas = tuple(sorted(exploradas_set))

        # Filtrar de pendientes las carpetas que ya han sido exploradas
        candidatas_pendientes = set(self.carpetas_pendientes) | set(
            otro.carpetas_pendientes
        )
        pendientes_restantes = {
            p
            for p in candidatas_pendientes
            if not any(
                p == exp or p.startswith(exp.rstrip("/") + "/")
                for exp in exploradas_set
            )
        }
        carpetas_pendientes = tuple(sorted(pendientes_restantes))

        errores_combinados = tuple(self.errores) + tuple(
            e for e in otro.errores if e not in self.errores
        )

        limite_alcanzado = (
            self.limite_alcanzado and bool(carpetas_pendientes)
        ) or otro.limite_alcanzado

        if self.estado == ESTADO_CANCELADO or otro.estado == ESTADO_CANCELADO:
            estado = ESTADO_CANCELADO
            limite_alcanzado = False
        elif limite_alcanzado or bool(carpetas_pendientes):
            estado = ESTADO_TRUNCADO
            limite_alcanzado = True
        elif (
            errores_combinados
            or self.estado == ESTADO_PARCIAL_ERROR
            or otro.estado == ESTADO_PARCIAL_ERROR
        ):
            estado = ESTADO_PARCIAL_ERROR
            limite_alcanzado = False
        else:
            estado = ESTADO_COMPLETO
            limite_alcanzado = False

        return ResultadoExploracion(
            archivos=archivos_consolidados,
            estado=estado,
            total_procesados=len(archivos_consolidados),
            limite=self.limite,
            limite_alcanzado=limite_alcanzado,
            carpetas_pendientes=carpetas_pendientes,
            carpetas_exploradas=carpetas_exploradas,
            errores=errores_combinados,
        )


def _verificar_archivos_pendientes(
    pendientes: list[Path],
    carpeta_raiz: Path,
) -> bool:
    """Comprueba si en las carpetas pendientes existe al menos un archivo elegible.

    Se detiene inmediatamente tras encontrar el primer archivo para no degradar
    el rendimiento ni consumir memoria innecesaria.
    """
    for carpeta in pendientes:
        try:
            it = os.scandir(carpeta)
            entradas = list(it) if not hasattr(it, "__enter__") else []
            if hasattr(it, "__enter__"):
                with it as scandir_it:
                    entradas = list(scandir_it)
            for entry in entradas:
                try:
                    if entry.is_file(
                        follow_symlinks=False
                    ) and not _es_archivo_ignorado(entry.name):
                        return True
                    if (
                        entry.is_dir(follow_symlinks=False)
                        and not entry.is_symlink()
                        and not _es_directorio_ignorado(entry.name)
                        and _verificar_archivos_pendientes(
                            [Path(entry.path)], carpeta_raiz
                        )
                    ):
                        return True
                except OSError:
                    continue
        except OSError:
            continue
    return False


def explorar_archivos(
    raiz: str | os.PathLike[str],
    *,
    limite: int | None = None,
    subcarpetas: Sequence[str] | None = None,
    archivos_previos: Sequence[str] | None = None,
    cancel_token: Callable[[], bool] | None = None,
) -> ResultadoExploracion:
    """Recorre de forma determinista y segura los archivos elegibles de un proyecto.

    Ordena directorios y archivos por su ruta relativa normalizada antes de procesarlos.
    No sigue enlaces simbólicos que salgan de la raíz autorizada ni entra en enlaces
    simbólicos a directorios para prevenir ciclos.

    Args:
        raiz: Carpeta raíz del proyecto.
        limite: Cantidad máxima de archivos a recopilar (por defecto 20.000).
        subcarpetas: Subcarpetas relativas específicas a explorar (continuación por módulos).
        archivos_previos: Archivos de una exploración previa para consolidar sin duplicados.
        cancel_token: Función opcional que devuelve True si el usuario canceló.

    Returns:
        ResultadoExploracion con los archivos normalizados y metadatos de estado.

    Raises:
        NotADirectoryError: si ``raiz`` no es una carpeta existente.
    """
    carpeta_raiz = Path(raiz).resolve()
    if not carpeta_raiz.is_dir():
        raise NotADirectoryError(f"No es una carpeta: {raiz}")

    tope = MAX_ARCHIVOS_DETECCION if limite is None else limite
    encontrados: list[str] = []
    vistos: set[str] = set()
    if archivos_previos:
        for a in archivos_previos:
            posix_norm = PurePosixPath(a).as_posix()
            if posix_norm not in vistos:
                vistos.add(posix_norm)
                encontrados.append(posix_norm)

    carpetas_exploradas: list[str] = []
    carpetas_pendientes: list[str] = []
    errores: list[dict[str, str]] = []

    # Inicializar la pila de directorios a recorrer
    if subcarpetas is not None:
        pila: list[Path] = []
        # Normalizar y ordenar las subcarpetas solicitadas
        rutas_validas: list[Path] = []
        for s in subcarpetas:
            limpia = s.strip().replace("\\", "/").strip("/")
            if not limpia:
                continue
            sub_path = (carpeta_raiz / Path(limpia)).resolve()
            if not sub_path.is_relative_to(carpeta_raiz):
                # Protección contra directory traversal fuera de la raíz autorizada
                continue
            if sub_path.is_dir() and not sub_path.is_symlink():
                rutas_validas.append(sub_path)
        # Orden determinista inverso para extraer en orden con pop()
        rutas_validas.sort(
            key=lambda p: p.relative_to(carpeta_raiz).as_posix(), reverse=True
        )
        pila.extend(rutas_validas)
    else:
        pila = [carpeta_raiz]

    limite_alcanzado = False
    hay_pendientes = False

    while pila:
        if cancel_token is not None and cancel_token():
            carpetas_pendientes.extend(
                p.relative_to(carpeta_raiz).as_posix() or "." for p in pila
            )
            return ResultadoExploracion(
                archivos=tuple(sorted(encontrados)),
                estado=ESTADO_CANCELADO,
                total_procesados=len(encontrados),
                limite=limite,
                limite_alcanzado=False,
                carpetas_pendientes=tuple(sorted(set(carpetas_pendientes))),
                carpetas_exploradas=tuple(sorted(set(carpetas_exploradas))),
                errores=tuple(errores),
            )

        directorio_actual = pila.pop()
        rel_dir = directorio_actual.relative_to(carpeta_raiz).as_posix() or "."
        carpetas_exploradas.append(rel_dir)

        # Leer entradas del directorio de forma segura
        try:
            it = os.scandir(directorio_actual)
            if hasattr(it, "__enter__"):
                with it as scandir_it:
                    entradas = list(scandir_it)
            else:
                entradas = list(it)
        except (PermissionError, OSError) as err:
            errores.append({"ruta": rel_dir, "error": str(err)})
            continue

        # Separar subdirectorios y archivos elegibles
        subdirectorios: list[Path] = []
        archivos_locales: list[str] = []

        for entrada in entradas:
            try:
                nombre = entrada.name
                if (
                    entrada.is_dir(follow_symlinks=False)
                    and not entrada.is_symlink()
                    and not _es_directorio_ignorado(nombre)
                ):
                    subdirectorios.append(Path(entrada.path))
                elif entrada.is_file(
                    follow_symlinks=False
                ) and not _es_archivo_ignorado(nombre):
                    # Comprobación de seguridad en enlaces simbólicos a archivos
                    if entrada.is_symlink():
                        try:
                            destino = Path(entrada.path).resolve()
                            if not destino.is_relative_to(carpeta_raiz):
                                continue
                        except (OSError, ValueError):
                            continue
                    archivos_locales.append(nombre)
            except OSError as err:
                errores.append(
                    {
                        "ruta": f"{rel_dir}/{entrada.name}".lstrip("./"),
                        "error": str(err),
                    }
                )

        # Ordenar determinísticamente por nombre
        archivos_locales.sort()
        # Para la pila DFS pre-order: ordenamos de forma inversa para procesar en orden alfabético
        subdirectorios.sort(key=lambda p: p.name, reverse=True)

        base_path = directorio_actual.relative_to(carpeta_raiz)

        for idx, nombre in enumerate(archivos_locales):
            if len(encontrados) >= tope:
                limite_alcanzado = True
                hay_pendientes = True
                carpetas_pendientes.append(rel_dir)
                break

            ruta_rel = (
                (base_path / nombre).as_posix() if base_path != Path(".") else nombre
            )
            if ruta_rel not in vistos:
                vistos.add(ruta_rel)
                encontrados.append(ruta_rel)

        if limite_alcanzado:
            # Añadir subdirectorios pendientes no explorados
            for sub in subdirectorios:
                carpetas_pendientes.append(sub.relative_to(carpeta_raiz).as_posix())
            # Y todos los restantes en la pila
            for p in pila:
                carpetas_pendientes.append(p.relative_to(carpeta_raiz).as_posix())
            break

        # Si no se alcanzó el límite, agregar los subdirectorios a la pila para continuar
        pila.extend(subdirectorios)

    # Caso límite: se alcanzó exactamente el límite sin encontrar archivos extra inmediatamente
    if (
        len(encontrados) == tope
        and not limite_alcanzado
        and pila
        and _verificar_archivos_pendientes(pila, carpeta_raiz)
    ):
        limite_alcanzado = True
        hay_pendientes = True
        for p in pila:
            carpetas_pendientes.append(p.relative_to(carpeta_raiz).as_posix())

    # Determinar estado
    if limite_alcanzado and hay_pendientes:
        estado = ESTADO_TRUNCADO
    elif errores:
        estado = ESTADO_PARCIAL_ERROR
    else:
        estado = ESTADO_COMPLETO

    return ResultadoExploracion(
        archivos=tuple(sorted(encontrados)),
        estado=estado,
        total_procesados=len(encontrados),
        limite=tope,
        limite_alcanzado=limite_alcanzado,
        carpetas_pendientes=tuple(sorted(set(carpetas_pendientes))),
        carpetas_exploradas=tuple(sorted(set(carpetas_exploradas))),
        errores=tuple(errores),
    )

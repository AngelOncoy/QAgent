"""Construcción del comando Stryker acotado por rangos de líneas (#179).

Solo muta las funciones críticas seleccionadas dentro del módulo, nunca el
repositorio completo ni el archivo entero sin delimitar.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from qagent.lenguajes.base import ComandoSandbox

EXTENSIONES_JS_TS = frozenset(
    {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts"}
)
CONFIG_STRYKER_TEMPORAL = ".qagent-stryker.json"
IDENTIFICADOR = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$.]*$")


def comando_stryker(
    modulo: str,
    funciones: list[str],
    rangos: dict[str, tuple[int, int]] | None = None,
) -> ComandoSandbox:
    """Construye el comando Stryker acotado a los rangos de las funciones críticas.

    Args:
        modulo: ruta relativa del archivo en el proyecto (ej. `src/precios.ts`).
        funciones: nombres de las funciones críticas seleccionadas.
        rangos: mapeo opcional de función a `(linea_inicio, linea_fin)`. Si no se
            da, intenta extraerlos del archivo si existe o de los nombres.

    Returns:
        ComandoSandbox con `stryker run` y `--mutate` delimitado a las líneas
        de las funciones críticas.

    Raises:
        ValueError: si la ruta, la selección o los rangos no son válidos.
    """
    ruta_posix = modulo.replace("\\", "/")
    ruta = PurePosixPath(ruta_posix)
    partes = ruta.parts

    if (
        ruta.is_absolute()
        or ".." in partes
        or ruta.suffix.lower() not in EXTENSIONES_JS_TS
        or any("*" in p or "?" in p for p in partes)
    ):
        raise ValueError(
            f"Ruta de módulo no admitida para Stryker: {modulo!r}. "
            "Se requiere ruta relativa sin comodines ni recorridos relativos."
        )

    if not funciones:
        raise ValueError(
            "No hay funciones críticas seleccionadas; no se ejecutará Stryker."
        )

    for f in funciones:
        if not f or not IDENTIFICADOR.match(f):
            raise ValueError(f"Nombre de función crítica inválido: {f!r}")

    # Resolver rangos si no se pasaron explícitamente
    rangos_resueltos: dict[str, tuple[int, int]] = {}
    if rangos is not None:
        rangos_resueltos = dict(rangos)
    else:
        # Intentar obtenerlos si el archivo existe en disco
        archivo = Path(modulo)
        if archivo.is_file():
            from qagent.sandbox.stryker_preparacion import extraer_rangos_funciones

            rangos_resueltos = extraer_rangos_funciones(Path("."), modulo, funciones)

    # Validar que todas las funciones pedidas tengan rango
    faltantes = [f for f in funciones if f not in rangos_resueltos]
    if faltantes:
        raise ValueError(
            f"No se pudieron determinar los rangos de líneas para: {faltantes} en {modulo}."
        )

    # Validar rangos individuales
    patrones_mutate: list[str] = []
    for nombre in sorted(dict.fromkeys(funciones)):
        inicio, fin = rangos_resueltos[nombre]
        if not isinstance(inicio, int) or not isinstance(fin, int):
            raise TypeError(f"Rango inválido para {nombre}: {(inicio, fin)}")
        if inicio < 1 or fin < inicio:
            raise ValueError(f"Rango de líneas inválido para {nombre}: {inicio}-{fin}.")
        patrones_mutate.append(f"{ruta_posix}:{inicio}-{fin}")

    patron_completo = ",".join(patrones_mutate)

    return ComandoSandbox(
        comando=[
            "stryker",
            "run",
            CONFIG_STRYKER_TEMPORAL,
            f"--mutate={patron_completo}",
            "--concurrency",
            "1",
        ],
        entorno={
            "NODE_ENV": "test",
            "NO_COLOR": "1",
        },
    )

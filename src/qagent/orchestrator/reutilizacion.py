"""Solicita snapshots al adaptador sin conocer reglas de un lenguaje (#307)."""

from pathlib import Path
from typing import Any

from qagent.lenguajes import REGISTRO


def claves_actuales(
    raiz: Path, configuracion: Any = None, imagen: str | None = None
) -> dict[tuple[str, str], dict[str, Any]]:
    """Claves adicionales para adaptadores que declaran esta política."""
    resultado = {}
    for lenguaje in REGISTRO.lenguajes:
        adaptador = REGISTRO.adaptador_para(lenguaje)
        if not adaptador.requiere_claves_reutilizacion:
            continue
        if not adaptador.completo:
            continue
        analisis = adaptador.analizar(raiz)
        resultado.update(
            adaptador.claves_reutilizacion(
                raiz, analisis["modulos"], configuracion, imagen
            )
            or {}
        )
    return resultado

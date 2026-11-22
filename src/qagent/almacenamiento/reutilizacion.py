"""Metadatos de vigencia independientes de los contratos entre agentes (#307)."""

import re
from typing import Any


def valida(datos: Any) -> bool:
    """Reconoce la versión y las claves completas, sin inferir metadatos antiguos."""
    return (
        isinstance(datos, dict)
        and datos.get("version") == "1"
        and set(datos) == {"version", "spec", "pruebas", "mutacion", "entorno"}
        and all(
            isinstance(datos.get(k), str) and re.fullmatch(r"[a-f0-9]{64}", datos[k])
            for k in ("spec", "pruebas", "mutacion")
        )
        and (
            datos["entorno"] is None
            or isinstance(datos["entorno"], str)
            and 0 < len(datos["entorno"]) <= 256
        )
    )


def vigente(
    guardada: Any, actual: Any, etapa: str, *, comprobar_entorno: bool = True
) -> bool:
    """Ausencia, versión desconocida o contexto distinto impiden la reutilización."""
    if not valida(guardada) or not valida(actual) or guardada[etapa] != actual[etapa]:
        return False
    if etapa == "spec":
        return True
    if guardada["entorno"] is None:
        return False
    return not comprobar_entorno or actual["entorno"] == guardada["entorno"]


def requiere_claves(contrato: dict[str, Any]) -> bool:
    """El adaptador declara si exige esta política adicional de vigencia."""
    from qagent.lenguajes import adaptador_de_contrato

    return adaptador_de_contrato(contrato).requiere_claves_reutilizacion

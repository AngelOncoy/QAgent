"""Resúmenes deterministas de evidencia ejecutada, sin IA ni cambios de veredicto."""

from __future__ import annotations

import json
from typing import Any


def _valor(valor: Any) -> str:
    """Representa un valor explícito del informe sin volcar una salida extensa."""
    texto = (
        json.dumps(valor, ensure_ascii=False) if not isinstance(valor, str) else valor
    )
    return texto if len(texto) <= 120 else texto[:117] + "…"


def resumir_prueba(funcion: dict[str, Any], perfil: str | None = None) -> str:
    """Resume el resultado conocido; no convierte un error técnico en un bug.

    Los valores se citan exclusivamente si el runner los registró para un caso
    fallido. Sin ellos se describe el veredicto sin adivinar entradas ni salidas.
    El feedback técnico no es una explicación para el usuario.
    """
    estado = funcion.get("estado")
    if estado == "aprobado":
        alcance = (
            " En Humo se comprueba un caso normal por objetivo."
            if perfil == "humo"
            else ""
        )
        return (
            "Pasaron los casos ejecutados. Esto no garantiza que todo el método esté "
            "libre de defectos." + alcance
        )
    if estado == "bug_detectado":
        casos = (funcion.get("ejecucion") or {}).get("casos") or []
        for caso in casos:
            if (
                caso.get("resultado") == "fallo"
                and caso.get("esperado") is not None
                and caso.get("obtenido") is not None
            ):
                return (
                    f"La prueba esperaba {_valor(caso['esperado'])} y obtuvo "
                    f"{_valor(caso['obtenido'])}. Se detectó una diferencia con "
                    "el comportamiento esperado."
                )
        return "Una prueba ejecutada detectó una diferencia con el comportamiento esperado."
    if estado == "sin_veredicto":
        return (
            "No se obtuvo un veredicto por un problema de planificación o ejecución. "
            "Esto no demuestra un defecto en el método. Consulta el detalle técnico."
        )
    if estado == "rechazado_laundering":
        return "Se rechazó una prueba que debilitaba las comprobaciones del comportamiento esperado."
    if estado == "requiere_corrida_nueva":
        return "El código cambió: vuelve a ejecutar las pruebas para verificar esta versión."
    if estado == "estancado":
        return "No se logró una prueba verificable dentro de los intentos permitidos. Consulta el detalle técnico."
    return (
        "No hay un resultado de ejecución suficiente para confirmar el comportamiento."
    )

"""Traduce los eventos de la corrida al formato del Monitor en vivo (HU-09).

El orquestador emite `Evento` técnicos (agente, estado, decisión…). La pantalla del
Monitor espera filas `{a, f, fn, t, guard, hechos, total}`, donde `a` elige la etiqueta y
el ícono (las mismas claves que `TAG` en `monitor.js`). Aquí solo se decide cómo se
presenta cada evento; los textos se escapan en la pantalla, no aquí.
"""

from __future__ import annotations

from typing import Any

LARGO_MAXIMO = 400  # caracteres del texto de una fila del Monitor

_VEREDICTO = {
    "accept": ("reviewer", "Prueba aprobada en el sandbox (intento {intento})", None),
    "bug_detectado": (
        "oracle",
        "La prueba muestra un bug: el código no hace lo que dice su documentación",
        ("Oráculo del contrato: el valor esperado no se cumple", "BUG"),
    ),
}


def a_fila_monitor(evento: dict[str, Any]) -> dict[str, Any] | None:
    """Fila del Monitor para un evento de la corrida, o None si no se muestra.

    Los cambios de estado internos de la máquina (`tipo == "transicion"`) no se
    muestran: son pasos técnicos que ya cuentan los mensajes de los agentes.
    """
    if evento.get("tipo") == "transicion":
        return None
    agente = evento.get("agente") or "orquestador"
    mensaje = str(evento.get("mensaje") or "")
    tipo_fila, guard = _clasificar(agente, evento.get("tipo"), mensaje, evento)
    if evento.get("tipo") == "veredicto":
        mensaje = _texto_veredicto(evento, mensaje)
    if len(mensaje) > LARGO_MAXIMO:  # la salida de pytest puede ser muy larga
        mensaje = mensaje[: LARGO_MAXIMO - 1].rstrip() + "…"
    progreso = evento.get("progreso") or {}
    return {
        "a": tipo_fila,
        "f": evento.get("archivo") or "",
        "fn": evento.get("funcion") or "",
        "t": mensaje,
        "guard": list(guard) if guard else None,
        "hechos": int(progreso.get("hechos", 0)),
        "total": int(progreso.get("total", 0)),
        "tipo": evento.get("tipo"),
    }


def a_evento_bitacora(fila: dict[str, Any]) -> dict[str, Any]:
    """Misma fila en el formato de `bitacora.registrar_evento` (consola de Python)."""
    mensaje = fila["t"] + (
        f" [{fila['guard'][0]}: {fila['guard'][1]}]" if fila["guard"] else ""
    )
    return {
        "tipo": fila["a"],
        "agente": fila["a"],
        "archivo": fila["f"],
        "funcion": fila["fn"],
        "mensaje": mensaje,
        "progreso": f"{fila['hechos']}/{fila['total']}" if fila["total"] else "",
    }


def _clasificar(
    agente: str, tipo: Any, mensaje: str, evento: dict[str, Any]
) -> tuple[str, tuple[str, str] | None]:
    if agente in ("planner", "generator"):
        return agente, None
    if agente == "reviewer":
        if tipo == "veredicto":
            datos = evento.get("datos") or {}
            decision = datos.get("decision")
            if decision == "stalled":
                return "stuck", (str(datos.get("etiqueta") or mensaje), "ESTANCADO")
            fila, _, guard = _VEREDICTO.get(decision, ("reviewer", "", None))
            return fila, guard
        if "LAUNDERING" in mensaje.upper():
            return "guard", (
                "Assertion Laundering: la corrección debilitó la prueba",
                "RECHAZADA",
            )
        return "reviewer", None
    # Orquestador: preparación, avisos, fallos y fin.
    if tipo == "fallo":
        return "stuck", ("Corrida", "DETENIDA")
    return "sistema", None


def _texto_veredicto(evento: dict[str, Any], mensaje: str) -> str:
    datos = evento.get("datos") or {}
    decision = datos.get("decision")
    if decision in _VEREDICTO:
        return _VEREDICTO[decision][1].format(intento=datos.get("intento", 1))
    return mensaje

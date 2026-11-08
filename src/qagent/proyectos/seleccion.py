"""Validación de los objetivos elegidos en la Vista previa."""

from __future__ import annotations

from typing import Any


class SeleccionInvalida(ValueError):
    """Indica que la selección no coincide con el análisis AST del proyecto."""


def filtrar_modulos(
    modulos: list[dict[str, Any]], seleccion: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Filtra módulos y objetivos tras validar una selección de la interfaz.

    ``None`` conserva el comportamiento histórico: incluye todos los módulos que
    tengan funciones públicas o endpoints. Una lista explícita nunca puede incluir
    rutas u objetivos que no existan en el análisis AST recibido.

    Cada entrada puede traer ``criticas``: los objetivos marcados en la columna
    Profundizar, nombres de función (HU-06) u objetivos de endpoint como
    ``"POST /pedidos"`` (#74). Deben estar entre sus ``funciones`` o ``endpoints``;
    cada objetivo seleccionado se copia con ``critical`` True o False según esa
    lista, sin modificar el análisis recibido. Sin ``criticas``, nada es crítico.

    Los ``componentes`` React (#171) se seleccionan por nombre igual que las
    funciones, pero nunca se profundizan: la mutación no corre sobre componentes.

    Las ``integraciones`` (#245, ADR-014) son opcionales y se eligen por el nombre de la
    función raíz, entre las cadenas candidatas del análisis. Sin una selección que las
    pida, el módulo sale sin ellas (el tipo nunca se activa solo). Si se elige una raíz
    cuya función unitaria no está seleccionada, la función queda en el módulo con
    ``solo_integracion``: el Planner la necesita para derivar la integración, pero no
    se ejecuta como prueba unitaria.
    """
    analizables = [
        m
        for m in modulos
        if m.get("funciones") or m.get("endpoints") or m.get("componentes")
    ]
    if seleccion is None:
        return [_sin_integraciones(m) for m in analizables]
    if not isinstance(seleccion, list) or not seleccion:
        raise SeleccionInvalida("Selecciona al menos un objetivo analizable.")

    por_ruta = {m.get("ruta"): m for m in analizables}
    rutas_vistas: set[str] = set()
    filtrados: list[dict[str, Any]] = []

    for entrada in seleccion:
        if not isinstance(entrada, dict):
            raise SeleccionInvalida("La selección de objetivos no es válida.")
        ruta = entrada.get("ruta")
        funciones = entrada.get("funciones", [])
        endpoints = entrada.get("endpoints", [])
        componentes = entrada.get("componentes", [])
        integraciones = entrada.get("integraciones", [])
        criticas = entrada.get("criticas", [])
        if (
            not isinstance(ruta, str)
            or not ruta
            or not _lista_unica_de_textos(funciones)
            or not _lista_unica_de_textos(endpoints)
            or not _lista_unica_de_textos(componentes)
            or not _lista_unica_de_textos(integraciones)
            or not _lista_unica_de_textos(criticas)
        ):
            raise SeleccionInvalida("La selección de objetivos no es válida.")
        if ruta in rutas_vistas:
            raise SeleccionInvalida(f"El módulo está repetido en la selección: {ruta}")
        rutas_vistas.add(ruta)

        modulo = por_ruta.get(ruta)
        if modulo is None:
            raise SeleccionInvalida(
                f"El módulo no existe o no contiene objetivos analizables: {ruta}"
            )
        funciones_reales = {f.get("nombre"): f for f in modulo.get("funciones", [])}
        endpoints_reales = {e.get("objetivo"): e for e in modulo.get("endpoints", [])}
        inexistentes_fn = [
            nombre for nombre in funciones if nombre not in funciones_reales
        ]
        inexistentes_ep = [
            objetivo for objetivo in endpoints if objetivo not in endpoints_reales
        ]
        componentes_reales = {c.get("nombre"): c for c in modulo.get("componentes", [])}
        inexistentes_co = [n for n in componentes if n not in componentes_reales]
        integraciones_reales = {
            i.get("nombre"): i for i in modulo.get("integraciones", [])
        }
        inexistentes_in = [n for n in integraciones if n not in integraciones_reales]
        if inexistentes_fn or inexistentes_ep or inexistentes_co or inexistentes_in:
            inexistentes = ", ".join(
                inexistentes_fn + inexistentes_ep + inexistentes_co + inexistentes_in
            )
            raise SeleccionInvalida(f"Objetivos inexistentes en {ruta}: {inexistentes}")
        if not funciones and not endpoints and not componentes and not integraciones:
            raise SeleccionInvalida(
                f"El módulo no tiene objetivos seleccionados: {ruta}"
            )
        no_seleccionadas = [
            nombre
            for nombre in criticas
            if nombre not in funciones and nombre not in endpoints
        ]
        if no_seleccionadas:
            raise SeleccionInvalida(
                "Funciones o endpoints marcados para profundizar que no están "
                f"seleccionadas en {ruta}: {', '.join(no_seleccionadas)}"
            )

        filtrado = dict(modulo)
        filtrado["funciones"] = [
            {**funciones_reales[nombre], "critical": nombre in criticas}
            for nombre in funciones
        ]
        filtrado["endpoints"] = [
            {**endpoints_reales[objetivo], "critical": objetivo in criticas}
            for objetivo in endpoints
        ]
        if "componentes" in modulo:
            filtrado["componentes"] = [
                componentes_reales[nombre] for nombre in componentes
            ]
        filtrado.pop("integraciones", None)
        if integraciones:
            filtrado["integraciones"] = [
                integraciones_reales[nombre] for nombre in integraciones
            ]
            filtrado["funciones"].extend(
                {
                    **funciones_reales[nombre],
                    "critical": False,
                    "solo_integracion": True,
                }
                for nombre in integraciones
                if nombre not in funciones and nombre in funciones_reales
            )
        filtrados.append(filtrado)

    return filtrados


def _sin_integraciones(modulo: dict[str, Any]) -> dict[str, Any]:
    """Copia del módulo sin las cadenas candidatas: no se piden, no se ejecutan."""
    if "integraciones" not in modulo:
        return modulo
    return {k: v for k, v in modulo.items() if k != "integraciones"}


def _lista_unica_de_textos(valor: Any) -> bool:
    """Comprueba que el valor sea una lista no ambigua de textos no vacíos."""
    return (
        isinstance(valor, list)
        and all(isinstance(item, str) and bool(item) for item in valor)
        and len(valor) == len(set(valor))
    )

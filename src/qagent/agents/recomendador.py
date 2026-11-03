"""Agente Recomendador por reglas: qué tipos de prueba conviene hacer (#197, ADR-011).

Después del análisis estático y antes de la corrida, convierte un resumen mínimo de
la Vista previa en una lista ordenada de tipos de prueba, cada uno con su motivo,
en el contrato ``recommendation.v1``.

Reglas que no se rompen (ADR-008 y ADR-011):

* Es determinista y no usa ningún LLM (0 tokens). Si más adelante se agrega un modo
  con IA (#200), estas reglas siguen siendo la autoridad y el respaldo.
* Solo recomienda lo que declara en ``tipos_prueba`` el adaptador con el que se
  analizó el proyecto (el de la Vista previa) y que además tiene objetivos. Lo que
  un lenguaje detectado aún no ejecuta va aparte, como «próximamente».
* Los motivos no nombran frameworks: lo propio de cada lenguaje vive en su
  adaptador (ADR-007).
* Informa y nada más: no inicia corridas, no cambia la selección del usuario y no
  entra en la máquina de estados del orquestador.
* Trabaja sobre una proyección hecha por lista permitida (cantidades, rutas HTTP y
  capacidades), nunca sobre el objeto completo de la Vista previa ni el código.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

from qagent import contracts
from qagent.lenguajes import REGISTRO, Deteccion, Registro

_log = logging.getLogger(__name__)

#: Cuántas rutas HTTP de ejemplo entran en la proyección y en el motivo.
MAX_RUTAS_EJEMPLO = 3
#: Largo máximo de una ruta HTTP de ejemplo (es un dato del proyecto, no confiable).
MAX_LARGO_RUTA = 80

Proyeccion = dict[str, Any]


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _detectados(n: int) -> str:
    return "Se detectó 1 archivo" if n == 1 else f"Se detectaron {n} archivos"


def _recortar(texto: str, largo: int = MAX_LARGO_RUTA) -> str:
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _es_critico(objetivo: dict[str, Any]) -> bool:
    return bool(objetivo.get("critica_propuesta", (objetivo.get("ramas") or 0) > 0))


def _endpoint_resuelto(endpoint: dict[str, Any]) -> bool:
    return bool(endpoint.get("objetivo")) and endpoint.get("resuelta") is not False


# --- Entrada: proyección mínima ------------------------------------------------


def proyectar(
    vista: dict[str, Any],
    detecciones: Sequence[Deteccion],
    registro: Registro = REGISTRO,
) -> Proyeccion:
    """Resumen mínimo de la Vista previa que usan las reglas (ADR-011 §5.1).

    Se arma campo por campo (lista permitida): lenguajes detectados con sus
    capacidades, cantidades de objetivos, algunas rutas HTTP y cuántos objetivos
    se proponen como críticos. No copia código, docstrings ni rutas de archivos.

    Los objetivos de la vista salen de un solo adaptador (``vista["lenguaje"]``):
    solo ese lenguaje aporta tipos soportados. Si la vista no lo indica, cuentan
    todos los adaptadores completos detectados.

    Args:
        vista: resultado de ``generar_vista_previa`` (módulos con funciones y
            endpoints, ya anotados con ``critica_propuesta``).
        detecciones: lenguajes del proyecto (``Registro.detectar``).
        registro: registro de adaptadores que declara las capacidades.
    """
    analizado = vista.get("lenguaje")
    lenguajes = []
    for deteccion in detecciones:
        if not deteccion.archivos:
            continue
        adaptador = registro.adaptador_para(deteccion.lenguaje)
        aporta = adaptador.completo and analizado in (None, adaptador.lenguaje)
        lenguajes.append(
            {
                "lenguaje": adaptador.lenguaje,
                "nombre": adaptador.nombre_visible,
                "archivos": deteccion.archivos,
                "analizado": adaptador.lenguaje == analizado,
                "tipos_prueba_soportados": list(adaptador.tipos_prueba)
                if aporta
                else [],
                "tipos_prueba_previstos": list(adaptador.tipos_prueba_previstos),
            }
        )

    modulos = vista.get("modulos") or []
    funciones = [f for m in modulos for f in m.get("funciones") or []]
    endpoints = [e for m in modulos for e in m.get("endpoints") or []]
    resueltos = [e for e in endpoints if _endpoint_resuelto(e)]
    criticos = sum(1 for f in funciones if _es_critico(f)) + sum(
        1 for e in resueltos if _es_critico(e)
    )
    return {
        "lenguajes": lenguajes,
        "objetivos": {
            "funciones": {
                "cantidad": len(funciones),
                "documentadas": sum(
                    1 for f in funciones if f.get("docstring") and f.get("tipada")
                ),
            },
            "endpoints": {
                "cantidad": len(resueltos),
                "sin_resolver": len(endpoints) - len(resueltos),
                "rutas_http": [
                    _recortar(e["objetivo"]) for e in resueltos[:MAX_RUTAS_EJEMPLO]
                ],
            },
        },
        "objetivos_critical": criticos,
        "hay_objetivos_critical": criticos > 0,
    }


# --- Reglas -----------------------------------------------------------------------


def tipos_soportados(proyeccion: Proyeccion) -> set[str]:
    """Tipos operativos del adaptador analizado (o de los completos detectados)."""
    return {
        tipo
        for lenguaje in proyeccion.get("lenguajes", [])
        for tipo in lenguaje.get("tipos_prueba_soportados", [])
    }


def tipos_elegibles(proyeccion: Proyeccion) -> set[str]:
    """Tipos soportados que además tienen objetivos en el proyecto (ADR-011 §5.2)."""
    objetivos = proyeccion["objetivos"]
    con_objetivos = set()
    if objetivos["funciones"]["cantidad"]:
        con_objetivos.add("funcion")
    if objetivos["endpoints"]["cantidad"]:
        con_objetivos.add("endpoint")
    if proyeccion.get("hay_objetivos_critical") and con_objetivos:
        con_objetivos.add("mutacion")
    return tipos_soportados(proyeccion) & con_objetivos


def _motivo_endpoint(endpoints: dict[str, Any]) -> str:
    n = endpoints["cantidad"]
    ejemplos = ", ".join(endpoints["rutas_http"])
    encontrados = (
        f"Se encontró 1 endpoint con ruta resuelta ({ejemplos})"
        if n == 1
        else f"Se encontraron {n} endpoints con ruta resuelta (por ejemplo, {ejemplos})"
    )
    motivo = (
        f"{encontrados}. Se prueban en el sandbox, sin red y comparando contra lo "
        "que declara cada ruta."
    )
    if endpoints["sin_resolver"]:
        motivo += (
            f" {_plural(endpoints['sin_resolver'], 'otro', 'otros')} no se "
            "pueden probar porque su ruta no se pudo resolver."
        )
    return motivo


def _motivo_funcion(funciones: dict[str, Any]) -> str:
    total, documentadas = funciones["cantidad"], funciones["documentadas"]
    if documentadas == total:
        todas = (
            "La única función pública tiene"
            if total == 1
            else f"Las {total} funciones públicas tienen"
        )
        return (
            f"{todas} tipos y documentación: hay de dónde sacar los valores esperados."
        )

    if documentadas:
        return (
            f"{documentadas} de {_plural(total, 'función pública', 'funciones públicas')} "
            "tienen tipos y documentación. Las demás tendrán un oráculo débil hasta "
            "que se documenten."
        )
    return (
        f"Hay {_plural(total, 'función pública', 'funciones públicas')}, pero ninguna "
        "tiene tipos y documentación: los valores esperados serán débiles. "
        "Documentarlas mejora las pruebas."
    )


def _motivo_mutacion(criticos: int) -> str:
    propuestos = (
        "1 objetivo con decisiones (condiciones o excepciones) se propone como crítico"
        if criticos == 1
        else f"{criticos} objetivos con decisiones (condiciones o excepciones) se "
        "proponen como críticos"
    )
    return (
        f"{propuestos}. La mutación comprueba si sus pruebas detectan errores; va al "
        "final porque necesita las pruebas anteriores."
    )


def recomendar(proyeccion: Proyeccion) -> dict[str, Any]:
    """Lista ordenada de tipos de prueba recomendados, en ``recommendation.v1``.

    Orden: endpoints (cubren más comportamiento por prueba), después unitarias y al
    final la mutación de los objetivos críticos, que se apoya en las anteriores.
    Si no hay nada elegible, la lista está vacía.
    """
    elegibles = tipos_elegibles(proyeccion)
    objetivos = proyeccion["objetivos"]
    recomendaciones = []
    if "endpoint" in elegibles:
        recomendaciones.append(
            {
                "tipo_prueba": "endpoint",
                "motivo": _motivo_endpoint(objetivos["endpoints"]),
            }
        )
    if "funcion" in elegibles:
        recomendaciones.append(
            {
                "tipo_prueba": "funcion",
                "motivo": _motivo_funcion(objetivos["funciones"]),
            }
        )
    if "mutacion" in elegibles:
        recomendaciones.append(
            {
                "tipo_prueba": "mutacion",
                "motivo": _motivo_mutacion(proyeccion["objetivos_critical"]),
            }
        )
    return validar_recomendacion(
        {"version": "1", "origen": "reglas", "recomendaciones": recomendaciones},
        proyeccion,
    )


def validar_recomendacion(dato: Any, proyeccion: Proyeccion) -> dict[str, Any]:
    """Valida una recomendación; si no sirve, devuelve una lista vacía (ADR-011 §5.3).

    Primero el schema (``recommendation.v1``) y después las capacidades: cada tipo
    debe estar entre los elegibles del proyecto. Una salida inválida nunca se
    muestra a medias.
    """
    vacia = {"version": "1", "origen": "reglas", "recomendaciones": []}
    try:
        contracts.validar_versionado(contracts.FAMILIA_RECOMMENDATION, dato)
    except (contracts.ContratoInvalido, ValueError) as exc:
        _log.error("Recomendación descartada por no cumplir el contrato: %s", exc)
        return vacia
    elegibles = tipos_elegibles(proyeccion)
    fuera = [
        r["tipo_prueba"]
        for r in dato["recomendaciones"]
        if r["tipo_prueba"] not in elegibles
    ]
    if fuera:
        _log.error("Recomendación descartada: tipos no elegibles %s", fuera)
        return vacia
    return dato


def proximamente(proyeccion: Proyeccion) -> list[dict[str, Any]]:
    """Lenguajes detectados con tipos de prueba aprobados que aún no funcionan.

    No forman parte de la recomendación: la Vista previa los muestra aparte, como
    «próximamente», para que la persona sepa que esa parte del proyecto no se probará.
    """
    pendientes = []
    for lenguaje in proyeccion.get("lenguajes", []):
        tipos = [
            t
            for t in lenguaje.get("tipos_prueba_previstos", [])
            if t not in lenguaje.get("tipos_prueba_soportados", [])
        ]
        if not tipos:
            continue
        nombre = lenguaje["nombre"]
        pendientes.append(
            {
                "lenguaje": lenguaje["lenguaje"],
                "nombre": nombre,
                "tipos_prueba": tipos,
                "motivo": (
                    f"{_detectados(lenguaje['archivos'])} de {nombre}. QAgent "
                    "todavía no ofrece estos tipos de prueba para el lenguaje."
                ),
            }
        )
    return pendientes


def recomendar_para_vista(
    vista: dict[str, Any],
    raiz: str | os.PathLike[str],
    registro: Registro = REGISTRO,
) -> dict[str, Any]:
    """Recomendación y «próximamente» para la Vista previa del proyecto en ``raiz``.

    Returns:
        ``{"recomendacion": <recommendation.v1>, "proximamente": [...]}``.
    """
    proyeccion = proyectar(vista, registro.detectar(raiz), registro)
    return {
        "recomendacion": recomendar(proyeccion),
        "proximamente": proximamente(proyeccion),
    }

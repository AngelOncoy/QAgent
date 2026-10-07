"""Vista previa del proyecto — HU-04.

Como equipo de QA, quiero ver automáticamente los módulos y funciones del
proyecto con sus tipos, documentación y número de ramas, para saber qué se va a
probar sin mapearlo a mano.

Criterios de aceptación (HU-04):
1. Dado un proyecto abierto, la Vista previa muestra el árbol de módulos .py y,
   por cada función pública: firma, si tiene tipos, si tiene docstring y número
   de ramas (if/else, try/except).
2. La información se obtiene por análisis estático (AST): el código del usuario
   no se ejecuta.
3. La carpeta tests/ existente y la carpeta .pyagent/ se ignoran.
4. Las funciones sin docstring se marcan "⚠ falta" con el aviso: el valor esperado
   no tendrá fuente (oráculo débil).
5. Un archivo con error de sintaxis se marca "no se pudo analizar" sin detener el
   análisis del resto.
6. La Vista previa muestra el resumen del proyecto: módulos encontrados,
   funciones públicas, errores (archivos no analizables) e inconsistencias
   (funciones sin docstring o sin tipos), con su porcentaje sobre el total de
   funciones; los valores coinciden con el JSON de EN-02.
7. Los módulos se listan priorizados: primero los que tienen más funciones con
   ramas.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pyagent.analysis.analyzer import analizar_proyecto

AVISO_ORACULO_DEBIL = "el valor esperado no tendrá fuente (oráculo débil)"
ETIQUETA_FALTA_DOCSTRING = "⚠ falta"
ETIQUETA_NO_ANALIZABLE = "no se pudo analizar"


def contar_funciones_con_ramas(modulo: dict[str, Any]) -> int:
    """Cuenta cuántas funciones públicas del módulo tienen al menos una rama."""
    return sum(1 for f in modulo.get("funciones", []) if f.get("ramas", 0) > 0)


def contar_total_ramas(modulo: dict[str, Any]) -> int:
    """Suma todas las ramas de las funciones públicas del módulo."""
    return sum(f.get("ramas", 0) for f in modulo.get("funciones", []))


def priorizar_modulos(modulos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prioriza los módulos: primero los que tienen más funciones con ramas (criterio 7).

    En caso de empate, prioriza por total acumulado de ramas y luego por ruta alfabética.
    """

    def clave_orden(m: dict[str, Any]) -> tuple[int, int, str]:
        return (
            -contar_funciones_con_ramas(m),
            -contar_total_ramas(m),
            m.get("ruta", "").lower(),
        )

    return sorted(modulos, key=clave_orden)


def generar_vista_previa(raiz: str | os.PathLike[str]) -> dict[str, Any]:
    """Genera los datos de la Vista previa para un proyecto dado (HU-04).

    Utiliza análisis estático (AST) mediante :func:`analizar_proyecto` (EN-02),
    prioriza los módulos por funciones con ramas, enriquece las funciones con
    avisos de documentación y conserva el resumen exacto de EN-02.

    Returns:
        dict con ``ok``, ``ruta``, ``nombre``, ``modulos`` (priorizados),
        ``errores`` (archivos no analizables), ``resumen`` (métricas e
        inconsistencias EN-02) y ``avisos``.
    """
    carpeta = Path(raiz)
    if not carpeta.is_dir():
        return {
            "ok": False,
            "error": f"La ruta no es una carpeta válida: {raiz}",
            "modulos": [],
            "errores": [],
            "resumen": {
                "total_modulos": 0,
                "total_funciones_publicas": 0,
                "total_errores": 0,
                "inconsistencias": {
                    "sin_docstring": {"cantidad": 0, "porcentaje": 0.0},
                    "sin_tipos": {"cantidad": 0, "porcentaje": 0.0},
                    "con_alguna": {"cantidad": 0, "porcentaje": 0.0},
                },
            },
            "avisos": {
                "oraculo_debil": AVISO_ORACULO_DEBIL,
                "falta_docstring": ETIQUETA_FALTA_DOCSTRING,
                "no_analizable": ETIQUETA_NO_ANALIZABLE,
            },
        }

    resultado_ast = analizar_proyecto(carpeta)

    # Anotamos los módulos con su conteo de funciones con ramas y aviso en funciones sin docstring
    modulos_procesados: list[dict[str, Any]] = []
    for mod in resultado_ast["modulos"]:
        funciones_mod: list[dict[str, Any]] = []
        for f in mod.get("funciones", []):
            doc = f.get("docstring")
            aviso_doc = AVISO_ORACULO_DEBIL if doc is None else None
            etiqueta_doc = ETIQUETA_FALTA_DOCSTRING if doc is None else "✓"
            funciones_mod.append(
                {
                    **f,
                    "aviso_docstring": aviso_doc,
                    "etiqueta_docstring": etiqueta_doc,
                    "critica_propuesta": f.get("ramas", 0) > 0,
                }
            )
        mod_copia = {
            **mod,
            "funciones": funciones_mod,
            "funciones_con_ramas": sum(
                1 for f in funciones_mod if f.get("ramas", 0) > 0
            ),
            "total_ramas": sum(f.get("ramas", 0) for f in funciones_mod),
        }
        modulos_procesados.append(mod_copia)

    # Priorización: primero los módulos con más funciones con ramas (criterio 7)
    modulos_priorizados = priorizar_modulos(modulos_procesados)

    # Errores con su etiqueta "no se pudo analizar" (criterio 5)
    errores_procesados = [
        {
            **err,
            "etiqueta": ETIQUETA_NO_ANALIZABLE,
        }
        for err in resultado_ast["errores"]
    ]

    return {
        "ok": True,
        "ruta": str(carpeta.resolve()),
        "nombre": carpeta.name or str(carpeta),
        "modulos": modulos_priorizados,
        "errores": errores_procesados,
        "resumen": resultado_ast["resumen"],
        "avisos": {
            "oraculo_debil": AVISO_ORACULO_DEBIL,
            "falta_docstring": ETIQUETA_FALTA_DOCSTRING,
            "no_analizable": ETIQUETA_NO_ANALIZABLE,
        },
    }

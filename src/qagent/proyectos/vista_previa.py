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
3. La carpeta tests/ existente y la carpeta .qagent/ se ignoran.
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

#197: además recomienda qué tipos de prueba conviene hacer y en qué orden
(``recomendacion``, contrato ``recommendation.v1``) y lista como ``proximamente`` los
lenguajes detectados que QAgent todavía no prueba. La interfaz solo las muestra y el
usuario decide si las aplica.

#200: con ``modo = "ia"`` en ``[agentes.recomendador]`` un LLM ordena y justifica esos
tipos (``recomendacion.origen == "ia"``); sin clave, con error o fuera de tiempo se
usan las reglas. Su consumo de tokens y costo sale en ``consumo_recomendador``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from qagent.agents.recomendador import AGENTE as AGENTE_RECOMENDADOR
from qagent.agents.recomendador import RecomendadorConIA, recomendar_para_vista
from qagent.agents.recomendador_ia import crear_recomendador_ia
from qagent.lenguajes import (
    LenguajeNoSoportado,
    adaptador_del_proyecto,
    adaptador_e2e_del_proyecto,
)
from qagent.llm.tracker import TokenTracker

_log = logging.getLogger(__name__)

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


def _recomendador_configurado() -> RecomendadorConIA | None:
    """El Recomendador con IA si `[agentes.recomendador]` tiene `modo = "ia"` (#200).

    None (reglas) con `modo = "reglas"`, sin configuración válida o sin clave: la Vista
    previa nunca depende de que el LLM esté disponible.
    """
    from qagent.config import carga as config_carga
    from qagent.config import cargar_configuracion

    try:
        # Primero solo la configuración (sin tocar `.env`): con `modo = "reglas"`, el
        # valor predeterminado, la Vista previa no necesita nada más.
        previa = cargar_configuracion(
            simulado=True, ruta_local=config_carga.RUTA_CONFIG_LOCAL
        )
        if previa.config is None or previa.config.recomendador.modo != "ia":
            return None
        carga = cargar_configuracion(ruta_local=config_carga.RUTA_CONFIG_LOCAL)
        return crear_recomendador_ia(
            previa.config.recomendador,
            TokenTracker(),
            carga.claves,
            simulado=carga.simulado,
        )
    except Exception as error:  # noqa: BLE001 — la IA es opcional
        _log.warning("Recomendación con reglas, sin IA: %s", error)
        return None


def _recomendar(
    vista: dict[str, Any],
    carpeta: Path,
    recomendador: RecomendadorConIA | None,
) -> dict[str, Any]:
    """Recomendación de la Vista previa y, si hubo IA, lo que consumió (#200)."""
    if recomendador is None:
        recomendador = _recomendador_configurado()
    resultado = recomendar_para_vista(vista, carpeta, recomendador=recomendador)
    consumo = (
        recomendador.tracker.totales_por_agente().get(AGENTE_RECOMENDADOR)
        if recomendador is not None
        else None
    )
    if consumo is not None:
        resultado["consumo_recomendador"] = consumo
    return resultado


def generar_vista_previa(
    raiz: str | os.PathLike[str], *, recomendador: RecomendadorConIA | None = None
) -> dict[str, Any]:
    """Genera los datos de la Vista previa para un proyecto dado (HU-04).

    Utiliza el análisis estático del adaptador elegido por el registro,
    prioriza los módulos por funciones con ramas, enriquece las funciones con
    avisos de documentación y conserva el resumen exacto de EN-02.

    Args:
        raiz: carpeta del proyecto.
        recomendador: Recomendador con IA (#200); si es None se crea el de
            ``[agentes.recomendador]`` cuando su modo es ``ia``.

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
            "recomendacion": {
                "version": "1",
                "origen": "reglas",
                "recomendaciones": [],
            },
            "proximamente": [],
        }

    solo_e2e = False
    try:
        adaptador = adaptador_del_proyecto(carpeta)
    except LenguajeNoSoportado as error:
        try:
            adaptador = adaptador_e2e_del_proyecto(carpeta)
            solo_e2e = True
        except (LenguajeNoSoportado, LookupError):
            # #197: sin objetivos no hay recomendación, pero sí lo que viene
            # «próximamente» para los lenguajes detectados.
            return {
                "ok": False,
                "error": str(error),
                "modulos": [],
                "errores": [],
                **recomendar_para_vista({"modulos": []}, carpeta),
            }
    resultado_ast = adaptador.analizar(carpeta)

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
        # #74: un endpoint con decisiones en su manejador se propone para profundizar,
        # con la misma regla que una función.
        endpoints_mod = [
            {**e, "critica_propuesta": e.get("ramas", 0) > 0}
            for e in mod.get("endpoints", [])
        ]
        mod_copia = {
            **mod,
            "funciones": funciones_mod,
            "endpoints": endpoints_mod,
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

    vista = {
        "ok": True,
        "ruta": str(carpeta.resolve()),
        "nombre": carpeta.name or str(carpeta),
        "lenguaje": adaptador.lenguaje,
        "nombre_lenguaje": adaptador.nombre_visible,
        "framework_pruebas": adaptador.frameworks_pruebas[0],
        "solo_e2e": solo_e2e,
        "e2e_humo_disponible": adaptador.e2e_humo_disponible,
        "modulos": modulos_priorizados,
        "errores": errores_procesados,
        "resumen": resultado_ast["resumen"],
        # #171: React se prueba; otro framework de interfaz se avisa como
        # «componentes no soportados» y solo se prueba la lógica.
        "framework_ui": resultado_ast.get("framework_ui"),
        "avisos": {
            "oraculo_debil": AVISO_ORACULO_DEBIL,
            "falta_docstring": ETIQUETA_FALTA_DOCSTRING,
            "no_analizable": ETIQUETA_NO_ANALIZABLE,
        },
    }
    # #197/#200: recomendación (reglas o IA). Solo informa; no cambia la selección.
    return {**vista, **_recomendar(vista, carpeta, recomendador)}

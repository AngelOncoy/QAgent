"""HU-23: Historial de corridas del proyecto y apertura de reportes.

Criterios de Aceptación:
1. Tabla con cada corrida: número, fecha, perfil, modelos, specs (generados o
   reutilizados), Pass Rate, tokens y costo.
2. Se guarda en .qagent/runs/ y persiste entre sesiones.
3. Desde cada fila se abre el reporte de esa corrida.
4. Evidencia de aceptación: tras 2 corridas y reiniciar la aplicación, el Historial
   lista ambas con sus valores y cada fila abre su reporte.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("webview")

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.app.desktop import DesktopAPI
from qagent.llm import cargar_precios
from qagent.storage import escribir_corrida
from tests.storage.test_registro import correr

METAS = {
    "pass_rate_min": 60.0,
    "cobertura_lineas_min": 60.0,
    "iteraciones_promedio_max": 2.0,
    "tope_por_corrida_usd": 10.0,
}

CONTRATO = json.loads(
    (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
        encoding="utf-8"
    )
)


def _crear_corrida_con_datos(
    raiz: Path,
    perfil: str,
    decision: str = "accept",
    specs_estado: str = "generado",
) -> tuple[str, dict]:
    """Crea una corrida real con run.json, results.json, log.json y detalle.json."""
    almacen = AlmacenProyecto(raiz)
    precios = cargar_precios()
    tracker, resultado = correr(precios, decisiones=(decision,))
    rutas = escribir_corrida(raiz, resultado, tracker, precios, perfil, metas=METAS)

    # Registra run en AlmacenProyecto
    from datetime import datetime

    momento = datetime.now().astimezone().isoformat(timespec="seconds")
    run = {
        "run_id": rutas.run_id,
        "inicio": momento,
        "fin": None,
        "tipos_prueba": ["funcion"],
        "imagen_docker": "qagent-sandbox:base",
        "estado": "en_curso",
        "resumen": None,
    }
    almacen.guardar_run(run)
    plan = almacen.guardar_plan_modulo(
        CONTRATO["modulo"],
        CONTRATO["huella"],
        [CONTRATO],
        rutas.run_id,
        specs_estado,
    )
    almacen.registrar_specs_run(
        rutas.run_id,
        [
            {
                "modulo": plan["modulo"],
                "huella": plan["huella"],
                "run_origen": plan["run_origen"],
                "estado": specs_estado,
            }
        ],
    )
    pasaron = 1 if decision == "accept" else 0
    fallaron = 0 if decision == "accept" else 1
    almacen.finalizar_run(rutas.run_id, "fin", pasaron=pasaron, fallaron=fallaron)
    return rutas.run_id, {
        "pasaron": pasaron,
        "fallaron": fallaron,
        "perfil": perfil,
        "specs_estado": specs_estado,
    }


def test_criterio1_y_criterio2_corridas_guardadas_en_runs_y_tabla_con_todos_los_campos(
    tmp_path: Path,
) -> None:
    """Criterios 1 y 2: se guarda en .qagent/runs/ y devuelve todos los campos requeridos."""
    run_id, _info = _crear_corrida_con_datos(tmp_path, perfil="deep")

    # Verifica que se guardó en .qagent/runs/<run_id>/
    carpeta_run = tmp_path / ".qagent" / "runs" / run_id
    assert carpeta_run.is_dir()
    assert (carpeta_run / "run.json").is_file()
    assert (carpeta_run / "results.json").is_file()
    assert (carpeta_run / "log.json").is_file()
    assert (carpeta_run / "detalle.json").is_file()

    api = DesktopAPI()
    historial = api.obtener_historial(str(tmp_path))
    assert historial["ok"] is True
    assert len(historial["corridas"]) == 1

    fila = historial["corridas"][0]
    # 1. número (run_id)
    assert fila["run_id"] == run_id
    # 2. fecha
    assert fila["fecha"]
    # 3. perfil (y su nombre legible, #70)
    assert fila["perfil"] == "deep"
    assert fila["perfil_nombre"] == "Estándar + profundizar"
    # 4. modelos
    assert isinstance(fila["modelos"], dict)
    assert set(fila["modelos"].keys()) == {"planner", "generator", "reviewer"}
    # 5. specs (generados o reutilizados)
    assert fila["resumen_specs"]["generado"] == 1
    assert fila["resumen_specs"]["reutilizado"] == 0
    # 6. Pass Rate
    assert fila["pass_rate"] == 100.0
    # 7. tokens y costo
    assert fila["total_tokens"] > 0
    assert fila["tokens_planner"] >= 0
    assert fila["costo_usd"] > 0.0


def test_criterio3_desde_cada_fila_se_abre_el_reporte_de_esa_corrida(
    tmp_path: Path,
) -> None:
    """Criterio 3: desde cada fila se abre el reporte de esa corrida con sus datos individuales."""
    run_1, _ = _crear_corrida_con_datos(tmp_path, perfil="deep", decision="accept")
    run_2, _ = _crear_corrida_con_datos(
        tmp_path, perfil="quick", decision="bug_detectado"
    )

    api = DesktopAPI()
    historial = api.obtener_historial(str(tmp_path))
    assert len(historial["corridas"]) == 2

    # Abrir reporte de la corrida 1 usando su run_id de la fila
    rep_1 = api.obtener_reporte(str(tmp_path), run_id=run_1)
    assert rep_1["ok"] is True
    assert rep_1["run_id"] == run_1
    assert rep_1["perfil"] == "deep"
    assert rep_1["indicadores"]["pass_rate"]["valor"] == 100.0
    assert len(rep_1["funciones"]) == 1
    assert rep_1["funciones"][0]["verde"] is True

    # Abrir reporte de la corrida 2 usando su run_id de la fila
    rep_2 = api.obtener_reporte(str(tmp_path), run_id=run_2)
    assert rep_2["ok"] is True
    assert rep_2["run_id"] == run_2
    assert rep_2["perfil"] == "quick"
    assert rep_2["indicadores"]["pass_rate"]["valor"] == 0.0
    assert len(rep_2["funciones"]) == 1
    assert rep_2["funciones"][0]["verde"] is False


def test_criterio4_evidencia_dos_corridas_y_reinicio_aplicacion(
    tmp_path: Path,
) -> None:
    """Criterio 4 (Evidencia de aceptación):

    Tras 2 corridas y reiniciar la aplicación, el Historial lista ambas con sus valores
    y cada fila abre su reporte.
    """
    # Sesión 1: Primera corrida (generando specs)
    run_1, _ = _crear_corrida_con_datos(
        tmp_path, perfil="deep", decision="accept", specs_estado="generado"
    )

    # Sesión 1: Segunda corrida (reutilizando specs)
    run_2, _ = _crear_corrida_con_datos(
        tmp_path, perfil="std", decision="accept", specs_estado="reutilizado"
    )

    # "Reiniciar la aplicación": se instancia una nueva sesión de DesktopAPI
    nueva_sesion_api = DesktopAPI()

    historial = nueva_sesion_api.obtener_historial(str(tmp_path))
    assert historial["ok"] is True
    assert len(historial["corridas"]) == 2

    corridas_por_id = {c["run_id"]: c for c in historial["corridas"]}
    assert run_1 in corridas_por_id
    assert run_2 in corridas_por_id

    # Comprueba valores de la primera corrida en el historial
    c1 = corridas_por_id[run_1]
    assert c1["perfil"] == "deep"
    assert c1["resumen_specs"]["generado"] == 1
    assert c1["resumen_specs"]["reutilizado"] == 0
    assert c1["pass_rate"] == 100.0
    assert c1["total_tokens"] > 0
    assert c1["costo_usd"] > 0

    # Comprueba valores de la segunda corrida en el historial
    c2 = corridas_por_id[run_2]
    assert c2["perfil"] == "std"
    assert c2["resumen_specs"]["generado"] == 0
    assert c2["resumen_specs"]["reutilizado"] == 1
    assert c2["pass_rate"] == 100.0
    assert c2["total_tokens"] > 0
    assert c2["costo_usd"] > 0

    # Comprueba que cada fila abre su reporte independiente tras el reinicio
    rep_1 = nueva_sesion_api.obtener_reporte(str(tmp_path), run_id=run_1)
    rep_2 = nueva_sesion_api.obtener_reporte(str(tmp_path), run_id=run_2)

    assert rep_1["ok"] is True and rep_1["run_id"] == run_1
    assert rep_2["ok"] is True and rep_2["run_id"] == run_2
    assert rep_1["perfil"] == "deep"
    assert rep_2["perfil"] == "std"


def test_frontend_historial_conecta_tabla_y_apertura_de_reportes() -> None:
    """Comprueba que la interfaz web de Historial renderiza las columnas y llama a cargarReporteReal."""
    contenido_historial = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "qagent"
        / "frontend"
        / "componentes"
        / "historial"
        / "historial.js"
    ).read_text(encoding="utf-8")
    # El informe dejó de ser una pantalla: abrir una corrida lleva a Resultados (ejecucion.js).
    contenido_resultados = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "qagent"
        / "frontend"
        / "componentes"
        / "ejecucion"
        / "ejecucion.js"
    ).read_text(encoding="utf-8")

    # Columnas de la tabla (Criterio 1)
    assert "<th>Corrida</th>" in contenido_historial
    assert "<th>Fecha</th>" in contenido_historial
    assert "<th>Perfil</th>" in contenido_historial
    assert "<th>Modelos</th>" in contenido_historial
    assert "<th>Specs</th>" in contenido_historial
    assert "<th>Pass Rate</th>" in contenido_historial
    assert "<th>Tokens</th>" in contenido_historial
    assert "<th>Costo</th>" in contenido_historial

    # Conexión con api.obtener_historial
    assert "api.obtener_historial(projectPath)" in contenido_historial

    # Desde cada fila se abren los resultados de esa corrida (Criterio 3)
    assert "cargarEjecucionReal('${escHtml(h.run_id)}')" in contenido_historial

    # Resultados pide a Python esa corrida por runId, su evidencia, y navega a la bandeja
    assert "api.obtener_ejecucion(projectPath, runId || null)" in contenido_resultados
    assert "api.obtener_reporte(projectPath, runId)" in contenido_resultados
    assert "reporteReal = r;" in contenido_resultados
    assert "go('exec')" in contenido_resultados

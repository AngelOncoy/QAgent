"""Aprovisionamiento bajo demanda y ejecución aislada del humo E2E."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.almacenamiento.disco import escribir_json_atomico
from qagent.almacenamiento.proyecto import AlmacenProyecto
from qagent.e2e.deteccion import configuracion_declarada, detectar_plan_e2e
from qagent.e2e.modelos import ConfiguracionE2E
from qagent.sandbox.ejecucion import ejecutar_en_sandbox
from qagent.sandbox.imagen import asegurar_imagen
from qagent.sandbox.modelos import (
    IMAGEN_NAVEGADOR,
    ErrorSandbox,
    LimitesSandbox,
)

ARCHIVO_RESULTADO = "e2e.json"
ARCHIVO_RUNNER = "e2e-result.json"


def ejecutar_humo_e2e(
    project: str | Path,
    *,
    config: ConfiguracionE2E | None = None,
    client: Any = None,
    advance: Any = None,
) -> dict[str, Any]:
    """Detecta, aprovisiona y visita rutas sin LLM ni red durante la corrida."""
    root = Path(project).resolve()
    config = config or configuracion_declarada(root)
    config.validate()
    plan = detectar_plan_e2e(root, config)
    store = AlmacenProyecto(root)
    run = store.crear_run(["e2e_humo"], IMAGEN_NAVEGADOR)
    run_id = run["run_id"]
    folder = store.carpeta_run(run_id)
    started = time.monotonic()
    image = IMAGEN_NAVEGADOR
    raw: dict[str, Any] | None = None
    error: str | None = None
    try:
        image = asegurar_imagen(
            root, imagen=IMAGEN_NAVEGADOR, cliente=client, avanzar=advance
        )
        raw = _run_container(root, folder, plan, config, image, client)
    except (ErrorSandbox, TypeError, ValueError, OSError) as exc:
        error = str(exc)

    duration = round(time.monotonic() - started, 3)
    result = _complete_result(run_id, plan, config, image, raw, error, duration)
    contracts.validar_versionado(contracts.FAMILIA_E2E_RESULT, result)
    escribir_json_atomico(folder / ARCHIVO_RESULTADO, result)
    summary = result["summary"]
    state = "fin" if result["status"] != "sin_veredicto" else "fallo_controlado"
    store.finalizar_run(
        run_id,
        state,
        summary["passed"],
        summary["failed"] + summary["no_verdict"],
        tipos_prueba=["e2e_humo"],
        duracion_s=result["duration_s"],
        total_seleccionados=summary["total"],
        total_procesados=summary["passed"] + summary["failed"],
        tipo_terminacion="e2e_humo",
    )
    return result


def _run_container(
    root: Path,
    destination: Path,
    plan: dict[str, Any],
    config: ConfiguracionE2E,
    image: str,
    client: Any,
) -> dict[str, Any] | None:
    with tempfile.TemporaryDirectory(prefix="qagent-e2e-plan-") as temporary:
        tests = Path(temporary)
        runner_plan = {
            "start_command": plan["start_command"],
            "environment": {},
            "port": plan["port"],
            "routes": plan["routes"],
            "startup_timeout_ms": config.startup_timeout_s * 1000,
            "route_timeout_ms": config.route_timeout_s * 1000,
            "settle_ms": config.settle_ms,
        }
        (tests / "plan.json").write_text(
            json.dumps(runner_plan, ensure_ascii=False), encoding="utf-8"
        )
        captured: dict[str, Any] = {}

        def preserve(_copy: Path, output: Path) -> None:
            result_path = output / ARCHIVO_RUNNER
            if result_path.is_file() and result_path.stat().st_size <= 2_000_000:
                captured["result"] = json.loads(result_path.read_text(encoding="utf-8"))
            source = output / "capturas"
            if source.is_dir():
                target = destination / "capturas"
                target.mkdir(parents=True, exist_ok=True)
                for screenshot in source.glob("*.png"):
                    if screenshot.is_file() and screenshot.stat().st_size <= 20_000_000:
                        shutil.copyfile(screenshot, target / screenshot.name)

        sandbox_result = ejecutar_en_sandbox(
            image,
            ["node", "/opt/qagent/runner.mjs"],
            root,
            tests,
            LimitesSandbox(config.cpus, config.memory, config.total_timeout_s),
            al_terminar=preserve,
            cliente=client,
        )
        if sandbox_result.timed_out:
            return _raw_no_verdict(
                plan["port"], config, "La corrida E2E excedió el tiempo total."
            )
        if sandbox_result.oom_killed:
            return _raw_no_verdict(
                plan["port"],
                config,
                "Chromium o la aplicación excedieron la memoria disponible.",
            )
        if "result" not in captured:
            detail = (sandbox_result.stderr or sandbox_result.stdout or "sin detalle")[
                -2000:
            ]
            return _raw_no_verdict(
                plan["port"], config, f"El ejecutor no produjo resultados: {detail}"
            )
        return captured["result"]


def _raw_no_verdict(port: int, config: ConfiguracionE2E, reason: str) -> dict[str, Any]:
    return {
        "version": "1",
        "status": "sin_veredicto",
        "startup": {
            "ready": False,
            "exit_code": None,
            "port": port,
            "timeout_ms": config.startup_timeout_s * 1000,
            "log": "",
            "reason": reason,
        },
        "routes": [],
        "duration_s": 0.0,
    }


def _complete_result(
    run_id: str,
    plan: dict[str, Any],
    config: ConfiguracionE2E,
    image: str,
    raw: dict[str, Any] | None,
    error: str | None,
    duration: float,
) -> dict[str, Any]:
    raw = raw or _raw_no_verdict(
        plan["port"], config, error or "No se pudo ejecutar el humo E2E."
    )
    routes = raw.get("routes") if isinstance(raw.get("routes"), list) else []
    # Las capturas siempre son relativas a la carpeta de la corrida.
    for item in routes:
        if isinstance(item, dict) and item.get("screenshot"):
            item["screenshot"] = str(item["screenshot"]).replace("\\", "/")
    summary = {
        "total": len(routes),
        "passed": sum(item.get("status") == "cumple" for item in routes),
        "failed": sum(item.get("status") == "falla" for item in routes),
        "no_verdict": sum(item.get("status") == "sin_veredicto" for item in routes),
    }
    if not raw.get("startup", {}).get("ready") and not routes:
        summary["total"] = len(plan["routes"])
        summary["no_verdict"] = len(plan["routes"])
    return {
        "version": "1",
        "run_id": run_id,
        "status": raw.get("status", "sin_veredicto"),
        "language": plan["language"],
        "framework": plan["framework"],
        "image": image,
        "limits": {
            "cpus": config.cpus,
            "memory": config.memory,
            "startup_timeout_s": config.startup_timeout_s,
            "route_timeout_s": config.route_timeout_s,
            "total_timeout_s": config.total_timeout_s,
            "max_routes": config.max_routes,
            "network": "none",
        },
        "startup": raw["startup"],
        "routes": routes,
        "summary": summary,
        "duration_s": max(duration, round(float(raw.get("duration_s", 0.0)), 3)),
        "tokens": 0,
    }


def leer_resultado_e2e(project: str | Path, run_id: str) -> dict[str, Any]:
    """Lee un resultado E2E validado y compatible con corridas futuras."""
    path = AlmacenProyecto(project).carpeta_run(run_id) / ARCHIVO_RESULTADO
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"No se pudo leer el resultado E2E: {error}") from error
    return contracts.validar_versionado(contracts.FAMILIA_E2E_RESULT, data)

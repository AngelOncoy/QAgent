"""Lectura de cobertura de Vitest (@vitest/coverage-v8) en formato común (EP-11a).

Convierte el reporte JSON de Istanbul/NYC (coverage-final.json) al formato común
de coverage.py (files y totals), que interpreta el Reviewer para medir líneas y ramas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qagent.sandbox.ejecucion import leer_coverage

NOMBRES_COBERTURA = (
    "coverage-final.json",
    "coverage/coverage-final.json",
    "coverage.json",
)


def leer_cobertura_v8(dir_salida: str | Path) -> dict[str, Any] | None:
    """Lee el informe de cobertura dejado por Vitest y lo convierte a formato común.

    Devuelve None si el informe no existe o no se puede interpretar.
    """
    raiz = Path(dir_salida)
    if not raiz.is_dir():
        return None

    archivo_py = raiz / "coverage.json"
    if archivo_py.is_file():
        datos = leer_coverage(archivo_py)
        if datos and "files" in datos and "totals" in datos:
            return datos

    for nombre in NOMBRES_COBERTURA:
        archivo = raiz / nombre
        if archivo.is_file():
            try:
                datos = json.loads(archivo.read_text(encoding="utf-8"))
                if isinstance(datos, dict):
                    if "files" in datos and "totals" in datos:
                        return datos
                    return interpretar_cobertura_v8(datos)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
    return None


def interpretar_cobertura_v8(datos_v8: dict[str, Any]) -> dict[str, Any] | None:
    """Convierte el formato Istanbul/NYC (coverage-final.json) a files/totals comunes."""
    archivos: dict[str, Any] = {}
    total_exec = 0
    total_miss = 0
    total_br_exec = 0
    total_br_miss = 0

    for key, file_cov in datos_v8.items():
        if not isinstance(file_cov, dict):
            continue
        rel = file_cov.get("path", key).replace("\\", "/")
        if "/work/proyecto/" in rel:
            rel = rel.split("/work/proyecto/", 1)[-1]
        elif "proyecto/" in rel:
            rel = rel.split("proyecto/", 1)[-1]

        s_map = file_cov.get("statementMap", {})
        s_counts = file_cov.get("s", {})
        executed_lines = set()
        missing_lines = set()
        for s_id, count in s_counts.items():
            st = s_map.get(s_id)
            if not st:
                continue
            line = st.get("start", {}).get("line")
            if line is not None:
                if count > 0:
                    executed_lines.add(int(line))
                else:
                    missing_lines.add(int(line))
        missing_lines -= executed_lines

        b_map = file_cov.get("branchMap", {})
        b_counts = file_cov.get("b", {})
        executed_branches = []
        missing_branches = []
        for b_id, counts in b_counts.items():
            br = b_map.get(b_id)
            line = (
                br.get("line") or br.get("loc", {}).get("start", {}).get("line")
                if br
                else None
            )
            if line is None:
                continue
            for idx, c in enumerate(counts if isinstance(counts, list) else []):
                if c > 0:
                    executed_branches.append([int(line), idx + 1])
                else:
                    missing_branches.append([int(line), -(idx + 1)])

        exec_l = sorted(executed_lines)
        miss_l = sorted(missing_lines)
        n_l = len(exec_l) + len(miss_l)
        pct_l = round(len(exec_l) * 100 / n_l, 2) if n_l else 100.0
        n_b = len(executed_branches) + len(missing_branches)
        pct_b = round(len(executed_branches) * 100 / n_b, 2) if n_b else None

        archivos[rel] = {
            "executed_lines": exec_l,
            "missing_lines": miss_l,
            "executed_branches": executed_branches,
            "missing_branches": missing_branches,
            "summary": {
                "covered_lines": len(exec_l),
                "missing_lines": len(miss_l),
                "num_statements": n_l,
                "percent_covered": pct_l,
                "covered_branches": len(executed_branches),
                "missing_branches": len(missing_branches),
                "num_branches": n_b,
                "percent_branches_covered": pct_b,
            },
        }
        total_exec += len(exec_l)
        total_miss += len(miss_l)
        total_br_exec += len(executed_branches)
        total_br_miss += len(missing_branches)

    if not archivos:
        return None

    tot_l = total_exec + total_miss
    tot_b = total_br_exec + total_br_miss
    totals = {
        "covered_lines": total_exec,
        "missing_lines": total_miss,
        "num_statements": tot_l,
        "percent_covered": round(total_exec * 100 / tot_l, 2) if tot_l else 100.0,
        "covered_branches": total_br_exec,
        "missing_branches": total_br_miss,
        "num_branches": tot_b,
        "percent_branches_covered": (
            round(total_br_exec * 100 / tot_b, 2) if tot_b else None
        ),
    }
    return {"files": archivos, "totals": totals, "coverage_format": "v8"}

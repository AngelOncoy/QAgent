"""Informes legibles y autocontenidos de humo E2E."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import escribir_texto_atomico
from qagent.e2e.ejecucion import leer_resultado_e2e


def construir_markdown(data: dict[str, Any]) -> str:
    """Representa cada ruta, su HTTP, errores y evidencia."""
    lines = [
        f"# Humo E2E · {data['run_id']}",
        "",
        f"**Estado:** {data['status']} · **Framework:** {data['framework']} · **Duración:** {data['duration_s']:.3f} s · **Tokens:** 0",
        "",
        f"**Arranque:** {'listo' if data['startup']['ready'] else 'sin veredicto'} · Puerto {data['startup']['port']}",
        "",
    ]
    if data["startup"]["reason"]:
        lines += [f"> {data['startup']['reason']}", ""]
    for route in data["routes"]:
        lines += [
            f"## `{route['path']}` · {route['status']}",
            "",
            f"- HTTP: {route['http_status'] if route['http_status'] is not None else '—'}",
            f"- Contenido visible: {'sí' if route['visible_content'] else 'no'}",
            f"- Duración: {route['duration_ms']} ms",
        ]
        if route["reason"]:
            lines.append(f"- Motivo: {route['reason']}")
        for label, key in (
            ("Consola", "console_errors"),
            ("JavaScript", "page_errors"),
            ("Red", "request_errors"),
        ):
            for message in route[key]:
                lines.append(f"- {label}: `{message}`")
        if route["screenshot"]:
            lines.append(f"- Captura: `{route['screenshot']}`")
        lines.append("")
    if data["startup"]["log"]:
        lines += [
            "## Log de arranque",
            "",
            "```text",
            data["startup"]["log"],
            "```",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def construir_html(data: dict[str, Any]) -> str:
    """HTML sin red ni scripts, con enlaces relativos a capturas auténticas."""
    sections = []
    for route in data["routes"]:
        errors = "".join(
            f"<li>{html.escape(message)}</li>"
            for key in ("console_errors", "page_errors", "request_errors")
            for message in route[key]
        )
        image = (
            f'<img src="{html.escape(route["screenshot"])}" alt="Captura de {html.escape(route["path"])}">'
            if route["screenshot"]
            else ""
        )
        sections.append(
            f"<section><h2><code>{html.escape(route['path'])}</code> · {html.escape(route['status'])}</h2><p>HTTP {route['http_status'] if route['http_status'] is not None else '—'} · visible: {'sí' if route['visible_content'] else 'no'} · {route['duration_ms']} ms</p><p>{html.escape(route['reason'] or 'Sin errores')}</p><ul>{errors}</ul>{image}</section>"
        )
    return (
        '<!doctype html><html lang="es"><meta charset="utf-8"><title>Humo E2E</title><style>body{font-family:system-ui;max-width:1000px;margin:40px auto;padding:0 20px;color:#18202b}section{border-top:1px solid #d9dde5;padding:18px 0}img{max-width:100%;border:1px solid #ccd2dc}pre{white-space:pre-wrap;background:#f4f6f8;padding:12px}</style>'
        + f"<h1>Humo E2E</h1><p>Corrida {html.escape(data['run_id'])} · <strong>{html.escape(data['status'])}</strong> · 0 tokens</p>"
        + "".join(sections)
        + f"<h2>Log de arranque</h2><pre>{html.escape(data['startup']['log'])}</pre></html>"
    )


def exportar(
    project: str | Path,
    run_id: str,
    format: str = "html",
    destination: str | Path | None = None,
) -> dict[str, Any]:
    """Exporta JSON, Markdown o HTML junto con las capturas de la corrida."""
    fmt = format.lower().strip()
    if fmt not in {"json", "md", "html"}:
        raise ValueError("El formato E2E debe ser json, md o html.")
    data = leer_resultado_e2e(project, run_id)
    folder = (
        Path(destination)
        if destination
        else Path(project) / ".qagent" / "runs" / run_id
    )
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"e2e_{run_id}.{fmt}"
    content = (
        json.dumps(data, indent=2, ensure_ascii=False)
        if fmt == "json"
        else construir_markdown(data)
        if fmt == "md"
        else construir_html(data)
    )
    escribir_texto_atomico(path, content)
    return {"ok": True, "run_id": run_id, "format": fmt, "path": str(path)}

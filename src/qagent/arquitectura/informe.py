"""Exportación autocontenida de resultados arquitectónicos."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import escribir_texto_atomico
from qagent.arquitectura.ejecucion import leer_resultado_arquitectura


def construir_markdown(datos: dict[str, Any]) -> str:
    """Informe Markdown con cada regla y todas sus ubicaciones verificables."""
    lineas = [
        f"# Verificación de arquitectura · {datos['run_id']}",
        "",
        f"**Lenguaje:** {datos['lenguaje']} · **Estado:** {datos['estado']} · **Duración:** {datos['duracion_s']:.3f} s",
        "",
    ]
    for regla in datos["reglas"]:
        lineas.extend(
            [
                f"## {regla['nombre']}",
                "",
                f"- Estado: **{regla['estado']}**",
                f"- Origen: {regla['origen']}",
                f"- Herramienta: {regla['herramienta']}",
            ]
        )
        if regla["motivo_sin_veredicto"]:
            lineas.append(f"- Motivo: {regla['motivo_sin_veredicto']}")
        for hallazgo in regla["hallazgos"]:
            ubicacion = hallazgo["archivo"] or "ubicación no disponible"
            if hallazgo["linea"] is not None:
                ubicacion += f":{hallazgo['linea']}"
            lineas.append(
                f"- Infracción: `{hallazgo['desde']}` → `{hallazgo['hacia']}` ({ubicacion})"
            )
        lineas.append("")
    return "\n".join(lineas).rstrip() + "\n"


def construir_html(datos: dict[str, Any]) -> str:
    """HTML sin scripts ni recursos externos, apto para compartir localmente."""
    secciones = []
    for regla in datos["reglas"]:
        hallazgos = "".join(
            "<li><code>"
            + html.escape(h["desde"])
            + "</code> → <code>"
            + html.escape(h["hacia"])
            + "</code> · "
            + html.escape(h["archivo"] or "ubicación no disponible")
            + (f":{h['linea']}" if h["linea"] else "")
            + "</li>"
            for h in regla["hallazgos"]
        )
        motivo = (
            f"<p>{html.escape(regla['motivo_sin_veredicto'])}</p>"
            if regla["motivo_sin_veredicto"]
            else ""
        )
        secciones.append(
            f"<section><h2>{html.escape(regla['nombre'])}</h2>"
            f"<p><strong>{regla['estado']}</strong> · {html.escape(regla['herramienta'])}</p>"
            f"{motivo}<ul>{hallazgos}</ul></section>"
        )
    return (
        '<!doctype html><html lang="es"><meta charset="utf-8">'
        "<title>Verificación de arquitectura</title><style>body{font-family:system-ui;max-width:900px;margin:40px auto;padding:0 20px;color:#1b1e23}section{border-top:1px solid #d9dde5;padding:16px 0}code{background:#f1f3f6;padding:2px 4px}</style>"
        f"<h1>Verificación de arquitectura</h1><p>Corrida {html.escape(datos['run_id'])} · {html.escape(datos['lenguaje'])} · <strong>{datos['estado']}</strong></p>"
        + "".join(secciones)
        + "</html>"
    )


def construir_pdf(datos: dict[str, Any]) -> bytes:
    """PDF auditable mediante el lienzo sin dependencias externas de QAgent."""
    from qagent.storage.informe_pdf import TEXTO_3, _ensamblar, _Lienzo

    lienzo = _Lienzo(f"Verificación de arquitectura {datos['run_id']}")
    lienzo.titulo_seccion("Verificación de arquitectura")
    lienzo.parrafo(
        f"Corrida {datos['run_id']} · {datos['lenguaje']} · {datos['estado']} · {datos['duracion_s']:.3f} s",
        10,
        "F1",
        TEXTO_3,
    )
    for regla in datos["reglas"]:
        lienzo.titulo_seccion(regla["nombre"])
        lienzo.parrafo(
            f"Estado: {regla['estado']}. Herramienta: {regla['herramienta']}.", 9
        )
        if regla["motivo_sin_veredicto"]:
            lienzo.parrafo(regla["motivo_sin_veredicto"], 9)
        for hallazgo in regla["hallazgos"]:
            lugar = hallazgo["archivo"] or "ubicación no disponible"
            if hallazgo["linea"]:
                lugar += f":{hallazgo['linea']}"
            lienzo.parrafo(f"{hallazgo['desde']} -> {hallazgo['hacia']} ({lugar})", 9)
    return _ensamblar(lienzo.cerrar(), str(datos["run_id"]))


def exportar(
    ruta_proyecto: str | Path,
    run_id: str,
    formato: str,
    destino: str | Path | None = None,
) -> dict[str, Any]:
    """Exporta JSON, Markdown, HTML o PDF en la carpeta de la corrida por defecto."""
    fmt = formato.lower().strip()
    if fmt not in {"json", "md", "html", "pdf"}:
        raise ValueError("El formato debe ser json, md, html o pdf.")
    datos = leer_resultado_arquitectura(ruta_proyecto, run_id)
    carpeta = (
        Path(destino) if destino else Path(ruta_proyecto) / ".qagent" / "runs" / run_id
    )
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"arquitectura_{run_id}.{fmt}"
    if fmt == "json":
        escribir_texto_atomico(ruta, json.dumps(datos, indent=2, ensure_ascii=False))
    elif fmt == "md":
        escribir_texto_atomico(ruta, construir_markdown(datos))
    elif fmt == "html":
        escribir_texto_atomico(ruta, construir_html(datos))
    else:
        ruta.write_bytes(construir_pdf(datos))
    return {"ok": True, "run_id": run_id, "formato": fmt, "ruta": str(ruta)}

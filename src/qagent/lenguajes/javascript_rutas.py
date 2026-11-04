"""Detección estática conservadora de páginas Express/Vite para #186."""

from __future__ import annotations

import json
import re
from pathlib import Path

from qagent.e2e.modelos import RutaWeb
from qagent.lenguajes.registro import listar_archivos

_EXPRESS_ROUTE = re.compile(
    r"\b(?:app|router)\s*\.\s*(get|all)\s*\(\s*(['\"])(/[^'\"]*)\2",
    re.MULTILINE,
)
_JSON_RESPONSE = re.compile(r"\b(?:res\s*\.\s*)?json\s*\(")


def detectar_rutas_web(
    root: Path, extensions: tuple[str, ...]
) -> tuple[list[RutaWeb], list[str], str]:
    """Obtiene rutas literales y un script npm conocido, sin ejecutar el proyecto."""
    package_file = root / "package.json"
    try:
        package = json.loads(package_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Se necesita un package.json legible: {error}") from error
    if not isinstance(package, dict):
        raise TypeError("package.json debe contener un objeto.")
    dependencies = {
        **(package.get("dependencies") or {}),
        **(package.get("devDependencies") or {}),
    }
    if "express" in dependencies:
        framework = "express"
    elif "vite" in dependencies:
        framework = "vite"
    else:
        raise ValueError("El adaptador no detectó Express ni Vite en package.json.")

    scripts = package.get("scripts") or {}
    if not isinstance(scripts, dict):
        scripts = {}
    if framework == "vite" and "dev" in scripts:
        command = ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "4173"]
    elif "start" in scripts:
        command = ["npm", "run", "start"]
    elif framework == "vite" and "preview" in scripts:
        command = [
            "npm",
            "run",
            "preview",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            "4173",
        ]
    else:
        raise ValueError("No hay un script npm start, dev o preview compatible.")

    routes: list[RutaWeb] = []
    if framework == "vite":
        if (root / "index.html").is_file():
            routes.append(RutaWeb("/", "index.html"))
    else:
        for relative in listar_archivos(root):
            if not relative.lower().endswith(extensions):
                continue
            file = root / relative
            try:
                source = file.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            matches = list(_EXPRESS_ROUTE.finditer(source))
            for index, match in enumerate(matches):
                path = match.group(3)
                next_start = (
                    matches[index + 1].start()
                    if index + 1 < len(matches)
                    else match.end() + 1200
                )
                tail = source[match.end() : next_start]
                route_type = "api" if _JSON_RESPONSE.search(tail) else "page"
                routes.append(
                    RutaWeb(
                        path,
                        f"{relative}:{source.count(chr(10), 0, match.start()) + 1}",
                        route_type,
                    )
                )
    if not routes:
        raise ValueError("No se detectaron rutas web literales compatibles.")
    return routes, command, framework

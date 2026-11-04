"""Detección estática y validación de rutas de humo E2E."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from qagent import contracts
from qagent.e2e.modelos import ConfiguracionE2E, RutaWeb
from qagent.lenguajes import REGISTRO
from qagent.lenguajes.base import NoImplementado

ARCHIVO_CONFIG = ".qagent/e2e.json"
_DINAMICA = re.compile(r"(?:[:*][A-Za-z_][\w-]*|\[[^\]]+\]|\{[^}]+\})")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_COMANDOS = {"node", "npm", "npx", "python", "python3"}


def normalizar_ruta(value: str) -> str:
    """Devuelve una ruta local segura; nunca acepta URL, credenciales ni traversal."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("La ruta web debe ser texto no vacío.")
    value = value.strip()
    if _CONTROL.search(value) or "\\" in value:
        raise ValueError("La ruta contiene caracteres no permitidos.")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Solo se permiten rutas locales relativas al origen.")
    if not value.startswith("/") or value.startswith("//"):
        raise ValueError("La ruta debe comenzar con una sola barra.")
    if any(part == ".." for part in parsed.path.split("/")):
        raise ValueError("La ruta no puede contener traversal '..'.")
    return value


def validar_url_local(url: str, port: int) -> bool:
    """Indica si la URL HTTP pertenece exactamente al loopback autorizado."""
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            and (parsed.port or (443 if parsed.scheme == "https" else 80)) == port
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def validar_comando(command: Any) -> list[str]:
    """Acepta argumentos estructurados con un ejecutable limitado, nunca shell."""
    if not isinstance(command, list) or not command:
        raise ValueError("El comando de inicio debe ser una lista no vacía.")
    if not all(
        isinstance(arg, str) and arg and not _CONTROL.search(arg) for arg in command
    ):
        raise ValueError("Cada argumento del comando debe ser texto seguro.")
    executable = Path(command[0]).name.lower()
    if executable not in _COMANDOS:
        raise ValueError(f"El ejecutable '{executable}' no está autorizado para E2E.")
    if any(arg in {"-c", "--eval", "-e"} for arg in command[1:]):
        raise ValueError("No se permiten argumentos que ejecuten código en línea.")
    return list(command)


def leer_declaracion(root: Path) -> dict[str, Any]:
    """Lee la configuración explícita del proyecto sin salir de `.qagent`."""
    path = root / ARCHIVO_CONFIG
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"No se pudo leer {ARCHIVO_CONFIG}: {error}") from error
    if not isinstance(data, dict):
        raise TypeError(f"{ARCHIVO_CONFIG} debe contener un objeto JSON.")
    return data


def configuracion_declarada(root: Path) -> ConfiguracionE2E:
    """Aplica únicamente límites conocidos y acotados desde `.qagent/e2e.json`."""
    declaration = leer_declaracion(root)
    limits = declaration.get("limits", {})
    if not isinstance(limits, dict):
        raise TypeError("limits en .qagent/e2e.json debe ser un objeto.")
    allowed = {
        "port",
        "max_routes",
        "startup_timeout_s",
        "route_timeout_s",
        "total_timeout_s",
        "settle_ms",
        "cpus",
        "memory",
    }
    unknown = sorted(set(limits) - allowed)
    if unknown:
        raise ValueError(f"Límites E2E desconocidos: {', '.join(unknown)}.")
    config = ConfiguracionE2E(**limits)
    config.validate()
    return config


def detectar_plan_e2e(
    project: str | Path, config: ConfiguracionE2E | None = None
) -> dict[str, Any]:
    """Construye el contrato de rutas desde el adaptador y la declaración del usuario."""
    root = Path(project).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"No es una carpeta: {root}")
    declaration = leer_declaracion(root)
    config = config or configuracion_declarada(root)
    config.validate()
    language = REGISTRO.lenguaje_principal(root)
    if language not in {"javascript", "typescript"}:
        raise ValueError(
            "El humo E2E admite proyectos JavaScript y TypeScript compatibles."
        )
    adapter = REGISTRO.adaptador_para(language)
    try:
        detected, detected_command, framework = adapter.rutas_web(root)
    except NoImplementado as error:
        raise ValueError(str(error)) from error

    command = validar_comando(declaration.get("start_command", detected_command))
    declared = declaration.get("routes", [])
    if not isinstance(declared, list):
        raise TypeError("routes en .qagent/e2e.json debe ser una lista.")
    routes = list(detected)
    for value in declared:
        route = value.get("path") if isinstance(value, dict) else value
        normalized = normalizar_ruta(route)
        route_type = value.get("type", "page") if isinstance(value, dict) else "page"
        if route_type not in {"page", "api", "static", "auth"}:
            raise ValueError(f"Tipo de ruta no admitido: {route_type!r}.")
        routes.append(RutaWeb(normalized, "declarada", route_type))

    unique: dict[str, RutaWeb] = {}
    for route in routes:
        normalized = normalizar_ruta(route.path)
        dynamic = bool(_DINAMICA.search(normalized))
        eligible = route.eligible and not dynamic and route.route_type == "page"
        reason = route.reason
        if dynamic:
            reason = (
                "Ruta dinámica sin valores declarados; QAgent no inventa parámetros."
            )
        elif route.route_type != "page":
            reason = f"La ruta es de tipo {route.route_type}, no una página de humo."
        candidate = RutaWeb(
            normalized, route.source, route.route_type, eligible, reason
        )
        previous = unique.get(normalized)
        if previous is None or (
            candidate.source == "declarada" and previous.source != "declarada"
        ):
            unique[normalized] = candidate
    ordered = sorted(unique.values(), key=lambda item: item.path)
    if len(ordered) > config.max_routes:
        ordered = ordered[: config.max_routes]
    plan = {
        "version": "1",
        "language": language,
        "framework": framework,
        "adapter": adapter.__class__.__name__,
        "start_command": command,
        "port": config.port,
        "routes": [route.as_dict() for route in ordered],
    }
    return contracts.validar_versionado(contracts.FAMILIA_E2E_ROUTES, plan)

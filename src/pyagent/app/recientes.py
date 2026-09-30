"""Proyectos recientes (HU-03).

Guarda y lee ``~/.pyagent/recientes.json``. La Bienvenida muestra hasta
``MAX_VISIBLES`` proyectos, del más reciente al más antiguo.
Solo lee el sistema de archivos: nunca ejecuta código del usuario.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_VISIBLES = 10
MAX_GUARDADOS = 50
ORIGENES = ("local", "git")


def ruta_por_defecto() -> Path:
    """Ubicación del archivo de recientes: ``~/.pyagent/recientes.json``."""
    return Path.home() / ".pyagent" / "recientes.json"


def _archivo(archivo: str | Path | None) -> Path:
    return Path(archivo) if archivo else ruta_por_defecto()


def _clave(ruta: str | Path) -> str:
    """Clave para comparar rutas (en Windows no distingue mayúsculas)."""
    return os.path.normcase(os.path.normpath(str(ruta)))


def _valida(d: Any) -> bool:
    return (
        isinstance(d, dict)
        and isinstance(d.get("nombre"), str)
        and isinstance(d.get("ruta"), str)
        and d.get("origen") in ORIGENES
        and isinstance(d.get("ultima_apertura"), str)
    )


def cargar(archivo: str | Path | None = None) -> list[dict[str, Any]]:
    """Lee la lista completa (más reciente primero). Tolera archivo ausente o dañado."""
    try:
        datos = json.loads(_archivo(archivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [d for d in datos if _valida(d)] if isinstance(datos, list) else []


def _guardar(lista: list[dict[str, Any]], archivo: str | Path | None) -> None:
    destino = _archivo(archivo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
        os.replace(tmp, destino)  # escritura atómica
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def registrar(
    nombre: str,
    origen: str,
    ruta: str | Path,
    url: str | None = None,
    archivo: str | Path | None = None,
    ahora: datetime | None = None,
) -> None:
    """Agrega el proyecto al inicio de la lista (o lo sube si ya estaba)."""
    if origen not in ORIGENES:
        raise ValueError(f"origen inválido: {origen!r} (use 'local' o 'git')")
    ruta = str(ruta)
    entrada = {
        "nombre": nombre,
        "origen": origen,
        "ruta": ruta,
        "url": url,
        "ultima_apertura": (ahora or datetime.now()).isoformat(timespec="seconds"),
    }
    resto = [d for d in cargar(archivo) if _clave(d["ruta"]) != _clave(ruta)]
    _guardar([entrada, *resto][:MAX_GUARDADOS], archivo)


def ultima_corrida(ruta: str | Path) -> str | None:
    """Fecha ISO de la corrida más reciente en ``<ruta>/.pyagent/runs/``, o None."""
    runs = Path(ruta) / ".pyagent" / "runs"
    try:
        marcas = [d.stat().st_mtime for d in runs.iterdir() if d.is_dir()]
    except OSError:
        return None
    if not marcas:
        return None
    return datetime.fromtimestamp(max(marcas)).isoformat(timespec="seconds")


def listar(
    limite: int = MAX_VISIBLES, archivo: str | Path | None = None
) -> list[dict[str, Any]]:
    """Proyectos para la Bienvenida, con ``estado`` 'ok' o 'no_encontrada'."""
    salida = []
    for d in cargar(archivo)[:limite]:
        existe = Path(d["ruta"]).is_dir()
        salida.append(
            {
                "nombre": d["nombre"],
                "origen": d["origen"],
                "ruta": d["ruta"],
                "url": d.get("url"),
                "ultima_apertura": d["ultima_apertura"],
                "ultima_corrida": ultima_corrida(d["ruta"]) if existe else None,
                "estado": "ok" if existe else "no_encontrada",
            }
        )
    return salida


def quitar(ruta: str | Path, archivo: str | Path | None = None) -> bool:
    """Quita un proyecto de la lista (no borra nada del disco). True si estaba."""
    lista = cargar(archivo)
    nueva = [d for d in lista if _clave(d["ruta"]) != _clave(ruta)]
    if len(nueva) == len(lista):
        return False
    _guardar(nueva, archivo)
    return True


def abrir(ruta: str | Path, archivo: str | Path | None = None) -> dict[str, Any]:
    """Valida un reciente y lo sube al inicio. Devuelve ``{ok, ...}`` para la interfaz."""
    entrada = next((d for d in cargar(archivo) if _clave(d["ruta"]) == _clave(ruta)), None)
    if entrada is None:
        return {"ok": False, "error": "no_registrada"}
    if not Path(entrada["ruta"]).is_dir():
        return {"ok": False, "error": "no_encontrada"}
    registrar(entrada["nombre"], entrada["origen"], entrada["ruta"], entrada.get("url"), archivo)
    return {"ok": True, "proyecto": entrada}
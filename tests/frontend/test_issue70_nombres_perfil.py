"""#70: el historial y el informe muestran el nombre del perfil que da el backend."""

from __future__ import annotations

from pathlib import Path

COMPONENTES = (
    Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend" / "componentes"
)


def leer(ruta: str) -> str:
    return (COMPONENTES / ruta).read_text(encoding="utf-8")


def test_el_historial_usa_el_nombre_del_backend() -> None:
    historial = leer("historial/historial.js")

    assert "const nomPerfil = h.perfil_nombre || h.perfil || '—';" in historial
    assert "Equilibrado" not in historial  # nombres anteriores a #69

"""El puente de escritorio expone la vista previa a la interfaz (HU-04)."""

from __future__ import annotations

from pathlib import Path

from pyagent.app.desktop import DesktopAPI


def _crear_archivo(raiz: Path, ruta_relativa: str, contenido: str) -> Path:
    destino = raiz / ruta_relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    return destino


def test_desktop_api_obtener_vista_previa(tmp_path: Path) -> None:
    _crear_archivo(
        tmp_path,
        "main.py",
        "def inicio(x: int) -> int:\n    '''Inicio.'''\n    return x\n",
    )
    api = DesktopAPI()
    vista = api.obtener_vista_previa(str(tmp_path))
    assert vista["ok"] is True
    assert len(vista["modulos"]) == 1
    assert vista["modulos"][0]["funciones"][0]["nombre"] == "inicio"

    alias = api.analizar_proyecto(str(tmp_path))
    assert alias == vista

"""Pruebas de integración de la detección y comunicación de recorridos incompletos.

Verifica:
- inspeccionar_carpeta informa estado 'completo' en repositorios normales.
- inspeccionar_carpeta detecta truncamiento y emite aviso cuando se supera el límite.
- generar_vista_previa propaga metadatos de estado y carpetas pendientes.
- La selección del adaptador de lenguaje respeta el alcance realmente explorado.
- La continuación por módulos/carpetas permite completar el análisis sin duplicados.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from qagent.app.desktop import DesktopAPI
from qagent.lenguajes.exploracion import (
    ESTADO_COMPLETO,
    ESTADO_TRUNCADO,
    MAX_ARCHIVOS_DETECCION,
    explorar_archivos,
)
from qagent.proyectos.proyecto_local import inspeccionar_carpeta
from qagent.proyectos.vista_previa import generar_vista_previa


def _crear(
    raiz: Path, ruta_relativa: str, contenido: str = "def f(): return 1\n"
) -> Path:
    destino = raiz / ruta_relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    return destino


def test_inspeccionar_carpeta_normal_es_completa(tmp_path: Path) -> None:
    _crear(tmp_path, "main.py")
    _crear(tmp_path, "services/pagos.py")

    info = inspeccionar_carpeta(str(tmp_path))
    assert info["ok"] is True
    assert info["estado_exploracion"] == ESTADO_COMPLETO
    assert info["exploracion_incompleta"] is False
    assert info["limite_archivos"] == MAX_ARCHIVOS_DETECCION
    assert info["carpetas_pendientes"] == []
    assert info["aviso_exploracion"] is None


def test_inspeccionar_carpeta_truncada_incluye_aviso_y_pendientes(
    tmp_path: Path,
) -> None:
    """Superar el límite configurado debe advertir explícitamente sobre el recorrido parcial."""
    for i in range(5):
        _crear(tmp_path, f"backend/api_{i}.py")
    for i in range(5):
        _crear(tmp_path, f"frontend/comp_{i}.py")

    with (
        patch("qagent.lenguajes.exploracion.MAX_ARCHIVOS_DETECCION", 5),
        patch("qagent.proyectos.proyecto_local.MAX_ARCHIVOS_DETECCION", 5),
    ):
        info = inspeccionar_carpeta(str(tmp_path))

    assert info["ok"] is True
    assert info["estado_exploracion"] == ESTADO_TRUNCADO
    assert info["exploracion_incompleta"] is True
    assert "frontend" in info["carpetas_pendientes"]
    assert info["aviso_exploracion"] is not None
    assert "Exploración parcial" in info["aviso_exploracion"]
    assert "5" in info["aviso_exploracion"]


def test_generar_vista_previa_incluye_metadatos_de_exploracion(tmp_path: Path) -> None:
    _crear(tmp_path, "main.py")

    vista = generar_vista_previa(tmp_path)
    assert vista["ok"] is True
    assert vista["estado_exploracion"] == ESTADO_COMPLETO
    assert vista["exploracion_incompleta"] is False
    assert vista["carpetas_pendientes"] == []
    assert vista["aviso_exploracion"] is None


def test_generar_vista_previa_truncada_emite_aviso_estructurado(tmp_path: Path) -> None:
    for i in range(4):
        _crear(tmp_path, f"core/m_{i}.py")
    _crear(tmp_path, "pendientes/extra.py")

    with (
        patch("qagent.lenguajes.exploracion.MAX_ARCHIVOS_DETECCION", 3),
        patch("qagent.proyectos.vista_previa.MAX_ARCHIVOS_DETECCION", 3),
    ):
        vista = generar_vista_previa(tmp_path)

    assert vista["ok"] is True
    assert vista["estado_exploracion"] == ESTADO_TRUNCADO
    assert vista["exploracion_incompleta"] is True
    assert len(vista["carpetas_pendientes"]) > 0
    assert vista["aviso_exploracion"] is not None
    assert "Exploración parcial" in vista["aviso_exploracion"]


def test_desktop_api_continuar_exploracion_por_modulos(tmp_path: Path) -> None:
    """La API pywebview DesktopAPI expone continuar_exploracion para carpetas seleccionadas."""
    _crear(tmp_path, "backend/app.py")
    _crear(tmp_path, "frontend/index.py")

    api = DesktopAPI()
    vista = api.continuar_exploracion(str(tmp_path), ["frontend"])

    assert vista["ok"] is True
    assert any("frontend/index.py" in m["ruta"] for m in vista["modulos"])


def test_seleccion_de_lenguaje_respeta_alcance_explorado(tmp_path: Path) -> None:
    """La selección del adaptador usa únicamente los archivos que efectivamente se exploraron."""
    # Backend con 5 archivos Python y frontend con 10 archivos JavaScript
    for i in range(5):
        _crear(tmp_path, f"backend/serv_{i}.py")
    for i in range(10):
        _crear(tmp_path, f"frontend/comp_{i}.js", "function a() {}")

    # Si se exploran solo los archivos de backend:
    assert len(explorar_archivos(tmp_path, subcarpetas=["backend"]).archivos) == 5
    info_backend = inspeccionar_carpeta(str(tmp_path), subcarpetas=["backend"])

    assert info_backend["lenguaje"] == "python"
    assert info_backend["cantidad_fuentes"] == 5

    # Si se continúa explorando frontend:
    info_frontend = inspeccionar_carpeta(str(tmp_path), subcarpetas=["frontend"])
    assert info_frontend["lenguaje"] == "javascript"
    assert info_frontend["cantidad_fuentes"] == 10

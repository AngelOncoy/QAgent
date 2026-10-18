"""Pruebas del contrato frontend para proyectos recientes y apertura de proyectos con pruebas."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"
INICIO = (FRONTEND / "componentes" / "inicio" / "inicio.js").read_text(encoding="utf-8")
MODAL_ABRIR = (FRONTEND / "componentes" / "inicio" / "modal-abrir.js").read_text(
    encoding="utf-8"
)
PASOS = (FRONTEND / "componentes" / "pasos-proyecto" / "pasos-proyecto.js").read_text(
    encoding="utf-8"
)
VISTA_PREVIA = (
    FRONTEND / "componentes" / "vista-previa" / "vista-previa.js"
).read_text(encoding="utf-8")


def test_recientes_distingue_origen_carpeta_y_github() -> None:
    """La lista de recientes distingue git y carpeta local con texto (el color es para estados)."""
    assert "r.origen === 'git'" in INICIO
    assert "ini-origen-git" in INICIO
    assert "ini-origen-carpeta" in INICIO
    assert ">Git</span>" in INICIO
    assert ">Carpeta local</span>" in INICIO


def test_abrir_reciente_transmite_opciones_de_prueba_previa() -> None:
    """Al abrir un reciente, se detecta si ya cargo prueba y se pasa a loadProject."""
    assert "yaCargoPrueba" in INICIO
    assert "esReciente: true" in INICIO
    assert "loadProject(info.nombre" in INICIO


def test_pasos_definen_desbloquear_todas_las_vistas() -> None:
    """pasos-proyecto.js ofrece una funcion para habilitar todos los modulos a la vez."""
    assert "function desbloquearTodasLasVistas()" in PASOS
    assert (
        "document.querySelectorAll('#views a').forEach(a => {\n    a.classList.remove('hide', 'off');\n  });"
        in PASOS
    )


def test_load_project_desbloquea_todos_los_modulos_si_ya_cargo_prueba() -> None:
    """Si el proyecto reciente ya tiene una prueba cargada, habilita todos los modulos y va a reporte."""
    assert "if (esReciente && yaCargoPrueba) {" in VISTA_PREVIA
    assert "desbloquearTodasLasVistas()" in VISTA_PREVIA
    assert "go('report');" in VISTA_PREVIA
    assert "reiniciarVistasProyecto()" in VISTA_PREVIA
    assert "go('preview');" in VISTA_PREVIA


def test_modal_abrir_actualiza_recientes() -> None:
    """Al abrir una carpeta local se llama a cargarRecientes para reflejar el proyecto."""
    assert "cargarRecientes()" in MODAL_ABRIR

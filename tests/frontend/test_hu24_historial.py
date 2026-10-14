"""La pantalla Historial consume las specs reales de HU-24."""

from pathlib import Path

HISTORIAL = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "frontend"
    / "componentes"
    / "historial"
    / "historial.js"
).read_text(encoding="utf-8")


def test_historial_consulta_corridas_y_specs_del_backend() -> None:
    assert "api.obtener_historial(projectPath)" in HISTORIAL
    assert "renderHistoryReal(datos)" in HISTORIAL
    assert "spec.ultima_accion" in HISTORIAL
    assert "tokens_planner" in HISTORIAL


def test_historial_descarga_specs_reales_en_zip() -> None:
    assert "api.descargar_specs_zip(projectPath, modulo)" in HISTORIAL
    assert "r.cancelado" in HISTORIAL
    assert "r.ruta" in HISTORIAL
    assert "contenido_base64" not in HISTORIAL

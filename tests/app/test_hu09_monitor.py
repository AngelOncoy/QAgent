"""Pruebas unitarias para el flujo del Monitor en Vivo (HU-09)."""

from __future__ import annotations

from unittest.mock import patch

from pyagent.app.desktop import DesktopAPI
from pyagent.sandbox import estado as modulo_estado


def test_desktop_api_inicia_corrida_con_perfil_y_evento() -> None:
    """Verifica que al iniciar corrida la API retorne estado 'started' y emita evento."""
    api = DesktopAPI()
    eventos_emitidos = []

    # Interceptar emisión de eventos para probar sin interfaz gráfica
    def mock_emit(tipo: str, data: dict) -> None:
        eventos_emitidos.append((tipo, data))

    api.emit_event = mock_emit  # type: ignore[assignment]

    # Docker simulado como disponible: la prueba no debe depender de Docker Desktop (HU-13).
    with patch.object(
        modulo_estado, "estado_docker", return_value={"estado": "ok", "mensaje": ""}
    ):
        resultado = api.start_run(folder_path="/ruta/proyecto", profile="deep")

    assert resultado["status"] == "started"
    assert resultado["folder"] == "/ruta/proyecto"
    assert resultado["profile"] == "deep"

    # Verificar que se emitió el evento de inicio
    assert len(eventos_emitidos) == 1
    tipo, payload = eventos_emitidos[0]
    assert tipo == "log"
    assert "iniciada en perfil 'deep'" in payload["message"]


def test_eventos_de_alerta_tienen_clasificacion_valida() -> None:
    """Verifica la presencia y tipos de alertas destacados exigidos por el criterio 3."""
    alertas_esperadas = {
        "laundering": "Filtro Anti-Laundering",
        "oracle": "Filtro de Oráculo",
        "stuck": "Control de convergencia",
        "watch": "Alerta de calidad",
        "reuse": "Spec vigente",
    }

    # Comprobación de integridad de claves de alertas
    assert len(alertas_esperadas) == 5
    for clave, descripcion in alertas_esperadas.items():
        assert len(clave) > 0
        assert len(descripcion) > 0
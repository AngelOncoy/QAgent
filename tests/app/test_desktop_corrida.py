"""El botón «Iniciar corrida» lanza el pipeline real (conexión de EN-04 con la app)."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("webview")

from qagent.app.desktop import DesktopAPI
from qagent.orchestrator.corrida import ResumenCorrida
from qagent.sandbox import estado as modulo_estado


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> DesktopAPI:
    puente = DesktopAPI()
    puente.set_window(MagicMock())
    puente.verificar_entorno = lambda: {  # type: ignore[method-assign]
        "listo": True,
        "mensaje": "Entorno listo",
        "problemas": [],
        "comprobaciones": [],
    }
    return puente


def _docker(estado: str):
    return patch.object(
        modulo_estado, "estado_docker", return_value={"estado": estado, "mensaje": ""}
    )


def test_con_ia_real_lanza_el_pipeline(api, monkeypatch, corridas_lanzadas) -> None:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "0")
    with _docker("ok"):
        resultado = api.start_run("C:/proyecto", "deep")

    assert resultado["status"] == "started"
    assert resultado["modo"] == "real"
    assert corridas_lanzadas == [("C:/proyecto", "deep", None, False, None)]


def test_con_ia_simulada_y_docker_listo_tambien_es_real(
    api, monkeypatch, corridas_lanzadas
) -> None:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    monkeypatch.setattr(DesktopAPI, "_sandbox_listo", lambda self: True)

    resultado = api.start_run("C:/proyecto", "deep")

    assert resultado["modo"] == "real"
    assert corridas_lanzadas == [("C:/proyecto", "deep", None, True, None)]


def test_envia_al_pipeline_la_seleccion_validada(
    api, monkeypatch, corridas_lanzadas, tmp_path
) -> None:
    (tmp_path / "servicio.py").write_text(
        "def activa() -> bool:\n    return True\n", encoding="utf-8"
    )
    seleccion = [{"ruta": "servicio.py", "funciones": ["activa"], "endpoints": []}]
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    monkeypatch.setattr(DesktopAPI, "_sandbox_listo", lambda self: True)

    resultado = api.start_run(str(tmp_path), "deep", seleccion)

    assert resultado["status"] == "started"
    assert corridas_lanzadas == [(str(tmp_path), "deep", None, True, seleccion)]


def test_rechaza_objetivo_inexistente_antes_de_iniciar(
    api, monkeypatch, corridas_lanzadas, tmp_path
) -> None:
    (tmp_path / "servicio.py").write_text(
        "def activa() -> bool:\n    return True\n", encoding="utf-8"
    )
    seleccion = [{"ruta": "servicio.py", "funciones": ["inventada"], "endpoints": []}]

    resultado = api.start_run(str(tmp_path), "deep", seleccion)

    assert resultado["status"] == "seleccion_invalida"
    assert "Objetivos inexistentes" in resultado["mensaje"]
    assert corridas_lanzadas == []


def test_con_ia_simulada_sin_docker_queda_en_demostracion(
    api, monkeypatch, corridas_lanzadas
) -> None:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")

    resultado = api.start_run("C:/proyecto", "deep")

    assert resultado["status"] == "started"
    assert resultado["modo"] == "demostracion"
    assert corridas_lanzadas == []


def test_no_lanza_dos_corridas_a_la_vez(api, monkeypatch, corridas_lanzadas) -> None:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    sigue = threading.Event()
    api._corrida = threading.Thread(target=sigue.wait, daemon=True)
    api._corrida.start()
    try:
        resultado = api.start_run("C:/proyecto", "deep")
    finally:
        sigue.set()

    assert resultado["status"] == "en_curso"
    assert corridas_lanzadas == []


def test_el_hilo_envia_las_filas_y_el_resumen(api, monkeypatch) -> None:
    eventos: list[tuple[str, dict]] = []
    api.emit_event = lambda tipo, datos: eventos.append((tipo, datos))  # type: ignore[method-assign]

    def corrida_falsa(ruta, perfil, config, claves, *, simulado, al_evento, run_id):
        al_evento(
            {
                "agente": "orquestador",
                "archivo": None,
                "funcion": None,
                "mensaje": "Estado: generar",
                "estado": "generar",
                "tipo": "transicion",
                "datos": None,
                "progreso": {"hechos": 0, "total": 1},
            }
        )
        al_evento(
            {
                "agente": "reviewer",
                "archivo": "a.py",
                "funcion": "f",
                "mensaje": "Veredicto: accept",
                "estado": "ejecutar_revisar",
                "tipo": "veredicto",
                "datos": {"decision": "accept", "intento": 1},
                "progreso": {"hechos": 1, "total": 1},
            }
        )
        return ResumenCorrida(
            run_id=run_id, estado="fin", motivo=None, total_funciones=1, aceptadas=1
        )

    monkeypatch.setattr("qagent.orchestrator.corrida.ejecutar_corrida", corrida_falsa)

    api._correr("C:/proyecto", "deep", "20261010-020000-abcd", True)

    tipos = [tipo for tipo, _ in eventos]
    assert tipos == ["corrida_evento", "corrida_fin"]  # la transición no se envía
    assert eventos[0][1]["a"] == "reviewer"
    assert eventos[1][1]["aceptadas"] == 1
    assert eventos[1][1]["run_id"] == "20261010-020000-abcd"


def test_detener_corrida_activa_evento_cancelacion(api: DesktopAPI) -> None:
    api._cancelar_corrida.clear()
    # Sin corrida activa
    res_inactiva = api.detener_corrida()
    assert res_inactiva["ok"] is False

    # Con corrida activa
    api._corrida = MagicMock(is_alive=lambda: True)
    res_activa = api.detener_corrida()
    assert res_activa["ok"] is True
    assert api._cancelar_corrida.is_set()


def test_start_run_reinicia_evento_cancelacion(
    api: DesktopAPI, monkeypatch: pytest.MonkeyPatch, corridas_lanzadas: list
) -> None:
    api._cancelar_corrida.set()
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    monkeypatch.setattr(DesktopAPI, "_sandbox_listo", lambda self: True)

    resultado = api.start_run("C:/proyecto", "deep")
    assert resultado["status"] == "started"
    # El evento debe haberse limpiado al iniciar
    assert not api._cancelar_corrida.is_set()


def test_guardar_limites_con_max_tokens(api: DesktopAPI, tmp_path: Path) -> None:
    local = tmp_path / "config.local.toml"
    with patch("qagent.config.limites.config_carga.RUTA_CONFIG_LOCAL", local):
        res = api.guardar_limites(max_intentos=3, max_tokens=85000)
        assert res["ok"] is True
        limites = api.obtener_limites()
        assert limites["max_intentos"] == 3
        assert limites["max_tokens_por_corrida"] == 85000

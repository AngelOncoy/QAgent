"""La cancelación y el timeout matan solo el contenedor de la comprobación."""

from unittest.mock import MagicMock

from qagent.sandbox import ejecucion


def test_cancelacion_no_se_confunde_con_oom_y_limpia_contenedor(tmp_path):
    proyecto, pruebas = tmp_path / "proyecto", tmp_path / "pruebas"
    proyecto.mkdir()
    pruebas.mkdir()
    cliente = MagicMock()
    cliente.info.return_value = {"NCPU": 4}
    contenedor = cliente.containers.run.return_value
    contenedor.attrs = {"State": {"Running": False, "ExitCode": 137}}
    contenedor.logs.return_value = b""
    resultado = ejecucion.ejecutar_en_sandbox(
        "imagen-prueba",
        ["mvn", "compile"],
        proyecto,
        pruebas,
        cliente=cliente,
        cancelado=lambda: True,
    )
    assert resultado.cancelado and not resultado.oom_killed and not resultado.timed_out
    contenedor.kill.assert_called_once()
    contenedor.remove.assert_called_once_with(force=True)
    opciones = cliente.containers.run.call_args.kwargs
    assert opciones["network_mode"] == "none" and opciones["read_only"] is True
    assert opciones["cap_drop"] == ["ALL"]


def test_cancelacion_durante_espera_es_cooperativa(monkeypatch):
    estado = {"cancelado": False}
    contenedor = MagicMock()
    contenedor.attrs = {"State": {"Running": True}}
    monkeypatch.setattr(
        ejecucion.time, "sleep", lambda _: estado.update(cancelado=True)
    )
    codigo, agotado, cancelado = ejecucion._esperar_cancelable(
        contenedor, 10, lambda: estado["cancelado"]
    )
    assert (codigo, agotado, cancelado) == (137, False, True)
    contenedor.kill.assert_called_once()
    contenedor.wait.assert_not_called()


def test_timeout_no_se_registra_como_cancelacion():
    contenedor = MagicMock()
    assert ejecucion._esperar_cancelable(contenedor, 0, lambda: False) == (
        137,
        True,
        False,
    )
    contenedor.kill.assert_called_once()


def test_salida_normal_no_mata_el_contenedor():
    contenedor = MagicMock()
    contenedor.attrs = {"State": {"Running": False, "ExitCode": 0}}
    assert ejecucion._esperar_cancelable(contenedor, 10, lambda: False) == (
        0,
        False,
        False,
    )
    contenedor.kill.assert_not_called()

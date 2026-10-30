"""#194: API de escritorio para iniciar la verificación desde Historial."""

from __future__ import annotations

from qagent.almacenamiento import ErrorAlmacen
from qagent.app.desktop import DesktopAPI
from qagent.sandbox import DockerNoDisponible


class HiloFalso:
    def __init__(self, *, target, args, name, daemon):
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon
        self.iniciado = False

    def start(self):
        self.iniciado = True

    def is_alive(self):
        return self.iniciado


def _preparar(monkeypatch, inspeccion=None):
    inspeccion = inspeccion or {
        "run_origen_id": "20261030-100000-abcd",
        "total": 1,
        "ejecutables": 1,
        "no_comparables": 0,
        "motivos": [],
    }
    monkeypatch.setattr(
        "qagent.orchestrator.verificacion_correccion.inspeccionar_verificacion",
        lambda *_args: inspeccion,
    )
    monkeypatch.setattr("qagent.sandbox.verificar_docker", lambda: None)
    monkeypatch.setattr(
        "qagent.config.verificar_entorno",
        lambda *_args, **_kwargs: {"listo": True, "mensaje": "OK", "problemas": []},
    )
    monkeypatch.setattr(
        "qagent.app.desktop._registrar_run",
        lambda *_args, **_kwargs: "20261030-110000-ef01",
    )
    monkeypatch.setattr("qagent.app.desktop._tomar_bloqueo", lambda *_args: None)
    monkeypatch.setattr("qagent.app.desktop.threading.Thread", HiloFalso)


def test_inicia_hilo_con_run_elegido_y_sin_perfil_llm(monkeypatch) -> None:
    _preparar(monkeypatch)
    api = DesktopAPI()
    eventos = []
    monkeypatch.setattr(
        api, "emit_event", lambda nombre, datos: eventos.append((nombre, datos))
    )

    respuesta = api.verificar_correccion("C:/proyecto", "20261030-100000-abcd")

    assert respuesta["status"] == "started"
    assert respuesta["run_origen_id"] == "20261030-100000-abcd"
    assert respuesta["run_id"] == "20261030-110000-ef01"
    assert api._corrida.name == "qagent-verificar-correccion"
    assert api._corrida.iniciado is True
    assert "no se usa IA" in eventos[0][1]["message"]


def test_doble_inicio_se_rechaza_antes_de_inspeccionar(monkeypatch) -> None:
    api = DesktopAPI()
    api._corrida = HiloFalso(target=None, args=(), name="activa", daemon=True)
    api._corrida.start()
    monkeypatch.setattr(
        "qagent.orchestrator.verificacion_correccion.inspeccionar_verificacion",
        lambda *_args: (_ for _ in ()).throw(AssertionError("no debe inspeccionar")),
    )

    respuesta = api.verificar_correccion("C:/proyecto", "20261030-100000-abcd")

    assert respuesta["status"] == "en_curso"


def test_corrida_ajena_o_inexistente_da_error_claro(monkeypatch) -> None:
    monkeypatch.setattr(
        "qagent.orchestrator.verificacion_correccion.inspeccionar_verificacion",
        lambda *_args: (_ for _ in ()).throw(ErrorAlmacen("corrida inexistente")),
    )

    respuesta = DesktopAPI().verificar_correccion("C:/proyecto", "20261030-100000-abcd")

    assert respuesta == {"status": "no_verificable", "mensaje": "corrida inexistente"}


def test_sin_pruebas_ejecutables_no_exige_docker(monkeypatch) -> None:
    _preparar(
        monkeypatch,
        {
            "run_origen_id": "20261030-100000-abcd",
            "total": 1,
            "ejecutables": 0,
            "no_comparables": 1,
            "motivos": ["firma incompatible"],
        },
    )
    monkeypatch.setattr(
        "qagent.sandbox.verificar_docker",
        lambda: (_ for _ in ()).throw(AssertionError("Docker no es necesario")),
    )

    respuesta = DesktopAPI().verificar_correccion("C:/proyecto", "20261030-100000-abcd")

    assert respuesta["status"] == "started"
    assert respuesta["no_comparables"] == 1


def test_pruebas_comparables_requieren_docker(monkeypatch) -> None:
    _preparar(monkeypatch)
    monkeypatch.setattr(
        "qagent.sandbox.verificar_docker",
        lambda: (_ for _ in ()).throw(DockerNoDisponible("Docker apagado")),
    )

    respuesta = DesktopAPI().verificar_correccion("C:/proyecto", "20261030-100000-abcd")

    assert respuesta == {
        "status": "docker_no_disponible",
        "mensaje": "Docker apagado",
    }

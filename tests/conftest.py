"""Configuración común de las pruebas."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import soporte_docker

#: Imágenes de QAgent que había antes de las pruebas `docker` (#250).
_IMAGENES_ANTES = pytest.StashKey[set]()
#: Imágenes que se borraron al terminar, y las que no se pudieron borrar.
_LIMPIEZA = pytest.StashKey[tuple]()
#: Imágenes base que se reconstruyeron por desactualizadas, y las que fallaron.
_ACTUALIZADAS = pytest.StashKey[tuple]()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Opciones de las pruebas con Docker real (#250)."""
    grupo = parser.getgroup("qagent", "QAgent")
    grupo.addoption(
        "--docker",
        action="store_true",
        default=False,
        help="corre las pruebas con Docker real (tardan varios minutos y crean imágenes)",
    )
    grupo.addoption(
        "--conservar-imagenes",
        action="store_true",
        default=False,
        help="no borra al terminar las imágenes que crearon las pruebas docker",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Omite las pruebas `docker` salvo que se pidan; si se piden, avisa y anota las imágenes."""
    docker = [item for item in items if item.get_closest_marker("docker")]
    if not docker:
        return
    activas = soporte_docker.pruebas_docker_activas(
        config.getoption("--docker"), config.getoption("-m")
    )
    if not activas:
        omitir = pytest.mark.skip(reason=soporte_docker.MOTIVO_OMITIDA)
        for item in docker:
            item.add_marker(omitir)
        return
    conservar = config.getoption("--conservar-imagenes")
    _escribir(config, soporte_docker.texto_aviso(len(docker), conservar))
    if not conservar:
        cliente = _cliente_docker()
        if cliente is not None:
            config.stash[_IMAGENES_ANTES] = soporte_docker.etiquetas_qagent(cliente)


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Borra las imágenes de QAgent que crearon las pruebas `docker`."""
    antes = session.config.stash.get(_IMAGENES_ANTES, None)
    if antes is None:
        return
    cliente = _cliente_docker()
    if cliente is None:
        return
    nuevas = soporte_docker.imagenes_creadas(
        antes, soporte_docker.etiquetas_qagent(cliente)
    )
    session.config.stash[_LIMPIEZA] = soporte_docker.borrar_imagenes(cliente, nuevas)


def pytest_terminal_summary(terminalreporter, config: pytest.Config) -> None:
    """Informa qué imágenes se reconstruyeron y cuáles se borraron al terminar."""
    actualizadas = config.stash.get(_ACTUALIZADAS, None)
    limpieza = config.stash.get(_LIMPIEZA, None)
    if actualizadas is None and limpieza is None:
        return
    terminalreporter.section("Imágenes de las pruebas docker")
    reconstruidas, fallidas = actualizadas or ([], {})
    for etiqueta in reconstruidas:
        terminalreporter.write_line(f"reconstruida (receta nueva) {etiqueta}")
    for etiqueta, motivo in fallidas.items():
        terminalreporter.write_line(f"no se pudo reconstruir {etiqueta}: {motivo}")
    if limpieza is None:
        return
    borradas, errores = limpieza
    if not borradas and not errores:
        terminalreporter.write_line("Las pruebas no crearon imágenes nuevas.")
    for etiqueta in borradas:
        terminalreporter.write_line(f"borrada   {etiqueta}")
    for etiqueta, motivo in errores.items():
        terminalreporter.write_line(f"no borrada {etiqueta}: {motivo}")


@pytest.fixture(autouse=True)
def imagenes_base_al_dia(request: pytest.FixtureRequest) -> None:
    """Antes de la primera prueba `docker`, reconstruye las imágenes base viejas (#250).

    Una imagen base construida con una receta anterior (por ejemplo `qagent-sandbox:java`
    sin ArchUnit, de antes de #185) hace fallar las pruebas por el entorno. Se revisa una
    sola vez por sesión y nunca en las pruebas sin Docker.
    """
    if request.node.get_closest_marker("docker") is None:
        return
    config = request.config
    if _ACTUALIZADAS in config.stash:
        return
    cliente = _cliente_docker()
    if cliente is None:
        config.stash[_ACTUALIZADAS] = ([], {})
        return
    from qagent.sandbox.imagen import construir_imagen_base, imagen_desactualizada

    config.stash[_ACTUALIZADAS] = soporte_docker.actualizar_imagenes_base(
        cliente,
        imagen_desactualizada,
        lambda cliente, etiqueta: construir_imagen_base(cliente, imagen=etiqueta),
    )


@pytest.fixture(scope="session")
def cliente_docker():
    """Cliente Docker real; omite la prueba si Docker no está disponible."""
    from qagent.sandbox import DockerNoDisponible, obtener_cliente

    try:
        return obtener_cliente()
    except DockerNoDisponible as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="session")
def imagen_base(cliente_docker) -> str:
    """Imagen base del sandbox; la construye una vez si no existe."""
    from qagent.sandbox import construir_imagen_base
    from qagent.sandbox.imagen import IMAGEN_BASE, _imagen_existe

    if not _imagen_existe(cliente_docker, IMAGEN_BASE):
        construir_imagen_base(cliente_docker)
    return IMAGEN_BASE


def _escribir(config: pytest.Config, texto: str) -> None:
    """Escribe en la terminal de pytest (o en stdout si no hay)."""
    terminal = config.pluginmanager.get_plugin("terminalreporter")
    if terminal is None:
        print(texto)
        return
    terminal.write_line("")
    for linea in texto.splitlines():
        terminal.write_line(linea, yellow=True)


def _cliente_docker():
    """Cliente Docker, o None si Docker no responde (las pruebas se omiten solas)."""
    try:
        from qagent.sandbox import DockerNoDisponible, obtener_cliente

        return obtener_cliente()
    except (ImportError, DockerNoDisponible):
        return None


@pytest.fixture(autouse=True)
def sin_config_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Las pruebas usan solo el `config.toml` del equipo, nunca el `config.local.toml`
    ni el `.env` personales (`~/.qagent/`) de la computadora donde se ejecutan.

    Cada prueba tiene sus propias rutas: la pantalla Configuración escribe en
    `config.local.toml` (TA-06) y lo que guarde una prueba no debe verlo la siguiente.
    """
    from qagent.config import carga

    monkeypatch.setattr(carga, "RUTA_CONFIG_LOCAL", tmp_path / "sin-config-local.toml")
    monkeypatch.setattr(carga, "RUTA_ENV", tmp_path / "sin-env" / ".env")


@pytest.fixture(autouse=True)
def corridas_lanzadas(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Ninguna prueba lanza el pipeline real en un hilo al llamar a `start_run`.

    `start_run` decide el modo y llama a `_lanzar_corrida`; aquí esa llamada solo se
    anota (la lista que devuelve el fixture) y Docker se da por no listo, salvo que la
    prueba lo cambie. El pipeline en sí se prueba en `tests/orchestrator/test_corrida.py`.
    """
    lanzadas: list[tuple] = []
    try:
        from qagent.app import desktop
    except ImportError:  # sin pywebview instalado no hay puente que parchear
        return lanzadas
    monkeypatch.setattr(
        desktop.DesktopAPI,
        "_lanzar_corrida",
        lambda self, *argumentos: lanzadas.append(argumentos),
    )
    monkeypatch.setattr(desktop.DesktopAPI, "_sandbox_listo", lambda self: False)
    return lanzadas

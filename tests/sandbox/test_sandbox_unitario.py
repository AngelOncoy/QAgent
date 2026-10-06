"""Pruebas unitarias del sandbox con el cliente Docker simulado (no necesitan Docker)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from docker.errors import APIError, BuildError, DockerException, ImageNotFound
from requests.exceptions import ReadTimeout

from pyagent.sandbox import (
    IMAGEN_BASE,
    DockerNoDisponible,
    ErrorConstruccionImagen,
    ImagenNoEncontrada,
    LimitesSandbox,
    copiar_proyecto,
    ejecucion,
    ejecutar_en_sandbox,
    ejecutar_pruebas,
    modelos,
    obtener_cliente,
    preparar_imagen,
)
from pyagent.sandbox import cliente as modulo_cliente
from pyagent.sandbox.imagen import etiqueta_para_requirements


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    """Proyecto de ejemplo con archivos que nunca deben copiarse."""
    raiz = tmp_path / "proyecto"
    (raiz / "paquete").mkdir(parents=True)
    (raiz / "paquete" / "calc.py").write_text(
        "def f():\n    return 1\n", encoding="utf-8"
    )
    (raiz / ".env").write_text("CLAVE=secreta\n", encoding="utf-8")
    (raiz / ".env.local").write_text("CLAVE=secreta\n", encoding="utf-8")
    (raiz / ".git").mkdir()
    (raiz / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    for carpeta in (".venv", "venv", ".pyagent", "node_modules", "paquete/__pycache__"):
        (raiz / carpeta).mkdir(parents=True)
        (raiz / carpeta / "x.txt").write_text("x", encoding="utf-8")
    return raiz


@pytest.fixture
def carpeta_tests(tmp_path: Path) -> Path:
    """Carpeta de tests de ejemplo."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_x.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    return tests


def _cliente_simulado(estado: dict | None = None, oom: bool = False) -> MagicMock:
    """Crea un cliente Docker simulado cuyo contenedor termina con `estado`."""
    contenedor = MagicMock()
    contenedor.wait.return_value = estado or {"StatusCode": 0}
    contenedor.logs.side_effect = lambda stdout, stderr: (
        b"salida" if stdout else b"errores"
    )
    contenedor.attrs = {"State": {"OOMKilled": oom}}
    cliente = MagicMock()
    cliente.containers.run.return_value = contenedor
    return cliente


def _argumentos_run(cliente: MagicMock) -> dict:
    """Devuelve los argumentos con nombre de la llamada a containers.run."""
    return cliente.containers.run.call_args.kwargs


def _montaje(argumentos: dict, destino: str) -> dict:
    """Busca el montaje con el destino indicado."""
    return next(m for m in argumentos["mounts"] if m["Target"] == destino)


# --- Parámetros del contenedor ---------------------------------------------------------


def test_contenedor_sin_red_con_limites_y_sin_privilegios(proyecto, carpeta_tests):
    cliente = _cliente_simulado()

    ejecutar_en_sandbox("img", ["pytest"], proyecto, carpeta_tests, cliente=cliente)

    argumentos = _argumentos_run(cliente)
    assert argumentos["network_mode"] == "none"
    assert argumentos["nano_cpus"] == 1_000_000_000
    assert argumentos["mem_limit"] == "256m"
    assert argumentos["memswap_limit"] == "256m"
    assert argumentos["pids_limit"] > 0
    assert argumentos["cap_drop"] == ["ALL"]
    assert argumentos["security_opt"] == ["no-new-privileges"]
    assert argumentos["detach"] is True
    assert "/tmp" in argumentos["tmpfs"]


def test_limites_personalizados(proyecto, carpeta_tests):
    cliente = _cliente_simulado()

    ejecutar_en_sandbox(
        "img",
        ["pytest"],
        proyecto,
        carpeta_tests,
        LimitesSandbox(cpus=0.5, memoria="128m"),
        cliente=cliente,
    )

    argumentos = _argumentos_run(cliente)
    assert argumentos["nano_cpus"] == 500_000_000
    assert argumentos["mem_limit"] == "128m"
    assert argumentos["memswap_limit"] == "128m"


def test_no_pasa_variables_de_entorno_del_host(proyecto, carpeta_tests, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-del-host")
    cliente = _cliente_simulado()

    ejecutar_en_sandbox("img", ["pytest"], proyecto, carpeta_tests, cliente=cliente)

    entorno = _argumentos_run(cliente)["environment"]
    assert entorno == {"PYTHONPATH": "/work/proyecto", "HOME": "/tmp"}


def test_montajes_tests_solo_lectura_y_sin_socket_docker(proyecto, carpeta_tests):
    cliente = _cliente_simulado()

    ejecutar_en_sandbox("img", ["pytest"], proyecto, carpeta_tests, cliente=cliente)

    argumentos = _argumentos_run(cliente)
    assert _montaje(argumentos, "/work/tests")["ReadOnly"] is True
    assert _montaje(argumentos, "/work/tests")["Source"] == str(carpeta_tests.resolve())
    assert _montaje(argumentos, "/work/proyecto")["Source"] != str(proyecto.resolve())
    fuentes = " ".join(m["Source"] for m in argumentos["mounts"])
    assert "docker.sock" not in fuentes
    assert "volumes" not in argumentos


def test_ejecutar_pruebas_arma_comando_pytest_con_cobertura(proyecto, carpeta_tests):
    cliente = _cliente_simulado()

    ejecutar_pruebas("img", proyecto, carpeta_tests, "paquete", cliente=cliente)

    comando = cliente.containers.run.call_args.args[1]
    assert comando[:2] == ["pytest", "/work/tests"]
    assert "--cov=paquete" in comando
    assert "--cov-branch" in comando
    assert "--cov-report=json:/out/coverage.json" in comando
    assert comando[-2:] == ["-p", "no:cacheprovider"]
    assert _argumentos_run(cliente)["environment"]["COVERAGE_FILE"] == "/out/.coverage"


# --- Resultado -------------------------------------------------------------------------


def test_devuelve_codigo_salida_logs_y_coverage(proyecto, carpeta_tests):
    cliente = _cliente_simulado({"StatusCode": 1})
    contenedor = cliente.containers.run.return_value

    def escribir_coverage(timeout):
        salida = _montaje(_argumentos_run(cliente), "/out")["Source"]
        Path(salida, "coverage.json").write_text(
            json.dumps({"totals": {}}), encoding="utf-8"
        )
        return {"StatusCode": 1}

    contenedor.wait.side_effect = escribir_coverage

    resultado = ejecutar_pruebas(
        "img", proyecto, carpeta_tests, "paquete", cliente=cliente
    )

    assert resultado.exit_code == 1
    assert resultado.stdout == "salida"
    assert resultado.stderr == "errores"
    assert resultado.coverage == {"totals": {}}
    assert resultado.timed_out is False
    assert resultado.oom_killed is False


def test_sin_coverage_json_devuelve_none(proyecto, carpeta_tests):
    resultado = ejecutar_en_sandbox(
        "img", ["true"], proyecto, carpeta_tests, cliente=_cliente_simulado()
    )

    assert resultado.coverage is None


def test_timeout_mata_el_contenedor_y_marca_timed_out(proyecto, carpeta_tests):
    cliente = _cliente_simulado()
    contenedor = cliente.containers.run.return_value
    contenedor.wait.side_effect = [ReadTimeout(), {"StatusCode": 137}]

    resultado = ejecutar_en_sandbox(
        "img",
        ["sleep", "999"],
        proyecto,
        carpeta_tests,
        LimitesSandbox(timeout_s=1),
        cliente=cliente,
    )

    contenedor.kill.assert_called_once()
    assert contenedor.wait.call_args_list[0].kwargs["timeout"] == 1
    assert resultado.timed_out is True
    assert resultado.oom_killed is False
    contenedor.remove.assert_called_once_with(force=True)


@pytest.mark.parametrize(
    ("estado", "oom"), [({"StatusCode": 137}, False), ({"StatusCode": 1}, True)]
)
def test_detecta_falta_de_memoria(proyecto, carpeta_tests, estado, oom):
    cliente = _cliente_simulado(estado, oom=oom)

    resultado = ejecutar_en_sandbox(
        "img", ["x"], proyecto, carpeta_tests, cliente=cliente
    )

    assert resultado.oom_killed is True


# --- Limpieza --------------------------------------------------------------------------


def _registrar_temporales(monkeypatch) -> list[Path]:
    """Registra las carpetas temporales que crea el sandbox."""
    creadas: list[Path] = []
    original = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        ruta = original(*args, **kwargs)
        creadas.append(Path(ruta))
        return ruta

    monkeypatch.setattr(ejecucion.tempfile, "mkdtemp", mkdtemp)
    return creadas


def test_contenedor_y_temporales_se_eliminan_tras_exito(
    proyecto, carpeta_tests, monkeypatch
):
    creadas = _registrar_temporales(monkeypatch)
    cliente = _cliente_simulado()

    ejecutar_en_sandbox("img", ["x"], proyecto, carpeta_tests, cliente=cliente)

    cliente.containers.run.return_value.remove.assert_called_once_with(force=True)
    assert creadas and not any(c.exists() for c in creadas)


def test_contenedor_y_temporales_se_eliminan_aunque_haya_error(
    proyecto, carpeta_tests, monkeypatch
):
    creadas = _registrar_temporales(monkeypatch)
    cliente = _cliente_simulado()
    contenedor = cliente.containers.run.return_value
    contenedor.logs.side_effect = APIError("fallo al leer logs")

    with pytest.raises(APIError):
        ejecutar_en_sandbox("img", ["x"], proyecto, carpeta_tests, cliente=cliente)

    contenedor.remove.assert_called_once_with(force=True)
    assert creadas and not any(c.exists() for c in creadas)


def test_temporales_se_eliminan_si_la_imagen_no_existe(
    proyecto, carpeta_tests, monkeypatch
):
    creadas = _registrar_temporales(monkeypatch)
    cliente = _cliente_simulado()
    cliente.containers.run.side_effect = ImageNotFound("no existe")

    with pytest.raises(ImagenNoEncontrada, match="preparar_imagen"):
        ejecutar_en_sandbox("img", ["x"], proyecto, carpeta_tests, cliente=cliente)

    assert creadas and not any(c.exists() for c in creadas)


# --- Copia del proyecto ----------------------------------------------------------------


def test_copia_excluye_secretos_git_y_carpetas_pesadas(proyecto, tmp_path):
    copia = copiar_proyecto(proyecto, tmp_path / "copia")

    copiados = {p.relative_to(copia).as_posix() for p in copia.rglob("*")}
    assert copiados == {"paquete", "paquete/calc.py"}


def test_proyecto_original_queda_intacto(proyecto, carpeta_tests):
    antes = {p: p.read_bytes() for p in proyecto.rglob("*") if p.is_file()}
    cliente = _cliente_simulado()
    contenedor = cliente.containers.run.return_value

    def modificar_copia(timeout):
        copia = Path(_montaje(_argumentos_run(cliente), "/work/proyecto")["Source"])
        (copia / "paquete" / "calc.py").write_text("roto", encoding="utf-8")
        (copia / "nuevo.py").write_text("x", encoding="utf-8")
        return {"StatusCode": 0}

    contenedor.wait.side_effect = modificar_copia

    ejecutar_en_sandbox("img", ["x"], proyecto, carpeta_tests, cliente=cliente)

    despues = {p: p.read_bytes() for p in proyecto.rglob("*") if p.is_file()}
    assert despues == antes


# --- Imagen ----------------------------------------------------------------------------


def _solo_existen(*etiquetas: str):
    """Simula `images.get`: solo existen las imágenes indicadas."""

    def get(etiqueta: str) -> MagicMock:
        if etiqueta not in etiquetas:
            raise ImageNotFound(etiqueta)
        return MagicMock()

    return get


def test_etiqueta_por_hash_del_requirements():
    etiqueta = etiqueta_para_requirements(b"fastapi==0.115.0\n")

    assert etiqueta.startswith("pyagent-sandbox:req-")
    assert len(etiqueta.removeprefix("pyagent-sandbox:req-")) == 12
    assert etiqueta == etiqueta_para_requirements(b"fastapi==0.115.0\n")
    assert etiqueta != etiqueta_para_requirements(b"fastapi==0.116.0\n")


def test_sin_requirements_usa_la_imagen_base(proyecto):
    cliente = MagicMock()

    assert preparar_imagen(proyecto, cliente=cliente) == IMAGEN_BASE
    cliente.images.build.assert_not_called()


def test_falla_si_no_existe_la_imagen_base(proyecto):
    cliente = MagicMock()
    cliente.images.get.side_effect = ImageNotFound("no existe")

    with pytest.raises(ImagenNoEncontrada, match="construir_imagen_base"):
        preparar_imagen(proyecto, cliente=cliente)


def test_reutiliza_imagen_derivada_existente(proyecto):
    (proyecto / "requirements.txt").write_bytes(b"six\n")
    cliente = MagicMock()

    etiqueta = preparar_imagen(proyecto, cliente=cliente)

    assert etiqueta == etiqueta_para_requirements(b"six\n")
    cliente.images.build.assert_not_called()


def test_construye_imagen_derivada_solo_con_requirements(proyecto):
    (proyecto / "requirements.txt").write_bytes(b"six\n")
    cliente = MagicMock()
    etiqueta = etiqueta_para_requirements(b"six\n")
    cliente.images.get.side_effect = _solo_existen(IMAGEN_BASE)
    contexto: dict = {}

    def build(path, tag, **kwargs):
        contexto["archivos"] = sorted(p.name for p in Path(path).iterdir())
        contexto["dockerfile"] = Path(path, "Dockerfile").read_text(encoding="utf-8")
        contexto["ruta"] = Path(path)
        return MagicMock(), iter([])

    cliente.images.build.side_effect = build

    assert preparar_imagen(proyecto, cliente=cliente) == etiqueta
    assert contexto["archivos"] == ["Dockerfile", "requirements.txt"]
    assert contexto["dockerfile"].startswith(f"FROM {IMAGEN_BASE}")
    assert not contexto["ruta"].exists()
    assert cliente.images.build.call_args.kwargs["tag"] == etiqueta


def test_error_de_pip_da_mensaje_claro_con_log(proyecto):
    (proyecto / "requirements.txt").write_bytes(b"paquete-que-no-existe\n")
    cliente = MagicMock()
    cliente.images.get.side_effect = _solo_existen(IMAGEN_BASE)
    log = [
        {"stream": "Collecting paquete-que-no-existe\n"},
        {"error": "No matching distribution"},
    ]
    cliente.images.build.side_effect = BuildError("pip falló", log)

    with pytest.raises(ErrorConstruccionImagen, match="requirements.txt") as error:
        preparar_imagen(proyecto, cliente=cliente)

    assert "No matching distribution" in error.value.log


# --- Docker no disponible --------------------------------------------------------------


@pytest.mark.parametrize(
    ("ejecutable", "mensaje"),
    [
        (None, modelos.MENSAJE_NO_INSTALADO),
        ("C:/docker.exe", modelos.MENSAJE_NO_INICIADO),
    ],
)
def test_docker_no_disponible_da_mensaje_claro(ejecutable, mensaje):
    with (
        patch.object(
            modulo_cliente.docker, "from_env", side_effect=DockerException("pipe")
        ),
        patch.object(modelos.shutil, "which", return_value=ejecutable),
        pytest.raises(DockerNoDisponible) as error,
    ):
        obtener_cliente()

    assert str(error.value) == mensaje
    assert "Traceback" not in str(error.value)

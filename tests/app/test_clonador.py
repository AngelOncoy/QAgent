"""Pruebas del clonado de repositorios por URL (HU-02)."""

from __future__ import annotations

import io
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from pyagent.app import clonador

URL_OK = "https://github.com/usuario/repositorio.git"


class _ProcesoFalso:
    """Imita a `subprocess.Popen`: entrega un stderr fijo y un código de salida."""

    def __init__(self, stderr: str, codigo: int) -> None:
        self.stderr = io.StringIO(stderr)
        self._codigo = codigo

    def wait(self) -> int:
        return self._codigo


def _popen_falso(stderr: str, codigo: int, crear_destino: bool = False):
    """Fábrica de Popen falso; si `crear_destino`, crea la carpeta como haría git."""
    llamadas: list[dict] = []

    def popen(comando, **kwargs):
        llamadas.append({"comando": comando, **kwargs})
        if crear_destino:
            destino = Path(comando[-1])
            destino.mkdir(parents=True, exist_ok=True)
            (destino / ".git").mkdir(exist_ok=True)
        return _ProcesoFalso(stderr, codigo)

    popen.llamadas = llamadas
    return popen


# ---------------------------------------------------------------- validar_url


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/usuario/repositorio",
        "https://github.com/usuario/repositorio.git",
        "https://gitlab.com/grupo/mi-proyecto.git",
        "https://bitbucket.org/equipo/repo_1",
        "https://git.mi-empresa.com.pe/u/r.v2",
    ],
)
def test_validar_url_acepta_https_con_usuario_y_repositorio(url):
    assert clonador.validar_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://github.com/usuario/repositorio.git",
        "git@github.com:usuario/repositorio.git",
        "ssh://git@github.com/usuario/repositorio.git",
        "git://github.com/usuario/repositorio.git",
        "https://github.com/usuario",
        "https://github.com/usuario/repositorio/extra",
        "https://github.com/usuario/repositorio/",
        "https://github.com/usuario/repo sitorio",
        " https://github.com/usuario/repositorio",
        "https://github.com/usuario/repositorio\n",
        "https://user:token@github.com/usuario/repositorio",
        "https://github.com:8443/usuario/repositorio",
        "https://localhost/usuario/repositorio",
        "https://github.com/-usuario/repositorio",
        "https://github.com/usuario/--upload-pack=touch",
        "https://github.com/usuario/repo;rm -rf",
        "https://github.com/usuario/repo$(whoami)",
        "https://github.com/usuario/repo?x=1",
        "https://github.com/../repositorio",
        "https://github.com/usuario/repositório",
    ],
)
def test_validar_url_rechaza_formatos_no_permitidos(url):
    assert not clonador.validar_url(url)


def test_validar_url_rechaza_no_cadenas():
    assert not clonador.validar_url(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------- validar_rama


@pytest.mark.parametrize(
    "rama", ["main", "master", "develop", "feat/hu-02", "v1.2.3", "release_1"]
)
def test_validar_rama_acepta_nombres_comunes(rama):
    assert clonador.validar_rama(rama)


@pytest.mark.parametrize(
    "rama",
    [
        "",
        "-main",
        "--upload-pack=x",
        "a..b",
        "rama/",
        "rama.",
        "a//b",
        "a/.b",
        "x.lock",
        "a b",
        "a;b",
    ],
)
def test_validar_rama_rechaza_nombres_peligrosos_o_invalidos(rama):
    assert not clonador.validar_rama(rama)


# ---------------------------------------------------------------- nombre y destino


@pytest.mark.parametrize(
    ("url", "nombre"),
    [
        ("https://github.com/usuario/repositorio.git", "repositorio"),
        ("https://github.com/usuario/repositorio", "repositorio"),
        ("https://github.com/usuario/mi.repo.git", "mi.repo"),
    ],
)
def test_nombre_repositorio_quita_extension_git(url, nombre):
    assert clonador.nombre_repositorio(url) == nombre


def test_nombre_repositorio_con_url_invalida_lanza_error():
    with pytest.raises(ValueError, match="Formato esperado"):
        clonador.nombre_repositorio("git@github.com:u/r.git")


def test_destino_por_defecto_usa_carpeta_de_proyectos(tmp_path):
    assert clonador.destino_por_defecto(URL_OK, tmp_path) == tmp_path / "repositorio"


def test_destino_por_defecto_sin_carpeta_usa_la_del_usuario():
    esperado = clonador.carpeta_proyectos_por_defecto() / "repositorio"
    assert clonador.destino_por_defecto(URL_OK) == esperado


# ---------------------------------------------------------------- armar_comando


def test_armar_comando_superficial_por_defecto(tmp_path):
    destino = tmp_path / "repositorio"
    assert clonador.armar_comando(URL_OK, "main", destino) == [
        "git", "clone", "--progress", "--depth", "1",
        "--branch", "main", "--", URL_OK, str(destino),
    ]  # fmt: skip


def test_armar_comando_sin_superficial_omite_depth(tmp_path):
    comando = clonador.armar_comando(URL_OK, "develop", tmp_path, superficial=False)
    assert "--depth" not in comando
    assert comando[comando.index("--branch") + 1] == "develop"


def test_armar_comando_url_va_despues_de_doble_guion(tmp_path):
    comando = clonador.armar_comando(URL_OK, "main", tmp_path)
    assert comando.index("--") < comando.index(URL_OK)


@pytest.mark.parametrize(
    ("url", "rama"), [("http://github.com/u/r", "main"), (URL_OK, "-x")]
)
def test_armar_comando_rechaza_url_o_rama_invalidas(url, rama, tmp_path):
    with pytest.raises(ValueError):
        clonador.armar_comando(url, rama, tmp_path)


def test_entorno_git_desactiva_peticion_de_credenciales():
    entorno = clonador.entorno_git()
    assert entorno["GIT_TERMINAL_PROMPT"] == "0"
    assert entorno["GCM_INTERACTIVE"] == "never"


# ---------------------------------------------------------------- progreso y errores


@pytest.mark.parametrize(
    ("linea", "esperado"),
    [
        ("Receiving objects:   0% (0/212)", 10),
        ("Receiving objects:  50% (106/212), 40 KiB", 45),
        ("Receiving objects: 100% (212/212), 88.4 KiB, done.", 80),
        ("Resolving deltas: 100% (31/31), done.", 95),
        ("Cloning into 'repositorio'...", None),
    ],
)
def test_porcentaje_total_por_fase(linea, esperado):
    assert clonador.porcentaje_total(linea) == esperado


@pytest.mark.parametrize(
    ("stderr", "tipo"),
    [
        ("fatal: Remote branch dev not found in upstream origin", "rama_inexistente"),
        ("remote: Repository not found.\nfatal: repository 'https://github.com/u/r/' not found",
         "privado_o_inexistente"),
        ("fatal: could not read Username for 'https://github.com': terminal prompts disabled",
         "privado_o_inexistente"),
        ("fatal: unable to access 'https://x.y/u/r/': Could not resolve host: x.y", "sin_red"),
        ("fatal: algo inesperado", "git"),
    ],
)  # fmt: skip
def test_interpretar_error_diferencia_motivos(stderr, tipo):
    obtenido, mensaje = clonador.interpretar_error(stderr, "dev")
    assert obtenido == tipo
    assert mensaje


# ---------------------------------------------------------------- clonar


def test_clonar_exitoso_reporta_avance_y_pasa_entorno(tmp_path):
    stderr = "Cloning into 'r'...\rReceiving objects:  50% (1/2)\rReceiving objects: 100% (2/2)\n"
    popen = _popen_falso(stderr, 0, crear_destino=True)
    avances: list[tuple[int | None, str]] = []

    resultado = clonador.clonar(
        URL_OK,
        "main",
        tmp_path / "r",
        al_avanzar=lambda p, ln: avances.append((p, ln)),
        popen=popen,
    )

    assert resultado.ok and resultado.error is None
    assert [p for p, _ in avances] == [None, 45, 80]
    llamada = popen.llamadas[0]
    assert llamada["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert "shell" not in llamada
    assert isinstance(llamada["comando"], list)


def test_clonar_git_no_instalado(tmp_path):
    def popen(*_args, **_kwargs):
        raise FileNotFoundError("git")

    resultado = clonador.clonar(URL_OK, "main", tmp_path / "r", popen=popen)

    assert not resultado.ok
    assert resultado.tipo_error == "git_no_instalado"
    assert "Git no está instalado" in resultado.error
    assert not (tmp_path / "r").exists()


def test_clonar_fallido_no_deja_carpeta_residual(tmp_path):
    destino = tmp_path / "proyectos" / "nuevos" / "r"
    popen = _popen_falso("remote: Repository not found.", 128, crear_destino=True)

    resultado = clonador.clonar(URL_OK, "main", destino, popen=popen)

    assert resultado.tipo_error == "privado_o_inexistente"
    # Tampoco quedan las carpetas padre que creó git
    assert not (tmp_path / "proyectos").exists()
    assert list(tmp_path.iterdir()) == []


def test_clonar_rama_inexistente(tmp_path):
    popen = _popen_falso("fatal: Remote branch nada not found in upstream origin", 128)
    resultado = clonador.clonar(URL_OK, "nada", tmp_path / "r", popen=popen)
    assert resultado.tipo_error == "rama_inexistente"
    assert "nada" in resultado.error


def test_clonar_fallido_no_borra_carpeta_vacia_preexistente(tmp_path):
    destino = tmp_path / "r"
    destino.mkdir()
    popen = _popen_falso("remote: Repository not found.", 128)

    resultado = clonador.clonar(URL_OK, "main", destino, popen=popen)

    assert not resultado.ok
    assert destino.is_dir()


def test_clonar_rechaza_destino_existente_no_vacio_sin_tocarlo(tmp_path):
    destino = tmp_path / "r"
    destino.mkdir()
    (destino / "importante.txt").write_text("no borrar", encoding="utf-8")
    popen = _popen_falso("", 0)

    resultado = clonador.clonar(URL_OK, "main", destino, popen=popen)

    assert resultado.tipo_error == "destino_ocupado"
    assert popen.llamadas == []  # git ni siquiera se ejecuta
    assert (destino / "importante.txt").read_text(encoding="utf-8") == "no borrar"


@pytest.mark.parametrize(
    ("url", "rama", "tipo"),
    [
        ("http://github.com/u/r", "main", "url_invalida"),
        (URL_OK, "--x", "rama_invalida"),
    ],
)
def test_clonar_con_datos_invalidos_no_ejecuta_git(url, rama, tipo, tmp_path):
    popen = _popen_falso("", 0)
    resultado = clonador.clonar(url, rama, tmp_path / "r", popen=popen)
    assert resultado.tipo_error == tipo
    assert popen.llamadas == []
    assert not (tmp_path / "r").exists()


# ---------------------------------------------------------------- integración (red)


def _hay_red(host: str = "github.com") -> bool:
    try:
        socket.create_connection((host, 443), timeout=3).close()
        return True
    except OSError:
        return False


requiere_red = pytest.mark.skipif(
    shutil.which("git") is None or not _hay_red(),
    reason="sin Git o sin conexión a internet",
)


@pytest.mark.red
@requiere_red
def test_integracion_clona_repositorio_publico_pequeno(tmp_path):
    destino = tmp_path / "proyectos" / "Hello-World"
    avances: list[int | None] = []

    resultado = clonador.clonar(
        "https://github.com/octocat/Hello-World.git",
        "master",
        destino,
        al_avanzar=lambda p, _ln: avances.append(p),
    )

    assert resultado.ok, resultado.error
    assert (destino / "README").is_file()
    commits = subprocess.run(
        ["git", "-C", str(destino), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert commits.stdout.strip() == "1"  # clonado superficial


@pytest.mark.red
@requiere_red
def test_integracion_repositorio_inexistente_no_crea_carpeta(tmp_path):
    destino = tmp_path / "proyectos" / "no-existe"

    resultado = clonador.clonar(
        "https://github.com/octocat/este-repo-no-existe-qagent-hu02.git",
        "main",
        destino,
    )

    assert resultado.tipo_error == "privado_o_inexistente"
    assert not (tmp_path / "proyectos").exists()

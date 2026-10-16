"""Regresión de la issue #61: los clones exitosos aparecen en recientes."""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from qagent.almacenamiento import recientes
from qagent.app import desktop
from qagent.proyectos import clonador
from qagent.proyectos.proyecto_local import detectar_rama

URL = "https://qagent.test/equipo/demo.git"


@pytest.fixture
def archivo_recientes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aísla el registro de recientes del home real."""
    archivo = tmp_path / "home" / ".qagent" / "recientes.json"
    monkeypatch.setattr(desktop.recientes, "ruta_por_defecto", lambda: archivo)
    return archivo


def _ejecutar_clonado(
    api: desktop.DesktopAPI,
    destino: Path,
    rama: str = "main",
    al_emitir: Callable[[str, dict], None] | None = None,
) -> list[dict]:
    """Inicia el clonado y espera su evento final sin abrir una ventana real."""
    eventos: list[dict] = []
    terminado = threading.Event()

    def emitir(tipo: str, datos: dict) -> None:
        eventos.append({"tipo": tipo, "datos": datos})
        if al_emitir:
            al_emitir(tipo, datos)
        if tipo == "clonado_fin":
            terminado.set()

    api.emit_event = emitir  # type: ignore[method-assign]
    assert api.clonar_repositorio(URL, rama, str(destino)) == {"iniciado": True}
    assert terminado.wait(15), "No se recibió el evento clonado_fin"
    return eventos


def test_clonado_exitoso_registra_antes_del_evento_y_persiste(
    tmp_path: Path,
    archivo_recientes: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destino = tmp_path / "demo-personalizado"
    destino.mkdir()
    orden: list[str] = []
    registrar_real = recientes.registrar

    def clonar_exitoso(*_args, **_kwargs) -> clonador.ResultadoClonado:
        return clonador.ResultadoClonado(True, str(destino))

    def registrar_y_anotar(*args, **kwargs) -> None:
        orden.append("registrar")
        registrar_real(*args, **kwargs)

    monkeypatch.setattr(clonador, "clonar", clonar_exitoso)
    monkeypatch.setattr(desktop.recientes, "registrar", registrar_y_anotar)
    api = desktop.DesktopAPI()

    def emitir_y_anotar(tipo: str, datos: dict) -> None:
        if tipo == "clonado_fin":
            orden.append("evento")

    eventos = _ejecutar_clonado(api, destino, al_emitir=emitir_y_anotar)

    assert orden == ["registrar", "evento"]
    assert eventos[-1]["datos"] == {
        "ok": True,
        "destino": str(destino),
        "tipo_error": None,
        "error": None,
    }
    [guardado] = recientes.cargar(archivo_recientes)
    assert guardado["nombre"] == "demo-personalizado"
    assert guardado["origen"] == "git"
    assert guardado["ruta"] == str(destino)
    assert guardado["url"] == URL
    assert desktop.DesktopAPI().listar_recientes()[0]["ruta"] == str(destino)


def test_clonar_dos_veces_el_mismo_destino_no_duplica(
    tmp_path: Path,
    archivo_recientes: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destino = tmp_path / "demo"
    destino.mkdir()
    monkeypatch.setattr(
        clonador,
        "clonar",
        lambda *_args, **_kwargs: clonador.ResultadoClonado(True, str(destino)),
    )

    _ejecutar_clonado(desktop.DesktopAPI(), destino)
    _ejecutar_clonado(desktop.DesktopAPI(), destino)

    assert [p["ruta"] for p in recientes.cargar(archivo_recientes)] == [str(destino)]


def test_clonado_fallido_no_registra(
    tmp_path: Path,
    archivo_recientes: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destino = tmp_path / "demo"
    monkeypatch.setattr(
        clonador,
        "clonar",
        lambda *_args, **_kwargs: clonador.ResultadoClonado(
            False, str(destino), "rama_inexistente", "La rama no existe."
        ),
    )

    eventos = _ejecutar_clonado(desktop.DesktopAPI(), destino, "inexistente")

    assert eventos[-1]["datos"]["ok"] is False
    assert recientes.cargar(archivo_recientes) == []
    assert not archivo_recientes.exists()


def test_error_al_guardar_es_advertencia_y_el_clonado_sigue_exitoso(
    tmp_path: Path,
    archivo_recientes: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destino = tmp_path / "demo"
    destino.mkdir()
    monkeypatch.setattr(
        clonador,
        "clonar",
        lambda *_args, **_kwargs: clonador.ResultadoClonado(True, str(destino)),
    )

    def fallar_registro(*_args, **_kwargs) -> None:
        raise OSError("solo lectura")

    monkeypatch.setattr(desktop.recientes, "registrar", fallar_registro)

    eventos = _ejecutar_clonado(desktop.DesktopAPI(), destino)

    final = eventos[-1]["datos"]
    assert final["ok"] is True
    assert "advertencia" in final
    assert "Proyectos recientes" in final["advertencia"]
    assert not archivo_recientes.exists()


def _git(*args: str, cwd: Path | None = None) -> None:
    """Ejecuta Git únicamente sobre repositorios temporales de la prueba."""
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="Git no está instalado")
def test_clona_rama_especifica_desde_repositorio_local_sin_red(
    tmp_path: Path,
    archivo_recientes: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remotos = tmp_path / "remotos" / "equipo"
    remotos.mkdir(parents=True)
    remoto = remotos / "demo.git"
    semilla = tmp_path / "semilla"
    _git("init", "--bare", str(remoto))
    _git("init", "-b", "main", str(semilla))
    _git("config", "user.name", "QAgent Tests", cwd=semilla)
    _git("config", "user.email", "tests@qagent.local", cwd=semilla)
    (semilla / "main.py").write_text("ORIGEN = 'main'\n", encoding="utf-8")
    _git("add", "main.py", cwd=semilla)
    _git("commit", "-m", "main", cwd=semilla)
    _git("switch", "-c", "feature/demo", cwd=semilla)
    (semilla / "rama.py").write_text("RAMA = 'feature/demo'\n", encoding="utf-8")
    _git("add", "rama.py", cwd=semilla)
    _git("commit", "-m", "rama", cwd=semilla)
    _git("remote", "add", "origin", str(remoto), cwd=semilla)
    _git("push", "origin", "main", "feature/demo", cwd=semilla)

    base_local = (tmp_path / "remotos").as_uri() + "/"
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{base_local}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://qagent.test/")
    destino = tmp_path / "clonado"

    eventos = _ejecutar_clonado(desktop.DesktopAPI(), destino, "feature/demo")

    assert eventos[-1]["datos"]["ok"] is True
    assert detectar_rama(destino) == "feature/demo"
    assert (destino / "rama.py").is_file()
    [guardado] = recientes.cargar(archivo_recientes)
    assert guardado["ruta"] == str(destino)
    assert guardado["origen"] == "git"

"""Pruebas de la verificación del entorno (EN-06): config, claves, Docker y Git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from qagent.config import (
    MENSAJE_IA_SIMULADA,
    MENSAJE_LISTO,
    estado_git,
    verificar_entorno,
)
from qagent.config import entorno as modulo_entorno
from qagent.config.carga import RUTA_CONFIG

OK = {"estado": "ok", "mensaje": "ok"}
DOCKER_APAGADO = {
    "estado": "no_iniciado",
    "mensaje": "Docker Desktop no está iniciado.",
}
GIT_AUSENTE = {"estado": "no_instalado", "mensaje": "Git no está instalado."}


@pytest.fixture
def env_completo(tmp_path: Path) -> Path:
    ruta = tmp_path / ".env"
    ruta.write_text(
        "ANTHROPIC_API_KEY=a-prueba-1\n"
        "OPENAI_API_KEY=o-prueba-1\n"
        "XIAOMI_API_KEY=x-prueba-1\n",
        encoding="utf-8",
    )
    return ruta


def _verificar(env: Path, docker=lambda: OK, git=lambda: OK, simulado=False) -> dict:
    return verificar_entorno(
        RUTA_CONFIG, env, simulado=simulado, docker=docker, git=git
    )


def test_todo_correcto_muestra_entorno_listo(env_completo):
    r = _verificar(env_completo)
    assert r["listo"] is True
    assert r["mensaje"] == MENSAJE_LISTO == "Entorno listo"
    assert r["problemas"] == []
    assert [c["id"] for c in r["comprobaciones"]] == [
        "config",
        "claves",
        "docker",
        "git",
    ]
    assert all(c["ok"] for c in r["comprobaciones"])


def test_sin_una_clave_no_esta_listo_y_dice_cual(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=a-prueba-1\nXIAOMI_API_KEY=x-prueba-1\n")
    r = _verificar(env)
    assert r["listo"] is False
    assert "OPENAI_API_KEY" in r["mensaje"]
    claves = next(c for c in r["comprobaciones"] if c["id"] == "claves")
    assert claves["ok"] is False


def test_docker_apagado_es_el_motivo(env_completo):
    r = _verificar(env_completo, docker=lambda: DOCKER_APAGADO)
    assert r["listo"] is False
    assert r["mensaje"] == DOCKER_APAGADO["mensaje"]


def test_docker_sin_imagen_no_bloquea_la_primera_corrida_la_prepara(env_completo):
    """TA-06 (cambia el criterio de EN-06, que bloqueaba): instalado no hay comando para
    construir la imagen, así que la prepara la primera corrida real."""
    r = _verificar(
        env_completo,
        docker=lambda: {"estado": "sin_imagen", "mensaje": "Falta la imagen"},
    )
    assert r["listo"] is True
    docker = next(c for c in r["comprobaciones"] if c["id"] == "docker")
    assert docker["ok"] is True and docker["pendiente"] is True
    assert docker["mensaje"] == "Falta la imagen"  # se sigue informando


def test_docker_apagado_sigue_bloqueando_aunque_falte_la_imagen(env_completo):
    r = _verificar(env_completo, docker=lambda: DOCKER_APAGADO)
    assert r["listo"] is False


def test_git_ausente_es_el_motivo(env_completo):
    r = _verificar(env_completo, git=lambda: GIT_AUSENTE)
    assert r["listo"] is False
    assert r["mensaje"] == GIT_AUSENTE["mensaje"]


def test_varios_problemas_se_listan_todos(tmp_path):
    r = _verificar(
        tmp_path / ".env", docker=lambda: DOCKER_APAGADO, git=lambda: GIT_AUSENTE
    )
    assert r["listo"] is False
    # .env creado + 4 claves vacías (una por agente, HU-30 y EP-10) + Docker + Git
    assert len(r["problemas"]) == 7
    assert DOCKER_APAGADO["mensaje"] in r["problemas"]
    assert GIT_AUSENTE["mensaje"] in r["problemas"]
    assert "(y 6 problema(s) más)" in r["mensaje"]


def test_ia_simulada_se_informa_y_no_dice_que_cargo_claves(tmp_path):
    r = _verificar(tmp_path / ".env", simulado=True)
    assert r["listo"] is True and r["simulado"] is True
    claves = next(c for c in r["comprobaciones"] if c["id"] == "claves")
    assert claves["mensaje"] == MENSAJE_IA_SIMULADA
    assert not (tmp_path / ".env").exists()  # no crea .env si no hace falta


def test_ia_real_se_informa(env_completo):
    assert _verificar(env_completo)["simulado"] is False


def test_ia_simulada_por_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    r = verificar_entorno(
        RUTA_CONFIG, tmp_path / ".env", docker=lambda: OK, git=lambda: OK
    )
    assert r["listo"] is True and r["simulado"] is True


def test_ia_simulada_no_exige_claves_ni_docker(tmp_path):
    r = _verificar(tmp_path / ".env", docker=lambda: DOCKER_APAGADO, simulado=True)
    assert r["listo"] is True
    assert r["problemas"] == []
    docker = next(c for c in r["comprobaciones"] if c["id"] == "docker")
    assert docker["ok"] is True and docker["opcional"] is True
    assert modulo_entorno.MENSAJE_DOCKER_OPCIONAL in docker["mensaje"]
    assert (
        DOCKER_APAGADO["mensaje"] in docker["mensaje"]
    )  # se sigue informando qué pasa


def test_ia_simulada_con_docker_disponible_no_marca_nada_como_opcional(tmp_path):
    r = _verificar(tmp_path / ".env", simulado=True)
    docker = next(c for c in r["comprobaciones"] if c["id"] == "docker")
    assert docker["ok"] is True and "opcional" not in docker


def test_ia_simulada_sigue_exigiendo_git(tmp_path):
    r = _verificar(tmp_path / ".env", git=lambda: GIT_AUSENTE, simulado=True)
    assert r["listo"] is False
    assert GIT_AUSENTE["mensaje"] in r["problemas"]


def test_ia_real_sigue_exigiendo_docker(env_completo):
    r = _verificar(env_completo, docker=lambda: DOCKER_APAGADO, simulado=False)
    assert r["listo"] is False
    assert DOCKER_APAGADO["mensaje"] in r["problemas"]


def test_config_invalida_bloquea(tmp_path, env_completo):
    mala = tmp_path / "config.toml"
    mala.write_text("[presupuesto]\ntope_por_corrida_usd = 1.0\n", encoding="utf-8")
    r = verificar_entorno(
        mala, env_completo, simulado=False, docker=lambda: OK, git=lambda: OK
    )
    assert r["listo"] is False
    assert next(c for c in r["comprobaciones"] if c["id"] == "config")["ok"] is False


# ---------- Git ----------


def test_estado_git_ok_en_este_equipo():
    if modulo_entorno.shutil.which("git") is None:
        pytest.skip("git no está instalado en este equipo")
    assert estado_git()["estado"] == "ok"


def test_estado_git_no_instalado(monkeypatch):
    monkeypatch.setattr(modulo_entorno.shutil, "which", lambda _: None)
    # #251: tampoco está en las carpetas del instalador ni en el PATH del registro.
    monkeypatch.setattr(modulo_entorno, "_carpetas_git", lambda _entorno: [])
    monkeypatch.setattr(modulo_entorno, "_path_del_registro", list)
    assert estado_git()["estado"] == "no_instalado"


# ---------- Git instalado con la app abierta (#251) ----------


def _git_falso(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True)
    ejecutable = carpeta / "git.exe"
    ejecutable.write_text("", encoding="utf-8")
    return ejecutable


def test_buscar_git_usa_el_path_si_lo_encuentra(monkeypatch):
    monkeypatch.setattr(modulo_entorno.shutil, "which", lambda _: "C:/git/git.exe")
    entorno = {"PATH": "C:/otra"}
    assert modulo_entorno.buscar_git(entorno, list, en_windows=True) == (
        "C:/git/git.exe"
    )
    assert entorno == {"PATH": "C:/otra"}


def test_buscar_git_en_la_carpeta_del_instalador_y_lo_agrega_al_path(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(modulo_entorno.shutil, "which", lambda _: None)
    ejecutable = _git_falso(tmp_path / "Archivos" / "Git" / "cmd")
    entorno = {"ProgramFiles": str(tmp_path / "Archivos"), "PATH": "C:/antes"}
    assert modulo_entorno.buscar_git(entorno, list, en_windows=True) == str(ejecutable)
    assert entorno["PATH"].split(modulo_entorno.os.pathsep) == [
        str(ejecutable.parent),
        "C:/antes",
    ]


def test_buscar_git_en_el_path_del_registro(monkeypatch, tmp_path):
    monkeypatch.setattr(modulo_entorno.shutil, "which", lambda _: None)
    ejecutable = _git_falso(tmp_path / "nuevo" / "bin")
    entorno: dict[str, str] = {}
    encontrado = modulo_entorno.buscar_git(
        entorno, lambda: [str(tmp_path / "vacia"), str(ejecutable.parent)], True
    )
    assert encontrado == str(ejecutable)
    assert entorno["PATH"] == str(ejecutable.parent)


def test_buscar_git_fuera_de_windows_solo_mira_el_path(monkeypatch, tmp_path):
    monkeypatch.setattr(modulo_entorno.shutil, "which", lambda _: None)
    _git_falso(tmp_path / "Git" / "cmd")
    entorno = {"ProgramFiles": str(tmp_path)}
    assert modulo_entorno.buscar_git(entorno, list, en_windows=False) is None
    assert "PATH" not in entorno


def test_sin_git_el_mensaje_pide_comprobar_de_nuevo(monkeypatch):
    monkeypatch.setattr(modulo_entorno, "buscar_git", lambda: None)
    estado = estado_git()
    assert estado["estado"] == "no_instalado"
    assert "Comprobar de nuevo" in estado["mensaje"]
    assert "reinicia QAgent" in estado["mensaje"]


def test_estado_git_que_falla(monkeypatch):
    monkeypatch.setattr(modulo_entorno.shutil, "which", lambda _: "git")

    def falla(*_a, **_k):
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(modulo_entorno.subprocess, "run", falla)
    assert estado_git()["estado"] == "error"


def test_estado_git_con_codigo_de_error(monkeypatch):
    monkeypatch.setattr(modulo_entorno.shutil, "which", lambda _: "git")
    monkeypatch.setattr(
        modulo_entorno.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(["git"], 1, "", "boom"),
    )
    assert estado_git()["estado"] == "error"

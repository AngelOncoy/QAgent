"""HU-13: pruebas unitarias del aislamiento (no necesitan Docker)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pyagent.sandbox import (
    MENSAJE_DOCKER_CERRADO,
    DockerNoDisponible,
    ResultadoSandbox,
    clasificar_resultado,
    copiar_proyecto,
    verificar_docker,
)
from pyagent.sandbox import estado as modulo_estado


def test_mensaje_de_docker_cerrado_es_el_del_criterio():
    assert (
        MENSAJE_DOCKER_CERRADO == "Docker no está abierto: inícialo y vuelve a intentar"
    )


@pytest.mark.parametrize("estado", ["no_iniciado", "no_instalado"])
def test_verificar_docker_falla_con_el_mensaje_exacto(estado):
    with (
        patch.object(
            modulo_estado,
            "estado_docker",
            return_value={"estado": estado, "mensaje": "otro texto"},
        ),
        pytest.raises(DockerNoDisponible) as error,
    ):
        verificar_docker()

    assert str(error.value) == MENSAJE_DOCKER_CERRADO


@pytest.mark.parametrize("estado", ["ok", "sin_imagen"])
def test_verificar_docker_no_falla_si_docker_responde(estado):
    with patch.object(
        modulo_estado, "estado_docker", return_value={"estado": estado, "mensaje": ""}
    ):
        verificar_docker()


@pytest.mark.parametrize(
    ("resultado", "esperado"),
    [
        (ResultadoSandbox(exit_code=0, stdout="", stderr=""), "ok"),
        (ResultadoSandbox(exit_code=1, stdout="", stderr=""), "fallo"),
        (ResultadoSandbox(exit_code=2, stdout="", stderr=""), "error"),
        (
            ResultadoSandbox(exit_code=137, stdout="", stderr="", timed_out=True),
            "timeout",
        ),
        (ResultadoSandbox(exit_code=137, stdout="", stderr="", oom_killed=True), "oom"),
    ],
)
def test_clasificar_resultado_usa_el_enum_del_contrato(resultado, esperado):
    assert clasificar_resultado(resultado) == esperado


def test_copia_excluye_archivos_de_credenciales(tmp_path: Path):
    proyecto = tmp_path / "proyecto"
    (proyecto / "certs").mkdir(parents=True)
    (proyecto / "app.py").write_text("x = 1\n", encoding="utf-8")
    for secreto in (
        ".env",
        ".env.production",
        "certs/servidor.pem",
        "certs/privada.key",
        "id_rsa",
        "id_ed25519.pub",
        ".netrc",
        ".pypirc",
    ):
        (proyecto / secreto).write_text("secreto", encoding="utf-8")

    copia = copiar_proyecto(proyecto, tmp_path / "copia")

    copiados = {p.relative_to(copia).as_posix() for p in copia.rglob("*")}
    assert copiados == {"app.py", "certs"}

"""Avance de la construcción de la imagen del sandbox (sin Docker real ni red)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import APIError, ImageNotFound

from qagent.orchestrator.corrida import avance_limitado
from qagent.sandbox import IMAGEN_BASE, construir_imagen_base, preparar_imagen
from qagent.sandbox.imagen import (
    AVISO_BASE,
    AVISO_DEPENDENCIAS,
    AVISO_LISTO,
    describir_linea,
)
from qagent.sandbox.modelos import ErrorConstruccionImagen

LOG_PIP = [
    {"stream": "Step 1/5 : FROM qagent-sandbox:base\n"},
    {"stream": "Collecting torch~=2.7.1\n"},
    {
        "stream": "  Downloading torch-2.7.1-cp311-cp311-manylinux_2_28_x86_64.whl (821.0 MB)\n"
    },
    {"stream": "Installing collected packages: numpy, torch\n"},
    {"stream": "Successfully installed numpy-2.2.4 torch-2.7.1\n"},
]


def _solo_existe_la_base(etiqueta: str) -> MagicMock:
    if etiqueta != IMAGEN_BASE:
        raise ImageNotFound(etiqueta)
    return MagicMock()


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    (tmp_path / "requirements.txt").write_text("torch~=2.7.1\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("linea", "esperado"),
    [
        ("Collecting torch~=2.7.1", "Preparando torch"),
        (
            "  Downloading torch-2.7.1-cp311-cp311-manylinux_2_28_x86_64.whl (821.0 MB)",
            "Descargando torch (821.0 MB)",
        ),
        (
            "Downloading https://files.example/opencv_python-4.11.0.86-cp37-abi3.whl (63 MB)",
            "Descargando opencv_python (63 MB)",
        ),
        (
            "Installing collected packages: numpy, torch, pillow",
            "Instalando 3 paquetes",
        ),
        ("Installing collected packages: numpy", "Instalando 1 paquete"),
        ("Successfully installed numpy-2.2.4", AVISO_LISTO),
        ("Step 1/5 : FROM qagent-sandbox:base", None),
        ("WARNING: Running pip as the 'root' user", None),
        ("", None),
    ],
)
def test_describir_linea_traduce_solo_los_pasos_utiles(
    linea: str, esperado: str | None
) -> None:
    assert describir_linea(linea) == esperado


def test_preparar_imagen_informa_las_fases_y_los_pasos_de_pip(proyecto: Path) -> None:
    cliente = MagicMock()
    cliente.images.get.side_effect = _solo_existe_la_base
    cliente.api.build.return_value = iter(LOG_PIP)
    avances: list[str] = []

    etiqueta = preparar_imagen(proyecto, cliente=cliente, avanzar=avances.append)

    assert etiqueta.startswith("qagent-sandbox:req-")
    assert cliente.api.build.call_args.kwargs["decode"] is True
    cliente.images.build.assert_not_called()
    assert avances[0] == AVISO_DEPENDENCIAS
    assert "Preparando torch" in avances
    assert "Descargando torch (821.0 MB)" in avances
    assert "Instalando 2 paquetes" in avances
    assert avances[-1] == AVISO_LISTO


def test_sin_avance_se_construye_como_siempre(proyecto: Path) -> None:
    cliente = MagicMock()
    cliente.images.get.side_effect = _solo_existe_la_base

    preparar_imagen(proyecto, cliente=cliente)

    cliente.images.build.assert_called_once()
    cliente.api.build.assert_not_called()


def test_imagen_existente_no_construye_ni_informa(proyecto: Path) -> None:
    cliente = MagicMock()
    avances: list[str] = []

    preparar_imagen(proyecto, cliente=cliente, avanzar=avances.append)

    cliente.api.build.assert_not_called()
    assert avances == []


def test_un_error_del_build_conserva_el_log(proyecto: Path) -> None:
    cliente = MagicMock()
    cliente.images.get.side_effect = _solo_existe_la_base
    cliente.api.build.return_value = iter(
        [
            {"stream": "Collecting paquete-roto\n"},
            {"error": "pip falló: no existe paquete-roto"},
        ]
    )

    with pytest.raises(ErrorConstruccionImagen, match="requirements.txt") as error:
        preparar_imagen(proyecto, cliente=cliente, avanzar=lambda _texto: None)

    assert "Collecting paquete-roto" in error.value.log
    assert "pip falló" in error.value.log


def test_un_error_de_la_api_se_traduce(proyecto: Path) -> None:
    cliente = MagicMock()
    cliente.images.get.side_effect = _solo_existe_la_base
    cliente.api.build.side_effect = APIError("daemon caído")

    with pytest.raises(ErrorConstruccionImagen):
        preparar_imagen(proyecto, cliente=cliente, avanzar=lambda _texto: None)


def test_un_fallo_de_quien_escucha_no_corta_la_construccion(proyecto: Path) -> None:
    cliente = MagicMock()
    cliente.images.get.side_effect = _solo_existe_la_base
    cliente.api.build.return_value = iter(LOG_PIP)

    def avanzar(_texto: str) -> None:
        raise RuntimeError("la interfaz se cerró")

    assert preparar_imagen(proyecto, cliente=cliente, avanzar=avanzar).startswith(
        "qagent-sandbox:req-"
    )


def test_la_imagen_base_informa_su_fase() -> None:
    cliente = MagicMock()
    cliente.api.build.return_value = iter(
        [{"stream": "Step 1/3 : FROM python:3.11-slim\n"}]
    )
    avances: list[str] = []

    assert construir_imagen_base(cliente, avanzar=avances.append) == IMAGEN_BASE
    assert avances == [AVISO_BASE]


def test_avance_limitado_respeta_el_intervalo_y_deja_pasar_las_fases() -> None:
    enviados: list[str] = []
    momentos = iter([0.0, 0.5, 1.0, 1.2, 3.5])
    avanzar = avance_limitado(
        enviados.append, intervalo_s=2.0, reloj=lambda: next(momentos)
    )

    avanzar(AVISO_DEPENDENCIAS)  # 0.0: fase, pasa
    avanzar("Preparando torch")  # 0.5: muy pronto, se descarta
    avanzar("Descargando torch (821 MB)")  # 1.0: muy pronto, se descarta
    avanzar(AVISO_LISTO)  # 1.2: fase, pasa aunque sea pronto
    avanzar("Preparando numpy")  # 3.5: pasaron 2,3 s desde el último enviado, pasa
    avanzar("Preparando numpy")  # repetido: no se reenvía (no consume reloj)

    assert enviados == [AVISO_DEPENDENCIAS, AVISO_LISTO, "Preparando numpy"]

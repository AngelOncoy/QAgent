"""#150: el backend rechaza `reg_deep` sin funciones críticas repetibles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.app.desktop import DesktopAPI
from qagent.orchestrator.regresion import (
    funciones_criticas_repetibles,
    huellas_de_objetivos,
)


def _contrato(objetivo: str, casos: list[dict]) -> dict:
    return {
        "version": "2",
        "modulo": "modulo.py",
        "huella": "1" * 64,
        "tipo": "funcion",
        "objetivo": objetivo,
        "firma": "(x)",
        "critical": False,
        "llama_a": [],
        "casos": casos,
    }


def _guardar_spec(
    raiz: Path, objetivo: str, casos: list[dict], *, archivo: bool = True
) -> None:
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    nombre = f"test_{objetivo}.py"
    if archivo:
        almacen.guardar_prueba_aprobada(nombre, "def test_guardada():\n    pass\n")
    huella = huellas_de_objetivos(raiz)[("modulo.py", objetivo)]
    almacen.guardar_spec(
        _contrato(objetivo, casos),
        "20261028-000000-150a",
        archivo_prueba=nombre,
        huella_objetivo=huella,
    )


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    (tmp_path / "modulo.py").write_text(
        "def valida(x):\n    return x * 2\n\ndef trivial(x):\n    return x\n",
        encoding="utf-8",
    )
    _guardar_spec(
        tmp_path,
        "valida",
        [
            {
                "id": "normal",
                "entrada": {"x": 2},
                "valor_esperado": 4,
                "origen": "docstring",
                "categoria": "normal",
            }
        ],
    )
    _guardar_spec(
        tmp_path,
        "trivial",
        [
            {
                "id": "firma",
                "entrada": {},
                "excepcion": "TypeError",
                "origen": "firma",
                "categoria": "error",
            }
        ],
    )
    return tmp_path


def _seleccion(*criticas: str) -> list[dict]:
    return [
        {
            "ruta": "modulo.py",
            "funciones": ["valida", "trivial"],
            "endpoints": [],
            "criticas": list(criticas),
        }
    ]


def test_elegibilidad_backend_respeta_seleccion_y_filtro_typeerror(
    proyecto: Path,
) -> None:
    assert funciones_criticas_repetibles(proyecto, _seleccion("valida")) == [
        {"modulo": "modulo.py", "objetivo": "valida"}
    ]
    assert funciones_criticas_repetibles(proyecto, _seleccion("trivial")) == []
    assert funciones_criticas_repetibles(proyecto, _seleccion()) == []
    assert funciones_criticas_repetibles(proyecto, None) == []


def test_start_run_rechaza_reg_deep_manipulado_sin_elegibles(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verificar = Mock()
    monkeypatch.setattr("qagent.sandbox.verificar_docker", verificar)

    resultado = DesktopAPI().start_run(str(proyecto), "reg_deep", _seleccion("trivial"))

    assert resultado["status"] == "perfil_no_disponible"
    assert "función crítica" in resultado["mensaje"]
    verificar.assert_not_called()


def test_start_run_acepta_reg_deep_con_critica_valida(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    monkeypatch.setattr("qagent.sandbox.verificar_docker", lambda: None)
    monkeypatch.setattr(
        "qagent.config.verificar_entorno",
        lambda *_args, **_kwargs: {
            "listo": True,
            "mensaje": "",
            "problemas": [],
        },
    )
    monkeypatch.setattr("qagent.app.desktop._registrar_run", lambda *_a, **_k: "run")
    api = DesktopAPI()
    lanzar = Mock()
    monkeypatch.setattr(api, "_lanzar_corrida", lanzar)

    resultado = api.start_run(str(proyecto), "reg_deep", _seleccion("valida"))

    assert resultado["status"] == "started"
    assert resultado["profile"] == "reg_deep"
    assert resultado["modo"] == "real"
    lanzar.assert_called_once()
    assert lanzar.call_args.args[1] == "reg_deep"


def test_regresion_normal_no_exige_criticas(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    monkeypatch.setattr("qagent.sandbox.verificar_docker", lambda: None)
    monkeypatch.setattr(
        "qagent.config.verificar_entorno",
        lambda *_args, **_kwargs: {
            "listo": True,
            "mensaje": "",
            "problemas": [],
        },
    )
    monkeypatch.setattr("qagent.app.desktop._registrar_run", lambda *_a, **_k: "run")
    api = DesktopAPI()
    monkeypatch.setattr(api, "_lanzar_corrida", Mock())

    resultado = api.start_run(str(proyecto), "reg", _seleccion())

    assert resultado["status"] == "started"
    assert resultado["profile"] == "reg"

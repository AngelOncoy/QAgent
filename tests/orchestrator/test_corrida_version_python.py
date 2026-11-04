"""Pruebas para el manejo de versiones de Python en la corrida del orquestador (sin Docker).

Cubre:
- Detención temprana con mensaje claro si el proyecto pide una versión de Python fuera de rango.
- Emisión de eventos de entorno con estado 'fallo' y mensaje explicativo.
- No invocación de Docker ni del LLM cuando la versión no está soportada.
- Inclusión de la versión de Python en los avisos del Monitor (preparando y listo).
- Elección de la imagen base adecuada (ej. base-py3.12) para _preparar_imagen.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import FALLO, ejecutar_corrida

FUNCION_PY = (
    'def duplicar(x: int) -> int:\n    """Devuelve 2 * x."""\n    return 2 * x\n'
)


def _escribir(raiz: Path, archivos: dict[str, str]) -> Path:
    for ruta, texto in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return raiz


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


def test_corrida_detenida_cuando_version_python_no_soportada_menor(
    tmp_path: Path, config
) -> None:
    _escribir(
        tmp_path,
        {
            "calc.py": FUNCION_PY,
            ".python-version": "3.9\n",
        },
    )
    AlmacenProyecto(tmp_path).inicializar()
    eventos: list[dict] = []
    preparar = MagicMock()

    resumen = ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
        preparar_imagen=preparar,
    )

    assert resumen.estado == FALLO
    assert resumen.tipo_terminacion == "detenida_error"
    assert "3.9" in resumen.motivo
    assert "3.10" in resumen.motivo
    assert "3.14" in resumen.motivo

    # No se invoca la construcción de Docker ni la IA
    preparar.assert_not_called()
    assert not any(e.get("agente") == "planner" for e in eventos)

    # El aviso de fallo de entorno se emitió para el Monitor
    fallo_eventos = [
        e for e in eventos if (e.get("datos") or {}).get("entorno") == "fallo"
    ]
    assert len(fallo_eventos) == 1
    assert "3.9" in fallo_eventos[0]["mensaje"]
    assert "3.10" in fallo_eventos[0]["mensaje"]


def test_corrida_detenida_cuando_version_python_no_soportada_mayor(
    tmp_path: Path, config
) -> None:
    _escribir(
        tmp_path,
        {
            "calc.py": FUNCION_PY,
            "pyproject.toml": '[project]\nname = "demo"\nrequires-python = ">=3.15"\n',
        },
    )
    AlmacenProyecto(tmp_path).inicializar()
    eventos: list[dict] = []
    preparar = MagicMock()

    resumen = ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
        preparar_imagen=preparar,
    )

    assert resumen.estado == FALLO
    assert resumen.tipo_terminacion == "detenida_error"
    assert ">=3.15" in resumen.motivo
    preparar.assert_not_called()


def test_corrida_emite_version_en_eventos_entorno_cuando_version_312(
    tmp_path: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _escribir(
        tmp_path,
        {
            "calc.py": FUNCION_PY,
            ".python-version": "3.12\n",
        },
    )
    AlmacenProyecto(tmp_path).inicializar()
    eventos: list[dict] = []
    preparar_mock = MagicMock(return_value="qagent-sandbox:base-py3.12")
    monkeypatch.setattr("qagent.orchestrator.corrida._preparar_imagen", preparar_mock)

    # Mockeamos estado_docker para simular docker disponible
    monkeypatch.setattr(
        "qagent.sandbox.estado.estado_docker",
        lambda: {"instalado": True, "corriendo": True, "version": "24.0.0"},
    )
    # Mockeamos ejecutar_pruebas para no correr sandbox real
    resultado_mock = MagicMock()
    resultado_mock.pruebas_pasaron = True
    resultado_mock.exitoso = True
    resultado_mock.codigo_salida = 0
    monkeypatch.setattr(
        "qagent.orchestrator.corrida.ejecutar_pruebas",
        lambda *args, **kwargs: resultado_mock,
    )

    ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
    )

    # Verificar que _preparar_imagen recibió la imagen base con versión 3.12
    preparar_mock.assert_called_once()
    _, kwargs = preparar_mock.call_args
    assert kwargs.get("imagen_base") == "qagent-sandbox:base-py3.12"

    # Verificar avisos de entorno con la versión
    prep_eventos = [
        e for e in eventos if (e.get("datos") or {}).get("entorno") == "preparando"
    ]
    assert any("Python 3.12" in e.get("mensaje", "") for e in prep_eventos)

    listo_eventos = [
        e for e in eventos if (e.get("datos") or {}).get("entorno") == "listo"
    ]
    assert len(listo_eventos) == 1
    assert "Python 3.12" in listo_eventos[0].get("mensaje", "")


def test_corrida_por_defecto_usa_311_sin_declaracion(
    tmp_path: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _escribir(
        tmp_path,
        {
            "calc.py": FUNCION_PY,
        },
    )
    AlmacenProyecto(tmp_path).inicializar()
    eventos: list[dict] = []
    preparar_mock = MagicMock(return_value="qagent-sandbox:base")
    monkeypatch.setattr("qagent.orchestrator.corrida._preparar_imagen", preparar_mock)

    monkeypatch.setattr(
        "qagent.sandbox.estado.estado_docker",
        lambda: {"instalado": True, "corriendo": True, "version": "24.0.0"},
    )
    resultado_mock = MagicMock()
    resultado_mock.pruebas_pasaron = True
    resultado_mock.exitoso = True
    resultado_mock.codigo_salida = 0
    monkeypatch.setattr(
        "qagent.orchestrator.corrida.ejecutar_pruebas",
        lambda *args, **kwargs: resultado_mock,
    )

    ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
    )

    preparar_mock.assert_called_once()
    _, kwargs = preparar_mock.call_args
    assert kwargs.get("imagen_base") == "qagent-sandbox:base"

    prep_eventos = [
        e for e in eventos if (e.get("datos") or {}).get("entorno") == "preparando"
    ]
    assert any("Python 3.11" in e.get("mensaje", "") for e in prep_eventos)

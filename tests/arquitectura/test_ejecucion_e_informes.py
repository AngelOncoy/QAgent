from __future__ import annotations

from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento.proyecto import AlmacenProyecto
from qagent.arquitectura.ejecucion import (
    leer_resultado_arquitectura,
    verificar_arquitectura,
)
from qagent.arquitectura.informe import (
    construir_html,
    construir_markdown,
    construir_pdf,
    exportar,
)
from qagent.sandbox.modelos import ResultadoSandbox


def _proyecto_python(raiz: Path) -> None:
    paquete = raiz / "app"
    paquete.mkdir()
    (paquete / "__init__.py").touch()
    (paquete / "servicio.py").write_text("x = 1\n", encoding="utf-8")


def test_ejecucion_mock_persiste_run_y_no_usa_llm(monkeypatch, tmp_path: Path) -> None:
    _proyecto_python(tmp_path)
    fuente = (tmp_path / "app/servicio.py").read_bytes()
    llamadas = []

    def ejecutar(imagen, comando, ruta_proyecto, ruta_tests, **opciones):
        llamadas.append((imagen, comando, Path(ruta_tests)))
        assert comando[0] == "lint-imports"
        assert Path(ruta_tests, "importlinter-0.ini").is_file()
        return ResultadoSandbox(0, "", "", duracion_s=0.01)

    monkeypatch.setattr("qagent.arquitectura.ejecucion.ejecutar_en_sandbox", ejecutar)
    resultado = verificar_arquitectura(tmp_path)
    assert resultado["estado"] == "cumple"
    assert resultado["reglas"][0]["estado"] == "cumple"
    assert llamadas
    assert (tmp_path / "app/servicio.py").read_bytes() == fuente
    assert leer_resultado_arquitectura(tmp_path, resultado["run_id"]) == resultado
    run = AlmacenProyecto(tmp_path).leer_run(resultado["run_id"])
    assert run["tipos_prueba"] == ["arquitectura"]
    assert (tmp_path / ".qagent/runs" / resultado["run_id"] / "results.json").is_file()


def test_sugerencia_no_confirmada_queda_registrada_sin_sandbox(
    monkeypatch, tmp_path: Path
) -> None:
    _proyecto_python(tmp_path)
    AlmacenProyecto(tmp_path).guardar_reglas_arquitectura(
        {
            "version": "1",
            "reglas": [
                {
                    "id": "ia-001",
                    "tipo": "dependencia_prohibida",
                    "nombre": "Sugerida",
                    "origen": "ia",
                    "confirmada": False,
                    "desde": "app",
                    "hacia": "infra",
                }
            ],
        }
    )
    llamadas = 0

    def ejecutar(*args, **kwargs):
        nonlocal llamadas
        llamadas += 1
        return ResultadoSandbox(0, "", "")

    monkeypatch.setattr("qagent.arquitectura.ejecucion.ejecutar_en_sandbox", ejecutar)
    resultado = verificar_arquitectura(tmp_path)
    assert llamadas == 1  # solo la universal
    sugerida = next(r for r in resultado["reglas"] if r["id"] == "ia-001")
    assert sugerida["estado"] == "no_ejecutada"


def test_informes_incluyen_reglas_hallazgos_y_pdf_valido() -> None:
    datos = {
        "version": "1",
        "run_id": "20261031-120000-abcd",
        "lenguaje": "python",
        "estado": "incumple",
        "duracion_s": 1.25,
        "reglas": [
            {
                "id": "capas",
                "nombre": "Dominio no importa interfaz",
                "tipo": "dependencia_prohibida",
                "origen": "usuario",
                "estado": "incumple",
                "herramienta": "import-linter 2.15",
                "motivo_sin_veredicto": None,
                "hallazgos": [
                    {
                        "desde": "app.dominio",
                        "hacia": "app.interfaz",
                        "archivo": "app/dominio.py",
                        "linea": 7,
                    }
                ],
            }
        ],
    }
    contracts.validar_versionado(contracts.FAMILIA_ARCHITECTURE_RESULT, datos)
    markdown = construir_markdown(datos)
    html = construir_html(datos)
    pdf = construir_pdf(datos)
    assert "app/dominio.py:7" in markdown
    assert "Dominio no importa interfaz" in html
    assert pdf.startswith(b"%PDF-1.4")


def test_exporta_todos_los_formatos_desde_resultado_persistido(
    monkeypatch, tmp_path: Path
) -> None:
    _proyecto_python(tmp_path)
    monkeypatch.setattr(
        "qagent.arquitectura.ejecucion.ejecutar_en_sandbox",
        lambda *_args, **_kwargs: ResultadoSandbox(0, "", ""),
    )
    resultado = verificar_arquitectura(tmp_path)
    destino = tmp_path / "exportados"

    for formato in ("json", "md", "html", "pdf"):
        exportado = exportar(tmp_path, resultado["run_id"], formato, destino)
        ruta = Path(exportado["ruta"])
        assert ruta.is_file()
        assert ruta.stat().st_size > 0

    with pytest.raises(ValueError, match="formato"):
        exportar(tmp_path, resultado["run_id"], "exe", destino)

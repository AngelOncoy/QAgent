"""Comprueba la exportación reproducible y sus códigos de salida (EN-19)."""

import json
from pathlib import Path

import pytest

from qagent.lenguajes.prototipo_java import main


def test_exporta_banco_con_javadoc_y_medicion(tmp_path: Path) -> None:
    """Espera seis métodos del banco en JSON UTF-8 y un tiempo no negativo."""
    banco = Path(__file__).resolve().parents[2] / "bench_java"
    salida = tmp_path / "resultados" / "analisis.json"
    assert main([str(banco), "--salida", str(salida)]) == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["lenguaje"] == "java"
    assert datos["resumen"]["total_funciones_publicas"] == 6
    assert datos["errores"] == []
    assert datos["medicion"]["duracion_analisis_s"] >= 0
    assert datos["medicion"]["tree_sitter_java"] == "0.23.5"
    assert any(
        "vacía" in f["docstring"] for m in datos["modulos"] for f in m["funciones"]
    )


def test_exporta_error_parcial_con_estado_fallido(tmp_path: Path) -> None:
    """Una fuente rota queda registrada y el comando devuelve código 1."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    (proyecto / "Mal.java").write_text("class Mal {", encoding="utf-8")
    salida = tmp_path / "error.json"
    assert main([str(proyecto), "--salida", str(salida)]) == 1
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["resumen"]["total_errores"] == 1
    assert datos["errores"][0]["ruta"] == "Mal.java"


def test_carpeta_inexistente_no_crea_salida(tmp_path: Path) -> None:
    """Una ruta inexistente falla sin producir un informe de éxito vacío."""
    salida = tmp_path / "salida.json"
    assert main([str(tmp_path / "ausente"), "--salida", str(salida)]) == 1
    assert not salida.exists()


def test_no_sobrescribe_fuentes_java(tmp_path: Path) -> None:
    """Una salida con extensión Java es rechazada antes de modificar archivos."""
    fuente = tmp_path / "A.java"
    fuente.write_text("class A {}", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main([str(tmp_path), "--salida", str(fuente)])
    assert error.value.code == 2
    assert fuente.read_text(encoding="utf-8") == "class A {}"


def test_proyecto_sin_fuentes_no_es_exito(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Una carpeta sin fuentes genera resumen vacío con código 1 y diagnóstico."""
    assert main([str(tmp_path)]) == 1
    salida = capsys.readouterr()
    assert json.loads(salida.out)["resumen"]["total_modulos"] == 0
    assert "no encontró módulos" in salida.err

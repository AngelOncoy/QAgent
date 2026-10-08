"""Búsqueda de patrones de clave en el repositorio (EN-06, RN-07)."""

from __future__ import annotations

from pathlib import Path

from pyagent.config.auditoria import PATRONES, buscar_claves, main


def test_el_repositorio_no_contiene_patrones_de_clave():
    """Evidencia de aceptación de RN-07: ninguna clave versionada."""
    hallazgos = buscar_claves()
    assert hallazgos == [], "\n".join(str(h) for h in hallazgos)


def test_detecta_una_clave_plantada_y_no_la_repite(tmp_path: Path):
    clave = "sk-ant-" + "a1B2c3D4" * 4  # armada en ejecución: no es una clave real
    (tmp_path / "codigo.py").write_text(f'CLIENTE = "{clave}"\n', encoding="utf-8")
    hallazgos = buscar_claves(tmp_path)
    assert [(h.archivo, h.linea) for h in hallazgos] == [("codigo.py", 1)]
    assert clave not in str(hallazgos[0])


def test_detecta_asignaciones_genericas(tmp_path: Path):
    (tmp_path / "a.env.txt").write_text(
        "OPENAI_API_KEY=abcdefghijklmnop1234\n", encoding="utf-8"
    )
    assert len(buscar_claves(tmp_path)) == 1


def test_no_marca_lecturas_de_entorno_ni_valores_vacios(tmp_path: Path):
    (tmp_path / "ok.py").write_text(
        'api_key = os.getenv("ANTHROPIC_API_KEY")\nOPENAI_API_KEY=\ntokens = 120000\n',
        encoding="utf-8",
    )
    assert buscar_claves(tmp_path) == []


def test_ignora_imagenes_base64_incrustadas(tmp_path: Path):
    linea = '<img src="data:image/png;base64,' + "sk-" + "Zz9" * 20 + '">\n'
    (tmp_path / "ui.html").write_text(linea, encoding="utf-8")
    assert buscar_claves(tmp_path) == []


def test_no_revisa_el_env_real(tmp_path: Path):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=abcdefghijklmnop1234\n", encoding="utf-8"
    )
    assert buscar_claves(tmp_path) == []


def test_main_devuelve_codigo_de_salida(tmp_path: Path, capsys):
    assert main([str(tmp_path)]) == 0
    (tmp_path / "x.py").write_text(
        'SECRET = "abcdefghijklmnop1234"\n', encoding="utf-8"
    )
    assert main([str(tmp_path)]) == 1
    assert "x.py:1" in capsys.readouterr().out


def test_hay_patrones_para_los_proveedores_del_equipo():
    assert {"clave de Anthropic", "clave tipo OpenAI/OpenRouter"} <= set(PATRONES)

"""Los cuatro formatos exportados traen los casos y los datos de la ejecución (EN-17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento.proyecto import AlmacenProyecto
from qagent.storage.exportar_informe import exportar_informe, extraer_texto_pdf
from qagent.storage.registro import escribir_corrida
from tests.storage.test_exportar_informe import METAS
from tests.storage.test_registro import correr, precios  # noqa: F401 (fixture)

EJEMPLO = json.loads(
    (contracts.DIR_CONTRATOS / "ejemplos" / "detalle.json").read_text(encoding="utf-8")
)
EJECUCION = EJEMPLO["funciones"][0]["intentos"][0]["ejecucion"]


@pytest.fixture
def raiz(tmp_path: Path, precios) -> Path:  # noqa: F811
    """Corrida real escrita en disco con un fallo de pytest en su último intento."""
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    tracker, resultado = correr(precios, decisiones=("retry", "bug_detectado"))
    ultima = resultado.objetivos[0].revisiones[-1]
    ultima["ejecucion"] = json.loads(json.dumps(EJECUCION))
    escribir_corrida(
        tmp_path, resultado, tracker, precios, "deep", run_id=run_id, metas=METAS
    )
    return tmp_path


def _exportar(raiz: Path, formato: str, **opciones) -> Path:
    r = exportar_informe(raiz, formato=formato, opciones=opciones or None)
    return Path(r["ruta"])


def test_markdown_trae_datos_de_ejecucion_y_el_fallo(raiz: Path) -> None:
    texto = _exportar(raiz, "md").read_text(encoding="utf-8")

    assert "## 2.1 Datos de la ejecución" in texto
    assert "qagent-sandbox:base" in texto
    assert "## 2.2 Casos de prueba por función" in texto
    assert "[FALLÓ] test_doble_de_cuatro" in texto
    assert "Dónde: tests/test_generado.py:4" in texto
    assert "Esperado: 8" in texto and "Obtenido: 12" in texto
    assert "Intento 1: Reintento" in texto


def test_markdown_sin_trazas_omite_la_pila_y_la_salida(raiz: Path) -> None:
    texto = _exportar(raiz, "md", trazas=False).read_text(encoding="utf-8")

    assert "Dónde: tests/test_generado.py:4" in texto
    assert "Pila de llamadas" not in texto
    assert "Salida completa de pytest" not in texto


def test_json_trae_casos_con_dondes_y_valores(raiz: Path) -> None:
    datos = json.loads(_exportar(raiz, "json").read_text(encoding="utf-8"))

    ejecucion = datos["ejecucion"]
    assert ejecucion["entorno"]["pytest"] == "9.1.1"
    assert ejecucion["totales_casos"]["fallaron"] == 1
    [funcion] = ejecucion["funciones"]
    caso = funcion["intentos"][-1]["ejecucion"]["casos"][0]
    assert (caso["archivo"], caso["linea"]) == ("tests/test_generado.py", 4)
    assert (caso["obtenido"], caso["esperado"]) == ("12", "8")


def test_json_sin_trazas_quita_la_salida_y_las_trazas(raiz: Path) -> None:
    datos = json.loads(
        _exportar(raiz, "json", trazas=False).read_text(encoding="utf-8")
    )

    ejecucion = datos["ejecucion"]["funciones"][0]["intentos"][-1]["ejecucion"]
    assert "salida" not in ejecucion
    assert all("traza" not in c and c["pila"] == [] for c in ejecucion["casos"])
    assert ejecucion["casos"][0]["linea"] == 4  # dónde y qué siguen


def test_json_sin_detalle_no_trae_ejecucion(raiz: Path) -> None:
    datos = json.loads(
        _exportar(raiz, "json", detalle=False).read_text(encoding="utf-8")
    )

    assert "ejecucion" not in datos


def test_html_tiene_la_pestana_de_casos(raiz: Path) -> None:
    texto = _exportar(raiz, "html").read_text(encoding="utf-8")

    assert "3. Casos y ejecución" in texto
    assert "test_doble_de_cuatro" in texto
    assert "tests/test_generado.py:4" in texto
    assert "<script>" not in texto.split('id="t3"')[1].split("</div>\n</div>")[0]


def test_html_escapa_lo_que_viene_de_pytest(raiz: Path, precios) -> None:  # noqa: F811
    peligroso = json.loads(json.dumps(EJECUCION))
    peligroso["casos"][0]["nombre"] = "test_<script>alert(1)</script>"
    peligroso["casos"][0]["codigo"] = "assert '<img src=x onerror=1>'"
    almacen = AlmacenProyecto(raiz)
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    tracker, resultado = correr(precios, decisiones=("bug_detectado",))
    resultado.objetivos[0].revisiones[-1]["ejecucion"] = peligroso
    escribir_corrida(
        raiz, resultado, tracker, precios, "deep", run_id=run_id, metas=METAS
    )

    ruta = exportar_informe(raiz, run_id=run_id, formato="html")["ruta"]
    texto = Path(ruta).read_text(encoding="utf-8")

    assert "<script>alert(1)</script>" not in texto
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in texto
    assert "<img src=x" not in texto


def test_pdf_trae_los_casos_y_es_valido(raiz: Path) -> None:
    ruta = _exportar(raiz, "pdf")

    assert ruta.read_bytes().startswith(b"%PDF-1.4")
    texto = extraer_texto_pdf(ruta)
    assert "Datos de la ejecucion" in texto or "Datos de la ejecución" in texto
    assert "test_doble_de_cuatro" in texto
    assert "tests/test_generado.py:4" in texto


def test_corrida_sin_ejecucion_dice_por_que_en_todos_los_formatos(
    tmp_path: Path,
    precios,  # noqa: F811
) -> None:
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    tracker, resultado = correr(precios, decisiones=("accept",))
    escribir_corrida(
        tmp_path, resultado, tracker, precios, "deep", run_id=run_id, metas=METAS
    )

    md = _exportar(tmp_path, "md").read_text(encoding="utf-8")
    html = _exportar(tmp_path, "html").read_text(encoding="utf-8")
    datos = json.loads(_exportar(tmp_path, "json").read_text(encoding="utf-8"))

    assert "no guardó datos de ejecución" in md
    assert "no guardó datos de ejecución" in html
    assert datos["ejecucion"]["funciones"] == []
    assert _exportar(tmp_path, "pdf").read_bytes().startswith(b"%PDF-1.4")

"""El puente entrega al Reporte los datos de la corrida (HU-21)."""

from __future__ import annotations

import pytest

pytest.importorskip("webview")

from qagent.app.desktop import DesktopAPI
from qagent.llm import cargar_precios
from qagent.storage import escribir_corrida
from tests.storage.test_registro import correr


def test_obtener_reporte_de_la_ultima_corrida(tmp_path) -> None:
    precios = cargar_precios()
    tracker, resultado = correr(precios)
    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "deep")

    reporte = DesktopAPI().obtener_reporte(str(tmp_path))

    assert reporte["ok"] is True
    assert reporte["run_id"] == rutas.run_id
    assert reporte["detalle_disponible"] is True
    assert len(reporte["funciones"][0]["controles"]) == 5


def test_sin_resultados_devuelve_el_motivo(tmp_path) -> None:
    assert DesktopAPI().obtener_reporte(str(tmp_path))["ok"] is False


def test_exportar_informe_en_los_tres_formatos_y_carpeta_personalizada(
    tmp_path,
) -> None:
    """HU-22: el puente exporta PDF, Markdown y JSON en la carpeta por defecto o elegida."""
    from pathlib import Path

    precios = cargar_precios()
    tracker, resultado = correr(precios)
    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "deep")
    api = DesktopAPI()

    for fmt, prefijo in (("pdf", "informe_"), ("md", "informe_"), ("json", "results_")):
        res = api.exportar_informe(str(tmp_path), rutas.run_id, fmt)
        assert res["ok"] is True
        assert res["nombre"] == f"{prefijo}{rutas.run_id}.{fmt}"
        assert Path(res["ruta"]).is_file()

    otra = tmp_path / "otra_carpeta"
    res_otra = api.exportar_informe(
        str(tmp_path),
        rutas.run_id,
        "md",
        opciones={"detalle": False, "trazas": False, "codigo": True, "contratos": True},
        carpeta_destino=str(otra),
    )
    assert res_otra["ok"] is True
    assert Path(res_otra["ruta"]) == otra / f"informe_{rutas.run_id}.md"
    assert Path(res_otra["ruta"]).is_file()


def test_exportar_informe_falla_con_formato_invalido_o_sin_corrida(tmp_path) -> None:
    api = DesktopAPI()
    assert api.exportar_informe(str(tmp_path))["ok"] is False
    assert api.exportar_informe(str(tmp_path), formato="exe")["ok"] is False


def test_exportar_informe_en_modo_demostracion_crea_archivos_reales(tmp_path) -> None:
    """HU-22: en modo demostración (corrida #8841-B) también guarda el archivo real en disco."""
    from pathlib import Path

    from qagent.storage.exportar_informe import (
        extraer_texto_pdf,
        verificar_archivo_sin_claves,
    )

    api = DesktopAPI()
    carpeta = api.carpeta_corrida(str(tmp_path), "8841-B")
    assert carpeta.endswith("8841-B\\")

    for fmt, prefijo in (("pdf", "informe_"), ("md", "informe_"), ("json", "results_")):
        res = api.exportar_informe(
            str(tmp_path),
            "8841-B",
            fmt,
            opciones={
                "detalle": True,
                "trazas": True,
                "codigo": True,
                "contratos": True,
            },
        )
        assert res["ok"] is True
        assert res["nombre"] == f"{prefijo}8841-B.{fmt}"
        ruta = Path(res["ruta"])
        assert ruta.is_file()
        assert verificar_archivo_sin_claves(ruta) == []

    # Verifica que results.json quedó creado en la carpeta de la corrida y el PDF abre con las 5 métricas
    assert (tmp_path / ".qagent" / "runs" / "8841-B" / "results.json").is_file()
    texto_pdf = extraer_texto_pdf(
        tmp_path / ".qagent" / "runs" / "8841-B" / "informe_8841-B.pdf"
    )
    assert "66.7% (6/9)" in texto_pdf
    assert "53.3% (6 críticas)" in texto_pdf
    assert "4 reutilizados" in texto_pdf

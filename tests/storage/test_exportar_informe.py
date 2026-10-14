"""Exportación del informe de la corrida como evidencia formal (HU-22)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent.almacenamiento.proyecto import AlmacenProyecto
from qagent.config.auditoria import buscar_claves
from qagent.config.carga import Claves
from qagent.storage.exportar_informe import (
    FormatoInvalido,
    exportar_informe,
    extraer_texto_pdf,
    verificar_archivo_sin_claves,
)
from qagent.storage.registro import escribir_corrida
from qagent.storage.vista_ejecucion import leer_results, vista_ejecucion
from qagent.storage.vista_reporte import leer_detalle, vista_reporte
from tests.storage.test_registro import correr, precios  # noqa: F401 (fixture)

METAS = {
    "pass_rate_min": 70,
    "cobertura_lineas_min": 60,
    "iteraciones_promedio_max": 2.0,
    "tope_por_corrida_usd": 1.0,
}

# Claves falsas armadas en ejecución para no activar el escáner estático en este archivo.
CLAVE_OPENAI_FALSA = "sk-proj-" + "A1b2C3d4" * 5
CLAVE_ANTHROPIC_FALSA = "sk-ant-" + "Z9y8X7w6" * 4


@pytest.fixture
def corrida_con_specs(tmp_path: Path, precios):  # noqa: F811
    """Corrida registrada en .qagent/runs/<run_id>/ con specs reutilizados y regenerados."""
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run = almacen.crear_run(tipos_prueba=["funcion"])
    run_id = run["run_id"]

    tracker, resultado = correr(precios, decisiones=("retry", "accept"))
    rutas = escribir_corrida(
        tmp_path,
        resultado,
        tracker,
        precios,
        "deep",
        run_id=run_id,
        metas=METAS,
        rama="develop",
    )
    almacen.registrar_specs_run(
        run_id,
        [
            {
                "modulo": "modulo_simulado.py",
                "huella": "a" * 64,
                "run_origen": run_id,
                "estado": "reutilizado",
            },
            {
                "modulo": "descuentos.py",
                "huella": "b" * 64,
                "run_origen": run_id,
                "estado": "regenerado",
            },
        ],
    )
    almacen.finalizar_run(
        run_id, "fin", pasaron=1, fallaron=0, tipos_prueba=["funcion"]
    )
    return tmp_path, rutas


def test_criterio2_guarda_por_defecto_en_carpeta_de_la_corrida_con_nombres_oficiales(
    corrida_con_specs,
) -> None:
    raiz, rutas = corrida_con_specs
    run_id = rutas.run_id
    carpeta_esperada = raiz / ".qagent" / "runs" / run_id

    res_pdf = exportar_informe(raiz, run_id=run_id, formato="pdf")
    res_md = exportar_informe(raiz, run_id=run_id, formato="md")
    res_json = exportar_informe(raiz, run_id=run_id, formato="json")

    assert res_pdf["nombre"] == f"informe_{run_id}.pdf"
    assert res_md["nombre"] == f"informe_{run_id}.md"
    assert res_json["nombre"] == f"results_{run_id}.json"

    assert Path(res_pdf["ruta"]) == carpeta_esperada / f"informe_{run_id}.pdf"
    assert Path(res_md["ruta"]) == carpeta_esperada / f"informe_{run_id}.md"
    assert Path(res_json["ruta"]) == carpeta_esperada / f"results_{run_id}.json"

    assert Path(res_pdf["ruta"]).is_file()
    assert Path(res_md["ruta"]).is_file()
    assert Path(res_json["ruta"]).is_file()


def test_criterio2_permite_cambiar_la_carpeta_de_destino(
    corrida_con_specs, tmp_path: Path
) -> None:
    raiz, rutas = corrida_con_specs
    otra_carpeta = tmp_path / "evidencias_auditor"

    res = exportar_informe(
        raiz,
        run_id=rutas.run_id,
        formato="md",
        carpeta_destino=otra_carpeta,
    )

    assert Path(res["carpeta"]) == otra_carpeta
    assert Path(res["ruta"]) == otra_carpeta / f"informe_{rutas.run_id}.md"
    assert Path(res["ruta"]).is_file()


def test_criterio1_resumen_va_siempre_y_secciones_opcionales_se_controlan(
    tmp_path: Path,
    precios,  # noqa: F811
) -> None:
    tracker, resultado = correr(precios, decisiones=("bug_detectado",))
    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "deep", metas=METAS)

    # Solo resumen (todo lo opcional desactivado)
    minimo = exportar_informe(
        tmp_path,
        run_id=rutas.run_id,
        formato="md",
        opciones={
            "resumen": False,  # aunque pidan False, el resumen va siempre
            "detalle": False,
            "trazas": False,
            "codigo": False,
            "contratos": False,
        },
    )
    texto_minimo = Path(minimo["ruta"]).read_text(encoding="utf-8")
    assert "## 1. Resumen de las 5 métricas" in texto_minimo
    assert "## 2. Resultado por función" not in texto_minimo
    assert "## 3. Trazas del Reviewer" not in texto_minimo
    assert "## 4. Código de las pruebas generadas" not in texto_minimo
    assert "## 5. Contratos JSON del Planner" not in texto_minimo

    # Todo activado
    completo = exportar_informe(
        tmp_path,
        run_id=rutas.run_id,
        formato="md",
        opciones={
            "detalle": True,
            "trazas": True,
            "codigo": True,
            "contratos": True,
        },
    )
    texto_completo = Path(completo["ruta"]).read_text(encoding="utf-8")
    assert "## 1. Resumen de las 5 métricas" in texto_completo
    assert "## 2. Resultado por función" in texto_completo
    assert "## 3. Trazas del Reviewer de los incidentes" in texto_completo
    assert "assert 19 == 20" in texto_completo
    assert "## 4. Código de las pruebas generadas" in texto_completo
    assert "def test_caso_1():" in texto_completo
    assert "## 5. Contratos JSON del Planner" in texto_completo
    assert '"version": "2"' in texto_completo


def test_criterio3_y_4_incluye_5_metricas_modelos_costo_por_agente_specs_y_coincide_con_pantalla(
    corrida_con_specs,
) -> None:
    raiz, rutas = corrida_con_specs
    results = leer_results(raiz, rutas.run_id)
    detalle = leer_detalle(raiz, rutas.run_id)
    pantalla_ejec = vista_ejecucion(results)
    pantalla_rep = vista_reporte(results, detalle)

    exp_md = exportar_informe(raiz, run_id=rutas.run_id, formato="md")
    exp_pdf = exportar_informe(raiz, run_id=rutas.run_id, formato="pdf")
    exp_json = exportar_informe(raiz, run_id=rutas.run_id, formato="json")

    texto_md = Path(exp_md["ruta"]).read_text(encoding="utf-8")
    texto_pdf = extraer_texto_pdf(exp_pdf["ruta"])
    datos_json = json.loads(Path(exp_json["ruta"]).read_text(encoding="utf-8"))

    # Las 5 métricas están presentes con meta y estado (Cumple / No cumple)
    claves_metricas = [m["clave"] for m in datos_json["metricas"]]
    assert claves_metricas == [
        "pass_rate",
        "cobertura",
        "iteraciones",
        "costo",
        "mutation_score",
    ]
    for m in datos_json["metricas"]:
        assert m["meta"]
        assert m["estado"].startswith(("Cumple", "No cumple"))
        assert m["nombre"] in texto_md
        assert m["nombre"] in texto_pdf

    # Modelos usados y costo por agente en los 3 formatos
    for agente in ("planner", "generator", "reviewer"):
        modelo = results["modelos"][agente]["modelo"]
        assert modelo in texto_md
        assert modelo in texto_pdf
        assert datos_json["modelos"][agente]["modelo"] == modelo
        assert (
            datos_json["costo_por_agente"][agente]["costo_usd"]
            == pantalla_ejec["indicadores"]["costo"]["por_agente"][agente]["costo_usd"]
        )

    # Specs reutilizados
    assert "1 reutilizados (modulo_simulado.py)" in texto_md
    assert "1 regenerados (descuentos.py)" in texto_md
    assert "1 reutilizados (modulo_simulado.py)" in texto_pdf
    assert datos_json["specs"]["reutilizados"] == 1
    assert datos_json["specs"]["regenerados"] == 1

    # Criterio 4: las cifras coinciden exactamente con results.json y la pantalla
    assert datos_json["resumen"] == results["resumen"]
    assert (
        datos_json["metricas"][0]["valor"]
        == pantalla_rep["indicadores"]["pass_rate"]["valor"]
        == results["resumen"]["pass_rate"]
    )
    assert (
        datos_json["metricas"][1]["lineas"]
        == pantalla_rep["indicadores"]["cobertura"]["lineas"]
        == results["resumen"]["cobertura_lineas_promedio"]
    )
    assert (
        datos_json["metricas"][3]["costo_total_usd"]
        == pantalla_rep["indicadores"]["costo"]["usd"]
        == results["resumen"]["costo_total_usd"]
    )


def test_criterio5_y_6_evidencia_aceptacion_sin_claves_rn07_y_pdf_valido(
    corrida_con_specs,
) -> None:
    """Criterio 5 y 6: el informe abre, tiene las 5 métricas y 0 patrones de clave (RN-07)."""
    raiz, rutas = corrida_con_specs
    # Plantamos patrones de clave en detalle.json para comprobar que nunca salen al informe
    detalle = json.loads(rutas.detalle.read_text(encoding="utf-8"))
    detalle["funciones"][0]["traza"] = (
        f"Error con OPENAI_API_KEY={CLAVE_OPENAI_FALSA} y {CLAVE_ANTHROPIC_FALSA}"
    )
    detalle["funciones"][0]["codigo"] += f"\n# token={CLAVE_OPENAI_FALSA}\n"
    rutas.detalle.write_text(json.dumps(detalle), encoding="utf-8")

    claves = Claves({"XIAOMI_API_KEY": "secreto_xiaomi_super_largo_12345"})
    opciones_completas = {
        "detalle": True,
        "trazas": True,
        "codigo": True,
        "contratos": True,
    }

    carpeta_export = raiz / "exportados_auditoria"
    for fmt in ("pdf", "md", "json"):
        res = exportar_informe(
            raiz,
            run_id=rutas.run_id,
            formato=fmt,
            opciones=opciones_completas,
            carpeta_destino=carpeta_export,
            claves=claves,
        )
        ruta = Path(res["ruta"])
        assert ruta.is_file() and ruta.stat().st_size > 0
        assert verificar_archivo_sin_claves(ruta) == []

        contenido_txt = (
            extraer_texto_pdf(ruta)
            if fmt == "pdf"
            else ruta.read_text(encoding="utf-8")
        )
        assert CLAVE_OPENAI_FALSA not in contenido_txt
        assert CLAVE_ANTHROPIC_FALSA not in contenido_txt
        assert "secreto_xiaomi_super_largo_12345" not in contenido_txt

    # Escaneo completo de la carpeta con el buscador oficial de RN-07
    assert buscar_claves(carpeta_export) == []

    # El archivo PDF tiene cabecera y estructura PDF-1.4 válida y contiene las 5 métricas
    bytes_pdf = (carpeta_export / f"informe_{rutas.run_id}.pdf").read_bytes()
    assert bytes_pdf.startswith(b"%PDF-1.4")
    assert b"%%EOF" in bytes_pdf
    texto_pdf = extraer_texto_pdf(bytes_pdf)
    for nombre in (
        "Pass Rate",
        "Cobertura de líneas / ramas",
        "Iteraciones promedio",
        "Tokens y costo de la corrida",
        "Mutation Score",
    ):
        assert nombre in texto_pdf


def test_formato_invalido_lanza_excepcion(corrida_con_specs) -> None:
    raiz, rutas = corrida_con_specs
    with pytest.raises(FormatoInvalido):
        exportar_informe(raiz, run_id=rutas.run_id, formato="docx")

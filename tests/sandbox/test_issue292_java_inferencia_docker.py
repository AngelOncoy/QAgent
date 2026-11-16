"""Regresión Java inferida: flujo real, evidencia persistida e informes honestos."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.llm import RespuestaLLM
from qagent.llm.fake import MARCA_CONTRATO
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.orchestrator.regresion import ejecutar_regresion
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.storage.exportar_informe import (
    construir_html_informe,
    construir_markdown_informe,
    construir_pdf_informe,
    datos_informe,
    extraer_texto_pdf,
)
from qagent.storage.vista_reporte import vista_reporte
from tests.lenguajes.test_issue292_java_inferencia import escribir

pytestmark = pytest.mark.docker
MODULO = "src/main/java/demo/Calc.java"


class ProveedorGrabado:
    """Declara una inferencia correcta o equivocada; no obtiene valores ejecutando Java."""

    def __init__(self, esperado):
        self.esperado = esperado

    def generar(self, prompt, rol="planner"):
        if rol == "planner":
            casos = (
                [
                    {
                        "objetivo": "Calc.producto",
                        "casos": [
                            {
                                "id": "producto_normal",
                                "entrada": {"a": 2, "b": 3},
                                "valor_esperado": self.esperado,
                                "origen": "inferido",
                                "evidencia": ["cuerpo"],
                                "categoria": "normal",
                            }
                        ],
                    }
                ]
                if prompt.startswith("Infiere")
                else []
            )
            contenido = json.dumps(casos)
        elif rol == "generator":
            contrato = json.loads(prompt.rsplit(MARCA_CONTRATO, 1)[1])
            esperado = contrato["casos"][0]["valor_esperado"]
            contenido = f"package demo; import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.assertEquals; class CalcTest {{ @Test void test_producto_normal() {{ assertEquals({esperado}, Calc.producto(2,3)); }} }}"
        else:
            contenido = "{}"
        return RespuestaLLM(contenido, 0, 0, 0, "java-inferencia-grabada")


@pytest.mark.parametrize("perfil,esperado", [("humo", 6), ("std", 99), ("deep", 6)])
def test_corrida_java_inferida_conserva_procedencia_y_no_confirma_bugs(
    cliente_docker, tmp_path, monkeypatch, perfil, esperado
):
    """Un oráculo mal inferido falla en JUnit, pero el informe lo deja a revisión."""
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta la imagen base Java.")
    proyecto = tmp_path / "proyecto"
    escribir(
        proyecto,
        MODULO,
        "package demo; public class Calc { public static int producto(int a, int b) { return a*b; } }",
    )
    escribir(
        proyecto,
        "pom.xml",
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><groupId>demo</groupId><artifactId>inferencia</artifactId><version>1</version><properties><maven.compiler.release>21</maven.compiler.release></properties></project>',
    )
    if perfil == "deep":
        receta = (
            Path(__file__).resolve().parents[2]
            / "src/qagent/sandbox/java/calentamiento/pom.xml"
        )
        pom = ET.fromstring(receta.read_text(encoding="utf-8"))
        plugins = pom.find("{*}build/{*}plugins")
        for plugin in list(plugins):
            if plugin.findtext("{*}artifactId") == "pitest-maven":
                plugins.remove(plugin)
        ET.ElementTree(pom).write(
            proyecto / "pom.xml", encoding="utf-8", xml_declaration=True
        )
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    almacen = AlmacenProyecto(proyecto)
    almacen.inicializar()
    cliente = ProveedorGrabado(esperado)
    monkeypatch.setattr(
        "qagent.orchestrator.corrida.crear_cliente", lambda *a, **kw: cliente
    )
    config = cargar_configuracion(simulado=True).config
    seleccion = [
        {
            "ruta": MODULO,
            "funciones": ["Calc.producto"],
            "endpoints": [],
            "criticas": ["Calc.producto"] if perfil == "deep" else [],
        }
    ]
    resultado = ejecutar_corrida(
        proyecto,
        perfil,
        config,
        None,
        simulado=True,
        seleccion=seleccion,
        preparar_imagen=lambda _: IMAGEN_JAVA,
    )
    assert resultado.estado == "fin", resultado.motivo
    assert resultado.total_procesados == 1
    assert resultado.tokens == 0
    carpeta = Path(resultado.carpeta)
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    detalle = json.loads((carpeta / "detalle.json").read_text(encoding="utf-8"))
    vista = vista_reporte(results, detalle)
    [funcion] = vista["funciones"]
    assert funcion["respaldo"] == "inferido"
    assert funcion["evidencia_inferida"] == ["cuerpo"]
    assert vista["con_contrato"] == 0 and vista["de_regresion"] == 1
    assert resultado.aceptadas == int(esperado == 6)
    assert funcion["intentos"][-1]["ejecucion"]["totales"]["total"] == 1
    if esperado != 6:
        assert "hallazgo a revisar" in vista["aviso_hallazgo_inferido"]
    if perfil == "deep":
        assert funcion["mutacion"]["estado"] == "ok", funcion.get("mutacion")
        assert funcion["mutacion"]["puntuacion"] is not None
    datos = datos_informe(proyecto, resultado.run_id)
    md = construir_markdown_informe(datos)
    html = construir_html_informe(datos)
    pdf = construir_pdf_informe(datos)
    for texto in (md, html, extraer_texto_pdf(pdf)):
        assert "sin contrato documentado" in texto.lower()
        assert "defecto confirmado" not in texto.lower()
        assert "cuerpo" in texto
    assert (
        vista["funciones"][0]["estado"] != "hallazgo_inferido"
    )  # exportar no cambia la evidencia canónica
    if esperado == 6:

        def prohibido(*args, **kwargs):
            pytest.fail("La regresión no debe crear clientes IA.")

        monkeypatch.setattr("qagent.orchestrator.corrida.crear_cliente", prohibido)
        run = almacen.crear_run()
        repetida = ejecutar_regresion(
            proyecto,
            "reg_deep" if perfil == "deep" else "reg",
            config,
            run_id=run["run_id"],
            seleccion=seleccion,
            preparar_imagen=lambda _: IMAGEN_JAVA,
        )
        assert repetida.aceptadas == repetida.total_procesados == 1, repetida.motivo
        assert repetida.tokens == 0
        datos = json.loads(
            (Path(repetida.carpeta) / "detalle.json").read_text(encoding="utf-8")
        )
        assert datos["funciones"][0]["contrato"]["casos"][0]["origen"] == "inferido"
        if perfil == "deep":
            repetidos = json.loads(
                (Path(repetida.carpeta) / "results.json").read_text(encoding="utf-8")
            )
            assert repetidos["objetivos"][0]["mutacion"]["reutilizada"] is True
    assert all(
        (proyecto / ruta).read_bytes() == contenido
        for ruta, contenido in originales.items()
    )
    print(
        f"Java inferido: {perfil}; esperado={esperado}; 1 JUnit real; evidencia conservada; originales intactos; 0 tokens"
    )

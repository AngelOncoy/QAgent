"""Evidencia Java trazable sin compilar, ejecutar ni consultar proveedores de IA."""

import json
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_inferencia import ProveedorInferenciaJava


def escribir(raiz: Path, ruta: str, codigo: str) -> None:
    archivo = raiz / ruta
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(codigo, encoding="utf-8")


@pytest.fixture
def proyecto(tmp_path):
    escribir(
        tmp_path,
        "src/main/java/demo/Calc.java",
        "package demo; public class Calc { public static int sumar(int a, int b) { return a+b; } public int doble(int a) { return a*2; } }",
    )
    escribir(
        tmp_path,
        "src/main/java/demo/Uso.java",
        "package demo; public class Uso { public static int total() { return Calc.sumar(2, 3); } }",
    )
    escribir(
        tmp_path,
        "src/main/java/demo/Servicio.java",
        "package demo; public class Servicio { public static int calcular() { return Calc.sumar(4, 5); } }",
    )
    escribir(
        tmp_path,
        "src/test/java/demo/CalcTest.java",
        "package demo; import org.junit.jupiter.api.Test; class CalcTest { @Test void prueba() { org.junit.jupiter.api.Assertions.assertEquals(5, Calc.sumar(2,3)); } }",
    )
    return tmp_path, JavaAdapter().analizar(tmp_path)


def proveedor(proyecto, tope=6000):
    raiz, analisis = proyecto
    assert not analisis["errores"]
    return ProveedorInferenciaJava(raiz, analisis["modulos"], tope)


def test_contexto_cita_cuerpo_llamadores_y_tests_sin_ejecutarlos(proyecto):
    p = proveedor(proyecto)
    contexto = p.contexto("src/main/java/demo/Calc.java", "Calc.sumar")
    assert "return a+b" in contexto.codigo
    assert len(contexto.llamadores) == 2
    assert (
        "test_existente:src/test/java/demo/CalcTest.java::CalcTest.prueba"
        in contexto.referencias
    )
    assert len(json.dumps(contexto.a_dict(), ensure_ascii=False)) <= 6000
    assert p.contexto("src/main/java/demo/Calc.java", "Calc.noExiste") is None


def test_dependencia_resuelta_con_identidad_completa(proyecto):
    contexto = proveedor(proyecto).contexto(
        "src/main/java/demo/Servicio.java", "Servicio.calcular"
    )
    assert (
        "dependencia:src/main/java/demo/Calc.java::Calc.sumar" in contexto.referencias
    )
    assert "public static int sumar" in contexto.dependencias[0]


@pytest.mark.parametrize(
    "llamada,objetivo",
    [
        ("Calc.sumar(2,2)", "Calc.sumar"),
        ("new Calc().doble(2)", "Calc.doble"),
        ("c.doble(2)", "Calc.doble"),
    ],
)
def test_test_existente_se_asocia_a_clase_y_metodo(proyecto, llamada, objetivo):
    raiz, _ = proyecto
    escribir(
        raiz,
        "src/test/java/otro/ImportTest.java",
        "package otro; import demo.Calc; import org.junit.jupiter.api.Test; class ImportTest { @Test void prueba() { Calc c = new Calc(); org.junit.jupiter.api.Assertions.assertEquals(4, "
        + llamada
        + "); } }",
    )
    contexto = proveedor(proyecto).contexto("src/main/java/demo/Calc.java", objetivo)
    assert any("ImportTest.prueba" in r for r, _ in contexto.tests)


def test_no_atribuye_mismo_nombre_de_otra_clase(proyecto):
    raiz, _ = proyecto
    escribir(
        raiz,
        "src/test/java/demo/OtroTest.java",
        "package demo; import ajeno.Calc; import org.junit.jupiter.api.Test; class OtroTest { @Test void prueba() { Calc.sumar(100,200); } }",
    )
    contexto = proveedor(proyecto).contexto(
        "src/main/java/demo/Calc.java", "Calc.sumar"
    )
    assert all("OtroTest" not in r for r, _ in contexto.tests)


def test_no_utiliza_comentarios_como_llamadas(proyecto):
    raiz, _ = proyecto
    escribir(
        raiz,
        "src/test/java/demo/ComentarioTest.java",
        'package demo; import org.junit.jupiter.api.Test; class ComentarioTest { @Test void prueba() { String s = "Calc.sumar(2,3)"; /* Calc.sumar(2,3); */ } }',
    )
    contexto = proveedor(proyecto).contexto(
        "src/main/java/demo/Calc.java", "Calc.sumar"
    )
    assert all("ComentarioTest" not in r for r, _ in contexto.tests)


def test_rechaza_objetivo_documentado_y_cuerpo_sin_implementacion(tmp_path):
    escribir(
        tmp_path,
        "Calc.java",
        "public class Calc { /** Devuelve tres. */ public static int documentado() { return 3; } public native int nativo(); }",
    )
    p = proveedor((tmp_path, JavaAdapter().analizar(tmp_path)))
    assert p.contexto("Calc.java", "Calc.documentado") is None
    assert p.contexto("Calc.java", "Calc.nativo") is None


def test_tope_de_contexto_y_fuente_se_respetan(proyecto, monkeypatch):
    assert (
        proveedor(proyecto, 10).contexto("src/main/java/demo/Calc.java", "Calc.sumar")
        is None
    )
    monkeypatch.setattr("qagent.lenguajes.java_inferencia.MAX_BYTES_ARCHIVO", 10)
    assert (
        proveedor(proyecto).contexto("src/main/java/demo/Calc.java", "Calc.sumar")
        is None
    )


def test_no_lee_archivos_fuera_de_la_raiz(proyecto, tmp_path):
    p = proveedor(proyecto)
    assert p._leer("../fuera.java") is None
    assert p._leer(str(tmp_path.parent / "fuera.java")) is None


@pytest.mark.parametrize(
    "cuerpo",
    [
        "System.currentTimeMillis()",
        "java.lang.System.nanoTime()",
        "Math.random()",
        "new java.util.Random().nextDouble()",
    ],
)
def test_no_propone_inferencia_para_reloj_azar_y_entorno(tmp_path, cuerpo):
    escribir(
        tmp_path,
        "Calc.java",
        f"public class Calc {{ public static double valor() {{ return {cuerpo}; }} }}",
    )
    p = proveedor((tmp_path, JavaAdapter().analizar(tmp_path)))
    assert p.contexto("Calc.java", "Calc.valor") is None


@pytest.mark.parametrize(
    "importacion", ["java.lang.System.currentTimeMillis", "java.lang.System.*"]
)
def test_rechaza_reloj_con_import_estatico(tmp_path, importacion):
    escribir(
        tmp_path,
        "Calc.java",
        f"import static {importacion}; public class Calc {{ public static long valor() {{ return currentTimeMillis(); }} }}",
    )
    p = proveedor((tmp_path, JavaAdapter().analizar(tmp_path)))
    assert p.contexto("Calc.java", "Calc.valor") is None

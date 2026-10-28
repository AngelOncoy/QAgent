"""Comprueba el parser Java real sin compilar ni ejecutar las fuentes (EN-19)."""

import json
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.treesitter import (
    cargar_gramatica,
    extraer_errores_sintaxis,
    obtener_parser,
)


def test_gramatica_java_en_cache() -> None:
    """Comprueba que dos solicitudes reutilizan la misma gramática Java.

    Resultado esperado: ambas llamadas devuelven el mismo objeto en memoria.
    La prueba no devuelve datos; falla si la caché no reutiliza la gramática.
    """
    assert cargar_gramatica("java") is cargar_gramatica("java")


def test_parser_java_reconoce_clase_y_metodo() -> None:
    """Analiza una clase Suma con un método sumar y dos parámetros enteros.

    Resultado esperado: árbol sin errores, clase Suma, método sumar, tipo de
    retorno int y dos parámetros. Solo analiza el texto; no ejecuta la suma.
    La prueba no devuelve datos; falla si falta alguna estructura esperada.
    """
    codigo = b"class Suma { int sumar(int a, int b) { return a + b; } }"
    raiz = obtener_parser("java").parse(codigo).root_node
    assert not raiz.has_error
    clase = raiz.named_children[0]
    assert clase.type == "class_declaration"
    assert clase.child_by_field_name("name").text == b"Suma"
    metodo = clase.child_by_field_name("body").named_children[0]
    assert metodo.type == "method_declaration"
    assert metodo.child_by_field_name("name").text == b"sumar"
    assert metodo.child_by_field_name("type").text == b"int"
    assert len(metodo.child_by_field_name("parameters").named_children) == 2


def test_parser_java_reporta_error_sintactico() -> None:
    """Analiza una asignación Java sin expresión a la derecha del signo igual.

    Resultado esperado: el árbol marca un error y el diagnóstico menciona la
    línea 2, donde se encuentra la asignación incompleta.
    La prueba no devuelve datos; falla si se acepta el código inválido o si
    no se identifica la línea esperada.
    """
    codigo = b"class Rota {\n int valor = ;\n}"
    raiz = obtener_parser("java").parse(codigo).root_node
    assert raiz.has_error
    assert any("línea 2" in error for error in extraer_errores_sintaxis(raiz))


def test_parser_java_reporta_elemento_faltante() -> None:
    """Analiza una clase Java a la que le falta la llave de cierre.

    Resultado esperado: el árbol marca un error y se obtiene al menos un
    diagnóstico por la estructura incompleta.
    La prueba no devuelve datos; falla si el parser no informa el problema.
    """
    raiz = obtener_parser("java").parse(b"class Incompleta {").root_node
    assert raiz.has_error
    assert extraer_errores_sintaxis(raiz)


def test_analiza_banco_ta01() -> None:
    """Analiza el banco real: espera dos clases, seis métodos públicos y Javadoc.

    Excluye las pruebas Maven y los constructores privados; no ejecuta Java.
    La estructura debe poder serializarse como JSON sin perder información.
    """
    banco = Path(__file__).resolve().parents[2] / "bench_java"
    adaptador = JavaAdapter()
    estructura = adaptador.analizar(banco)
    assert estructura["errores"] == []
    assert estructura["resumen"] == {
        "total_modulos": 2,
        "total_clases": 2,
        "total_funciones_publicas": 6,
        "total_endpoints": 0,
        "total_errores": 0,
    }
    funciones = {f["nombre"]: f for m in estructura["modulos"] for f in m["funciones"]}
    assert set(funciones) == {
        "BancoCorrecto.sumarPrecios",
        "BancoCorrecto.aplicarDescuento",
        "BancoCorrecto.esMayorDeEdad",
        "BancoDefectuoso.calcularPromedio",
        "BancoDefectuoso.calcularEnvio",
        "BancoDefectuoso.calcularTotalConImpuesto",
    }
    suma = funciones["BancoCorrecto.sumarPrecios"]
    assert suma["parametros"] == [
        {"nombre": "precios", "tipo": "List<Double>", "por_defecto": None}
    ]
    assert suma["retorno"] == "double"
    assert "Una lista vacía devuelve cero" in suma["docstring"]
    assert all(f["docstring"].startswith("/**") for f in funciones.values())
    assert all(len(m["huella"]) == 64 for m in estructura["modulos"])
    assert {o["objetivo"] for o in adaptador.objetivos(estructura)} == set(funciones)
    assert json.loads(json.dumps(estructura, ensure_ascii=False)) == estructura


def test_javadoc_anotaciones_y_tipos(tmp_path: Path) -> None:
    """Conserva Javadoc literal con anotaciones, genéricos, arrays y varargs.

    Espera nombres y tipos de los parámetros y el retorno tal como se declaran.
    """
    (tmp_path / "Tipos.java").write_text(
        "/** Clase de ejemplo. */ public class Tipos {\n"
        "/** Devuelve etiquetas. */ @Deprecated\n"
        "public java.util.List<String> etiquetas(final int valores[], String... nombres) { return null; }\n"
        "}",
        encoding="utf-8",
    )
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    [funcion] = modulo["funciones"]
    assert modulo["clases"][0]["docstring"] == "/** Clase de ejemplo. */"
    assert funcion["docstring"] == "/** Devuelve etiquetas. */"
    assert funcion["retorno"] == "java.util.List<String>"
    assert [(p["nombre"], p["tipo"]) for p in funcion["parametros"]] == [
        ("valores", "int[]"),
        ("nombres", "String..."),
    ]


def test_no_inventa_javadoc_y_excluye_privados(tmp_path: Path) -> None:
    """Un comentario común no es un oráculo; métodos privados no son objetivos."""
    (tmp_path / "SinDoc.java").write_text(
        "class SinDoc { /** No pertenece a b. */ private void a() {}\n"
        "/* comentario común */ public void b() {} }",
        encoding="utf-8",
    )
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    assert [f["nombre"] for f in modulo["funciones"]] == ["SinDoc.b"]
    assert modulo["funciones"][0]["docstring"] is None


def test_clases_anidadas(tmp_path: Path) -> None:
    """Los métodos de clases anidadas conservan su clase para evitar colisiones."""
    (tmp_path / "Exterior.java").write_text(
        "class Exterior { public void f() {} class Interior { public void f() {} } }",
        encoding="utf-8",
    )
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    assert {f["nombre"] for f in modulo["funciones"]} == {
        "Exterior.f",
        "Exterior.Interior.f",
    }


def test_errores_no_detienen_otros_archivos(tmp_path: Path) -> None:
    """Una fuente inválida se reporta y no impide extraer métodos de otra válida."""
    (tmp_path / "Mal.java").write_text("class Mal { int a = ; }", encoding="utf-8")
    (tmp_path / "Bien.java").write_text(
        "class Bien { public int f() { return 1; } }", encoding="utf-8"
    )
    estructura = JavaAdapter().analizar(tmp_path)
    assert [m["ruta"] for m in estructura["modulos"]] == ["Bien.java"]
    assert estructura["errores"][0]["ruta"] == "Mal.java"
    assert "error de sintaxis" in estructura["errores"][0]["mensaje"]


def test_excluye_pruebas_y_compilados(tmp_path: Path) -> None:
    """No convierte pruebas Maven ni fuentes generadas en objetivos de producción."""
    for carpeta in ("src/test/java", "target/generated-sources", ".oculta"):
        destino = tmp_path / carpeta
        destino.mkdir(parents=True)
        (destino / "Ignorada.java").write_text("class Ignorada {}", encoding="utf-8")
    assert JavaAdapter().analizar(tmp_path)["modulos"] == []


def test_reporta_sobrecargas_sin_objetivos_ambiguos(tmp_path: Path) -> None:
    """Dos métodos con el mismo objetivo generan un error de alcance explícito."""
    (tmp_path / "Sobrecarga.java").write_text(
        "class A { public void f() {} public void f(int x) {} }",
        encoding="utf-8",
    )
    estructura = JavaAdapter().analizar(tmp_path)
    assert estructura["modulos"] == []
    assert "Sobrecarga no admitida" in estructura["errores"][0]["mensaje"]


def test_raiz_inexistente(tmp_path: Path) -> None:
    """Una carpeta inexistente produce NotADirectoryError, no un éxito vacío."""
    with pytest.raises(NotADirectoryError):
        JavaAdapter().analizar(tmp_path / "inexistente")


def test_fuente_no_utf8(tmp_path: Path) -> None:
    """Una codificación inválida queda identificada como error de lectura."""
    (tmp_path / "Bytes.java").write_bytes(b"class Bytes { /* \xff */ }")
    estructura = JavaAdapter().analizar(tmp_path)
    assert estructura["modulos"] == []
    assert estructura["errores"][0]["tipo"] == "UnicodeDecodeError"


def test_validar_sintaxis_desde_adaptador() -> None:
    """El punto de extensión Java acepta sintaxis válida y diagnostica la inválida."""
    adaptador = JavaAdapter()
    assert adaptador.validar_sintaxis("class A {}") == []
    assert adaptador.validar_sintaxis("class A {")

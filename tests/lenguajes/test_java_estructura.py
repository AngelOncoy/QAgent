"""Estructura Java ampliada de #181: Javadoc, constructores y decisiones sin JVM."""

import json
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_estructura import desglosar_javadoc


def _analizar(tmp_path: Path, codigo: str) -> dict:
    """Analiza texto de una fixture Java y exige que su sintaxis sea válida."""
    (tmp_path / "Ejemplo.java").write_text(codigo, encoding="utf-8")
    estructura = JavaAdapter().analizar(tmp_path)
    assert estructura["errores"] == []
    return estructura


def test_javadoc_con_etiquetas_y_continuaciones() -> None:
    """Separa parámetros, retorno y excepciones conservando las descripciones."""
    texto = """/**
     * Calcula un importe.
     * Segunda línea de descripción.
     * @param <T> tipo de entrada
     * @param valor importe no negativo
     *   expresado en soles
     * @return importe con descuento
     * @throws IllegalArgumentException si el importe es negativo
     * @exception NullPointerException si falta la entrada
     * @since 1.0
     */"""
    doc = desglosar_javadoc(texto)
    assert doc["descripcion"] == "Calcula un importe.\nSegunda línea de descripción."
    assert doc["parametros"] == {
        "<T>": "tipo de entrada",
        "valor": "importe no negativo\nexpresado en soles",
    }
    assert doc["retorno"] == "importe con descuento"
    assert doc["excepciones"] == [
        {
            "tipo": "IllegalArgumentException",
            "descripcion": "si el importe es negativo",
        },
        {"tipo": "NullPointerException", "descripcion": "si falta la entrada"},
    ]
    assert doc["otras_etiquetas"] == {"since": ["1.0"]}
    assert desglosar_javadoc(None) is None
    assert desglosar_javadoc("/** */")["retorno"] is None


def test_constructores_se_describen_sin_convertirse_en_metodos(tmp_path: Path) -> None:
    """Conserva firmas sobrecargadas, visibilidad, parámetros y documentación."""
    estructura = _analizar(
        tmp_path,
        """public class Ejemplo {
        /** Construye con saldo cero. */ public Ejemplo() {}
        /** @param saldo importe inicial */
        private Ejemplo(int saldo) { if (saldo < 0) { throw new IllegalArgumentException(); } }
        public int saldo() { return 0; }
    }""",
    )
    clase = estructura["modulos"][0]["clases"][0]
    constructores = clase["constructores"]
    assert [c["visibilidad"] for c in constructores] == ["public", "private"]
    assert [c["firma"] for c in constructores] == [
        "public Ejemplo()",
        "private Ejemplo(int saldo)",
    ]
    assert constructores[1]["parametros"] == [
        {"nombre": "saldo", "tipo": "int", "por_defecto": None}
    ]
    assert constructores[1]["javadoc"]["parametros"] == {"saldo": "importe inicial"}
    assert constructores[1]["ramas"] == 1
    assert [o["objetivo"] for o in JavaAdapter().objetivos(estructura)] == [
        "Ejemplo.saldo"
    ]
    assert json.loads(json.dumps(estructura)) == estructura


def test_constructor_compacto_record_y_constructor_implicito(tmp_path: Path) -> None:
    """El constructor compacto usa los parámetros del record; no inventa implícitos."""
    estructura = _analizar(
        tmp_path,
        """record Ejemplo(int saldo) {
        public Ejemplo { if (saldo < 0) throw new IllegalArgumentException(); }
    }
    class SinConstructor {}""",
    )
    clases = estructura["modulos"][0]["clases"]
    assert clases[0]["constructores"][0]["parametros"] == [
        {"nombre": "saldo", "tipo": "int", "por_defecto": None}
    ]
    assert clases[0]["constructores"][0]["ramas"] == 1
    assert clases[1]["constructores"] == []


@pytest.mark.parametrize(
    ("cuerpo", "esperadas"),
    [
        ("return 1;", 0),
        ("if (x > 0) { return 1; } else if (x < 0) { return -1; } return 0;", 2),
        ("return x > 0 ? 1 : 0;", 1),
        (
            "for (int i=0;i<x;i++) {} while(x>0) {x--;} do {x++;} while(x<0); return x;",
            3,
        ),
        ("for (int v : new int[]{1,2}) {} return x;", 1),
        ("try { return x; } catch (RuntimeException e) { return 0; }", 1),
        ("switch(x) {case 1: return 1; case 2: return 2; default: return 0;}", 2),
        ("return switch(x) {case 1, 2 -> 1; default -> 0;};", 1),
        ("if (x>0 && x<10 || x==20) {return 1;} return 0;", 3),
    ],
)
def test_decisiones_y_criticidad(tmp_path: Path, cuerpo: str, esperadas: int) -> None:
    """Cuenta decisiones del AST y conserva el mismo criterio de critical en objetivos."""
    estructura = _analizar(
        tmp_path, "public class Ejemplo { public static int f(int x) {" + cuerpo + "} }"
    )
    funcion = estructura["modulos"][0]["funciones"][0]
    assert funcion["ramas"] == esperadas
    assert funcion["critical"] is (esperadas > 0)
    assert funcion["es_static"] is True
    assert JavaAdapter().objetivos(estructura) == [
        {
            "modulo": "Ejemplo.java",
            "tipo": "funcion",
            "objetivo": "Ejemplo.f",
            "critical": esperadas > 0,
        }
    ]


def test_no_suma_decisiones_de_otros_ambitos(tmp_path: Path) -> None:
    """Las ramas de lambdas, clases locales y objetos anónimos no son de su exterior."""
    estructura = _analizar(
        tmp_path,
        """class Ejemplo {
        public int f(int x) {
            Runnable r = () -> { if (x > 0) {} };
            class Local { int g() { if (x > 0) return 1; return 0; } }
            Object o = new Object() { int h() { if (x > 0) return 1; return 0; } };
            return 0;
        }
    }""",
    )
    [funcion] = estructura["modulos"][0]["funciones"]
    assert funcion["ramas"] == 0
    assert funcion["critical"] is False


def test_banco_ta01_conserva_oraculos_y_marca_decisiones() -> None:
    """El banco real mantiene seis métodos y conserva etiquetas sin ejecutar sus bugs."""
    banco = Path(__file__).resolve().parents[2] / "bench_java"
    estructura = JavaAdapter().analizar(banco)
    assert estructura["errores"] == []
    funciones = {f["nombre"]: f for m in estructura["modulos"] for f in m["funciones"]}
    assert len(funciones) == 6
    suma = funciones["BancoCorrecto.sumarPrecios"]
    assert suma["ramas"] == 1
    assert suma["critical"] is True
    assert "[10, 20] devuelve 30" in suma["javadoc"]["retorno"]
    assert "precios" in suma["javadoc"]["parametros"]
    assert all(
        c["constructores"][0]["visibilidad"] == "private"
        for m in estructura["modulos"]
        for c in m["clases"]
    )


def test_ignora_build_target_y_tests_existentes(tmp_path: Path) -> None:
    """Las fuentes generadas y pruebas del proyecto quedan fuera del análisis."""
    for ruta in (
        "target/generated/Uno.java",
        "build/generated/Dos.java",
        "src/test/java/Tres.java",
    ):
        archivo = tmp_path / ruta
        archivo.parent.mkdir(parents=True)
        archivo.write_text(
            "class Ignorada { public int f() { return 1; } }", encoding="utf-8"
        )
    assert JavaAdapter().analizar(tmp_path)["modulos"] == []

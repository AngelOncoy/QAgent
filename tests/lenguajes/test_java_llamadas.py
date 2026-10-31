"""Mapa de llamadas Java de #181: AST real, sin JDK, Docker ni servicios de IA."""

import json
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter


def _analizar(raiz: Path, fuentes: dict[str, str]) -> dict[str, dict]:
    """Escribe fixtures Java y devuelve métodos por ruta::nombre, sin ejecutarlos."""
    for relativa, codigo in fuentes.items():
        archivo = raiz / relativa
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(codigo, encoding="utf-8")
    estructura = JavaAdapter().analizar(raiz)
    assert estructura["errores"] == []
    assert json.loads(json.dumps(estructura)) == estructura
    return {
        f"{m['ruta']}::{f['nombre']}": f
        for m in estructura["modulos"]
        for f in m["funciones"]
    }


def test_propias_this_recursion_privados_y_duplicados(tmp_path: Path) -> None:
    """Solo enlaza métodos públicos propios; deduplica y omite la recursión directa."""
    funciones = _analizar(
        tmp_path,
        {
            "Banco.java": """class Banco {
        public int total() { subtotal(); this.subtotal(); privado(); return total(); }
        public int subtotal() { return 10; }
        private int privado() { return 0; }
    }"""
        },
    )
    assert funciones["Banco.java::Banco.total"]["llama_a"] == [
        "Banco.java::Banco.subtotal"
    ]
    assert funciones["Banco.java::Banco.subtotal"]["llama_a"] == []


@pytest.mark.parametrize("llamada", ["Util.sumar(1)", "p.Util.sumar(1)"])
def test_clase_del_mismo_paquete_y_calificada(tmp_path: Path, llamada: str) -> None:
    """Reconoce destinos static del proyecto desde otro archivo del mismo paquete."""
    funciones = _analizar(
        tmp_path,
        {
            "p/Util.java": "package p; public class Util { public static int sumar(int x) {return x;} }",
            "p/Cliente.java": "package p; class Cliente { public int total() {return "
            + llamada
            + ";} }",
        },
    )
    assert funciones["p/Cliente.java::Cliente.total"]["llama_a"] == [
        "p/Util.java::Util.sumar"
    ]


@pytest.mark.parametrize(
    ("cabecera", "llamada"),
    [
        ("import p.Util;", "Util.sumar(1)"),
        ("import static p.Util.sumar;", "sumar(1)"),
    ],
)
def test_imports_explicitos_y_estaticos(
    tmp_path: Path, cabecera: str, llamada: str
) -> None:
    """Resuelve los imports declarados en el archivo sin buscar clases por intuición."""
    funciones = _analizar(
        tmp_path,
        {
            "p/Util.java": "package p; public class Util { public static int sumar(int x) {return x;} }",
            "q/Cliente.java": "package q; "
            + cabecera
            + " class Cliente { public int f() { return "
            + llamada
            + ";} }",
        },
    )
    assert funciones["q/Cliente.java::Cliente.f"]["llama_a"] == [
        "p/Util.java::Util.sumar"
    ]


@pytest.mark.parametrize(
    ("declaracion", "cuerpo"),
    [
        ("", "Servicio s = new Servicio(); return s.valor();"),
        ("private Servicio servicio;", "return this.servicio.valor();"),
        ("private Servicio servicio;", "return servicio.valor();"),
    ],
)
def test_receptores_con_tipo_declarado(
    tmp_path: Path, declaracion: str, cuerpo: str
) -> None:
    """Enlaza una variable local o un campo por su tipo escrito en la fuente."""
    funciones = _analizar(
        tmp_path,
        {
            "p/Servicio.java": "package p; public class Servicio { public int valor() {return 1;} }",
            "p/Cliente.java": "package p; class Cliente {"
            + declaracion
            + "public int f() {"
            + cuerpo
            + "} }",
        },
    )
    assert funciones["p/Cliente.java::Cliente.f"]["llama_a"] == [
        "p/Servicio.java::Servicio.valor"
    ]


def test_parametro_importado_y_clase_homonima(tmp_path: Path) -> None:
    """El import del parámetro distingue dos clases de paquetes diferentes."""
    funciones = _analizar(
        tmp_path,
        {
            "a/Servicio.java": "package a; public class Servicio { public int valor() {return 1;} }",
            "b/Servicio.java": "package b; public class Servicio { public int valor() {return 2;} }",
            "q/Cliente.java": "package q; import b.Servicio; class Cliente { public int f(Servicio s) {return s.valor();} }",
        },
    )
    assert funciones["q/Cliente.java::Cliente.f"]["llama_a"] == [
        "b/Servicio.java::Servicio.valor"
    ]


@pytest.mark.parametrize(
    ("firma", "cuerpo"),
    [
        ("f()", "var s = new Servicio(); return s.valor();"),
        ("f(Object Servicio)", "return Servicio.valor();"),
        ("f(Servicio[] s)", "return s.hashCode();"),
        ("f(Servicio s[])", "return s.hashCode();"),
        ("f(Servicio... s)", "return s.hashCode();"),
        ("f()", "return crear().valor();"),
    ],
)
def test_tipos_desconocidos_arrays_y_sombras_no_inventan_enlaces(
    tmp_path: Path, firma: str, cuerpo: str
) -> None:
    """Una variable oculta el tipo; arrays y expresiones sin tipo resuelto quedan fuera."""
    funciones = _analizar(
        tmp_path,
        {
            "Servicio.java": "class Servicio { public int valor() {return 1;} public int hashCode() {return 1;} }",
            "Cliente.java": "class Cliente { public int "
            + firma
            + " {"
            + cuerpo
            + "} }",
        },
    )
    assert funciones["Cliente.java::Cliente.f"]["llama_a"] == []


def test_api_externa_importada_no_se_confunde_con_clase_local(tmp_path: Path) -> None:
    """Un import externo impide enlazar por error una clase homónima del proyecto."""
    funciones = _analizar(
        tmp_path,
        {
            "p/Servicio.java": "package p; class Servicio { public static int valor() {return 1;} }",
            "p/Cliente.java": "package p; import externa.Servicio; class Cliente { public int f() {return Servicio.valor();} }",
        },
    )
    assert funciones["p/Cliente.java::Cliente.f"]["llama_a"] == []


def test_no_elige_una_sobrecarga_privada_por_nombre(tmp_path: Path) -> None:
    """Un método público con otro privado homónimo no se resuelve sin comprobar tipos."""
    funciones = _analizar(
        tmp_path,
        {
            "Banco.java": """class Banco {
        public int f() { return sumar(1); }
        public int sumar(int x) {return x;}
        private int sumar(String x) {return 0;}
    }"""
        },
    )
    assert funciones["Banco.java::Banco.f"]["llama_a"] == []


def test_llamadas_fuera_de_aridad_y_varargs(tmp_path: Path) -> None:
    """Descarta argumentos incompatibles en cantidad y admite la aridad variable."""
    funciones = _analizar(
        tmp_path,
        {
            "Banco.java": """class Banco {
        public int f() { uno(); muchos(); muchos(1,2); return 0; }
        public int uno(int x) {return x;}
        public int muchos(int... x) {return x.length;}
    }"""
        },
    )
    assert funciones["Banco.java::Banco.f"]["llama_a"] == ["Banco.java::Banco.muchos"]


def test_clases_locales_genericos_y_ambitos_internos(tmp_path: Path) -> None:
    """Las clases locales y parámetros genéricos ocultan tipos del proyecto."""
    funciones = _analizar(
        tmp_path,
        {
            "Servicio.java": "class Servicio { public static int valor() {return 1;} }",
            "Cliente.java": """class Cliente<Servicio> {
            public int f(Servicio s) {return s.valor();}
            public int g() { class Servicio { int valor() {return 0;} } return new Servicio().valor(); }
            public int h() { Runnable r = () -> Servicio.valor(); return 0; }
        }""",
        },
    )
    assert all(
        f["llama_a"] == []
        for nombre, f in funciones.items()
        if "Cliente.java::" in nombre
    )


def test_clases_anidadas_e_import_de_tipo_anidado(tmp_path: Path) -> None:
    """El nombre calificado de una clase anidada se conserva en la referencia común."""
    funciones = _analizar(
        tmp_path,
        {
            "p/Exterior.java": "package p; public class Exterior { public static class Interior { public static int valor() {return 1;} } }",
            "q/Cliente.java": "package q; import p.Exterior; class Cliente { public int f() {return Exterior.Interior.valor();} }",
        },
    )
    assert funciones["q/Cliente.java::Cliente.f"]["llama_a"] == [
        "p/Exterior.java::Exterior.Interior.valor"
    ]


def test_no_resuelve_comodines_herencia_ni_referencias(tmp_path: Path) -> None:
    """Las construcciones que necesitan resolución adicional quedan sin enlaces."""
    funciones = _analizar(
        tmp_path,
        {
            "p/Servicio.java": "package p; public class Servicio { public static int valor() {return 1;} }",
            "q/Cliente.java": "package q; import p.*; class Cliente extends Base { public int f() { java.util.function.Supplier<Integer> s = Servicio::valor; return Servicio.valor(); } }",
        },
    )
    assert funciones["q/Cliente.java::Cliente.f"]["llama_a"] == []


def test_banco_real_no_enlaza_metodos_de_bibliotecas() -> None:
    """Las operaciones de listas del banco no se presentan como métodos del proyecto."""
    banco = Path(__file__).resolve().parents[2] / "bench_java"
    estructura = JavaAdapter().analizar(banco)
    assert estructura["errores"] == []
    assert all(
        f["llama_a"] == [] for m in estructura["modulos"] for f in m["funciones"]
    )

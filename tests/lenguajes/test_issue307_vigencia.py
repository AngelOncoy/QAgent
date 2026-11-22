"""Vigencia transitiva y evidencia Java: análisis estático, sin ejecutar fuentes."""

from copy import deepcopy
from dataclasses import replace

import pytest

from qagent.almacenamiento import AlmacenProyecto, id_de_spec
from qagent.almacenamiento.reutilizacion import valida, vigente
from qagent.config import cargar_configuracion
from qagent.lenguajes import JavaAdapter, java_vigencia

IMAGEN = "sha256:" + "a" * 64
RUN = "20261121-000000-0307"


def escribir(raiz, relativa, contenido):
    ruta = raiz / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


@pytest.fixture
def proyecto(tmp_path):
    escribir(
        tmp_path,
        "A.java",
        """public class A {
      public static int f() { return B.g(); }
      /** Devuelve uno. @return uno */ public static int documentado() { return B.g(); }
    }""",
    )
    escribir(
        tmp_path, "B.java", "public class B { public static int g() { return C.h(); } }"
    )
    escribir(
        tmp_path, "C.java", "public class C { public static int h() { return 1; } }"
    )
    escribir(
        tmp_path,
        "Usos.java",
        "public class Usos { public int usar() { return A.f(); } }",
    )
    escribir(
        tmp_path,
        "U.java",
        "public class U { /** Devuelve siete. */ public static int sano() { return 7; } }",
    )
    escribir(
        tmp_path,
        "src/test/java/ATest.java",
        """import org.junit.jupiter.api.Test;
      import static org.junit.jupiter.api.Assertions.assertEquals;
      class ATest { @Test void comprueba() { assertEquals(1,A.f()); } }""",
    )
    escribir(
        tmp_path, "pom.xml", "<project><modelVersion>4.0.0</modelVersion></project>"
    )
    return tmp_path


def claves(raiz, config=None, imagen=IMAGEN):
    adaptador = JavaAdapter()
    analisis = adaptador.analizar(raiz)
    return adaptador.claves_reutilizacion(raiz, analisis["modulos"], config, imagen)


def contrato_a(raiz):
    modulo = next(
        m for m in JavaAdapter().analizar(raiz)["modulos"] if m["ruta"] == "A.java"
    )
    funcion = next(f for f in modulo["funciones"] if f["nombre"] == "A.f")
    return {
        "version": "3",
        "lenguaje": "java",
        "framework_pruebas": "junit5",
        "tipo": "funcion",
        "modulo": "A.java",
        "huella": modulo["huella"],
        "objetivo": "A.f",
        "firma": funcion["firma"],
        "critical": False,
        "casos": [
            {
                "id": "inferido",
                "entrada": {},
                "valor_esperado": 1,
                "origen": "inferido",
                "evidencia": ["cuerpo", "dependencia:B.java::B.g"],
                "categoria": "normal",
            }
        ],
    }


def test_control_sin_cambios_y_tres_claves_distintas(proyecto):
    anterior = claves(proyecto)
    assert anterior == claves(proyecto)
    assert ("A.java", "A.f") in anterior
    assert all(valida(meta) for meta in anterior.values())
    assert (
        len({anterior[("A.java", "A.f")][k] for k in ("spec", "pruebas", "mutacion")})
        == 3
    )


@pytest.mark.parametrize("archivo", ["B.java", "C.java", "Usos.java"])
def test_dependencias_transitivas_y_llamadores_invalidan_sin_tocar_a(proyecto, archivo):
    anterior = claves(proyecto)
    original_a = (proyecto / "A.java").read_bytes()
    ruta = proyecto / archivo
    ruta.write_text(
        ruta.read_text(encoding="utf-8") + "\n// cambio pertinente", encoding="utf-8"
    )
    actual = claves(proyecto)
    assert actual[("A.java", "A.f")] != anterior[("A.java", "A.f")]
    assert actual[("U.java", "U.sano")] == anterior[("U.java", "U.sano")]
    assert (proyecto / "A.java").read_bytes() == original_a


@pytest.mark.parametrize("accion", ["cambiar", "borrar", "agregar"])
def test_evidencia_tests_afecta_inferidos_no_contratos_documentados(proyecto, accion):
    anterior = claves(proyecto)
    ruta = proyecto / "src/test/java/ATest.java"
    if accion == "borrar":
        ruta.unlink()
    elif accion == "cambiar":
        ruta.write_text(
            ruta.read_text(encoding="utf-8").replace(
                "assertEquals(1", "assertEquals(2"
            ),
            encoding="utf-8",
        )
    else:
        escribir(
            proyecto,
            "src/test/java/OtroTest.java",
            "class OtroTest { int dato() { return A.f(); } }",
        )
    actual = claves(proyecto)
    assert actual[("A.java", "A.f")] != anterior[("A.java", "A.f")]
    assert actual[("A.java", "A.documentado")] == anterior[("A.java", "A.documentado")]
    assert actual[("U.java", "U.sano")] == anterior[("U.java", "U.sano")]


def test_ciclo_es_determinista_y_el_borrado_de_dependencia_invalida(proyecto):
    escribir(
        proyecto, "C.java", "public class C { public static int h() { return B.g(); } }"
    )
    anterior = claves(proyecto)
    assert anterior == claves(proyecto)
    (proyecto / "B.java").unlink()
    assert claves(proyecto)[("A.java", "A.f")] != anterior[("A.java", "A.f")]


@pytest.mark.parametrize(
    "archivo", ["pom.xml", ".mvn/maven.config", "src/main/resources/datos.txt"]
)
def test_entorno_de_proyecto_invalida_todas_las_claves(proyecto, archivo):
    anterior = claves(proyecto)
    escribir(proyecto, archivo, "cambio de configuración")
    actual = claves(proyecto)
    assert all(actual[k] != v for k, v in anterior.items())


def test_configuracion_distingue_spec_pruebas_y_mutacion(proyecto):
    config = cargar_configuracion(simulado=True).config
    clave = ("A.java", "A.f")
    anterior = claves(proyecto, config)[clave]
    inferencia = claves(
        proyecto,
        replace(
            config, inferencia=replace(config.inferencia, max_caracteres_contexto=5000)
        ),
    )[clave]
    assert anterior["spec"] != inferencia["spec"]
    limites = replace(config.limites_sandbox("java"), timeout_s=111)
    ejecucion = claves(proyecto, replace(config, sandbox_lenguajes={"java": limites}))[
        clave
    ]
    assert (
        anterior["spec"] == ejecucion["spec"]
        and anterior["pruebas"] != ejecucion["pruebas"]
    )
    pit = claves(
        proyecto,
        replace(
            config, mutacion=replace(config.mutacion, tiempo_maximo_por_funcion_s=111)
        ),
    )[clave]
    assert anterior["spec"] == pit["spec"] and anterior["pruebas"] == pit["pruebas"]
    assert anterior["mutacion"] != pit["mutacion"]


def test_imagen_distinta_no_reutiliza_pruebas_ni_pit_pero_conserva_contrato(proyecto):
    anterior = claves(proyecto)[("A.java", "A.f")]
    actual = claves(proyecto, imagen="sha256:" + "b" * 64)[("A.java", "A.f")]
    assert vigente(anterior, actual, "spec")
    assert not vigente(anterior, actual, "pruebas")
    assert not vigente(anterior, actual, "mutacion")


def test_guardar_contrato_y_cambiar_solo_b_no_lo_hace_vigente(proyecto):
    contrato = contrato_a(proyecto)
    copia = deepcopy(contrato)
    meta = claves(proyecto)
    almacen = AlmacenProyecto(proyecto)
    almacen.guardar_plan_modulo(
        "A.java",
        contrato["huella"],
        [contrato],
        RUN,
        "generado",
        reutilizacion={"A.f": meta[("A.java", "A.f")]},
    )
    estado = {p: p.read_bytes() for p in almacen.carpeta_specs.glob("*")}
    assert almacen.buscar_plan_vigente(
        "A.java", contrato["huella"], {"A.f": meta[("A.java", "A.f")]}
    )
    escribir(
        proyecto, "B.java", "public class B { public static int g() { return 2; } }"
    )
    actual = claves(proyecto)
    assert (
        almacen.buscar_plan_vigente(
            "A.java", contrato["huella"], {"A.f": actual[("A.java", "A.f")]}
        )
        is None
    )
    assert all(p.read_bytes() == datos for p, datos in estado.items())
    assert contrato == copia


def test_registro_antiguo_legible_sin_inventar_contexto(proyecto):
    contrato = contrato_a(proyecto)
    almacen = AlmacenProyecto(proyecto)
    almacen.guardar_plan_modulo(
        "A.java", contrato["huella"], [contrato], RUN, "generado"
    )
    spec = almacen.guardar_spec(contrato, RUN, huella_objetivo="a" * 64)
    archivos = {p: p.read_bytes() for p in almacen.carpeta_specs.glob("*")}
    assert (
        almacen.leer_spec(spec["id"])["contrato"]["casos"][0]["evidencia"]
        == contrato["casos"][0]["evidencia"]
    )
    assert (
        almacen.buscar_plan_vigente(
            "A.java", contrato["huella"], {"A.f": claves(proyecto)[("A.java", "A.f")]}
        )
        is None
    )
    assert all(p.read_bytes() == contenido for p, contenido in archivos.items())


@pytest.mark.parametrize("invalida", [None, {}, {"version": "999"}, []])
def test_metadata_ausente_o_desconocida_no_reutilizable(proyecto, invalida):
    actual = claves(proyecto)[("A.java", "A.f")]
    assert not vigente(invalida, actual, "spec")


def test_lectura_acotada_no_habilita_cache_parcial(proyecto, monkeypatch):
    monkeypatch.setattr(java_vigencia, "MAX_ARCHIVOS", 1)
    assert claves(proyecto) == {}


def test_snapshot_no_certifica_fuentes_cambiadas_tras_el_analisis(proyecto):
    adaptador = JavaAdapter()
    modulos = adaptador.analizar(proyecto)["modulos"]
    escribir(
        proyecto, "B.java", "public class B { public static int g() { return 3; } }"
    )
    assert adaptador.claves_reutilizacion(proyecto, modulos, imagen=IMAGEN) == {}


def test_cache_de_mutacion_exige_contexto_y_conserva_scores_anteriores(proyecto):
    almacen = AlmacenProyecto(proyecto)
    meta = claves(proyecto)[("A.java", "A.f")]
    identificador = id_de_spec("A.java", "A.f")
    almacen.guardar_mutacion(
        identificador,
        "a" * 64,
        "b" * 64,
        {"estado": "ok", "puntuacion": 100},
        RUN,
        reutilizacion=meta,
    )
    assert almacen.mutacion_vigente(identificador, "a" * 64, "b" * 64, meta)
    ruta = almacen.carpeta_mutacion / (identificador + ".json")
    contenido = ruta.read_bytes()
    escribir(
        proyecto, "C.java", "public class C { public static int h() { return 9; } }"
    )
    actual = claves(proyecto)[("A.java", "A.f")]
    assert almacen.mutacion_vigente(identificador, "a" * 64, "b" * 64, actual) is None
    assert ruta.read_bytes() == contenido

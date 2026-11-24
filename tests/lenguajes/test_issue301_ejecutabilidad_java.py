"""Ejecutabilidad de objetivos Java antes de gastar Planner o Generator (#301).

Todo es lectura estática con tree-sitter: no se compila ni se ejecuta Java en el host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_ejecutabilidad import clasificar_local
from qagent.lenguajes.java_generacion import contexto_java

INTERFAZ = """package com.demo;

/** Contrato. */
public interface I {
    /** @return el valor */
    int valor();
    /** @return 2 */
    default int doble() { return 2; }
    /** @return 3 */
    static int tres() { return 3; }
}
"""
ABSTRACTA = """package com.demo;

public abstract class A {
    /** @return el valor */
    public abstract int valor();
    /** @return 1 */
    public int uno() { return 1; }
    /** @return 4 */
    public static int cuatro() { return 4; }
}
"""
CONCRETA = """package com.demo;

public class C {
    /** @return 5 */
    public int cinco() { return 5; }
}
"""
PRIVADA = """package com.demo;

public class P {
    private P() {}
    /** @return 5 */
    public int cinco() { return 5; }
    /** @return una instancia */
    public static P crear() { return new P(); }
}
"""
ANIDADAS = """package com.demo;

public class Externa {
    public class Interna {
        /** @return 1 */
        public int uno() { return 1; }
    }
    public static class Estatica {
        /** @return 2 */
        public int dos() { return 2; }
    }
    private static class Oculta {
        /** @return 3 */
        public static int tres() { return 3; }
    }
    public record Par(int a) {
        /** @return a */
        public int primero() { return a; }
    }
}
"""
CON_DEPENDENCIA = """package com.demo;

public class Servicio {
    private final Repo repo;
    public Servicio(Repo repo) { this.repo = repo; }
    /** @return 7 */
    public int siete() { return 7; }
}
"""
REPO = """package com.demo;

public interface Repo {
    /** @return el total */
    int total();
}
"""
SIMPLE = """package com.demo;

public class Contador {
    private final int base;
    public Contador(int base) { this.base = base; }
    /** @return la base */
    public int base() { return base; }
}
"""
AUTORREFERENCIA = """package com.demo;

public class Nodo {
    public Nodo(Nodo siguiente) {}
    /** @return 0 */
    public int cero() { return 0; }
}
"""
POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.demo</groupId><artifactId>demo</artifactId><version>1</version>
  <dependencies>{dependencias}</dependencies>
</project>
"""
MOCKITO = (
    "<dependency><groupId>org.mockito</groupId>"
    "<artifactId>mockito-core</artifactId><version>5.14.2</version>"
    "<scope>test</scope></dependency>"
)


def _proyecto(raiz: Path, archivos: dict[str, str], pom: str | None = "") -> Path:
    if pom is not None:
        archivos = {"pom.xml": POM.format(dependencias=pom), **archivos}
    for ruta, texto in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return raiz


def _clasificacion(raiz: Path) -> dict[str, dict]:
    estructura = JavaAdapter().analizar(raiz)
    assert estructura["errores"] == []
    return {
        f["nombre"]: f["ejecutabilidad"]
        for m in estructura["modulos"]
        for f in m["funciones"]
    }


def _ruta(clase: str) -> str:
    return f"src/main/java/com/demo/{clase}.java"


def test_reproduce_interfaz_y_clase_abstracta(tmp_path: Path) -> None:
    """Antes del fix, los cinco primeros llegaban al Planner como objetivos normales."""
    raiz = _proyecto(
        tmp_path,
        {_ruta("I"): INTERFAZ, _ruta("A"): ABSTRACTA, _ruta("C"): CONCRETA},
    )
    estados = {n: e["estado"] for n, e in _clasificacion(raiz).items()}
    assert estados == {
        "I.valor": "no_ejecutable",
        "I.doble": "pendiente_contexto",
        "I.tres": "ejecutable",
        "A.valor": "no_ejecutable",
        "A.uno": "pendiente_contexto",
        "A.cuatro": "ejecutable",
        "C.cinco": "ejecutable",
    }


def test_cada_objetivo_no_ejecutable_registra_su_motivo(tmp_path: Path) -> None:
    raiz = _proyecto(tmp_path, {_ruta("I"): INTERFAZ, _ruta("A"): ABSTRACTA})
    clasificacion = _clasificacion(raiz)
    assert "abstracta sin cuerpo" in clasificacion["I.valor"]["motivo"]
    assert "abstracta sin cuerpo" in clasificacion["A.valor"]["motivo"]
    assert "default" in clasificacion["I.doble"]["motivo"]
    assert "abstracta" in clasificacion["A.uno"]["motivo"]
    assert clasificacion["I.tres"]["motivo"] is None
    adaptador = JavaAdapter()
    assert (
        adaptador.motivo_funcion_no_planificable(
            {"ejecutabilidad": clasificacion["A.uno"]}
        )
        == clasificacion["A.uno"]["motivo"]
    )
    assert (
        adaptador.motivo_funcion_no_planificable(
            {"ejecutabilidad": clasificacion["I.tres"]}
        )
        is None
    )


def test_constructor_privado_y_fabrica_estatica(tmp_path: Path) -> None:
    clasificacion = _clasificacion(_proyecto(tmp_path, {_ruta("P"): PRIVADA}))
    assert clasificacion["P.cinco"]["estado"] == "no_ejecutable"
    assert "constructor accesible" in clasificacion["P.cinco"]["motivo"]
    assert clasificacion["P.crear"]["estado"] == "ejecutable"


def test_clases_anidadas_enum_y_record(tmp_path: Path) -> None:
    clasificacion = _clasificacion(_proyecto(tmp_path, {_ruta("Externa"): ANIDADAS}))
    estados = {n: e["estado"] for n, e in clasificacion.items()}
    assert estados == {
        "Externa.Interna.uno": "no_ejecutable",
        "Externa.Estatica.dos": "ejecutable",
        "Externa.Oculta.tres": "no_ejecutable",
        "Externa.Par.primero": "ejecutable",
    }
    assert "clase externa" in clasificacion["Externa.Interna.uno"]["motivo"]
    assert "private" in clasificacion["Externa.Oculta.tres"]["motivo"]


def test_metodo_de_instancia_de_enum_queda_pendiente() -> None:
    """El análisis aún no extrae métodos de enum; la regla queda lista si se amplía."""
    clases = {
        "Color": {
            "nombre": "Color",
            "tipo": "enum_declaration",
            "modificadores": ["public"],
            "contenedor_tipo": None,
            "constructores": [],
        }
    }
    funcion = {"clase": "Color", "es_static": False, "abstracto": False}
    clasificacion = clasificar_local(funcion, clases)
    assert clasificacion["estado"] == "pendiente_contexto"
    assert "constante del enum" in clasificacion["motivo"]
    estatica = clasificar_local({**funcion, "es_static": True}, clases)
    assert estatica["estado"] == "ejecutable"


def test_dependencias_del_constructor_segun_mockito(tmp_path: Path) -> None:
    archivos = {
        _ruta("Servicio"): CON_DEPENDENCIA,
        _ruta("Repo"): REPO,
        _ruta("Contador"): SIMPLE,
        _ruta("Nodo"): AUTORREFERENCIA,
    }
    sin = _clasificacion(_proyecto(tmp_path / "sin", archivos))
    assert sin["Servicio.siete"]["estado"] == "pendiente_contexto"
    assert "Repo" in sin["Servicio.siete"]["motivo"]
    assert "Mockito" in sin["Servicio.siete"]["motivo"]
    assert sin["Contador.base"]["estado"] == "ejecutable"

    con = _clasificacion(_proyecto(tmp_path / "con", archivos, MOCKITO))
    assert con["Servicio.siete"]["estado"] == "ejecutable"
    # Simular el propio objetivo violaría el guardrail, aunque haya Mockito.
    assert con["Nodo.cero"]["estado"] == "pendiente_contexto"
    assert "propia clase" in con["Nodo.cero"]["motivo"]


def test_spring_boot_starter_test_aporta_mockito(tmp_path: Path) -> None:
    starter = (
        "<dependency><groupId>org.springframework.boot</groupId>"
        "<artifactId>spring-boot-starter-test</artifactId>"
        "<scope>test</scope></dependency>"
    )
    archivos = {_ruta("Servicio"): CON_DEPENDENCIA, _ruta("Repo"): REPO}
    clasificacion = _clasificacion(_proyecto(tmp_path, archivos, starter))
    assert clasificacion["Servicio.siete"]["estado"] == "ejecutable"


def test_mockito_heredado_del_pom_padre_del_reactor(tmp_path: Path) -> None:
    _proyecto(tmp_path, {}, MOCKITO)
    modulo = tmp_path / "core"
    _proyecto(
        modulo,
        {_ruta("Servicio"): CON_DEPENDENCIA, _ruta("Repo"): REPO},
    )
    estructura = JavaAdapter().analizar(tmp_path)
    clasificacion = {
        f["nombre"]: f["ejecutabilidad"]
        for m in estructura["modulos"]
        for f in m["funciones"]
    }
    assert clasificacion["Servicio.siete"]["estado"] == "ejecutable"


@pytest.mark.parametrize(
    ("clase", "fuente", "objetivo", "fragmento"),
    [
        ("I", INTERFAZ, "I.valor", "abstracta sin cuerpo"),
        ("A", ABSTRACTA, "A.uno", "abstracta"),
        ("P", PRIVADA, "P.cinco", "constructor accesible"),
    ],
)
def test_contexto_java_rechaza_con_la_misma_regla(
    tmp_path: Path, clase: str, fuente: str, objetivo: str, fragmento: str
) -> None:
    """Defensa en el Generator: una spec antigua no puede saltarse la clasificación."""
    raiz = _proyecto(tmp_path, {_ruta(clase): fuente})
    funcion = next(
        f
        for m in JavaAdapter().analizar(raiz)["modulos"]
        for f in m["funciones"]
        if f["nombre"] == objetivo
    )
    contrato = {
        "modulo": _ruta(clase),
        "objetivo": objetivo,
        "firma": funcion["firma"],
        "tipo": "funcion",
    }
    with pytest.raises(ValueError, match=fragmento):
        contexto_java(contrato, raiz)


def test_contexto_java_acepta_estaticos_y_concretos(tmp_path: Path) -> None:
    raiz = _proyecto(tmp_path, {_ruta("A"): ABSTRACTA, _ruta("C"): CONCRETA})
    for modulo in JavaAdapter().analizar(raiz)["modulos"]:
        for funcion in modulo["funciones"]:
            if funcion["ejecutabilidad"]["estado"] != "ejecutable":
                continue
            contrato = {
                "modulo": modulo["ruta"],
                "objetivo": funcion["nombre"],
                "firma": funcion["firma"],
                "tipo": "funcion",
            }
            assert contexto_java(contrato, raiz)["clase"] == funcion["clase"]

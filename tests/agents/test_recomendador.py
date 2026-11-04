"""Agente Recomendador por reglas (#197, ADR-011).

Criterios de aceptación:
1. Una función determinista recibe el análisis y devuelve una lista ordenada de
   tipos de prueba, cada uno con su motivo.
2. Solo recomienda lo que declara el adaptador de cada lenguaje; lo demás aparece
   como «próximamente».
3. (Interfaz: ver ``tests/frontend/test_issue197_recomendacion.py``.)
4. No usa ningún LLM (0 tokens).
5. Proyectos de ejemplo: solo funciones, solo FastAPI, mixto y sin nada que probar
   (y, desde que Java está completo, un proyecto Maven con Spring).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents import recomendador
from qagent.agents.recomendador import (
    proximamente,
    proyectar,
    recomendar,
    recomendar_para_vista,
    validar_recomendacion,
)
from qagent.lenguajes import REGISTRO
from qagent.proyectos.vista_previa import generar_vista_previa

FUNCIONES = '''
def sumar(a: int, b: int) -> int:
    """Suma dos enteros."""
    return a + b


def clasificar(n: int) -> str:
    """Devuelve 'par' o 'impar'."""
    if n % 2 == 0:
        return "par"
    return "impar"
'''

API = '''
from fastapi import FastAPI

app = FastAPI()


@app.get("/items/{item_id}")
def leer_item(item_id: int) -> dict:
    """Devuelve un ítem."""
    return {"id": item_id}


@app.post("/items", status_code=201)
def crear_item(nombre: str) -> dict:
    """Crea un ítem."""
    return {"nombre": nombre}
'''


def _crear(raiz: Path, archivos: dict[str, str]) -> Path:
    for ruta, contenido in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
    return raiz


def _tipos(vista: dict[str, Any]) -> list[str]:
    return [r["tipo_prueba"] for r in vista["recomendacion"]["recomendaciones"]]


# --- Proyectos de ejemplo (criterio 5) ---------------------------------------------


def test_solo_funciones_recomienda_unitarias_y_mutacion(tmp_path: Path) -> None:
    vista = generar_vista_previa(_crear(tmp_path, {"calc.py": FUNCIONES}))

    assert _tipos(vista) == ["funcion", "mutacion"]
    motivos = [r["motivo"] for r in vista["recomendacion"]["recomendaciones"]]
    assert "Las 2 funciones públicas tienen tipos y documentación" in motivos[0]
    assert "1 objetivo con decisiones" in motivos[1]
    assert vista["proximamente"] == []


def test_solo_fastapi_recomienda_endpoints(tmp_path: Path) -> None:
    vista = generar_vista_previa(_crear(tmp_path, {"app/main.py": API}))

    assert _tipos(vista) == ["endpoint"]
    motivo = vista["recomendacion"]["recomendaciones"][0]["motivo"]
    assert "2 endpoints con ruta resuelta" in motivo
    assert "FastAPI" not in motivo  # los motivos no nombran frameworks (ADR-007)
    assert "GET /items/{item_id}" in motivo


def test_mixto_ordena_endpoints_unitarias_y_mutacion(tmp_path: Path) -> None:
    vista = generar_vista_previa(
        _crear(tmp_path, {"app/main.py": API, "app/calc.py": FUNCIONES})
    )

    assert _tipos(vista) == ["endpoint", "funcion", "mutacion"]
    contracts.validar_versionado("recommendation", vista["recomendacion"])
    assert vista["recomendacion"]["origen"] == "reglas"


def test_sin_nada_que_probar_devuelve_lista_vacia(tmp_path: Path) -> None:
    vista = generar_vista_previa(
        _crear(tmp_path, {"constantes.py": "LIMITE = 10\n", "_interno.py": ""})
    )

    assert vista["recomendacion"] == {
        "version": "1",
        "origen": "reglas",
        "recomendaciones": [],
    }


def test_carpeta_invalida_trae_recomendacion_vacia(tmp_path: Path) -> None:
    vista = generar_vista_previa(tmp_path / "no-existe")

    assert vista["ok"] is False
    assert vista["recomendacion"]["recomendaciones"] == []
    assert vista["proximamente"] == []


# --- Reglas (criterio 1) ------------------------------------------------------------


def test_es_determinista(tmp_path: Path) -> None:
    raiz = _crear(tmp_path, {"app/main.py": API, "app/calc.py": FUNCIONES})

    assert (
        generar_vista_previa(raiz)["recomendacion"]
        == (generar_vista_previa(raiz)["recomendacion"])
    )


def test_funciones_sin_documentar_avisan_oraculo_debil(tmp_path: Path) -> None:
    vista = generar_vista_previa(
        _crear(tmp_path, {"m.py": "def doble(x):\n    return x * 2\n"})
    )

    assert _tipos(vista) == ["funcion"]
    assert (
        "ninguna tiene tipos y documentación"
        in (vista["recomendacion"]["recomendaciones"][0]["motivo"])
    )


def test_endpoint_sin_ruta_resuelta_no_se_recomienda() -> None:
    vista = {
        "modulos": [
            {
                "funciones": [],
                "endpoints": [
                    {"objetivo": None, "resuelta": False, "ramas": 2},
                ],
            }
        ]
    }
    proyeccion = proyectar(vista, REGISTRO.detectar_en(["main.py"]))

    assert proyeccion["objetivos"]["endpoints"]["cantidad"] == 0
    assert proyeccion["objetivos"]["endpoints"]["sin_resolver"] == 1
    assert recomendar(proyeccion)["recomendaciones"] == []


def test_la_proyeccion_no_lleva_codigo_ni_rutas_de_archivos(tmp_path: Path) -> None:
    raiz = _crear(tmp_path, {"app/main.py": API, "app/calc.py": FUNCIONES})
    vista = generar_vista_previa(raiz)

    proyeccion = proyectar(vista, REGISTRO.detectar(raiz))
    texto = repr(proyeccion)

    assert str(tmp_path) not in texto
    assert "app/main.py" not in texto
    assert "Suma dos enteros" not in texto
    assert proyeccion["objetivos"]["endpoints"]["rutas_http"] == [
        "GET /items/{item_id}",
        "POST /items",
    ]


# --- Capacidades del adaptador (criterio 2) -----------------------------------------


CALC_JAVA = """package demo;

public class Calc {
    /** Devuelve el mayor de dos enteros. */
    public int mayor(int a, int b) {
        if (a > b) {
            return a;
        }
        return b;
    }
}
"""

API_SPRING = """package demo;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class Api {
    /** Saluda. */
    @GetMapping("/hola")
    public String hola() { return "hola"; }
}
"""

POM = "<project><modelVersion>4.0.0</modelVersion></project>\n"


def test_proyecto_java_con_spring_recomienda_los_tres_tipos(tmp_path: Path) -> None:
    raiz = _crear(
        tmp_path,
        {
            "pom.xml": POM,
            "src/main/java/demo/Calc.java": CALC_JAVA,
            "src/main/java/demo/Api.java": API_SPRING,
        },
    )
    vista = generar_vista_previa(raiz)

    assert vista["lenguaje"] == "java"
    assert _tipos(vista) == ["endpoint", "funcion", "mutacion"]
    assert "GET /api/hola" in vista["recomendacion"]["recomendaciones"][0]["motivo"]
    assert vista["proximamente"] == []


def test_lenguaje_en_desarrollo_aparece_como_proximamente(tmp_path: Path) -> None:
    raiz = _crear(tmp_path, {"calc.py": FUNCIONES, "web/a.ts": "x;"})
    vista = generar_vista_previa(raiz)

    assert _tipos(vista) == ["funcion", "mutacion"]
    assert [p["nombre"] for p in vista["proximamente"]] == ["TypeScript"]
    assert vista["proximamente"][0]["tipos_prueba"] == ["funcion", "mutacion"]
    assert "Se detectó 1 archivo de TypeScript" in vista["proximamente"][0]["motivo"]


def test_proyecto_e2e_only_conserva_tipos_proximos(tmp_path: Path) -> None:
    vista = generar_vista_previa(_crear(tmp_path, {"web/a.ts": "export const x = 1;"}))

    assert vista["ok"] is True
    assert vista["solo_e2e"] is True
    assert vista["recomendacion"]["recomendaciones"] == []
    assert [p["lenguaje"] for p in vista["proximamente"]] == ["typescript"]
    assert vista["proximamente"][0]["tipos_prueba"] == ["funcion", "mutacion"]


def test_solo_cuenta_el_lenguaje_analizado() -> None:
    # Proyecto Python con algo de Java: los objetivos son de Python, así que Java
    # (aunque esté completo) no aporta tipos ni aparece como «próximamente».
    vista = {
        "lenguaje": "python",
        "modulos": [{"funciones": [{"nombre": "f", "ramas": 0}]}],
    }
    proyeccion = proyectar(vista, REGISTRO.detectar_en(["a.py", "b.py", "C.java"]))
    por_lenguaje = {x["lenguaje"]: x for x in proyeccion["lenguajes"]}

    assert por_lenguaje["python"]["analizado"] is True
    assert por_lenguaje["java"]["tipos_prueba_soportados"] == []
    assert proximamente(proyeccion) == []


def test_sin_adaptador_completo_no_recomienda_nada() -> None:
    vista = {"modulos": [{"funciones": [{"nombre": "f", "ramas": 1}]}]}
    proyeccion = proyectar(vista, REGISTRO.detectar_en(["web/a.ts"]))

    assert proyeccion["lenguajes"][0]["tipos_prueba_soportados"] == []
    assert recomendar(proyeccion)["recomendaciones"] == []
    assert [p["lenguaje"] for p in proximamente(proyeccion)] == ["typescript"]


def test_solo_recomienda_lo_que_declara_el_adaptador(tmp_path: Path) -> None:
    raiz = _crear(tmp_path, {"app/main.py": API, "app/calc.py": FUNCIONES})
    vista = generar_vista_previa(raiz)
    proyeccion = proyectar(vista, REGISTRO.detectar(raiz))
    proyeccion["lenguajes"][0]["tipos_prueba_soportados"] = ["funcion"]

    assert [r["tipo_prueba"] for r in recomendar(proyeccion)["recomendaciones"]] == [
        "funcion"
    ]


@pytest.mark.parametrize(
    "dato",
    [
        # Tipo que el proyecto no tiene (no hay endpoints).
        {
            "version": "1",
            "origen": "reglas",
            "recomendaciones": [{"tipo_prueba": "endpoint", "motivo": "x"}],
        },
        # Fuera del contrato.
        {
            "version": "1",
            "origen": "reglas",
            "recomendaciones": [{"tipo_prueba": "e2e", "motivo": "x"}],
        },
        {"version": "1", "origen": "reglas", "recomendaciones": [], "start_run": True},
    ],
)
def test_una_salida_invalida_se_descarta_entera(dato: dict[str, Any]) -> None:
    vista = {"modulos": [{"funciones": [{"nombre": "f", "ramas": 0}]}]}
    proyeccion = proyectar(vista, REGISTRO.detectar_en(["m.py"]))

    assert validar_recomendacion(dato, proyeccion)["recomendaciones"] == []


def test_recomendar_para_vista_usa_el_registro_dado(tmp_path: Path) -> None:
    raiz = _crear(tmp_path, {"calc.py": FUNCIONES})
    vista = generar_vista_previa(raiz)

    resultado = recomendar_para_vista(vista, raiz, REGISTRO)

    assert set(resultado) == {"recomendacion", "proximamente"}


# --- Sin IA (criterio 4) ----------------------------------------------------------------


def test_no_importa_ningun_cliente_de_ia() -> None:
    arbol = ast.parse(Path(recomendador.__file__).read_text(encoding="utf-8"))
    modulos = {
        n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)
    } | {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}

    assert not any(m.startswith(("qagent.llm", "anthropic", "openai")) for m in modulos)

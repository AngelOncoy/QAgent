"""#76: categoría de cada caso de prueba (normal / límite / error).

Schema, inferencia en specs antiguas, coherencia sin IA en el Planner, conteo en
`results.json` y presentación. Con la IA simulada y sin Docker.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents import PlannerAgent
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.contracts import categoria_de, contar_categorias
from qagent.llm import FakeLLMClient, TokenTracker
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.storage.vista_ejecucion import texto_categorias, vista_ejecucion
from qagent.storage.vista_reporte import vista_reporte
from tests.orchestrator.test_en09_mutacion_corrida import ejecutor_exitoso

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLOS = RAIZ / "src" / "qagent" / "contracts" / "ejemplos"
FRONTEND = RAIZ / "src" / "qagent" / "frontend" / "componentes"


def ejemplo(nombre: str) -> dict:
    return json.loads((EJEMPLOS / f"{nombre}.json").read_text(encoding="utf-8"))


# --- Schema ---------------------------------------------------------------------------


@pytest.mark.parametrize("categoria", ["normal", "limite", "error"])
def test_el_schema_acepta_las_tres_categorias(categoria) -> None:
    contrato = ejemplo("planner_contract.v2")
    contrato["casos"][0]["categoria"] = categoria

    contracts.validar(contracts.PLANNER, contrato)


@pytest.mark.parametrize("valor", ["borde", "Normal", "", 1, None])
def test_el_schema_rechaza_una_categoria_desconocida(valor) -> None:
    contrato = ejemplo("planner_contract.v2")
    contrato["casos"][0]["categoria"] = valor

    assert not contracts.es_valido(contracts.PLANNER, contrato)


def test_una_spec_antigua_sin_categoria_sigue_siendo_valida() -> None:
    for nombre in ("planner_contract.v2", "planner_contract.endpoint"):
        contrato = ejemplo(nombre)
        for caso in contrato["casos"]:
            caso.pop("categoria")

        contracts.validar(contracts.PLANNER, contrato)


def test_los_ejemplos_traen_las_categorias() -> None:
    funcion = [c["categoria"] for c in ejemplo("planner_contract.v2")["casos"]]
    endpoint = [c["categoria"] for c in ejemplo("planner_contract.endpoint")["casos"]]

    assert funcion == ["normal", "limite", "error"]
    assert endpoint == ["normal", "error", "error"]


def test_results_acepta_el_conteo_por_categoria_y_rechaza_uno_invalido() -> None:
    results = ejemplo("run_log.results")
    conteo = {"normal": 2, "limite": 1, "error": 1}
    results["objetivos"][0]["casos_por_categoria"] = conteo
    results["resumen"]["casos_por_categoria"] = conteo
    contracts.validar(contracts.RUN_LOG, results)

    results["resumen"]["casos_por_categoria"] = {"normal": 2, "limite": 1}
    assert not contracts.es_valido(contracts.RUN_LOG, results)
    results["resumen"]["casos_por_categoria"] = {**conteo, "borde": 1}
    assert not contracts.es_valido(contracts.RUN_LOG, results)


# --- Inferencia en specs antiguas ----------------------------------------------------


@pytest.mark.parametrize(
    "caso, categoria",
    [
        ({"excepcion": "ValueError"}, "error"),
        ({"valor_esperado": 3}, "normal"),
        ({"valor_esperado": None}, "normal"),
        ({"valor_esperado": {"status_code": 404}}, "error"),
        ({"valor_esperado": {"status_code": 500}}, "error"),
        ({"valor_esperado": {"status_code": 201}}, "normal"),
        ({"valor_esperado": 0, "categoria": "limite"}, "limite"),
    ],
)
def test_se_infiere_la_categoria_si_falta(caso, categoria) -> None:
    assert categoria_de(caso) == categoria


def test_conteo_y_texto_por_categoria() -> None:
    casos = [
        {"valor_esperado": 1},
        {"valor_esperado": 2, "categoria": "normal"},
        {"valor_esperado": 0, "categoria": "limite"},
        {"excepcion": "ValueError"},
    ]

    conteo = contar_categorias(casos)

    assert conteo == {"normal": 2, "limite": 1, "error": 1}
    assert texto_categorias(conteo) == "2 normales · 1 límite · 1 error"
    assert (
        texto_categorias(contar_categorias([])) == "0 normales · 0 límites · 0 errores"
    )


# --- Coherencia sin IA en el Planner --------------------------------------------------

MODULO = {
    "ruta": "calc.py",
    "huella": "a" * 64,
    "funciones": [
        {
            "nombre": "descuento",
            "firma": "(precio: float, porcentaje: float) -> float",
            "docstring": "Aplica el porcentaje (0 a 100); fuera de rango lanza ValueError.",
        },
        {"nombre": "sin_doc", "firma": "(x: int) -> int", "docstring": None},
    ],
}

CASOS = {
    "calc.py::descuento": [
        # Mal clasificado: espera un valor, no un error.
        {
            "id": "normal_mal_marcado",
            "entrada": {"precio": 100, "porcentaje": 20},
            "valor_esperado": 80.0,
            "origen": "docstring",
            "categoria": "error",
        },
        # Mal clasificado: espera una excepción.
        {
            "id": "error_mal_marcado",
            "entrada": {"precio": 100, "porcentaje": 150},
            "excepcion": "ValueError",
            "origen": "docstring",
            "categoria": "normal",
        },
        # Límite descrito en el docstring: se acepta.
        {
            "id": "porcentaje_maximo",
            "entrada": {"precio": 100, "porcentaje": 100},
            "valor_esperado": 0.0,
            "origen": "docstring",
            "categoria": "limite",
        },
        # Sin categoría: queda sin ella y se infiere al leerla.
        {
            "id": "sin_categoria",
            "entrada": {"precio": 50, "porcentaje": 10},
            "valor_esperado": 45.0,
            "origen": "docstring",
        },
    ],
    "calc.py::sin_doc": [
        {"id": "basico", "entrada": {"x": 1}, "valor_esperado": 1, "origen": "tipo"},
        # Sin docstring ni tipos con restricciones: un límite no tiene oráculo.
        {
            "id": "limite_inventado",
            "entrada": {"x": 0},
            "valor_esperado": 0,
            "origen": "tipo",
            "categoria": "limite",
        },
    ],
}


def planificar(perfil: str | None = None):
    agente = PlannerAgent(
        FakeLLMClient(grabaciones=CASOS),
        TokenTracker(),
        es_simulado=True,
        perfil=perfil,
    )
    plan = {c["objetivo"]: c for c in agente.planificar(MODULO)}
    return agente, plan


def test_una_categoria_incoherente_se_corrige_con_aviso_sin_descartar() -> None:
    agente, plan = planificar()

    casos = {c["id"]: c for c in plan["descuento"]["casos"]}
    assert casos["normal_mal_marcado"]["categoria"] == "normal"
    assert casos["error_mal_marcado"]["categoria"] == "error"
    assert casos["porcentaje_maximo"]["categoria"] == "limite"
    assert "categoria" not in casos["sin_categoria"]
    assert categoria_de(casos["sin_categoria"]) == "normal"
    assert len(agente.avisos) == 2
    assert any(
        "'normal_mal_marcado'" in a and "se clasifica como 'normal'" in a
        for a in agente.avisos
    )
    assert any(
        "'error_mal_marcado'" in a and "se clasifica como 'error'" in a
        for a in agente.avisos
    )
    for contrato in plan.values():
        contracts.validar(contracts.PLANNER, contrato)


def test_un_limite_sin_especificacion_se_descarta() -> None:
    agente, plan = planificar()

    assert [c["id"] for c in plan["sin_doc"]["casos"]] == ["basico"]
    assert any(
        "limite_inventado" in d and "sin una especificación" in d
        for d in agente.descartados
    )


def test_humo_elige_un_caso_normal_y_no_un_limite() -> None:
    grabaciones = copy.deepcopy(CASOS)
    grabaciones["calc.py::descuento"] = [
        grabaciones["calc.py::descuento"][2],  # el límite va primero
        grabaciones["calc.py::descuento"][3],
    ]
    agente = PlannerAgent(
        FakeLLMClient(grabaciones=grabaciones),
        TokenTracker(),
        es_simulado=True,
        perfil="humo",
    )

    plan = {c["objetivo"]: c for c in agente.planificar(MODULO)}

    assert [c["id"] for c in plan["descuento"]["casos"]] == ["sin_categoria"]


def test_un_endpoint_normal_que_espera_un_422_se_corrige_a_error() -> None:
    from qagent.analysis import analizar_proyecto

    [modulo] = analizar_proyecto(RAIZ / "bench_api")["modulos"]
    grabaciones = {
        "api_mvp.py::POST /items": [
            {
                "id": "precio_cero",
                "entrada": {
                    "metodo": "POST",
                    "ruta": "/items",
                    "json": {"nombre": "lapiz", "precio": 0},
                },
                "valor_esperado": {"status_code": 422},
                "origen": "modelo_pydantic",
                "categoria": "normal",
            }
        ]
    }
    agente = PlannerAgent(
        FakeLLMClient(grabaciones=grabaciones), TokenTracker(), es_simulado=True
    )

    [contrato] = agente.planificar_endpoints(modulo)

    assert contrato["casos"][0]["categoria"] == "error"
    assert any("se clasifica como 'error'" in a for a in agente.avisos)


# --- Conteo en results.json y presentación --------------------------------------------


@pytest.fixture
def corrida(tmp_path: Path):
    shutil.copy(RAIZ / "bench" / "banco_mvp.py", tmp_path / "banco_mvp.py")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    ejecutar_corrida(
        tmp_path,
        "std",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor_exitoso,
    )
    carpeta = almacen.carpeta_run(run_id)
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    detalle_ruta = carpeta / "detalle.json"
    detalle = (
        json.loads(detalle_ruta.read_text(encoding="utf-8"))
        if detalle_ruta.is_file()
        else None
    )
    return results, detalle


def test_results_cuenta_los_casos_por_categoria(corrida) -> None:
    results, _ = corrida

    contracts.validar(contracts.RUN_LOG, results)
    por_objetivo = {
        o["funcion"]: o["casos_por_categoria"] for o in results["objetivos"]
    }
    assert por_objetivo["calcular_descuento"] == {"normal": 1, "limite": 1, "error": 2}
    assert por_objetivo["clasificar_edad"] == {"normal": 2, "limite": 2, "error": 1}
    assert por_objetivo["es_palindromo"] == {"normal": 2, "limite": 0, "error": 0}
    total = results["resumen"]["casos_por_categoria"]
    assert total == {
        c: sum(o[c] for o in por_objetivo.values())
        for c in ("normal", "limite", "error")
    }


def test_el_informe_muestra_el_conteo_y_avisa_sin_limites(corrida) -> None:
    results, detalle = corrida

    v = vista_reporte(results, detalle)

    assert v["texto_categorias"] == texto_categorias(
        results["resumen"]["casos_por_categoria"]
    )
    funciones = {f["funcion"]: f for f in v["funciones"]}
    descuento = funciones["calcular_descuento"]
    assert descuento["texto_categorias"] == "1 normal · 1 límite · 2 errores"
    assert descuento["aviso_limites"] is None
    palindromo = funciones["es_palindromo"]
    assert palindromo["aviso_limites"].startswith("Sin casos límite")
    # El aviso no cuenta como fallo.
    assert palindromo["verde"] is True
    assert vista_ejecucion(results)["modulos"][0]["pruebas"][0]["categorias"]


def test_una_corrida_anterior_sin_conteo_se_infiere_del_contrato(corrida) -> None:
    results, detalle = corrida
    for objetivo in results["objetivos"]:
        objetivo.pop("casos_por_categoria")
    results["resumen"].pop("casos_por_categoria")
    if detalle is None:
        pytest.skip("la corrida no guardó detalle.json con los contratos")
    for funcion in detalle["funciones"]:
        for caso in (funcion.get("contrato") or {}).get("casos", []):
            caso.pop("categoria", None)

    v = vista_reporte(results, detalle)

    descuento = next(f for f in v["funciones"] if f["funcion"] == "calcular_descuento")
    # Sin la categoría declarada, el límite se infiere como normal.
    assert descuento["categorias"] == {"normal": 2, "limite": 0, "error": 2}
    assert v["texto_categorias"] is None


def test_la_interfaz_muestra_las_categorias() -> None:
    informe = (FRONTEND / "informe" / "informe.js").read_text(encoding="utf-8")
    ejecucion = (FRONTEND / "ejecucion" / "ejecucion.js").read_text(encoding="utf-8")

    assert "Casos de la corrida: ${escHtml(v.texto_categorias)}" in informe
    assert "Casos: ${escHtml(f.texto_categorias)}" in informe
    assert "escHtml(f.aviso_limites)" in informe
    assert "categoriaDeCaso(f, c.nombre)" in informe
    assert "NOMBRE_CATEGORIA[c.categoria]" in informe
    assert "escHtml(p.categorias)" in ejecucion

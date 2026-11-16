"""Inferencia Java en el Planner real: contrato, evidencia y omisiones."""

import pytest

from qagent import contracts
from qagent.agents.planner import PlannerAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import TokenTracker
from tests.agents.test_planner_inferencia import ClienteSecuencia
from tests.lenguajes.test_issue292_java_inferencia import escribir


def preparar(tmp_path, caso, *, perfil="std", inferir=True):
    escribir(
        tmp_path,
        "src/main/java/demo/Calc.java",
        "package demo; public class Calc { public static int producto(int a, int b) { return a*b; } }",
    )
    adaptador = JavaAdapter()
    analisis = adaptador.analizar(tmp_path)
    [modulo] = analisis["modulos"]
    cliente = ClienteSecuencia([], [{"objetivo": "Calc.producto", "casos": caso}])
    planner = PlannerAgent(
        cliente,
        TokenTracker(),
        adaptador=adaptador,
        perfil=perfil,
        es_simulado=True,
        proveedor_inferencia=adaptador.proveedor_inferencia(tmp_path, analisis, 6000)
        if inferir
        else None,
    )
    return planner, cliente, planner.planificar(modulo)


def caso(**cambios):
    return {
        "id": "producto_normal",
        "entrada": {"a": 2, "b": 3},
        "valor_esperado": 6,
        "origen": "inferido",
        "evidencia": ["cuerpo"],
        "categoria": "normal",
        **cambios,
    }


def test_infiere_contrato_java_valido_con_evidencia(tmp_path):
    planner, cliente, plan = preparar(tmp_path, [caso()])
    [contrato] = plan
    contracts.validar(contracts.PLANNER_V3, contrato)
    assert contrato["lenguaje"] == "java"
    assert contrato["framework_pruebas"] == "junit5"
    assert contracts.es_contrato_inferido(contrato)
    assert contrato["casos"][0]["valor_esperado"] == 6
    assert not planner.omitidas
    assert len(cliente.prompts) == 2
    assert "REGRESIÓN" in cliente.prompts[1]
    assert "return a*b" in cliente.prompts[1]


@pytest.mark.parametrize(
    "invalido",
    [
        caso(evidencia=[]),
        caso(evidencia=["test_existente:inventado"]),
        caso(valor_esperado="seis"),
        caso(entrada={"a": "dos", "b": 3}),
        caso(origen="docstring"),
        caso(tipo_valor_esperado="tuple"),
    ],
)
def test_rechaza_evidencia_y_valores_incompatibles(tmp_path, invalido):
    planner, _, plan = preparar(tmp_path, [invalido])
    assert plan == []
    assert "Calc.producto" in planner.omitidas


def test_humo_conserva_un_normal_y_estandar_conserva_casos_validos(tmp_path):
    casos = [
        caso(),
        caso(id="producto_otro", entrada={"a": 3, "b": 4}, valor_esperado=12),
    ]
    _, _, plan = preparar(tmp_path, casos, perfil="humo")
    assert len(plan[0]["casos"]) == 1
    _, _, plan = preparar(tmp_path, casos)
    assert len(plan[0]["casos"]) == 2


def test_desactivada_no_pide_contexto_ni_llamada_de_inferencia(tmp_path):
    planner, cliente, plan = preparar(tmp_path, [caso()], inferir=False)
    assert not plan
    assert "Calc.producto" in planner.omitidas
    assert len(cliente.prompts) == 1


def test_contrato_documentado_no_se_reinterpreta(tmp_path):
    escribir(
        tmp_path,
        "Calc.java",
        "/** Clase. */ public class Calc { /** Devuelve seis. */ public static int producto(int a, int b) { return 999; } }",
    )
    adaptador = JavaAdapter()
    analisis = adaptador.analizar(tmp_path)
    documentado = caso(origen="docstring")
    documentado.pop("evidencia")
    cliente = ClienteSecuencia([{"objetivo": "Calc.producto", "casos": [documentado]}])
    planner = PlannerAgent(
        cliente,
        TokenTracker(),
        adaptador=adaptador,
        es_simulado=True,
        proveedor_inferencia=adaptador.proveedor_inferencia(tmp_path, analisis, 6000),
    )
    [contrato] = planner.planificar(analisis["modulos"][0])
    assert contrato["casos"][0]["valor_esperado"] == 6
    assert not contracts.es_contrato_inferido(contrato)
    assert len(cliente.prompts) == 1

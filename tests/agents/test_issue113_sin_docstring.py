"""Regresiones de la issue #113: funciones sin docstring y oráculos fiables."""

from __future__ import annotations

import json

import pytest

from qagent import contracts
from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import ErrorRespuestaPlanner, PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.analysis import analizar_proyecto, comparar_aserciones
from qagent.llm import RespuestaLLM, TokenTracker


class ClienteGrabado:
    """Devuelve una respuesta controlada sin llamar a un proveedor real."""

    def __init__(self, propuesta: object) -> None:
        self.contenido = (
            propuesta if isinstance(propuesta, str) else json.dumps(propuesta)
        )
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(
            contenido=self.contenido,
            tokens_entrada=1,
            tokens_salida=1,
            costo_usd=0,
            modelo="modelo-prueba",
        )


def funcion(
    *,
    nombre: str = "objetivo",
    firma: str = "(x)",
    retorno: str | None = None,
    docstring: str | None = None,
) -> dict:
    """Crea metadatos mínimos equivalentes a los producidos por el analizador."""
    return {
        "nombre": nombre,
        "firma": firma,
        "retorno": retorno,
        "docstring": docstring,
        "llama_a": [],
    }


def modulo(*funciones: dict) -> dict:
    """Crea un módulo sintético para Planner."""
    return {
        "ruta": "app/utils/siamese_loader.py",
        "huella": "1" * 64,
        "funciones": list(funciones),
    }


def caso(
    *,
    entrada: dict,
    origen: str,
    valor: object = pytest.param,
    excepcion: str | None = None,
) -> dict:
    """Crea un caso funcional o de error."""
    resultado = {
        "id": "caso",
        "entrada": entrada,
        "origen": origen,
        "categoria": "normal",
    }
    if excepcion is not None:
        resultado.update(excepcion=excepcion, categoria="error")
    else:
        resultado["valor_esperado"] = valor
    return resultado


def planificar(meta: dict, propuesta: list[dict]) -> tuple[list[dict], PlannerAgent]:
    """Planifica una función con un cliente enteramente local."""
    planner = PlannerAgent(ClienteGrabado(propuesta), TokenTracker(), es_simulado=True)
    return planner.planificar(modulo(meta)), planner


def test_analizador_conserva_funcion_sin_docstring(tmp_path) -> None:
    (tmp_path / "ejemplo.py").write_text(
        "def constante() -> None:\n    return None\n", encoding="utf-8"
    )

    [meta] = analizar_proyecto(tmp_path)["modulos"][0]["funciones"]

    assert meta["nombre"] == "constante"
    assert meta["docstring"] is None
    assert meta["retorno"] == "None"


def test_funcion_documentada_conserva_su_contrato() -> None:
    meta = funcion(
        docstring="Devuelve el doble de x.", firma="(x: int) -> int", retorno="int"
    )
    prueba = caso(entrada={"x": 2}, origen="docstring", valor=4)

    plan, _ = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert plan[0]["casos"] == [prueba]
    assert contracts.es_valido(contracts.PLANNER, plan[0])


def test_sin_docstring_permite_none_declarado_por_tipo() -> None:
    meta = funcion(firma="(x: int) -> None", retorno="None")
    prueba = caso(entrada={"x": 2}, origen="tipo", valor=None)

    plan, _ = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert plan[0]["casos"] == [prueba]


def test_origen_tipo_sin_anotacion_no_justifica_un_valor_concreto() -> None:
    meta = funcion(firma="(x)")
    prueba = caso(entrada={"x": 2}, origen="tipo", valor=999)

    plan, planner = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert plan == []
    assert "objetivo" in planner.omitidas
    assert any("tipo" in motivo for motivo in planner.descartados)


def test_sin_docstring_ni_tipos_admite_typeerror_deducible_de_firma() -> None:
    meta = funcion(firma="(x)")
    prueba = caso(entrada={}, origen="firma", excepcion="TypeError")

    plan, _ = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert plan[0]["casos"] == [prueba]


def test_firma_no_justifica_un_resultado_funcional_arbitrario() -> None:
    meta = funcion(firma="(x)")
    prueba = caso(entrada={"x": 2}, origen="firma", valor=4)

    plan, planner = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert plan == []
    assert "objetivo" in planner.omitidas


@pytest.mark.parametrize("device", [None, "cpu", "cuda"])
def test_regresion_get_siamese_model_no_acepta_docstring_inexistente(device) -> None:
    meta = funcion(nombre="get_siamese_model", firma="(device=None)")
    prueba = caso(entrada={"device": device}, origen="docstring", valor="modelo")
    prueba["id"] = f"device_{device or 'por_defecto'}"

    plan, planner = planificar(
        meta, [{"objetivo": "get_siamese_model", "casos": [prueba]}]
    )

    assert plan == []
    assert "get_siamese_model" in planner.omitidas
    assert "no tiene docstring" in planner.omitidas["get_siamese_model"].lower()
    assert any("docstring" in motivo for motivo in planner.descartados)


def test_caso_malformado_sigue_siendo_error_del_planner() -> None:
    propuesta = [{"objetivo": "objetivo", "casos": [{"id": "incompleto"}]}]

    with pytest.raises(ErrorRespuestaPlanner, match="ningún contrato"):
        planificar(funcion(), propuesta)


def test_json_malformado_sigue_siendo_error_recuperable() -> None:
    planner = PlannerAgent(ClienteGrabado("{"), TokenTracker(), es_simulado=True)

    with pytest.raises(ErrorRespuestaPlanner, match="JSON válido"):
        planner.planificar(modulo(funcion()))


def test_objetivo_sin_oraculo_no_impide_otro_objetivo_valido() -> None:
    sin_oraculo = funcion(nombre="get_siamese_model", firma="(device=None)")
    verificable = funcion(nombre="limpiar_cache", firma="() -> None", retorno="None")
    propuesta = [
        {
            "objetivo": "get_siamese_model",
            "casos": [caso(entrada={}, origen="firma", valor="modelo")],
        },
        {
            "objetivo": "limpiar_cache",
            "casos": [caso(entrada={}, origen="tipo", valor=None)],
        },
    ]
    planner = PlannerAgent(ClienteGrabado(propuesta), TokenTracker(), es_simulado=True)

    plan = planner.planificar(modulo(sin_oraculo, verificable))

    assert [contrato["objetivo"] for contrato in plan] == ["limpiar_cache"]
    assert list(planner.omitidas) == ["get_siamese_model"]


def test_prompt_distingue_fuentes_y_prohibe_inventar_oraculos() -> None:
    cliente = ClienteGrabado([])
    planner = PlannerAgent(cliente, TokenTracker(), es_simulado=True)

    planner.planificar(modulo(funcion(firma="(x: int) -> None", retorno="None")))

    prompt = cliente.prompts[0]
    assert "sin docstring" in prompt.lower()
    assert "no inventes" in prompt.lower()
    assert "TypeError" in prompt
    assert "-> None" in prompt


def test_literal_unico_sin_docstring_respalda_valor_exacto() -> None:
    meta = funcion(firma="() -> Literal['ok']", retorno="Literal['ok']")
    prueba = caso(entrada={}, origen="tipo", valor="ok")

    plan, _ = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert plan[0]["casos"] == [prueba]


def test_literal_unico_rechaza_un_valor_distinto() -> None:
    meta = funcion(firma="() -> Literal['ok']", retorno="Literal['ok']")
    prueba = caso(entrada={}, origen="tipo", valor="otro")

    plan, planner = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert plan == []
    assert "objetivo" in planner.omitidas


def test_none_declarado_rechaza_un_valor_inventado() -> None:
    meta = funcion(firma="() -> None", retorno="None")
    prueba = caso(entrada={}, origen="tipo", valor="resultado")

    plan, _ = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert plan == []


def test_humo_no_disfraza_un_error_de_firma_como_caso_funcional() -> None:
    meta = funcion(firma="(x)")
    prueba = caso(entrada={}, origen="firma", excepcion="TypeError")
    planner = PlannerAgent(
        ClienteGrabado([{"objetivo": "objetivo", "casos": [prueba]}]),
        TokenTracker(),
        es_simulado=True,
        perfil="humo",
    )

    assert planner.planificar(modulo(meta)) == []
    assert "objetivo" in planner.omitidas


def test_contrato_sin_docstring_es_compatible_con_generator_y_reviewer() -> None:
    meta = funcion(nombre="limpiar_cache", firma="() -> None", retorno="None")
    prueba = caso(entrada={}, origen="tipo", valor=None)
    prueba["id"] = "limpia"
    [contrato], _ = planificar(meta, [{"objetivo": "limpiar_cache", "casos": [prueba]}])
    codigo = (
        "from app.utils.siamese_loader import limpiar_cache\n\n"
        "def test_limpia():\n"
        "    assert limpiar_cache() is None\n"
    )
    generado = GeneratorAgent(
        ClienteGrabado(codigo), TokenTracker(), es_simulado=True
    ).generar(contrato, 1, None)

    assert contracts.es_valido(contracts.GENERATED_TEST, generado)
    assert ReviewerAgent._validar_oraculo(contrato, generado["codigo"]) is None


def test_assertion_laundering_sigue_detectando_asercion_debilitada() -> None:
    fuerte = "def test_modelo():\n    assert obtener_modelo() == 'modelo-esperado'\n"
    debil = "def test_modelo():\n    assert obtener_modelo() is not None\n"

    comparacion = comparar_aserciones(fuerte, debil)

    assert comparacion.es_laundering is True
    assert any(
        "Rigor debilitado" in diferencia.motivo
        for diferencia in comparacion.diferencias
    )


def test_contrato_historico_documentado_sigue_siendo_valido() -> None:
    meta = funcion(docstring="Devuelve x.", firma="(x: int) -> int", retorno="int")
    prueba = caso(entrada={"x": 1}, origen="docstring", valor=1)
    [contrato], _ = planificar(meta, [{"objetivo": "objetivo", "casos": [prueba]}])

    assert contracts.validar(contracts.PLANNER, contrato) is contrato

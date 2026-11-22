"""Normalización formal Spring, colisiones y aislamiento; sin ejecutar Java (#302)."""

import json
from copy import deepcopy

import pytest

from qagent.agents.planner import ErrorRespuestaPlanner, PlannerAgent
from qagent.lenguajes import JavaAdapter, adaptador_para
from qagent.llm import RespuestaLLM, TokenTracker
from tests.agents.test_planner_spring import _caso, _modulo, _planner

FUENTE = """@RestController class Api {
  @PostMapping("/api/items") @ResponseStatus(HttpStatus.CREATED)
  public String crear() { return "no deducir esperado del cuerpo"; }
  @PostMapping("/otro") @ResponseStatus(HttpStatus.CREATED)
  public String otro() { return null; }
}"""


class ClienteJSON:
    """Devuelve una respuesta grabada literal con cero tokens y sin API."""

    def __init__(self, contenido):
        self.contenido = contenido

    def generar(self, prompt, rol="planner"):
        assert rol == "planner"
        return RespuestaLLM(self.contenido, 0, 0, 0, "grabado-302")


def planificar(modulo, propuesta, *, perfil="std"):
    planner = PlannerAgent(
        ClienteJSON(json.dumps(propuesta)),
        TokenTracker(),
        es_simulado=True,
        adaptador=JavaAdapter(),
        perfil=perfil,
    )
    return planner, planner.planificar_endpoints(modulo)


@pytest.mark.parametrize(
    "identificador,normalizado",
    [
        ("declarado", "declarado"),
        ("CrearPago_Normal", "crearpago_normal"),
        ("Crear Pago-Normal", "crear_pago_normal"),
        ("Pago...OK", "pago_ok"),
    ],
)
def test_mismo_post_created_normaliza_solo_id(tmp_path, identificador, normalizado):
    modulo = _modulo(tmp_path, FUENTE)
    caso = {**_caso(headers={"X-Dato": "Valor Exacto"}), "id": identificador}
    original = deepcopy(caso)
    planner = _planner([caso])
    [contrato] = planner.planificar_endpoints(modulo)
    assert contrato["casos"] == [{**original, "id": normalizado}]
    assert caso == original
    assert contrato["lenguaje"] == "java" and contrato["framework_app"] == "spring"
    assert contrato["casos"][0]["valor_esperado"] == {"status_code": 201}
    assert planner.tracker.total_tokens == 0


def test_preparacion_no_toca_entradas_esperado_excepcion_ni_procedencia():
    caso = {
        "id": "CrearPago_Normal",
        "entrada": {"json": {"Monto": 3.75}, "headers": {"X": "Ñ"}},
        "valor_esperado": {"status_code": 201, "json": {"Pago": [1, None]}},
        "excepcion": {"tipo": "Declarada"},
        "origen": "status_code",
        "categoria": "normal",
    }
    original = deepcopy(caso)
    reparado = JavaAdapter().preparar_caso_endpoint({}, caso)
    assert reparado == {**original, "id": "crearpago_normal"}
    assert caso == original


@pytest.mark.parametrize("lenguaje", ["python", "javascript", "typescript"])
def test_otros_adaptadores_no_reciben_normalizacion_java(lenguaje):
    original = {"id": "CrearPago_Normal", "entrada": {"dato": [1, 2]}}
    assert adaptador_para(lenguaje).preparar_caso_endpoint({}, original) == original


def test_colisiones_no_eliminan_casos_independientes_y_no_mutan_propuesta(tmp_path):
    modulo = _modulo(tmp_path, FUENTE)
    casos = [
        {**_caso(), "id": "CrearPago-Normal"},
        {**_caso(headers={"X-Entrada": "diferente"}), "id": "crearpago_normal"},
        {**_caso(), "id": "Otro_Valido"},
    ]
    original = deepcopy(casos)
    planner, [contrato] = planificar(
        modulo, [{"objetivo": "POST /api/items", "casos": casos}]
    )
    assert [c["id"] for c in contrato["casos"]] == ["crearpago_normal", "otro_valido"]
    assert contrato["casos"][0] == {**original[0], "id": "crearpago_normal"}
    assert any(
        "caso 2" in d and "ID repetido después de normalizar" in d
        for d in planner.descartados
    )
    assert casos == original


@pytest.mark.parametrize("id_invalido", [None, 7, [], {}, ""])
def test_id_invalido_no_se_inventa_y_conserva_caso_sano(tmp_path, id_invalido):
    modulo = _modulo(tmp_path, FUENTE)
    casos = [{**_caso(), "id": id_invalido}, {**_caso(), "id": "Sano"}]
    planner, [contrato] = planificar(
        modulo, [{"objetivo": "POST /api/items", "casos": casos}]
    )
    assert [c["id"] for c in contrato["casos"]] == ["sano"]
    assert planner.descartados


def test_invalido_anterior_no_reserva_id_normalizado(tmp_path):
    modulo = _modulo(tmp_path, FUENTE)
    malo = {
        **_caso(),
        "id": "CrearPago_Normal",
        "valor_esperado": {"status_code": "201"},
    }
    bueno = {**_caso(), "id": "crearpago_normal"}
    planner, [contrato] = planificar(
        modulo, [{"objetivo": "POST /api/items", "casos": [malo, bueno]}]
    )
    assert contrato["casos"] == [bueno]
    assert not any("ID repetido" in d for d in planner.descartados)


@pytest.mark.parametrize(
    "malo",
    [None, [], {"id": "Invalido"}, {**_caso(), "valor_esperado": {"status_code": 200}}],
)
def test_un_endpoint_invalido_no_descarta_otro_contrato(tmp_path, malo):
    modulo = _modulo(tmp_path, FUENTE)
    propuesta = [
        {"objetivo": "POST /api/items", "casos": [malo]},
        {
            "objetivo": "POST /otro",
            "casos": [{**_caso(ruta="/otro"), "id": "CrearPago_Normal"}],
        },
    ]
    original = deepcopy(propuesta)
    planner, plan = planificar(modulo, propuesta)
    assert [c["objetivo"] for c in plan] == ["POST /otro"]
    assert plan[0]["casos"][0]["valor_esperado"] == {"status_code": 201}
    assert propuesta == original and planner.descartados


@pytest.mark.parametrize("objetivo", [[], {}, None, 9])
def test_objetivo_mal_formado_no_tumba_endpoints_validos(tmp_path, objetivo):
    modulo = _modulo(tmp_path, FUENTE)
    planner, plan = planificar(
        modulo,
        [
            {"objetivo": objetivo, "casos": [_caso()]},
            {"objetivo": "POST /api/items", "casos": [_caso()]},
        ],
    )
    assert len(plan) == 1 and planner.descartados


def test_ids_iguales_en_endpoints_diferentes_no_colisionan(tmp_path):
    modulo = _modulo(tmp_path, FUENTE)
    _, plan = planificar(
        modulo,
        [
            {"objetivo": "POST /api/items", "casos": [{**_caso(), "id": "Igual"}]},
            {
                "objetivo": "POST /otro",
                "casos": [{**_caso(ruta="/otro"), "id": "igual"}],
            },
        ],
    )
    assert len(plan) == 2
    assert all(c["casos"][0]["id"] == "igual" for c in plan)


def test_humo_no_convierte_binding_400_en_exito_201(tmp_path):
    modulo = _modulo(
        tmp_path,
        """@RestController class Api {
      @PostMapping("/api/items") @ResponseStatus(HttpStatus.CREATED)
      public String crear(@RequestParam int cantidad) { return null; }
    }""",
    )
    error = {**_caso(400, "tipo"), "id": "CrearPago_Error", "categoria": "error"}
    original = deepcopy(error)
    propuesta = [{"objetivo": "POST /api/items", "casos": [error]}]
    with pytest.raises(ErrorRespuestaPlanner, match="respuesta exitosa declarada"):
        planificar(modulo, propuesta, perfil="humo")
    assert error == original
    _, [contrato] = planificar(modulo, propuesta, perfil="std")
    assert contrato["casos"] == [{**original, "id": "crearpago_error"}]


def test_humo_recupera_normal_despues_de_error_con_id_reparado(tmp_path):
    modulo = _modulo(
        tmp_path,
        """@RestController class Api {
      @PostMapping("/api/items") @ResponseStatus(HttpStatus.CREATED)
      public String crear(@RequestParam int cantidad) { return null; }
    }""",
    )
    casos = [
        {**_caso(400, "tipo"), "id": "Error", "categoria": "error"},
        {**_caso(query={"cantidad": 2}), "id": "CrearPago_Normal"},
    ]
    _, [contrato] = planificar(
        modulo, [{"objetivo": "POST /api/items", "casos": casos}], perfil="humo"
    )
    assert contrato["casos"] == [{**casos[1], "id": "crearpago_normal"}]


def test_json_ilegible_y_oraculo_ausente_siguen_distinguidos(tmp_path):
    modulo = _modulo(tmp_path, FUENTE)
    planner = PlannerAgent(
        ClienteJSON('{"dato":'), TokenTracker(), adaptador=JavaAdapter()
    )
    with pytest.raises(ErrorRespuestaPlanner, match="JSON válido"):
        planner.planificar_endpoints(modulo)
    (tmp_path / "Api.java").unlink()
    modulo = _modulo(
        tmp_path,
        '@RestController class Api { @PostMapping("/api/items") public Object crear() { return null; } }',
    )
    planner = _planner([_caso(200)])
    assert planner.planificar_endpoints(modulo) == []
    assert "sin resultado esperado verificable" in planner.omitidas["POST /api/items"]
    assert planner.tracker.llamadas == []

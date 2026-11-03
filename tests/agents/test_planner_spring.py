"""Planner Spring con adaptador, parser y contratos reales; IA grabada (#183)."""

from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.planner import ErrorRespuestaPlanner, PlannerAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import FakeLLMClient, TokenTracker

_IMPORTS = """package ejemplo;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
"""


def _modulo(tmp_path: Path, fuente: str) -> dict:
    """Analiza la fuente sin compilarla y devuelve el módulo para el Planner."""
    (tmp_path / "Api.java").write_text(_IMPORTS + fuente, encoding="utf-8")
    estructura = JavaAdapter().analizar(tmp_path)
    assert estructura["errores"] == []
    return estructura["modulos"][0]


def _caso(estado: int = 201, origen: str = "status_code", **entrada) -> dict:
    """Construye una propuesta de IA fija; el filtro debe contrastarla con la fuente."""
    return {
        "id": "declarado",
        "entrada": {"metodo": "POST", "ruta": "/api/items", **entrada},
        "valor_esperado": {"status_code": estado},
        "origen": origen,
        "categoria": "normal",
    }


def _planner(casos: list[dict]) -> PlannerAgent:
    """Usa los tres componentes productivos de planificación y un cliente sin red."""
    return PlannerAgent(
        FakeLLMClient(grabaciones={"Api.java::POST /api/items": casos}),
        TokenTracker(),
        es_simulado=True,
        adaptador=JavaAdapter(),
    )


def test_contrato_spring_v3_de_estado_declarado(tmp_path: Path) -> None:
    """El estado sale de ResponseStatus aunque el cuerpo arroje un error."""
    modulo = _modulo(
        tmp_path,
        """@RestController @RequestMapping("/api") class Api {
      @PostMapping("/items") @ResponseStatus(HttpStatus.CREATED)
      public String crear() { throw new Error("IMPLEMENTACION_SECRETA"); }
    }""",
    )
    planner = _planner([_caso()])
    [contrato] = planner.planificar_endpoints(modulo)
    contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)
    assert (
        contrato["version"],
        contrato["lenguaje"],
        contrato["framework_app"],
        contrato["framework_pruebas"],
    ) == ("3", "java", "spring", "junit5")
    assert (contrato["manejador"], contrato["aplicacion"]) == ("Api.crear", "Api")
    assert contrato["casos"][0]["valor_esperado"] == {"status_code": 201}
    assert all(
        l.costo_usd == l.tokens_entrada == l.tokens_salida == 0
        for l in planner.tracker.llamadas
    )
    assert modulo["funciones"] == []


@pytest.mark.parametrize("retorno", ["String", "Object", "ResponseEntity<String>"])
def test_sin_declaracion_no_pide_ia_ni_inventa_200(
    tmp_path: Path, retorno: str
) -> None:
    """Ni el valor retornado ni la propuesta de IA suplen una declaración ausente."""
    modulo = _modulo(
        tmp_path,
        f"""@RestController class Api {{
      @PostMapping("/api/items") public {retorno} crear() {{ return null; }}
    }}""",
    )
    planner = _planner([_caso(200)])
    assert planner.planificar_endpoints(modulo) == []
    assert "sin resultado esperado verificable" in planner.omitidas["POST /api/items"]
    assert planner.tracker.llamadas == []


@pytest.mark.parametrize(
    "cambio", ["estado", "json", "ruta", "verbo", "origen", "preparacion"]
)
def test_rechaza_oraculos_o_peticion_inventados(tmp_path: Path, cambio: str) -> None:
    """No acepta JSON concreto, estados, rutas ni preparaciones sin declaración."""
    modulo = _modulo(
        tmp_path,
        """@RestController class Api {
      @PostMapping("/api/items") @ResponseStatus(HttpStatus.CREATED)
      public String crear() { return "el cuerpo no es el oraculo"; }
    }""",
    )
    caso = _caso()
    if cambio == "estado":
        caso["valor_esperado"]["status_code"] = 200
    elif cambio == "json":
        caso["valor_esperado"]["json"] = {"valor": 1}
    elif cambio == "ruta":
        caso["entrada"]["ruta"] = "/otra"
    elif cambio == "verbo":
        caso["entrada"]["metodo"] = "GET"
    elif cambio == "origen":
        caso["origen"] = "docstring"
    else:
        caso["entrada"]["preparacion"] = [
            {
                "dependencia": "servicio",
                "metodo": "crear",
                "modelo": "Item",
                "argumentos": {},
            }
        ]
    with pytest.raises(ErrorRespuestaPlanner):
        _planner([caso]).planificar_endpoints(modulo)


def test_ausencia_de_query_requerida_respalda_400(tmp_path: Path) -> None:
    """RequestParam requerido respalda un 400 de binding, no un éxito inventado."""
    modulo = _modulo(
        tmp_path,
        """@RestController class Api {
      @PostMapping("/api/items") public String crear(@RequestParam int cantidad) {return null;}
    }""",
    )
    caso = _caso(400, "tipo")
    caso["categoria"] = "error"
    [contrato] = _planner([caso]).planificar_endpoints(modulo)
    assert contrato["casos"][0]["valor_esperado"] == {"status_code": 400}


def test_query_opcional_no_respalda_error_400(tmp_path: Path) -> None:
    """required=false y defaultValue impiden inventar un error por omisión."""
    modulo = _modulo(
        tmp_path,
        """@RestController class Api {
      @PostMapping("/api/items") public String crear(@RequestParam(defaultValue="1") int cantidad) {return null;}
    }""",
    )
    planner = _planner([_caso(400, "tipo")])
    assert planner.planificar_endpoints(modulo) == []
    assert "sin resultado esperado verificable" in planner.omitidas["POST /api/items"]


def test_prompt_no_envia_implementacion_ni_notas(tmp_path: Path) -> None:
    """El prompt solo incluye declaraciones y no usa el código fuente recibido."""
    modulo = _modulo(
        tmp_path,
        """@RestController class Api {
      /** @implNote SECRETO_DOC */
      @PostMapping("/api/items") @ResponseStatus(HttpStatus.CREATED)
      public String crear() {return "SECRETO_CUERPO";}
    }""",
    )
    e = modulo["endpoints"][0]
    prompt = (
        JavaAdapter()
        .reglas_planificacion()
        .prompt_endpoints(modulo, {e["objetivo"]: e}, "SECRETO_FUENTE", False)
    )
    assert "201" in prompt and "MockMvc" in prompt
    assert all(
        s not in prompt for s in ("SECRETO_DOC", "SECRETO_CUERPO", "SECRETO_FUENTE")
    )


def test_objetivos_http_sin_duplicar_invocacion_directa(tmp_path: Path) -> None:
    """Vista previa y Planner conservan la identidad HTTP del controlador."""
    _modulo(
        tmp_path,
        """@RestController class Api {
      @PostMapping("/api/items") @ResponseStatus(HttpStatus.CREATED)
      public String crear() {return null;}
    }""",
    )
    objetivos = JavaAdapter().objetivos(JavaAdapter().analizar(tmp_path))
    assert [(o["tipo"], o["objetivo"]) for o in objetivos] == [
        ("endpoint", "POST /api/items")
    ]


def test_controladores_del_mismo_modulo_conservan_su_clase(tmp_path: Path) -> None:
    """Cada contrato usa su propio controlador para el futuro WebMvcTest."""
    modulo = _modulo(
        tmp_path,
        """
      @RestController class Api { @PostMapping("/api/items") @ResponseStatus(HttpStatus.CREATED) public String crear(){return null;} }
      @RestController class Otra { @PostMapping("/otro") @ResponseStatus(HttpStatus.CREATED) public String crear(){return null;} }
    """,
    )
    planner = PlannerAgent(
        FakeLLMClient(
            grabaciones={
                "Api.java::POST /api/items": [_caso()],
                "Api.java::POST /otro": [_caso(ruta="/otro")],
            }
        ),
        TokenTracker(),
        es_simulado=True,
        adaptador=JavaAdapter(),
    )
    plan = planner.planificar_endpoints(modulo)
    assert [(c["objetivo"], c["aplicacion"]) for c in plan] == [
        ("POST /api/items", "Api"),
        ("POST /otro", "Otra"),
    ]


@pytest.mark.parametrize(
    "parametro,entrada",
    [
        (
            '@RequestParam("cantidad") int cantidad',
            {"query": {"cantidad": "no_numero"}},
        ),
        ('@RequestParam("cantidad") int cantidad', {"query": {"cantidad": 2147483648}}),
        (
            '@RequestParam("cantidad") boolean cantidad',
            {"query": {"cantidad": "talvez"}},
        ),
    ],
)
def test_no_planifica_exito_con_parametro_incompatible(
    tmp_path: Path, parametro: str, entrada: dict
) -> None:
    """Una petición que falla en el binding no sirve para probar un éxito declarado."""
    modulo = _modulo(
        tmp_path,
        f"""@RestController class Api {{
      @PostMapping("/api/items") @ResponseStatus(HttpStatus.CREATED)
      public String crear({parametro}) {{ return null; }}
    }}""",
    )
    with pytest.raises(ErrorRespuestaPlanner):
        _planner([_caso(**entrada)]).planificar_endpoints(modulo)


def test_orquestador_registra_omision_sin_generar_ni_ejecutar(tmp_path: Path) -> None:
    """El flujo productivo conserva el motivo; un endpoint sin oráculo no se ejecuta."""
    from qagent.orchestrator.orquestador import Orquestador

    class NoDebeLlamarse:
        """Centinela para fallar ante cualquier intento de generar o revisar."""

        def __getattr__(self, nombre: str):
            raise AssertionError(f"No se debe llamar al agente: {nombre}")

    modulo = _modulo(
        tmp_path,
        """@RestController class Api {
      @PostMapping("/api/items") public Object crear() {throw new Error();}
    }""",
    )
    planner = _planner([_caso(200)])
    resultado = Orquestador(planner, NoDebeLlamarse(), NoDebeLlamarse()).ejecutar(
        modulo
    )
    assert resultado.motivo_fallo is None
    assert resultado.objetivos == []
    assert len(resultado.omitidos) == 1
    assert resultado.omitidos[0]["tipo"] == "endpoint"
    assert resultado.omitidos[0]["objetivo"] == "POST /api/items"
    assert "sin resultado esperado verificable" in resultado.omitidos[0]["motivo"]
    assert planner.tracker.llamadas == []

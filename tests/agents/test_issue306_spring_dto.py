"""DTO con Bean Validation en endpoints Spring (#306, ADR-024), sin Docker ni red.

Usa el parser, el adaptador, el Planner y la validación de contratos productivos; solo
la respuesta de IA está grabada. Los esperados salen de las restricciones declaradas
en el DTO, nunca del cuerpo del controlador.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.planner import PlannerAgent
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_spring_validacion import violaciones
from qagent.llm import FakeLLMClient, TokenTracker

POM_VALIDACION = """<project><modelVersion>4.0.0</modelVersion>
<groupId>demo</groupId><artifactId>demo</artifactId><version>1</version>
<dependencies><dependency><groupId>org.springframework.boot</groupId>
<artifactId>spring-boot-starter-validation</artifactId></dependency></dependencies>
</project>"""
POM_SIN_VALIDACION = POM_VALIDACION.replace(
    "spring-boot-starter-validation", "spring-boot-starter-web"
)
CONTROLADOR = """package demo;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api") public class Pedidos {
  @PostMapping("/pedidos") @ResponseStatus(HttpStatus.CREATED)
  public void crear(@Valid @RequestBody PedidoDto pedido) { throw new IllegalStateException("IMPLEMENTACION"); }
  @PostMapping("/libre") @ResponseStatus(HttpStatus.CREATED)
  public void libre(@RequestBody PedidoDto pedido) { }
}
"""
DTO = """package demo;
import jakarta.validation.constraints.*;
public record PedidoDto(
  @NotBlank String cliente,
  @Min(1) @Max(10) int cantidad,
  @Size(max = 5) String nota) {}
"""
VALIDO = {"cliente": "Ana", "cantidad": 2, "nota": "ok"}


def _proyecto(
    tmp_path: Path, dto: str = DTO, pom: str = POM_VALIDACION, **extra
) -> dict:
    archivos = {
        "pom.xml": pom,
        "src/main/java/demo/Pedidos.java": CONTROLADOR,
        "src/main/java/demo/PedidoDto.java": dto,
        **extra,
    }
    for nombre, texto in archivos.items():
        ruta = tmp_path / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
    estructura = JavaAdapter().analizar(tmp_path)
    assert estructura["errores"] == []
    return next(m for m in estructura["modulos"] if m["ruta"].endswith("Pedidos.java"))


def _endpoint(modulo: dict, objetivo: str = "POST /api/pedidos") -> dict:
    return next(e for e in modulo["endpoints"] if e["objetivo"] == objetivo)


def _normal(json: dict | None = None) -> dict:
    return {
        "id": "valido",
        "entrada": {"metodo": "POST", "ruta": "/api/pedidos", "json": json or VALIDO},
        "valor_esperado": {"status_code": 201},
        "origen": "status_code",
        "categoria": "normal",
    }


def _violacion(json: dict, evidencia: list[str], estado: int = 400, **otros) -> dict:
    return {
        "id": "violacion",
        "entrada": {"metodo": "POST", "ruta": "/api/pedidos", "json": json},
        "valor_esperado": {"status_code": estado},
        "origen": "bean_validation",
        "evidencia": evidencia,
        "categoria": "error",
        **otros,
    }


class _ClienteConRegistro(FakeLLMClient):
    """IA grabada que guarda los prompts para revisar qué se le envió."""

    def __init__(self, grabaciones: dict) -> None:
        super().__init__(grabaciones=grabaciones)
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator"):
        self.prompts.append(prompt)
        return super().generar(prompt, rol)


def _planner(casos: list[dict], objetivo: str = "POST /api/pedidos") -> PlannerAgent:
    return PlannerAgent(
        _ClienteConRegistro({f"Pedidos.java::{objetivo}": casos}),
        TokenTracker(),
        es_simulado=True,
        adaptador=JavaAdapter(),
    )


def test_lee_el_dto_de_otro_archivo_sin_su_implementacion(tmp_path: Path) -> None:
    """Campos, tipos y restricciones salen del record declarado en el proyecto."""
    validacion = _endpoint(_proyecto(tmp_path))["validacion"]
    assert validacion["motivo"] is None
    assert validacion["campos"] == [
        {
            "nombre": "cliente",
            "tipo": "String",
            "restricciones": [{"tipo": "NotBlank"}],
        },
        {
            "nombre": "cantidad",
            "tipo": "int",
            "restricciones": [
                {"tipo": "Min", "value": 1},
                {"tipo": "Max", "value": 10},
            ],
        },
        {
            "nombre": "nota",
            "tipo": "String",
            "restricciones": [{"tipo": "Size", "max": 5}],
        },
    ]


def test_sin_valid_no_hay_validacion(tmp_path: Path) -> None:
    """Sin @Valid/@Validated Spring no valida el DTO: no se representan violaciones."""
    assert "validacion" not in _endpoint(_proyecto(tmp_path), "POST /api/libre")


def test_planifica_valido_y_violaciones_con_procedencia(tmp_path: Path) -> None:
    """Cada 400 cita la única restricción incumplida; el válido usa @ResponseStatus."""
    modulo = _proyecto(tmp_path)
    casos = [
        _normal(),
        {
            **_violacion({**VALIDO, "cliente": "  "}, ["PedidoDto.cliente@NotBlank"]),
            "id": "sin_cliente",
        },
        {
            **_violacion({**VALIDO, "cantidad": 11}, ["PedidoDto.cantidad@Max"]),
            "id": "cantidad_alta",
        },
        {
            **_violacion({**VALIDO, "cantidad": 0}, ["PedidoDto.cantidad@Min"]),
            "id": "cantidad_baja",
        },
        {
            **_violacion({**VALIDO, "nota": "seis!!"}, ["PedidoDto.nota@Size"]),
            "id": "nota_larga",
        },
    ]
    planner = _planner(casos)
    [contrato] = planner.planificar_endpoints(modulo)
    contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)
    assert [c["id"] for c in contrato["casos"]] == [
        "valido",
        "sin_cliente",
        "cantidad_alta",
        "cantidad_baja",
        "nota_larga",
    ]
    errores = [c for c in contrato["casos"] if c["origen"] == "bean_validation"]
    assert all(c["valor_esperado"] == {"status_code": 400} for c in errores)
    assert errores[0]["evidencia"] == ["PedidoDto.cliente@NotBlank"]
    # El prompt lleva las restricciones declaradas, nunca el cuerpo del controlador.
    [prompt] = planner.cliente.prompts
    assert '"validacion"' in prompt and "PedidoDto" in prompt and "Max" in prompt
    assert "IMPLEMENTACION" not in prompt


@pytest.mark.parametrize(
    "caso,motivo",
    [
        (
            _violacion({**VALIDO, "cantidad": 11}, ["PedidoDto.cantidad@Min"]),
            "evidencia",
        ),
        (
            _violacion(
                {**VALIDO, "cantidad": 11, "cliente": ""}, ["PedidoDto.cantidad@Max"]
            ),
            "exactamente una",
        ),
        (_violacion(VALIDO, ["PedidoDto.cantidad@Max"]), "exactamente una"),
        (
            _violacion({**VALIDO, "cantidad": 11}, ["PedidoDto.cantidad@Max"], 422),
            "solo respalda un 400",
        ),
        (
            _violacion({**VALIDO, "extra": 1}, ["PedidoDto.cantidad@Max"]),
            "exactamente los campos",
        ),
        (
            _violacion({**VALIDO, "cantidad": "2"}, ["PedidoDto.cantidad@Max"]),
            "no es compatible",
        ),
        (_normal({**VALIDO, "cantidad": 11}), "solo respalda un 400"),
        (_normal({"cliente": "Ana"}), "exactamente los campos"),
    ],
)
def test_rechaza_violaciones_inventadas_o_ambiguas(
    tmp_path: Path, caso: dict, motivo: str
) -> None:
    """Evidencia falsa, varias violaciones, estados o cuerpos sin respaldo se rechazan."""
    modulo = _proyecto(tmp_path)
    planner = _planner([{**_normal(), "id": "control"}, {**caso, "id": "propuesto"}])
    [contrato] = planner.planificar_endpoints(modulo)
    assert [c["id"] for c in contrato["casos"]] == ["control"]
    [descartado] = planner.descartados
    assert "propuesto" in descartado and motivo in descartado, descartado


@pytest.mark.parametrize(
    "cambio,motivo",
    [
        ({"pom": POM_SIN_VALIDACION}, "hibernate-validator"),
        (
            {"dto": DTO.replace("@NotBlank String", '@Pattern(regexp = "a") String')},
            "aún no admitida",
        ),
        (
            {
                "dto": DTO.replace(
                    "@NotBlank String", "@NotBlank(groups = A.class) String"
                )
            },
            "groups",
        ),
        (
            {
                "dto": DTO.replace(
                    "@NotBlank String cliente",
                    '@NotBlank @com.fasterxml.jackson.annotation.JsonProperty("c") String cliente',
                )
            },
            "no es una restricción admitida",
        ),
        (
            {
                "dto": DTO.replace(
                    "String nota", "java.util.List<String> nota"
                ).replace("@Size(max = 5) ", "")
            },
            "aún no representable",
        ),
        (
            {
                "src/main/java/demo/Errores.java": "package demo; import org.springframework.web.bind.annotation.*; @RestControllerAdvice class Errores {}"
            },
            "@ControllerAdvice",
        ),
    ],
)
def test_configuracion_no_representable_no_planifica_violaciones(
    tmp_path: Path, cambio: dict, motivo: str
) -> None:
    """Sin proveedor, con consejo global o DTO complejo: motivo y ningún 400 de validación."""
    argumentos = {k: v for k, v in cambio.items() if k in ("dto", "pom")}
    extra = {k: v for k, v in cambio.items() if k not in ("dto", "pom")}
    modulo = _proyecto(tmp_path, **argumentos, **extra)
    validacion = _endpoint(modulo)["validacion"]
    assert validacion["campos"] is None and motivo in validacion["motivo"]
    planner = _planner(
        [_normal(), _violacion({**VALIDO, "cantidad": 11}, ["PedidoDto.cantidad@Max"])]
    )
    [contrato] = planner.planificar_endpoints(modulo)
    assert [c["origen"] for c in contrato["casos"]] == ["status_code"]


def test_exception_handler_del_controlador_bloquea_violaciones(tmp_path: Path) -> None:
    modulo_texto = CONTROLADOR.replace(
        '  @PostMapping("/libre")',
        '  @ExceptionHandler(IllegalStateException.class) public void manejar() {}\n  @PostMapping("/libre")',
    )
    ruta = tmp_path / "src/main/java/demo/Pedidos.java"
    _proyecto(tmp_path)
    ruta.write_text(modulo_texto, encoding="utf-8")
    estructura = JavaAdapter().analizar(tmp_path)
    modulo = next(
        m for m in estructura["modulos"] if m["ruta"].endswith("Pedidos.java")
    )
    assert "@ExceptionHandler" in _endpoint(modulo)["validacion"]["motivo"]


def test_contrato_exige_evidencia_con_bean_validation() -> None:
    """El schema v3 pide evidencia para bean_validation y la prohíbe en otros orígenes."""
    base = {
        "version": "3",
        "lenguaje": "java",
        "framework_pruebas": "junit5",
        "framework_app": "spring",
        "modulo": "src/main/java/demo/Pedidos.java",
        "tipo": "endpoint",
        "objetivo": "POST /api/pedidos",
        "manejador": "Pedidos.crear",
        "aplicacion": "Pedidos",
        "huella": "0" * 64,
        "firma": "public void crear(PedidoDto pedido)",
        "critical": False,
        "casos": [_violacion({**VALIDO, "cantidad": 11}, ["PedidoDto.cantidad@Max"])],
    }
    sin = {
        **base,
        "casos": [{k: v for k, v in base["casos"][0].items() if k != "evidencia"}],
    }
    con_en_otro = {**base, "casos": [{**_normal(), "evidencia": ["x"]}]}
    assert contracts.es_valido(contracts.PLANNER_V3, base), contracts.validar(
        contracts.PLANNER_V3, base
    )
    assert not contracts.es_valido(contracts.PLANNER_V3, sin)
    assert not contracts.es_valido(contracts.PLANNER_V3, con_en_otro)


@pytest.mark.parametrize(
    "valor,esperadas",
    [
        ({**VALIDO, "nota": None}, []),  # Size acepta null
        ({**VALIDO, "cliente": None}, ["PedidoDto.cliente@NotBlank"]),
        ({**VALIDO, "cliente": "\t\n "}, ["PedidoDto.cliente@NotBlank"]),
        ({**VALIDO, "nota": "😀😀😀"}, ["PedidoDto.nota@Size"]),  # 6 unidades UTF-16
        ({**VALIDO, "cantidad": True}, "no es compatible"),
        ({**VALIDO, "cantidad": None}, "no es compatible"),  # primitivo
    ],
)
def test_semantica_de_hibernate_validator(
    tmp_path: Path, valor: dict, esperadas
) -> None:
    validacion = _endpoint(_proyecto(tmp_path))["validacion"]
    resultado = violaciones(validacion, valor)
    if isinstance(esperadas, str):
        assert isinstance(resultado, str) and esperadas in resultado
    else:
        assert resultado == esperadas

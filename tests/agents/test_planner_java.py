"""Contratos Java del Planner compartido sobre AST real y respuestas de IA simuladas (#181)."""

from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.planner import PlannerAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import FakeLLMClient, TokenTracker


def _caso(entrada, esperado, origen="docstring", categoria="normal") -> dict:
    """Propuesta grabada: el esperado se declara en la fixture, no se ejecuta Java."""
    return {
        "id": "caso_normal",
        "entrada": entrada,
        "valor_esperado": esperado,
        "origen": origen,
        "categoria": categoria,
    }


def _planificar(tmp_path: Path, codigo: str, casos: list[dict], perfil=None):
    """Usa análisis Java y FakeLLMClient para probar los filtros del Planner real."""
    (tmp_path / "Banco.java").write_text(codigo, encoding="utf-8")
    estructura = JavaAdapter().analizar(tmp_path)
    assert estructura["errores"] == []
    [modulo] = estructura["modulos"]
    tracker = TokenTracker()
    cliente = FakeLLMClient(grabaciones={"Banco.java::Banco.f": casos})
    planner = PlannerAgent(
        cliente, tracker, es_simulado=True, adaptador=JavaAdapter(), perfil=perfil
    )
    plan = planner.planificar(modulo)
    assert all(
        llamada.tokens_entrada == llamada.tokens_salida == 0
        for llamada in tracker.llamadas
    )
    return planner, plan


def test_planifica_banco_ta01_con_oraculos_de_su_javadoc() -> None:
    """Los seis contratos usan Javadoc, incluso donde el cuerpo contiene un defecto."""
    banco = Path(__file__).resolve().parents[2] / "bench_java"
    estructura = JavaAdapter().analizar(banco)
    assert estructura["errores"] == []
    grabadas = {
        "BancoCorrecto.java::BancoCorrecto.sumarPrecios": [
            _caso({"precios": [10, 20]}, 30)
        ],
        "BancoCorrecto.java::BancoCorrecto.aplicarDescuento": [
            _caso({"precio": 100, "porcentaje": 20}, 80)
        ],
        "BancoCorrecto.java::BancoCorrecto.esMayorDeEdad": [_caso({"edad": 18}, True)],
        "BancoDefectuoso.java::BancoDefectuoso.calcularPromedio": [
            _caso({"numeros": [2, 3]}, 2.5)
        ],
        "BancoDefectuoso.java::BancoDefectuoso.calcularEnvio": [
            _caso({"importe": 100}, 0, categoria="limite")
        ],
        "BancoDefectuoso.java::BancoDefectuoso.calcularTotalConImpuesto": [
            _caso({"subtotal": 100, "porcentaje": 18}, 118)
        ],
    }
    tracker = TokenTracker()
    planner = PlannerAgent(
        FakeLLMClient(grabaciones=grabadas),
        tracker,
        es_simulado=True,
        adaptador=JavaAdapter(),
    )
    plan = [
        contrato
        for modulo in estructura["modulos"]
        for contrato in planner.planificar(modulo)
    ]
    assert len(plan) == 6
    por_nombre = {c["objetivo"]: c for c in plan}
    for contrato in plan:
        contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)
        assert contrato["version"] == "3"
        assert contrato["lenguaje"] == "java"
        assert contrato["framework_pruebas"] == "junit5"
    assert (
        por_nombre["BancoDefectuoso.calcularPromedio"]["casos"][0]["valor_esperado"]
        == 2.5
    )
    assert (
        por_nombre["BancoDefectuoso.calcularEnvio"]["casos"][0]["valor_esperado"] == 0
    )
    assert (
        por_nombre["BancoDefectuoso.calcularTotalConImpuesto"]["casos"][0][
            "valor_esperado"
        ]
        == 118
    )
    assert por_nombre["BancoCorrecto.sumarPrecios"]["critical"] is True
    assert len(tracker.llamadas) == 2
    assert all(
        l.tokens_entrada == l.tokens_salida == 0 and l.costo_usd == 0
        for l in tracker.llamadas
    )


def test_prompt_solo_envia_especificacion_funcional(tmp_path: Path) -> None:
    """Excluye cuerpos y notas de implementación que podrían revelar el defecto real."""
    (tmp_path / "Banco.java").write_text(
        """class Banco {
        /** Devuelve el doble.
         * @param x entrada
         * @return x multiplicado por dos
         * @implNote DEFECTO_SECRETO: devuelve siempre 99
         */
        public int f(int x) { return 99; }
    }""",
        encoding="utf-8",
    )
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    prompt = JavaAdapter().reglas_planificacion().prompt_funciones(modulo, False)
    assert "x multiplicado por dos" in prompt
    assert "DEFECTO_SECRETO" not in prompt
    assert "return 99" not in prompt
    assert "JUnit 5" in prompt
    assert "OBJETIVOS_JSON:" in prompt


@pytest.mark.parametrize(
    ("retorno", "esperado", "origen"),
    [
        ("int", 42, "tipo"),
        ("boolean", True, "tipo"),
        ("String", "texto", "tipo"),
        ("int", 1, "firma"),
        ("int", 1, "docstring"),
    ],
)
def test_sin_especificacion_no_inventa_resultado(
    tmp_path: Path, retorno: str, esperado, origen: str
) -> None:
    """Un tipo general o el cuerpo no son oráculos; queda omitido con motivo claro."""
    planner, plan = _planificar(
        tmp_path,
        f"class Banco {{ public {retorno} f(int x) {{ return valorOculto(); }} }}",
        [_caso({"x": 1}, esperado, origen)],
    )
    assert plan == []
    assert "resultado esperado verificable" in planner.omitidas["Banco.f"]


def test_javadoc_solo_de_parametros_no_inventa_resultado(tmp_path: Path) -> None:
    """Documentar cómo se recibe x no determina por sí solo qué devuelve f."""
    planner, plan = _planificar(
        tmp_path,
        "class Banco { /** @param x entero de entrada */ public int f(int x) {return x;} }",
        [_caso({"x": 1}, 1)],
    )
    assert plan == []
    assert "Banco.f" in planner.omitidas


@pytest.mark.parametrize(
    "entrada", [{}, {"otro": 2}, [1, 2], {"x": True}, {"x": 1.5}, {"x": 2**40}]
)
def test_invocacion_incompatible_no_se_planifica(tmp_path: Path, entrada) -> None:
    """Rechaza nombres, aridad y valores que no pueden representar el parámetro int."""
    planner, plan = _planificar(
        tmp_path,
        "class Banco { /** Devuelve el doble de x. */ public int f(int x) {return x*2;} }",
        [_caso(entrada, 4)],
    )
    assert plan == []
    assert "firma Java" in planner.omitidas["Banco.f"]


@pytest.mark.parametrize(
    ("retorno", "esperado"),
    [
        ("int", True),
        ("int", 1.5),
        ("int", 2**40),
        ("boolean", 1),
        ("String", 1),
        ("char", "dos"),
        ("char", "\U0001f600"),
        ("double", 2**2000),
        ("double", float("inf")),
        ("double", float("nan")),
        ("java.util.List<Integer>", [1, "dos"]),
        ("void", None),
    ],
)
def test_esperado_incompatible_no_se_planifica(
    tmp_path: Path, retorno: str, esperado
) -> None:
    """La procedencia Javadoc no permite contradecir el tipo de retorno declarado."""
    planner, plan = _planificar(
        tmp_path,
        f"class Banco {{ /** Devuelve el resultado documentado. */ public {retorno} f() {{ devolver(); }} }}",
        [_caso([], esperado)],
    )
    assert plan == []
    assert "Banco.f" in planner.omitidas
    assert any("incompatible" in d for d in planner.descartados)


@pytest.mark.parametrize(
    ("etiqueta", "aceptada"),
    [
        ("@throws IllegalArgumentException si x es negativo", True),
        ("@throws OtraException si x es negativo", False),
        ("@param x entrada", False),
    ],
)
def test_excepciones_deben_estar_documentadas(
    tmp_path: Path, etiqueta: str, aceptada: bool
) -> None:
    """Solo admite la excepción prevista en el Javadoc con sus condiciones."""
    codigo = "class Banco { /** " + etiqueta + " */ public void f(int x) {} }"
    caso = {
        "id": "negativo",
        "entrada": {"x": -1},
        "excepcion": "IllegalArgumentException",
        "origen": "docstring",
        "categoria": "error",
    }
    planner, plan = _planificar(tmp_path, codigo, [caso])
    assert bool(plan) is aceptada
    if not aceptada:
        assert "Banco.f" in planner.omitidas


def test_humo_conserva_solo_un_caso_normal(tmp_path: Path) -> None:
    """El perfil Humo del Planner común también limita los casos de Java."""
    casos = [_caso([2], 4), {**_caso([3], 6), "id": "otro"}]
    planner, plan = _planificar(
        tmp_path,
        "class Banco { /** Devuelve el doble. */ public int f(int x) {return x*2;} }",
        casos,
        "humo",
    )
    assert len(plan[0]["casos"]) == 1
    assert planner.avisos


def test_contrato_conserva_criticidad_y_mapa_del_analizador(tmp_path: Path) -> None:
    """Los metadatos del análisis llegan al contrato sin depender del modelo."""
    codigo = """class Banco {
        /** Devuelve uno cuando x es positivo y cero en otro caso. */
        public int f(int x) { if (x > 0) return auxiliar(); return 0; }
        public int auxiliar() {return 1;}
    }"""
    _, plan = _planificar(tmp_path, codigo, [_caso([1], 1)])
    assert plan[0]["critical"] is True
    assert plan[0]["llama_a"] == ["Banco.java::Banco.auxiliar"]


@pytest.mark.parametrize(
    ("entrada", "tipo", "esperado"),
    [
        ([1, 2, 3], "int...", 6),
        ({"xs": [1, 2, 3]}, "int...", 6),
        ({"xs": [1, 2, 3]}, "int[]", 6),
    ],
)
def test_entradas_arrays_y_varargs(
    tmp_path: Path, entrada, tipo: str, esperado
) -> None:
    """Arrays y varargs admiten la representación JSON acordada para el Planner."""
    _, plan = _planificar(
        tmp_path,
        f"class Banco {{ /** Devuelve la suma de xs. */ public int f({tipo} xs) {{return 0;}} }}",
        [_caso(entrada, esperado)],
    )
    assert len(plan) == 1


def test_endpoints_spring_no_reutilizan_prompts_fastapi() -> None:
    """#183 implementa Spring sin usar instrucciones Python/TestClient de FastAPI."""
    prompt = (
        JavaAdapter()
        .reglas_planificacion()
        .prompt_endpoints({"ruta": "Api.java"}, {}, None, False)
    )
    assert "Spring MVC" in prompt
    assert "JUnit 5" in prompt
    assert "MockMvc" in prompt
    assert "TestClient" not in prompt
    assert "FastAPI" not in prompt

"""Planner y Generator reales, IA grabada y JUnit offline para colecciones (#300)."""

from copy import deepcopy

import pytest
from docker.errors import NotFound

from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_colecciones import expresion_coleccion
from qagent.llm import FakeLLMClient, TokenTracker
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.sandbox.modelos import IMAGEN_JAVA, LimitesSandbox
from tests.agents.test_generator_java import ClienteJUnitGrabado
from tests.sandbox.test_issue305_construccion_docker import pom_de_fixture

pytestmark = pytest.mark.docker


def casos_set():
    """Oráculos declarados por la fixture, independientes de ejecutar la fuente."""
    return [
        {
            "id": f"caso_{i}",
            "entrada": {"caso": i},
            "valor_esperado": valor,
            "origen": "docstring",
            "categoria": "normal",
        }
        for i, valor in enumerate(
            [["uno", "dos"], ["uno", "dos"], [], None, ["uno", None]]
        )
    ]


def fuente_set(defecto=False):
    """La variante defectuosa pierde dos en el caso 1, contrario a su Javadoc."""
    segundo = 'Set.of("uno")' if defecto else 'Set.of("uno", "dos")'
    return """package ejemplo; import java.util.*; public class Banco {
      /** Para caso 0 y 1 devuelve el conjunto uno y dos, sin orden.
       * Para caso 2 devuelve vacío; caso 3 devuelve null;
       * caso 4 devuelve el conjunto uno y null.
       * @param caso selector 0 a 4
       * @return el conjunto declarado para el selector */
      public static Set<String> valores(int caso) {
        return switch(caso) {
          case 0 -> Set.of("dos", "uno"); case 1 -> SEGUNDO;
          case 2 -> Set.of(); case 3 -> null;
          default -> new HashSet<>(Arrays.asList("uno", null));
        };
      }
    }""".replace("SEGUNDO", segundo)


def codigo_de_casos(casos, tipo="Set<String>", argumentos=None):
    """JUnit grabado desde los datos del contrato; no obtiene valores de la fuente."""
    metodos = []
    for caso in casos:
        args = str(caso["entrada"]["caso"]) if argumentos is None else argumentos
        sujeto = f"Banco.valores({args})"
        esperado = caso["valor_esperado"]
        asercion = (
            f"assertNull({sujeto});"
            if esperado is None
            else f"assertEquals({expresion_coleccion(tipo, esperado)}, {sujeto});"
        )
        metodos.append(f"@Test void test_{caso['id']}() {{ {asercion} }}")
    return (
        "package ejemplo; import org.junit.jupiter.api.Test; "
        "import static org.junit.jupiter.api.Assertions.*; class BancoTest {"
        + "\n".join(metodos)
        + "}"
    )


def ejecutar_fixture(
    cliente_docker, tmp_path, monkeypatch, fuente, casos, codigo, fallos
):
    raiz = tmp_path / "proyecto"
    archivo = raiz / "src/main/java/ejemplo/Banco.java"
    archivo.parent.mkdir(parents=True)
    archivo.write_text(fuente, encoding="utf-8")
    pom_de_fixture(raiz)
    originales = {p: p.read_bytes() for p in raiz.rglob("*") if p.is_file()}
    adaptador = JavaAdapter()
    [modulo] = adaptador.analizar(raiz)["modulos"]
    copia = deepcopy(casos)
    tracker = TokenTracker()
    cliente = FakeLLMClient(grabaciones={"Banco.java::Banco.valores": casos})
    [contrato] = PlannerAgent(
        cliente, tracker, es_simulado=True, adaptador=adaptador
    ).planificar(modulo)
    assert contrato["casos"] == copia
    generado = GeneratorAgent(
        ClienteJUnitGrabado(codigo), tracker, es_simulado=True, ruta_proyecto=raiz
    ).generar(contrato, 1, None)
    assert adaptador.validar_oraculo(contrato, generado["codigo"], raiz) is None
    pruebas = tmp_path / "pruebas"
    destino = pruebas / generado["archivo"]
    destino.parent.mkdir(parents=True)
    destino.write_text(generado["codigo"], encoding="utf-8")
    creados = []
    coleccion = type(cliente_docker.containers)
    run = coleccion.run

    def registrar(self, *args, **kwargs):
        assert kwargs["network_mode"] == "none"
        assert kwargs["read_only"] and kwargs["cap_drop"] == ["ALL"]
        assert kwargs["security_opt"] == ["no-new-privileges"]
        contenedor = run(self, *args, **kwargs)
        creados.append(contenedor.id)
        return contenedor

    monkeypatch.setattr(coleccion, "run", registrar)
    resultado = ejecutar_comando_pruebas(
        IMAGEN_JAVA,
        adaptador.comando_pruebas(contrato["modulo"]),
        raiz,
        pruebas,
        leer_cobertura=adaptador.leer_cobertura,
        archivo_informe=adaptador.entorno_sandbox().informe,
        limites=LimitesSandbox(cpus=2, memoria="2g", timeout_s=120),
        cliente=cliente_docker,
        preparar=adaptador.preparador_sandbox(),
        leer_informe=adaptador.lector_informe_sandbox(),
    )
    informe = adaptador.interpretar_resultados(resultado.junit_xml or "")
    assert informe["total"] == len(casos), resultado.stdout
    assert informe["errores"] == informe["omitidos"] == 0, resultado.stdout
    assert informe["fallaron"] == fallos, resultado.stdout
    clasificacion = adaptador.clasificar_ejecucion(resultado)
    if fallos:
        assert clasificacion is not None and clasificacion.tipo == "fallo_asercion"
    else:
        assert resultado.exit_code == 0 and clasificacion is None, resultado.stdout
    assert creados
    for identificador in creados:
        with pytest.raises(NotFound):
            cliente_docker.containers.get(identificador)
    assert tracker.total_tokens == 0
    assert all(p.read_bytes() == contenido for p, contenido in originales.items())
    assert casos == copia
    print(
        f"#300: JUnit={informe['total']}; fallos={fallos}; red=none; originales y contratos intactos; 0 tokens"
    )


@pytest.mark.parametrize("defecto", [False, True], ids=["correcta", "defecto-real"])
def test_set_junit_conserva_contenido_null_y_vacios(
    cliente_docker, tmp_path, monkeypatch, defecto
):
    casos = casos_set()
    ejecutar_fixture(
        cliente_docker,
        tmp_path,
        monkeypatch,
        fuente_set(defecto),
        casos,
        codigo_de_casos(casos),
        int(defecto),
    )


def test_elementos_boxed_y_entradas_compilan_sin_conversiones_ambiguas(
    cliente_docker, tmp_path, monkeypatch
):
    tipos = [
        "Set<Byte>",
        "List<Short>",
        "Set<Long>",
        "List<Float>",
        "Set<Double>",
        "Set<Character>",
        "List<Boolean>",
    ]
    valores = [
        [-128, 127],
        [-32768, 32767],
        [1, 2**60],
        [1.5, 2.5],
        [0.1, 1.0],
        ["'", "\n", "\x00", "á"],
        [True, False],
    ]
    parametros = ", ".join(f"{tipo} p{i}" for i, tipo in enumerate(tipos))
    fuente = (
        "package ejemplo; import java.util.*; public class Banco { "
        "/** Devuelve el conjunto uno para las entradas declaradas. @return conjunto uno */ "
        f'public static Set<String> valores({parametros}) {{ return Set.of("uno"); }} }}'
    )
    casos = [
        {
            "id": "tipos",
            "entrada": {f"p{i}": valor for i, valor in enumerate(valores)},
            "valor_esperado": ["uno"],
            "origen": "docstring",
            "categoria": "normal",
        }
    ]
    args = ", ".join(expresion_coleccion(t, v) for t, v in zip(tipos, valores))
    ejecutar_fixture(
        cliente_docker,
        tmp_path,
        monkeypatch,
        fuente,
        casos,
        codigo_de_casos(casos, argumentos=args),
        0,
    )


def test_set_anidado_con_igualdad_de_valor(cliente_docker, tmp_path, monkeypatch):
    fuente = """package ejemplo; import java.util.*; public class Banco {
      /** Devuelve en orden: el conjunto a y b, vacío, null.
       * @return lista ordenada con conjunto a y b, conjunto vacío y null */
      public static List<Set<String>> valores() {
        return Arrays.asList(Set.of("b", "a"), Set.of(), null);
      }
    }"""
    casos = [
        {
            "id": "anidados",
            "entrada": {},
            "valor_esperado": [["a", "b"], [], None],
            "origen": "docstring",
            "categoria": "normal",
        }
    ]
    ejecutar_fixture(
        cliente_docker,
        tmp_path,
        monkeypatch,
        fuente,
        casos,
        codigo_de_casos(casos, "List<Set<String>>", argumentos=""),
        0,
    )

"""Clase concreta con dependencia simulada en Docker, sin intentar lo no ejecutable (#301).

Proveedores grabados (0 tokens): el esperado está escrito en la grabación y sale
del Javadoc, nunca de ejecutar Java. Maven resuelve Mockito al preparar la imagen y
la prueba corre en el sandbox sin red.
"""

import json
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.llm import RespuestaLLM
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA
from tests.lenguajes.test_issue292_java_inferencia import escribir

pytestmark = pytest.mark.docker

POM = (
    '<project xmlns="http://maven.apache.org/POM/4.0.0">'
    "<modelVersion>4.0.0</modelVersion><groupId>demo</groupId>"
    "<artifactId>dependencias</artifactId><version>1</version>"
    "<properties><maven.compiler.release>21</maven.compiler.release></properties>"
    "<dependencies><dependency><groupId>org.mockito</groupId>"
    "<artifactId>mockito-core</artifactId><version>5.14.2</version>"
    "<scope>test</scope></dependency></dependencies></project>"
)
SERVICIO = """package demo;
public class Servicio {
    private final Repo repo;
    public Servicio(Repo repo) { this.repo = repo; }
    /** Siempre devuelve siete. @return 7 */
    public int siete() { return 7; }
}
"""
REPO = """package demo;
public interface Repo {
    /** @return el total guardado */
    int total();
}
"""
FORMA = """package demo;
public abstract class Forma {
    /** @return el área */
    public abstract double area();
    /** @return 1 */
    public int uno() { return 1; }
}
"""
PRUEBA_DEPENDENCIA = (
    "package demo; import org.junit.jupiter.api.Test; "
    "import static org.junit.jupiter.api.Assertions.assertEquals; "
    "import static org.mockito.Mockito.mock; "
    "class ServicioTest { @Test void test_siete_normal() { "
    "Repo repo = mock(Repo.class); Servicio servicio = new Servicio(repo); "
    "assertEquals(7, servicio.siete()); } }"
)
PRUEBA_MOCK_OBJETIVO = (
    "package demo; import org.junit.jupiter.api.Test; "
    "import static org.junit.jupiter.api.Assertions.assertEquals; "
    "import static org.mockito.Mockito.mock; "
    "class ServicioTest { @Test void test_siete_normal() { "
    "Servicio servicio = mock(Servicio.class); "
    "assertEquals(7, servicio.siete()); } }"
)


class ProveedorGrabado:
    """Plan y JUnit grabados; registra los prompts para comprobar qué se pidió."""

    def __init__(self, prueba: str) -> None:
        self.prueba = prueba
        self.prompts: list[tuple[str, str]] = []

    def generar(self, prompt, rol="planner"):
        self.prompts.append((rol, prompt))
        if rol == "planner":
            contenido = json.dumps(
                [
                    {
                        "objetivo": "Servicio.siete",
                        "casos": [
                            {
                                "id": "siete_normal",
                                "entrada": {},
                                "valor_esperado": 7,
                                "origen": "docstring",
                                "categoria": "normal",
                            }
                        ],
                    }
                ]
                if "Servicio.siete" in prompt
                else []
            )
        elif rol == "generator":
            contenido = self.prueba
        else:
            contenido = "{}"
        return RespuestaLLM(contenido, 0, 0, 0, "java-dependencias-grabada")


@pytest.mark.parametrize(
    ("prueba", "aceptadas"),
    [(PRUEBA_DEPENDENCIA, 1), (PRUEBA_MOCK_OBJETIVO, 0)],
    ids=["mock-de-dependencia", "mock-del-objetivo"],
)
def test_dependencia_permitida_en_docker_y_guardrail_del_objetivo(
    cliente_docker, tmp_path, monkeypatch, prueba, aceptadas
):
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta la imagen base Java.")
    proyecto = tmp_path / "proyecto"
    escribir(proyecto, "pom.xml", POM)
    escribir(proyecto, "src/main/java/demo/Servicio.java", SERVICIO)
    escribir(proyecto, "src/main/java/demo/Repo.java", REPO)
    escribir(proyecto, "src/main/java/demo/Forma.java", FORMA)
    AlmacenProyecto(proyecto).inicializar()
    proveedor = ProveedorGrabado(prueba)
    monkeypatch.setattr(
        "qagent.orchestrator.corrida.crear_cliente", lambda *a, **kw: proveedor
    )

    resultado = ejecutar_corrida(
        proyecto,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
    )

    assert resultado.tokens == 0
    assert resultado.aceptadas == aceptadas, resultado.motivo
    prompts = [p for _, p in proveedor.prompts]
    assert not any("Forma." in p for p in prompts), "Forma no debía llegar a la IA"
    assert not any("Repo.total" in p for p in prompts if p.startswith("Infiere"))
    results = json.loads(
        (Path(resultado.carpeta) / "results.json").read_text(encoding="utf-8")
    )
    motivos = {o["objetivo"]: o["motivo"] for o in results["omitidos"]}
    assert {"Forma.area", "Forma.uno", "Repo.total"} <= set(motivos)
    if aceptadas == 0:
        detalle = (Path(resultado.carpeta) / "detalle.json").read_text(encoding="utf-8")
        assert "Mockito" in detalle

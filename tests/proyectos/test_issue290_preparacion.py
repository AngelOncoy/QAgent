"""Requisitos Maven visibles antes de IA: carpeta, proyecto clonado y backend."""

from pathlib import Path

import pytest

from qagent.config import cargar_configuracion
from qagent.lenguajes import JavaAdapter, PythonAdapter
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.proyectos.vista_previa import generar_vista_previa
from qagent.sandbox.maven import comprobar_preparacion, recolectar_archivos


def _proyecto(raiz: Path, cuerpo: str = "") -> Path:
    """Crea un proyecto Java mínimo para inspección; no compila su código."""
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "pom.xml").write_text("<project>" + cuerpo + "</project>", encoding="utf-8")
    fuente = raiz / "src/main/java/demo/Banco.java"
    fuente.parent.mkdir(parents=True)
    fuente.write_text(
        "package demo; public class Banco { /** Devuelve a más b. */ public static int sumar(int a, int b) { return a+b; } }",
        encoding="utf-8",
    )
    return raiz


@pytest.mark.parametrize(
    "declaracion",
    [
        "<properties><maven.compiler.release>26</maven.compiler.release></properties>",
        "<parent><artifactId>incompleto</artifactId></parent>",
        "<dependencies><dependency><systemPath>/externo/archivo.jar</systemPath></dependency></dependencies>",
        "<build><sourceDirectory>otro/directorio</sourceDirectory></build>",
    ],
)
def test_vista_previa_conserva_analisis_pero_explica_bloqueo_sin_ia(
    tmp_path, monkeypatch, declaracion
):
    """Se puede explorar el código; el Recomendador IA no se invoca si está bloqueado."""
    raiz = _proyecto(tmp_path / "proyecto", declaracion)

    def prohibido(*args, **kwargs):
        raise AssertionError("La comprobación no debe invocar IA")

    monkeypatch.setattr(
        "qagent.proyectos.vista_previa._recomendador_configurado", prohibido
    )
    previa = generar_vista_previa(raiz)
    assert previa["ok"] is True
    assert previa["lenguaje"] == "java"
    assert previa["resumen"]["total_funciones_publicas"] == 1
    assert previa["preparacion_proyecto"]["compatible"] is False
    assert previa["preparacion_proyecto"]["mensaje"]


@pytest.mark.parametrize("perfil", ["humo", "std", "deep"])
def test_corrida_bloquea_antes_de_clientes_y_docker(tmp_path, monkeypatch, perfil):
    """Una configuración incompatible no gasta tokens ni recibe veredictos inventados."""
    raiz = _proyecto(
        tmp_path / "repo", "<properties><java.version>26</java.version></properties>"
    )

    def prohibido(*args, **kwargs):
        raise AssertionError("No debe iniciar IA ni Docker")

    monkeypatch.setattr("qagent.orchestrator.corrida.crear_cliente", prohibido)
    config = cargar_configuracion(simulado=True).config
    eventos = []
    resultado = ejecutar_corrida(
        raiz,
        perfil,
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
        preparar_imagen=prohibido,
        ejecutor=prohibido,
    )
    assert resultado.estado == "fallo_controlado"
    assert resultado.tipo_terminacion == "detenida_error"
    assert "Java 26" in resultado.motivo
    assert resultado.total_procesados == 0
    assert resultado.aceptadas == resultado.bugs_detectados == resultado.tokens == 0
    assert any("Java 26" in evento["mensaje"] for evento in eventos)


def test_proyecto_admitido_informa_que_falta_comprobar_dependencias(tmp_path):
    raiz = _proyecto(
        tmp_path / "repo", "<properties><java.version>21</java.version></properties>"
    )
    datos = comprobar_preparacion(raiz)
    assert datos["compatible"]
    assert datos["descriptores"][0]["java"] == "21"
    assert "se comprobarán" in datos["mensaje"]
    assert PythonAdapter().comprobar_preparacion(raiz) == {
        "compatible": True,
        "mensaje": "",
    }


def test_sin_pom_explica_que_el_ejecutor_requiere_maven(tmp_path):
    datos = JavaAdapter().comprobar_preparacion(tmp_path)
    assert not datos["compatible"]
    assert "pom.xml" in datos["mensaje"]


def test_perfil_en_maven_config_se_conserva_y_afecta_la_huella(tmp_path):
    raiz = _proyecto(
        tmp_path / "repo",
        "<profiles><profile><id>java21</id><properties><java.version>21</java.version></properties></profile></profiles>",
    )
    (raiz / ".mvn").mkdir()
    (raiz / ".mvn/maven.config").write_text("-Pjava21\n", encoding="utf-8")
    assert comprobar_preparacion(raiz)["descriptores"][0]["java"] == "21"
    assert (
        recolectar_archivos(raiz)[".mvn/maven.config"]
        == (raiz / ".mvn/maven.config").read_bytes()
    )


@pytest.mark.parametrize(
    "archivo, contenido",
    [
        (".mvn/maven.config", "--settings privado.xml"),
        (".mvn/jvm.config", "-javaagent:agente.jar"),
        (".mvn/extensions.xml", "<extensions/>"),
    ],
)
def test_opciones_no_admitidas_no_se_ignoran(tmp_path, archivo, contenido):
    raiz = _proyecto(tmp_path / "repo")
    (raiz / ".mvn").mkdir()
    (raiz / archivo).write_text(contenido, encoding="utf-8")
    assert not comprobar_preparacion(raiz)["compatible"]

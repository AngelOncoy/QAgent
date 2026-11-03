"""Ejecutor PIT con sandbox simulado: ningún test de este archivo ejecuta Java (#180)."""

from pathlib import Path

import pytest

from qagent.sandbox import pit_ejecucion
from qagent.sandbox.modelos import LimitesSandbox, ResultadoSandbox
from qagent.sandbox.mutacion import CONFIG_PROPIA, ERROR, OK, TIEMPO_AGOTADO

MODULO = "src/main/java/ejemplo/Banco.java"
XML = """<mutations><mutation status="KILLED"><mutatedClass>ejemplo.Banco</mutatedClass>
<mutatedMethod>sumar</mutatedMethod><methodDescription>(II)I</methodDescription>
<lineNumber>1</lineNumber><mutator>MathMutator</mutator><indexes><index>0</index></indexes>
<description>suma por resta</description></mutation></mutations>"""


@pytest.fixture
def datos(tmp_path: Path) -> tuple[Path, Path]:
    """Prepara un proyecto mínimo y una prueba aprobada, con valores ficticios."""
    proyecto = tmp_path / "proyecto"
    fuente = proyecto / MODULO
    fuente.parent.mkdir(parents=True)
    fuente.write_text(
        "package ejemplo; public class Banco { public int sumar(int a,int b) { return a+b; } }",
        encoding="utf-8",
    )
    (proyecto / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion><groupId>ejemplo</groupId><artifactId>banco</artifactId><version>1</version></project>",
        encoding="utf-8",
    )
    pruebas = tmp_path / "pruebas"
    pruebas.mkdir()
    (pruebas / "test_hash.py").write_text(
        "package ejemplo; public class BancoTest {}", encoding="utf-8"
    )
    return proyecto, pruebas


def test_ejecutor_usa_copia_y_limites(
    monkeypatch: pytest.MonkeyPatch, datos: tuple[Path, Path], tmp_path: Path
) -> None:
    """Solo la copia contiene el POM temporal; los límites y el XML se conservan."""
    proyecto, pruebas = datos
    vistos = {}

    def sandbox(imagen, comando, copia, tests, limites, **opciones):
        """Simula el contenedor y el informe sin ejecutar ninguna herramienta Java."""
        vistos.update(
            copia=copia, limites=limites, comando=comando, cliente=opciones["cliente"]
        )
        assert copia != proyecto
        assert (copia / ".qagent-pit.xml").is_file()
        assert (copia / ".qagent-pit-tests/ejemplo/BancoTest.java").is_file()
        salida = tmp_path / "salida"
        (salida / "pit").mkdir(parents=True)
        (salida / "pit/mutations.xml").write_text(XML, encoding="utf-8")
        opciones["al_terminar"](copia, salida)
        return ResultadoSandbox(0, "PIT correcto", "", duracion_s=1.25)

    monkeypatch.setattr(pit_ejecucion, "ejecutar_en_sandbox", sandbox)
    informes = []
    cliente = object()
    resultado = pit_ejecucion.ejecutar_pit(
        "imagen-java",
        proyecto,
        pruebas,
        MODULO,
        ["Banco.sumar"],
        LimitesSandbox(cpus=2, memoria="4g", timeout_s=30),
        cliente=cliente,
        al_informe=informes.append,
    )
    assert resultado.funciones["Banco.sumar"].estado == OK
    assert resultado.funciones["Banco.sumar"].puntuacion == 100.0
    assert resultado.duracion_s == 1.25
    assert vistos["limites"] == LimitesSandbox(cpus=2, memoria="4g", timeout_s=30)
    assert vistos["cliente"] is cliente
    assert not vistos["copia"].exists()
    assert not (proyecto / ".qagent-pit.xml").exists()
    assert informes == [XML]


@pytest.mark.parametrize(
    ("salida", "estado", "mensaje"),
    [
        (ResultadoSandbox(137, "", "", timed_out=True), TIEMPO_AGOTADO, "tiempo"),
        (ResultadoSandbox(137, "", "", oom_killed=True), ERROR, "memoria"),
        (ResultadoSandbox(1, "", "error de compilación"), ERROR, "código 1"),
        (ResultadoSandbox(0, "", ""), ERROR, "XML"),
    ],
)
def test_fallo_no_da_score(
    monkeypatch: pytest.MonkeyPatch,
    datos: tuple[Path, Path],
    salida: ResultadoSandbox,
    estado: str,
    mensaje: str,
) -> None:
    """Timeout, OOM, compilación fallida o informe ausente no se consideran éxitos."""
    monkeypatch.setattr(pit_ejecucion, "ejecutar_en_sandbox", lambda *a, **k: salida)
    funcion = pit_ejecucion.ejecutar_pit(
        "java", *datos, MODULO, ["Banco.sumar"]
    ).funciones["Banco.sumar"]
    assert funcion.estado == estado
    assert funcion.puntuacion is None
    assert mensaje in funcion.mensaje


def test_config_propia_no_invoca_docker(
    monkeypatch: pytest.MonkeyPatch, datos: tuple[Path, Path]
) -> None:
    """PIT declarado por el proyecto se omite sin alterar el POM ni llamar a Docker."""
    proyecto, pruebas = datos
    pom = proyecto / "pom.xml"
    original = pom.read_text(encoding="utf-8").replace(
        "</project>",
        "<build><plugins><plugin><artifactId>pitest-maven</artifactId></plugin></plugins></build></project>",
    )
    pom.write_text(original, encoding="utf-8")

    def prohibido(*a, **k):
        """La prueba falla si se intenta ejecutar PIT sobre configuración propia."""
        pytest.fail("No debe invocarse Docker")

    monkeypatch.setattr(pit_ejecucion, "ejecutar_en_sandbox", prohibido)
    funcion = pit_ejecucion.ejecutar_pit(
        None, proyecto, pruebas, MODULO, ["Banco.sumar"]
    ).funciones["Banco.sumar"]
    assert funcion.estado == CONFIG_PROPIA
    assert funcion.puntuacion is None
    assert pom.read_text(encoding="utf-8") == original


def test_presupuesto_de_mutacion_y_memoria_java(
    monkeypatch: pytest.MonkeyPatch, datos: tuple[Path, Path]
) -> None:
    """Sin límites explícitos aplica memoria Java y el presupuesto de mutación del equipo."""
    vistos = []
    monkeypatch.setattr(
        pit_ejecucion,
        "ejecutar_en_sandbox",
        lambda i, c, p, t, limites, **kw: (
            vistos.append(limites) or ResultadoSandbox(0, "", "")
        ),
    )
    pit_ejecucion.ejecutar_pit(None, *datos, MODULO, ["Banco.sumar", "Banco.sumar"])
    assert vistos[0].memoria == "4g"
    assert vistos[0].timeout_s == 120


def test_vacio_no_invoca_docker(
    monkeypatch: pytest.MonkeyPatch, datos: tuple[Path, Path]
) -> None:
    """Sin métodos críticos no hay ejecución ni resultado ficticio."""
    monkeypatch.setattr(
        pit_ejecucion,
        "ejecutar_en_sandbox",
        lambda *a, **k: pytest.fail("No debe ejecutarse"),
    )
    assert pit_ejecucion.ejecutar_pit(None, *datos, MODULO, []).funciones == {}

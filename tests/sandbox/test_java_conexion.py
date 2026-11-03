"""Conecta preparación/lectores Java con el sandbox común usando Docker simulado (#182)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qagent.lenguajes import JavaAdapter, PythonAdapter
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.sandbox.modelos import LimitesSandbox
from tests.lenguajes.test_java_ejecucion import MODULO, POM_BASE, crear_proyecto


@pytest.fixture
def proyecto(tmp_path: Path) -> tuple[Path, Path]:
    """Comparte el proyecto controlado con los tests de preparación, sin ejecutarlo."""
    return crear_proyecto(tmp_path)


def _cliente():
    """Cliente y contenedor simulados con salida de JUnit fallida, sin usar Docker real."""
    cliente = MagicMock()
    cliente.info.return_value = {"NCPU": 2}
    contenedor = cliente.containers.run.return_value
    contenedor.wait.return_value = {"StatusCode": 1}
    contenedor.attrs = {"State": {"OOMKilled": False}}
    contenedor.logs.return_value = b"QAGENT_JAVA_ETAPA=ejecucion\n"
    return cliente, contenedor


def _ejecutar(proyecto, cliente, preparar=None):
    """Usa el comando y lectores reales del adaptador con un cliente sustituido."""
    raiz, pruebas = proyecto
    adaptador = JavaAdapter()
    return ejecutar_comando_pruebas(
        "qagent-sandbox:java",
        adaptador.comando_pruebas(MODULO),
        raiz,
        pruebas,
        leer_cobertura=adaptador.leer_cobertura,
        archivo_informe=adaptador.entorno_sandbox().informe,
        limites=LimitesSandbox(cpus=4, memoria="4g", timeout_s=300),
        cliente=cliente,
        preparar=preparar or adaptador.preparador_sandbox(),
        leer_informe=adaptador.lector_informe_sandbox(),
    )


def test_prepara_copia_recoge_informes_y_conserva_aislamiento(proyecto) -> None:
    """La preparación sucede antes del contenedor y los lectores antes de limpiar sus carpetas."""
    raiz, _ = proyecto
    original = (raiz / "pom.xml").read_bytes()
    cliente, contenedor = _cliente()
    montajes = {}
    llamadas = []

    def iniciar(imagen, comando, **opciones):
        """Escribe reportes sintéticos como doble del contenedor; no ejecuta Java."""
        for montaje in opciones["mounts"]:
            montajes[montaje["Target"]] = Path(montaje["Source"])
        copia = montajes["/work/proyecto"]
        salida = montajes["/out"]
        assert (copia / ".qagent-junit.xml").is_file()
        assert (copia / ".qagent-junit-tests/ejemplo/BancoGeneradoTest.java").is_file()
        assert (copia / "pom.xml").read_bytes() == original
        informes = salida / "junit-raw"
        informes.mkdir()
        (informes / "TEST-Banco.xml").write_text(
            '<testsuite><testcase classname="ejemplo.BancoGeneradoTest" name="suma"><failure type="org.opentest4j.AssertionFailedError" message="expected: &lt;3&gt; but was: &lt;2&gt;"/></testcase></testsuite>',
            encoding="utf-8",
        )
        fixture = (
            Path(__file__).resolve().parents[1] / "fixtures/java/jacoco-controlado.xml"
        )
        (salida / "jacoco.xml").write_bytes(fixture.read_bytes())
        llamadas.append(opciones)
        return contenedor

    cliente.containers.run.side_effect = iniciar
    resultado = _ejecutar(proyecto, cliente)
    assert resultado.exit_code == 1
    assert resultado.coverage["totals"]["percent_covered"] == 80.0
    informe = JavaAdapter().interpretar_resultados(resultado.junit_xml)
    assert informe["fallaron"] == 1
    assert informe["casos"][0]["obtenido"] == "2"
    [opciones] = llamadas
    assert opciones["network_mode"] == "none"
    assert opciones["read_only"] is True
    assert opciones["mem_limit"] == opciones["memswap_limit"] == "4g"
    assert opciones["nano_cpus"] == 2_000_000_000
    assert (
        next(m for m in opciones["mounts"] if m["Target"] == "/work/tests")["ReadOnly"]
        is True
    )
    assert resultado.limites.timeout_s == 300
    assert resultado.limites.cpus == 2
    contenedor.wait.assert_called_once_with(timeout=300)
    contenedor.remove.assert_called_once_with(force=True)
    assert not montajes["/work/proyecto"].exists()
    assert not montajes["/out"].exists()
    assert (raiz / "pom.xml").read_bytes() == original
    assert not (raiz / ".qagent-junit.xml").exists()


@pytest.mark.parametrize("etapa", ["proyecto", "prueba"])
def test_preparacion_fallida_no_lanza_contenedor(proyecto, etapa: str) -> None:
    """Un fallo controlado se devuelve con su etapa y se limpia la copia sin ejecutar."""
    raiz, pruebas = proyecto
    if etapa == "proyecto":
        (raiz / "pom.xml").write_text(
            POM_BASE.replace("</project>", "<parent/></project>"), encoding="utf-8"
        )
    else:
        (pruebas / "otra.java").write_text("class Otra {}", encoding="utf-8")
    cliente, _ = _cliente()
    copias = []

    def preparar(copia, recibidas):
        """Registra la copia para verificar su limpieza, delegando en el preparador real."""
        copias.append(copia)
        JavaAdapter().preparador_sandbox()(copia, recibidas)

    resultado = _ejecutar(proyecto, cliente, preparar)
    assert resultado.exit_code == 2
    assert f"QAGENT_JAVA_ETAPA={etapa}" in resultado.stderr
    assert resultado.junit_xml is resultado.coverage is None
    cliente.containers.run.assert_not_called()
    assert all(not copia.exists() for copia in copias)


def test_error_inesperado_no_se_disfraza_como_resultado(proyecto) -> None:
    """Los errores de programación se propagan y también limpian la copia temporal."""
    cliente, _ = _cliente()
    copias = []

    def preparar(copia, pruebas):
        """Falla deliberadamente para comprobar finally, sin ejecutar código ajeno."""
        copias.append(copia)
        raise RuntimeError("fallo del preparador")

    with pytest.raises(RuntimeError, match="fallo del preparador"):
        _ejecutar(proyecto, cliente, preparar)
    cliente.containers.run.assert_not_called()
    assert all(not copia.exists() for copia in copias)


def test_python_conserva_su_ejecucion_sin_preparador() -> None:
    """Los puertos nuevos son opcionales y Python conserva su lector habitual."""
    adaptador = PythonAdapter()
    assert adaptador.preparador_sandbox() is None
    assert adaptador.lector_informe_sandbox() is None

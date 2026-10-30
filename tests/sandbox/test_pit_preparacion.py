"""Preparación estática sobre copias de proyectos Maven, sin JVM ni Docker (#180)."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.sandbox.pit_preparacion import ConfiguracionPitPropia, preparar_pit

MODULO = "src/main/java/ejemplo/Banco.java"
POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>ejemplo</groupId>
<artifactId>banco</artifactId><version>1</version>
<dependencies><dependency><groupId>org.junit.jupiter</groupId>
<artifactId>junit-jupiter</artifactId><version>5.14.4</version>
<scope>test</scope></dependency></dependencies></project>"""


@pytest.fixture
def proyecto(tmp_path: Path) -> tuple[Path, Path]:
    """Crea una copia sintética y una prueba aprobada cuyo nombre de entrada es hash."""
    copia = tmp_path / "copia"
    fuente = copia / MODULO
    fuente.parent.mkdir(parents=True)
    fuente.write_text(
        "package ejemplo; public class Banco { public static int sumar(int a, int b) { return a+b; } public int otro() { return 1; } }",
        encoding="utf-8",
    )
    (copia / "pom.xml").write_text(POM, encoding="utf-8")
    pruebas = tmp_path / "aprobadas"
    pruebas.mkdir()
    (pruebas / "test_hash.py").write_text(
        "package ejemplo; import org.junit.jupiter.api.Test; public class BancoTest { @Test void suma() { org.junit.jupiter.api.Assertions.assertEquals(3, Banco.sumar(1,2)); } }",
        encoding="utf-8",
    )
    return copia, pruebas


def test_prepara_sin_tocar_originales(proyecto: tuple[Path, Path]) -> None:
    """Conserva POM y pruebas originales y crea solo el POM y tests reservados."""
    copia, pruebas = proyecto
    originales = {
        p.relative_to(copia): p.read_bytes() for p in copia.rglob("*") if p.is_file()
    }
    anterior = copia / "src/test/java/AntiguaTest.java"
    anterior.parent.mkdir(parents=True)
    anterior.write_text("class AntiguaTest {}", encoding="utf-8")
    resultado = preparar_pit(copia, pruebas, MODULO, ["Banco.sumar"])
    assert resultado == {"Banco.sumar": ("ejemplo.Banco", "sumar")}
    assert all(
        (copia / ruta).read_bytes() == datos for ruta, datos in originales.items()
    )
    assert anterior.read_text(encoding="utf-8") == "class AntiguaTest {}"
    assert (copia / ".qagent-pit-tests/ejemplo/BancoTest.java").is_file()
    contenido_pom = (copia / ".qagent-pit.xml").read_text(encoding="utf-8")
    assert "<project " in contenido_pom  # Maven rechaza ns0:project.
    pom = ET.parse(copia / ".qagent-pit.xml").getroot()
    assert (
        pom.findtext("{*}build/{*}testSourceDirectory")
        == "/work/proyecto/.qagent-pit-tests"
    )
    assert pom.findtext("{*}dependencies/{*}dependency/{*}version") == "5.14.4"
    plugin = pom.find("{*}build/{*}plugins/{*}plugin")
    assert plugin.findtext("{*}version") == "1.30.1"
    assert (
        plugin.findtext("{*}dependencies/{*}dependency/{*}artifactId")
        == "pitest-junit5-plugin"
    )
    assert plugin.findtext("{*}dependencies/{*}dependency/{*}version") == "1.2.3"


@pytest.mark.parametrize("en_perfil", [False, True])
def test_respeta_config_pit_en_pom(
    proyecto: tuple[Path, Path], en_perfil: bool
) -> None:
    """PIT declarado directamente o en un perfil se conserva y no se ejecuta."""
    copia, pruebas = proyecto
    plugin = "<build><plugins><plugin><artifactId>pitest-maven</artifactId></plugin></plugins></build>"
    contenido = POM.replace(
        "</project>",
        (
            "<profiles><profile>" + plugin + "</profile></profiles>"
            if en_perfil
            else plugin
        )
        + "</project>",
    )
    (copia / "pom.xml").write_text(contenido, encoding="utf-8")
    with pytest.raises(ConfiguracionPitPropia):
        preparar_pit(copia, pruebas, MODULO, ["Banco.sumar"])
    assert (copia / "pom.xml").read_text(encoding="utf-8") == contenido
    assert not (copia / ".qagent-pit.xml").exists()


@pytest.mark.parametrize("nombre", ["build.gradle", "build.gradle.kts"])
def test_respeta_pit_gradle(proyecto: tuple[Path, Path], nombre: str) -> None:
    """Una configuración PIT de Gradle no se reemplaza por la configuración Maven."""
    copia, pruebas = proyecto
    archivo = copia / nombre
    archivo.write_text('plugins { id("info.solidsoft.pitest") }', encoding="utf-8")
    with pytest.raises(ConfiguracionPitPropia):
        preparar_pit(copia, pruebas, MODULO, ["Banco.sumar"])
    assert (
        archivo.read_text(encoding="utf-8") == 'plugins { id("info.solidsoft.pitest") }'
    )


@pytest.mark.parametrize(
    "fuente",
    [
        "package otro; public class Banco { public int sumar() { return 1; } }",
        "package ejemplo; public class Banco { public int otro() { return 1; } }",
        "package ejemplo; public class Banco { public int sumar() { return 1; } public int sumar(int a) { return a; } }",
        "package ejemplo; public class Banco {",
    ],
)
def test_rechaza_alcance_no_verificable(
    proyecto: tuple[Path, Path], fuente: str
) -> None:
    """Paquete distinto, método ausente, sobrecarga o sintaxis inválida no generan POM."""
    copia, pruebas = proyecto
    (copia / MODULO).write_text(fuente, encoding="utf-8")
    with pytest.raises(ValueError):
        preparar_pit(copia, pruebas, MODULO, ["Banco.sumar"])
    assert not (copia / ".qagent-pit.xml").exists()


def test_rechaza_pruebas_vacias(proyecto: tuple[Path, Path], tmp_path: Path) -> None:
    """No se lanza mutación sin pruebas aprobadas disponibles."""
    copia, _ = proyecto
    vacia = tmp_path / "sin_pruebas"
    vacia.mkdir()
    with pytest.raises(ValueError, match="No hay pruebas"):
        preparar_pit(copia, vacia, MODULO, ["Banco.sumar"])


@pytest.mark.parametrize(
    "extra",
    [
        "<parent><artifactId>padre</artifactId></parent>",
        "<modules><module>otro</module></modules>",
    ],
)
def test_no_asume_configuracion_heredada(
    proyecto: tuple[Path, Path], extra: str
) -> None:
    """Herencia o módulos no resueltos fallan explícitamente en esta etapa."""
    copia, pruebas = proyecto
    (copia / "pom.xml").write_text(
        POM.replace("</project>", extra + "</project>"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="herencia o módulos"):
        preparar_pit(copia, pruebas, MODULO, ["Banco.sumar"])


def test_reserva_archivos_sin_sobrescribir(proyecto: tuple[Path, Path]) -> None:
    """Un archivo reservado ya presente no se reemplaza silenciosamente."""
    copia, pruebas = proyecto
    reservado = copia / ".qagent-pit.xml"
    reservado.write_text("contenido previo", encoding="utf-8")
    with pytest.raises(ValueError, match="reservados"):
        preparar_pit(copia, pruebas, MODULO, ["Banco.sumar"])
    assert reservado.read_text(encoding="utf-8") == "contenido previo"


def test_no_admite_entidades_xml(proyecto: tuple[Path, Path]) -> None:
    """El POM con entidades externas se rechaza sin resolverlas."""
    copia, pruebas = proyecto
    (copia / "pom.xml").write_text(
        '<!DOCTYPE project [<!ENTITY x SYSTEM "file:///etc/passwd">]><project/>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="entidades"):
        preparar_pit(copia, pruebas, MODULO, ["Banco.sumar"])

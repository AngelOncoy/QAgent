"""Pruebas sin Docker del alcance del comando de mutación Java (#180)."""

import re
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.sandbox.pit_comando import comando_pit

MODULO = "src/main/java/org/ejemplo/Banco.java"


def _propiedad(comando: list[str], nombre: str) -> str:
    """Obtiene una propiedad -D del comando para comprobar el filtro completo."""
    return next(a.split("=", 1)[1] for a in comando if a.startswith(f"-D{nombre}="))


def test_clase_exacta_y_metodos_seleccionados() -> None:
    """Solo la clase exacta y los dos métodos elegidos quedan dentro del alcance.

    Comprueba también constructores, nombres parecidos y clases anidadas. Estos
    tests verifican la expresión construida; la semántica real de PIT se validará
    adicionalmente con una ejecución Docker, no se presenta como ya comprobada.
    """
    comando = JavaAdapter().comando_mutacion(MODULO, ["Banco.sumar", "Banco.restar"])
    assert comando.comando[0] == "mvn"
    assert "--offline" in comando.comando
    assert comando.entorno == {}
    clase = _propiedad(comando.comando, "targetClasses")
    assert clase.startswith("~")
    assert re.fullmatch(clase[1:], "org.ejemplo.Banco")
    assert not re.fullmatch(clase[1:], "org.ejemplo.BancoExtra")
    assert not re.fullmatch(clase[1:], "org.ejemplo.Banco$Anidada")
    filtro = _propiedad(comando.comando, "excludedMethods")[1:]
    for permitido in ("sumar", "restar"):
        assert not re.fullmatch(filtro, permitido)
    for excluido in ("sumarExtra", "restarTodo", "otro", "<init>", "<clinit>"):
        assert re.fullmatch(filtro, excluido)


def test_comando_determinista_y_version_de_la_receta() -> None:
    """Duplicados y orden no cambian el comando, que usa la versión PIT del sandbox."""
    a = comando_pit(MODULO, ["Banco.sumar", "Banco.restar", "Banco.sumar"])
    b = comando_pit(MODULO, ["Banco.restar", "Banco.sumar"])
    assert a == b
    assert "org.pitest:pitest-maven:1.30.1:mutationCoverage" in a.comando
    assert "-DoutputFormats=XML" in a.comando
    assert "-DreportsDirectory=/out/pit" in a.comando


@pytest.mark.parametrize(
    "funciones",
    [
        [],
        ["Banco.*"],
        ["Otro.sumar"],
        ["sumar"],
        ["Banco.sumar;exit"],
        ["Banco.Banco"],
        ["Banco.sumar", "Otro.restar"],
    ],
)
def test_rechaza_selecciones_no_acotadas(funciones: list[str]) -> None:
    """Selecciones vacías, ajenas o con comodines no deben generar un comando."""
    with pytest.raises(ValueError):
        comando_pit(MODULO, funciones)


@pytest.mark.parametrize(
    "modulo",
    [
        "../Banco.java",
        "/src/main/java/Banco.java",
        "Banco.java",
        "src/main/java/../Banco.java",
        "src/main/java/paquete*/Banco.java",
        "src/main/java/Banco.py",
        "submodulo/src/main/java/Banco.java",
    ],
)
def test_rechaza_rutas_no_admitidas(modulo: str) -> None:
    """Una ruta no admitida falla explícitamente, sin recurrir al proyecto completo."""
    with pytest.raises(ValueError):
        comando_pit(modulo, ["Banco.sumar"])


def test_construccion_no_toca_pom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Construir el comando no crea ni modifica archivos de configuración del proyecto."""
    pom = tmp_path / "pom.xml"
    original = "<project><build>configuración propia</build></project>"
    pom.write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    comando = comando_pit(MODULO, ["Banco.sumar"])
    assert pom.read_text(encoding="utf-8") == original
    assert list(tmp_path.iterdir()) == [pom]
    assert "/work/proyecto/.qagent-pit.xml" in comando.comando

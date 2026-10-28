"""Registro de adaptadores y detección básica del lenguaje (EN-17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.lenguajes import AdaptadorEnDesarrollo, Registro, listar_archivos


class Java(AdaptadorEnDesarrollo):
    lenguaje = "java"
    extensiones = (".java",)
    marcadores = ("pom.xml",)
    frameworks_pruebas = ("junit5",)


class Python(AdaptadorEnDesarrollo):
    lenguaje = "python"
    extensiones = (".py",)
    marcadores = ("pyproject.toml",)
    frameworks_pruebas = ("pytest",)
    frameworks_app = ("fastapi",)


def registro() -> Registro:
    return Registro([Python(), Java()])


# --- Registro ----------------------------------------------------------------------


def test_adaptador_por_lenguaje() -> None:
    r = registro()
    assert r.lenguajes == ("python", "java")
    assert isinstance(r.adaptador_para("java"), Java)


def test_lenguaje_sin_adaptador() -> None:
    with pytest.raises(KeyError, match="python, java"):
        registro().adaptador_para("typescript")


def test_no_se_registra_dos_veces_el_mismo_lenguaje() -> None:
    r = registro()
    with pytest.raises(ValueError, match="Ya hay"):
        r.registrar(Java())
    otro = Java()
    r.registrar(otro, reemplazar=True)
    assert r.adaptador_para("java") is otro


@pytest.mark.parametrize(
    "atributos",
    [
        {"lenguaje": "cobol"},
        {"frameworks_pruebas": ("pytest",)},
        {"frameworks_pruebas": ()},
        {"frameworks_app": ("express",)},
        {"extensiones": ("java",)},
        {"extensiones": ()},
    ],
)
def test_adaptador_incoherente_con_los_contratos(atributos: dict) -> None:
    Malo = type("Malo", (Java,), atributos)
    with pytest.raises(ValueError):
        Registro([Malo()])


def ejemplo(nombre: str) -> dict:
    ruta = contracts.DIR_CONTRATOS / "ejemplos" / f"{nombre}.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_adaptador_de_un_contrato_v2_es_python() -> None:
    r = registro()
    assert isinstance(r.adaptador_de_contrato(ejemplo("planner_contract.v2")), Python)
    assert isinstance(
        r.adaptador_de_contrato(ejemplo("planner_contract.v3.java")), Java
    )


def test_adaptador_de_un_contrato_invalido() -> None:
    with pytest.raises(contracts.ContratoInvalido):
        registro().adaptador_de_contrato({"version": "9"})


# --- Detección básica --------------------------------------------------------------


def test_detecta_un_solo_lenguaje() -> None:
    [deteccion] = registro().detectar_en(["pyproject.toml", "app/main.py", "a.py"])
    assert deteccion.lenguaje == "python"
    assert deteccion.archivos == 2
    assert deteccion.marcadores == ("pyproject.toml",)
    assert deteccion.confianza == 1.0


def test_proyecto_mixto_ordena_por_confianza() -> None:
    detecciones = registro().detectar_en(
        ["A.java", "B.java", "C.java", "scripts/util.py"]
    )
    assert [d.lenguaje for d in detecciones] == ["java", "python"]
    assert [d.confianza for d in detecciones] == [0.75, 0.25]


def test_sin_lenguajes_conocidos() -> None:
    assert registro().detectar_en(["README.md", "index.html"]) == []
    assert registro().detectar_en([]) == []


def test_solo_marcador_sin_fuentes_tiene_confianza_cero() -> None:
    [deteccion] = registro().detectar_en(["pom.xml"])
    assert deteccion.lenguaje == "java"
    assert deteccion.confianza == 0.0


def test_detectar_en_disco_ignora_carpetas_de_dependencias(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text("class App {}", encoding="utf-8")
    for carpeta in ("node_modules", ".venv", "target", "tests"):
        (tmp_path / carpeta).mkdir()
        for i in range(5):
            (tmp_path / carpeta / f"m{i}.py").write_text("x = 1", encoding="utf-8")

    assert listar_archivos(tmp_path) == ["src/App.java"]
    assert registro().lenguaje_principal(tmp_path) == "java"


def test_lenguaje_principal_de_una_carpeta_vacia(tmp_path: Path) -> None:
    assert registro().lenguaje_principal(tmp_path) is None


def test_detectar_en_algo_que_no_es_carpeta(tmp_path: Path) -> None:
    archivo = tmp_path / "x.py"
    archivo.write_text("", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        registro().detectar(archivo)

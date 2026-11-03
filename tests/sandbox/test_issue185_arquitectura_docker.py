"""#185: herramientas reales de arquitectura dentro de Docker sin red."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.almacenamiento.proyecto import AlmacenProyecto
from qagent.arquitectura.ejecucion import verificar_arquitectura
from qagent.lenguajes import adaptador_para
from qagent.sandbox import ejecutar_en_sandbox

pytestmark = pytest.mark.docker


def _regla_capas(proyecto: Path) -> None:
    AlmacenProyecto(proyecto).guardar_reglas_arquitectura(
        {
            "version": "1",
            "reglas": [
                {
                    "id": "capas-001",
                    "tipo": "dependencia_prohibida",
                    "nombre": "Dominio no debe depender de interfaz",
                    "origen": "usuario",
                    "confirmada": True,
                    "desde": "dominio",
                    "hacia": "interfaz",
                }
            ],
        }
    )


@pytest.mark.parametrize(
    ("lenguaje", "comando", "esperado"),
    [
        ("python", ["lint-imports", "--version"], "2.15"),
        ("javascript", ["dependency-cruiser", "--version"], "18.6.0"),
        (
            "java",
            [
                "sh",
                "-c",
                "test -f /opt/qagent/archunit/archunit-1.5.1.jar && echo 1.5.1",
            ],
            "1.5.1",
        ),
    ],
)
def test_imagen_contiene_herramienta_fijada(
    cliente_docker, tmp_path: Path, lenguaje: str, comando: list[str], esperado: str
) -> None:
    proyecto = tmp_path / lenguaje
    pruebas = tmp_path / f"tests-{lenguaje}"
    proyecto.mkdir()
    pruebas.mkdir()
    imagen = adaptador_para(lenguaje).entorno_sandbox().imagen
    resultado = ejecutar_en_sandbox(
        imagen, comando, proyecto, pruebas, cliente=cliente_docker
    )
    assert resultado.exit_code == 0, resultado.stderr
    assert esperado in resultado.stdout


def test_python_detecta_ciclo_y_linea_de_capa(cliente_docker, tmp_path: Path) -> None:
    proyecto = tmp_path / "python"
    for carpeta in ("app", "app/dominio", "app/interfaz"):
        (proyecto / carpeta).mkdir(parents=True, exist_ok=True)
        (proyecto / carpeta / "__init__.py").touch()
    (proyecto / "app/dominio/a.py").write_text(
        "from app.interfaz import b\n", encoding="utf-8"
    )
    (proyecto / "app/interfaz/b.py").write_text(
        "from app.dominio import a\n", encoding="utf-8"
    )
    _regla_capas(proyecto)
    resultado = verificar_arquitectura(proyecto, cliente=cliente_docker)
    assert resultado["estado"] == "incumple"
    capas = next(r for r in resultado["reglas"] if r["id"] == "capas-001")
    assert capas["estado"] == "incumple"
    assert capas["hallazgos"][0]["linea"] == 1


def test_python_detecta_ciclo_de_tres_y_error_de_sintaxis_sin_falso_hallazgo(
    cliente_docker, tmp_path: Path
) -> None:
    proyecto = tmp_path / "python-tres"
    (proyecto / "app").mkdir(parents=True)
    (proyecto / "app/__init__.py").touch()
    (proyecto / "app/a.py").write_text("from app import b\n", encoding="utf-8")
    (proyecto / "app/b.py").write_text("from app import c\n", encoding="utf-8")
    (proyecto / "app/c.py").write_text("from app import a\n", encoding="utf-8")
    resultado = verificar_arquitectura(proyecto, cliente=cliente_docker)
    assert resultado["estado"] == "incumple"

    invalido = tmp_path / "python-invalido"
    (invalido / "app").mkdir(parents=True)
    (invalido / "app/__init__.py").touch()
    (invalido / "app/a.py").write_text("from app import (\n", encoding="utf-8")
    resultado_invalido = verificar_arquitectura(invalido, cliente=cliente_docker)
    assert resultado_invalido["estado"] == "sin_veredicto"
    assert resultado_invalido["reglas"][0]["hallazgos"] == []


@pytest.mark.parametrize(
    "lenguaje,extension", [("javascript", "js"), ("typescript", "ts")]
)
def test_node_detecta_ciclo_y_capa(
    cliente_docker, tmp_path: Path, lenguaje: str, extension: str
) -> None:
    proyecto = tmp_path / lenguaje
    (proyecto / "dominio").mkdir(parents=True)
    (proyecto / "interfaz").mkdir()
    tipo_modulo = "commonjs" if lenguaje == "javascript" else "module"
    (proyecto / "package.json").write_text(
        f'{{"name":"arquitectura-fixture","version":"1.0.0","type":"{tipo_modulo}"}}',
        encoding="utf-8",
    )
    if lenguaje == "javascript":
        (proyecto / "dominio/a.js").write_text(
            'const b = require("../interfaz/b.js");\nmodule.exports = b;\n',
            encoding="utf-8",
        )
        (proyecto / "interfaz/b.js").write_text(
            'const a = require("../dominio/a.js");\nmodule.exports = a;\n',
            encoding="utf-8",
        )
    else:
        (proyecto / f"dominio/a.{extension}").write_text(
            f'import {{ b }} from "../interfaz/b.{extension}";\nexport const a = b;\n',
            encoding="utf-8",
        )
        (proyecto / f"interfaz/b.{extension}").write_text(
            f'import {{ a }} from "../dominio/a.{extension}";\nexport const b = a;\n',
            encoding="utf-8",
        )
    _regla_capas(proyecto)
    resultado = verificar_arquitectura(proyecto, cliente=cliente_docker)
    assert resultado["estado"] == "incumple"
    assert all(r["estado"] == "incumple" for r in resultado["reglas"])


def test_java_detecta_ciclo_y_capa(cliente_docker, tmp_path: Path) -> None:
    proyecto = tmp_path / "java"
    dominio = proyecto / "src/main/java/com/app/dominio/A.java"
    interfaz = proyecto / "src/main/java/com/app/interfaz/B.java"
    dominio.parent.mkdir(parents=True)
    interfaz.parent.mkdir(parents=True)
    dominio.write_text(
        "package com.app.dominio; import com.app.interfaz.B; public class A { B b; }",
        encoding="utf-8",
    )
    interfaz.write_text(
        "package com.app.interfaz; import com.app.dominio.A; public class B { A a; }",
        encoding="utf-8",
    )
    _regla_capas(proyecto)
    resultado = verificar_arquitectura(proyecto, cliente=cliente_docker)
    assert resultado["estado"] == "incumple"
    assert all(r["estado"] == "incumple" for r in resultado["reglas"])
    hallazgos = [h for regla in resultado["reglas"] for h in regla["hallazgos"]]
    assert any(h["linea"] == 1 for h in hallazgos)
    assert any(h["archivo"].endswith("A.java") for h in hallazgos if h["archivo"])


@pytest.mark.parametrize("lenguaje", ["python", "javascript", "typescript", "java"])
def test_proyecto_limpio_cumple_regla_universal(
    cliente_docker, tmp_path: Path, lenguaje: str
) -> None:
    proyecto = tmp_path / f"limpio-{lenguaje}"
    if lenguaje == "python":
        (proyecto / "app").mkdir(parents=True)
        (proyecto / "app/__init__.py").touch()
        (proyecto / "app/b.py").write_text("valor = 1\n", encoding="utf-8")
        (proyecto / "app/a.py").write_text(
            "import json\nfrom .b import valor as dato\n", encoding="utf-8"
        )
    elif lenguaje in {"javascript", "typescript"}:
        extension = "ts" if lenguaje == "typescript" else "js"
        proyecto.mkdir()
        (proyecto / "package.json").write_text(
            '{"name":"limpio","version":"1.0.0","type":"module"}',
            encoding="utf-8",
        )
        (proyecto / f"a.{extension}").write_text(
            "export const valor = 1;\n", encoding="utf-8"
        )
    else:
        fuente = proyecto / "src/main/java/com/app/dominio/A.java"
        otra = proyecto / "src/main/java/com/app/interfaz/B.java"
        fuente.parent.mkdir(parents=True)
        otra.parent.mkdir(parents=True)
        fuente.write_text(
            "package com.app.dominio; public class A {}", encoding="utf-8"
        )
        otra.write_text("package com.app.interfaz; public class B {}", encoding="utf-8")
    resultado = verificar_arquitectura(proyecto, cliente=cliente_docker)
    assert resultado["estado"] == "cumple"
    assert resultado["reglas"][0]["estado"] == "cumple"


@pytest.mark.parametrize("lenguaje", ["python", "javascript", "typescript", "java"])
def test_regla_de_capa_cumplida_en_docker(
    cliente_docker, tmp_path: Path, lenguaje: str
) -> None:
    proyecto = tmp_path / f"capas-limpias-{lenguaje}"
    if lenguaje == "python":
        (proyecto / "app").mkdir(parents=True)
        (proyecto / "app/__init__.py").touch()
        (proyecto / "app/dominio.py").write_text("valor = 1\n", encoding="utf-8")
        (proyecto / "app/interfaz.py").write_text("valor = 2\n", encoding="utf-8")
    elif lenguaje in {"javascript", "typescript"}:
        extension = "ts" if lenguaje == "typescript" else "js"
        (proyecto / "dominio").mkdir(parents=True)
        (proyecto / "interfaz").mkdir()
        (proyecto / "package.json").write_text(
            '{"name":"capas","version":"1.0.0","type":"module"}',
            encoding="utf-8",
        )
        (proyecto / f"dominio/a.{extension}").write_text(
            "export const a = 1;\n", encoding="utf-8"
        )
        (proyecto / f"interfaz/b.{extension}").write_text(
            "export const b = 2;\n", encoding="utf-8"
        )
    else:
        dominio = proyecto / "src/main/java/com/app/dominio/A.java"
        interfaz = proyecto / "src/main/java/com/app/interfaz/B.java"
        dominio.parent.mkdir(parents=True)
        interfaz.parent.mkdir(parents=True)
        dominio.write_text(
            "package com.app.dominio; public class A {}", encoding="utf-8"
        )
        interfaz.write_text(
            "package com.app.interfaz; public class B {}", encoding="utf-8"
        )
    _regla_capas(proyecto)

    resultado = verificar_arquitectura(proyecto, cliente=cliente_docker)

    assert resultado["estado"] == "cumple"
    assert all(r["estado"] == "cumple" for r in resultado["reglas"])

"""#169: construcción y ejecución mínima de las imágenes de Node y Java (Docker real).

Necesitan Docker Desktop iniciado e internet: la primera vez construyen
`qagent-sandbox:node` (~45 s) y `qagent-sandbox:java` (~3-4 min) y las imágenes
derivadas descargan dependencias. Las pruebas en sí corren sin red (`network_mode
none`), con el sistema de archivos de solo lectura y los límites de su lenguaje.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.lenguajes import adaptador_para
from qagent.sandbox import asegurar_imagen, ejecutar_en_sandbox

pytestmark = [pytest.mark.docker, pytest.mark.red]

CALENTAMIENTO = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "sandbox"
    / "java"
    / "calentamiento"
)

PACKAGE_JSON = {
    "name": "demo",
    "version": "1.0.0",
    "type": "module",
    "dependencies": {"is-odd": "3.0.1"},
}
PACKAGE_LOCK = {
    "name": "demo",
    "version": "1.0.0",
    "lockfileVersion": 3,
    "requires": True,
    "packages": {
        "": {"name": "demo", "version": "1.0.0", "dependencies": {"is-odd": "3.0.1"}},
        "node_modules/is-number": {
            "version": "6.0.0",
            "resolved": "https://registry.npmjs.org/is-number/-/is-number-6.0.0.tgz",
            "integrity": "sha512-Wu1VHeILBK8KAWJUAiSZQX94GmOE45Rg6/538fKwiloUu21Knc"
            "EkYGPqob2oSZ5mUT73vLGrHQjKw3KMPwfDzg==",
            "license": "MIT",
            "engines": {"node": ">=0.10.0"},
        },
        "node_modules/is-odd": {
            "version": "3.0.1",
            "resolved": "https://registry.npmjs.org/is-odd/-/is-odd-3.0.1.tgz",
            "integrity": "sha512-CQpnWPrDwmP1+SMHXZhtLtJv90yiyVfluGsX5iNCVkrhQtU3TQHs"
            "UWPG9wkdk9Lgd5yNpAg9jQEo90CBaXgWMA==",
            "license": "MIT",
            "dependencies": {"is-number": "^6.0.0"},
            "engines": {"node": ">=4"},
        },
    },
}


def _limites(lenguaje: str):
    """Límites de `[sandbox.<lenguaje>]` del config.toml del equipo."""
    carga = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True)
    return carga.config.limites_sandbox(lenguaje)


def _imagen(lenguaje: str, proyecto: Path, cliente) -> str:
    """Imagen del proyecto según su adaptador; construye la base si falta."""
    base = adaptador_para(lenguaje).entorno_sandbox().imagen
    return asegurar_imagen(proyecto, base, cliente)


@pytest.mark.parametrize("lenguaje", ["javascript", "typescript"])
def test_node_ejecuta_vitest_con_cobertura_sin_red(cliente_docker, tmp_path, lenguaje):
    proyecto = tmp_path / "proyecto"
    (proyecto / "src").mkdir(parents=True)
    (proyecto / "package.json").write_text(json.dumps(PACKAGE_JSON), encoding="utf-8")
    (proyecto / "package-lock.json").write_text(
        json.dumps(PACKAGE_LOCK), encoding="utf-8"
    )
    extension = "ts" if lenguaje == "typescript" else "js"
    tipo = ": number" if lenguaje == "typescript" else ""
    (proyecto / "src" / f"suma.{extension}").write_text(
        'import isOdd from "is-odd";\n\n'
        f"export function suma(a{tipo}, b{tipo}) {{\n  return a + b;\n}}\n\n"
        f"export function esImpar(n{tipo}) {{\n  return isOdd(n);\n}}\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / f"suma.test.{extension}").write_text(
        'import { expect, it } from "vitest";\n'
        f'import {{ esImpar, suma }} from "../proyecto/src/suma.{extension}";\n\n'
        'it("suma", () => expect(suma(2, 3)).toBe(5));\n'
        'it("usa una dependencia del proyecto", () => expect(esImpar(3)).toBe(true));\n',
        encoding="utf-8",
    )
    imagen = _imagen(lenguaje, proyecto, cliente_docker)
    assert imagen.startswith("qagent-sandbox:node-")
    # Segunda vez: se reutiliza la derivada (mismo package-lock.json).
    assert _imagen(lenguaje, proyecto, cliente_docker) == imagen

    resultado = ejecutar_en_sandbox(
        imagen,
        [
            "sh",
            "-c",
            (
                "cd /work/proyecto && vitest run --dir /work/tests "
                "--coverage.enabled --coverage.reporter=json-summary "
                "--coverage.reportsDirectory=/out/coverage "
                "--reporter=junit --outputFile=/out/junit.xml "
                "&& cat /out/junit.xml && test -f /out/coverage/coverage-summary.json"
            ),
        ],
        proyecto,
        tests,
        _limites(lenguaje),
        cliente=cliente_docker,
    )

    assert resultado.exit_code == 0, resultado.stdout + resultado.stderr
    assert 'tests="2" failures="0" errors="0"' in resultado.stdout
    assert resultado.limites.memoria == "2g"


def test_java_maven_ejecuta_junit_y_jacoco_sin_red(cliente_docker, tmp_path):
    proyecto = tmp_path / "proyecto"
    shutil.copytree(CALENTAMIENTO, proyecto)
    pom = proyecto / "pom.xml"
    pom.write_text(
        pom.read_text(encoding="utf-8").replace(
            "<artifactId>calentamiento</artifactId>", "<artifactId>demo</artifactId>"
        ),
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    imagen = _imagen("java", proyecto, cliente_docker)
    assert imagen.startswith("qagent-sandbox:java-")

    resultado = ejecutar_en_sandbox(
        imagen,
        [
            "sh",
            "-c",
            (
                "cd /work/proyecto && mvn -o -q verify "
                "&& cat target/surefire-reports/TEST-qagent.CalentamientoTest.xml "
                "&& test -f target/site/jacoco/jacoco.xml"
            ),
        ],
        proyecto,
        tests,
        _limites("java"),
        cliente=cliente_docker,
    )

    assert resultado.exit_code == 0, resultado.stdout + resultado.stderr
    assert 'tests="1"' in resultado.stdout and 'failures="0"' in resultado.stdout
    assert "jansi" not in resultado.stderr
    assert resultado.limites.memoria == "4g"


def test_java_gradle_ejecuta_junit_sin_red(cliente_docker, tmp_path):
    proyecto = tmp_path / "proyecto"
    shutil.copytree(CALENTAMIENTO / "src", proyecto / "src")
    (proyecto / "settings.gradle.kts").write_text(
        'rootProject.name = "demo"\n', encoding="utf-8"
    )
    (proyecto / "build.gradle.kts").write_text(
        'plugins {\n    id("java")\n}\n\n'
        "repositories {\n    mavenCentral()\n}\n\n"
        "dependencies {\n"
        '    testImplementation(platform("org.junit:junit-bom:5.14.4"))\n'
        '    testImplementation("org.junit.jupiter:junit-jupiter")\n'
        '    testRuntimeOnly("org.junit.platform:junit-platform-launcher")\n'
        "}\n\n"
        "tasks.test {\n    useJUnitPlatform()\n}\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    imagen = _imagen("java", proyecto, cliente_docker)

    resultado = ejecutar_en_sandbox(
        imagen,
        [
            "sh",
            "-c",
            (
                "cd /work/proyecto && gradle --offline -q test "
                "&& cat build/test-results/test/TEST-qagent.CalentamientoTest.xml"
            ),
        ],
        proyecto,
        tests,
        _limites("java"),
        cliente=cliente_docker,
    )

    assert resultado.exit_code == 0, resultado.stdout + resultado.stderr
    assert 'tests="1"' in resultado.stdout and 'failures="0"' in resultado.stdout

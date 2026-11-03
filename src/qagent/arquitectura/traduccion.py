"""Traducción de reglas comunes a configuraciones sin comandos proporcionados por el usuario."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from qagent.lenguajes.base import PlanArquitectura
from qagent.lenguajes.registro import listar_archivos


def _paquetes_python(raiz: Path) -> list[str]:
    return sorted(
        p.parent.relative_to(raiz).as_posix().replace("/", ".")
        for p in raiz.glob("*/__init__.py")
        if p.is_file() and not p.is_symlink()
    )


def _modulo_python(patron: str, paquetes: list[str]) -> str:
    modulo = patron.replace("/", ".").strip(".")
    if any(modulo == p or modulo.startswith(p + ".") for p in paquetes):
        return modulo
    return f"{paquetes[0]}.{modulo}" if len(paquetes) == 1 else modulo


def traducir_python(reglas: list[dict[str, Any]], raiz: Path) -> list[PlanArquitectura]:
    """Crea un contrato import-linter aislado por regla para atribuir el resultado."""
    paquetes = _paquetes_python(raiz)
    if not paquetes:
        raise ValueError(
            "import-linter requiere al menos un paquete Python con __init__.py."
        )
    cabecera = "[importlinter]\nroot_packages =\n" + "".join(
        f"  {paquete}\n" for paquete in paquetes
    )
    planes = []
    for indice, regla in enumerate(reglas):
        seccion = [
            "",
            f"[importlinter:contract:qagent-{indice}]",
            f"name = {regla['id']}",
        ]
        if regla["tipo"] == "ciclos_importacion":
            seccion.extend(["type = acyclic_siblings", "ancestors ="])
            seccion.extend(f"  {paquete}" for paquete in paquetes)
        else:
            seccion.extend(
                [
                    "type = forbidden",
                    "source_modules =",
                    f"  {_modulo_python(regla['desde'], paquetes)}",
                    "forbidden_modules =",
                    f"  {_modulo_python(regla['hacia'], paquetes)}",
                    "allow_indirect_imports = true",
                ]
            )
        archivo = f"importlinter-{indice}.ini"
        planes.append(
            PlanArquitectura(
                regla=regla,
                herramienta="import-linter 2.15",
                comando=[
                    "lint-imports",
                    "--config",
                    f"/work/tests/{archivo}",
                    "--no-cache",
                    "--no-logo",
                ],
                archivos={archivo: cabecera + "\n".join(seccion) + "\n"},
            )
        )
    return planes


def _regex_ruta(patron: str) -> str:
    normalizado = patron.replace("\\", "/").strip("/")
    cuerpo = re.escape(normalizado).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return rf"(^|/){cuerpo}(/|$)"


def traducir_node(
    reglas: list[dict[str, Any]], raiz: Path, lenguaje: str
) -> list[PlanArquitectura]:
    """Crea reglas JSON de dependency-cruiser sin ejecutar `npx` ni descargar nada."""
    planes = []
    for indice, regla in enumerate(reglas):
        if regla["tipo"] == "ciclos_importacion":
            prohibida = {
                "name": regla["id"],
                "severity": "error",
                "from": {},
                "to": {"circular": True},
            }
        else:
            prohibida = {
                "name": regla["id"],
                "severity": "error",
                "from": {"path": _regex_ruta(regla["desde"])},
                "to": {"path": _regex_ruta(regla["hacia"])},
            }
        config = {
            "forbidden": [prohibida],
            "options": {
                "doNotFollow": {"path": "node_modules"},
                "exclude": {"path": "(^|/)(test|tests|dist|build|coverage)(/|$)"},
                "moduleSystems": ["es6", "cjs"],
                "skipAnalysisNotInRules": True,
            },
        }
        archivo = f"dependency-cruiser-{indice}.json"
        archivos: dict[str, str] = {}
        if lenguaje == "typescript":
            config["options"].update(
                {
                    "parser": "tsc",
                    "tsPreCompilationDeps": True,
                    "tsConfig": {"fileName": "/work/tests/qagent-tsconfig.json"},
                }
            )
            archivos["qagent-tsconfig.json"] = json.dumps(
                {
                    "compilerOptions": {
                        "module": "NodeNext",
                        "moduleResolution": "NodeNext",
                        "target": "ES2022",
                        "allowImportingTsExtensions": True,
                        "noEmit": True,
                    },
                    "include": ["/work/proyecto/**/*.ts", "/work/proyecto/**/*.tsx"],
                }
            )
        archivos[archivo] = json.dumps(config, ensure_ascii=False)
        planes.append(
            PlanArquitectura(
                regla=regla,
                herramienta="dependency-cruiser 18.6.0",
                comando=[
                    "dependency-cruiser",
                    "--config",
                    f"/work/tests/{archivo}",
                    "--output-type",
                    "json",
                    ".",
                ],
                archivos=archivos,
            )
        )
    return planes


def _paquete_base_java(raiz: Path) -> str:
    paquetes = []
    for relativa in listar_archivos(raiz):
        if not relativa.endswith(".java") or "/test/" in f"/{relativa}/":
            continue
        try:
            texto = (raiz / relativa).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        if encontrado := re.search(
            r"(?m)^\s*package\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*;", texto
        ):
            paquetes.append(encontrado.group(1))
    if not paquetes:
        raise ValueError(
            "ArchUnit requiere clases Java dentro de un paquete declarado."
        )
    segmentos = [p.split(".") for p in paquetes]
    comunes = []
    for partes in zip(*segmentos):
        if len(set(partes)) != 1:
            break
        comunes.append(partes[0])
    if not comunes:
        raise ValueError("No se encontró un paquete raíz Java común.")
    # Un único segmento suele ser un dominio (`com`); dos identifican la aplicación.
    profundidad = min(max(2, len(comunes)), len(segmentos[0]) - 1)
    if profundidad < 1:
        raise ValueError("El paquete Java no tiene subpaquetes comparables.")
    return ".".join(segmentos[0][:profundidad])


def _literal_java(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace('"', '\\"')


def traducir_java(reglas: list[dict[str, Any]], raiz: Path) -> list[PlanArquitectura]:
    """Genera un pequeño evaluador ArchUnit; el código del proyecto se compila en Docker."""
    base = _paquete_base_java(raiz)
    planes = []
    for indice, regla in enumerate(reglas):
        if regla["tipo"] == "ciclos_importacion":
            expresion = (
                'SlicesRuleDefinition.slices().matching("'
                + _literal_java(base)
                + '.(*)..").should().beFreeOfCycles()'
            )
        else:
            desde = _literal_java(regla["desde"].replace("/", ".").strip("."))
            hacia = _literal_java(regla["hacia"].replace("/", ".").strip("."))
            expresion = (
                'ArchRuleDefinition.noClasses().that().resideInAPackage("..'
                + desde
                + '..").should().dependOnClassesThat().resideInAPackage("..'
                + hacia
                + '..")'
            )
        fuente = _FUENTE_JAVA.replace("__REGLA__", expresion)
        script = _SCRIPT_JAVA
        planes.append(
            PlanArquitectura(
                regla=regla,
                herramienta="ArchUnit 1.5.1",
                comando=["sh", f"/work/tests/arquitectura-{indice}.sh"],
                archivos={
                    "QAgentArchitecture.java": fuente,
                    f"arquitectura-{indice}.sh": script,
                },
            )
        )
    return planes


_FUENTE_JAVA = """\
import java.nio.file.Paths;
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition;
import com.tngtech.archunit.library.dependencies.SlicesRuleDefinition;

public final class QAgentArchitecture {
  public static void main(String[] args) {
    JavaClasses classes = new ClassFileImporter().importPath(Paths.get("/tmp/qagent-classes"));
    ArchRule rule = __REGLA__;
    var result = rule.evaluate(classes);
    if (result.hasViolation()) {
      System.out.println("QAGENT_STATUS\\tincumple");
      System.out.println(result.getFailureReport());
      System.exit(1);
    }
    System.out.println("QAGENT_STATUS\\tcumple");
  }
}
"""

_SCRIPT_JAVA = """\
#!/bin/sh
set -eu
rm -rf /tmp/qagent-classes
mkdir -p /tmp/qagent-classes
find /work/proyecto -type f -name '*.java' ! -path '*/src/test/*' > /tmp/qagent-sources.txt
javac -cp '/opt/qagent/archunit/*' -d /tmp/qagent-classes @/tmp/qagent-sources.txt /work/tests/QAgentArchitecture.java
java -cp '/tmp/qagent-classes:/opt/qagent/archunit/*' QAgentArchitecture
"""

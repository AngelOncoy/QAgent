"""#272: monorepos JS con pnpm y npm workspaces en Docker real.

El proyecto tiene un `postinstall` que falla: si QAgent lo ejecutara al construir la
imagen derivada, la construcción se caería. Después, Vitest corre sin red y resuelve
tanto una dependencia externa como un paquete del propio monorepo (`workspace:*`).
Necesitan Docker Desktop iniciado e internet para descargar pnpm y los paquetes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.sandbox import IMAGEN_NODE, asegurar_imagen, ejecutar_en_sandbox

pytestmark = [pytest.mark.docker, pytest.mark.red]

POSTINSTALL_QUE_FALLA = "node scripts/no-existe.js"


def _escribir(raiz: Path, archivos: dict[str, str | dict]) -> None:
    for nombre, contenido in archivos.items():
        ruta = raiz / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        texto = json.dumps(contenido) if isinstance(contenido, dict) else contenido
        ruta.write_text(texto, encoding="utf-8")


def _monorepo(proyecto: Path, gestor: str) -> None:
    raiz: dict = {
        "name": "mono",
        "private": True,
        "scripts": {"postinstall": POSTINSTALL_QUE_FALLA, "prepare": "husky"},
    }
    archivos: dict[str, str | dict] = {}
    if gestor == "pnpm":
        raiz["packageManager"] = "pnpm@10.33.4"
        archivos["pnpm-workspace.yaml"] = "packages:\n  - 'packages/*'\n"
        dependencia_interna = "workspace:*"
    else:
        raiz["workspaces"] = ["packages/*"]
        dependencia_interna = "1.0.0"
    archivos.update(
        {
            "package.json": raiz,
            "packages/util/package.json": {
                "name": "@mono/util",
                "version": "1.0.0",
                "type": "module",
                "main": "src/index.js",
                "dependencies": {"is-odd": "3.0.1"},
                "scripts": {"postinstall": POSTINSTALL_QUE_FALLA},
            },
            "packages/util/src/index.js": (
                'import isOdd from "is-odd";\nexport const esImpar = (n) => isOdd(n);\n'
            ),
            "packages/app/package.json": {
                "name": "@mono/app",
                "version": "1.0.0",
                "type": "module",
                "dependencies": {"@mono/util": dependencia_interna},
            },
            "packages/app/src/suma.js": (
                'import { esImpar } from "@mono/util";\n'
                "export const sumaEsImpar = (a, b) => esImpar(a + b);\n"
            ),
        }
    )
    _escribir(proyecto, archivos)


@pytest.mark.parametrize("gestor", ["pnpm", "npm"])
def test_monorepo_instala_sin_scripts_y_resuelve_workspaces_sin_red(
    cliente_docker, tmp_path, gestor
):
    proyecto = tmp_path / "proyecto"
    _monorepo(proyecto, gestor)
    tests = tmp_path / "tests"
    _escribir(
        tests,
        {
            "suma.test.js": (
                'import { expect, it } from "vitest";\n'
                'import { sumaEsImpar } from "../proyecto/packages/app/src/suma.js";\n\n'
                'it("usa el workspace y su dependencia", () => '
                "expect(sumaEsImpar(1, 2)).toBe(true));\n"
            )
        },
    )

    imagen = asegurar_imagen(proyecto, IMAGEN_NODE, cliente_docker)
    assert imagen.startswith("qagent-sandbox:node-")

    carga = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True)
    resultado = ejecutar_en_sandbox(
        imagen,
        [
            "sh",
            "-c",
            "cd /work/proyecto && vitest run --dir /work/tests --reporter=verbose",
        ],
        proyecto,
        tests,
        carga.config.limites_sandbox("javascript"),
        cliente=cliente_docker,
    )

    assert resultado.exit_code == 0, resultado.stdout + resultado.stderr
    assert "1 passed" in resultado.stdout

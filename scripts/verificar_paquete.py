"""Verifica que QAgent funcione instalado como paquete, fuera del repositorio (TA-06).

Hace lo mismo que quien instala QAgent: construye el paquete (wheel y sdist), lo
instala en un entorno virtual nuevo en una carpeta temporal y, desde fuera del
repositorio, comprueba que el comando abre y que encuentra todos sus recursos. Durante
la prueba la carpeta personal apunta a una carpeta temporal: tus `~/.qagent/` reales no
se tocan.

Uso (desde la raíz del repositorio, con internet para instalar las dependencias):
    python scripts/verificar_paquete.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: Archivos que deben venir en el paquete para que la app funcione instalada.
RECURSOS = (
    "qagent/frontend/index.html",
    "qagent/frontend/css/tokens.css",
    "qagent/contracts/planner_contract.v2.schema.json",
    "qagent/contracts/ejemplos/planner_contract.v2.json",
    "qagent/config/config.toml",
    "qagent/llm/proveedores.toml",
    "qagent/llm/ia_simulada.json",
    "qagent/sandbox/Dockerfile",
)

#: Prueba de humo que corre con el Python del entorno nuevo, fuera del repositorio.
HUMO = r"""
import json, sys, tempfile
from pathlib import Path

import qagent
from qagent import contracts
from qagent.app.desktop import FRONTEND_DIR
from qagent.config import carga
from qagent.analysis.analyzer import analizar_proyecto
from qagent.llm.fake import RUTA_GRABACIONES, cargar_grabaciones
from qagent.usuario import carpeta_usuario

paquete = Path(qagent.__file__).resolve().parent
assert "site-packages" in paquete.parts, f"no se usa el paquete instalado: {paquete}"
assert (FRONTEND_DIR / "index.html").is_file(), "falta la interfaz"
assert carga.RUTA_ENV.parent == carpeta_usuario(), "el .env no está en ~/.qagent/"
assert paquete not in carga.RUTA_ENV.parents, "el .env quedaría dentro del programa"

resultado = carga.cargar_configuracion(simulado=True)
assert resultado.config is not None, resultado.avisos_config

ejemplo = json.loads((contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(encoding="utf-8"))
contracts.validar(contracts.PLANNER, ejemplo)

assert cargar_grabaciones(RUTA_GRABACIONES), "la IA simulada no tiene respuestas"

proyecto = Path(tempfile.mkdtemp()) / "demo"
proyecto.mkdir()
(proyecto / "calc.py").write_text("def suma(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
funciones = [f["nombre"] for m in analizar_proyecto(proyecto)["modulos"] for f in m["funciones"]]
assert funciones == ["suma"], funciones

print("version:", qagent.__version__)
print("paquete:", paquete)
print("interfaz:", sum(1 for _ in FRONTEND_DIR.rglob("*") if _.is_file()), "archivos")
print("configuración del equipo: ok · contratos: ok · IA simulada: ok · análisis: ok")
"""


def _correr(comando: list[str], **kwargs) -> subprocess.CompletedProcess:
    visible = ["<prueba de humo>" if c == HUMO else str(c) for c in comando]
    print("$", " ".join(visible), flush=True)
    return subprocess.run(comando, check=True, text=True, **kwargs)


def _revisar_wheel(wheel: Path) -> None:
    nombres = set(zipfile.ZipFile(wheel).namelist())
    faltan = [r for r in RECURSOS if r not in nombres]
    fuera = sorted({n.split("/")[0] for n in nombres if not n.startswith("qagent")})
    assert not faltan, f"faltan en el wheel: {faltan}"
    assert not fuera, f"el wheel trae carpetas ajenas: {fuera}"
    print(f"wheel: {len(nombres)} archivos, con los {len(RECURSOS)} recursos clave")


def _revisar_sdist(sdist: Path) -> None:
    with tarfile.open(sdist) as tar:
        nombres = tar.getnames()
    faltan = [r for r in RECURSOS if not any(n.endswith("src/" + r) for n in nombres)]
    assert not faltan, f"faltan en el sdist: {faltan}"
    print(f"sdist: {len(nombres)} entradas, con los {len(RECURSOS)} recursos clave")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="qagent-paquete-") as tmp:
        tmp = Path(tmp)
        dist = tmp / "dist"
        _correr([sys.executable, "-m", "build", "--outdir", str(dist), str(RAIZ)])
        [wheel] = dist.glob("*.whl")
        [sdist] = dist.glob("*.tar.gz")
        _revisar_wheel(wheel)
        _revisar_sdist(sdist)

        entorno_virtual = tmp / "venv"
        venv.create(entorno_virtual, with_pip=True)
        carpeta_bin = "Scripts" if os.name == "nt" else "bin"
        python = (
            entorno_virtual
            / carpeta_bin
            / ("python.exe" if os.name == "nt" else "python")
        )
        _correr([str(python), "-m", "pip", "install", "-q", str(wheel)])

        # Fuera del repositorio y con una carpeta personal temporal.
        casa = tmp / "casa"
        casa.mkdir()
        entorno = {**os.environ, "HOME": str(casa), "USERPROFILE": str(casa)}
        entorno.pop("PYTHONPATH", None)
        qagent = (
            entorno_virtual
            / carpeta_bin
            / ("qagent.exe" if os.name == "nt" else "qagent")
        )
        _correr([str(qagent), "--version"], cwd=casa, env=entorno)
        _correr([str(python), "-c", HUMO], cwd=casa, env=entorno)
    print("\nOK: QAgent funciona instalado como paquete, fuera del repositorio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller para QAgent en Windows (TA-06).

No se usa a mano: la llama `python scripts/construir_windows.py`. Genera una carpeta
(`dist/windows/QAgent/`) con `QAgent.exe` y todo lo que necesita; el instalador de Inno
Setup (`qagent.iss`) empaqueta esa carpeta. Se eligió carpeta y no un único .exe porque
abre más rápido y los antivirus lo marcan menos.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

AQUI = Path(SPECPATH)  # noqa: F821 (variable que define PyInstaller)

# Interfaz, contratos, config.toml, IA simulada y Dockerfile: los mismos datos que el
# wheel. Quedan en `qagent/...` junto a sus módulos, así las rutas de TA-06 funcionan igual.
# La metadata va con el nombre de PyPI (qagent-pytest): de ahí sale `qagent --version`.
# Incluye las gramáticas de tree-sitter para análisis multilenguaje (ADR-009).
datos = (
    collect_data_files("qagent")
    + collect_data_files("tree_sitter")
    + collect_data_files("tree_sitter_javascript")
    + collect_data_files("tree_sitter_typescript")
    + copy_metadata("qagent-pytest")
)

a = Analysis(  # noqa: F821
    [str(AQUI / "lanzador.py")],
    datas=datos,
    # Varios módulos se importan dentro de funciones: PyInstaller no los ve solo.
    hiddenimports=(
        collect_submodules("qagent")
        + collect_submodules("tree_sitter")
        + collect_submodules("tree_sitter_javascript")
        + collect_submodules("tree_sitter_typescript")
    ),
    excludes=["pytest", "ruff", "tkinter", "build"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QAgent",
    icon=str(AQUI / "qagent.ico"),
    console=False,  # aplicación de ventana: la bitácora va a ~/.qagent/registro.log
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="QAgent", upx=False)  # noqa: F821

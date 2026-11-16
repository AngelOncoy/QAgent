"""#287: un módulo del proyecto que falta es del entorno, no de la prueba.

El Reviewer decide si un `ModuleNotFoundError` se reintenta (la prueba importó algo
inventado) o se reporta como entorno (el proyecto lo necesita y no está instalado).
Antes comparaba el nombre de la distribución con el del módulo, leyendo los archivos
línea por línea, y fallaba en 9 de 11 formas habituales de declarar una dependencia.
Todo se lee de forma estática: nada del proyecto se ejecuta.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.lenguajes import python_dependencias
from qagent.lenguajes.python_revision import ReglasRevisionPython


def _salida_import(modulo: str, desde: str = "../tests/test_generado.py:3") -> str:
    """Salida de pytest cuando falla un import al recolectar el archivo de prueba."""
    return (
        "ImportError while importing test module '/work/tests/test_generado.py'.\n"
        "Traceback:\n"
        "/usr/local/lib/python3.11/importlib/__init__.py:126: in import_module\n"
        "    return _bootstrap._gcd_import(name[level:], package, level)\n"
        f"{desde}: in <module>\n"
        f"    import {modulo}\n"
        f"E   ModuleNotFoundError: No module named '{modulo}'\n"
    )


def _escribir(raiz: Path, archivos: dict[str, str]) -> Path:
    for ruta, contenido in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
    return raiz


# Las 11 formas de la auditoría (PY2) y tres más: setup.cfg, un workspace de uv y
# python-dotenv, el caso real que gastó reintentos en el spike #289.
FORMAS = {
    "pep621_en_una_linea": (
        {
            "pyproject.toml": '[project]\nname = "p"\ndependencies = ["requests>=2.31"]\n'
        },
        "requests",
        "requests",
    ),
    "pep621_multilinea": (
        {
            "pyproject.toml": (
                '[project]\nname = "p"\ndependencies = [\n    "requests>=2.31",\n]\n'
            )
        },
        "requests",
        "requests",
    ),
    "poetry": (
        {
            "pyproject.toml": (
                '[tool.poetry.dependencies]\npython = "^3.11"\nrequests = "^2.31"\n'
            )
        },
        "requests",
        "requests",
    ),
    "extra_entre_corchetes": (
        {"requirements.txt": "Django[argon2]>=5.0\n"},
        "django",
        "Django",
    ),
    "pyyaml": ({"requirements.txt": "PyYAML>=6\n"}, "yaml", "PyYAML"),
    "pillow": ({"requirements.txt": "Pillow==11.0\n"}, "PIL", "Pillow"),
    "beautifulsoup4": (
        {"requirements.txt": "beautifulsoup4\n"},
        "bs4",
        "beautifulsoup4",
    ),
    "scikit_learn": (
        {"requirements.txt": "scikit-learn>=1.5\n"},
        "sklearn",
        "scikit-learn",
    ),
    "python_dateutil": (
        {"requirements.txt": "python-dateutil\n"},
        "dateutil",
        "python-dateutil",
    ),
    "setup_py": (
        {
            "setup.py": (
                "from setuptools import setup\n"
                "setup(name='p', install_requires=['requests>=2.31', 'PyYAML'])\n"
            )
        },
        "yaml",
        "PyYAML",
    ),
    "pipfile": (
        {"Pipfile": '[packages]\nrequests = "*"\n\n[dev-packages]\npytest = "*"\n'},
        "requests",
        "requests",
    ),
    "setup_cfg": (
        {
            "setup.cfg": (
                "[metadata]\nname = p\n\n[options]\ninstall_requires =\n"
                "    requests>=2.31\n    python-dateutil\n"
            )
        },
        "dateutil",
        "python-dateutil",
    ),
    "workspace_uv": (
        {
            "pyproject.toml": (
                '[project]\nname = "raiz"\ndependencies = []\n\n'
                '[tool.uv.workspace]\nmembers = ["paquetes/*"]\n'
            ),
            "paquetes/asistente/pyproject.toml": (
                '[project]\nname = "asistente"\ndependencies = ["fastapi>=0.110"]\n'
            ),
        },
        "fastapi",
        "fastapi",
    ),
    "python_dotenv": (
        {"pyproject.toml": '[project]\nname = "p"\ndependencies = ["python-dotenv"]\n'},
        "dotenv",
        "python-dotenv",
    ),
}


@pytest.mark.parametrize(
    ("archivos", "modulo", "distribucion"), FORMAS.values(), ids=FORMAS.keys()
)
def test_modulo_de_una_dependencia_declarada_es_del_entorno(
    tmp_path: Path, archivos: dict[str, str], modulo: str, distribucion: str
) -> None:
    raiz = _escribir(tmp_path, archivos)

    clasificacion = ReglasRevisionPython.clasificar_salida(
        _salida_import(modulo), {}, raiz
    )

    assert clasificacion is not None
    assert clasificacion.tipo == "entorno"
    assert distribucion in clasificacion.detalle  # nombra la dependencia que falta


def test_submodulo_de_una_dependencia_declarada_es_del_entorno(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path, {"requirements.txt": "Django>=5\n"})

    clasificacion = ReglasRevisionPython.clasificar_salida(
        _salida_import("django.http"), {}, raiz
    )

    assert clasificacion is not None
    assert clasificacion.tipo == "entorno"


def test_modulo_que_importa_un_archivo_del_proyecto_es_del_entorno(
    tmp_path: Path,
) -> None:
    """P15: el proyecto usa boto3 sin declararlo; la prueba no puede arreglarlo."""
    raiz = _escribir(tmp_path, {"app/almacen.py": "import boto3\n"})

    clasificacion = ReglasRevisionPython.clasificar_salida(
        _salida_import("boto3", desde="app/almacen.py:1"), {}, raiz
    )

    assert clasificacion is not None
    assert clasificacion.tipo == "entorno"
    assert "boto3" in clasificacion.detalle
    assert "app/almacen.py" in clasificacion.detalle


def test_modulo_inventado_por_la_prueba_se_sigue_reintentando(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path, {"requirements.txt": "requests\n"})

    clasificacion = ReglasRevisionPython.clasificar_salida(
        _salida_import("requests_mock"), {}, raiz
    )

    assert clasificacion is not None
    assert clasificacion.tipo == "error_test"


def test_un_archivo_de_dependencias_con_otro_nombre_no_confunde(tmp_path: Path) -> None:
    """`dependencies` o `install_requires` no son paquetes (antes se tomaban como tales)."""
    raiz = _escribir(
        tmp_path,
        {"pyproject.toml": '[project]\nname = "p"\ndependencies = ["requests"]\n'},
    )

    for modulo in ("dependencies", "project", "name"):
        clasificacion = ReglasRevisionPython.clasificar_salida(
            _salida_import(modulo), {}, raiz
        )
        assert clasificacion is not None
        assert clasificacion.tipo == "error_test", modulo


def test_archivo_del_proyecto_que_no_existe_no_cuenta_como_proyecto(
    tmp_path: Path,
) -> None:
    """Un marco cuyo archivo no está en el proyecto (p. ej. un helper inventado) no basta."""
    clasificacion = ReglasRevisionPython.clasificar_salida(
        _salida_import("boto3", desde="app/no_existe.py:1"), {}, tmp_path
    )

    assert clasificacion is not None
    assert clasificacion.tipo == "error_test"


# --- Lectura de dependencias ------------------------------------------------------


def test_lee_extras_grupos_y_dependencias_de_desarrollo(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path,
        {
            "pyproject.toml": (
                '[project]\nname = "p"\ndependencies = ["requests"]\n'
                '[project.optional-dependencies]\nimagenes = ["Pillow"]\n'
                '[dependency-groups]\ndev = ["pytest", {include-group = "otro"}]\n'
                'otro = ["PyYAML"]\n'
                "[tool.poetry.group.test.dependencies]\n"
                'beautifulsoup4 = "*"\n'
            ),
        },
    )

    modulos = python_dependencias.dependencias_declaradas(raiz)

    assert modulos["requests"] == "requests"
    assert modulos["PIL"] == "Pillow"
    assert modulos["pytest"] == "pytest"
    assert modulos["yaml"] == "PyYAML"
    assert modulos["bs4"] == "beautifulsoup4"


def test_requirements_ignora_opciones_rutas_y_comentarios(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path,
        {
            "requirements.txt": (
                "# comentario\n"
                "--extra-index-url https://ejemplo.invalid/simple\n"
                "-e .\n"
                "-r otros.txt\n"
                "requests==2.31 ; python_version >= '3.8'  # fijo\n"
                "itsdangerous @ git+https://github.com/pallets/itsdangerous@2.2.0\n"
                "./paquete_local\n"
            ),
            "requirements-dev.txt": "PyYAML\n",
        },
    )

    modulos = python_dependencias.dependencias_declaradas(raiz)

    assert set(modulos) == {"requests", "itsdangerous", "yaml"}


def test_setup_py_se_lee_sin_ejecutarlo(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path,
        {
            "setup.py": (
                "raise SystemExit('si esto corre, la lectura no es estática')\n"
                "setup(install_requires=['requests'], "
                "extras_require={'img': ['Pillow']})\n"
            )
        },
    )

    modulos = python_dependencias.dependencias_declaradas(raiz)

    assert modulos == {"requests": "requests", "PIL": "Pillow"}


def test_archivos_ilegibles_no_rompen_la_lectura(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path,
        {
            "pyproject.toml": "[project\nesto no es toml",
            "Pipfile": "tampoco = = toml",
            "setup.cfg": "[options\ninstall_requires = requests",
            "setup.py": "setup(install_requires=[",
            "requirements.txt": "PyYAML\n",
        },
    )

    assert python_dependencias.dependencias_declaradas(raiz) == {"yaml": "PyYAML"}


def test_los_miembros_del_workspace_no_salen_de_la_raiz(tmp_path: Path) -> None:
    afuera = _escribir(
        tmp_path / "afuera", {"pyproject.toml": '[project]\ndependencies = ["boto3"]\n'}
    )
    raiz = _escribir(
        tmp_path / "proyecto",
        {
            "pyproject.toml": (
                f'[tool.uv.workspace]\nmembers = ["../{afuera.name}", "paquetes/*"]\n'
            )
        },
    )

    assert "boto3" not in python_dependencias.dependencias_declaradas(raiz)

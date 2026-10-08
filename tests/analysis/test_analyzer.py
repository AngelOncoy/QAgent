"""Pruebas del analizador AST (EN-02). No llaman a ninguna API de IA."""

import ast
import json
from pathlib import Path

import pytest

from pyagent.analysis import analizar_proyecto, analizar_proyecto_json
from pyagent.analysis.analyzer import calcular_huella, contar_ramas, main

CALCULOS = '''"""Cálculos de ejemplo."""


def calcular_descuento(total: float, cupon: str | None = None) -> float:
    """Aplica un descuento si hay cupón."""
    if cupon == "VERANO" and total > 100:
        return total * 0.8
    elif cupon:
        return total * 0.9
    return total


def _auxiliar(x: int) -> int:
    return x
'''

UTILIDADES = '''def dividir(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return None


async def cargar(ruta: str) -> str:
    """Carga un archivo."""
    for _ in range(3):
        pass
    return ruta
'''

ROTO = "def mal(:\n    pass\n"


def escribir(raiz: Path, ruta: str, texto: str) -> None:
    destino = raiz / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Evidencia de aceptación (criterio 6 de EN-02)
# --------------------------------------------------------------------------- #
def test_analiza_tres_archivos_de_ejemplo(tmp_path):
    """3 archivos (uno con error de sintaxis): el JSON coincide con lo esperado."""
    escribir(tmp_path, "calculos.py", CALCULOS)
    escribir(tmp_path, "utilidades.py", UTILIDADES)
    escribir(tmp_path, "roto.py", ROTO)

    resultado = json.loads(analizar_proyecto_json(tmp_path))

    # El texto exacto del mensaje de SyntaxError cambia entre versiones de Python.
    assert resultado["errores"][0].pop("mensaje")

    assert resultado == {
        "modulos": [
            {
                "ruta": "calculos.py",
                "huella": "97567775f4d74e5e063d8e043fdce2a5bf42d1d08408ec16341cb100d41099d1",
                "funciones": [
                    {
                        "nombre": "calcular_descuento",
                        "linea": 4,
                        "firma": "(total: float, cupon: str | None=None) -> float",
                        "parametros": [
                            {"nombre": "total", "tipo": "float", "por_defecto": None},
                            {
                                "nombre": "cupon",
                                "tipo": "str | None",
                                "por_defecto": "None",
                            },
                        ],
                        "retorno": "float",
                        "docstring": "Aplica un descuento si hay cupón.",
                        "ramas": 2,
                        "tipada": True,
                        "es_async": False,
                    }
                ],
            },
            {
                "ruta": "utilidades.py",
                "huella": "2577b2ecca5b2987d08f8f5ec4039c3e711fbfc59376f57245777a872da5b9e0",
                "funciones": [
                    {
                        "nombre": "dividir",
                        "linea": 1,
                        "firma": "(a, b)",
                        "parametros": [
                            {"nombre": "a", "tipo": None, "por_defecto": None},
                            {"nombre": "b", "tipo": None, "por_defecto": None},
                        ],
                        "retorno": None,
                        "docstring": None,
                        "ramas": 1,
                        "tipada": False,
                        "es_async": False,
                    },
                    {
                        "nombre": "cargar",
                        "linea": 8,
                        "firma": "(ruta: str) -> str",
                        "parametros": [
                            {"nombre": "ruta", "tipo": "str", "por_defecto": None}
                        ],
                        "retorno": "str",
                        "docstring": "Carga un archivo.",
                        "ramas": 1,
                        "tipada": True,
                        "es_async": True,
                    },
                ],
            },
        ],
        "errores": [{"ruta": "roto.py", "tipo": "SyntaxError", "linea": 1}],
        "resumen": {
            "total_modulos": 2,
            "total_funciones_publicas": 3,
            "total_errores": 1,
            "inconsistencias": {
                "sin_docstring": {"cantidad": 1, "porcentaje": 33.3},
                "sin_tipos": {"cantidad": 1, "porcentaje": 33.3},
                "con_alguna": {"cantidad": 1, "porcentaje": 33.3},
            },
        },
    }


# --------------------------------------------------------------------------- #
# Criterio 2: qué se ignora
# --------------------------------------------------------------------------- #
def test_ignora_carpetas_excluidas_y_funciones_privadas(tmp_path):
    escribir(
        tmp_path,
        "app/servicio.py",
        "def publica():\n    pass\n\ndef _privada():\n    pass\n",
    )
    escribir(tmp_path, "tests/test_algo.py", "def test_algo():\n    pass\n")
    escribir(tmp_path, ".pyagent/specs/x.py", "def spec():\n    pass\n")
    escribir(tmp_path, ".venv/lib/paquete.py", "def externa():\n    pass\n")
    escribir(tmp_path, "app/tests/test_interno.py", "def test_interno():\n    pass\n")

    resultado = analizar_proyecto(tmp_path)

    assert [m["ruta"] for m in resultado["modulos"]] == ["app/servicio.py"]
    nombres = [f["nombre"] for f in resultado["modulos"][0]["funciones"]]
    assert nombres == ["publica"]


def test_la_raiz_puede_llamarse_tests(tmp_path):
    """Solo se ignoran las subcarpetas; la raíz elegida siempre se analiza."""
    raiz = tmp_path / "tests"
    escribir(raiz, "modulo.py", "def f():\n    pass\n")
    assert analizar_proyecto(raiz)["resumen"]["total_modulos"] == 1


def test_no_ejecuta_el_codigo_del_usuario(tmp_path):
    """Regla de AGENTS.md: el análisis es solo estático."""
    marca = tmp_path / "ejecutado.txt"
    escribir(
        tmp_path,
        "peligroso.py",
        f"open({str(marca)!r}, 'w').write('x')\n\ndef f():\n    pass\n",
    )
    analizar_proyecto(tmp_path)
    assert not marca.exists()


# --------------------------------------------------------------------------- #
# Criterio 3: errores sin detener el análisis
# --------------------------------------------------------------------------- #
def test_archivo_ilegible_se_reporta_y_el_resto_se_analiza(tmp_path):
    escribir(tmp_path, "bien.py", "def ok() -> None:\n    '''Doc.'''\n")
    (tmp_path / "binario.py").write_bytes(b"def f():\n    return '\xff\xfe'\n")
    escribir(tmp_path, "roto.py", ROTO)

    resultado = analizar_proyecto(tmp_path)

    assert [m["ruta"] for m in resultado["modulos"]] == ["bien.py"]
    assert [e["ruta"] for e in resultado["errores"]] == ["binario.py", "roto.py"]
    assert resultado["resumen"]["total_errores"] == 2
    assert resultado["errores"][1]["linea"] == 1


# --------------------------------------------------------------------------- #
# Criterio 4: huella
# --------------------------------------------------------------------------- #
def test_huella_es_sha256_y_cambia_con_codigo_o_docstring(tmp_path):
    base = 'def f():\n    """Doc."""\n    return 1\n'
    huella = calcular_huella(base)
    assert len(huella) == 64
    assert calcular_huella(base.replace("return 1", "return 2")) != huella
    assert calcular_huella(base.replace("Doc.", "Otra doc.")) != huella

    escribir(tmp_path, "m.py", base)
    assert analizar_proyecto(tmp_path)["modulos"][0]["huella"] == huella


def test_huella_no_depende_de_los_saltos_de_linea():
    assert calcular_huella("a = 1\r\nb = 2\r\n") == calcular_huella("a = 1\nb = 2\n")


# --------------------------------------------------------------------------- #
# Criterio 1: ramas
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("cuerpo", "esperadas"),
    [
        ("return 1", 0),
        ("if x:\n    return 1\nreturn 2", 1),
        ("if x:\n    return 1\nelif y:\n    return 2\nelse:\n    return 3", 2),
        ("for i in x:\n    pass", 1),
        ("while x:\n    break", 1),
        ("try:\n    pass\nexcept ValueError:\n    pass\nexcept KeyError:\n    pass", 2),
        ("return 1 if x else 2", 1),
        ("return [i for i in x if i if i > 1]", 2),
        ("match x:\n    case 1:\n        pass\n    case _:\n        pass", 2),
        ("def interna():\n    if x:\n        pass\nreturn interna", 0),
    ],
)
def test_conteo_de_ramas(cuerpo, esperadas):
    codigo = "def f(x, y=None):\n" + "\n".join("    " + l for l in cuerpo.splitlines())
    funcion = ast.parse(codigo).body[0]
    assert contar_ramas(funcion) == esperadas


def test_firma_con_todos_los_tipos_de_parametros(tmp_path):
    escribir(
        tmp_path,
        "m.py",
        "def f(a: int, /, b: str = 'x', *args: int, c: bool = True, **kw: str) -> None:\n"
        "    '''Doc.'''\n",
    )
    funcion = analizar_proyecto(tmp_path)["modulos"][0]["funciones"][0]
    assert [p["nombre"] for p in funcion["parametros"]] == [
        "a",
        "b",
        "*args",
        "c",
        "**kw",
    ]
    assert [p["por_defecto"] for p in funcion["parametros"]] == [
        None,
        "'x'",
        None,
        "True",
        None,
    ]
    assert funcion["tipada"] is True


def test_docstring_vacio_cuenta_como_ausente(tmp_path):
    escribir(tmp_path, "m.py", 'def f() -> None:\n    """   """\n')
    funcion = analizar_proyecto(tmp_path)["modulos"][0]["funciones"][0]
    assert funcion["docstring"] is None


# --------------------------------------------------------------------------- #
# Criterio 5: resumen
# --------------------------------------------------------------------------- #
def test_resumen_de_proyecto_sin_funciones(tmp_path):
    escribir(tmp_path, "vacio.py", "X = 1\n")
    resumen = analizar_proyecto(tmp_path)["resumen"]
    assert resumen["total_funciones_publicas"] == 0
    assert resumen["inconsistencias"]["con_alguna"] == {
        "cantidad": 0,
        "porcentaje": 0.0,
    }


def test_resultado_es_deterministico(tmp_path):
    for nombre in ("b.py", "a.py", "z/c.py"):
        escribir(tmp_path, nombre, "def f():\n    pass\n")
    primero = analizar_proyecto_json(tmp_path)
    assert analizar_proyecto_json(tmp_path) == primero
    rutas = [m["ruta"] for m in json.loads(primero)["modulos"]]
    assert rutas == sorted(rutas)


# --------------------------------------------------------------------------- #
# Uso
# --------------------------------------------------------------------------- #
def test_carpeta_inexistente_lanza_error(tmp_path):
    with pytest.raises(NotADirectoryError):
        analizar_proyecto(tmp_path / "no_existe")


def test_cli_imprime_json(tmp_path, capsys):
    escribir(tmp_path, "m.py", "def f() -> None:\n    '''Doc.'''\n")
    assert main([str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["resumen"]["total_modulos"] == 1


def test_cli_sin_argumentos_o_carpeta_invalida(tmp_path, capsys):
    assert main([]) == 2
    assert main([str(tmp_path / "no_existe")]) == 1
    assert capsys.readouterr().err

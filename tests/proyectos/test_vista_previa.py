"""Pruebas de la Vista previa del proyecto (HU-04).

Criterios de aceptación (HU-04):
1. Dado un proyecto abierto, la Vista previa muestra el árbol de módulos .py y,
   por cada función pública: firma, si tiene tipos, si tiene docstring y número
   de ramas (if/else, try/except).
2. La información se obtiene por análisis estático (AST): el código del usuario
   no se ejecuta.
3. La carpeta tests/ existente y la carpeta .pyagent/ se ignoran.
4. Las funciones sin docstring se marcan "⚠ falta" con el aviso: el valor esperado
   no tendrá fuente (oráculo débil).
5. Un archivo con error de sintaxis se marca "no se pudo analizar" sin detener el
   análisis del resto.
6. La Vista previa muestra el resumen del proyecto: módulos encontrados,
   funciones públicas, errores (archivos no analizables) e inconsistencias
   (funciones sin docstring o sin tipos), con su porcentaje sobre el total de
   funciones; los valores coinciden con el JSON de EN-02.
7. Los módulos se listan priorizados: primero los que tienen más funciones con
   ramas.
"""

from __future__ import annotations

from pathlib import Path

from pyagent.analysis import analizar_proyecto
from pyagent.proyectos.vista_previa import (
    AVISO_ORACULO_DEBIL,
    ETIQUETA_FALTA_DOCSTRING,
    ETIQUETA_NO_ANALIZABLE,
    generar_vista_previa,
    priorizar_modulos,
)


def _crear_archivo(raiz: Path, ruta_relativa: str, contenido: str) -> Path:
    destino = raiz / ruta_relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    return destino


def test_criterio_1_arbol_modulos_y_funciones_con_firma_tipos_docstring_ramas(
    tmp_path: Path,
) -> None:
    codigo = '''"""Módulo de prueba."""

def procesar(x: int, y: str = "defecto") -> bool:
    """Documentación completa."""
    if x > 0:
        return True
    elif y == "test":
        return False
    return False

def sin_doc(a: float) -> float:
    return a * 2.0
'''
    _crear_archivo(tmp_path, "services/servicio.py", codigo)

    vista = generar_vista_previa(tmp_path)

    assert vista["ok"] is True
    assert len(vista["modulos"]) == 1

    mod = vista["modulos"][0]
    assert mod["ruta"] == "services/servicio.py"
    assert len(mod["funciones"]) == 2

    f1 = mod["funciones"][0]
    assert f1["nombre"] == "procesar"
    assert f1["firma"] == "(x: int, y: str='defecto') -> bool"
    assert f1["tipada"] is True
    assert f1["docstring"] == "Documentación completa."
    assert f1["ramas"] == 2
    assert f1["critica_propuesta"] is True

    f2 = mod["funciones"][1]
    assert f2["nombre"] == "sin_doc"
    assert f2["firma"] == "(a: float) -> float"
    assert f2["tipada"] is True
    assert f2["docstring"] is None
    assert f2["ramas"] == 0
    assert f2["critica_propuesta"] is False


def test_criterio_2_analisis_es_estatico_no_ejecuta_codigo_usuario(
    tmp_path: Path,
) -> None:
    archivo_trampa = tmp_path / "ejecutado.txt"
    codigo_peligroso = f'''import sys

with open(r"{archivo_trampa}", "w") as f:
    f.write("PELIGRO")

def saludar(nombre: str) -> str:
    """Saluda."""
    return f"Hola {{nombre}}"
'''
    _crear_archivo(tmp_path, "peligro.py", codigo_peligroso)

    vista = generar_vista_previa(tmp_path)

    assert vista["ok"] is True
    assert not archivo_trampa.exists()


def test_criterio_3_ignora_carpeta_tests_y_pyagent(tmp_path: Path) -> None:
    _crear_archivo(
        tmp_path, "app/nucleo.py", "def nucleo() -> int:\n    return 42\n"
    )
    _crear_archivo(
        tmp_path, "tests/test_nucleo.py", "def test_f():\n    assert True\n"
    )
    _crear_archivo(
        tmp_path,
        ".pyagent/specs/nucleo.spec.py",
        "def spec():\n    pass\n",
    )
    _crear_archivo(
        tmp_path, "app/tests/test_interno.py", "def test_i():\n    pass\n"
    )

    vista = generar_vista_previa(tmp_path)

    rutas = [m["ruta"] for m in vista["modulos"]]
    assert rutas == ["app/nucleo.py"]


def test_criterio_4_funciones_sin_docstring_tienen_aviso_oraculo_debil(
    tmp_path: Path,
) -> None:
    codigo = """def con_doc(x: int) -> int:
    '''Docstring.'''
    return x

def sin_doc(y: int) -> int:
    return y * 2
"""
    _crear_archivo(tmp_path, "modulo.py", codigo)

    vista = generar_vista_previa(tmp_path)
    funciones = vista["modulos"][0]["funciones"]

    f_con = next(f for f in funciones if f["nombre"] == "con_doc")
    f_sin = next(f for f in funciones if f["nombre"] == "sin_doc")

    assert f_con["etiqueta_docstring"] == "✓"
    assert f_con["aviso_docstring"] is None

    assert f_sin["etiqueta_docstring"] == ETIQUETA_FALTA_DOCSTRING
    assert f_sin["aviso_docstring"] == AVISO_ORACULO_DEBIL
    assert "oráculo débil" in f_sin["aviso_docstring"]


def test_criterio_5_archivo_con_error_sintaxis_se_marca_no_se_pudo_analizar(
    tmp_path: Path,
) -> None:
    _crear_archivo(
        tmp_path,
        "valido.py",
        "def correcto() -> str:\n    '''Ok.'''\n    return 'ok'\n",
    )
    _crear_archivo(tmp_path, "roto.py", "def mal(:\n    pass\n")

    vista = generar_vista_previa(tmp_path)

    assert len(vista["modulos"]) == 1
    assert vista["modulos"][0]["ruta"] == "valido.py"

    assert len(vista["errores"]) == 1
    err = vista["errores"][0]
    assert err["ruta"] == "roto.py"
    assert err["tipo"] == "SyntaxError"
    assert err["etiqueta"] == ETIQUETA_NO_ANALIZABLE
    assert err["linea"] == 1


def test_criterio_6_resumen_coincide_con_json_en02(tmp_path: Path) -> None:
    _crear_archivo(
        tmp_path,
        "modulo1.py",
        '''def f1(a: int) -> int:
    """Documentada y tipada."""
    return a

def f2(b):
    # Sin docstring y sin tipos
    return b
''',
    )
    _crear_archivo(
        tmp_path,
        "modulo2.py",
        '''def f3(c: str):
    """Documentada pero sin tipo de retorno."""
    return c
''',
    )
    _crear_archivo(tmp_path, "roto.py", "def error(:\n    pass\n")

    en02_resultado = analizar_proyecto(tmp_path)
    vista = generar_vista_previa(tmp_path)

    # El resumen de la vista previa debe coincidir exactamente con el JSON de EN-02
    assert vista["resumen"] == en02_resultado["resumen"]

    resumen = vista["resumen"]
    assert resumen["total_modulos"] == 2
    assert resumen["total_funciones_publicas"] == 3
    assert resumen["total_errores"] == 1

    inconsistencias = resumen["inconsistencias"]
    assert inconsistencias["sin_docstring"]["cantidad"] == 1
    assert inconsistencias["sin_docstring"]["porcentaje"] == 33.3

    assert inconsistencias["sin_tipos"]["cantidad"] == 2
    assert inconsistencias["sin_tipos"]["porcentaje"] == 66.7

    assert inconsistencias["con_alguna"]["cantidad"] == 2
    assert inconsistencias["con_alguna"]["porcentaje"] == 66.7


def test_criterio_7_modulos_listados_priorizados_mas_funciones_con_ramas_primero(
    tmp_path: Path,
) -> None:
    # modulo_a: 1 función con ramas
    _crear_archivo(
        tmp_path,
        "a.py",
        """def fa1(x):
    if x:
        return 1
    return 0
""",
    )

    # modulo_b: 3 funciones con ramas
    _crear_archivo(
        tmp_path,
        "b.py",
        """def fb1(x):
    if x:
        return 1
    return 0

def fb2(x):
    for i in x:
        pass

def fb3(x):
    try:
        return 1
    except ValueError:
        return 0
""",
    )

    # modulo_c: 4 funciones sin ramas (todas lineales)
    _crear_archivo(
        tmp_path,
        "c.py",
        """def fc1():
    return 1

def fc2():
    return 2

def fc3():
    return 3

def fc4():
    return 4
""",
    )

    vista = generar_vista_previa(tmp_path)

    rutas = [m["ruta"] for m in vista["modulos"]]
    # Prioridad: b.py (3 fns con ramas), a.py (1 fn con ramas), c.py (0 fns con ramas)
    assert rutas == ["b.py", "a.py", "c.py"]


def test_priorizar_modulos_empate_usa_total_ramas_luego_ruta() -> None:
    m1 = {
        "ruta": "z.py",
        "funciones": [{"ramas": 2}, {"ramas": 0}],
    }
    m2 = {
        "ruta": "a.py",
        "funciones": [{"ramas": 10}, {"ramas": 0}],
    }
    # Ambos tienen 1 función con ramas, pero m2 tiene 10 ramas en total vs m1 con 2
    ordenados = priorizar_modulos([m1, m2])
    assert [m["ruta"] for m in ordenados] == ["a.py", "z.py"]


def test_carpeta_invalida_retorna_ok_false(tmp_path: Path) -> None:
    inexistente = tmp_path / "no_existe"
    vista = generar_vista_previa(inexistente)
    assert vista["ok"] is False
    assert "no es una carpeta" in vista["error"].lower()
    assert vista["resumen"]["total_modulos"] == 0

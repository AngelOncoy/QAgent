"""#149: las pruebas guardadas triviales no cuentan como regresiones válidas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import construir_historial
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.regresion import (
    ejecutar_regresion,
    huellas_de_objetivos,
    objetivos_repetibles,
)
from qagent.sandbox import ResultadoSandbox

COBERTURA = {
    "totals": {"percent_covered": 100.0, "num_branches": 0, "covered_branches": 0}
}


def _caso_trivial() -> dict:
    return {
        "id": "sin_argumentos",
        "entrada": {},
        "excepcion": "TypeError",
        "origen": "firma",
        "categoria": "error",
    }


def _caso_valido(entrada: dict | None = None) -> dict:
    return {
        "id": "comportamiento",
        "entrada": entrada or {"x": 2},
        "valor_esperado": 4,
        "origen": "docstring",
        "categoria": "normal",
    }


def _caso_typeerror_legitimo() -> dict:
    return {
        "id": "tipo_invalido",
        "entrada": {"x": "texto"},
        "excepcion": "TypeError",
        "origen": "docstring",
        "categoria": "error",
    }


def _contrato(objetivo: str, firma: str, casos: list[dict]) -> dict:
    return {
        "version": "2",
        "modulo": "modulo.py",
        "huella": "1" * 64,
        "tipo": "funcion",
        "objetivo": objetivo,
        "firma": firma,
        "critical": False,
        "llama_a": [],
        "casos": casos,
    }


@pytest.fixture
def proyecto(tmp_path: Path):
    fuente = """\
def trivial(a, b):
    return a + b

def valida(x):
    \"\"\"Devuelve x multiplicado por dos.\"\"\"
    return x * 2

def typeerror_legitimo(x):
    \"\"\"Lanza TypeError cuando x no es entero.\"\"\"
    if not isinstance(x, int):
        raise TypeError("x debe ser entero")
    return x * 2

def mixta(x):
    \"\"\"Devuelve x multiplicado por dos.\"\"\"
    return x * 2
"""
    (tmp_path / "modulo.py").write_text(fuente, encoding="utf-8")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    return tmp_path, almacen, config


def _guardar(
    proyecto,
    objetivo: str,
    firma: str,
    casos: list[dict],
    codigo: str,
) -> tuple[Path, Path]:
    raiz, almacen, _ = proyecto
    contrato = _contrato(objetivo, firma, casos)
    archivo = f"test_{objetivo}.py"
    ruta_prueba = almacen.guardar_prueba_aprobada(archivo, codigo)
    huella = huellas_de_objetivos(raiz)[("modulo.py", objetivo)]
    spec = almacen.guardar_spec(
        contrato,
        "20261026-144244-4beb",
        archivo_prueba=archivo,
        huella_objetivo=huella,
    )
    return ruta_prueba, almacen.carpeta_specs / f"{spec['id']}.json"


def _ejecutar(proyecto, llamadas: list[str]):
    raiz, almacen, config = proyecto

    def ejecutor(_imagen, _proyecto, tests, _modulo):
        llamadas.append(next(Path(tests).glob("test_*.py")).name)
        return ResultadoSandbox(0, "1 passed", "", COBERTURA)

    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_regresion(
        raiz,
        "reg",
        config,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen",
        ejecutor=ejecutor,
    )
    carpeta = almacen.carpeta_run(run_id)
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    return resumen, results


def test_unico_typeerror_de_firma_se_excluye_sin_docker_y_sin_borrar(proyecto) -> None:
    prueba, spec = _guardar(
        proyecto,
        "trivial",
        "(a, b)",
        [_caso_trivial()],
        "def test_trivial():\n    pass\n",
    )
    prueba_antes, spec_antes = prueba.read_bytes(), spec.read_bytes()
    llamadas: list[str] = []

    resumen, results = _ejecutar(proyecto, llamadas)

    assert llamadas == []
    assert resumen.aceptadas == 0
    assert resumen.objetivos_omitidos == 1
    assert resumen.total_seleccionados == 1
    assert resumen.total_elegibles == 0
    assert resumen.total_procesados == 0
    assert results["objetivos"] == []
    assert results["objetivos_omitidos"] == 1
    assert results["tipo_terminacion"] == "completada"
    assert results["resumen"]["pass_rate"] == 0.0
    [omitida] = results["omitidos"]
    assert omitida["objetivo"] == "trivial"
    assert "TypeError provocado por argumentos incorrectos" in omitida["motivo"]
    assert "se conservó" in omitida["motivo"]
    assert prueba.read_bytes() == prueba_antes
    assert spec.read_bytes() == spec_antes
    assert objetivos_repetibles(proyecto[0]) == []
    [corrida] = construir_historial(proyecto[0])["corridas"]
    assert corrida["total_seleccionados"] == 1
    assert corrida["total_elegibles"] == 0
    assert corrida["total_procesados"] == 0
    assert corrida["objetivos_omitidos"] == 1
    assert corrida["pruebas_aprobadas"] == 0


@pytest.mark.parametrize(
    ("objetivo", "firma", "casos"),
    [
        ("valida", "(x)", [_caso_valido()]),
        ("typeerror_legitimo", "(x)", [_caso_typeerror_legitimo()]),
        ("valida", "(x=1)", [_caso_typeerror_legitimo()]),
        ("valida", "(*args, **kwargs)", [_caso_typeerror_legitimo()]),
    ],
)
def test_pruebas_validas_y_typeerror_legitimos_siguen_ejecutandose(
    proyecto, objetivo, firma, casos
) -> None:
    _guardar(proyecto, objetivo, firma, casos, "def test_valida():\n    pass\n")
    llamadas: list[str] = []

    resumen, results = _ejecutar(proyecto, llamadas)

    assert len(llamadas) == 1
    assert resumen.aceptadas == 1
    assert resumen.objetivos_omitidos == 0
    assert results["resumen"]["aceptadas"] == 1


def test_regresion_mixta_ejecuta_la_prueba_valida_y_excluye_la_trivial(
    proyecto,
) -> None:
    trivial, spec_trivial = _guardar(
        proyecto,
        "trivial",
        "(a, b)",
        [_caso_trivial()],
        "def test_trivial():\n    pass\n",
    )
    valida, spec_valida = _guardar(
        proyecto,
        "valida",
        "(x)",
        [_caso_valido()],
        "def test_valida():\n    pass\n",
    )
    originales = {
        ruta: ruta.read_bytes() for ruta in (trivial, spec_trivial, valida, spec_valida)
    }
    llamadas: list[str] = []

    resumen, results = _ejecutar(proyecto, llamadas)

    assert llamadas == ["test_valida.py"]
    assert resumen.total_seleccionados == 2
    assert resumen.total_elegibles == 1
    assert resumen.total_procesados == 1
    assert resumen.objetivos_omitidos == 1
    assert resumen.aceptadas == 1
    assert results["resumen"]["pass_rate"] == 100.0
    [corrida] = construir_historial(proyecto[0])["corridas"]
    assert corrida["total_seleccionados"] == 2
    assert corrida["total_elegibles"] == 1
    assert corrida["total_procesados"] == 1
    assert corrida["objetivos_omitidos"] == 1
    assert corrida["pruebas_aprobadas"] == 1
    assert all(ruta.read_bytes() == contenido for ruta, contenido in originales.items())


def test_spec_mixta_conserva_y_contabiliza_solo_casos_validos(proyecto) -> None:
    prueba, spec = _guardar(
        proyecto,
        "mixta",
        "(x)",
        [_caso_valido(), _caso_trivial()],
        "def test_valido():\n    pass\n\ndef test_trivial():\n    pass\n",
    )
    prueba_antes, spec_antes = prueba.read_bytes(), spec.read_bytes()
    llamadas: list[str] = []

    resumen, results = _ejecutar(proyecto, llamadas)

    assert llamadas == ["test_mixta.py"]
    assert resumen.aceptadas == 1
    [objetivo] = results["objetivos"]
    assert objetivo["casos_por_categoria"] == {
        "normal": 1,
        "limite": 0,
        "error": 0,
    }
    assert prueba.read_bytes() == prueba_antes
    assert spec.read_bytes() == spec_antes


def test_spec_incompleta_o_malformada_no_se_borra_ni_se_clasifica_por_texto(
    proyecto,
) -> None:
    raiz, almacen, _ = proyecto
    prueba = almacen.guardar_prueba_aprobada(
        "test_historica.py", "import pytest\n# TypeError no basta para clasificar\n"
    )
    spec = almacen.carpeta_specs / "historica.json"
    spec.write_text(
        '{"estado":"vigente","archivo_prueba":"test_historica.py"}', encoding="utf-8"
    )
    originales = prueba.read_bytes(), spec.read_bytes()

    assert objetivos_repetibles(raiz) == []
    assert almacen.tiene_pruebas_aprobadas() is False
    assert (prueba.read_bytes(), spec.read_bytes()) == originales

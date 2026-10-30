"""Arma los casos fijos del Explicador en `casos/` (SPK #167). Sin red, Docker ni tokens.

Uso, desde la raíz del repositorio:

    python bench_explicador/preparar_casos.py

1. Corre `bench/banco_mvp.py` con la IA simulada y las salidas de pytest grabadas
   (`tests/orchestrator/grabaciones/`): de ahí salen los 3 bugs de código, con lo que
   pytest dijo de verdad.
2. Agrega tres objetivos de `banco_explicador.py` con su traza completa de intentos:
   una prueba estancada, un Assertion Laundering y uno sin veredicto. El feedback del
   laundering lo escribe el mismo comparador que usa el Reviewer.
3. Quita la ruta absoluta del proyecto y fija `run_id` y fechas para que el resultado
   no dependa de la máquina.

Solo hace falta repetirlo si cambian el banco, las grabaciones o el formato de
`results.json` o `detalle.json`; la medición lee los archivos ya versionados.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))  # para `tests.orchestrator.ejecutor_grabado`

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.analysis.laundering import comparar_aserciones
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from tests.orchestrator.ejecutor_grabado import EjecutorGrabado

CASOS = Path(__file__).resolve().parent / "casos"
RUN_ID = "spk167-banco-explicador"
FECHA = "2026-10-30T00:00:00-05:00"
MODULO = "banco_explicador.py"
ENTORNO = {
    "imagen": "qagent-sandbox:base",
    "comando": (
        "pytest /work/tests --cov=banco_explicador --cov-branch "
        "--cov-report=json:/out/coverage.json --junitxml=/out/junit.xml "
        "-p no:cacheprovider"
    ),
    "plataforma": "linux",
    "python": "3.11.9",
    "pytest": "9.1.1",
    "limites": {"cpus": 4.0, "memoria": "3g", "timeout_s": 120},
}


def correr_banco_grabado() -> tuple[dict[str, Any], dict[str, Any]]:
    """results.json y detalle.json de `bench/` con la IA simulada y pytest grabado."""
    with tempfile.TemporaryDirectory(prefix="qagent-spk167-") as temporal:
        carpeta = Path(temporal) / "banco"
        shutil.copytree(
            RAIZ / "bench",
            carpeta,
            ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent"),
        )
        almacen = AlmacenProyecto(carpeta)
        almacen.inicializar()
        config = cargar_configuracion(
            RUTA_CONFIG, "no-existe.env", simulado=True
        ).config
        run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
        resumen = ejecutar_corrida(
            carpeta,
            "deep",
            config,
            None,
            simulado=True,
            run_id=run_id,
            preparar_imagen=lambda ruta: ENTORNO["imagen"],
            ejecutor=EjecutorGrabado(),
        )
        if resumen.estado != "fin":
            raise SystemExit(f"La corrida grabada no terminó: {resumen.motivo}")
        carpeta_run = almacen.carpeta_run(run_id)
        results = json.loads((carpeta_run / "results.json").read_text("utf-8"))
        detalle = json.loads((carpeta_run / "detalle.json").read_text("utf-8"))
    return results, detalle


# --- Las tres trazas que el banco MVP no da ------------------------------------------


def _salida_pytest(nombre: str, traza: str, error: str) -> str:
    return (
        "============================= test session starts "
        "=============================\n"
        "platform linux -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0\n"
        "rootdir: /work\ncollected 1 item\n\n"
        "../tests/test_generado.py E"
        "                                                [100%]\n\n"
        "==================================== ERRORS "
        "====================================\n"
        f"______________________ ERROR at setup of {nombre} ______________________\n"
        f"{traza}\n"
        "=========================== short test summary info "
        "============================\n"
        f"ERROR ../tests/test_generado.py::{nombre} - {error}\n"
        "============================== 1 error in 0.08s "
        "==============================="
    )


def _ejecucion_con_error(
    codigo: str, nombre: str, tipo_error: str, mensaje: str, linea: int, traza: str
) -> dict[str, Any]:
    salida = _salida_pytest(nombre, traza, f"{tipo_error}: {mensaje}")
    return {
        "exit_code": 1,
        "duracion_s": 1.4,
        "duracion_pytest_s": 0.08,
        "timeout": False,
        "oom": False,
        "salida": salida,
        "codigo_test": codigo,
        "totales": {
            "total": 1,
            "pasaron": 0,
            "fallaron": 0,
            "errores": 1,
            "omitidos": 0,
        },
        "casos": [
            {
                "nombre": nombre,
                "ruta": "tests.test_generado",
                "resultado": "error",
                "duracion_s": 0.001,
                "mensaje": f"{tipo_error}: {mensaje}",
                "tipo_error": tipo_error,
                "archivo": "tests/test_generado.py",
                "linea": linea,
                "traza": traza,
                "pila": [
                    {
                        "archivo": "tests/test_generado.py",
                        "linea": linea,
                        "detalle": tipo_error,
                    }
                ],
            }
        ],
        "lineas_sin_cubrir": [],
        "entorno": ENTORNO,
    }


def _intento(
    numero: int,
    decision: str,
    feedback: str,
    hash_error: str,
    *,
    ejecucion: dict[str, Any] | None,
    laundering: bool = False,
) -> dict[str, Any]:
    return {
        "intento": numero,
        "decision": decision,
        "estado_sandbox": "fallo",
        "tipo_fallo": "error_test",
        "laundering_detectado": laundering,
        "feedback": feedback,
        "hash_error": hash_error,
        "cobertura": None,
        "ejecucion": ejecucion,
        "duracion_s": 9.0,
        "generacion_s": 7.5,
        "revision_s": 1.5,
    }


def _contrato(objetivo: str, firma: str, casos: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": "3",
        "lenguaje": "python",
        "framework_pruebas": "pytest",
        "modulo": MODULO,
        "tipo": "funcion",
        "objetivo": objetivo,
        "firma": firma,
        "critical": False,
        "llama_a": [],
        "casos": casos,
    }


def estancada() -> dict[str, Any]:
    """`total_con_impuesto`: el test no logra construir el carrito; se corta al repetir."""
    base = (
        "from banco_explicador import Carrito, total_con_impuesto\n\n\n"
        "def test_dos_productos():\n"
        "    carrito = {carrito}\n"
        "    assert total_con_impuesto(carrito) == 23.6\n"
    )
    sin_tasas = base.format(carrito='Carrito([("a", 10.0), ("b", 10.0)])')
    tasas_vacias = base.format(carrito='Carrito([("a", 10.0), ("b", 10.0)], tasas={})')
    error_1 = (
        "TypeError",
        "Carrito.__init__() missing 1 required keyword-only argument: 'tasas'",
    )
    error_2 = ("ValueError", "el carrito necesita las tasas de su región")

    def traza(codigo_carrito: str, tipo: str, mensaje: str) -> str:
        return (
            "def test_dos_productos():\n"
            f">       carrito = {codigo_carrito}\n"
            f"E       {tipo}: {mensaje}\n\n"
            f"../tests/test_generado.py:5: {tipo}"
        )

    t1 = traza('Carrito([("a", 10.0), ("b", 10.0)])', *error_1)
    t2 = traza('Carrito([("a", 10.0), ("b", 10.0)], tasas={})', *error_2)
    e1 = _ejecucion_con_error(sin_tasas, "test_dos_productos", *error_1, 5, t1)
    e2 = _ejecucion_con_error(tasas_vacias, "test_dos_productos", *error_2, 5, t2)
    intentos = [
        _intento(1, "retry", e1["salida"], "a1" * 32, ejecucion=e1),
        _intento(2, "retry", e2["salida"], "b2" * 32, ejecucion=e2),
        # Mismo error que el intento 2: el orquestador corta por error repetido.
        _intento(3, "stalled", e2["salida"], "b2" * 32, ejecucion=copy.deepcopy(e2)),
    ]
    contrato = _contrato(
        "total_con_impuesto",
        "(carrito: Carrito) -> float",
        [
            {
                "id": "dos_productos",
                "descripcion": "Dos productos de 10.0 con impuesto general de 18 %",
                "entrada": {"carrito": "dos productos de 10.0, tasa general 0.18"},
                "valor_esperado": 23.6,
                "origen": "docstring",
                "categoria": "normal",
            }
        ],
    )
    return {
        "objetivo": {
            "decision": "stalled",
            "motivo_estancado": "error_repetido",
            "motivo_sin_veredicto": None,
            "laundering_detectado": False,
            "iteraciones": 3,
        },
        "funcion": {
            "contrato": contrato,
            "codigo": tasas_vacias,
            "traza": e2["salida"],
            "intentos": intentos,
        },
    }


def laundering() -> dict[str, Any]:
    """`calcular_envio`: tras un error de import, el test debilita la comprobación."""
    original = (
        "import pytest\n\n"
        "from banco_explicador import calcular_envios\n\n\n"
        "def test_envio_normal():\n"
        "    assert calcular_envio(peso_kg=3.0) == 11.0\n\n\n"
        "def test_envio_express():\n"
        "    assert calcular_envio(peso_kg=3.0, express=True) == 22.0\n\n\n"
        "def test_peso_negativo():\n"
        "    with pytest.raises(ValueError):\n"
        "        calcular_envio(peso_kg=-1.0)\n"
    )
    debilitado = (
        "import pytest\n\n"
        "from banco_explicador import calcular_envio\n\n\n"
        "def test_envio_normal():\n"
        "    assert calcular_envio(peso_kg=3.0) == 11.0\n\n\n"
        "def test_envio_express():\n"
        "    assert calcular_envio(peso_kg=3.0, express=True) > 0\n\n\n"
        "def test_peso_negativo():\n"
        "    with pytest.raises(ValueError):\n"
        "        calcular_envio(peso_kg=-1.0)\n"
    )
    comparacion = comparar_aserciones(original, debilitado)
    if not comparacion.es_laundering:
        raise SystemExit(
            "El comparador ya no ve laundering en el caso de calcular_envio"
        )
    error = (
        "ImportError",
        (
            "cannot import name 'calcular_envios' from 'banco_explicador' "
            "(/work/proyecto/banco_explicador.py). Did you mean: 'calcular_envio'?"
        ),
    )
    traza = (
        "../tests/test_generado.py:3: in <module>\n"
        "    from banco_explicador import calcular_envios\n"
        f"E   {error[0]}: {error[1]}"
    )
    e1 = _ejecucion_con_error(original, "test_envio_normal", *error, 3, traza)
    intentos = [
        _intento(1, "retry", e1["salida"], "c3" * 32, ejecucion=e1),
        _intento(
            2, "retry", comparacion.resumen, "d4" * 32, ejecucion=None, laundering=True
        ),
        _intento(
            3,
            "stalled",
            comparacion.resumen,
            "d4" * 32,
            ejecucion=None,
            laundering=True,
        ),
    ]
    contrato = _contrato(
        "calcular_envio",
        "(peso_kg: float, express: bool = False) -> float",
        [
            {
                "id": "envio_normal",
                "descripcion": "3 kg con envío normal cuesta 11.0",
                "entrada": {"peso_kg": 3.0},
                "valor_esperado": 11.0,
                "origen": "docstring",
                "categoria": "normal",
            },
            {
                "id": "envio_express",
                "descripcion": "3 kg con envío express cuesta el doble: 22.0",
                "entrada": {"peso_kg": 3.0, "express": True},
                "valor_esperado": 22.0,
                "origen": "docstring",
                "categoria": "normal",
            },
            {
                "id": "peso_negativo",
                "entrada": {"peso_kg": -1.0},
                "excepcion": "ValueError",
                "origen": "docstring",
                "categoria": "error",
            },
        ],
    )
    return {
        "objetivo": {
            "decision": "stalled",
            "motivo_estancado": "error_repetido",
            "motivo_sin_veredicto": None,
            "laundering_detectado": True,
            "iteraciones": 3,
        },
        "funcion": {
            "contrato": contrato,
            "codigo": debilitado,
            "traza": comparacion.resumen,
            "intentos": intentos,
        },
    }


def sin_veredicto() -> dict[str, Any]:
    """`convertir_moneda`: un error del test y luego el LLM no responde a tiempo."""
    codigo = (
        "from banco_explicador import convertir_moneda\n\n\n"
        "def test_conversion_normal():\n"
        "    assert convertir_moneda(monto=100.0, tasa=3.75) == pytest.approx(375.0)\n"
    )
    error = ("NameError", "name 'pytest' is not defined")
    traza = (
        "def test_conversion_normal():\n"
        ">       assert convertir_moneda(monto=100.0, tasa=3.75) == "
        "pytest.approx(375.0)\n"
        f"E       {error[0]}: {error[1]}\n\n"
        f"../tests/test_generado.py:5: {error[0]}"
    )
    e1 = _ejecucion_con_error(codigo, "test_conversion_normal", *error, 5, traza)
    contrato = _contrato(
        "convertir_moneda",
        "(monto: float, tasa: float) -> float",
        [
            {
                "id": "conversion_normal",
                "descripcion": "100.0 con tasa 3.75 da 375.0",
                "entrada": {"monto": 100.0, "tasa": 3.75},
                "valor_esperado": 375.0,
                "origen": "docstring",
                "categoria": "normal",
            },
            {
                "id": "tasa_cero",
                "entrada": {"monto": 100.0, "tasa": 0.0},
                "excepcion": "ValueError",
                "origen": "docstring",
                "categoria": "error",
            },
        ],
    )
    return {
        "objetivo": {
            "decision": None,
            "motivo_estancado": None,
            "motivo_sin_veredicto": "tiempo_agotado",
            "laundering_detectado": False,
            "iteraciones": 2,
        },
        "funcion": {
            "contrato": contrato,
            "codigo": codigo,
            "traza": e1["salida"],
            # El intento 2 no llegó a revisarse: el Generator no respondió a tiempo.
            "intentos": [_intento(1, "retry", e1["salida"], "e5" * 32, ejecucion=e1)],
        },
    }


TRAZAS = {
    "total_con_impuesto": estancada,
    "calcular_envio": laundering,
    "convertir_moneda": sin_veredicto,
}


def agregar_trazas(results: dict[str, Any], detalle: dict[str, Any]) -> None:
    """Suma a la corrida del banco los tres objetivos de `banco_explicador.py`."""
    plantilla = next(
        o for o in results["objetivos"] if o["decision"] == "bug_detectado"
    )
    for nombre, armar in TRAZAS.items():
        caso = armar()
        datos = caso["objetivo"]
        objetivo = copy.deepcopy(plantilla)
        objetivo.update(
            modulo=MODULO,
            funcion=nombre,
            decision=datos["decision"],
            motivo_estancado=datos["motivo_estancado"],
            motivo_sin_veredicto=datos["motivo_sin_veredicto"],
            laundering_detectado=datos["laundering_detectado"],
            controles={
                "sintaxis": True,
                "sandbox": False,
                "aserciones": not datos["laundering_detectado"],
                "cobertura": False,
                "mutation": None,
            },
            casos_por_categoria=None,
            tiempos_intentos=[],
        )
        objetivo["metricas"] = {
            **objetivo["metricas"],
            "paso": False,
            "cobertura_lineas": None,
            "iteraciones": datos["iteraciones"],
        }
        results["objetivos"].append(objetivo)
        detalle["funciones"].append(
            {"modulo": MODULO, "funcion": nombre, **caso["funcion"]}
        )

    resumen = results["resumen"]
    objetivos = results["objetivos"]
    resumen["total_funciones"] = resumen["total_seleccionados"] = len(objetivos)
    resumen["total_elegibles"] = resumen["total_procesados"] = len(objetivos)
    resumen["stalled"] = sum(o["decision"] == "stalled" for o in objetivos)
    resumen["sin_veredicto"] = sum(o["decision"] is None for o in objetivos)
    resumen["pass_rate"] = round(100 * resumen["aceptadas"] / len(objetivos), 1)
    for clave in ("total_seleccionados", "total_elegibles", "total_procesados"):
        results[clave] = len(objetivos)


def fijar_datos_de_maquina(results: dict[str, Any], detalle: dict[str, Any]) -> None:
    """Sin rutas absolutas ni datos que cambien con cada corrida."""
    results.update(run_id=RUN_ID, fecha=FECHA, proyecto="banco")
    detalle["run_id"] = RUN_ID
    detalle["entorno"] = {**detalle["entorno"], "imagen": ENTORNO["imagen"]}
    texto = json.dumps([results, detalle])
    for marca in (":\\\\", "C:/", "/Users/", "/home/", "AppData"):
        if marca in texto:
            raise SystemExit(f"Quedó una ruta de la máquina en los casos: {marca}")


def main() -> None:
    results, detalle = correr_banco_grabado()
    agregar_trazas(results, detalle)
    fijar_datos_de_maquina(results, detalle)
    contracts.validar(contracts.DETALLE, detalle)
    CASOS.mkdir(exist_ok=True)
    for nombre, datos in (("results.json", results), ("detalle.json", detalle)):
        (CASOS / nombre).write_text(
            json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    no_aceptados = [
        o["funcion"] for o in results["objetivos"] if o["decision"] != "accept"
    ]
    print(f"Casos en {CASOS}: {len(no_aceptados)} hallazgos: {', '.join(no_aceptados)}")


if __name__ == "__main__":
    main()

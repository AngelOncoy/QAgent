"""Rutas acotadas y lectura histórica sin depender del registro de Windows (#268)."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import (
    AlmacenProyecto,
    disco,
    id_de_modulo,
    id_de_spec,
    nombre_prueba,
)
from qagent.almacenamiento.proyecto import LIMITE_ID_ARCHIVO, huella_de_prueba
from qagent.config import cargar_configuracion
from qagent.orchestrator.regresion import (
    _specs_aprobadas,
    ejecutar_regresion,
    huellas_de_objetivos,
)
from qagent.sandbox import ResultadoSandbox

MODULO = "src/main/java/org/qagent/bench/BancoDefectuoso.java"
OBJETIVO = "BancoDefectuoso.calcularTotalConImpuesto"
ANTERIOR = "src_main_java_org_qagent_bench_BancoDefectuoso_java__BancoDefectuoso_calcularTotalConImpuesto"
CODIGO = "// Prueba Java grabada; este test solo guarda texto, no ejecuta Java.\n"


def contrato_java() -> dict:
    """Contrato de ejemplo válido con identidad larga y esperado independiente."""
    contrato = {
        "version": "3",
        "lenguaje": "java",
        "framework_pruebas": "junit5",
        "modulo": MODULO,
        "huella": "a" * 64,
        "tipo": "funcion",
        "objetivo": OBJETIVO,
        "firma": "public static double calcularTotalConImpuesto(double subtotal, double porcentaje)",
        "critical": False,
        "llama_a": [],
        "casos": [
            {
                "id": "normal",
                "entrada": {"subtotal": 100, "porcentaje": 18},
                "valor_esperado": 118,
                "origen": "docstring",
                "categoria": "normal",
            }
        ],
    }
    contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)
    return contrato


@pytest.fixture
def historial_corto():
    """Las fixtures históricas caben también cuando Windows no admite rutas largas."""
    carpeta = Path(__file__).resolve().parents[2] / ".qagent"
    carpeta.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="h268-", dir=carpeta) as temporal:
        yield Path(temporal)


def test_temporal_no_repite_nombre_y_sigue_siendo_atomico(tmp_path, monkeypatch):
    """Observa el temporal real, en la carpeta destino, antes de os.replace."""
    destino = tmp_path / ("evidencia_" + "x" * 90 + ".json")
    originales = []
    reemplazar = disco.os.replace

    def observar(temporal, final):
        temporal = Path(temporal)
        assert temporal.parent == destino.parent
        assert temporal.name.startswith(".qa-")
        assert len(temporal.name) <= 20
        assert destino.name not in temporal.name
        assert temporal.read_text("utf-8") == "evidencia íntegra"
        originales.append(temporal)
        reemplazar(temporal, final)

    monkeypatch.setattr(disco.os, "replace", observar)
    disco.escribir_texto_atomico(destino, "evidencia íntegra")
    assert destino.read_text("utf-8") == "evidencia íntegra"
    assert originales and not originales[0].exists()


def test_error_de_reemplazo_conserva_destino_y_limpia_temporal(tmp_path, monkeypatch):
    """Un error no destruye la evidencia previa ni deja archivos a medio escribir."""
    destino = tmp_path / "evidencia.json"
    destino.write_text("anterior", encoding="utf-8")

    def fallar(*args):
        raise PermissionError("reemplazo bloqueado")

    monkeypatch.setattr(disco.os, "replace", fallar)
    with pytest.raises(PermissionError):
        disco.escribir_texto_atomico(destino, "nuevo")
    assert destino.read_text("utf-8") == "anterior"
    assert list(tmp_path.iterdir()) == [destino]


def test_ids_largos_estables_acotados_y_distintos():
    """El hash considera la identidad completa, incluso diferencias al final."""
    modulo = "src/main/java/" + "paquete/" * 25 + "Banco.java"
    primero = id_de_spec(modulo, OBJETIVO)
    assert len(primero) == LIMITE_ID_ARCHIVO
    assert primero == id_de_spec(modulo, OBJETIVO)
    assert primero != id_de_spec(modulo, OBJETIVO + "Otro")
    assert primero != id_de_spec(modulo.replace("paquete/", "paquete-/", 1), OBJETIVO)
    assert len(nombre_prueba(primero)) <= LIMITE_ID_ARCHIVO + len("test_.py")
    assert len(nombre_prueba("x" * 400)) <= LIMITE_ID_ARCHIVO + len("test_.py")
    assert len(id_de_modulo(modulo)) <= LIMITE_ID_ARCHIVO
    assert id_de_spec("banco.py", "f") == "banco_py__f"
    assert nombre_prueba("banco_py__f") == "test_banco_py__f.py"
    assert id_de_modulo("banco.py") == "banco"


def test_carpeta_profunda_guarda_evidencia_spec_plan_y_prueba_bajo_260(
    tmp_path, monkeypatch
):
    """Limita cada escritura como Windows clásico sin modificar el registro."""
    raiz = tmp_path / ("proyecto_" + "p" * max(1, 128 - len(str(tmp_path)) - 10))
    almacen = AlmacenProyecto(raiz)
    contrato = contrato_java()
    contrato["modulo"] = "src/main/java/" + "paquete/" * 18 + "BancoDefectuoso.java"
    crear = disco.tempfile.mkstemp
    reemplazar = disco.os.replace
    rutas = []

    def temporal_corto(*args, **kwargs):
        descriptor, nombre = crear(*args, **kwargs)
        rutas.append(nombre)
        assert len(str(Path(nombre).resolve())) < 260
        return descriptor, nombre

    def final_corto(origen, destino):
        rutas.append(str(destino))
        assert len(str(Path(destino).resolve())) < 260
        reemplazar(origen, destino)

    monkeypatch.setattr(disco.tempfile, "mkstemp", temporal_corto)
    monkeypatch.setattr(disco.os, "replace", final_corto)
    run = almacen.crear_run(["funcion"])
    evidencia = almacen.guardar_evidencia_bug(contrato, CODIGO, run["run_id"])
    archivo = nombre_prueba(id_de_spec(contrato["modulo"], contrato["objetivo"]))
    almacen.guardar_prueba_aprobada(archivo, CODIGO)
    spec = almacen.guardar_spec(contrato, run["run_id"], archivo_prueba=archivo)
    almacen.guardar_plan_modulo(
        contrato["modulo"], contrato["huella"], [contrato], run["run_id"], "generado"
    )
    assert almacen.leer_evidencia_bug(run["run_id"], evidencia["id"]) == evidencia
    assert almacen.leer_spec(spec["id"])["contrato"] == contrato
    assert almacen.leer_prueba_aprobada(archivo) == CODIGO
    assert almacen.leer_plan_modulo(contrato["modulo"])["contratos"] == [contrato]
    assert rutas
    print(
        f"Rutas Windows: máximo observado={max(map(len, rutas))}; límite <260; registro sin modificar"
    )


def guardar_spec_anterior(almacen, contrato, run_id):
    """Escribe una fixture con el formato histórico, independiente del ID nuevo."""
    antigua = {
        "id": ANTERIOR,
        "creado": "2026-11-08T12:00:00+00:00",
        "run_origen": run_id,
        "estado": "vigente",
        "archivo_prueba": f"test_{ANTERIOR}.py",
        "contrato": contrato,
    }
    ruta = almacen.carpeta_specs / f"{ANTERIOR}.json"
    ruta.write_text(json.dumps(antigua), encoding="utf-8")
    (almacen.carpeta_tests / antigua["archivo_prueba"]).write_text(
        CODIGO, encoding="utf-8"
    )
    return antigua, ruta


def test_spec_y_prueba_anteriores_se_reutilizan_sin_borrarlas(historial_corto):
    """La lectura con ID nuevo encuentra la spec anterior y su prueba original."""
    almacen = AlmacenProyecto(historial_corto)
    run = almacen.crear_run()
    contrato = contrato_java()
    antigua, ruta = guardar_spec_anterior(almacen, contrato, run["run_id"])
    original = ruta.read_bytes()
    assert almacen.leer_spec(id_de_spec(MODULO, OBJETIVO)) == antigua
    assert almacen.listar_specs() == [antigua]
    assert _specs_aprobadas(almacen) == [antigua]
    assert almacen.leer_prueba_aprobada(antigua["archivo_prueba"]) == CODIGO
    assert ruta.read_bytes() == original


@pytest.mark.parametrize("aprobada", [True, False])
def test_guardado_nuevo_no_duplica_ni_resucita_aprobaciones_antiguas(
    historial_corto, aprobada
):
    """El formato actual prevalece incluso si el objetivo ya no tiene una prueba aprobada."""
    almacen = AlmacenProyecto(historial_corto)
    run = almacen.crear_run()
    contrato = contrato_java()
    _, ruta = guardar_spec_anterior(almacen, contrato, run["run_id"])
    archivo = nombre_prueba(id_de_spec(MODULO, OBJETIVO)) if aprobada else None
    if archivo:
        almacen.guardar_prueba_aprobada(archivo, CODIGO)
    nueva = almacen.guardar_spec(contrato, run["run_id"], archivo_prueba=archivo)
    assert almacen.listar_specs() == [nueva]
    assert _specs_aprobadas(almacen) == ([nueva] if aprobada else [])
    assert ruta.is_file()


def test_evidencia_anterior_conserva_procedencia_y_es_idempotente(historial_corto):
    """Las evidencias históricas siguen válidas con sus IDs y nombres originales."""
    almacen = AlmacenProyecto(historial_corto)
    run = almacen.crear_run()
    contrato = contrato_java()
    evidencia = almacen.guardar_evidencia_bug(contrato, CODIGO, run["run_id"])
    actual = almacen.carpeta_evidencias_bugs / run["run_id"] / f"{evidencia['id']}.json"
    antigua = copy.deepcopy(evidencia)
    antigua.update(id=ANTERIOR, archivo_prueba=f"test_{ANTERIOR}.py")
    historica = actual.with_name(f"{ANTERIOR}.json")
    actual.rename(historica)
    historica.write_text(json.dumps(antigua), encoding="utf-8")
    original = historica.read_bytes()
    assert almacen.leer_evidencia_bug(run["run_id"], ANTERIOR) == antigua
    assert almacen.guardar_evidencia_bug(contrato, CODIGO, run["run_id"]) == antigua
    assert almacen.listar_evidencias_bug(run["run_id"]) == [antigua]
    assert historica.read_bytes() == original
    assert antigua["huella_prueba"] == huella_de_prueba(CODIGO)


def test_plan_modular_anterior_se_reutiliza_y_exporta(historial_corto):
    """El hash nuevo no invalida la caché modular ni su descarga histórica."""
    almacen = AlmacenProyecto(historial_corto)
    run = almacen.crear_run()
    contrato = contrato_java()
    plan = almacen.guardar_plan_modulo(
        MODULO, contrato["huella"], [contrato], run["run_id"], "generado"
    )
    historico_id = (
        "src__main__java__org__qagent__bench__BancoDefectuoso--"
        + hashlib.sha256(MODULO.encode("utf-8")).hexdigest()[:12]
    )
    actual = almacen.carpeta_specs / f"{id_de_modulo(MODULO)}.spec.json"
    historica = actual.with_name(f"{historico_id}.spec.json")
    actual.rename(historica)
    original = historica.read_bytes()
    assert almacen.leer_plan_modulo(MODULO) == plan
    assert almacen.buscar_plan_vigente(MODULO, contrato["huella"]) == plan
    assert almacen.crear_zip_specs(MODULO)[1].startswith(b"PK")
    assert almacen.listar_planes_modulo() == [plan]
    reutilizado = almacen.guardar_plan_modulo(
        MODULO, contrato["huella"], [contrato], run["run_id"], "reutilizado"
    )
    assert actual.is_file()
    assert almacen.listar_planes_modulo() == [reutilizado]
    assert historica.read_bytes() == original


def test_regresion_ejecuta_una_prueba_java_historica_sin_ia(
    historial_corto, monkeypatch
):
    """Repite una spec y archivo del formato anterior; el ejecutor es simulado."""
    almacen = AlmacenProyecto(historial_corto)
    origen = almacen.crear_run()
    fuente = historial_corto / MODULO
    fuente.parent.mkdir(parents=True)
    fuente.write_text(
        "package org.qagent.bench; public class BancoDefectuoso {"
        "/** Devuelve subtotal más su impuesto. */"
        "public static double calcularTotalConImpuesto(double subtotal, double porcentaje) {"
        "return subtotal * (1 + porcentaje / 100);}}",
        encoding="utf-8",
    )
    contrato = contrato_java()
    antigua, ruta = guardar_spec_anterior(almacen, contrato, origen["run_id"])
    antigua.update(
        huella_objetivo=huellas_de_objetivos(historial_corto)[(MODULO, OBJETIVO)],
        version_huella_objetivo=2,
    )
    ruta.write_text(json.dumps(antigua), encoding="utf-8")
    bytes_anteriores = ruta.read_bytes()
    llamadas = []

    def simular(imagen, proyecto, tests, modulo):
        llamadas.append(modulo)
        assert next(Path(tests).rglob("*.java")).read_text("utf-8") == CODIGO
        return ResultadoSandbox(
            0,
            "1 passed",
            "",
            {"totals": {"percent_covered": 100}},
            junit_xml='<testsuite name="BancoDefectuosoTest" tests="1" failures="0" '
            'errors="0" skipped="0" time="0.01"><testcase '
            'classname="org.qagent.bench.BancoDefectuosoTest" name="test_normal" time="0.01"/>'
            "</testsuite>",
        )

    def prohibir_ia(*args, **kwargs):
        pytest.fail("La regresión no debe crear clientes de IA.")

    monkeypatch.setattr("qagent.orchestrator.corrida.crear_cliente", prohibir_ia)
    run = almacen.crear_run()
    resultado = ejecutar_regresion(
        historial_corto,
        "reg",
        cargar_configuracion(simulado=True).config,
        run_id=run["run_id"],
        preparar_imagen=lambda _: "imagen-simulada",
        ejecutor=simular,
    )
    assert resultado.estado == "fin", resultado.motivo
    assert resultado.aceptadas == resultado.total_procesados == 1
    assert resultado.tokens == 0
    assert len(llamadas) == 1
    assert ruta.read_bytes() == bytes_anteriores

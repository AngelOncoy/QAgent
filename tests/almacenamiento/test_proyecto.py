"""EN-07 (criterio 2): guardar y leer corridas, specs y pruebas aprobadas."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pyagent import contracts
from pyagent.almacenamiento import (
    AlmacenProyecto,
    DatoCorrupto,
    DatoNoEncontrado,
    ErrorAlmacen,
    id_de_spec,
    nombre_prueba,
)
from pyagent.app import desktop

MOMENTO = datetime(2026, 10, 9, 14, 30, 5, tzinfo=timezone.utc)
RUN_ID = "20261009-143005-abcd"
CONTRATO = json.loads(
    (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture
def almacen(tmp_path: Path) -> AlmacenProyecto:
    return AlmacenProyecto(tmp_path)


# --- Corridas -----------------------------------------------------------------------


def test_crear_run_escribe_run_json_en_su_carpeta(almacen):
    run = almacen.crear_run(["funcion"], "pyagent-sandbox:base", ahora=MOMENTO)

    assert run["run_id"].startswith("20261009-143005-")
    ruta = almacen.carpeta_runs / run["run_id"] / "run.json"
    assert json.loads(ruta.read_text(encoding="utf-8")) == {
        "run_id": run["run_id"],
        "inicio": "2026-10-09T14:30:05+00:00",
        "fin": None,
        "tipos_prueba": ["funcion"],
        "imagen_docker": "pyagent-sandbox:base",
        "estado": "en_curso",
        "resumen": None,
    }


def test_finalizar_run_guarda_estado_fin_y_resumen(almacen):
    run = almacen.crear_run(ahora=MOMENTO)

    almacen.finalizar_run(
        run["run_id"],
        "fin",
        pasaron=3,
        fallaron=1,
        tipos_prueba=["funcion", "endpoint"],
        ahora=MOMENTO + timedelta(minutes=2),
    )

    leido = almacen.leer_run(run["run_id"])
    assert leido["estado"] == "fin"
    assert leido["fin"] == "2026-10-09T14:32:05+00:00"
    assert leido["resumen"] == {"pasaron": 3, "fallaron": 1}
    assert leido["tipos_prueba"] == ["funcion", "endpoint"]


def test_run_json_convive_con_log_y_results_de_en05(almacen):
    run = almacen.crear_run(ahora=MOMENTO)
    carpeta = almacen.carpeta_run(run["run_id"])
    (carpeta / "results.json").write_text("{}", encoding="utf-8")

    almacen.finalizar_run(run["run_id"], "fin", 1, 0)

    assert sorted(p.name for p in carpeta.iterdir()) == ["results.json", "run.json"]


def test_listar_runs_en_orden_cronologico(almacen):
    tarde = almacen.crear_run(ahora=MOMENTO + timedelta(days=1))
    temprano = almacen.crear_run(ahora=MOMENTO)
    medio = almacen.crear_run(ahora=MOMENTO + timedelta(hours=1))

    ids = [r["run_id"] for r in almacen.listar_runs()]

    assert ids == [temprano["run_id"], medio["run_id"], tarde["run_id"]]


def test_listar_runs_sin_pyagent_devuelve_lista_vacia(almacen):
    assert almacen.listar_runs() == []
    assert not almacen.existe()


@pytest.mark.parametrize(
    "cambio",
    [
        {"estado": "terminado"},
        {"tipos_prueba": ["e2e"]},
        {"resumen": {"pasaron": "3"}},
        {"run_id": "../../fuera"},
    ],
)
def test_guardar_run_rechaza_valores_no_validos(almacen, cambio):
    run = {
        "run_id": RUN_ID,
        "inicio": "2026-10-09T14:30:05+00:00",
        "fin": None,
        "tipos_prueba": [],
        "imagen_docker": None,
        "estado": "en_curso",
        "resumen": None,
        **cambio,
    }

    with pytest.raises(ErrorAlmacen):
        almacen.guardar_run(run)

    assert not almacen.existe()


def test_leer_run_inexistente_lanza_dato_no_encontrado(almacen):
    with pytest.raises(DatoNoEncontrado):
        almacen.leer_run(RUN_ID)


# --- Specs --------------------------------------------------------------------------


def test_guardar_y_leer_spec(almacen):
    spec = almacen.guardar_spec(
        CONTRATO,
        RUN_ID,
        archivo_prueba="test_tienda_precios_py__calcular_descuento.py",
        ahora=MOMENTO,
    )

    assert spec["id"] == "tienda_precios_py__calcular_descuento"
    assert (almacen.carpeta_specs / f"{spec['id']}.json").is_file()
    assert almacen.leer_spec(spec["id"]) == {
        "id": "tienda_precios_py__calcular_descuento",
        "creado": "2026-10-09T14:30:05+00:00",
        "run_origen": RUN_ID,
        "estado": "vigente",
        "archivo_prueba": "test_tienda_precios_py__calcular_descuento.py",
        "contrato": CONTRATO,
    }


def test_guardar_la_misma_spec_la_reemplaza(almacen):
    almacen.guardar_spec(CONTRATO, RUN_ID)
    otro_run = "20261010-090000-0f0f"

    almacen.guardar_spec(CONTRATO, otro_run, estado="obsoleta")

    specs = almacen.listar_specs()
    assert len(specs) == 1
    assert specs[0]["run_origen"] == otro_run
    assert specs[0]["estado"] == "obsoleta"


def test_listar_specs_y_tiene_specs(almacen):
    assert almacen.tiene_specs() is False
    endpoint = {
        **copy.deepcopy(CONTRATO),
        "tipo": "endpoint",
        "objetivo": "GET /precios/{id}",
    }

    almacen.guardar_spec(CONTRATO, RUN_ID)
    almacen.guardar_spec(endpoint, RUN_ID)

    assert almacen.tiene_specs() is True
    assert [s["id"] for s in almacen.listar_specs()] == [
        "tienda_precios_py__GET_precios_id",
        "tienda_precios_py__calcular_descuento",
    ]


def test_spec_con_contrato_invalido_no_se_escribe(almacen):
    invalido = {**CONTRATO, "casos": []}

    with pytest.raises(contracts.ContratoInvalido):
        almacen.guardar_spec(invalido, RUN_ID)

    assert not almacen.existe()


def test_spec_con_run_origen_no_valido_no_se_escribe(almacen):
    with pytest.raises(ErrorAlmacen):
        almacen.guardar_spec(CONTRATO, "ayer")

    assert not almacen.existe()


def test_id_de_spec_y_nombre_de_prueba_son_nombres_de_archivo_seguros():
    assert id_de_spec("mi-api/v1/rutas.py", "POST /items/{id}") == (
        "mi_api_v1_rutas_py__POST_items_id"
    )
    assert nombre_prueba("tienda_precios_py__calcular") == (
        "test_tienda_precios_py__calcular.py"
    )


# --- Pruebas aprobadas -------------------------------------------------------------


def test_guardar_y_listar_pruebas_aprobadas(almacen):
    codigo = "def test_suma():\n    assert 1 + 1 == 2  # año, ñandú\n"

    ruta = almacen.guardar_prueba_aprobada("test_calc__sumar.py", codigo)
    almacen.guardar_prueba_aprobada("test_a__b.py", "def test_x():\n    pass\n")

    assert ruta == almacen.carpeta_tests / "test_calc__sumar.py"
    assert [p.name for p in almacen.listar_pruebas_aprobadas()] == [
        "test_a__b.py",
        "test_calc__sumar.py",
    ]
    assert almacen.leer_prueba_aprobada("test_calc__sumar.py") == codigo
    assert ruta.read_bytes() == codigo.encode("utf-8")  # UTF-8 y fin de línea \n


def test_listar_pruebas_ignora_archivos_que_no_son_test(almacen):
    almacen.guardar_prueba_aprobada("test_ok.py", "")
    (almacen.carpeta_tests / "conftest.py").write_text("", encoding="utf-8")
    (almacen.carpeta_tests / "notas.txt").write_text("", encoding="utf-8")

    assert [p.name for p in almacen.listar_pruebas_aprobadas()] == ["test_ok.py"]


@pytest.mark.parametrize(
    "nombre", ["calc.py", "test_x.txt", "../test_x.py", "sub/test_x.py", "test_.py.."]
)
def test_guardar_prueba_rechaza_nombres_no_validos(almacen, nombre):
    with pytest.raises(ErrorAlmacen):
        almacen.guardar_prueba_aprobada(nombre, "")


def test_leer_prueba_inexistente_lanza_dato_no_encontrado(almacen):
    with pytest.raises(DatoNoEncontrado):
        almacen.leer_prueba_aprobada("test_nada.py")


# --- Archivos dañados o ausentes ----------------------------------------------------


def test_run_json_corrupto_se_omite_al_listar_y_falla_claro_al_leer(almacen):
    bueno = almacen.crear_run(ahora=MOMENTO)
    malo = almacen.crear_run(ahora=MOMENTO + timedelta(hours=1))
    ruta_mala = almacen.carpeta_run(malo["run_id"]) / "run.json"
    ruta_mala.write_text('{"run_id": "2026', encoding="utf-8")  # cierre a mitad
    (almacen.carpeta_runs / "20261009-150000-0000").mkdir()  # carpeta sin run.json
    (almacen.carpeta_runs / "basura").mkdir()

    assert [r["run_id"] for r in almacen.listar_runs()] == [bueno["run_id"]]
    with pytest.raises(DatoCorrupto, match="no es un JSON válido"):
        almacen.leer_run(malo["run_id"])


@pytest.mark.parametrize(
    "contenido",
    [b"[1, 2]", b'{"run_id": "20261009-143005-abcd"}', b"\xff\xfe no es UTF-8"],
)
def test_run_json_con_formato_inesperado_es_dato_corrupto(almacen, contenido):
    carpeta = almacen.carpeta_run(RUN_ID)
    carpeta.mkdir(parents=True)
    (carpeta / "run.json").write_bytes(contenido)

    with pytest.raises(DatoCorrupto):
        almacen.leer_run(RUN_ID)
    assert almacen.listar_runs() == []


def test_run_json_de_otra_carpeta_es_dato_corrupto(almacen):
    run = almacen.crear_run(ahora=MOMENTO)
    copia = almacen.carpeta_run(RUN_ID)
    copia.mkdir()
    origen = almacen.carpeta_run(run["run_id"]) / "run.json"
    (copia / "run.json").write_text(
        origen.read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(DatoCorrupto, match="no coincide"):
        almacen.leer_run(RUN_ID)


def test_spec_corrupta_se_omite_y_no_cuenta_para_tiene_specs(almacen):
    almacen.inicializar()
    (almacen.carpeta_specs / "rota.json").write_text("{", encoding="utf-8")
    sin_contrato = {
        "id": "x__y",
        "creado": "2026-10-09T14:30:05+00:00",
        "run_origen": RUN_ID,
        "estado": "vigente",
        "archivo_prueba": None,
        "contrato": {"version": "2"},
    }
    (almacen.carpeta_specs / "x__y.json").write_text(
        json.dumps(sin_contrato), encoding="utf-8"
    )

    assert almacen.listar_specs() == []
    assert almacen.tiene_specs() is False
    with pytest.raises(DatoCorrupto):
        almacen.leer_spec("rota")
    with pytest.raises(DatoCorrupto):
        almacen.leer_spec("x__y")


def test_un_fallo_al_escribir_no_deja_el_json_a_medias(
    almacen, monkeypatch: pytest.MonkeyPatch
):
    run = almacen.crear_run(ahora=MOMENTO)
    ruta = almacen.carpeta_run(run["run_id"]) / "run.json"
    antes = ruta.read_text(encoding="utf-8")

    def corte(*_args, **_kwargs):
        raise OSError("se cerró la aplicación")

    monkeypatch.setattr("pyagent.almacenamiento.disco.os.replace", corte)
    with pytest.raises(OSError):
        almacen.finalizar_run(run["run_id"], "fin", 1, 0)

    assert ruta.read_text(encoding="utf-8") == antes
    assert [p.name for p in ruta.parent.iterdir()] == ["run.json"]  # sin .tmp


# --- Integración con el puente de escritorio ---------------------------------------


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> desktop.DesktopAPI:
    """Puente con el entorno dado por listo y la IA simulada (Docker opcional)."""
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    puente = desktop.DesktopAPI()
    puente.verificar_entorno = lambda: {  # type: ignore[method-assign]
        "listo": True,
        "mensaje": "Entorno listo",
        "problemas": [],
        "comprobaciones": [],
    }
    return puente


def test_start_run_registra_la_corrida_en_un_proyecto_abierto(api, almacen):
    almacen.inicializar()

    resultado = api.start_run(str(almacen.raiz), "deep")

    assert resultado["status"] == "started"
    run = almacen.leer_run(resultado["run_id"])
    assert run["estado"] == "en_curso"
    assert run["imagen_docker"] is None  # IA simulada: no se usa el sandbox


def test_start_run_no_crea_pyagent_en_carpetas_no_abiertas(api, almacen):
    resultado = api.start_run(str(almacen.raiz), "deep")

    assert resultado["status"] == "started"
    assert resultado["run_id"] is None
    assert not almacen.existe()

"""#139: reabrir un proyecto con corridas interrumpidas no lo trata como si tuviera resultados."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto, BloqueoCorrida, corrida_activa
from qagent.app import desktop

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


@pytest.fixture
def archivo_recientes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    archivo = tmp_path / "home" / ".qagent" / "recientes.json"
    monkeypatch.setattr(desktop.recientes, "ruta_por_defecto", lambda: archivo)
    return archivo


def _proyecto(tmp_path: Path) -> Path:
    carpeta = tmp_path / "app_rf"
    carpeta.mkdir()
    (carpeta / "modulo.py").write_text("def suma(a, b): return a + b\n", "utf-8")
    return carpeta


def test_solo_corridas_interrumpidas_no_cuentan_como_corridas(
    tmp_path: Path, archivo_recientes: Path
) -> None:
    carpeta = _proyecto(tmp_path)
    api = desktop.DesktopAPI()
    api.abrir_proyecto(str(carpeta))
    almacen = AlmacenProyecto(str(carpeta))
    run_id = almacen.crear_run(["funcion"])["run_id"]  # la app se cerró a mitad
    desktop.recientes.registrar_corrida(str(carpeta), archivo=archivo_recientes)

    res = api.abrir_reciente(str(carpeta))

    assert res["ok"] is True
    assert res["tiene_corridas"] is False
    assert res["ya_cargo_prueba"] is False
    assert almacen.leer_run(run_id)["estado"] == "interrumpida"


def test_abrir_carpeta_tambien_cierra_las_interrumpidas(
    tmp_path: Path, archivo_recientes: Path
) -> None:
    carpeta = _proyecto(tmp_path)
    almacen = AlmacenProyecto(str(carpeta))
    almacen.inicializar()
    run_id = almacen.crear_run(["funcion"])["run_id"]

    res = desktop.DesktopAPI().abrir_proyecto(str(carpeta))

    assert res["tiene_corridas"] is False
    assert almacen.leer_run(run_id)["estado"] == "interrumpida"


def test_una_corrida_en_ejecucion_no_se_marca_al_reabrir(
    tmp_path: Path, archivo_recientes: Path
) -> None:
    carpeta = _proyecto(tmp_path)
    api = desktop.DesktopAPI()
    api.abrir_proyecto(str(carpeta))
    almacen = AlmacenProyecto(str(carpeta))
    run_id = almacen.crear_run(["funcion"])["run_id"]

    bloqueo = BloqueoCorrida.tomar(almacen.carpeta_run(run_id))
    try:
        api.abrir_reciente(str(carpeta))
        assert almacen.leer_run(run_id)["estado"] == "en_curso"
    finally:
        bloqueo.liberar()


def test_la_corrida_suelta_su_bloqueo_aunque_falle(tmp_path: Path) -> None:
    carpeta = tmp_path / "run"
    bloqueo = BloqueoCorrida.tomar(carpeta)
    api = desktop.DesktopAPI()

    def falla(*_args) -> None:
        raise RuntimeError("fallo inesperado")

    api._correr = falla  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        api._correr_y_liberar("ruta", "std", "id", True, None, bloqueo)

    assert corrida_activa(carpeta) is False


def test_tomar_bloqueo_sin_run_id_no_bloquea() -> None:
    assert desktop._tomar_bloqueo("C:/no-importa", None) is None


# --- Interfaz ---------------------------------------------------------------------


def _js(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def test_volver_a_correr_depende_de_las_pruebas_guardadas() -> None:
    vista = _js("componentes/vista-previa/vista-previa.js")

    assert "HAS_PRIOR_RUN = corridaPrevia;" in vista
    assert "HAS_PRIOR_RUN = corridaPrevia || yaCargoPrueba;" not in vista


def test_al_reabrir_solo_salta_a_resultados_si_los_hay() -> None:
    vista = _js("componentes/vista-previa/vista-previa.js")
    precarga = vista.index("cargarEjecucionReal(null, false, {silencioso: true})")
    decision = vista.index("yaCargoPrueba = !!ejecucionReal;")
    salto = vista.index("if (esReciente && yaCargoPrueba) {")

    assert precarga < decision < salto


def test_resultados_en_la_app_no_usa_la_demostracion() -> None:
    js = _js("componentes/ejecucion/ejecucion.js")
    render = js[js.index("function renderExec") :]

    assert "const sinResultados = !v && enAppEscritorio();" in render
    assert render.index("if (sinResultados) {") < render.index("elementosDemo()")
    assert 'id="bnjVacio"' in js
    assert "Este proyecto todavía no tiene resultados" in js
    assert "if (!silencioso && typeof toastError" in js
    css = _js("componentes/ejecucion/ejecucion.css")
    assert "#s-exec.bnj-sin-datos" in css


def test_exportar_en_la_app_no_usa_la_demostracion() -> None:
    js = _js("componentes/exportar/exportar.js")

    assert "(enAppEscritorio() ? [] : elementosDemo())" in js


def test_historial_nombra_la_corrida_interrumpida() -> None:
    js = _js("componentes/historial/historial.js")

    assert "h.tipo_terminacion === 'interrumpida' ? 'Interrumpida'" in js


def test_historial_no_ofrece_abrir_una_corrida_sin_resultados() -> None:
    js = _js("componentes/historial/historial.js")
    abrir = js[js.index("function abrirCorridaSeleccionada") :]

    assert "datos.demo || tieneResultados(h) ?" in js
    assert "if (fila && !tieneResultados(fila)) {" in abrir
    assert abrir.index("!tieneResultados(fila)") < abrir.index(
        "cargarEjecucionReal(histSel)"
    )

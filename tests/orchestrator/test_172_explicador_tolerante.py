"""EP-10 (#172): si el Explicador falla o está desactivado, todo sigue como hoy.

Cada caso compara contra lo que la corrida ya había escrito antes del Explicador
(`results.json`, `detalle.json`, `log.json`) y contra los informes de la misma
corrida sin `explicaciones.json`. Usa la IA simulada y el ejecutor simulado de
`test_corrida`: no ejecuta código ni llama a una API real.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.contracts import ContratoInvalido
from qagent.llm.fake import FakeLLMClient
from qagent.orchestrator import corrida
from qagent.storage import registro
from qagent.storage.exportar_informe import exportar_informe
from qagent.storage.registro import ARCHIVO_EXPLICACIONES
from qagent.storage.vista_reporte import leer_explicaciones, vista_reporte
from tests.orchestrator.test_corrida import BANCO
from tests.orchestrator.test_hu32_explicador_corrida import correr

FORMATOS = ("md", "html", "json")


@pytest.fixture
def proyecto(tmp_path: Path) -> AlmacenProyecto:
    carpeta = tmp_path / "banco"
    shutil.copytree(
        BANCO, carpeta, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    return almacen


@pytest.fixture
def config():
    """La del equipo: Explicador obligatorio con `modo = "ia"` (IA simulada)."""
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


@pytest.fixture
def antes(monkeypatch) -> dict[str, bytes]:
    """Lo que la corrida escribió antes de llamar al Explicador."""
    escritos: dict[str, bytes] = {}
    original = corrida.escribir_corrida

    def escribir_y_copiar(*args, **kwargs):
        rutas = original(*args, **kwargs)
        for nombre in ("results", "detalle", "log"):
            escritos[nombre] = getattr(rutas, nombre).read_bytes()
        return rutas

    monkeypatch.setattr(corrida, "escribir_corrida", escribir_y_copiar)
    return escritos


def _sigue_como_sin_explicador(
    proyecto: AlmacenProyecto, resumen, carpeta: Path, antes: dict[str, bytes]
) -> None:
    """Resultados, historial e informes iguales a una corrida sin Explicador."""
    assert resumen.estado == "fin", resumen.motivo
    assert proyecto.leer_run(resumen.run_id)["estado"] == "fin"
    for nombre in ("results", "detalle", "log"):
        assert (carpeta / f"{nombre}.json").read_bytes() == antes[nombre], nombre
    assert not (carpeta / ARCHIVO_EXPLICACIONES).exists()
    log = json.loads(antes["log"])
    assert "explicador" not in log["totales_por_agente"]
    assert resumen.tokens == log["total_tokens"]


def _informes(raiz: Path, run_id: str, destino: Path) -> dict[str, str]:
    """Informes exportados y la vista de Resultados de la corrida."""
    informes = {
        fmt: Path(
            exportar_informe(raiz, run_id, fmt, carpeta_destino=destino)["ruta"]
        ).read_text(encoding="utf-8")
        for fmt in FORMATOS
    }
    carpeta = raiz / ".qagent" / "runs" / run_id
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    detalle = json.loads((carpeta / "detalle.json").read_text(encoding="utf-8"))
    vista = vista_reporte(results, detalle, leer_explicaciones(raiz, results))
    informes["resultados"] = json.dumps(vista, sort_keys=True, ensure_ascii=False)
    return informes


def _informes_sin_explicaciones(raiz: Path, run_id: str, destino: Path):
    """Los informes de la misma corrida si `explicaciones.json` no existiera."""
    ruta = raiz / ".qagent" / "runs" / run_id / ARCHIVO_EXPLICACIONES
    guardado = ruta.read_bytes() if ruta.exists() else None
    ruta.unlink(missing_ok=True)
    try:
        return _informes(raiz, run_id, destino)
    finally:
        if guardado is not None:
            ruta.write_bytes(guardado)


# --- Desactivado -----------------------------------------------------------------------


def test_desactivado_no_cambia_nada(proyecto, config, antes, tmp_path):
    apagado = dataclasses.replace(
        config, explicador=dataclasses.replace(config.explicador, activo=False)
    )
    resumen, carpeta = correr(proyecto, apagado)

    _sigue_como_sin_explicador(proyecto, resumen, carpeta, antes)


# --- Fallas del Explicador ---------------------------------------------------------------


def test_una_excepcion_del_explicador_no_cambia_nada(
    proyecto, config, antes, monkeypatch, caplog, tmp_path
):
    def explota(*_args, **_kwargs):
        raise RuntimeError("falla inesperada del explicador")

    monkeypatch.setattr(corrida, "explicar_corrida", explota)
    with caplog.at_level(logging.WARNING, logger="qagent.corrida"):
        resumen, carpeta = correr(proyecto, config)

    _sigue_como_sin_explicador(proyecto, resumen, carpeta, antes)
    assert "El Explicador falló" in caplog.text
    raiz = proyecto.raiz
    assert _informes(raiz, resumen.run_id, tmp_path / "a") == (
        _informes_sin_explicaciones(raiz, resumen.run_id, tmp_path / "b")
    )


def test_una_salida_invalida_no_se_guarda_ni_cambia_nada(
    proyecto, config, antes, monkeypatch, tmp_path
):
    def invalida(*_args, **_kwargs):
        raise ContratoInvalido("explicaciones: no cumple el contrato")

    monkeypatch.setattr(corrida, "escribir_explicaciones", invalida)
    resumen, carpeta = correr(proyecto, config)

    _sigue_como_sin_explicador(proyecto, resumen, carpeta, antes)


def test_si_el_llm_falla_usa_la_plantilla_sin_tocar_los_resultados(
    proyecto, config, antes, monkeypatch, tmp_path
):
    original = FakeLLMClient.generar

    def falla_como_explicador(self, prompt, rol="generator"):
        if rol == "explicador":
            raise TimeoutError("el proveedor no respondió")
        return original(self, prompt, rol)

    monkeypatch.setattr(FakeLLMClient, "generar", falla_como_explicador)
    resumen, carpeta = correr(proyecto, config)

    assert resumen.estado == "fin", resumen.motivo
    for nombre in ("results", "detalle", "log"):
        assert (carpeta / f"{nombre}.json").read_bytes() == antes[nombre], nombre
    datos = json.loads((carpeta / ARCHIVO_EXPLICACIONES).read_text(encoding="utf-8"))
    assert datos["explicaciones"]
    assert all(e["origen"] == "plantilla" for e in datos["explicaciones"])


def test_si_no_se_puede_guardar_el_consumo_log_y_results_no_se_desparejan(
    proyecto, config, antes, monkeypatch, caplog
):
    original = registro._escribir_json

    def results_falla(ruta, datos):
        if ruta.name == "results.json" and "explicador" in json.dumps(
            datos["resumen"].get("por_agente", {})
        ):
            raise OSError("disco lleno")
        return original(ruta, datos)

    monkeypatch.setattr(registro, "_escribir_json", results_falla)
    with caplog.at_level(logging.WARNING, logger="qagent.corrida"):
        resumen, carpeta = correr(proyecto, config)

    assert resumen.estado == "fin", resumen.motivo
    assert "El Explicador falló" in caplog.text
    # Ni log.json ni results.json cuentan los tokens del Explicador.
    for nombre in ("results", "detalle", "log"):
        assert (carpeta / f"{nombre}.json").read_bytes() == antes[nombre], nombre
    assert resumen.tokens == json.loads(antes["log"])["total_tokens"]


# --- explicaciones.json dañado después de la corrida -----------------------------------


@pytest.mark.parametrize(
    "contenido",
    [b"{no es json", b'{"version": "1", "explicaciones": "otra cosa"}', b""],
)
def test_un_explicaciones_json_danado_deja_los_informes_como_sin_explicador(
    proyecto, config, tmp_path, contenido
):
    resumen, carpeta = correr(proyecto, config)
    (carpeta / ARCHIVO_EXPLICACIONES).write_bytes(contenido)

    raiz = proyecto.raiz
    assert _informes(raiz, resumen.run_id, tmp_path / "a") == (
        _informes_sin_explicaciones(raiz, resumen.run_id, tmp_path / "b")
    )

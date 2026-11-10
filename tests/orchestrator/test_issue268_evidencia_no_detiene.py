"""#268: un fallo de evidencia avisa al Monitor sin perder los veredictos."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto, ErrorAlmacen
from qagent.app.desktop import DesktopAPI
from qagent.config import cargar_configuracion
from qagent.orchestrator.corrida import ejecutar_corrida
from tests.orchestrator.test_corrida import BANCO, ejecutor_simulado


@pytest.mark.parametrize("error", [PermissionError, FileNotFoundError, ErrorAlmacen])
def test_fallo_evidencia_emite_aviso_y_completa_la_corrida(
    tmp_path, monkeypatch, error
):
    """Los tres bugs permanecen; los siguientes guardados y aprobados se conservan."""
    raiz = tmp_path / "banco"
    shutil.copytree(
        BANCO, raiz, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(raiz)
    run = almacen.crear_run(["funcion"])
    original = AlmacenProyecto.guardar_evidencia_bug

    def fallo_selectivo(self, contrato, *args, **kwargs):
        if contrato["objetivo"] == "calcular_descuento":
            raise error("escritura de evidencia bloqueada")
        return original(self, contrato, *args, **kwargs)

    monkeypatch.setattr(AlmacenProyecto, "guardar_evidencia_bug", fallo_selectivo)
    api = DesktopAPI()
    filas = []
    eventos = []
    monkeypatch.setattr(
        api, "emit_event", lambda tipo, dato: filas.append((tipo, dato))
    )

    def recibir(evento):
        eventos.append(evento)
        api._reenviar_evento(evento)

    resumen = ejecutar_corrida(
        raiz,
        "std",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        run_id=run["run_id"],
        al_evento=recibir,
        preparar_imagen=lambda _: "imagen-simulada",
        ejecutor=ejecutor_simulado,
    )
    assert resumen.estado == "fin", resumen.motivo
    assert resumen.bugs_detectados == resumen.aceptadas == 3
    assert resumen.total_procesados == 6
    assert resumen.tokens == 0
    [aviso] = [
        e
        for e in eventos
        if e["tipo"] == "aviso" and "guardar su evidencia" in e["mensaje"]
    ]
    assert "calcular_descuento" in aviso["mensaje"]
    assert "resultado se conserva" in aviso["mensaje"]
    assert any(
        tipo == "corrida_evento" and "guardar su evidencia" in dato["t"]
        for tipo, dato in filas
    )
    assert eventos[-1]["tipo"] == "fin"
    assert almacen.leer_run(run["run_id"])["estado"] == "fin"
    results = json.loads((Path(resumen.carpeta) / "results.json").read_text("utf-8"))
    assert results["resumen"]["bugs_detectados"] == 3
    assert len(almacen.listar_evidencias_bug(run["run_id"])) == 2
    assert len(almacen.listar_pruebas_aprobadas()) == 3
    assert len(almacen.listar_specs()) == 6
    print(
        "Evidencia no guardada: aviso enviado al Monitor; 3 bugs y 3 aprobados conservados; corrida fin"
    )

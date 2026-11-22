"""Sesión de recursos real a través de los hilos de agentes, sin API ni Docker."""

import json
import threading
from unittest.mock import MagicMock

from qagent.config import cargar_configuracion
from qagent.lenguajes.base import ResultadoConstruccion
from qagent.lenguajes.java_sesion import sesion_java
from qagent.orchestrator import corrida
from qagent.sandbox.modelos import ResultadoSandbox
from tests.agents.test_generator_java import preparar
from tests.lenguajes.test_issue305_construccion_java import POM
from tests.orchestrator.test_issue305_antes_de_ia import cliente_contado


def test_corrida_guarda_mediciones_cierra_cache_y_no_fabrica_cobertura(
    tmp_path, monkeypatch
):
    contrato = preparar(tmp_path)
    (tmp_path / "pom.xml").write_text(POM, encoding="utf-8")
    llamadas = []
    cliente_contado(monkeypatch, contrato, {"comprobada": True}, llamadas)
    r = corrida.ejecutar_corrida(
        tmp_path,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda _: "imagen-simulada",
        validar_construccion=lambda *a, **k: ResultadoConstruccion(
            "aprobado", "aprobado", "Comprobada"
        ),
        ejecutor=lambda *a, **k: ResultadoSandbox(
            0,
            "",
            "",
            junit_xml='<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="test_positivo" classname="ejemplo.BancoTest"/></testsuite>',
        ),
    )
    assert r.estado == "fin" and r.aceptadas == 1 and r.tokens_reales == 0, r.motivo
    assert r.recursos["cerrado"]
    assert r.recursos["contadores"]["java_cache_aciertos"] > 0
    assert r.recursos["datos"]["cache_java"]["entradas_al_cierre"] == 0
    carpeta = tmp_path / ".qagent/runs" / r.run_id
    assert (
        json.loads((carpeta / "recursos.json").read_text(encoding="utf-8"))
        == r.recursos
    )
    resultados = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    assert resultados["objetivos"][0]["metricas"]["cobertura_lineas"] is None


def test_cierre_solo_elimina_contenedores_propios_y_una_vez(tmp_path):
    propio, ajeno = MagicMock(id="propio"), MagicMock(id="ajeno")
    with sesion_java(tmp_path) as registro:
        registro.anotar_contenedor(propio)
    propio.remove.assert_called_once_with(force=True)
    ajeno.remove.assert_not_called()
    assert registro.resumen()["datos"]["contenedores_propios_pendientes_al_cierre"] == 0


def test_creacion_tardia_no_deja_contenedor_huerfano(tmp_path):
    import pytest

    with sesion_java(tmp_path) as registro:
        pass
    tardio = MagicMock(id="tardio")
    with pytest.raises(RuntimeError, match="corrida terminó"):
        registro.anotar_contenedor(tardio)
    tardio.remove.assert_called_once_with(force=True)


def test_limpieza_fallida_se_conserva_como_pendiente_no_como_exito(tmp_path):
    c = MagicMock(id="propio-con-fallo")
    c.remove.side_effect = RuntimeError("Docker no confirmó la eliminación")
    with sesion_java(tmp_path) as registro:
        registro.anotar_contenedor(c)
    assert registro.resumen()["datos"]["contenedores_propios_pendientes_al_cierre"] == 1
    assert registro.resumen()["contadores"]["contenedores_limpieza_fallida"] == 1


def test_cancelacion_es_de_la_sesion_y_su_medicion_no_es_cobertura(tmp_path):
    cancelar = threading.Event()
    with sesion_java(tmp_path, cancelar.is_set) as registro:
        assert not registro.cancelado()
        cancelar.set()
        assert registro.cancelado()
    assert registro.cancelado()
    assert "cobertura" not in registro.resumen()


def test_cancelacion_durante_ultimo_objetivo_no_se_presenta_como_fin_ni_bug(
    tmp_path, monkeypatch
):
    contrato = preparar(tmp_path)
    (tmp_path / "pom.xml").write_text(POM, encoding="utf-8")
    cliente_contado(monkeypatch, contrato, {"comprobada": True}, [])
    cancelar = threading.Event()
    errores_guardado = []
    guardar = corrida._registrar

    def registrar(*a, **k):
        try:
            return guardar(*a, **k)
        except Exception as error:
            errores_guardado.append(str(error))
            raise

    monkeypatch.setattr(corrida, "_registrar", registrar)

    def ejecutar(*a, **k):
        cancelar.set()
        return ResultadoSandbox(137, "", "", cancelado=True)

    r = corrida.ejecutar_corrida(
        tmp_path,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        cancelado=cancelar.is_set,
        preparar_imagen=lambda _: "imagen-simulada",
        validar_construccion=lambda *a, **k: ResultadoConstruccion(
            "aprobado", "aprobado", "Comprobada"
        ),
        ejecutor=ejecutar,
    )
    assert not errores_guardado
    assert (
        r.estado == corrida.FALLO and r.cancelada and r.tipo_terminacion == "cancelada"
    )
    assert r.bugs_detectados == r.aceptadas == 0
    assert r.recursos["cerrado"]

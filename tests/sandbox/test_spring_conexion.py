"""Selección del entorno y cobertura Spring sin Docker ni acceso a internet (#183)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from qagent.lenguajes import JavaAdapter, PythonAdapter
from qagent.orchestrator.corrida import _preparar_imagen
from qagent.orchestrator.regresion import huellas_de_objetivos
from tests.agents.test_generator_spring import FUENTE, preparar_spring


@pytest.mark.parametrize("falta_base", [False, True])
def test_prepara_imagen_java_y_no_comprueba_librerias_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, falta_base: bool
) -> None:
    """Selecciona Java incluso al reconstruir la base y no ejecuta el inspector Python."""
    from qagent.sandbox import ImagenNoEncontrada

    preparar = Mock(
        side_effect=[ImagenNoEncontrada("base ausente"), "qagent-sandbox:java-cache"]
        if falta_base
        else None,
        return_value="qagent-sandbox:java-cache",
    )
    construir = Mock()
    comprobar = Mock(
        side_effect=AssertionError("No corresponde inspeccionar Python en Java.")
    )
    monkeypatch.setattr("qagent.sandbox.preparar_imagen", preparar)
    monkeypatch.setattr("qagent.sandbox.construir_imagen_base", construir)
    monkeypatch.setattr(
        "qagent.sandbox.librerias.asegurar_librerias_sistema", comprobar
    )
    monkeypatch.setattr("qagent.sandbox.limpieza.registrar_uso", lambda imagen: None)
    adaptador = JavaAdapter()
    imagen = _preparar_imagen(
        tmp_path,
        imagen_base=adaptador.entorno_sandbox().imagen,
        comprobar_librerias=adaptador.comprobar_librerias_sistema,
    )
    assert imagen == "qagent-sandbox:java-cache"
    assert all(
        llamada.kwargs["imagen"] == "qagent-sandbox:java"
        for llamada in preparar.call_args_list
    )
    assert construir.call_count == int(falta_base)
    if falta_base:
        assert construir.call_args.kwargs["imagen"] == "qagent-sandbox:java"
    comprobar.assert_not_called()


def test_python_conserva_inspeccion_del_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El punto de extensión mantiene la comprobación de librerías del flujo Python."""
    comprobar = Mock(
        return_value=SimpleNamespace(imagen="python-comprobado", faltantes=[])
    )
    monkeypatch.setattr(
        "qagent.sandbox.preparar_imagen", lambda *a, **kw: "python-dependencias"
    )
    monkeypatch.setattr("qagent.sandbox.cliente.obtener_cliente", lambda: "cliente")
    monkeypatch.setattr(
        "qagent.sandbox.librerias.asegurar_librerias_sistema", comprobar
    )
    monkeypatch.setattr("qagent.sandbox.limpieza.registrar_uso", lambda imagen: None)
    adaptador = PythonAdapter()
    assert (
        _preparar_imagen(
            tmp_path,
            imagen_base=adaptador.entorno_sandbox().imagen,
            comprobar_librerias=adaptador.comprobar_librerias_sistema,
        )
        == "python-comprobado"
    )
    comprobar.assert_called_once()


def test_huella_endpoint_y_metodo_de_cobertura_son_estaticos(tmp_path: Path) -> None:
    """El guardado identifica el objetivo HTTP, mientras JaCoCo utiliza su manejador."""
    contrato = preparar_spring(tmp_path)
    adaptador = JavaAdapter()
    assert adaptador.objetivo_de_cobertura(contrato) == "Api.crear"
    clave = (contrato["modulo"], contrato["objetivo"])
    huella = huellas_de_objetivos(tmp_path)[clave]
    assert len(huella) == 64
    (tmp_path / contrato["modulo"]).write_text(
        FUENTE.replace(
            "servicio.guardar();", "servicio.guardar(); servicio.guardar();"
        ),
        encoding="utf-8",
    )
    assert huellas_de_objetivos(tmp_path)[clave] != huella


def test_rango_del_controlador_sigue_disponible_para_jacoco(tmp_path: Path) -> None:
    """Un manejador excluido de las unitarias conserva su ubicación como endpoint."""
    contrato = preparar_spring(tmp_path)
    rango = (
        JavaAdapter()
        .reglas_revision()
        .rango_de_objetivo(tmp_path, contrato["modulo"], contrato["manejador"])
    )
    assert rango is not None
    assert rango[0] <= rango[1]


@pytest.mark.parametrize("etiqueta", ["Status", "Response status"])
def test_lector_junit_conserva_estados_http_mockmvc(etiqueta: str) -> None:
    """El informe muestra esperado/obtenido del diagnóstico Spring, sin usarlos como oráculo."""
    xml = f"""<testsuite tests="1" failures="1" errors="0" skipped="0" time="0.1">
      <testcase classname="ApiTest" name="test_estado" time="0.1">
        <failure type="java.lang.AssertionError" message="{etiqueta} expected:&lt;201&gt; but was:&lt;200&gt;"/>
      </testcase>
    </testsuite>"""
    informe = JavaAdapter().interpretar_resultados(xml)
    assert informe["fallaron"] == 1
    assert informe["casos"][0]["esperado"] == "201"
    assert informe["casos"][0]["obtenido"] == "200"


def test_cierre_forzado_jvm_no_produce_veredicto_o_cobertura_confiable() -> None:
    """Un XML exitoso no basta si Surefire mató la JVM antes de completar sus salidas."""
    from qagent.lenguajes.java_revision import clasificar_java
    from qagent.sandbox.modelos import ResultadoSandbox

    resultado = ResultadoSandbox(
        0,
        "[ERROR] Surefire is going to kill self fork JVM. Maven did not acknowledge the end of the fork (BYE_ACK) within 30 seconds.",
        "",
        junit_xml='<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="caso" classname="ApiTest"/></testsuite>',
    )
    clasificacion = clasificar_java(resultado)
    assert clasificacion.tipo == "entorno"
    assert clasificacion.motivo_sin_veredicto == "terminacion_jvm"

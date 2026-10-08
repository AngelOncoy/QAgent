"""Bitácora de la corrida en la consola de Python: formato, limpieza y ocultación de claves."""

from __future__ import annotations

import io
import logging
import re

import pytest

from pyagent.app import bitacora
from pyagent.app.desktop import DesktopAPI
from pyagent.config import Claves

CLAVE_DE_PRUEBA = (
    "valor-de-prueba-" + "Z" * 14
)  # armado en la prueba: no es una clave real


@pytest.fixture
def salida():
    """Configura la bitácora hacia un buffer y la deja limpia al terminar."""
    flujo = io.StringIO()
    yield flujo
    for h in [
        h for h in bitacora.registro.handlers if getattr(h, "_de_la_bitacora", False)
    ]:
        bitacora.registro.removeHandler(h)
    bitacora.registro.propagate = True


def _lineas(flujo: io.StringIO) -> list[str]:
    return [linea for linea in flujo.getvalue().splitlines() if linea]


EVENTO = {
    "tipo": "planner",
    "agente": "Planner Agent",
    "archivo": "services/cart.py",
    "funcion": "calculate_tax_breakdown()",
    "mensaje": "Analizando el árbol de dependencias",
    "progreso": "2/9",
}


def test_cada_paso_sale_con_hora_nivel_agente_y_donde(salida):
    bitacora.configurar_registro(flujo=salida)
    bitacora.registrar_evento(EVENTO)
    (linea,) = _lineas(salida)
    assert re.match(r"^\d{2}:\d{2}:\d{2} INFO    \[Planner Agent\] ", linea)
    assert "services/cart.py :: calculate_tax_breakdown()" in linea
    assert linea.endswith("Analizando el árbol de dependencias (2/9)")


@pytest.mark.parametrize("tipo", ["guard", "watch", "oracle", "stuck"])
def test_las_alertas_salen_como_warning(salida, tipo):
    bitacora.configurar_registro(flujo=salida)
    bitacora.registrar_evento({**EVENTO, "tipo": tipo})
    assert " WARNING " in _lineas(salida)[0]


@pytest.mark.parametrize(
    "tipo", ["planner", "generator", "reviewer", "reuse", "fin", "control"]
)
def test_los_pasos_normales_salen_como_info(salida, tipo):
    bitacora.configurar_registro(flujo=salida)
    bitacora.registrar_evento({**EVENTO, "tipo": tipo})
    assert " INFO    " in _lineas(salida)[0]


def test_quita_el_html_y_las_entidades_de_los_mensajes():
    texto = 'Spec vigente (<span class="mono">.pyagent/specs/a.json</span>) &amp; reutilizado'
    assert (
        bitacora.limpiar_texto(texto)
        == "Spec vigente (.pyagent/specs/a.json) & reutilizado"
    )


def test_un_mensaje_no_puede_partir_ni_falsear_lineas(salida):
    bitacora.configurar_registro(flujo=salida)
    bitacora.registrar_evento({**EVENTO, "mensaje": "uno\n12:00:00 ERROR falso\r\ndos"})
    assert len(_lineas(salida)) == 1


def test_recorta_los_mensajes_larguisimos():
    largo = bitacora.limpiar_texto("a" * 5000)
    assert len(largo) <= bitacora.LARGO_MAXIMO and largo.endswith("…")


def test_los_pasos_de_control_no_llevan_guion_suelto(salida):
    bitacora.configurar_registro(flujo=salida)
    linea = bitacora.registrar_evento(
        {"tipo": "control", "agente": "Monitor", "mensaje": "Corrida pausada"}
    )
    assert linea == "[Monitor] Corrida pausada"


def test_tolera_eventos_incompletos_o_invalidos(salida):
    bitacora.configurar_registro(flujo=salida)
    assert bitacora.registrar_evento({}) == "[corrida]"
    assert bitacora.registrar_evento(None) == "[corrida]"  # type: ignore[arg-type]
    assert (
        bitacora.registrar_evento({"mensaje": "solo texto"}) == "[corrida] solo texto"
    )


def test_las_claves_nunca_llegan_a_la_consola(salida):
    claves = Claves({"OPENAI_API_KEY": CLAVE_DE_PRUEBA})
    bitacora.configurar_registro(claves, flujo=salida)
    bitacora.registrar_evento(
        {**EVENTO, "mensaje": f"la clave es {CLAVE_DE_PRUEBA} ¡cuidado!"}
    )
    texto = salida.getvalue()
    assert CLAVE_DE_PRUEBA not in texto and "cuidado" in texto


def test_configurar_dos_veces_no_duplica_las_lineas(salida):
    bitacora.configurar_registro(flujo=salida)
    bitacora.configurar_registro(flujo=salida)
    bitacora.registrar_evento(EVENTO)
    assert len(_lineas(salida)) == 1


def test_la_bitacora_no_se_repite_por_el_logger_raiz(salida):
    bitacora.configurar_registro(flujo=salida)
    assert bitacora.registro.propagate is False
    assert bitacora.registro.level == logging.INFO


def test_el_puente_registra_el_evento_que_envia_la_pantalla(salida):
    bitacora.configurar_registro(flujo=salida)
    DesktopAPI().registrar_evento(EVENTO)
    assert "[Planner Agent] services/cart.py" in salida.getvalue()


def test_iniciar_y_bloquear_la_corrida_quedan_en_la_bitacora(salida, monkeypatch):
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    bitacora.configurar_registro(flujo=salida)
    api = DesktopAPI()
    api.verificar_entorno = lambda: {"listo": True, "mensaje": "", "problemas": []}  # type: ignore[method-assign]
    api.start_run("C:/demo", "deep")
    assert (
        "Corrida iniciada en 'C:/demo' con perfil 'deep' (IA simulada)"
        in salida.getvalue()
    )

    api.verificar_entorno = lambda: {
        "listo": False,
        "mensaje": "Falta algo",
        "problemas": ["Falta algo"],
    }  # type: ignore[method-assign]
    api.start_run("C:/demo", "deep")
    assert "WARNING Corrida no iniciada: Falta algo" in salida.getvalue()

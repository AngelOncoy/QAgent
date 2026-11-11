"""#267 Capa 3: el puente de la pantalla Configuración → «Espacio en disco», sin Docker real.

`desktop.py` solo hace de puente: la lógica está en `qagent.sandbox.uso_disco`, que aquí se
simula. Se comprueba qué se llama, con qué argumentos, y que no se libera con una corrida viva.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from qagent.app import desktop
from qagent.app.desktop import DesktopAPI

USO = {"ok": True, "libre_bytes": 5, "bases": {"cantidad": 1, "bytes": 1}}


@pytest.fixture
def puente(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Anota las llamadas a la lógica de `uso_disco` y devuelve resultados fijos."""
    llamadas: list[tuple] = []
    monkeypatch.setattr(
        "qagent.sandbox.uso_disco.medir_uso",
        lambda *a, **k: llamadas.append(("medir", a, k)) or dict(USO),
    )
    monkeypatch.setattr(
        "qagent.sandbox.uso_disco.liberar_espacio",
        lambda *a, **k: (
            llamadas.append(("liberar", a, k))
            or {"ok": True, "mensaje": "Se liberaron 2,0 GB dentro de Docker."}
        ),
    )
    return llamadas


def test_obtener_espacio_disco_devuelve_la_medicion(puente):
    assert DesktopAPI().obtener_espacio_disco() == USO
    assert [llamada[0] for llamada in puente] == ["medir"]


def test_liberar_espacio_llama_a_la_logica_y_devuelve_la_medicion_nueva(puente):
    resultado = DesktopAPI().liberar_espacio()

    assert resultado["ok"] is True
    assert "2,0 GB" in resultado["mensaje"]
    assert resultado["uso"] == USO
    assert [llamada[0] for llamada in puente] == ["liberar", "medir"]


def test_por_defecto_no_se_poda_la_cache_de_compilacion(puente):
    DesktopAPI().liberar_espacio()

    assert puente[0][2]["incluir_cache"] is False


def test_la_cache_solo_se_poda_cuando_la_interfaz_lo_pide(puente):
    DesktopAPI().liberar_espacio(True)

    assert puente[0][2]["incluir_cache"] is True


def test_no_se_libera_espacio_con_una_corrida_en_curso(puente):
    api = DesktopAPI()
    api._corrida = SimpleNamespace(is_alive=lambda: True)

    resultado = api.liberar_espacio(True)

    assert resultado["ok"] is False and resultado["en_curso"] is True
    assert "corrida en curso" in resultado["mensaje"]
    assert puente == []  # no se toca Docker


def test_una_corrida_terminada_no_impide_liberar(puente):
    api = DesktopAPI()
    api._corrida = SimpleNamespace(is_alive=lambda: False)

    assert api.liberar_espacio()["ok"] is True


def test_no_se_libera_dos_veces_a_la_vez(puente):
    assert desktop._LIBERANDO_ESPACIO.acquire(blocking=False)
    try:
        resultado = DesktopAPI().liberar_espacio()
    finally:
        desktop._LIBERANDO_ESPACIO.release()

    assert resultado["ok"] is False
    assert puente == []


def test_el_candado_se_suelta_aunque_la_logica_falle(monkeypatch):
    def falla(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr("qagent.sandbox.uso_disco.liberar_espacio", falla)
    monkeypatch.setattr("qagent.sandbox.uso_disco.medir_uso", lambda *a, **k: USO)

    with pytest.raises(RuntimeError):
        DesktopAPI().liberar_espacio()

    assert desktop._LIBERANDO_ESPACIO.acquire(blocking=False)
    desktop._LIBERANDO_ESPACIO.release()


def test_el_resultado_queda_en_la_bitacora(puente, caplog):
    import logging

    with caplog.at_level(logging.INFO):
        DesktopAPI().liberar_espacio()

    assert "Se liberaron 2,0 GB" in caplog.text

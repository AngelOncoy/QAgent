"""Revisión opcional de los contratos inferidos (#275, ADR-015)."""

from __future__ import annotations

import threading
from typing import Any

from qagent.app.desktop import DesktopAPI
from qagent.orchestrator.orquestador import Orquestador


def _contrato(objetivo: str, inferido: bool) -> dict[str, Any]:
    caso: dict[str, Any] = {
        "id": f"{objetivo}_caso",
        "entrada": {"a": 2},
        "valor_esperado": 4,
        "origen": "inferido" if inferido else "docstring",
    }
    if inferido:
        caso["evidencia"] = ["cuerpo"]
    return {
        "modulo": "calc.py",
        "objetivo": objetivo,
        "firma": "(a)",
        "casos": [caso],
    }


def _orquestador(revisor: Any) -> Orquestador:
    return Orquestador(object(), object(), object(), revisor_inferidos=revisor)  # type: ignore[arg-type]


def test_sin_revisor_el_plan_no_cambia() -> None:
    plan = [_contrato("doble", True), _contrato("triple", False)]

    assert _orquestador(None)._revisar_inferidos(plan) == plan


def test_el_revisor_solo_ve_los_contratos_inferidos() -> None:
    vistas: list[list[dict[str, Any]]] = []

    def revisor(propuestas: list[dict[str, Any]]) -> set[str]:
        vistas.append(propuestas)
        return {p["objetivo"] for p in propuestas}

    plan = [_contrato("doble", True), _contrato("triple", False)]

    resultado = _orquestador(revisor)._revisar_inferidos(plan)

    assert resultado == plan
    [propuestas] = vistas
    assert [p["objetivo"] for p in propuestas] == ["doble"]
    assert propuestas[0]["casos"][0]["evidencia"] == ["cuerpo"]


def test_lo_que_no_se_acepta_se_omite_con_su_motivo() -> None:
    orquestador = _orquestador(lambda propuestas: set())
    plan = [_contrato("doble", True), _contrato("triple", False)]

    resultado = orquestador._revisar_inferidos(plan)

    assert [c["objetivo"] for c in resultado] == ["triple"]  # el documentado sigue
    assert "revisión" in orquestador._motivos_omision["doble"]


def test_sin_inferidos_no_se_molesta_a_la_persona() -> None:
    def revisor(propuestas: list[dict[str, Any]]) -> set[str]:
        raise AssertionError("no debía llamarse")

    plan = [_contrato("triple", False)]

    assert _orquestador(revisor)._revisar_inferidos(plan) == plan


def test_la_api_espera_la_respuesta_de_la_interfaz() -> None:
    api = DesktopAPI()
    enviados: list[tuple[str, dict[str, Any]]] = []
    api.emit_event = lambda tipo, datos: enviados.append((tipo, datos))  # type: ignore[method-assign]
    resultado: list[set[str]] = []
    propuestas = [{"objetivo": "doble", "casos": []}]

    hilo = threading.Thread(
        target=lambda: resultado.append(api._revisar_inferidos(propuestas))
    )
    hilo.start()
    while not enviados:  # el evento sale antes de esperar
        pass
    respuesta = api.responder_revision_inferidos(["doble"])
    hilo.join(timeout=5)

    assert respuesta == {"ok": True}
    assert enviados == [("revision_inferidos", {"propuestas": propuestas})]
    assert resultado == [{"doble"}]


def test_responder_sin_revision_pendiente_no_hace_nada() -> None:
    respuesta = DesktopAPI().responder_revision_inferidos(["doble"])

    assert respuesta["ok"] is False


def test_detener_la_corrida_descarta_lo_pendiente() -> None:
    api = DesktopAPI()
    api.emit_event = lambda tipo, datos: None  # type: ignore[method-assign]
    api._cancelar_corrida.set()

    assert api._revisar_inferidos([{"objetivo": "doble", "casos": []}]) == set()

"""Corridas concurrentes: cancela solo la propia, conserva aislamiento y limpia."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from docker.models.containers import ContainerCollection

from qagent.lenguajes.java_sesion import sesion_java
from qagent.sandbox.ejecucion import ejecutar_en_sandbox
from qagent.sandbox.modelos import IMAGEN_JAVA, LimitesSandbox

pytestmark = pytest.mark.docker


def test_cancelar_una_corrida_no_detiene_la_otra_y_limpia_copias(
    tmp_path, cliente_docker, monkeypatch
):
    cancelar = threading.Event()
    creados = []
    temporizadores = []
    ejecutar = ContainerCollection.run

    def observar(self, *args, **opciones):
        assert opciones["network_mode"] == "none" and opciones["read_only"]
        assert opciones["cap_drop"] == ["ALL"]
        c = ejecutar(self, *args, **opciones)
        creados.append(c.id)
        if args[1][-1] == "qagent-308-cancelar":
            t = threading.Timer(1, cancelar.set)
            temporizadores.append(t)
            t.start()
        return c

    monkeypatch.setattr(ContainerCollection, "run", observar)
    copias = []

    def correr(nombre, retardo, consulta):
        proyecto = tmp_path / nombre
        proyecto.mkdir()
        (proyecto / "original.txt").write_text(nombre, encoding="utf-8")
        pruebas = tmp_path / ("tests-" + nombre)
        pruebas.mkdir()

        def leer(copia, salida):
            assert (copia / "marca.txt").read_text() == nombre
            copias.append(copia)

        with sesion_java(proyecto, consulta) as registro:
            resultado = ejecutar_en_sandbox(
                IMAGEN_JAVA,
                [
                    "sh",
                    "-c",
                    f"printf %s {nombre} > marca.txt; sleep {retardo}",
                    "qagent-308-cancelar" if consulta else "qagent-308-continuar",
                ],
                proyecto,
                pruebas,
                LimitesSandbox(cpus=1, memoria="256m", timeout_s=30),
                cliente=cliente_docker,
                al_terminar=leer,
            )
        assert (proyecto / "original.txt").read_text() == nombre
        assert not (proyecto / "marca.txt").exists()
        datos = registro.resumen()
        assert (
            datos["contadores"]["contenedores_creados"]
            == datos["contadores"]["contenedores_eliminados"]
            == 1
        )
        assert datos["datos"]["contenedores_propios_pendientes_al_cierre"] == 0
        return resultado

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(correr, "primera", 15, cancelar.is_set)
            b = pool.submit(correr, "segunda", 2, None)
            ra, rb = a.result(), b.result()
        assert ra.cancelado and not ra.oom_killed
        assert rb.exit_code == 0 and not rb.cancelado
        assert len(creados) == 2 and len(copias) == 2
        assert all(not p.exists() for p in copias)
        assert all(
            not cliente_docker.containers.list(all=True, filters={"id": i})
            for i in creados
        )
    finally:
        for t in temporizadores:
            t.cancel()

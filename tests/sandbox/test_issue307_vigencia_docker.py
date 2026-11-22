"""Dependencia modificada, regresión y nueva inferencia con Docker real offline."""

import json

import pytest
from docker.errors import NotFound

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.orchestrator import corrida
from qagent.orchestrator.regresion import ejecutar_regresion
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.storage.vista_reporte import vista_reporte
from tests.orchestrator.test_issue307_reutilizacion_java import (
    MODULO,
    SELECCION,
    ClienteGrabado,
    preparar,
)
from tests.sandbox.test_issue305_construccion_docker import pom_de_fixture

pytestmark = pytest.mark.docker


def test_dependencia_invalida_contrato_y_test_sin_convertir_inferencia_en_bug(
    cliente_docker, tmp_path, monkeypatch
):
    raiz = preparar(tmp_path / "proyecto")
    pom_de_fixture(raiz)
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    cliente = ClienteGrabado()
    monkeypatch.setattr(corrida, "crear_cliente", lambda *a, **k: cliente)
    config = cargar_configuracion(simulado=True).config
    imagen = cliente_docker.images.get(IMAGEN_JAVA).id
    contenedores = []
    coleccion = type(cliente_docker.containers)
    run = coleccion.run

    def registrar(self, *args, **kwargs):
        assert kwargs["network_mode"] == "none"
        assert kwargs["read_only"] and kwargs["cap_drop"] == ["ALL"]
        assert kwargs["security_opt"] == ["no-new-privileges"]
        contenedor = run(self, *args, **kwargs)
        contenedores.append(contenedor.id)
        return contenedor

    monkeypatch.setattr(coleccion, "run", registrar)
    originales = {
        p: p.read_bytes()
        for p in raiz.rglob("*")
        if p.is_file() and ".qagent" not in p.parts
    }
    inicial = corrida.ejecutar_corrida(
        raiz,
        "humo",
        config,
        None,
        simulado=True,
        preparar_imagen=lambda *a: imagen,
        seleccion=[SELECCION[0]],
    )
    assert inicial.estado == "fin" and inicial.aceptadas == 1, inicial
    contrato = almacen.leer_plan_modulo(MODULO)["contratos"][0]
    assert contrato["casos"][0]["origen"] == "inferido"
    assert inicial.tokens == 0
    historicos = {
        p: p.read_bytes() for p in almacen.carpeta_runs.rglob("*") if p.is_file()
    }
    cliente.llamadas.clear()
    control = ejecutar_regresion(
        raiz,
        "reg",
        config,
        run_id=almacen.crear_run()["run_id"],
        preparar_imagen=lambda *a: imagen,
        seleccion=[SELECCION[0]],
    )
    assert control.aceptadas == 1 and not cliente.llamadas, control
    antes = len(contenedores)
    ruta_b = raiz / "src/main/java/demo/B.java"
    ruta_b.write_text(
        ruta_b.read_text(encoding="utf-8").replace("return x*2", "return x*3"),
        encoding="utf-8",
    )
    obsoleta = ejecutar_regresion(
        raiz,
        "reg",
        config,
        run_id=almacen.crear_run()["run_id"],
        preparar_imagen=lambda *a: pytest.fail(
            "No preparar entorno para evidencia obsoleta"
        ),
        seleccion=[SELECCION[0]],
    )
    assert obsoleta.requieren_corrida_nueva == 1 and obsoleta.aceptadas == 0
    assert len(contenedores) == antes and not cliente.llamadas
    nueva = corrida.ejecutar_corrida(
        raiz,
        "humo",
        config,
        None,
        simulado=True,
        preparar_imagen=lambda *a: imagen,
        seleccion=[SELECCION[0]],
    )
    assert nueva.estado == "fin" and nueva.tokens == 0, nueva
    assert len([p for rol, p in cliente.llamadas if rol == "planner"]) == 2
    resultados = json.loads(
        (almacen.carpeta_run(nueva.run_id) / "results.json").read_text(encoding="utf-8")
    )
    detalle = json.loads(
        (almacen.carpeta_run(nueva.run_id) / "detalle.json").read_text(encoding="utf-8")
    )
    vista = vista_reporte(resultados, detalle)
    assert vista["con_contrato"] == 0 and vista["de_regresion"] == 1
    assert "hallazgo a revisar" in vista["aviso_hallazgo_inferido"]
    assert vista["funciones"][0]["respaldo"] == "inferido"
    assert all(p.read_bytes() == contenido for p, contenido in historicos.items())
    assert all(
        p.read_bytes() == contenido
        for p, contenido in originales.items()
        if p != ruta_b
    )
    assert len(contenedores) == 5
    for identificador in contenedores:
        with pytest.raises(NotFound):
            cliente_docker.containers.get(identificador)
    evidencia = {
        "inicial": inicial.a_dict(),
        "control": control.a_dict(),
        "obsoleta": obsoleta.a_dict(),
        "nueva": nueva.a_dict(),
        "contenedores": contenedores,
        "contrato_original": contrato,
    }
    # La prueba deja las evidencias en el directorio temporal, sin versionar artefactos.
    (tmp_path / "evidencia307.json").write_text(
        json.dumps(evidencia, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "issue": 307,
                "runs": [r.run_id for r in (inicial, control, obsoleta, nueva)],
                "contenedores_offline": len(contenedores),
                "tokens": 0,
            },
            ensure_ascii=True,
        )
    )

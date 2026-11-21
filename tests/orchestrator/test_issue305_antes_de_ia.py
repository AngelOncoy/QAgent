"""Orden real del orquestador: un fallo de construcción no llama a ningún LLM."""

import json

import pytest

from qagent import contracts
from qagent.config import cargar_configuracion
from qagent.lenguajes.base import ResultadoConstruccion
from qagent.llm import FakeLLMClient, RespuestaLLM
from qagent.orchestrator import corrida
from qagent.sandbox.modelos import ResultadoSandbox
from tests.agents.test_generator_java import CODIGO, preparar
from tests.lenguajes.test_issue305_construccion_java import POM


@pytest.fixture
def proyecto(tmp_path):
    contrato = preparar(tmp_path)
    (tmp_path / "pom.xml").write_text(POM, encoding="utf-8")
    return tmp_path, contrato


def cliente_contado(monkeypatch, contrato, estado, llamadas):
    class Cliente(FakeLLMClient):
        def generar(self, prompt, rol="planner"):
            assert estado["comprobada"], "Se consumió IA antes de la construcción"
            llamadas.append(rol)
            if rol == "generator":
                return RespuestaLLM(
                    contenido=CODIGO,
                    modelo="fake-java",
                    tokens_entrada=0,
                    tokens_salida=0,
                    costo_usd=0,
                )
            return super().generar(prompt, rol)

    monkeypatch.setattr(
        corrida,
        "crear_cliente",
        lambda *a, **k: Cliente(
            grabaciones={"Banco.java::Banco.duplicar": contrato["casos"]}
        ),
    )


@pytest.mark.parametrize(
    "categoria",
    [
        "compilacion",
        "dependencias",
        "incompatibilidad_herramienta",
        "configuracion",
        "timeout",
        "cancelado",
    ],
)
def test_fallo_previo_no_llama_planner_generator_ni_explicador(
    proyecto, monkeypatch, categoria
):
    ruta, contrato = proyecto
    estado, llamadas = {"comprobada": False}, []
    cliente_contado(monkeypatch, contrato, estado, llamadas)
    salida = ResultadoConstruccion(
        categoria if categoria in {"timeout", "cancelado"} else "fallido",
        categoria,
        "Fallo controlado de construcción antes de IA",
        'password="no-publicar"',
    )
    resultado = corrida.ejecutar_corrida(
        ruta,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda r: "imagen-simulada",
        validar_construccion=lambda *a, **k: salida,
    )
    assert resultado.estado == corrida.FALLO and llamadas == []
    assert resultado.tokens == 0
    assert resultado.construccion["categoria"] == categoria
    carpeta = ruta / ".qagent/runs" / resultado.run_id
    assert (
        json.loads((carpeta / "construccion.json").read_text(encoding="utf-8"))[
            "categoria"
        ]
        == categoria
    )
    assert "no-publicar" not in (carpeta / "construccion.log").read_text(
        encoding="utf-8"
    )
    assert resultado.bugs_detectados == 0


def test_compatible_llama_agentes_solo_despues_de_la_comprobacion(
    proyecto, monkeypatch
):
    ruta, contrato = proyecto
    estado, llamadas = {"comprobada": False}, []
    cliente_contado(monkeypatch, contrato, estado, llamadas)

    def validar(*a, **k):
        estado["comprobada"] = True
        return ResultadoConstruccion("aprobado", "aprobado", "Construcción aprobada")

    def ejecutar(*a, **k):
        return ResultadoSandbox(
            0,
            "",
            "",
            junit_xml='<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="test_positivo" classname="ejemplo.BancoTest" time="0.01"/></testsuite>',
        )

    resultado = corrida.ejecutar_corrida(
        ruta,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda r: "imagen-simulada",
        validar_construccion=validar,
        ejecutor=ejecutar,
    )
    assert "planner" in llamadas and "generator" in llamadas
    assert resultado.estado == corrida.FIN, resultado.motivo
    assert resultado.aceptadas == 1, resultado.motivo
    assert resultado.construccion["estado"] == "aprobado"
    # La etapa nueva debe guardarse; su ausencia histórica sigue siendo válida.
    for nombre in ("log.json", "results.json"):
        archivo = ruta / ".qagent/runs" / resultado.run_id / nombre
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        if nombre == "results.json":
            assert datos["duracion_etapas"].pop("construccion") == 0
            datos["resumen"]["duracion_etapas"].pop("construccion")
        contracts.validar(contracts.RUN_LOG, datos)


def test_error_de_preparar_imagen_tambien_bloquea_la_planificacion(
    proyecto, monkeypatch
):
    ruta, contrato = proyecto
    estado, llamadas = {"comprobada": False}, []
    cliente_contado(monkeypatch, contrato, estado, llamadas)

    def preparar_imagen(_ruta):
        error = RuntimeError("Dependencia ausente en preparación")
        error.log = (
            "Cannot download https://usuario:clave@repo.test/maven?token=privado"
        )
        raise error

    resultado = corrida.ejecutar_corrida(
        ruta,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=preparar_imagen,
    )
    assert resultado.estado == corrida.FALLO and llamadas == []
    log = ruta / ".qagent/runs" / resultado.run_id / "entorno.log"
    assert log.is_file()
    assert "usuario:clave" not in log.read_text(encoding="utf-8")
    assert "token=privado" not in log.read_text(encoding="utf-8")

"""Catálogo de proveedores y clientes con interfaz común (HU-30). Sin red: transporte simulado."""

from __future__ import annotations

from typing import Any

import pytest

from qagent.config import Claves
from qagent.llm import PrecioAgente, crear_cliente
from qagent.llm.cliente import ErrorLLM, LimiteProveedor, SinConexion
from qagent.llm.proveedores import (
    CONECTADO,
    KEY_INVALIDA,
    LIMITE_DE_USO,
    MODELO_NO_DISPONIBLE,
    SIN_CONEXION,
    CatalogoInvalido,
    ClienteCompatibleOpenAI,
    ClienteOpenRouter,
    ClienteSinTexto,
    cargar_catalogo,
    catalogo,
    cliente_de,
    motivo_de_error,
)

# Valor de prueba armado en tiempo de ejecución: no es una clave real.
CLAVE = "clave-de-prueba-" + "Z" * 16

PROVEEDORES_HU30 = [
    "anthropic",
    "xiaomi",
    "openai",
    "canopylabs",
    "meta-llama",
    "whisper",
    "openrouter",
    "gemini",
]


class Transporte:
    """Transporte simulado: registra cada envío y responde u objeta según se le diga."""

    def __init__(self, error: BaseException | None = None) -> None:
        self.envios: list[dict[str, Any]] = []
        self.error = error

    def enviar(self, **kwargs: Any) -> dict[str, Any]:
        self.envios.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"choices": [{"message": {"content": "OK"}}], "usage": {}}


# --- Catálogo ------------------------------------------------------------------------


def test_el_catalogo_ofrece_los_ocho_proveedores_de_la_historia():
    visibles = [pid for pid, p in catalogo().items() if p.visible]
    assert visibles == PROVEEDORES_HU30


def test_cada_proveedor_tiene_su_propia_variable_de_env():
    variables = [p.variable for p in catalogo().values()]
    assert len(variables) == len(set(variables))
    assert all(v.endswith("_API_KEY") for v in variables)


def test_whisper_y_canopylabs_no_son_de_texto():
    assert catalogo()["whisper"].tipo == "audio"
    assert catalogo()["canopylabs"].tipo == "voz"
    assert not catalogo()["whisper"].genera_texto
    assert all(
        catalogo()[p].genera_texto
        for p in PROVEEDORES_HU30
        if p not in {"whisper", "canopylabs"}
    )


@pytest.mark.parametrize("pid", ["canopylabs", "meta-llama", "whisper"])
def test_los_modelos_de_groq_usan_la_url_de_groq(pid):
    assert catalogo()[pid].endpoint.startswith("https://api.groq.com/openai/")


def test_openrouter_usa_nombres_completos():
    assert all("/" in m.id for m in catalogo()["openrouter"].modelos)


def test_un_modelo_sin_precio_queda_sin_confirmar():
    opus = catalogo()["anthropic"].modelo("claude-opus-5-5")
    sonnet = catalogo()["anthropic"].modelo("claude-sonnet-5-5")
    assert opus.precio_confirmado and opus.entrada_usd_m == 4.0
    assert not sonnet.precio_confirmado and sonnet.entrada_usd_m == 0


def test_catalogo_invalido(tmp_path):
    ruta = tmp_path / "proveedores.toml"
    ruta.write_text("[proveedores.x]\nnombre = 'X'\n", encoding="utf-8")
    with pytest.raises(CatalogoInvalido):
        cargar_catalogo(ruta)
    with pytest.raises(CatalogoInvalido):
        cargar_catalogo(tmp_path / "no-existe.toml")


# --- Clientes ------------------------------------------------------------------------


def test_cada_proveedor_tiene_su_cliente():
    assert isinstance(cliente_de("openrouter"), ClienteOpenRouter)
    assert isinstance(cliente_de("openrouter"), ClienteCompatibleOpenAI)
    assert isinstance(cliente_de("whisper"), ClienteSinTexto)
    assert isinstance(cliente_de("canopylabs"), ClienteSinTexto)
    assert type(cliente_de("gemini")) is ClienteCompatibleOpenAI


def test_validar_texto_envia_una_llamada_minima():
    transporte = Transporte()
    resultado = cliente_de("openai", transporte).validar(CLAVE, "gpt-5-mini")

    assert resultado.ok and resultado.mensaje == CONECTADO
    [envio] = transporte.envios
    assert envio["url"] == "https://api.openai.com/v1/chat/completions"
    assert envio["datos"]["model"] == "gpt-5-mini"
    assert envio["datos"]["max_completion_tokens"] == 16
    assert envio["cabeceras"]["Authorization"] == f"Bearer {CLAVE}"


def test_validar_openrouter_reutiliza_la_api_de_openai_con_su_key():
    transporte = Transporte()
    cliente_de("openrouter", transporte).validar(CLAVE, "google/gemini-2.5-flash")

    [envio] = transporte.envios
    assert envio["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert envio["datos"]["model"] == "google/gemini-2.5-flash"
    assert envio["datos"]["max_tokens"] == 16


def test_validar_whisper_consulta_el_modelo_sin_generar():
    transporte = Transporte()
    resultado = cliente_de("whisper", transporte).validar(CLAVE, "whisper-large-v3")

    assert resultado.ok
    [envio] = transporte.envios
    assert envio["metodo"] == "GET"
    assert envio["datos"] is None
    assert envio["url"] == "https://api.groq.com/openai/v1/models/whisper-large-v3"


def test_un_modelo_sin_texto_falla_al_generar():
    cliente = cliente_de("canopylabs").crear_cliente_llm(
        CLAVE, "canopylabs/orpheus-v1-english"
    )
    with pytest.raises(ErrorLLM, match="no genera texto"):
        cliente.generar("hola", rol="planner")


def test_la_fabrica_usa_el_catalogo_y_la_variable_del_proveedor():
    transporte = Transporte()
    precio = PrecioAgente(
        "generator", "meta-llama", "llama-3.3-70b-versatile", 0.0, 0.0
    )
    claves = Claves({"META_LLAMA_API_KEY": CLAVE})

    crear_cliente(precio, claves, simulado=False, transporte=transporte).generar("x")

    [envio] = transporte.envios
    assert envio["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert envio["cabeceras"]["Authorization"] == f"Bearer {CLAVE}"


# --- Motivos de fallo ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "motivo"),
    [
        (ErrorLLM("HTTP 401", codigo=401), KEY_INVALIDA),
        (ErrorLLM("HTTP 403", codigo=403), KEY_INVALIDA),
        (ErrorLLM("HTTP 404", codigo=404), MODELO_NO_DISPONIBLE),
        (
            ErrorLLM("HTTP 400", codigo=400, detalle='{"reason": "API_KEY_INVALID"}'),
            KEY_INVALIDA,
        ),
        (
            ErrorLLM("HTTP 400", codigo=400, detalle="The model `x` does not exist"),
            MODELO_NO_DISPONIBLE,
        ),
        (SinConexion("sin red"), SIN_CONEXION),
        (LimiteProveedor("HTTP 429", codigo=429), LIMITE_DE_USO),
    ],
)
def test_motivo_de_error(error, motivo):
    resultado = cliente_de("gemini", Transporte(error)).validar(
        CLAVE, "gemini-2.5-flash"
    )
    assert not resultado.ok
    assert resultado.mensaje == motivo


def test_otro_codigo_indica_el_http():
    assert "HTTP 500" in motivo_de_error(ErrorLLM("x", codigo=500)).mensaje


def test_el_detalle_nunca_lleva_la_key():
    error = ErrorLLM(f"rechazada {CLAVE}", codigo=401)
    resultado = cliente_de("openai", Transporte(error)).validar(CLAVE, "gpt-5")
    assert CLAVE not in resultado.detalle
    assert "***" in resultado.detalle

"""Catálogo de proveedores y clientes con interfaz común (HU-30). Sin red: transporte simulado."""

from __future__ import annotations

from typing import Any

import pytest

from qagent.config import Claves
from qagent.llm import PrecioAgente, crear_cliente
from qagent.llm.cliente import ErrorLLM, LimiteProveedor, SinConexion, error_http
from qagent.llm.proveedores import (
    CONECTADO,
    KEY_INVALIDA,
    LIMITE_DE_USO,
    MODELO_NO_DISPONIBLE,
    SATURADO,
    SIN_CONEXION,
    SIN_CREDITO,
    SIN_CUPO_GRATUITO,
    CatalogoInvalido,
    ClienteCompatibleOpenAI,
    ClienteOpenRouter,
    ClienteSinTexto,
    ModeloCatalogo,
    Proveedor,
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
    "openrouter",
    "gemini",
    "groq",
]

#: Proveedor de voz armado en la prueba: el catálogo ya no trae ninguno (BU-01), pero
#: el tipo «voz»/«audio» se sigue aceptando.
PROVEEDOR_VOZ = Proveedor(
    id="voz-prueba",
    nombre="Voz de prueba",
    variable="VOZ_PRUEBA_API_KEY",
    endpoint="https://voz.example/v1/chat/completions",
    modelos_url="https://voz.example/v1/models",
    tipo="voz",
    modelos=(ModeloCatalogo("voz-1", "Voz 1"),),
)


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


def test_el_catalogo_ofrece_los_seis_proveedores():
    visibles = [pid for pid, p in catalogo().items() if p.visible]
    assert visibles == PROVEEDORES_HU30


def test_cada_proveedor_tiene_su_propia_variable_de_env():
    variables = [p.variable for p in catalogo().values()]
    assert len(variables) == len(set(variables))
    assert all(v.endswith("_API_KEY") for v in variables)


def test_todos_los_proveedores_del_catalogo_son_de_texto():
    """BU-01: se quitaron Canopy Labs (voz), Whisper (audio) y Meta Llama."""
    assert all(p.genera_texto for p in catalogo().values())
    assert not {"canopylabs", "whisper", "meta-llama"} & set(catalogo())


def test_groq_ofrece_solo_sus_modelos_gratuitos_de_texto():
    groq = catalogo()["groq"]

    assert groq.visible
    assert groq.endpoint == "https://api.groq.com/openai/v1/chat/completions"
    assert [m.id for m in groq.modelos] == [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
    ]
    assert all(
        m.precio_confirmado and m.entrada_usd_m == m.salida_usd_m == 0
        for m in groq.modelos
    )


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
    assert isinstance(cliente_de(PROVEEDOR_VOZ), ClienteSinTexto)
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
    cliente_de("openrouter", transporte).validar(CLAVE, "google/gemma-4-31b-it:free")

    [envio] = transporte.envios
    assert envio["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert envio["datos"]["model"] == "google/gemma-4-31b-it:free"
    assert envio["datos"]["max_tokens"] == 16


def test_validar_un_modelo_sin_texto_consulta_el_modelo_sin_generar():
    transporte = Transporte()
    resultado = cliente_de(PROVEEDOR_VOZ, transporte).validar(CLAVE, "voz-1")

    assert resultado.ok
    [envio] = transporte.envios
    assert envio["metodo"] == "GET"
    assert envio["datos"] is None
    assert envio["url"] == "https://voz.example/v1/models/voz-1"


def test_un_modelo_sin_texto_falla_al_generar():
    cliente = cliente_de(PROVEEDOR_VOZ).crear_cliente_llm(CLAVE, "voz-1")
    with pytest.raises(ErrorLLM, match="no genera texto"):
        cliente.generar("hola", rol="planner")


def test_la_fabrica_usa_el_catalogo_y_la_variable_del_proveedor():
    transporte = Transporte()
    precio = PrecioAgente("generator", "groq", "openai/gpt-oss-120b", 0.0, 0.0)
    claves = Claves({"GROQ_API_KEY": CLAVE})

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
        (LimiteProveedor("HTTP 503", codigo=503), SATURADO),
        (ErrorLLM("HTTP 402", codigo=402), SIN_CREDITO),
        (error_http(429), LIMITE_DE_USO),
        (error_http(503), SATURADO),
        (error_http(402, '{"error": "Insufficient credits"}'), SIN_CREDITO),
        (error_http(429, "Quota exceeded, limit: 0, model: x"), SIN_CUPO_GRATUITO),
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


def test_openrouter_ofrece_solo_modelos_gratuitos_de_gemma_4_y_nemotron():
    """BU-01: los modelos de pago fallaban sin crédito (HTTP 402)."""
    modelos = catalogo()["openrouter"].modelos

    assert all(m.id.endswith(":free") for m in modelos)
    assert all(
        m.precio_confirmado and m.entrada_usd_m == m.salida_usd_m == 0 for m in modelos
    )
    ids = [m.id for m in modelos]
    assert any(i.startswith("google/gemma-4-") for i in ids)
    assert any(i.startswith("nvidia/nemotron-") for i in ids)

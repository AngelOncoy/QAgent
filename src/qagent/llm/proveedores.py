"""Catálogo de proveedores y un cliente por proveedor con interfaz común (HU-30).

El catálogo (`proveedores.toml`, junto a este módulo) dice qué proveedores y modelos
puede elegir el usuario para cada agente. Cada proveedor tiene un `ClienteProveedor`
con dos operaciones:

- `validar(clave, modelo)`: llamada mínima de prueba antes de guardar la configuración.
- `completar(clave, modelo, prompt)`: una respuesta del modelo; los agentes usan
  `crear_cliente_llm()`, que devuelve el `ClienteLLM` de siempre.

Todos los proveedores del catálogo exponen una API compatible con OpenAI (OpenRouter
incluido), así que comparten `ClienteCompatibleOpenAI`; solo cambian la URL, la cabecera
de la clave y el parámetro que limita la salida. Si el catálogo trae modelos de voz o
de audio (`tipo`), no generan texto: se validan consultando el modelo y no completan.

Este módulo nunca guarda ni registra claves: las recibe del llamador y las redacta de
cualquier mensaje de error.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from qagent.llm.cliente import (
    AGENTE_USUARIO,
    ClienteLLMReal,
    ErrorLLM,
    LimiteProveedor,
    SinConexion,
    SinCupoGratuito,
    TransporteHTTP,
    TransporteLLM,
)
from qagent.llm.modelos import ClienteLLM, RespuestaLLM

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

RUTA_CATALOGO = Path(__file__).resolve().with_name("proveedores.toml")

#: Tipos de modelo del catálogo. Solo "texto" genera las respuestas que usan los agentes.
TIPO_TEXTO = "texto"
TIPOS = {
    TIPO_TEXTO: "texto",
    "voz": "texto → voz",
    "audio": "audio → texto",
}

#: Motivos que ve el usuario cuando la prueba de conexión falla (HU-30, criterio 6).
CONECTADO = "Conectado ✓"
KEY_INVALIDA = "Key inválida"
SIN_CONEXION = "Sin conexión"
MODELO_NO_DISPONIBLE = "Modelo no disponible"
LIMITE_DE_USO = (
    "Límite de uso de la cuenta alcanzado; inténtalo más tarde (las keys de la misma "
    "cuenta o proyecto comparten este límite)"
)
SATURADO = "El modelo está saturado en el proveedor; inténtalo en unos minutos"
SIN_CUPO_GRATUITO = (
    "Este modelo no tiene cupo gratuito en tu cuenta (limit: 0); elige otro modelo "
    "o activa la facturación del proveedor"
)
SIN_CREDITO = (
    "La cuenta no tiene crédito para este modelo; recarga crédito o elige un modelo "
    "gratuito (:free)"
)

PROMPT_PRUEBA = "Responde solo con la palabra OK."
TOKENS_PRUEBA = 16
TIMEOUT_VALIDACION_S = 30.0


@dataclass(frozen=True)
class ModeloCatalogo:
    """Un modelo que el usuario puede elegir.

    Atributos:
        id: identificador que se envía al proveedor (en OpenRouter, `empresa/modelo`).
        nombre: texto visible en la lista.
        entrada_usd_m: precio de entrada en US$ por millón de tokens (0 si no se conoce).
        salida_usd_m: precio de salida en US$ por millón de tokens (0 si no se conoce).
        precio_confirmado: False si el catálogo no trae precio (se usa 0).
    """

    id: str
    nombre: str
    entrada_usd_m: float = 0.0
    salida_usd_m: float = 0.0
    precio_confirmado: bool = False


@dataclass(frozen=True)
class Proveedor:
    """Un proveedor del catálogo. Nunca contiene claves, solo el nombre de su variable."""

    id: str
    nombre: str
    variable: str
    endpoint: str
    modelos_url: str
    tipo: str = TIPO_TEXTO
    cabecera_clave: str | None = None
    param_limite: str = "max_tokens"
    visible: bool = True
    modelos: tuple[ModeloCatalogo, ...] = field(default_factory=tuple)

    @property
    def genera_texto(self) -> bool:
        """True si sus modelos sirven como agente (devuelven texto)."""
        return self.tipo == TIPO_TEXTO

    def modelo(self, modelo_id: str) -> ModeloCatalogo | None:
        """Modelo del catálogo con ese id, o None."""
        return next((m for m in self.modelos if m.id == modelo_id), None)


class CatalogoInvalido(ValueError):
    """`proveedores.toml` falta o tiene un formato que no se puede usar."""


@dataclass(frozen=True)
class ResultadoValidacion:
    """Resultado de la llamada de prueba a un proveedor.

    Atributos:
        ok: True si el proveedor respondió bien con esa clave y ese modelo.
        mensaje: "Conectado ✓" o el motivo del fallo, para el usuario.
        detalle: información técnica sin la clave (código HTTP, respuesta resumida).
    """

    ok: bool
    mensaje: str
    detalle: str = ""


def cargar_catalogo(ruta: str | Path = RUTA_CATALOGO) -> dict[str, Proveedor]:
    """Lee el catálogo de proveedores y modelos.

    Raises:
        CatalogoInvalido: si el archivo no existe, no es TOML o le falta un campo.
    """
    try:
        with open(ruta, "rb") as archivo:
            datos = tomllib.load(archivo)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CatalogoInvalido(f"No se pudo leer {ruta}: {error}") from error
    proveedores = datos.get("proveedores")
    if not isinstance(proveedores, dict) or not proveedores:
        raise CatalogoInvalido(f"{ruta} no define [proveedores.*].")
    return {pid: _leer_proveedor(pid, tabla) for pid, tabla in proveedores.items()}


def _leer_proveedor(pid: str, tabla: dict[str, Any]) -> Proveedor:
    try:
        tipo = str(tabla.get("tipo", TIPO_TEXTO))
        if tipo not in TIPOS:
            raise CatalogoInvalido(f"Tipo desconocido '{tipo}' en [proveedores.{pid}].")
        modelos = tuple(_leer_modelo(m) for m in tabla["modelos"])
        if not modelos:
            raise CatalogoInvalido(f"[proveedores.{pid}] no tiene modelos.")
        return Proveedor(
            id=pid,
            nombre=str(tabla["nombre"]),
            variable=str(tabla["variable"]),
            endpoint=str(tabla["endpoint"]),
            modelos_url=str(tabla["modelos_url"]),
            tipo=tipo,
            cabecera_clave=tabla.get("cabecera_clave") or None,
            param_limite=str(tabla.get("param_limite", "max_tokens")),
            visible=bool(tabla.get("visible", True)),
            modelos=modelos,
        )
    except (KeyError, TypeError) as error:
        raise CatalogoInvalido(
            f"Falta o sobra un campo en [proveedores.{pid}]: {error}"
        ) from error


def _leer_modelo(tabla: dict[str, Any]) -> ModeloCatalogo:
    confirmado = "entrada" in tabla and "salida" in tabla
    return ModeloCatalogo(
        id=str(tabla["id"]),
        nombre=str(tabla.get("nombre") or tabla["id"]),
        entrada_usd_m=float(tabla.get("entrada", 0)),
        salida_usd_m=float(tabla.get("salida", 0)),
        precio_confirmado=confirmado,
    )


@lru_cache(maxsize=1)
def catalogo() -> dict[str, Proveedor]:
    """Catálogo por defecto (`proveedores.toml`), leído una sola vez."""
    return cargar_catalogo()


def variable_por_proveedor() -> dict[str, str]:
    """`{"openai": "OPENAI_API_KEY", ...}` para todos los proveedores del catálogo."""
    return {pid: p.variable for pid, p in catalogo().items()}


# --- Clientes -------------------------------------------------------------------------


class ClienteProveedor:
    """Interfaz común: lo que los agentes y la configuración necesitan de un proveedor."""

    def __init__(
        self, proveedor: Proveedor, transporte: TransporteLLM | None = None
    ) -> None:
        self.proveedor = proveedor
        self.transporte = transporte or TransporteHTTP()

    def validar(self, clave: str, modelo: str) -> ResultadoValidacion:
        """Llamada mínima con `clave` y `modelo`; nunca lanza excepciones."""
        raise NotImplementedError

    def crear_cliente_llm(self, clave: str, modelo: str, **opciones: Any) -> ClienteLLM:
        """Cliente que usan los agentes (`generar(prompt, rol)`)."""
        raise NotImplementedError

    def completar(self, clave: str, modelo: str, prompt: str) -> RespuestaLLM:
        """Una respuesta del modelo para `prompt`."""
        return self.crear_cliente_llm(clave, modelo).generar(prompt)

    def cabeceras(self, clave: str) -> dict[str, str]:
        """Cabeceras con la clave del proveedor."""
        cabeceras = {
            "Authorization": f"Bearer {clave}",
            "Content-Type": "application/json",
            "User-Agent": AGENTE_USUARIO,
        }
        if self.proveedor.cabecera_clave:
            cabeceras[self.proveedor.cabecera_clave] = clave
        return cabeceras


class ClienteCompatibleOpenAI(ClienteProveedor):
    """Proveedor con API de chat compatible con OpenAI (casi todos los del catálogo)."""

    def validar(self, clave: str, modelo: str) -> ResultadoValidacion:
        """Envía un prompt corto con salida limitada; basta con que responda HTTP 200."""
        datos = {
            "model": modelo,
            "messages": [{"role": "user", "content": PROMPT_PRUEBA}],
            self.proveedor.param_limite: TOKENS_PRUEBA,
        }
        return _probar(
            clave,
            lambda: self.transporte.enviar(
                url=self.proveedor.endpoint,
                cabeceras=self.cabeceras(clave),
                datos=datos,
                timeout_s=TIMEOUT_VALIDACION_S,
            ),
        )

    def crear_cliente_llm(self, clave: str, modelo: str, **opciones: Any) -> ClienteLLM:
        """`ClienteLLMReal` con la URL y la cabecera del proveedor.

        `opciones` admite `endpoint` (URL propia de config.toml), `esfuerzo` y
        `timeout_s`.
        """
        endpoint = opciones.pop("endpoint", None) or self.proveedor.endpoint
        return ClienteLLMReal(
            modelo=modelo,
            clave=clave,
            endpoint=endpoint,
            transporte=self.transporte,
            cabecera_clave=self.proveedor.cabecera_clave,
            **opciones,
        )


class ClienteOpenRouter(ClienteCompatibleOpenAI):
    """OpenRouter: misma API que OpenAI, modelos con nombre completo `empresa/modelo`."""

    def cabeceras(self, clave: str) -> dict[str, str]:
        """Agrega la identificación de la aplicación que recomienda OpenRouter."""
        return {**super().cabeceras(clave), "X-Title": "QAgent"}


class ClienteSinTexto(ClienteProveedor):
    """Modelos de voz o de audio (`tipo` "voz" o "audio"): no devuelven texto de chat.

    La validación consulta el modelo (`GET <modelos_url>/<id>`), lo que comprueba la
    clave y que el modelo exista sin generar audio. Si se asignan a un agente, cada
    llamada falla con un `ErrorLLM` claro y la corrida lo registra como fallo
    controlado.
    """

    def validar(self, clave: str, modelo: str) -> ResultadoValidacion:
        """Consulta el modelo con la clave."""
        cabeceras = self.cabeceras(clave)
        cabeceras.pop("Content-Type", None)
        return _probar(
            clave,
            lambda: self.transporte.enviar(
                url=f"{self.proveedor.modelos_url}/{quote(modelo, safe='')}",
                cabeceras=cabeceras,
                datos=None,
                timeout_s=TIMEOUT_VALIDACION_S,
                metodo="GET",
            ),
        )

    def crear_cliente_llm(self, clave: str, modelo: str, **opciones: Any) -> ClienteLLM:
        """Cliente que rechaza cada llamada: el modelo no genera texto."""
        return _ClienteQueNoGeneraTexto(self.proveedor, modelo)


class _ClienteQueNoGeneraTexto:
    """`ClienteLLM` de un modelo de voz o de audio asignado a un agente."""

    def __init__(self, proveedor: Proveedor, modelo: str) -> None:
        self.proveedor = proveedor
        self.modelo = modelo

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        """Siempre falla: el modelo no devuelve texto."""
        raise ErrorLLM(
            f"El modelo {self.modelo} de {self.proveedor.nombre} es de tipo "
            f"«{TIPOS[self.proveedor.tipo]}» y no genera texto: el {rol} no puede "
            "usarlo. Elige un modelo de texto en Configuración."
        )


def cliente_de(
    proveedor: str | Proveedor, transporte: TransporteLLM | None = None
) -> ClienteProveedor:
    """Cliente del proveedor indicado (por id o por `Proveedor`).

    Raises:
        KeyError: si el id no está en el catálogo.
    """
    datos = catalogo()[proveedor] if isinstance(proveedor, str) else proveedor
    if not datos.genera_texto:
        return ClienteSinTexto(datos, transporte)
    if datos.id == "openrouter":
        return ClienteOpenRouter(datos, transporte)
    return ClienteCompatibleOpenAI(datos, transporte)


# --- Traducción de errores ------------------------------------------------------------

_PISTAS_CLAVE = ("api key", "api_key", "apikey", "unauthorized", "authentication")
_PISTAS_MODELO = ("model", "modelo", "not found", "does not exist", "not supported")


def _probar(clave: str, llamada: Any) -> ResultadoValidacion:
    """Ejecuta `llamada` y traduce el resultado a un mensaje para el usuario."""
    try:
        llamada()
    except Exception as error:  # noqa: BLE001 - toda falla se informa, nunca se propaga
        return motivo_de_error(error, clave)
    return ResultadoValidacion(True, CONECTADO)


def motivo_de_error(error: BaseException, clave: str = "") -> ResultadoValidacion:
    """Traduce un error del proveedor a «Key inválida», «Sin conexión», etc.

    El detalle técnico se devuelve sin la clave.
    """
    detalle = str(error)
    if clave:
        detalle = detalle.replace(clave, "***")
    if isinstance(error, SinConexion):
        return ResultadoValidacion(False, SIN_CONEXION, detalle)
    if isinstance(error, SinCupoGratuito):
        return ResultadoValidacion(False, SIN_CUPO_GRATUITO, detalle)
    if isinstance(error, LimiteProveedor):
        motivo = SATURADO if error.codigo == 503 else LIMITE_DE_USO
        return ResultadoValidacion(False, motivo, detalle)
    if not isinstance(error, ErrorLLM) or error.codigo is None:
        return ResultadoValidacion(False, f"Error inesperado del proveedor: {detalle}")

    cuerpo = error.detalle.lower()
    if error.codigo == 402:
        return ResultadoValidacion(False, SIN_CREDITO, detalle)
    if error.codigo in (401, 403):
        return ResultadoValidacion(False, KEY_INVALIDA, detalle)
    if error.codigo == 404:
        return ResultadoValidacion(False, MODELO_NO_DISPONIBLE, detalle)
    if error.codigo in (400, 422):
        # Gemini responde 400 (API_KEY_INVALID) a una clave mala; se mira el cuerpo.
        if any(pista in cuerpo for pista in _PISTAS_CLAVE):
            return ResultadoValidacion(False, KEY_INVALIDA, detalle)
        if any(pista in cuerpo for pista in _PISTAS_MODELO):
            return ResultadoValidacion(False, MODELO_NO_DISPONIBLE, detalle)
    return ResultadoValidacion(
        False, f"El proveedor respondió con un error (HTTP {error.codigo})", detalle
    )

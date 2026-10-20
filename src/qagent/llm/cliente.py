"""Clientes LLM real y simulado utilizados por los agentes de QAgent."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from qagent.llm.fake import FakeLLMClient
from qagent.llm.modelos import ClienteLLM, RespuestaLLM


def estimar_tokens(texto: str) -> int:
    """Estimación heurística de tokens cuando el proveedor no los reporta (~4 caracteres por token)."""
    if not texto or not texto.strip():
        return 0
    return max(1, (len(texto) + 3) // 4)


class ErrorLLM(RuntimeError):
    """Error controlado durante una llamada a un proveedor LLM.

    Atributos:
        codigo: código HTTP con el que respondió el proveedor, o None si no hubo
            respuesta HTTP.
        detalle: cuerpo resumido de la respuesta de error (puede estar vacío).
    """

    def __init__(
        self, mensaje: str, *, codigo: int | None = None, detalle: str = ""
    ) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.detalle = detalle


class SinConexion(ErrorLLM):
    """No se llegó al proveedor: red, DNS, firewall o tiempo de espera agotado."""


class LimiteProveedor(ErrorLLM):
    """El proveedor rechazó la llamada por un motivo pasajero: se puede reintentar.

    Las subclases dicen cuál: `CupoAgotado` (HTTP 429) o `ProveedorSaturado` (503).

    Atributos:
        espera_s: segundos que pidió esperar el proveedor (`Retry-After`), o None.
    """

    def __init__(
        self,
        mensaje: str,
        espera_s: float | None = None,
        *,
        codigo: int | None = None,
        detalle: str = "",
    ) -> None:
        super().__init__(mensaje, codigo=codigo, detalle=detalle)
        self.espera_s = espera_s


class CupoAgotado(LimiteProveedor):
    """HTTP 429: se agotó el límite de uso de la cuenta (por minuto o por día)."""


class ProveedorSaturado(LimiteProveedor):
    """HTTP 503: el modelo está saturado en el proveedor; no es culpa de la cuenta."""


class SinCupoGratuito(ErrorLLM):
    """HTTP 429 con `limit: 0`: el modelo no tiene cupo en la capa gratuita.

    Gemini responde así a los modelos que la cuenta no puede usar sin facturación. No
    es pasajero: reintentar no sirve, hay que elegir otro modelo.
    """


class SinCredito(ErrorLLM):
    """HTTP 402: la cuenta no tiene crédito para el modelo (p. ej. OpenRouter)."""


#: Códigos HTTP que se reintentan: límite de uso de la capa gratuita y saturación.
CODIGOS_REINTENTABLES = frozenset({429, 503})
#: Cupo de la capa gratuita igual a cero en la respuesta de Gemini
#: («Quota exceeded for metric: …, limit: 0, model: …»).
_LIMITE_CERO = re.compile(r"\blimit\W{0,3}\s*0(?![\d.])", re.IGNORECASE)
#: Identifica al cliente ante el proveedor. Sin esta cabecera, `urllib` se presenta
#: como «Python-urllib» y Cloudflare (p. ej. Groq) lo rechaza con HTTP 403 / error 1010.
AGENTE_USUARIO = "QAgent/1.0"
#: Largo máximo del detalle del proveedor que se agrega a un error HTTP.
LARGO_DETALLE_ERROR = 300
#: Bytes que se leen de la respuesta en cada vuelta, para revisar el plazo entre una y
#: otra (algunos proveedores mandan espacios para mantener viva la conexión).
TAMANO_BLOQUE_LECTURA = 65536
#: Mínimo de tiempo que debe quedar del plazo para que valga la pena reintentar.
MINIMO_PARA_REINTENTAR_S = 5.0


class TransporteLLM(Protocol):
    """Interfaz del transporte utilizado para enviar solicitudes al proveedor."""

    def enviar(
        self,
        *,
        url: str,
        cabeceras: dict[str, str],
        datos: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        """Envía una solicitud JSON y devuelve la respuesta decodificada."""
        ...


class TransporteHTTP:
    """Transporte HTTP basado únicamente en la biblioteca estándar."""

    def enviar(
        self,
        *,
        url: str,
        cabeceras: dict[str, str],
        datos: dict[str, Any] | None,
        timeout_s: float,
        metodo: str = "POST",
    ) -> dict[str, Any]:
        """Realiza una solicitud al proveedor LLM (POST por defecto).

        `timeout_s` es el tiempo **total** de la solicitud, no solo el silencio máximo
        del socket: el timeout de `urlopen` se reinicia con cada byte recibido, así que
        un proveedor lento que envía la respuesta de a poco podía pasar varios minutos.

        Args:
            url: Endpoint del proveedor.
            cabeceras: Cabeceras HTTP, incluida la autorización.
            datos: Cuerpo JSON de la solicitud; None en un GET.
            timeout_s: Tiempo máximo total en segundos.
            metodo: "POST" o "GET" (consultar un modelo al validar la clave).

        Returns:
            Respuesta JSON convertida en un diccionario.

        Raises:
            ErrorLLM: Si la solicitud o la respuesta no son válidas.
        """
        cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else None
        solicitud = Request(
            url=url,
            data=cuerpo,
            headers=cabeceras,
            method=metodo,
        )

        plazo = time.monotonic() + timeout_s
        try:
            with urlopen(solicitud, timeout=timeout_s) as respuesta:
                contenido = _leer_con_plazo(respuesta, plazo).decode("utf-8")
        except HTTPError as error:
            raise error_http(
                error.code, _cuerpo_error(error), _segundos_retry_after(error)
            ) from error
        except URLError as error:
            raise SinConexion(
                f"No se pudo conectar con el proveedor LLM: {error.reason}"
            ) from error
        except TimeoutError as error:
            raise SinConexion(
                f"El proveedor LLM no respondió en {timeout_s:g} segundos."
            ) from error
        except OSError as error:
            raise SinConexion(
                f"Error de red al contactar al proveedor LLM: {error}"
            ) from error

        try:
            datos_respuesta = json.loads(contenido)
        except json.JSONDecodeError as error:
            raise ErrorLLM("El proveedor LLM devolvió JSON inválido.") from error

        if not isinstance(datos_respuesta, dict):
            raise ErrorLLM("El proveedor LLM no devolvió un objeto JSON.")

        return datos_respuesta


def _leer_con_plazo(respuesta: Any, plazo: float) -> bytes:
    """Lee el cuerpo de la respuesta por bloques sin pasar de `plazo` (reloj monotónico).

    Raises:
        TimeoutError: si se acaba el plazo antes de terminar de leer.
    """
    leer = getattr(respuesta, "read1", None) or respuesta.read
    partes: list[bytes] = []
    while True:
        restante = plazo - time.monotonic()
        if restante <= 0:
            raise TimeoutError("se agotó el plazo de la solicitud")
        _limitar_espera_del_socket(respuesta, restante)
        bloque = leer(TAMANO_BLOQUE_LECTURA)
        if not bloque:
            return b"".join(partes)
        partes.append(bloque)


def _limitar_espera_del_socket(respuesta: Any, segundos: float) -> None:
    """Hace que la próxima lectura espere como mucho lo que queda del plazo.

    Accede al socket de `http.client`; si la respuesta no lo expone (otra
    implementación o un doble de prueba), se queda con el timeout de `urlopen`.
    """
    socket = getattr(
        getattr(getattr(respuesta, "fp", None), "raw", None), "_sock", None
    )
    if socket is None:
        return
    try:
        socket.settimeout(max(segundos, 0.05))
    except OSError:
        pass


class ClienteLLMReal:
    """Cliente para proveedores con una API de chat compatible con OpenAI."""

    def __init__(
        self,
        modelo: str,
        clave: str,
        endpoint: str,
        *,
        transporte: TransporteLLM | None = None,
        timeout_s: float = 60.0,
        esfuerzo: str | None = None,
        cabecera_clave: str | None = None,
        reintentos_limite: int = 3,
        espera_maxima_s: float = 20.0,
        esperar: Callable[[float], None] = time.sleep,
        plazo_total_s: float | None = None,
    ) -> None:
        """Inicializa el cliente real.

        Args:
            modelo: Identificador del modelo configurado.
            clave: Clave del proveedor cargada desde `.env`.
            endpoint: URL del endpoint de chat del proveedor.
            transporte: Transporte reemplazable durante las pruebas.
            timeout_s: Tiempo máximo total de cada solicitud.
            esfuerzo: Valor de `reasoning_effort`; si es None no se envía.
            cabecera_clave: Cabecera adicional con la clave, para proveedores que
                no usan `Authorization: Bearer` (ej. `api-key` en Xiaomi MiMo).
            reintentos_limite: reintentos ante HTTP 429/503 (capas gratuitas con
                límite por minuto); 0 desactiva los reintentos.
            espera_maxima_s: tope de cada espera entre reintentos, aunque el
                proveedor pida más (el orquestador corta un paso a los 120 s).
            esperar: función de espera; se reemplaza en las pruebas.
            plazo_total_s: tiempo máximo de `generar()` sumando reintentos y esperas;
                por defecto `timeout_s`. Así una llamada nunca llega al timeout por
                paso del orquestador, ni siquiera con el sandbox del Reviewer.
        """
        if not modelo.strip():
            raise ValueError("El modelo LLM no puede estar vacío.")
        if not clave.strip():
            raise ValueError("La clave del proveedor no puede estar vacía.")
        if not endpoint.strip():
            raise ValueError("El endpoint del proveedor no puede estar vacío.")
        if timeout_s <= 0:
            raise ValueError("El timeout debe ser mayor que cero.")
        if reintentos_limite < 0:
            raise ValueError("Los reintentos no pueden ser negativos.")
        if plazo_total_s is not None and plazo_total_s <= 0:
            raise ValueError("El plazo total debe ser mayor que cero.")

        self.modelo = modelo
        self._clave = clave
        self.endpoint = endpoint
        self.transporte = transporte or TransporteHTTP()
        self.timeout_s = timeout_s
        self.esfuerzo = esfuerzo
        self.cabecera_clave = cabecera_clave
        self.reintentos_limite = reintentos_limite
        self.espera_maxima_s = espera_maxima_s
        self._esperar = esperar
        self.plazo_total_s = plazo_total_s if plazo_total_s is not None else timeout_s

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        """Genera una respuesta mediante el proveedor configurado.

        Args:
            prompt: Instrucción que se enviará al modelo.
            rol: Agente que realiza la solicitud.

        Returns:
            Respuesta uniforme con contenido, modelo y consumo de tokens.

        Raises:
            ErrorLLM: Si la solicitud falla o la respuesta está incompleta.
        """
        cabeceras = {
            "Authorization": f"Bearer {self._clave}",
            "Content-Type": "application/json",
            "User-Agent": AGENTE_USUARIO,
        }
        if self.cabecera_clave:
            cabeceras[self.cabecera_clave] = self._clave
        datos: dict[str, Any] = {
            "model": self.modelo,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"Actúas como el agente {rol} de QAgent. "
                        "Responde únicamente en el formato solicitado."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }
        if self.esfuerzo:
            datos["reasoning_effort"] = self.esfuerzo

        try:
            respuesta = self._enviar_con_reintentos(cabeceras, datos)
            return self._convertir_respuesta(respuesta, prompt=prompt)
        except Exception as error:
            mensaje = str(error).replace(self._clave, "***")
            if isinstance(error, ErrorLLM):
                raise ErrorLLM(mensaje) from error
            raise ErrorLLM(f"Error al llamar al proveedor LLM: {mensaje}") from error

    def _enviar_con_reintentos(
        self, cabeceras: dict[str, str], datos: dict[str, Any]
    ) -> dict[str, Any]:
        """Envía la solicitud; ante HTTP 429/503 espera y reintenta (capas gratuitas).

        Todo, solicitudes y esperas, cabe en `plazo_total_s`: cada solicitud recibe lo
        que queda del plazo y no se reintenta si ya no alcanza.
        """
        plazo = time.monotonic() + self.plazo_total_s
        for intento in range(self.reintentos_limite + 1):
            restante = plazo - time.monotonic()
            try:
                return self.transporte.enviar(
                    url=self.endpoint,
                    cabeceras=cabeceras,
                    datos=datos,
                    timeout_s=max(min(self.timeout_s, restante), 0.1),
                )
            except LimiteProveedor as error:
                if intento == self.reintentos_limite:
                    raise
                espera = min(
                    max(
                        error.espera_s
                        if error.espera_s is not None
                        else 2.0 * 2**intento,
                        0.0,
                    ),
                    self.espera_maxima_s,
                )
                if plazo - time.monotonic() - espera < MINIMO_PARA_REINTENTAR_S:
                    raise
                self._esperar(espera)
        raise AssertionError("inalcanzable")  # pragma: no cover

    def _convertir_respuesta(
        self, datos: dict[str, Any], prompt: str = ""
    ) -> RespuestaLLM:
        """Convierte la respuesta del proveedor al formato común de QAgent."""
        try:
            contenido = datos["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ErrorLLM(
                "La respuesta del proveedor no contiene contenido generado."
            ) from error

        if not isinstance(contenido, str) or not contenido.strip():
            raise ErrorLLM("La respuesta del proveedor no contiene contenido generado.")

        uso = datos.get("usage", {})
        if not isinstance(uso, dict):
            uso = {}

        es_estimado = False
        tiene_tokens = "prompt_tokens" in uso or "completion_tokens" in uso
        if tiene_tokens:
            tokens_entrada = self._entero_no_negativo(uso.get("prompt_tokens", 0))
            tokens_salida = self._entero_no_negativo(uso.get("completion_tokens", 0))
        else:
            tokens_entrada = estimar_tokens(prompt)
            tokens_salida = estimar_tokens(contenido)
            es_estimado = True

        modelo_respuesta = datos.get("model", self.modelo)
        if not isinstance(modelo_respuesta, str) or not modelo_respuesta:
            modelo_respuesta = self.modelo

        return RespuestaLLM(
            contenido=contenido,
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
            costo_usd=0.0,
            modelo=modelo_respuesta,
            es_estimado=es_estimado,
            datos_json=datos,
        )

    @staticmethod
    def _entero_no_negativo(valor: Any) -> int:
        """Convierte un contador de tokens a entero no negativo."""
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            return 0
        return max(numero, 0)


#: Variable que activa la IA simulada (EN-11), en el sistema o en el `.env`.
VARIABLE_SIMULADA = "QAGENT_FAKE_LLM"
#: Nombre anterior (PyAgent): se sigue aceptando para no romper `.env` ni scripts.
VARIABLE_SIMULADA_ANTERIOR = "PYAGENT_FAKE_LLM"


def valor_simulado(entorno: Mapping[str, str]) -> str | None:
    """Valor de la bandera de IA simulada en `entorno`, o None si no está definida.

    Si están las dos, manda `QAGENT_FAKE_LLM`; la anterior solo se usa como respaldo.
    """
    for nombre in (VARIABLE_SIMULADA, VARIABLE_SIMULADA_ANTERIOR):
        if nombre in entorno:
            return entorno[nombre]
    return None


def es_modo_simulado() -> bool:
    """Verifica si la simulación está activa mediante QAGENT_FAKE_LLM=1."""
    return (valor_simulado(os.environ) or "0").strip() == "1"


def obtener_cliente_llm(
    modelo: str = "default-model",
    *,
    clave: str | None = None,
    endpoint: str | None = None,
    transporte: TransporteLLM | None = None,
    timeout_s: float = 60.0,
) -> ClienteLLM:
    """Devuelve el cliente LLM simulado o real según el entorno.

    El modo simulado no necesita clave ni endpoint. En modo real ambos datos
    deben proceder de la configuración y del archivo `.env`.

    Args:
        modelo: Modelo que utilizará el cliente.
        clave: Clave cargada desde `.env`.
        endpoint: Endpoint correspondiente al proveedor.
        transporte: Transporte opcional para pruebas.
        timeout_s: Tiempo máximo por solicitud.

    Returns:
        Cliente simulado o real.

    Raises:
        NotImplementedError: Si se solicita el modo real sin configuración.
    """
    if es_modo_simulado():
        return FakeLLMClient(modelo=modelo)

    if not clave or not endpoint:
        raise NotImplementedError(
            "El cliente real necesita una clave cargada desde .env y el endpoint "
            "del proveedor."
        )

    return ClienteLLMReal(
        modelo=modelo,
        clave=clave,
        endpoint=endpoint,
        transporte=transporte,
        timeout_s=timeout_s,
    )


def _segundos_retry_after(error: HTTPError) -> float | None:
    """Segundos de la cabecera `Retry-After` (solo el formato numérico), o None."""
    valor = error.headers.get("Retry-After") if error.headers else None
    try:
        return float(valor) if valor is not None else None
    except ValueError:
        return None


def _cuerpo_error(error: HTTPError) -> str:
    """Cuerpo completo del error en una sola línea (p. ej. «modelo no encontrado»)."""
    try:
        cuerpo = error.read().decode("utf-8", errors="replace").strip()
    except (OSError, AttributeError):
        return ""
    return " ".join(cuerpo.split())


def error_http(
    codigo: int, cuerpo: str = "", espera_s: float | None = None
) -> ErrorLLM:
    """Error que corresponde a una respuesta HTTP fallida del proveedor.

    `cuerpo` se mira completo (el `limit: 0` de Gemini suele venir después de los
    primeros 300 caracteres) y se guarda recortado en `detalle`.
    """
    detalle = cuerpo[:LARGO_DETALLE_ERROR]
    sufijo = f" Detalle: {detalle}" if detalle else ""
    prefijo = f"El proveedor LLM respondió con HTTP {codigo}"
    if codigo == 429 and _LIMITE_CERO.search(cuerpo):
        return SinCupoGratuito(
            f"{prefijo} (el modelo no tiene cupo en la capa gratuita: limit 0).{sufijo}",
            codigo=codigo,
            detalle=detalle,
        )
    if codigo == 429:
        return CupoAgotado(
            f"{prefijo} (límite de uso de la cuenta alcanzado).{sufijo}",
            espera_s=espera_s,
            codigo=codigo,
            detalle=detalle,
        )
    if codigo == 503:
        return ProveedorSaturado(
            f"{prefijo} (modelo saturado en el proveedor).{sufijo}",
            espera_s=espera_s,
            codigo=codigo,
            detalle=detalle,
        )
    if codigo == 402:
        return SinCredito(
            f"{prefijo} (la cuenta no tiene crédito para este modelo).{sufijo}",
            codigo=codigo,
            detalle=detalle,
        )
    return ErrorLLM(f"{prefijo}.{sufijo}", codigo=codigo, detalle=detalle)

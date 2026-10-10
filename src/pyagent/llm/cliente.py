"""Clientes LLM real y simulado utilizados por los agentes de QAgent."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pyagent.llm.fake import FakeLLMClient
from pyagent.llm.modelos import ClienteLLM, RespuestaLLM


class ErrorLLM(RuntimeError):
    """Error controlado durante una llamada a un proveedor LLM."""


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
        datos: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        """Realiza una solicitud POST al proveedor LLM.

        Args:
            url: Endpoint del proveedor.
            cabeceras: Cabeceras HTTP, incluida la autorización.
            datos: Cuerpo JSON de la solicitud.
            timeout_s: Tiempo máximo de espera en segundos.

        Returns:
            Respuesta JSON convertida en un diccionario.

        Raises:
            ErrorLLM: Si la solicitud o la respuesta no son válidas.
        """
        cuerpo = json.dumps(datos).encode("utf-8")
        solicitud = Request(
            url=url,
            data=cuerpo,
            headers=cabeceras,
            method="POST",
        )

        try:
            with urlopen(solicitud, timeout=timeout_s) as respuesta:
                contenido = respuesta.read().decode("utf-8")
        except HTTPError as error:
            raise ErrorLLM(
                f"El proveedor LLM respondió con HTTP {error.code}."
            ) from error
        except URLError as error:
            raise ErrorLLM(
                f"No se pudo conectar con el proveedor LLM: {error.reason}"
            ) from error
        except TimeoutError as error:
            raise ErrorLLM(
                f"El proveedor LLM no respondió en {timeout_s:g} segundos."
            ) from error
        except OSError as error:
            raise ErrorLLM(
                f"Error de red al contactar al proveedor LLM: {error}"
            ) from error

        try:
            datos_respuesta = json.loads(contenido)
        except json.JSONDecodeError as error:
            raise ErrorLLM("El proveedor LLM devolvió JSON inválido.") from error

        if not isinstance(datos_respuesta, dict):
            raise ErrorLLM("El proveedor LLM no devolvió un objeto JSON.")

        return datos_respuesta


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
    ) -> None:
        """Inicializa el cliente real.

        Args:
            modelo: Identificador del modelo configurado.
            clave: Clave del proveedor cargada desde `.env`.
            endpoint: URL del endpoint de chat del proveedor.
            transporte: Transporte reemplazable durante las pruebas.
            timeout_s: Tiempo máximo de espera por solicitud.
        """
        if not modelo.strip():
            raise ValueError("El modelo LLM no puede estar vacío.")
        if not clave.strip():
            raise ValueError("La clave del proveedor no puede estar vacía.")
        if not endpoint.strip():
            raise ValueError("El endpoint del proveedor no puede estar vacío.")
        if timeout_s <= 0:
            raise ValueError("El timeout debe ser mayor que cero.")

        self.modelo = modelo
        self._clave = clave
        self.endpoint = endpoint
        self.transporte = transporte or TransporteHTTP()
        self.timeout_s = timeout_s

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
        }
        datos = {
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

        try:
            respuesta = self.transporte.enviar(
                url=self.endpoint,
                cabeceras=cabeceras,
                datos=datos,
                timeout_s=self.timeout_s,
            )
            return self._convertir_respuesta(respuesta)
        except Exception as error:
            mensaje = str(error).replace(self._clave, "***")
            if isinstance(error, ErrorLLM):
                raise ErrorLLM(mensaje) from error
            raise ErrorLLM(f"Error al llamar al proveedor LLM: {mensaje}") from error

    def _convertir_respuesta(self, datos: dict[str, Any]) -> RespuestaLLM:
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

        tokens_entrada = self._entero_no_negativo(uso.get("prompt_tokens", 0))
        tokens_salida = self._entero_no_negativo(uso.get("completion_tokens", 0))

        modelo_respuesta = datos.get("model", self.modelo)
        if not isinstance(modelo_respuesta, str) or not modelo_respuesta:
            modelo_respuesta = self.modelo

        return RespuestaLLM(
            contenido=contenido,
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
            costo_usd=0.0,
            modelo=modelo_respuesta,
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


def es_modo_simulado() -> bool:
    """Verifica si la simulación está activa mediante PYAGENT_FAKE_LLM=1."""
    return os.getenv("PYAGENT_FAKE_LLM", "0").strip() == "1"


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

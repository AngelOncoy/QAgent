"""Crea el cliente LLM de cada agente a partir de `config.toml` y `.env` (HU-11).

La URL y la cabecera de la clave de cada proveedor salen del catálogo
(`llm/proveedores.toml`, HU-30) y el cliente lo arma el `ClienteProveedor` de ese
proveedor (`llm/proveedores.py`). Un agente puede fijar su propia URL con
`endpoint = "..."` en `[agentes.<agente>]`.
"""

from __future__ import annotations

from typing import Protocol

from qagent.llm.cliente import TransporteLLM
from qagent.llm.fake import FakeLLMClient
from qagent.llm.modelos import ClienteLLM
from qagent.llm.precios import PrecioAgente
from qagent.llm.proveedores import catalogo, cliente_de

#: URL de chat completions por proveedor (se puede reemplazar con `endpoint`).
ENDPOINT_POR_PROVEEDOR = {pid: p.endpoint for pid, p in catalogo().items()}

#: Proveedores que leen la clave de una cabecera propia además de `Authorization`.
CABECERA_CLAVE_POR_PROVEEDOR = {
    pid: p.cabecera_clave for pid, p in catalogo().items() if p.cabecera_clave
}


class FuenteClaves(Protocol):
    """Lo único que la fábrica necesita de `qagent.config.Claves`."""

    def obtener(self, nombre: str) -> str | None:
        """Valor de la variable de `.env`, o None si no está."""
        ...


class ConfiguracionLLMIncompleta(ValueError):
    """Falta la clave o la URL para crear el cliente real de un agente."""


def crear_cliente(
    precio: PrecioAgente,
    claves: FuenteClaves | None,
    *,
    simulado: bool,
    transporte: TransporteLLM | None = None,
    timeout_s: float = 90.0,  # menor que el timeout por paso del orquestador (240 s)
) -> ClienteLLM:
    """Devuelve el cliente LLM del agente descrito por `precio`.

    Args:
        precio: entrada de `[agentes.<agente>]` (proveedor, modelo, endpoint, esfuerzo).
        claves: claves de `.env` (`cargar_configuracion().claves`); no se usan si
            `simulado` es True.
        simulado: True con `QAGENT_FAKE_LLM=1`: devuelve la IA simulada (0 tokens).
        transporte: transporte HTTP reemplazable en las pruebas.
        timeout_s: tiempo máximo por llamada.

    Raises:
        ConfiguracionLLMIncompleta: si falta la clave en `.env` o no hay URL para
            el proveedor.
    """
    if simulado:
        return FakeLLMClient(modelo=precio.modelo)

    # Import diferido: qagent.config importa qagent.llm al cargarse.
    from qagent.config.carga import variable_de_agente, variable_en_uso

    variable = (
        variable_en_uso(precio.agente, precio.proveedor, claves.obtener)
        if claves is not None
        else None
    )
    clave = claves.obtener(variable) if (claves is not None and variable) else None
    if not clave:
        propia = variable_de_agente(precio.agente, precio.proveedor)
        raise ConfiguracionLLMIncompleta(
            f"Falta la clave {propia or '(proveedor desconocido)'} en .env "
            f"para el {precio.agente}."
        )
    if precio.proveedor not in catalogo():
        raise ConfiguracionLLMIncompleta(
            f"No hay URL para el proveedor '{precio.proveedor}': agrégalo a "
            "src/qagent/llm/proveedores.toml."
        )
    return cliente_de(precio.proveedor, transporte).crear_cliente_llm(
        clave,
        precio.modelo,
        endpoint=precio.endpoint,
        timeout_s=timeout_s,
        esfuerzo=precio.esfuerzo,
    )

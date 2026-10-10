"""Modelos y precios por agente leídos de `config.toml` (EN-05).

Lector mínimo: solo la sección `[agentes.*]`. La carga completa de la configuración
(presupuesto, reintentos, verificación del entorno) corresponde a EN-06.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

RUTA_CONFIG = Path(__file__).resolve().parents[3] / "config.toml"
AGENTES = ("planner", "generator", "reviewer")
TOKENS_POR_MILLON = 1_000_000
DECIMALES_COSTO = 8


class ConfiguracionInvalida(ValueError):
    """Falta un agente o un precio en `config.toml`."""


@dataclass(frozen=True)
class PrecioAgente:
    """Modelo y precios (US$ por millón de tokens) de un agente."""

    agente: str
    proveedor: str
    modelo: str
    entrada_usd_m: float
    salida_usd_m: float
    #: URL de chat completions; si es None se usa la del proveedor (`llm.fabrica`).
    endpoint: str | None = None
    #: Esfuerzo de razonamiento (`reasoning_effort`); None = no se envía.
    esfuerzo: str | None = None

    def costo(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Costo en US$ de una llamada: tokens × precio / 1 000 000."""
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("Los tokens no pueden ser negativos")
        total = (
            prompt_tokens * self.entrada_usd_m + completion_tokens * self.salida_usd_m
        ) / TOKENS_POR_MILLON
        return round(total, DECIMALES_COSTO)


def cargar_precios(ruta: str | Path = RUTA_CONFIG) -> dict[str, PrecioAgente]:
    """Lee `[agentes.planner]`, `[agentes.generator]` y `[agentes.reviewer]`.

    Raises:
        FileNotFoundError: si no existe el archivo.
        ConfiguracionInvalida: si falta un agente o alguno de sus campos.
    """
    with open(ruta, "rb") as archivo:
        datos = tomllib.load(archivo)
    seccion = datos.get("agentes", {})
    precios: dict[str, PrecioAgente] = {}
    for agente in AGENTES:
        if agente not in seccion:
            raise ConfiguracionInvalida(f"Falta [agentes.{agente}] en {ruta}")
        precios[agente] = _leer_agente(agente, seccion[agente], ruta)
    return precios


def _leer_agente(agente: str, tabla: dict, ruta: str | Path) -> PrecioAgente:
    try:
        return PrecioAgente(
            agente=agente,
            proveedor=str(tabla["proveedor"]),
            modelo=str(tabla["modelo"]),
            entrada_usd_m=float(tabla["precio_entrada_usd_m"]),
            salida_usd_m=float(tabla["precio_salida_usd_m"]),
            endpoint=texto_opcional(tabla.get("endpoint")),
            esfuerzo=texto_opcional(tabla.get("esfuerzo")),
        )
    except KeyError as falta:
        raise ConfiguracionInvalida(
            f"Falta {falta.args[0]} en [agentes.{agente}] de {ruta}"
        ) from falta


def texto_opcional(valor: object) -> str | None:
    """Texto sin espacios de un campo opcional de config.toml; None si falta o está vacío."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    return valor.strip()

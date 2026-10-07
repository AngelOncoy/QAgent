"""Contabilidad de tokens y costo por llamada a la IA (EN-05, base de EN-11)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pyagent.llm.precios import PrecioAgente


def _ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class RegistroLlamada:
    """Detalle de una llamada individual a un modelo de IA.

    `tokens_entrada` y `tokens_salida` son `prompt_tokens` y `completion_tokens`
    del campo `usage` de la API; en log.json se escriben con esos nombres.
    """

    agente: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float
    es_simulado: bool
    funcion: str | None = None
    intento: int | None = None
    hora: str = field(default_factory=_ahora)

    def a_log(self) -> dict[str, Any]:
        """Entrada de la lista `llamadas` de log.json."""
        return {
            "agente": self.agente,
            "funcion": self.funcion,
            "intento": self.intento,
            "modelo": self.modelo,
            "prompt_tokens": self.tokens_entrada,
            "completion_tokens": self.tokens_salida,
            "costo_usd": self.costo_usd,
            "es_simulado": self.es_simulado,
            "hora": self.hora,
        }


class TokenTracker:
    """Acumula el consumo de tokens y su costo.

    Si recibe `precios` (de `cargar_precios()`), calcula el costo de cada llamada con
    el precio del agente en config.toml; si no, usa el `costo_usd` que se le pase.
    El orquestador fija con `fijar_contexto()` la función y el intento en curso, para
    que los agentes no necesiten conocerlos al registrar.
    """

    def __init__(self, precios: dict[str, PrecioAgente] | None = None) -> None:
        self.llamadas: list[RegistroLlamada] = []
        self.precios = precios or {}
        self._funcion: str | None = None
        self._intento: int | None = None

    def fijar_contexto(self, funcion: str | None, intento: int | None) -> None:
        """Indica qué función e intento se están procesando (lo usa el orquestador)."""
        self._funcion = funcion
        self._intento = intento

    def registrar(
        self,
        agente: str,
        modelo: str,
        tokens_entrada: int,
        tokens_salida: int,
        costo_usd: float = 0.0,
        es_simulado: bool = False,
        funcion: str | None = None,
        intento: int | None = None,
    ) -> RegistroLlamada:
        """Registra el consumo de una invocación y devuelve el registro creado."""
        precio = self.precios.get(agente)
        if precio is not None:
            costo_usd = precio.costo(tokens_entrada, tokens_salida)
        registro = RegistroLlamada(
            agente=agente,
            modelo=modelo,
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
            costo_usd=costo_usd,
            es_simulado=es_simulado,
            funcion=funcion if funcion is not None else self._funcion,
            intento=intento if intento is not None else self._intento,
        )
        self.llamadas.append(registro)
        return registro

    @property
    def total_tokens(self) -> int:
        """Suma de tokens de entrada y salida de todas las llamadas."""
        return sum(ll.tokens_entrada + ll.tokens_salida for ll in self.llamadas)

    @property
    def total_costo_usd(self) -> float:
        """Costo acumulado total en dólares."""
        return sum(ll.costo_usd for ll in self.llamadas)

    def totales_por_agente(self) -> dict[str, dict[str, Any]]:
        """Tokens, costo y número de llamadas de cada agente."""
        totales: dict[str, dict[str, Any]] = {}
        for ll in self.llamadas:
            fila = totales.setdefault(
                ll.agente,
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "costo_usd": 0.0,
                    "llamadas": 0,
                },
            )
            fila["prompt_tokens"] += ll.tokens_entrada
            fila["completion_tokens"] += ll.tokens_salida
            fila["costo_usd"] = round(fila["costo_usd"] + ll.costo_usd, 8)
            fila["llamadas"] += 1
        return totales

    def tokens_de_funcion(self, funcion: str) -> dict[str, dict[str, int]]:
        """Tokens por agente gastados en una función (el Planner trabaja por módulo)."""
        tokens: dict[str, dict[str, int]] = {}
        for ll in self.llamadas:
            if ll.funcion != funcion:
                continue
            fila = tokens.setdefault(
                ll.agente, {"prompt_tokens": 0, "completion_tokens": 0}
            )
            fila["prompt_tokens"] += ll.tokens_entrada
            fila["completion_tokens"] += ll.tokens_salida
        return tokens

    def guardar_log(self, ruta_archivo: Path | str) -> dict:
        """Guarda un resumen simple del consumo (formato de EN-11).

        El log.json completo de una corrida lo escribe `pyagent.storage.registro`.

        Returns:
            dict: Diccionario guardado en el archivo.
        """
        resumen = {
            "total_llamadas": len(self.llamadas),
            "total_tokens": self.total_tokens,
            "total_costo_usd": round(self.total_costo_usd, 6),
            "es_simulado": all(ll.es_simulado for ll in self.llamadas)
            if self.llamadas
            else True,
            "llamadas": [asdict(ll) for ll in self.llamadas],
        }

        path = Path(ruta_archivo)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(resumen, f, indent=2, ensure_ascii=False)

        return resumen

"""Módulo de contabilidad y registro de consumo de tokens y costos en log.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class RegistroLlamada:
    """Detalle de una llamada individual a un modelo de IA."""

    agente: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float
    es_simulado: bool


class TokenTracker:
    """Acumulador de consumo de tokens y exportador de log.json."""

    def __init__(self) -> None:
        self.llamadas: list[RegistroLlamada] = []

    def registrar(
        self,
        agente: str,
        modelo: str,
        tokens_entrada: int,
        tokens_salida: int,
        costo_usd: float = 0.0,
        es_simulado: bool = False,
    ) -> None:
        """Registra el consumo de una invocación."""
        self.llamadas.append(
            RegistroLlamada(
                agente=agente,
                modelo=modelo,
                tokens_entrada=tokens_entrada,
                tokens_salida=tokens_salida,
                costo_usd=costo_usd,
                es_simulado=es_simulado,
            )
        )

    @property
    def total_tokens(self) -> int:
        """Suma de tokens de entrada y salida de todas las llamadas."""
        return sum(ll.tokens_entrada + ll.tokens_salida for ll in self.llamadas)

    @property
    def total_costo_usd(self) -> float:
        """Costo acumulado total en dólares."""
        return sum(ll.costo_usd for ll in self.llamadas)

    def guardar_log(self, ruta_archivo: Path | str) -> dict:
        """Genera y guarda el archivo log.json con el resumen de la corrida.

        Returns:
            dict: Diccionario guardado en el archivo.
        """
        resumen = {
            "total_llamadas": len(self.llamadas),
            "total_tokens": self.total_tokens,
            "total_costo_usd": round(self.total_costo_usd, 6),
            "es_simulado": all(ll.es_simulado for ll in self.llamadas) if self.llamadas else True,
            "llamadas": [asdict(ll) for ll in self.llamadas],
        }

        path = Path(ruta_archivo)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(resumen, f, indent=2, ensure_ascii=False)

        return resumen
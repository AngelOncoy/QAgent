"""Ejecutor que repite salidas de pytest grabadas, sin Docker (EN-17).

Las grabaciones salen de `scripts/grabar_ejecuciones.py`: cada una está indexada por el
hash del test que la produjo. Como la IA simulada genera siempre el mismo test para un
mismo contrato, la corrida del banco se repite con resultados reales de pytest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qagent.sandbox import ResultadoSandbox

GRABACION = Path(__file__).parent / "grabaciones" / "bench_ejecuciones.json"


def clave(codigo: str) -> str:
    """Identificador de una grabación: el hash del código del test."""
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()


class EjecutorGrabado:
    """Cumple el contrato de `Ejecutor` devolviendo lo grabado para el test recibido."""

    def __init__(self, ruta: Path = GRABACION) -> None:
        self.grabaciones: dict[str, dict] = json.loads(ruta.read_text(encoding="utf-8"))
        self.usadas: set[str] = set()

    def __call__(
        self, imagen: str, ruta_proyecto: Path, ruta_tests: Path, modulo_cov: str
    ) -> ResultadoSandbox:
        codigo = (Path(ruta_tests) / "test_generado.py").read_text(encoding="utf-8")
        k = clave(codigo)
        if k not in self.grabaciones:
            raise AssertionError(
                "No hay grabación para este test; vuelve a grabar con "
                "`python scripts/grabar_ejecuciones.py`.\n" + codigo
            )
        self.usadas.add(k)
        return ResultadoSandbox(**self.grabaciones[k])

    @property
    def sin_usar(self) -> set[str]:
        return set(self.grabaciones) - self.usadas

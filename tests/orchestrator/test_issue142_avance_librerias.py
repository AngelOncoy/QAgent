"""Issue 142: los avisos de las librerías del sistema siempre llegan al Monitor."""

from __future__ import annotations

from qagent.orchestrator.corrida import avance_limitado
from qagent.sandbox.librerias import AVISO_COMPROBANDO, AVISO_INSTALANDO, AVISO_LISTAS


def test_los_avisos_de_librerias_no_se_descartan_aunque_lleguen_seguidos() -> None:
    avisos: list[str] = []
    avanzar = avance_limitado(avisos.append, intervalo_s=60, reloj=lambda: 0.0)
    instalando = f"{AVISO_INSTALANDO}: libgl1"

    avanzar(AVISO_COMPROBANDO)
    avanzar("Descargando paquete (1 MB)")  # paso de pip: se limita
    avanzar(instalando)
    avanzar(f"{AVISO_INSTALANDO}: libglib2.0-0t64")
    avanzar(AVISO_LISTAS)

    assert avisos == [
        AVISO_COMPROBANDO,
        instalando,
        f"{AVISO_INSTALANDO}: libglib2.0-0t64",
        AVISO_LISTAS,
    ]

"""TA-06: todo lo que la app necesita para funcionar instalada viaja dentro del paquete.

Si un recurso se busca en la raíz del repositorio, `pip install qagent` o el ejecutable
abren sin interfaz, sin contratos o sin configuración.
"""

from __future__ import annotations

import re
from pathlib import Path

import qagent
from qagent import contracts
from qagent.config import carga
from qagent.llm import fake, precios

PAQUETE = Path(qagent.__file__).resolve().parent


def _dentro_del_paquete(ruta: Path) -> bool:
    return PAQUETE in ruta.resolve().parents


def test_la_interfaz_esta_en_el_paquete():
    from qagent.app.desktop import FRONTEND_DIR

    assert _dentro_del_paquete(FRONTEND_DIR / "index.html")
    assert (FRONTEND_DIR / "index.html").is_file()


def test_los_contratos_estan_en_el_paquete():
    assert _dentro_del_paquete(contracts.DIR_CONTRATOS / "x")
    for nombre in (
        contracts.PLANNER,
        contracts.GENERATED_TEST,
        contracts.REVIEW_RESULT,
    ):
        assert (contracts.DIR_CONTRATOS / f"{nombre}.schema.json").is_file()


def test_la_configuracion_del_equipo_esta_en_el_paquete():
    assert carga.RUTA_CONFIG == precios.RUTA_CONFIG
    assert _dentro_del_paquete(carga.RUTA_CONFIG)
    assert carga.RUTA_CONFIG.is_file()


def test_las_respuestas_de_la_ia_simulada_estan_en_el_paquete():
    assert _dentro_del_paquete(fake.RUTA_GRABACIONES)
    assert fake.RUTA_GRABACIONES.is_file()


def test_ningun_modulo_busca_recursos_en_la_raiz_del_repo():
    """`parents[2]` o más desde un módulo de qagent sale del paquete (src/ o la raíz)."""
    permitidos = {
        "config/carga.py"
    }  # RAIZ: .env y config.local.toml (pasan a ~/.qagent/)
    sospechosos = sorted(
        p.relative_to(PAQUETE).as_posix()
        for p in PAQUETE.rglob("*.py")
        if re.search(r"parents\[[2-9]\]", p.read_text(encoding="utf-8"))
        and p.relative_to(PAQUETE).as_posix() not in permitidos
    )
    assert sospechosos == []

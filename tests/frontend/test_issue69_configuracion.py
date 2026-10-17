"""Issue #69: la configuración de pruebas se elige como opciones, no como planes."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def cuerpo_de(js: str, inicio: str, fin: str) -> str:
    return js[js.index(inicio) : js.index(fin, js.index(inicio))]


def test_la_eleccion_por_defecto_equivale_al_perfil_por_defecto() -> None:
    estado = leer("js/estado.js")

    assert "let profile = 'deep';" in estado
    assert (
        "let eleccionPruebas = {modo:'nuevas', tipo:'std', profundizar:true};" in estado
    )


def test_la_eleccion_se_traduce_a_los_cuatro_perfiles_del_backend() -> None:
    js = leer("componentes/config-pruebas/config-pruebas.js")
    cuerpo = cuerpo_de(js, "function perfilDeEleccion", "function elegirPruebas")

    assert "if (modo === 'repetir') return 'reg';" in cuerpo
    assert "if (tipo === 'humo') return 'humo';" in cuerpo
    assert "return profundizar ? 'deep' : 'std';" in cuerpo


def test_elegir_actualiza_el_perfil_y_desbloquea_el_monitor() -> None:
    js = leer("componentes/config-pruebas/config-pruebas.js")
    elegir = cuerpo_de(js, "function elegirPruebas", "}\n")
    elegir_perfil = cuerpo_de(js, "function pickProfile", "}\n")

    assert "eleccionPruebas = {...eleccionPruebas, ...cambio};" in elegir
    assert "pickProfile(perfilDeEleccion(eleccionPruebas));" in elegir
    assert "desbloquearVista('monitor')" in elegir_perfil

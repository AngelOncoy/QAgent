"""#133: Preparar vuelve a ofrecer la estrategia Humo y la envía a start_run como `humo`."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def cuerpo_de(js: str, inicio: str, fin: str) -> str:
    return js[js.index(inicio) : js.index(fin, js.index(inicio))]


def config() -> str:
    return leer("componentes/config-pruebas/config-pruebas.js")


def test_preparar_ofrece_la_revision_rapida_humo() -> None:
    modos = cuerpo_de(config(), "const MODOS_PREPARAR", "];")

    assert "{k:'humo'" in modos
    assert "Revisión rápida (humo)" in modos
    assert "Un caso normal por función o endpoint" in modos


def test_el_modo_humo_se_traduce_al_perfil_humo() -> None:
    cuerpo = cuerpo_de(config(), "function perfilDeEleccion", "function estFor")

    assert "if (modo === 'humo') return 'humo';" in cuerpo


def test_los_demas_modos_siguen_dando_sus_perfiles() -> None:
    cuerpo = cuerpo_de(config(), "function perfilDeEleccion", "function estFor")

    assert (
        "if (modo === 'repetir') return profundizarRepetir && repetibles > 0 ? 'reg_deep' : 'reg';"
        in cuerpo
    )
    assert "if (modo === 'fondo') return prioritarias > 0 ? 'deep' : 'std';" in cuerpo
    assert "  return 'std';\n}" in cuerpo
    # «Generar pruebas nuevas» no se volvió Humo: Humo solo sale si se elige.
    assert cuerpo.count("return 'humo'") == 1


def test_la_eleccion_por_defecto_sigue_siendo_generar_pruebas_nuevas() -> None:
    assert "let eleccionPruebas = {modo:'nuevas'," in leer("js/estado.js")


def test_la_estimacion_usa_los_valores_del_perfil_humo() -> None:
    estado = leer("js/estado.js")
    calc = cuerpo_de(config(), "function calc()", "\n}\n")

    assert "{k:'humo', n:'Humo'" in estado
    assert "const e = estFor(profile==='reg_deep' ? 'reg' : profile)" in calc
    assert "profile==='humo'" in cuerpo_de(
        config(), "function renderDetallesCorrida", "\n}\n"
    )


def test_con_humo_criticas_y_fortaleza_no_aplican() -> None:
    js = config()
    criticas = cuerpo_de(js, "function renderCriticas", "\n}\n")

    assert "const humo = eleccionPruebas.modo === 'humo';" in criticas
    assert "$('prepFortaleza').classList.toggle('prep-no-aplica', humo);" in criticas
    assert "checked disabled" in criticas
    assert "No aplica en la revisión rápida" in criticas
    assert "No se mide en la revisión rápida" in criticas
    assert 'id="prepFortaleza"' in js
    assert ".prep-no-aplica{" in leer("componentes/config-pruebas/config-pruebas.css")


def test_el_aviso_de_inicio_no_muestra_el_identificador_del_perfil() -> None:
    desktop = (RAIZ / "src" / "qagent" / "app" / "desktop.py").read_text(
        encoding="utf-8"
    )

    assert "Corrida iniciada: {nombre_perfil(profile)}" in desktop
    assert "Corrida iniciada en perfil '{profile}'" not in desktop

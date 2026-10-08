"""Estructura del frontend: componentes, archivos referenciados y tokens (sin navegador ni Node)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")

ESTILOS = re.findall(r'<link rel="stylesheet" href="([^"]+)"', INDEX)
SCRIPTS = re.findall(r'<script src="([^"]+)"', INDEX)
MARCADORES = re.findall(r'data-componente="([^"]+)"', INDEX)


def _registros() -> dict[str, Path]:
    """Ruta de componente -> archivo .js que la registra con `registrarComponente(...)`."""
    encontrados: dict[str, Path] = {}
    for js in (FRONTEND / "componentes").rglob("*.js"):
        for ruta in re.findall(
            r"registrarComponente\('([^']+)'", js.read_text(encoding="utf-8")
        ):
            encontrados[ruta] = js
    return encontrados


def test_index_referencia_solo_archivos_que_existen() -> None:
    faltantes = [r for r in ESTILOS + SCRIPTS if not (FRONTEND / r).is_file()]
    assert faltantes == []


def test_no_hay_css_ni_js_huerfanos() -> None:
    """Todo .css/.js de frontend/ está enlazado en index.html (nada olvidado al mover)."""
    referenciados = set(ESTILOS + SCRIPTS)
    existentes = {
        p.relative_to(FRONTEND).as_posix()
        for carpeta in ("css", "js", "componentes")
        for p in (FRONTEND / carpeta).rglob("*")
        if p.suffix in {".css", ".js"}
    }
    assert sorted(existentes - referenciados) == []


def test_cada_marcador_tiene_un_componente_registrado() -> None:
    registros = _registros()
    assert sorted(set(MARCADORES) - set(registros)) == []


def test_cada_componente_registrado_tiene_su_marcador() -> None:
    assert sorted(set(_registros()) - set(MARCADORES)) == []


def test_los_marcadores_no_se_repiten() -> None:
    assert len(MARCADORES) == len(set(MARCADORES))


@pytest.mark.parametrize("ruta", sorted(_registros()))
def test_el_componente_vive_en_su_carpeta_y_se_carga(ruta: str) -> None:
    """`carpeta/nombre` se registra en componentes/carpeta/nombre.js y ese script está en index.html."""
    esperado = FRONTEND / "componentes" / f"{ruta}.js"
    assert _registros()[ruta] == esperado
    assert f"componentes/{ruta}.js" in SCRIPTS


def test_cargador_y_utilidades_se_cargan_antes_que_los_componentes() -> None:
    primer_componente = min(
        i for i, s in enumerate(SCRIPTS) if s.startswith("componentes/")
    )
    for base in (
        "js/utils.js",
        "js/cargador.js",
        "js/iconos.js",
        "js/datos-corrida.js",
    ):
        assert SCRIPTS.index(base) < primer_componente


def test_main_arranca_al_final() -> None:
    assert SCRIPTS[-1] == "js/main.js"


def test_el_logo_de_los_tokens_existe() -> None:
    """--logo-icono es relativo a css/ (donde está tokens.css): la imagen debe existir."""
    tokens = (FRONTEND / "css" / "tokens.css").read_text(encoding="utf-8")
    rutas = re.findall(r"--logo-[a-z]+:url\('([^']+)'\)", tokens)
    assert rutas
    assert [r for r in rutas if not (FRONTEND / "css" / r).resolve().is_file()] == []


def test_no_quedan_colores_de_marca_sueltos_en_el_logo_de_la_barra_lateral() -> None:
    """La barra lateral usa el logo vectorizado vía token, no el ícono antiguo en línea."""
    html = (FRONTEND / "componentes" / "sidebar" / "sidebar.js").read_text(
        encoding="utf-8"
    )
    assert 'class="logo"' in html
    assert "<svg" not in html.split('class="logo"')[1].split("</div>")[0]

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


# ---------- colores: todo vive en css/tokens.css ----------

_COLOR = re.compile(
    r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)|hsla?\([^)]*\)"
)
_BASE64 = re.compile(r"base64,[A-Za-z0-9+/=]+")


def _archivos_de_interfaz() -> list[Path]:
    """CSS, JS y HTML del frontend, salvo tokens.css y los recursos (assets/)."""
    return [
        p
        for p in FRONTEND.rglob("*")
        if p.suffix in {".css", ".js", ".html"}
        and p.name != "tokens.css"
        and "assets" not in p.relative_to(FRONTEND).parts
    ]


def test_no_hay_colores_sueltos_fuera_de_tokens() -> None:
    """Colores hexadecimales, rgb() o hsl() solo en css/tokens.css; los demás usan var(--token)."""
    sueltos = []
    for archivo in _archivos_de_interfaz():
        texto = _BASE64.sub("", archivo.read_text(encoding="utf-8"))
        for color in _COLOR.findall(texto):
            sueltos.append(f"{archivo.relative_to(FRONTEND).as_posix()}: {color}")
    assert sueltos == []


def test_todo_token_usado_esta_definido_en_tokens_css() -> None:
    """Cada var(--x) sin valor alternativo apunta a una variable declarada en tokens.css."""
    tokens = (FRONTEND / "css" / "tokens.css").read_text(encoding="utf-8")
    definidos = set(re.findall(r"(--[a-z0-9-]+)\s*:", tokens))
    usados: dict[str, str] = {}
    for archivo in _archivos_de_interfaz() + [FRONTEND / "css" / "tokens.css"]:
        texto = _BASE64.sub("", archivo.read_text(encoding="utf-8"))
        for token in re.findall(r"var\((--[a-z0-9-]+)\s*\)", texto):
            usados.setdefault(token, archivo.relative_to(FRONTEND).as_posix())
    indefinidos = {t: a for t, a in usados.items() if t not in definidos}
    assert indefinidos == {}


def test_los_estados_de_la_corrida_definen_su_halo_como_token() -> None:
    """No se concatenan sufijos de opacidad a un color: cada estado trae su halo (--*-a20)."""
    datos = (FRONTEND / "js" / "datos-corrida.js").read_text(encoding="utf-8")
    estados = re.findall(
        r"^\s{2}(\w+):\{c:'var\(--[a-z0-9-]+\)', halo:'var\(--[a-z0-9-]+-a20\)'",
        datos,
        re.MULTILINE,
    )
    assert sorted(estados) == [
        "low_mutation",
        "passed",
        "rejected_laundering",
        "rejected_oracle",
        "stuck",
    ]


# ---------- fuentes: locales, sin depender de internet ----------


def test_la_interfaz_no_depende_de_recursos_externos() -> None:
    """index.html y los CSS no cargan nada de internet (fuentes, estilos ni scripts)."""
    externos = [r for r in ESTILOS + SCRIPTS if r.startswith(("http:", "https:", "//"))]
    css = [p.read_text(encoding="utf-8") for p in (FRONTEND / "css").glob("*.css")]
    externos += [
        u for texto in css for u in re.findall(r"url\(['\"]?(https?:[^)'\"]+)", texto)
    ]
    assert externos == []


def test_las_fuentes_declaradas_existen_y_tienen_licencia() -> None:
    fuentes_css = (FRONTEND / "css" / "fuentes.css").read_text(encoding="utf-8")
    rutas = re.findall(r"url\('([^']+)'\)", fuentes_css)
    assert rutas
    assert [r for r in rutas if not (FRONTEND / "css" / r).resolve().is_file()] == []
    licencias = {p.name for p in (FRONTEND / "assets" / "fuentes").glob("LICENSE-*")}
    assert licencias == {"LICENSE-Inter-OFL.txt", "LICENSE-JetBrainsMono-OFL.txt"}


def test_las_familias_de_los_tokens_tienen_su_font_face() -> None:
    """La primera familia de --fuente-ui y --fuente-mono está declarada en fuentes.css."""
    tokens = (FRONTEND / "css" / "tokens.css").read_text(encoding="utf-8")
    fuentes_css = (FRONTEND / "css" / "fuentes.css").read_text(encoding="utf-8")
    declaradas = set(re.findall(r"font-family:'([^']+)'", fuentes_css))
    principales = re.findall(r"--fuente-(?:ui|mono):'([^']+)'", tokens)
    assert len(principales) == 2
    assert set(principales) <= declaradas


def test_fuentes_css_se_carga_antes_que_los_tokens() -> None:
    assert ESTILOS.index("css/fuentes.css") < ESTILOS.index("css/tokens.css")


# ---------- datos de ejemplo: solo en la demostración y en la corrida simulada ----------

# Pantallas del flujo real (antes de la corrida): no deben llevar datos de ejemplo escritos a mano.
_FLUJO_REAL = [
    "vista-previa/vista-previa",
    "config-pruebas/config-pruebas",
    "barra-corrida/barra-corrida",
]
_EJEMPLOS = [
    "ecommerce-core",
    "retail-ai",
    "a8f91",
    "8841-B",
    "8791-A",
    "En el demo",
    "Python 3.11 detectado",
    "requirements.txt ✓",
    "cart.py, discounts.py",
]


@pytest.mark.parametrize("componente", _FLUJO_REAL)
def test_el_flujo_real_no_lleva_datos_de_ejemplo(componente: str) -> None:
    """El nombre del proyecto, el commit, las corridas previas, etc. salen del backend, no del HTML."""
    texto = (FRONTEND / "componentes" / f"{componente}.js").read_text(encoding="utf-8")
    assert [e for e in _EJEMPLOS if e in texto] == []


def test_la_barra_de_demo_esta_oculta_por_defecto() -> None:
    """«Reiniciar demo» solo se muestra sin pywebview (inicio.js la revela en modo demostración)."""
    assert re.search(r'<div class="demo hide" id="barraDemo">', INDEX)
    inicio = (FRONTEND / "componentes" / "inicio" / "inicio.js").read_text(
        encoding="utf-8"
    )
    assert "barraDemo" in inicio


def test_un_analisis_fallido_en_la_app_real_no_muestra_modulos_de_ejemplo() -> None:
    """En la rama de pywebview, si el análisis falla se vacía la vista previa (no aplicarResumenDemo)."""
    js = (FRONTEND / "componentes" / "vista-previa" / "vista-previa.js").read_text(
        encoding="utf-8"
    )
    cuerpo = js[
        js.index("async function loadProject") : js.index("function vaciarVistaPrevia")
    ]
    rama_real, _rama_demo = cuerpo.split("} else {\n    aplicarResumenDemo();", 1)
    assert "aplicarResumenDemo" not in rama_real
    assert "vaciarVistaPrevia()" in rama_real


# ---------- toda la interfaz vive en frontend/ ----------


def test_no_hay_archivos_de_interfaz_fuera_de_frontend() -> None:
    """HTML, CSS y JS solo existen en frontend/: el backend (src/) no guarda pantallas ni demos."""
    src = FRONTEND.parent / "src"
    sueltos = sorted(
        p.relative_to(src.parent).as_posix()
        for p in src.rglob("*")
        if p.suffix in {".html", ".htm", ".css", ".js"}
    )
    assert sueltos == []


# ---------- indicador del sandbox con la IA simulada ----------


def test_el_indicador_del_sandbox_distingue_la_ia_simulada() -> None:
    """Con IA simulada y Docker sin responder, el indicador es neutro (punto gris), no un error."""
    js = (FRONTEND / "componentes" / "sidebar" / "sidebar.js").read_text(
        encoding="utf-8"
    )
    assert "opcional:" in js and "r.simulado" in js
    estilos = (FRONTEND / "css" / "componentes.css").read_text(encoding="utf-8")
    assert ".dot.grey" in estilos and ".neutro" in estilos


# ---------- bitácora de la corrida en la consola de Python ----------


def test_cada_paso_del_monitor_se_envia_a_la_consola_de_python() -> None:
    """El monitor, el fin de la corrida y la pausa llaman a registrar_evento del puente."""
    monitor = (FRONTEND / "componentes" / "monitor" / "monitor.js").read_text(
        encoding="utf-8"
    )
    barra = (FRONTEND / "componentes" / "barra-corrida" / "barra-corrida.js").read_text(
        encoding="utf-8"
    )
    assert "api.registrar_evento" in monitor
    # un envío por cada paso, por el fin, por «completar» y por la pausa
    assert monitor.count("registrarEnPython(") >= 4
    assert "registrarEnPython(" in barra


# ---------- corrida real: filas que llegan de Python ----------


def test_el_monitor_recibe_la_corrida_real_y_escapa_sus_textos() -> None:
    """Las filas de la corrida real traen nombres del proyecto y texto de la IA: se escapan."""
    puente = (FRONTEND / "js" / "puente-python.js").read_text(encoding="utf-8")
    monitor = (FRONTEND / "componentes" / "monitor" / "monitor.js").read_text(
        encoding="utf-8"
    )
    assert "corrida_evento" in puente and "corrida_fin" in puente
    cuerpo = monitor[
        monitor.index("function monitorEventoReal") : monitor.index(
            "function monitorFinReal"
        )
    ]
    for campo in ("escHtml(lugar)", "escHtml(d.t", "escHtml(d.guard[0])"):
        assert campo in cuerpo
    assert "r.modo === 'real'" in monitor

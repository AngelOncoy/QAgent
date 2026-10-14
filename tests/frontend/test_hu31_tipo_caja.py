"""HU-31: cada perfil muestra su descripción y si es prueba de caja negra o blanca."""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"

ESPERADO = {
    "humo": "negra",
    "std": "negra",
    "deep": "blanca",
    "reg": "negra",
}


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def perfiles() -> list[str]:
    js = leer("js/estado.js")
    bloque = js[
        js.index("const PROFILES = [") : js.index("];", js.index("const PROFILES = ["))
    ]
    return re.findall(r"\{k:'[^']+'.*?\},?\n", bloque)


def test_los_cuatro_perfiles_declaran_descripcion_y_tipo_de_caja() -> None:
    filas = perfiles()
    assert len(filas) == 4
    for fila in filas:
        clave = re.search(r"k:'([^']+)'", fila).group(1)
        assert f"tipo_caja:'{ESPERADO[clave]}'" in fila
        descripcion = re.search(r"descripcion:'([^']+)'", fila)
        assert descripcion and len(descripcion.group(1)) > 40


def test_los_cuadros_se_generan_desde_los_datos() -> None:
    js = leer("componentes/config-pruebas/config-pruebas.js")
    assert "${p.descripcion}" in js
    assert "caja-${p.tipo_caja}" in js
    assert "TIPO_CAJA[p.tipo_caja]" in js


def test_la_leyenda_explica_ambos_terminos() -> None:
    js = leer("componentes/config-pruebas/config-pruebas.js")
    assert 'class="leyenda-caja"' in js
    assert "</span>: evalúa entradas y salidas sin mirar el código." in js
    assert "</span>: evalúa el código por dentro (caminos, ramas, cobertura)." in js


def test_cada_tipo_de_caja_tiene_su_color() -> None:
    css = leer("componentes/config-pruebas/config-pruebas.css")
    assert "var(--caja-negra-s)" in css and "var(--caja-blanca-s)" in css
    tokens = leer("css/tokens.css")
    assert "--caja-negra-s:" in tokens and "--caja-blanca-s:" in tokens


def test_configuracion_de_pruebas_no_muestra_costo_ni_iso() -> None:
    for ruta in (
        "componentes/config-pruebas/config-pruebas.js",
        "componentes/config-pruebas/config-pruebas.css",
    ):
        texto = leer(ruta)
        for prohibido in ("Costo", "costo", "S/ ", "US$", "TOPE_PEN", "FX", "ISO"):
            assert prohibido not in texto, f"{ruta} contiene {prohibido!r}"


def test_cada_perfil_muestra_su_duracion_aproximada() -> None:
    duraciones = {"humo": "rápida", "std": "media", "deep": "larga", "reg": "media"}
    for fila in perfiles():
        clave = re.search(r"k:'([^']+)'", fila).group(1)
        assert f"duracion:'{duraciones[clave]}'" in fila
    js = leer("componentes/config-pruebas/config-pruebas.js")
    assert "${p.duracion}" in js

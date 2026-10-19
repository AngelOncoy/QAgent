"""HU-31, ajustada por #69: cada perfil tiene descripción y solo Profundizar se etiqueta como caja blanca.

Antes de #69 los cuatro perfiles mostraban su tipo de caja y una leyenda la explicaba.
Con #69 la etiqueta solo aparece en Profundizar (la única capa de caja blanca) y la
leyenda se quita: Estándar es de caja negra en funciones pero gris en endpoints, así
que etiquetarlo como «caja negra» era inexacto.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def perfiles() -> list[str]:
    js = leer("js/estado.js")
    bloque = js[
        js.index("const PROFILES = [") : js.index("];", js.index("const PROFILES = ["))
    ]
    return re.findall(r"\{k:'[^']+'.*?\},?\n", bloque)


def test_los_cuatro_perfiles_declaran_descripcion() -> None:
    filas = perfiles()
    assert len(filas) == 4
    for fila in filas:
        descripcion = re.search(r"descripcion:'([^']+)'", fila)
        assert descripcion and len(descripcion.group(1)) > 40


def test_solo_profundizar_declara_tipo_de_caja_y_es_blanca() -> None:
    for fila in perfiles():
        clave = re.search(r"k:'([^']+)'", fila).group(1)
        if clave == "deep":
            assert "tipo_caja:'blanca'" in fila
        else:
            assert "tipo_caja:" not in fila


def test_las_opciones_se_generan_desde_los_datos() -> None:
    js = leer("componentes/config-pruebas/config-pruebas.js")
    assert "MODOS_PREPARAR.map" in js
    assert "${o.t}" in js


def test_no_queda_la_leyenda_ni_la_etiqueta_de_caja_negra() -> None:
    js = leer("componentes/config-pruebas/config-pruebas.js")
    css = leer("componentes/config-pruebas/config-pruebas.css")
    assert 'class="leyenda-caja"' not in js
    assert "Caja negra" not in js and "caja-negra" not in js
    assert ".leyenda-caja" not in css and ".caja-negra" not in css


def test_configuracion_de_pruebas_no_muestra_costo_ni_iso() -> None:
    for ruta in (
        "componentes/config-pruebas/config-pruebas.js",
        "componentes/config-pruebas/config-pruebas.css",
    ):
        texto = leer(ruta)
        for prohibido in ("Costo", "costo", "S/ ", "US$", "TOPE_PEN", "FX"):
            assert prohibido not in texto, f"{ruta} contiene {prohibido!r}"
        assert not re.search(r"\bISO\b", texto), f"{ruta} contiene 'ISO'"


def test_cada_perfil_muestra_su_duracion_aproximada() -> None:
    duraciones = {"humo": "rápida", "std": "media", "deep": "larga", "reg": "media"}
    for fila in perfiles():
        clave = re.search(r"k:'([^']+)'", fila).group(1)
        assert f"duracion:'{duraciones[clave]}'" in fila
    js = leer("componentes/config-pruebas/config-pruebas.js")
    assert "${p.duracion}" in js

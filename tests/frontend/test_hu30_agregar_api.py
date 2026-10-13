"""Interfaz de «Agregar API» por agente (HU-30): estructura del componente, sin navegador."""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
CONFIG_JS = FRONTEND / "componentes" / "configuracion" / "configuracion.js"
MODAL_JS = FRONTEND / "componentes" / "configuracion" / "modal-api.js"


def test_cada_agente_tiene_boton_agregar_o_editar():
    texto = CONFIG_JS.read_text(encoding="utf-8")
    assert "'Editar' : 'Agregar API'" in texto
    assert "Sin configurar" in texto


def test_el_modelo_es_una_lista_y_no_se_escribe_a_mano():
    texto = MODAL_JS.read_text(encoding="utf-8")
    assert '<select class="inp" id="apiProveedor"' in texto
    assert '<select class="inp" id="apiModelo"' in texto
    assert 'id="apiModelo" type="text"' not in texto


def test_la_key_se_escribe_oculta_y_se_puede_reutilizar():
    texto = MODAL_JS.read_text(encoding="utf-8")
    assert 'id="apiClave" type="password"' in texto
    assert 'id="apiReusar"' in texto


def test_el_catalogo_no_esta_en_la_interfaz():
    """La lista de proveedores y modelos sale de Python (proveedores.toml), no del JS."""
    texto = MODAL_JS.read_text(encoding="utf-8") + CONFIG_JS.read_text(encoding="utf-8")
    assert "listar_proveedores" in texto
    assert [
        m
        for m in ("claude-opus-5-5", "mimo-v2.6-pro", "whisper-large-v3")
        if m in texto
    ] == []


_TEXTO_DEL_BACKEND = re.compile(
    r"\$\{(?:r|p|m)\.(?:modelo|nombre|proveedor_nombre|modelo_nombre|variable|"
    r"clave_enmascarada|mensaje|detalle|tipo_nombre)\}"
)


def test_los_textos_del_backend_se_escapan():
    """Lo que llega de Python va a innerHTML solo con escHtml (textContent ya es seguro)."""
    sin_escapar = [
        f"{archivo.name}:{numero}"
        for archivo in (CONFIG_JS, MODAL_JS)
        for numero, linea in enumerate(
            archivo.read_text(encoding="utf-8").splitlines(), 1
        )
        if _TEXTO_DEL_BACKEND.search(linea) and "textContent" not in linea
    ]
    assert sin_escapar == []

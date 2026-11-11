"""#267 Capa 3: la sección «Espacio en disco» de Configuración y su confirmación (estructura, sin navegador)."""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def componente() -> str:
    return leer("componentes/configuracion/espacio-disco.js")


def modal() -> str:
    return leer("componentes/configuracion/modal-espacio.js")


def cuerpo_de(js: str, inicio: str, fin: str) -> str:
    return js[js.index(inicio) : js.index(fin, js.index(inicio))]


def test_la_tarjeta_esta_en_configuracion_y_se_pinta_al_entrar() -> None:
    config = leer("componentes/configuracion/configuracion.js")

    assert 'id="cfgEspacio"' in config
    assert "cargarEspacioDisco()" in cuerpo_de(config, "function renderConfig", "\n}\n")


def test_el_modal_y_el_script_estan_enlazados_en_index() -> None:
    index = leer("index.html")

    assert 'data-componente="configuracion/modal-espacio"' in index
    assert '<script src="componentes/configuracion/espacio-disco.js"></script>' in index
    assert '<script src="componentes/configuracion/modal-espacio.js"></script>' in index
    assert "registrarComponente('configuracion/modal-espacio'" in modal()


def test_el_componente_solo_llama_al_puente_de_python() -> None:
    js = componente()

    assert "window.pywebview.api.obtener_espacio_disco()" in js
    assert "window.pywebview.api.liberar_espacio(" in js
    # La pantalla no calcula ni borra nada por su cuenta.
    assert "fetch(" not in js


def test_la_tarjeta_muestra_base_derivadas_cache_y_espacio_libre() -> None:
    js = componente()

    for texto in (
        "Imágenes base",
        "Imágenes de tus proyectos",
        "Restos de construcciones cortadas",
        "Caché de compilación de Docker",
        "Total de QAgent",
        "libres en el disco de Docker",
        "Poco espacio libre",
        "Liberar espacio",
    ):
        assert texto in js
    for campo in ("u.bases", "u.derivadas", "u.restos", "u.cache", "u.libre_bytes"):
        assert campo in js


def test_explica_como_compactar_el_disco_de_docker() -> None:
    js = componente()

    assert "wsl --shutdown" in js
    assert "diskpart" in js
    for paso in ("attach vdisk readonly", "compact vdisk", "detach vdisk"):
        assert paso in js
    assert "docker_data.vhdx" in js
    assert "C: no recupera el espacio" in js


def test_la_confirmacion_lista_lo_que_se_borra_y_lo_que_se_conserva() -> None:
    js = componente()
    abrir = cuerpo_de(
        js, "async function abrirModalEspacio", "function cerrarModalEspacio"
    )

    assert "listaDeBorrado(u)" in abrir
    for texto in (
        "Las imágenes base del entorno aislado",
        "La imagen de una corrida en curso",
        "Todo lo que no sea de QAgent",
        "Tus proyectos, las pruebas guardadas y los resultados",
    ):
        assert texto in abrir
    lista = cuerpo_de(js, "function listaDeBorrado", "async function abrirModalEspacio")
    for texto in ("imágenes", "contenedores sobrantes", "capas"):
        assert texto in lista
    assert "Se borrará" in modal() and "Se conserva" in modal()
    assert 'id="espBorra"' in modal() and 'id="espConserva"' in modal()


def test_la_confirmacion_avisa_que_la_cache_es_de_todo_docker() -> None:
    js = componente()

    assert "<b>toda</b> la caché de compilación de Docker, no solo a la de QAgent" in js
    assert "también la de tus otros proyectos" in js
    # La caché es opcional y nunca viene marcada de antemano.
    assert '<input type="checkbox" id="espCache">' in modal()
    assert "$('espCache').checked = false;" in js
    assert "liberar_espacio($('espCache').checked)" in js


def test_el_borrado_pide_confirmacion_y_no_se_repite_ni_se_cierra_a_medias() -> None:
    js = componente()
    confirmar = cuerpo_de(js, "async function confirmarLiberarEspacio", "\n}\n")

    assert 'onclick="confirmarLiberarEspacio()"' in modal()
    assert "abrirModalEspacio()" in js  # el botón de la tarjeta abre el modal, no borra
    assert "if(liberandoEspacio" in confirmar
    assert "$('espConfirmar').disabled = true" in confirmar
    assert "if(liberandoEspacio) return;" in cuerpo_de(
        js, "function cerrarModalEspacio", "\n}\n"
    )


def test_los_textos_que_vienen_de_python_se_escapan() -> None:
    js = componente()

    assert "escHtml(u.mensaje" in js
    assert "escHtml(tamanoTexto(" in js
    assert "toast(escHtml(r.mensaje))" in js
    assert "toastError(escHtml(" in js


def test_sin_la_app_de_escritorio_no_ofrece_borrar() -> None:
    js = componente()

    assert "Disponible en la aplicación de escritorio" in js
    assert "if(!hayApiEspacio())" in js


def test_la_comprobacion_de_espacio_del_entorno_tiene_nombre() -> None:
    previa = leer("componentes/vista-previa/vista-previa.js")

    assert re.search(r"ENV_NOMBRES = \{[^}]*espacio:'Espacio libre en disco'", previa)


def test_los_estilos_de_la_seccion_usan_solo_tokens() -> None:
    css = leer("componentes/configuracion/configuracion.css")
    bloque = css[css.index("/* Espacio en disco") : css.index("/* Apariencia */")]

    assert ".esp-datos" in bloque and ".esp-codigo" in bloque
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", bloque)
    for uso in re.findall(r"var\((--[a-z0-9-]+)\)", bloque):
        assert uso in leer("css/tokens.css")

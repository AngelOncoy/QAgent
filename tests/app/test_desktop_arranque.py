"""Arranque de la ventana: cómo se carga la interfaz (sin abrir ninguna ventana real)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from pyagent.app import desktop


def _arrancar() -> dict:
    """Ejecuta main() con pywebview simulado y devuelve los argumentos de create_window."""
    with (
        patch.object(
            desktop.webview, "create_window", return_value=MagicMock()
        ) as crear,
        patch.object(desktop.webview, "start") as iniciar,
    ):
        desktop.main()
    iniciar.assert_called_once()
    return crear.call_args.kwargs


def test_la_interfaz_se_carga_como_url_file_y_no_como_ruta() -> None:
    """Con una ruta, pywebview levanta un servidor HTTP cuya cola de 5 conexiones rechaza
    peticiones al abrir la ventana (decenas de archivos a la vez): estilos y scripts perdidos."""
    url = _arrancar()["url"]
    assert url.startswith("file:///")


def test_la_url_apunta_al_index_del_frontend() -> None:
    url = _arrancar()["url"]
    ruta = Path(url2pathname(unquote(urlparse(url).path)))
    assert ruta.is_file()
    assert ruta.resolve() == (desktop.FRONTEND_DIR / "index.html").resolve()


def test_no_se_activa_el_servidor_http_de_pywebview() -> None:
    with (
        patch.object(desktop.webview, "create_window", return_value=MagicMock()),
        patch.object(desktop.webview, "start") as iniciar,
    ):
        desktop.main()
    assert iniciar.call_args.kwargs.get("http_server") in (None, False)

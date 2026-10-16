"""Selector nativo usado por el destino del clonado."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

webview = pytest.importorskip("webview")

from qagent.app.desktop import DesktopAPI


def test_select_folder_abre_dialogo_nativo_y_devuelve_la_carpeta(tmp_path) -> None:
    window = MagicMock()
    window.create_file_dialog.return_value = [str(tmp_path)]
    api = DesktopAPI()
    api.set_window(window)

    assert api.select_folder() == str(tmp_path)
    window.create_file_dialog.assert_called_once_with(webview.FOLDER_DIALOG)


def test_select_folder_cancelado_no_modifica_un_destino() -> None:
    window = MagicMock()
    window.create_file_dialog.return_value = None
    api = DesktopAPI()
    api.set_window(window)

    assert api.select_folder() is None

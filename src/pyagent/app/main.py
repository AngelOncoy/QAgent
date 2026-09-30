"""Punto de entrada de la aplicación de escritorio PyAgent."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import webview

from pyagent.app.api import Api

UI_INDEX = Path(__file__).parent / "ui" / "index.html"


def main() -> None:
    """Crea la ventana principal y arranca pywebview."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    webview.create_window(
        "PyAgent",
        str(UI_INDEX),
        js_api=Api(),
        width=1280,
        height=820,
        min_size=(960, 640),
        background_color="#0a0f1c",
    )
    webview.start(debug=os.environ.get("PYAGENT_DEBUG") == "1")


if __name__ == "__main__":
    main()

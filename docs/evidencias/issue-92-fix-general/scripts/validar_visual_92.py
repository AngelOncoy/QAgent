"""Validación visual automatizada de la issue #92 con Playwright (arnés reproducible).

Inicia un servidor HTTP local multihilo para servir src/qagent/frontend/,
recorre las 5 resoluciones requeridas (1024x700, 1280x720, 1366x768, 1440x900, 1920x1080)
y valida métricas DOM para los cuatro defectos corregidos:
  - Q92-001: scrollLeft == 0 y scrollWidth <= clientWidth en #s-preview .scroll.
  - Q92-002: ninguna celda de decisiones muestra 'undefined', 'null' ni 'NaN'.
  - Q92-003: scrollWidth <= clientWidth en .tree-head.
  - Q92-004: link al favicon SVG presente y resuelto sin HTTP 404.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[4]  # <repo>/docs/evidencias/issue-92-fix-general/scripts -> <repo>
FRONTEND = RAIZ / "src" / "qagent" / "frontend"
EVIDENCIAS = RAIZ / "docs" / "evidencias" / "issue-92-fix-general"
IMG_DESPUES = EVIDENCIAS / "img" / "despues"
IMG_DESPUES.mkdir(parents=True, exist_ok=True)

PORT = 8795
VIEWPORTS = [
    (1024, 700),
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1920, 1080),
]


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def log_message(self, format, *args):
        pass  # Silenciar registros HTTP estándar


def start_server():
    cwd_original = os.getcwd()
    os.chdir(str(FRONTEND))
    server = ThreadingServer(("127.0.0.1", PORT), http.server.SimpleHTTPRequestHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    return server, cwd_original


def run_tests():
    results = {}
    server, cwd_original = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for w, h in VIEWPORTS:
                label = f"{w}x{h}"
                context = browser.new_context(viewport={"width": w, "height": h})
                page = context.new_page()

                console_errors = []
                network_failures = []
                http_responses = []

                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.on("requestfailed", lambda req: network_failures.append(f"{req.method} {req.url} {req.failure}"))
                page.on("response", lambda res: http_responses.append((res.status, res.url)))

                page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
                page.wait_for_timeout(500)

                # Q92-004: Favicon
                favicon_responses = [resp for resp in http_responses if "favicon" in resp[1] or "icono.svg" in resp[1]]
                favicon_link = page.query_selector('link[rel="icon"]')
                favicon_href = favicon_link.get_attribute("href") if favicon_link else None
                favicon_404 = any(status == 404 and ("favicon" in url or "icono" in url) for status, url in http_responses)

                q004 = {
                    "favicon_link_present": favicon_link is not None,
                    "favicon_href": favicon_href,
                    "favicon_404_error": favicon_404,
                    "pass": (favicon_link is not None) and (not favicon_404) and any(s == 200 for s, u in favicon_responses),
                }

                # Abrir proyecto de demo
                page.evaluate("abrirReciente(0)")
                page.wait_for_timeout(500)

                # Q92-003: Encabezado del árbol
                tree_head = page.query_selector(".tree-head")
                q003 = {"pass": False, "scroll_width": None, "client_width": None}
                if tree_head:
                    dims = tree_head.evaluate("el => ({sw: el.scrollWidth, cw: el.clientWidth})")
                    q003["scroll_width"] = dims["sw"]
                    q003["client_width"] = dims["cw"]
                    q003["pass"] = dims["sw"] <= dims["cw"]

                page.screenshot(path=str(IMG_DESPUES / f"funciones-{label}.png"), full_page=False)

                # Cambiar a Endpoints
                page.evaluate("cambiarVistaObjetivos('endpoints')")
                page.wait_for_timeout(500)

                # Q92-001: Desbordamiento horizontal
                scroll_el = page.query_selector("#s-preview .scroll")
                q001 = {"pass": False, "scroll_left": None, "scroll_width": None, "client_width": None, "table_scroll": {}}
                if scroll_el:
                    dims = scroll_el.evaluate("el => ({sl: el.scrollLeft, sw: el.scrollWidth, cw: el.clientWidth})")
                    q001["scroll_left"] = dims["sl"]
                    q001["scroll_width"] = dims["sw"]
                    q001["client_width"] = dims["cw"]

                    table_scroll = page.query_selector("#s-preview .table-scroll.ep-scroll")
                    if table_scroll:
                        t_dims = table_scroll.evaluate("""el => ({
                            sw: el.scrollWidth,
                            cw: el.clientWidth,
                            sl: el.scrollLeft,
                            ox: window.getComputedStyle(el).overflowX
                        })""")
                        q001["table_scroll"] = t_dims

                    q001["pass"] = (dims["sl"] == 0) and (dims["sw"] <= dims["cw"])

                # Q92-002: Decisiones
                decision_cells = page.query_selector_all("#endpointTable tr:not(.file-row) td:nth-child(7)")
                valores = [(c.text_content() or "").strip() for c in decision_cells]
                undefined_present = any(v in ("undefined", "null", "NaN", "[object Object]") for v in valores)

                q002 = {
                    "total_celdas": len(valores),
                    "valores_unicos": sorted(list(set(valores))),
                    "undefined_present": undefined_present,
                    "pass": len(valores) > 0 and not undefined_present,
                }

                page.screenshot(path=str(IMG_DESPUES / f"endpoints-{label}.png"), full_page=False)
                if label == "1024x700":
                    page.screenshot(path=str(IMG_DESPUES / "vista-1024x700.png"), full_page=False)

                results[label] = {
                    "Q92-001": q001,
                    "Q92-002": q002,
                    "Q92-003": q003,
                    "Q92-004": q004,
                }
                context.close()

            browser.close()
    finally:
        server.shutdown()
        os.chdir(cwd_original)

    results_path = EVIDENCIAS / "validacion-visual-resultados.json"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return all(data.get("pass") for vp in results.values() for data in vp.values())


if __name__ == "__main__":
    success = run_tests()
    print("Validación visual:", "OK" if success else "FALLO")
    exit(0 if success else 1)

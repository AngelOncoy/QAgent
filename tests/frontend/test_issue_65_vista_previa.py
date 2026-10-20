"""Contrato estructural de la nueva Vista previa (issue #65).

Verifica, sin navegador ni Node obligatorio, el orden de columnas, el semáforo de
Calidad calculado en el frontend, los indicadores, los tooltips, la agrupación por
archivo, el plegado y la casilla "Incluir" con estado indeterminado. No toca el
backend ni los contratos de datos: todo se comprueba sobre el propio frontend.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"

VISTA_JS = (FRONTEND / "componentes" / "vista-previa" / "vista-previa.js").read_text(
    encoding="utf-8"
)
VISTA_CSS = (FRONTEND / "componentes" / "vista-previa" / "vista-previa.css").read_text(
    encoding="utf-8"
)
TOKENS = (FRONTEND / "css" / "tokens.css").read_text(encoding="utf-8")


def _bloque_funciones() -> str:
    return VISTA_JS[VISTA_JS.index('<table class="fn-table">') :]


def _encabezados() -> list[str]:
    """Etiquetas visibles de las cabeceras de la tabla de funciones, en orden."""
    thead = _bloque_funciones()[: _bloque_funciones().index("</thead>")]
    return [
        texto.strip()
        for texto in re.findall(r"<th[^>]*>(.*?)</th>", thead, re.DOTALL)
        if '<span class="vh"' not in texto
    ]


def _cuerpo(nombre_funcion: str) -> str:
    inicio = VISTA_JS.index(f"function {nombre_funcion}")
    resto = VISTA_JS[inicio:]
    return resto[: resto.index("\n}\n")]


# 1. Orden exacto de las columnas
def test_orden_exacto_de_las_columnas() -> None:
    # Rediseño: tabla compacta. «Incluir» es la casilla de la primera columna (sin título visible);
    # «Complejidad», «Desde la última vez» y «Profundizar».
    assert _encabezados() == [
        "Función / endpoint",
        "Complejidad",
        "Desde la última vez",
        "Profundizar",
    ]
    assert (
        '<th class="col-incl"><span class="vh">Incluir</span></th>'
        in _bloque_funciones()
    )


# 4-7. Cálculo de Complejidad
def test_complejidad_se_calcula_solo_en_el_frontend() -> None:
    assert "function textoComplejidad" in VISTA_JS
    assert "function normalizarDecisiones" in VISTA_JS


def test_complejidad_simple_cuando_pocas_decisiones() -> None:
    assert 'if(n < 3) return `<span title="${tip}">Simple</span>`;' in VISTA_JS


def test_complejidad_muchas_ramas() -> None:
    assert (
        'return `<span class="exp-aviso" title="${tip}">Muchas ramas</span>`;'
        in VISTA_JS
    )


def test_complejidad_ausente_muestra_guion() -> None:
    assert "if(n === null) return '<span class=\"exp-sub\">—</span>';" in VISTA_JS


def test_normalizar_decisiones_rechaza_no_enteros() -> None:
    cuerpo = _cuerpo("normalizarDecisiones")
    assert "Number.isInteger(valor)" in cuerpo
    assert "valor >= 0" in cuerpo


def test_desde_la_ultima_vez_muestra_reutilizacion_o_cambio() -> None:
    assert "function textoDesdeUltimaVez" in VISTA_JS
    assert "Sin cambios desde la última vez" in VISTA_JS
    assert "Cambió" in VISTA_JS


# 7. Condicionales con el campo existente
def test_condicionales_usan_el_campo_br_existente() -> None:
    assert "<td>${textoComplejidad(f.br)}</td>" in VISTA_JS


# 8. Cambio visual de Crítica a Profundizar
def test_la_columna_critica_se_renombra_a_profundizar() -> None:
    assert "Profundizar" in _encabezados()
    assert "Crítica" not in _encabezados()
    assert "<th>Crítica" not in VISTA_JS


# 9. Preservación interna de critical / crit
def test_se_conserva_la_variable_interna_crit() -> None:
    assert "toggle(${mi},${fi},'crit')" in VISTA_JS
    assert "f.crit" in VISTA_JS
    assert 'aria-label="Profundizar: ${escHtml(f.n)}"' in VISTA_JS


# 10. Valor inicial de critica_propuesta
def test_valor_inicial_de_profundizar_viene_de_critica_propuesta() -> None:
    assert "crit: f.critica_propuesta ?? ((f.ramas || 0) > 0)" in VISTA_JS


# 11. Edición manual de Profundizar
def test_profundizar_es_editable_manualmente() -> None:
    assert "onchange=\"toggle(${mi},${fi},'crit')\"" in VISTA_JS
    assert "Profundizar: solicita un análisis más exhaustivo" in VISTA_JS


# 12. Tooltips de las cabeceras
def test_tooltips_explicativos_en_las_cabeceras() -> None:
    assert "Profundizar: solicita un análisis más exhaustivo" in VISTA_JS
    assert 'title="${escHtml(f.n + f.sig)}"' in VISTA_JS
    assert "1 decisión (if, bucle o excepción)" in VISTA_JS


def test_tooltips_accesibles_con_mouse_y_teclado() -> None:
    assert 'id="tipFlotante"' in VISTA_JS
    assert 'role="tooltip"' in VISTA_JS
    assert "function mostrarTooltip" in VISTA_JS
    assert "function iniciarTooltips" in VISTA_JS
    assert "'mouseenter'" in VISTA_JS and "'focus'" in VISTA_JS
    assert ".tip-flotante" in VISTA_CSS


# 13. Árbol de carpetas y ruta en filas
def test_agrupacion_por_archivo_con_encabezado_plegable() -> None:
    assert 'id="tree"' in VISTA_JS
    assert "function renderTree" in VISTA_JS
    assert ".tree .row" in VISTA_CSS
    assert '<div class="sub">${escHtml(m.path)}</div>' in VISTA_JS


# 14. Conteo de funciones por archivo
def test_conteo_de_funciones_por_archivo() -> None:
    assert "resumenFunciones" in VISTA_JS
    assert "resumenEndpoints" in VISTA_JS
    assert "resumenModulos" in VISTA_JS


# 16. Preservación de etiquetas de spec
def test_se_conservan_las_etiquetas_de_spec() -> None:
    assert "Sin cambios desde la última vez" in VISTA_JS
    assert "Cambió" in VISTA_JS
    # Sin datos de una corrida anterior se muestra un guion: nunca se supone el estado.
    assert "No hay datos de una corrida anterior para este archivo" in VISTA_JS


# 21-22. Incluir / desmarcar todas las funciones del archivo
def test_checkbox_de_archivo_marca_desmarca_todas_las_funciones() -> None:
    cuerpo = _cuerpo("seleccionarCarpeta")
    assert "modulosDeCarpeta(dir).forEach(m => { m.sel = !!seleccionado; });" in cuerpo


# 24. Sincronización del encabezado con las funciones individuales
def test_encabezado_sincronizado_con_las_casillas_individuales() -> None:
    assert "function sincronizarCarpetas" in VISTA_JS
    assert "chk.indeterminate = sel > 0 && sel < mods.length;" in VISTA_JS
    assert "function actualizarSeleccionTodos" in VISTA_JS


# 25. Archivos con errores de sintaxis
def test_los_errores_de_sintaxis_se_siguen_mostrando() -> None:
    assert "no se pudo analizar" in VISTA_JS
    assert "Error de sintaxis" in VISTA_JS
    # Rediseño: se listan en el aviso «archivos no se pudieron leer», con su motivo.
    assert "function renderErroresLectura" in VISTA_JS
    assert "renderErroresLectura();" in VISTA_JS


# 26. Archivos sin funciones
def test_archivos_sin_funciones() -> None:
    assert "no-targets" in VISTA_JS
    assert "sin objetivos analizables" in VISTA_JS


# 27. Conservación de selección AST
def test_conserva_la_seleccion_ast() -> None:
    assert "function obtenerSeleccionObjetivos" in VISTA_JS
    assert "m.sel && moduloTieneObjetivos(m)" in VISTA_JS
    assert "filter(f => f.inc).map(f => f.n)" in VISTA_JS


# 28. La vista previa sigue mostrando endpoints
def test_conserva_la_tabla_de_endpoints() -> None:
    assert 'id="endpointTable"' in VISTA_JS
    assert "function renderEndpoints" in VISTA_JS


# 29. Compatibilidad con las regresiones de #63
def test_compatibilidad_con_las_regresiones_de_63() -> None:
    assert "sel: tieneObjetivos" in VISTA_JS
    assert "moduloTieneObjetivos(m) && seleccionado" in VISTA_JS
    assert "fns.length > 0 || endpoints.length > 0" in VISTA_JS


# Tokens de estado del sistema
def test_los_tokens_de_calidad_existen_y_se_usan() -> None:
    for token in (
        "--exito-t",
        "--aviso-t",
        "--enlace",
        "--texto-3",
    ):
        assert f"{token}:" in TOKENS
    assert "var(--exito-t)" in VISTA_CSS
    assert "var(--aviso-t)" in VISTA_CSS


# 30. Ausencia de errores JavaScript (si hay Node disponible)


def test_sin_errores_de_sintaxis_javascript() -> None:
    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está disponible para validar la sintaxis JavaScript.")
    ruta = FRONTEND / "componentes" / "vista-previa" / "vista-previa.js"
    try:
        resultado = subprocess.run(
            [node, "--check", str(ruta)],
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
    except OSError:
        # Algunos entornos con la salida redirigida no dejan crear el proceso hijo.
        pytest.skip("No se pudo ejecutar Node en este entorno.")
    assert resultado.returncode == 0, resultado.stderr

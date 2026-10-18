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
    return [texto.strip() for texto in re.findall(r"<th>(.*?)<span", thead, re.DOTALL)]


def _cuerpo(nombre_funcion: str) -> str:
    inicio = VISTA_JS.index(f"function {nombre_funcion}")
    resto = VISTA_JS[inicio:]
    return resto[: resto.index("\n}\n")]


# 1. Orden exacto de las columnas
def test_orden_exacto_de_las_columnas() -> None:
    # Rediseño: tabla compacta. «Incluir» es la casilla de la primera columna (sin título visible);
    # tipos y docstring se resumen en «Información» y las condicionales en «Complejidad».
    assert _encabezados() == [
        "Función",
        "Complejidad",
        "Información",
        "Desde la última vez",
        "Profundizar",
    ]
    assert (
        '<th class="col-incl"><span class="vh">Incluir</span></th>'
        in _bloque_funciones()
    )


# 4-7. Cálculo de Calidad y su prioridad
def test_calidad_se_calcula_solo_en_el_frontend() -> None:
    cuerpo = _cuerpo("calidadFuncion")

    assert "function calidadFuncion" in VISTA_JS
    # Incierto tiene prioridad: se evalúa primero, aunque existan tipos declarados.
    assert cuerpo.index("return 'incierto'") < cuerpo.index("return 'lista'")
    assert cuerpo.index("return 'lista'") < cuerpo.index("return 'mejorable'")
    assert "if(!f.doc) return 'incierto'" in cuerpo
    assert "if(f.typed) return 'lista'" in cuerpo
    assert "return 'mejorable'" in cuerpo
    assert (
        "CALIDAD_TEXTO = {lista:'Completa', mejorable:'Faltan tipos', incierto:'Sin descripción'}"
        in VISTA_JS
    )


def test_calidad_lista_cuando_hay_tipos_y_docstring() -> None:
    assert "if(f.typed) return 'lista'" in VISTA_JS


def test_calidad_mejorable_cuando_falta_tipos_pero_hay_docstring() -> None:
    assert "return 'mejorable'" in VISTA_JS
    assert "CALIDAD_TEXTO" in VISTA_JS


def test_calidad_incierto_cuando_falta_docstring() -> None:
    assert "if(!f.doc) return 'incierto'" in VISTA_JS


def test_incierto_tiene_prioridad_sobre_los_tipos() -> None:
    cuerpo = _cuerpo("calidadFuncion")
    assert cuerpo.index("f.doc") < cuerpo.index("f.typed")


# 6. Indicadores ✓ / ✗
def test_indicadores_tipos_y_docstring() -> None:
    assert (
        '<span class="ok" title="Declara los tipos que recibe y devuelve">✓</span>'
        in VISTA_JS
    )
    assert '<span class="no" title="No declara los tipos">✗</span>' in VISTA_JS
    assert '<span class="ok" title="Tiene descripción">✓</span>' in VISTA_JS
    # Docstring ausente se muestra con ✗ (texto, no solo color)
    assert (
        'title="el valor esperado no tendrá fuente (oráculo débil)">✗</span>'
        in VISTA_JS
    )


# 7. Condicionales con el campo existente
def test_condicionales_usan_el_campo_br_existente() -> None:
    assert '<td class="mono">${f.br}</td>' in VISTA_JS


# 8. Cambio visual de Crítica a Profundizar
def test_la_columna_critica_se_renombra_a_profundizar() -> None:
    assert "Profundizar" in _encabezados()
    assert "Crítica" not in _encabezados()
    assert "<th>Crítica" not in VISTA_JS


# 9. Preservación interna de critical / crit
def test_se_conserva_la_variable_interna_crit() -> None:
    assert "toggle(${mi},${fi},'crit')" in VISTA_JS
    assert "f.crit" in VISTA_JS
    assert "aria-pressed" in VISTA_JS


# 10. Valor inicial de critica_propuesta
def test_valor_inicial_de_profundizar_viene_de_critica_propuesta() -> None:
    assert "crit: f.critica_propuesta ?? ((f.ramas || 0) > 0)" in VISTA_JS


# 11. Edición manual de Profundizar
def test_profundizar_es_editable_manualmente() -> None:
    assert "onclick=\"toggle(${mi},${fi},'crit')\"" in VISTA_JS
    assert "Profundizar: solicita un análisis más exhaustivo" in VISTA_JS


# 12. Tooltips de las cabeceras
def test_tooltips_explicativos_en_las_cabeceras() -> None:
    textos = [
        "Nombre de la función encontrada en el archivo Python.",
        "Indica si QAgent tiene suficiente información para saber qué resultado debería producir la función.",
        "Indica si la función declara los tipos de datos que recibe y devuelve.",
        "Es la descripción de la función y ayuda a determinar el resultado esperado.",
        "Muestra cuántas estructuras condicionales se detectaron. Más condicionales pueden requerir más casos de prueba.",
        "Solicita un análisis más exhaustivo de la función. Puede requerir más tiempo de ejecución.",
        "Permite seleccionar si esta función formará parte del análisis.",
    ]
    for texto in textos:
        assert f'data-tip="{texto}"' in VISTA_JS


def test_tooltips_accesibles_con_mouse_y_teclado() -> None:
    assert 'class="info" tabindex="0"' in VISTA_JS
    assert 'role="tooltip"' in VISTA_JS
    assert 'aria-label="' in VISTA_JS
    assert "function mostrarTooltip" in VISTA_JS
    assert "function iniciarTooltips" in VISTA_JS
    assert "'mouseenter'" in VISTA_JS and "'focus'" in VISTA_JS
    # Estado visual de foco del icono informativo
    assert ".info:focus-visible" in VISTA_CSS


# 13. Agrupación por archivo
def test_agrupacion_por_archivo_con_encabezado_plegable() -> None:
    assert 'class="file-row"' in VISTA_JS
    assert 'class="file-head' in VISTA_JS
    assert "function toggleArchivo" in VISTA_JS
    assert "file-icon" in VISTA_JS
    assert "file-path" in VISTA_JS


# 14. Conteo de funciones por archivo
def test_conteo_de_funciones_por_archivo() -> None:
    assert 'class="file-count"' in VISTA_JS
    assert "'función' : 'funciones'" in VISTA_JS


# 15. Conteo de funciones por revisar (solo Mejorable e Incierto)
def test_conteo_por_revisar_excluye_las_listas() -> None:
    assert "function contarPorRevisar" in VISTA_JS
    assert "calidadFuncion(f) !== 'lista'" in VISTA_JS
    assert " por revisar" in VISTA_JS


# 16. Preservación de etiquetas de spec
def test_se_conservan_las_etiquetas_de_spec() -> None:
    assert "Vigente" in VISTA_JS
    assert "Cambió" in VISTA_JS
    # Sin datos de una corrida anterior se muestra un guion: nunca se supone el estado.
    assert "No hay datos de una corrida anterior para este archivo" in VISTA_JS


# 17-18. Plegado inicial según "por revisar"
def test_archivos_con_funciones_por_revisar_abren_por_defecto() -> None:
    assert "return contarPorRevisar(m) > 0" in VISTA_JS


def test_archivos_sin_funciones_por_revisar_quedan_plegados() -> None:
    # Sin entrada elegida y sin funciones por revisar -> no desplegado.
    cuerpo = _cuerpo("archivoAbierto")
    assert "contarPorRevisar(m) > 0" in cuerpo


# 19. Expansión y plegado manual (estado elegido por el usuario)
def test_el_usuario_puede_abrir_y_cerrar_manual() -> None:
    assert "ARCHIVOS_ABIERTOS[m.path] = !archivoAbierto(m)" in VISTA_JS
    assert "let ARCHIVOS_ABIERTOS = {}" in VISTA_JS


# 20. Preservación de selección al plegar
def test_plegar_no_altera_la_seleccion() -> None:
    cuerpo = _cuerpo("toggleArchivo")
    assert "ARCHIVOS_ABIERTOS" in cuerpo
    assert ".inc" not in cuerpo
    assert "m.sel" not in cuerpo


# 21-22. Incluir / desmarcar todas las funciones del archivo
def test_checkbox_de_archivo_marca_desmarca_todas_las_funciones() -> None:
    cuerpo = _cuerpo("seleccionarArchivo")
    assert "f.inc = !!seleccionado" in cuerpo
    assert "moduloTieneObjetivos(m)" in cuerpo


# 23. Checkbox indeterminado
def test_estado_indeterminado_del_checkbox_de_archivo() -> None:
    assert ".indeterminate" in VISTA_JS
    assert "chk.indeterminate" in VISTA_JS


# 24. Sincronización del encabezado con las funciones individuales
def test_encabezado_sincronizado_con_las_casillas_individuales() -> None:
    assert "function sincronizarCheckboxesArchivo" in VISTA_JS
    assert "sincronizarCheckboxesArchivo();" in VISTA_JS
    assert 'class="file-check" data-mi=' in VISTA_JS


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


# 28. La vista previa sigue mostrando endpoints (reescrito por la issue #66, que cambia
# esa tabla por una con Calidad, Estado, Respuesta, Errores y Simula, agrupada por archivo).
def test_conserva_la_tabla_de_endpoints() -> None:
    assert 'id="endpointTable"' in VISTA_JS
    assert "function renderEndpoints" in VISTA_JS


# 29. Compatibilidad con las pruebas existentes de #63
def test_compatibilidad_con_las_regresiones_de_63() -> None:
    assert "sel: tieneObjetivos" in VISTA_JS
    assert "moduloTieneObjetivos(m) && seleccionado" in VISTA_JS
    assert "fns.length > 0 || endpoints.length > 0" in VISTA_JS


# Semáforo sin depender solo del color
def test_los_tokens_de_calidad_existen_y_se_usan() -> None:
    for token in (
        "--calidad-lista-t",
        "--calidad-mejorable-t",
        "--calidad-incierto-t",
        "--tooltip-bg",
    ):
        assert f"{token}:" in TOKENS
    # Rediseño: Explorar usa los tokens de estado del sistema (éxito y aviso), siempre con texto.
    assert "var(--exito-s)" in VISTA_CSS
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

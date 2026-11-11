"""Issue 266, fase 2: cifras de Abrir y Exploración (I1), carpetas excluidas (I2) y
opciones avanzadas de Preparar plegadas (I6). Sin navegador."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"
VISTA = (FRONTEND / "componentes/vista-previa/vista-previa.js").read_text(
    encoding="utf-8"
)
PREPARAR = (FRONTEND / "componentes/config-pruebas/config-pruebas.js").read_text(
    encoding="utf-8"
)


def _cuerpo(js: str, funcion: str) -> str:
    resto = js[js.index(f"function {funcion}(") :]
    return resto[: resto.index("\n}\n")]


def test_i1_la_demo_de_abrir_cuenta_los_mismos_archivos_que_exploracion() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite ejecutar los datos de la demostración.")
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const rutas = JSON.parse(fs.readFileSync(0, 'utf8'));
const ctx = vm.createContext({window: {addEventListener() {}}, registrarComponente() {},
  document: {addEventListener() {}, querySelectorAll: () => []}});
for (const r of rutas) vm.runInContext(fs.readFileSync(r, 'utf8'), ctx);
// Exploración muestra en «Archivos» los legibles más los que no se pudieron leer.
const archivos = vm.runInContext('MODULES.length', ctx);
for (const carpeta of ['ecommerce-core', 'banco-pruebas-mvp'])
  assert.equal(vm.runInContext(`DEMO_CARPETAS['${carpeta}'].cantidad_py`, ctx), archivos);
"""
    rutas = [
        str(FRONTEND / "js/estado.js"),
        str(FRONTEND / "componentes/inicio/modal-abrir.js"),
    ]
    resultado = subprocess.run(
        [node, "-e", script],
        input=json.dumps(rutas),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_i1_la_tabla_explica_la_diferencia_con_la_pestana() -> None:
    # La pestaña sigue contando lo detectado (#66) y lo aclara al pasar el ratón.
    selector = _cuerpo(VISTA, "actualizarSelectorObjetivos")
    assert "funciones detectadas'} en el proyecto, incluidas o no" in selector
    assert "endpoints detectados'} en el proyecto, incluidos o no" in selector
    # «Mostrando» dice que cuenta solo las carpetas incluidas y cuánto queda fuera.
    tabla = _cuerpo(VISTA, "renderFns")
    assert "en las carpetas incluidas`" in tabla
    assert "más en carpetas no incluidas" in tabla
    assert (
        "(esFns ? totalFuncionesDetectadas() : totalEndpointsDetectados()) - vistaTodas.length"
        in tabla
    )


def test_i2_las_carpetas_excluidas_no_tienen_casilla() -> None:
    arbol = _cuerpo(VISTA, "renderTree")
    assert "['tests', '.qagent']" not in arbol
    assert 'class="row ign"' not in VISTA
    nota = VISTA[VISTA.index('id="expCarpetasNota"') :]
    nota = nota[: nota.index("</p>")]
    # Mismo criterio que «No se analizan» de Abrir proyecto y listar_archivos_py.
    for parte in ("tests", "entornos virtuales y dependencias", "carpetas ocultas"):
        assert parte in nota
    assert ".qagent" in nota and "ni se pueden seleccionar" in nota


def test_i6_arquitectura_y_e2e_quedan_plegadas_en_opciones_avanzadas() -> None:
    inicio = PREPARAR.index('<details class="np-opciones prep-avanzado"')
    fin = PREPARAR.index("</details>", inicio)
    avanzado = PREPARAR[inicio:fin]
    etiqueta = avanzado[: avanzado.index(">")]
    assert " open" not in etiqueta  # plegado por defecto
    assert (
        "data-caja-grupo" in etiqueta
    )  # se oculta si su caja no tiene nada que mostrar
    assert 'aria-labelledby="prepArquitecturaTitulo"' in avanzado
    assert 'aria-labelledby="prepE2ETitulo"' in avanzado
    # Lo necesario para iniciar queda fuera del plegado.
    for necesario in ('id="cfgModo"', 'id="prepTipos"', 'id="prepComprobaciones"'):
        assert necesario in PREPARAR and necesario not in avanzado
    caja = _cuerpo(PREPARAR, "aplicarCaja")
    assert "cajaActiva !== 'todas' && !avanzado.classList.contains('hide')" in caja
    assert "avanzado.open = true" in caja

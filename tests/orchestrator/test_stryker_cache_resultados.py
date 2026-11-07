"""Integra el informe de Stryker grabado con caché y resultados comunes sin Docker (#179).

Verifica la reutilización de resultados de mutación (.qagent/mutacion/<spec>.json),
la invalidación cuando cambia la función o la prueba aprobada, y la presencia
del Mutation Score y sobrevivientes en results.json y los informes exportados.
"""

import json
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.analysis.analyzer import calcular_huella
from qagent.lenguajes import TypeScriptAdapter
from qagent.llm import TokenTracker, cargar_precios
from qagent.orchestrator.estados import Estado
from qagent.orchestrator.mutacion import mutar_modulo
from qagent.orchestrator.orquestador import ResultadoCorrida, ResultadoObjetivo
from qagent.orchestrator.regresion import huellas_de_objetivos
from qagent.sandbox.stryker import interpretar_stryker
from qagent.storage.exportar_informe import exportar_informe, extraer_texto_pdf
from qagent.storage.registro import escribir_corrida
from qagent.storage.vista_reporte import vista_reporte

MODULO = "src/precios.ts"
OBJETIVO = "calcularDescuento"
FUENTE = """export function calcularDescuento(precio: number, tipo: string): number {
  if (precio > 100) {
    return precio * 0.9;
  }
  return precio;
}

export function formatearMoneda(monto: number): string {
  return '$' + monto.toFixed(2);
}
"""
PRUEBA = """import { describe, it, expect } from 'vitest';
import { calcularDescuento } from '../proyecto/src/precios';

describe('calcularDescuento', () => {
  it('aplica descuento a mayores de 100', () => {
    expect(calcularDescuento(200, 'normal')).toBe(180);
  });
});
"""

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "javascript"
    / "stryker-report.json"
)


@pytest.fixture
def preparado_ts(tmp_path: Path, monkeypatch):
    """Prepara proyecto TS con archivo fuente y AlmacenProyecto inicializado."""
    archivo = tmp_path / MODULO
    archivo.parent.mkdir(parents=True)
    archivo.write_text(FUENTE, encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()

    llamadas = []
    reporte_json = FIXTURE_PATH.read_text(encoding="utf-8")

    def ejecutar_grabado(imagen, raiz, pruebas, modulo, funciones, limites, **opciones):
        llamadas.append(list(funciones))
        assert modulo == MODULO
        assert funciones == [OBJETIVO]
        return interpretar_stryker(
            reporte_json,
            modulo,
            funciones,
            rangos={OBJETIVO: (1, 6)},
        )

    monkeypatch.setattr(
        "qagent.sandbox.stryker_ejecucion.ejecutar_stryker",
        ejecutar_grabado,
    )

    return tmp_path, almacen, llamadas


def _corrida(raiz: Path, codigo: str = PRUEBA) -> ResultadoCorrida:
    """Construye un ResultadoCorrida con objetivo calcularDescuento crítico y aprobado."""
    contrato = {
        "version": "3",
        "lenguaje": "typescript",
        "framework_pruebas": "vitest",
        "modulo": MODULO,
        "huella": calcular_huella((raiz / MODULO).read_text(encoding="utf-8")),
        "tipo": "funcion",
        "objetivo": OBJETIVO,
        "firma": "calcularDescuento(precio: number, tipo: string): number",
        "critical": True,
        "casos": [
            {
                "id": "mayor",
                "entrada": [200, "normal"],
                "valor_esperado": 180,
                "origen": "docstring",
            }
        ],
    }
    return ResultadoCorrida(
        modulo=MODULO,
        estado_final=Estado.FIN,
        motivo_fallo=None,
        objetivos=[
            ResultadoObjetivo(
                OBJETIVO,
                True,
                decision="accept",
                intentos=1,
                contrato=contrato,
                codigo=codigo,
            ),
            ResultadoObjetivo(
                "formatearMoneda",
                False,
                decision="accept",
                codigo="// prueba no critica",
            ),
        ],
        traza_estados=[],
        tokens_por_agente={},
        duracion_s=0.01,
    )


def _mutar(preparado, codigo: str = PRUEBA):
    """Ejecuta mutar_modulo y devuelve corrida y run_id."""
    raiz, almacen, _ = preparado
    corrida = _corrida(raiz, codigo)
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    mensajes = []

    mutar_modulo(
        raiz,
        None,
        {"funciones": TypeScriptAdapter().funciones_de_modulo(raiz, MODULO)},
        corrida,
        120,
        almacen=almacen,
        run_id=run_id,
        huellas=huellas_de_objetivos(raiz),
        avisar=mensajes.append,
    )

    assert any(
        "reutilizado" in m or "Mutation testing (Stryker)" in m for m in mensajes
    )
    return corrida, run_id


def test_cache_stryker_reutiliza_y_se_invalida(preparado_ts) -> None:
    """Sin cambios reutiliza; si cambia el cuerpo o la prueba, vuelve a evaluar."""
    raiz, _, llamadas = preparado_ts
    primera, run_id = _mutar(preparado_ts)
    repetida, _ = _mutar(preparado_ts)

    # Solo una ejecución real a través de Stryker
    assert llamadas == [[OBJETIVO]]
    mutacion = repetida.objetivos[0].mutacion
    assert mutacion["reutilizada"] is True
    assert mutacion["run_origen"] == run_id
    assert mutacion["puntuacion"] == primera.objetivos[0].mutacion["puntuacion"] == 75.0

    # 1. Cambiar cuerpo de la función invalida la huella
    (raiz / MODULO).write_text(
        FUENTE.replace("precio * 0.9", "precio * 0.8"), encoding="utf-8"
    )
    cambiada, _ = _mutar(preparado_ts)
    assert "reutilizada" not in cambiada.objetivos[0].mutacion
    assert llamadas == [[OBJETIVO], [OBJETIVO]]

    # 2. Cambiar el código de la prueba aprobada también invalida
    _mutar(preparado_ts, PRUEBA + "\n// nuevo caso aprobado")
    assert llamadas == [[OBJETIVO], [OBJETIVO], [OBJETIVO]]


def test_score_y_sobrevivientes_llegan_a_results_y_al_informe(preparado_ts) -> None:
    """Verifica que el Mutation Score y mutantes sobrevividos se guarden y exporten."""
    raiz, _, _ = preparado_ts
    corrida, run_id = _mutar(preparado_ts)
    corrida.objetivos = corrida.objetivos[:1]

    precios = cargar_precios()
    rutas = escribir_corrida(
        raiz, corrida, TokenTracker(precios), precios, "deep", run_id=run_id
    )

    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    objetivo = results["objetivos"][0]
    assert objetivo["metricas"]["mutation_score"] == 75.0
    assert objetivo["mutacion"]["detectados"] == 3
    assert len(objetivo["mutacion"]["sobrevivientes"]) == 1

    sobreviviente = objetivo["mutacion"]["sobrevivientes"][0]
    assert sobreviviente["linea"] == 3
    assert "* → /" in sobreviviente["cambio"]

    vista = vista_reporte(results, None)
    assert vista["funciones"][0]["mutacion"] == objetivo["mutacion"]

    exportado = exportar_informe(raiz, run_id=run_id, formato="md")
    contenido_md = Path(exportado["ruta"]).read_text(encoding="utf-8")
    assert "75%" in contenido_md
    assert "calcularDescuento" in contenido_md

    pdf = exportar_informe(raiz, run_id=run_id, formato="pdf")
    texto_pdf = extraer_texto_pdf(Path(pdf["ruta"]).read_bytes())
    assert "línea 3" in texto_pdf
    assert "* -> /" in texto_pdf or "* → /" in texto_pdf

"""Integra el XML PIT grabado con caché y resultados comunes, sin Docker (#180)."""

import json
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.analysis.analyzer import calcular_huella
from qagent.lenguajes import JavaAdapter
from qagent.llm import TokenTracker, cargar_precios
from qagent.orchestrator.estados import Estado
from qagent.orchestrator.mutacion import mutar_modulo
from qagent.orchestrator.orquestador import ResultadoCorrida, ResultadoObjetivo
from qagent.orchestrator.regresion import huellas_de_objetivos
from qagent.sandbox.pit import interpretar_pit
from qagent.storage.exportar_informe import exportar_informe, extraer_texto_pdf
from qagent.storage.registro import escribir_corrida
from qagent.storage.vista_reporte import vista_reporte

MODULO = "src/main/java/qagent/Criticos.java"
OBJETIVO = "Criticos.critico"
FUENTE = """package qagent;
public class Criticos {
    /** Duplica valores mayores a diez; en otro caso devuelve el valor. */
    public static int critico(int valor) {
        if (valor > 10) { return valor * 2; }
        return valor;
    }
    public static int noCritico(int valor) { return valor + 1; }
}
"""
PRUEBA = """package qagent;
import org.junit.jupiter.api.Test;
public class CriticosTest {
    @Test void normal() { org.junit.jupiter.api.Assertions.assertEquals(40, Criticos.critico(20)); }
}
"""


def test_regresion_profunda_usa_limites_del_lenguaje(tmp_path, monkeypatch) -> None:
    """El perfil de pruebas guardadas no entrega memoria Python al adaptador Java."""
    from qagent.config.carga import cargar_configuracion
    from qagent.orchestrator import regresion

    fuente = tmp_path / MODULO
    fuente.parent.mkdir(parents=True)
    fuente.write_text(FUENTE, encoding="utf-8")
    configuracion = cargar_configuracion(simulado=True).config
    assert configuracion is not None
    vistos = []
    monkeypatch.setattr(
        regresion, "mutar_modulo", lambda *a, **kw: vistos.append(kw["limites"])
    )
    regresion._mutar_criticas(
        tmp_path,
        None,
        [_corrida(tmp_path)],
        configuracion,
        None,
        AlmacenProyecto(tmp_path),
        None,
        {},
        lambda *a: None,
    )
    assert vistos == [configuracion.limites_sandbox("java")]
    assert vistos[0].memoria == "4g"


@pytest.fixture
def preparado(tmp_path: Path, monkeypatch):
    """Sustituye solo la ejecución Docker; conserva despacho, lector y caché reales."""
    archivo = tmp_path / MODULO
    archivo.parent.mkdir(parents=True)
    archivo.write_text(FUENTE, encoding="utf-8")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    llamadas = []
    xml = (
        Path(__file__).resolve().parents[1] / "fixtures/pit/critico-real.xml"
    ).read_text(encoding="utf-8")

    def ejecutar_grabado(imagen, raiz, pruebas, modulo, funciones, limites, **opciones):
        """Devuelve el XML ya grabado; esta prueba no vuelve a ejecutar PIT."""
        llamadas.append(list(funciones))
        assert modulo == MODULO
        assert funciones == [OBJETIVO]
        assert any(
            PRUEBA.strip() in p.read_text(encoding="utf-8")
            for p in Path(pruebas).iterdir()
        )
        return interpretar_pit(xml, modulo, {OBJETIVO: ("qagent.Criticos", "critico")})

    monkeypatch.setattr("qagent.sandbox.pit_ejecucion.ejecutar_pit", ejecutar_grabado)
    return tmp_path, almacen, llamadas


def _corrida(raiz: Path, codigo: str = PRUEBA) -> ResultadoCorrida:
    """Construye veredictos conocidos, con una crítica aprobada y objetivos excluidos."""
    contrato = {
        "version": "3",
        "lenguaje": "java",
        "framework_pruebas": "junit5",
        "modulo": MODULO,
        "huella": calcular_huella((raiz / MODULO).read_text(encoding="utf-8")),
        "tipo": "funcion",
        "objetivo": OBJETIVO,
        "firma": "public static int critico(int valor)",
        "critical": True,
        "casos": [
            {
                "id": "normal",
                "entrada": [20],
                "valor_esperado": 40,
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
                "Criticos.noCritico",
                False,
                decision="accept",
                codigo="// prueba aprobada",
            ),
            ResultadoObjetivo(
                "Criticos.rechazado",
                True,
                decision="reject",
                codigo="// prueba rechazada",
            ),
        ],
        traza_estados=[],
        tokens_por_agente={},
        duracion_s=0.01,
    )


def _mutar(preparado, codigo: str = PRUEBA):
    """Invoca la mutación común con las huellas Java y un run_id real del almacén."""
    raiz, almacen, _ = preparado
    corrida = _corrida(raiz, codigo)
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    mensajes = []
    mutar_modulo(
        raiz,
        None,
        {"funciones": JavaAdapter().funciones_de_modulo(raiz, MODULO)},
        corrida,
        120,
        almacen=almacen,
        run_id=run_id,
        huellas=huellas_de_objetivos(raiz),
        avisar=mensajes.append,
    )
    assert any("reutilizado" in m or "Mutation testing (PIT)" in m for m in mensajes)
    assert all(o.mutacion is None for o in corrida.objetivos[1:])
    return corrida, run_id


def test_cache_java_reutiliza_y_se_invalida(preparado) -> None:
    """Sin cambios reutiliza; cambiar cuerpo o prueba fuerza otra evaluación."""
    raiz, _, llamadas = preparado
    primera, run_id = _mutar(preparado)
    repetida, _ = _mutar(preparado)
    assert llamadas == [[OBJETIVO]]
    mutacion = repetida.objetivos[0].mutacion
    assert mutacion["reutilizada"] is True
    assert mutacion["run_origen"] == run_id
    assert mutacion["puntuacion"] == primera.objetivos[0].mutacion["puntuacion"] == 60.0
    (raiz / MODULO).write_text(
        FUENTE.replace("valor * 2", "valor * 3"), encoding="utf-8"
    )
    cambiada, _ = _mutar(preparado)
    assert "reutilizada" not in cambiada.objetivos[0].mutacion
    _mutar(preparado, PRUEBA + "\n// otra versión aprobada")
    assert llamadas == [[OBJETIVO], [OBJETIVO], [OBJETIVO]]


def test_score_y_sobrevivientes_llegan_a_results_y_al_informe(preparado) -> None:
    """Persiste datos PIT con el schema común y los conserva en el informe exportado."""
    raiz, _, _ = preparado
    corrida, run_id = _mutar(preparado)
    # La evidencia de almacenamiento contiene solo el objetivo con contrato completo.
    corrida.objetivos = corrida.objetivos[:1]
    precios = cargar_precios()
    rutas = escribir_corrida(
        raiz, corrida, TokenTracker(precios), precios, "deep", run_id=run_id
    )
    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    objetivo = results["objetivos"][0]
    assert objetivo["metricas"]["mutation_score"] == 60.0
    assert objetivo["mutacion"]["detectados"] == 3
    assert len(objetivo["mutacion"]["sobrevivientes"]) == 2
    vista = vista_reporte(results, None)
    assert vista["funciones"][0]["mutacion"] == objetivo["mutacion"]
    exportado = exportar_informe(raiz, run_id=run_id, formato="md")
    assert "60%" in Path(exportado["ruta"]).read_text(encoding="utf-8")
    pdf = exportar_informe(raiz, run_id=run_id, formato="pdf")
    texto_pdf = extraer_texto_pdf(Path(pdf["ruta"]).read_bytes())
    assert "changed conditional boundary" in texto_pdf
    assert "replaced int return with 0" in texto_pdf

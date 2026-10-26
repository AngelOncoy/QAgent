"""Issue 142: una librería del sistema que falta es un error del entorno, no del test.

Caso real (APP-RF): `import cv2` fallaba por `libGL.so.1`; el Reviewer lo tomaba como
error del test, pedía otro intento y el Generator terminaba simulando `cv2`.
"""

from __future__ import annotations

from pathlib import Path

from qagent import contracts
from qagent.agents.reviewer import ReviewerAgent
from qagent.app.monitor_eventos import a_fila_monitor
from qagent.llm import TokenTracker
from tests.agents.test_reviewer import CODIGO_VALIDO, CONTRATO, EjecutorGrabado, sandbox

RAIZ = Path(__file__).resolve().parents[2]

SALIDA_LIBGL = (
    "ImportError while importing test module '/work/tests/test_generado.py'.\n"
    "app/utils/face_utils.py:1: in <module>\n"
    "    import cv2\n"
    "E   ImportError: libGL.so.1: cannot open shared object file: "
    "No such file or directory\n"
)


def _revisar(tmp_path: Path, salida: str) -> dict:
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(sandbox(2, stdout=salida)),
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": CODIGO_VALIDO,
        "casos_cubiertos": ["duplica_positivo"],
    }
    return reviewer.revisar(CONTRATO, test, None)


def test_libgl_faltante_es_error_del_entorno_sin_reintento(tmp_path: Path) -> None:
    revision = _revisar(tmp_path, SALIDA_LIBGL)

    assert contracts.es_valido(contracts.REVIEW_RESULT, revision)
    assert revision["decision"] == "stalled"  # final: el Generator no vuelve a intentar
    assert revision["tipo_fallo"] is None  # ni error del test ni bug del código
    assert "Error de entorno" in revision["feedback"]
    assert "libGL.so.1" in revision["feedback"]
    assert "Reintentar no lo corrige" in revision["feedback"]


def test_otra_libreria_del_sistema_tambien_es_del_entorno(tmp_path: Path) -> None:
    salida = (
        "OSError: libsndfile.so.1: cannot open shared object file: "
        "No such file or directory\n"
    )

    revision = _revisar(tmp_path, salida)

    assert revision["decision"] == "stalled"
    assert "libsndfile.so.1" in revision["feedback"]


def test_un_import_inventado_por_el_test_sigue_reintentandose(tmp_path: Path) -> None:
    salida = (
        "ImportError while importing test module\n"
        "ModuleNotFoundError: No module named 'modulo_inventado'"
    )

    revision = _revisar(tmp_path, salida)

    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "retry"


# --- Monitor y corrida ------------------------------------------------------------


def test_el_monitor_destaca_la_libreria_faltante() -> None:
    fila = a_fila_monitor(
        {
            "agente": "orquestador",
            "archivo": None,
            "funcion": None,
            "mensaje": "Falta la librería del sistema libfoo.so.1, que necesita foo.",
            "estado": "preparacion",
            "tipo": "aviso",
        }
    )

    assert fila is not None
    assert fila["a"] == "watch"
    assert fila["guard"] == ["Falta una librería del sistema", "ENTORNO"]


def test_la_corrida_avisa_las_librerias_sin_resolver() -> None:
    corrida = (RAIZ / "src" / "qagent" / "orchestrator" / "corrida.py").read_text(
        encoding="utf-8"
    )
    preparar = corrida[corrida.index("def _preparar_imagen") :]

    assert "asegurar_librerias_sistema(imagen, obtener_cliente(), avanzar)" in preparar
    assert 'avisar_faltante(faltante["mensaje"])' in preparar
    assert 'avisar_faltante=lambda mensaje: avisar(mensaje, "aviso")' in corrida
    # La de dependencias también se anota como usada: la final se construye encima.
    llamada = preparar.index("asegurar_librerias_sistema(imagen")
    assert preparar.index("registrar_uso(imagen)") < llamada


def test_el_monitor_muestra_el_aviso_destacado() -> None:
    monitor = (
        RAIZ / "src" / "qagent" / "frontend" / "componentes" / "monitor" / "monitor.js"
    ).read_text(encoding="utf-8")

    assert "if(d.guard && d.guard[1] === 'ENTORNO' && PRG){" in monitor

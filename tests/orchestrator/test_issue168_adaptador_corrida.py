"""#168: la corrida pide el adaptador al registro y un lenguaje sin soporte se avisa.

Sin Docker ni red: el sandbox se simula.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qagent.app.desktop import DesktopAPI
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.lenguajes import (
    REGISTRO,
    LenguajeNoSoportado,
    adaptador_del_proyecto,
)
from qagent.orchestrator import regresion
from qagent.orchestrator.corrida import FALLO, ejecutar_corrida
from qagent.sandbox import ResultadoSandbox
from tests.lenguajes.en_desarrollo import simular_node_en_desarrollo

FUNCION_PY = (
    'def duplicar(x: int) -> int:\n    """Devuelve 2 * x."""\n    return 2 * x\n'
)


def _escribir(raiz: Path, archivos: dict[str, str]) -> Path:
    for ruta, texto in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return raiz


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


# --- Selección del adaptador ------------------------------------------------------


def test_un_proyecto_python_usa_el_adaptador_de_python(tmp_path) -> None:
    _escribir(tmp_path, {"calc.py": FUNCION_PY, "requirements.txt": ""})

    assert adaptador_del_proyecto(tmp_path).lenguaje == "python"


def test_python_con_algo_de_javascript_se_sigue_probando_como_python(tmp_path) -> None:
    """Un `static/` con más archivos .js que .py no cambia el lenguaje de la corrida."""
    _escribir(
        tmp_path,
        {
            "app.py": FUNCION_PY,
            **{f"static/js/m{n}.js": "export const a = 1;\n" for n in range(5)},
        },
    )

    assert REGISTRO.lenguaje_principal(tmp_path) == "javascript"
    assert adaptador_del_proyecto(tmp_path).lenguaje == "python"


@pytest.mark.parametrize(
    "archivos, nombre",
    [
        ({"src/suma.ts": "export const s = 1;\n", "tsconfig.json": "{}"}, "TypeScript"),
        ({"index.js": "module.exports = {};\n", "package.json": "{}"}, "JavaScript"),
    ],
)
def test_un_lenguaje_en_desarrollo_da_un_mensaje_claro(
    tmp_path, archivos, nombre, monkeypatch
):
    simular_node_en_desarrollo(monkeypatch)
    _escribir(tmp_path, archivos)

    with pytest.raises(LenguajeNoSoportado) as error:
        adaptador_del_proyecto(tmp_path)

    mensaje = str(error.value)
    assert f"aún no puede probar proyectos en {nombre}" in mensaje
    assert "Por ahora se admiten proyectos en Python" in mensaje


def test_sin_archivos_fuente_se_usa_el_lenguaje_de_los_contratos_anteriores(
    tmp_path,
) -> None:
    (tmp_path / "LEEME.txt").write_text("hola", encoding="utf-8")

    assert adaptador_del_proyecto(tmp_path).lenguaje == "python"


def test_todos_los_lenguajes_tienen_adaptador_completo() -> None:
    """EP-11: JavaScript y TypeScript se suman a Python y Java."""
    completos = {
        nombre
        for nombre in REGISTRO.lenguajes
        if REGISTRO.adaptador_para(nombre).completo
    }
    assert completos == {"python", "java", "javascript", "typescript"}


@pytest.mark.parametrize(
    "archivos, lenguaje",
    [
        ({"src/suma.ts": "export const s = 1;\n", "tsconfig.json": "{}"}, "typescript"),
        ({"index.js": "module.exports = {};\n", "package.json": "{}"}, "javascript"),
        ({"src/suma.ts": "export const s = 1;\n"}, "typescript"),
    ],
)
def test_un_proyecto_javascript_o_typescript_usa_su_adaptador(
    tmp_path, archivos, lenguaje
) -> None:
    """EP-11: la app y la corrida usan el adaptador Node con la imagen sin red."""
    _escribir(tmp_path, archivos)

    adaptador = adaptador_del_proyecto(tmp_path)

    assert adaptador.lenguaje == lenguaje
    assert adaptador.entorno_sandbox().imagen == "qagent-sandbox:node"
    assert "vitest" in " ".join(adaptador.comando_pruebas("src/suma.ts"))


def test_python_con_package_json_en_la_raiz_y_mas_javascript_es_javascript(
    tmp_path,
) -> None:
    """Con ``package.json`` en la raíz el JavaScript es del proyecto, no un ``static/``."""
    _escribir(
        tmp_path,
        {
            "scripts/util.py": FUNCION_PY,
            "package.json": "{}",
            **{f"src/m{n}.js": "export const a = 1;\n" for n in range(3)},
        },
    )

    assert adaptador_del_proyecto(tmp_path).lenguaje == "javascript"


def test_java_con_algo_de_typescript_sigue_siendo_java(tmp_path) -> None:
    _escribir(
        tmp_path,
        {
            "src/main/java/A.java": "class A {}\n",
            "pom.xml": "<project/>",
            **{f"web/m{n}.ts": "export const a = 1;\n" for n in range(3)},
        },
    )

    assert adaptador_del_proyecto(tmp_path).lenguaje == "java"


def test_proyecto_java_selecciona_adaptador_integrado(tmp_path) -> None:
    """El proyecto que antes se rechazaba entra ahora por el registro productivo."""
    _escribir(
        tmp_path, {"src/main/java/A.java": "class A {}\n", "pom.xml": "<project/>"}
    )
    adaptador = adaptador_del_proyecto(tmp_path)
    assert adaptador.lenguaje == "java"
    assert adaptador.completo is True
    assert adaptador.entorno_sandbox().imagen == "qagent-sandbox:java"
    assert "mvn" in " ".join(adaptador.comando_pruebas("src/main/java/A.java"))


# --- La corrida y la app con un lenguaje sin soporte --------------------------------


def test_la_corrida_de_un_lenguaje_en_desarrollo_termina_con_el_aviso(
    tmp_path, config, monkeypatch
) -> None:
    simular_node_en_desarrollo(monkeypatch)
    _escribir(tmp_path, {"src/suma.ts": "export const s = 1;\n"})
    eventos: list[dict] = []
    preparar = MagicMock()

    resumen = ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
        preparar_imagen=preparar,
    )

    assert resumen.estado == FALLO
    assert "TypeScript" in resumen.motivo
    preparar.assert_not_called()  # no se prepara Docker ni se llama a la IA
    assert not any(e.get("agente") == "planner" for e in eventos)


@pytest.fixture
def api(monkeypatch) -> DesktopAPI:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    puente = DesktopAPI()
    puente.set_window(MagicMock())
    puente.verificar_entorno = lambda: {  # type: ignore[method-assign]
        "listo": True,
        "mensaje": "Entorno listo",
        "problemas": [],
        "comprobaciones": [],
    }
    return puente


def test_la_app_no_inicia_un_proyecto_de_un_lenguaje_sin_soporte(
    api, tmp_path, monkeypatch
):
    simular_node_en_desarrollo(monkeypatch)
    _escribir(tmp_path, {"index.js": "module.exports = {};\n"})

    resultado = api.start_run(str(tmp_path), "deep")

    assert resultado["status"] == "lenguaje_no_soportado"
    assert "JavaScript" in resultado["mensaje"]
    api._window.evaluate_js.assert_not_called()


def test_la_interfaz_muestra_el_aviso_de_lenguaje_no_soportado() -> None:
    monitor = (
        Path(__file__).resolve().parents[2]
        / "src/qagent/frontend/componentes/monitor/monitor.js"
    ).read_text(encoding="utf-8")
    assert "r.status === 'lenguaje_no_soportado'" in monitor


# --- Regresión: archivos y huellas por adaptador ----------------------------------


def test_las_huellas_solo_recorren_los_archivos_fuente_de_un_adaptador_completo(
    tmp_path, monkeypatch
) -> None:
    from qagent.lenguajes import JavaScriptAdapter

    simular_node_en_desarrollo(monkeypatch)
    monkeypatch.setattr(JavaScriptAdapter, "huellas_disponibles", False)
    _escribir(
        tmp_path,
        {
            "calc.py": FUNCION_PY,
            "web/app.js": "export function duplicar(x) { return 2 * x; }\n",
            "notas.md": "def no_soy_codigo(): pass\n",
        },
    )

    huellas = regresion.huellas_de_objetivos(tmp_path)

    assert set(huellas) == {("calc.py", "duplicar")}


def test_la_regresion_corre_con_el_comando_del_adaptador(
    tmp_path, config, monkeypatch
) -> None:
    """Sin un doble de prueba, la regresión usa el comando y los lectores del adaptador."""
    from tests.orchestrator.test_issue168_contratos_versionados import (
        ejecutor_exitoso,
        mutador_vacio,
    )

    banco = Path(__file__).resolve().parents[2] / "bench" / "banco_mvp.py"
    (tmp_path / "banco_mvp.py").write_text(
        banco.read_text(encoding="utf-8"), encoding="utf-8"
    )
    from qagent.almacenamiento import AlmacenProyecto

    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        run_id=almacen.crear_run(tipos_prueba=["funcion"])["run_id"],
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor_exitoso,
        mutador=mutador_vacio,
    )
    llamadas: list[dict] = []

    def sandbox_real(imagen, comando, proyecto, tests, **opciones):
        llamadas.append({"comando": comando, **opciones})
        return ResultadoSandbox(0, "1 passed", "", duracion_s=0.01)

    monkeypatch.setattr(regresion, "ejecutar_comando_pruebas", sandbox_real)

    resumen = ejecutar_corrida(
        tmp_path,
        "reg",
        config,
        None,
        simulado=True,
        run_id=almacen.crear_run(tipos_prueba=["funcion"])["run_id"],
        preparar_imagen=lambda _ruta: "imagen-prueba",
    )

    assert resumen.estado == "fin"
    assert llamadas
    for llamada in llamadas:
        assert "--cov=banco_mvp" in llamada["comando"]
        assert llamada["archivo_informe"] == "junit.xml"
        assert llamada["variables"] == {"COVERAGE_FILE": "/out/.coverage"}
        assert llamada["limites"] == config.sandbox

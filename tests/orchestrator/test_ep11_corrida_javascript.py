"""EP-11: un proyecto JavaScript o TypeScript corre por la misma corrida que usa la app.

Las pruebas de #176 a #179 arman los agentes a mano; esta pasa por
``ejecutar_corrida`` (el camino de «Iniciar» en la app), que elige el adaptador con
el registro. Sin Docker ni red: la IA y el sandbox se simulan.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.llm.fake import FakeLLMClient
from qagent.orchestrator import corrida
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.storage.exportar_informe import exportar_informe
from qagent.storage.vista_ejecucion import vista_ejecucion
from tests.lenguajes.test_banco_js import BANCO, GRABACIONES
from tests.orchestrator.test_issue168_contratos_versionados import (
    ejecutor_exitoso,
    mutador_vacio,
)


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


@pytest.fixture
def proyecto_ts(tmp_path: Path) -> Path:
    """Las funciones TypeScript del banco en un proyecto con ``tsconfig.json``."""
    raiz = tmp_path / "banco_ts"
    (raiz / "src").mkdir(parents=True)
    for nombre in ("precios.ts", "texto.ts"):
        shutil.copy(BANCO / "src" / nombre, raiz / "src" / nombre)
    (raiz / "tsconfig.json").write_text("{}", encoding="utf-8")
    return raiz


@pytest.fixture
def ia_con_grabaciones(monkeypatch):
    """El Planner simulado propone los casos grabados del banco JS/TS."""
    monkeypatch.setattr(
        corrida,
        "crear_cliente",
        lambda precio, claves, simulado=True: FakeLLMClient(
            modelo=precio.modelo, grabaciones=GRABACIONES
        ),
    )


def test_la_corrida_de_un_proyecto_typescript_usa_vitest_en_la_imagen_node(
    proyecto_ts: Path, config, ia_con_grabaciones
) -> None:
    almacen = AlmacenProyecto(proyecto_ts)
    almacen.inicializar()
    imagenes: list[str] = []
    eventos: list[dict] = []

    def ejecutor(imagen, proyecto, tests, modulo):
        imagenes.append(imagen)
        archivos = sorted(p.name for p in Path(tests).rglob("*") if p.is_file())
        assert any(a.endswith(".test.ts") for a in archivos), archivos
        return ejecutor_exitoso(imagen, proyecto, tests, modulo)

    def preparar(ruta):
        return "qagent-sandbox:node-prueba"

    resumen = ejecutar_corrida(
        proyecto_ts,
        "deep",
        config,
        None,
        simulado=True,
        run_id=almacen.crear_run(tipos_prueba=["funcion"])["run_id"],
        preparar_imagen=preparar,
        ejecutor=ejecutor,
        mutador=mutador_vacio,
        al_evento=eventos.append,
    )

    assert resumen.estado == "fin", resumen.motivo
    assert resumen.total_procesados > 0
    assert resumen.aceptadas > 0
    assert imagenes and set(imagenes) == {"qagent-sandbox:node-prueba"}
    assert any(e.get("agente") == "generator" for e in eventos)


def test_la_corrida_prepara_la_imagen_desde_qagent_sandbox_node(
    proyecto_ts: Path, config, ia_con_grabaciones, monkeypatch
) -> None:
    """Sin un ``preparar_imagen`` propio, la base es la imagen Node sin red."""
    bases: list[str] = []

    def preparar_imagen(ruta, *, imagen_base, **_):
        bases.append(imagen_base)
        raise RuntimeError("sin Docker en esta prueba")

    monkeypatch.setattr(corrida, "_preparar_imagen", preparar_imagen)
    almacen = AlmacenProyecto(proyecto_ts)
    almacen.inicializar()

    ejecutar_corrida(
        proyecto_ts,
        "deep",
        config,
        None,
        simulado=True,
        run_id=almacen.crear_run(tipos_prueba=["funcion"])["run_id"],
        mutador=mutador_vacio,
    )

    assert bases == ["qagent-sandbox:node"]


def test_la_corrida_avisa_los_archivos_javascript_que_no_prueba(
    proyecto_ts: Path, config, ia_con_grabaciones
) -> None:
    """Con .ts y un .js, se prueba TypeScript y el Monitor avisa el .js omitido."""
    (proyecto_ts / "vite.config.js").write_text("export default {};\n", "utf-8")
    almacen = AlmacenProyecto(proyecto_ts)
    almacen.inicializar()
    eventos: list[dict] = []

    ejecutar_corrida(
        proyecto_ts,
        "deep",
        config,
        None,
        simulado=True,
        run_id=almacen.crear_run(tipos_prueba=["funcion"])["run_id"],
        preparar_imagen=lambda _ruta: "qagent-sandbox:node-prueba",
        ejecutor=ejecutor_exitoso,
        mutador=mutador_vacio,
        al_evento=eventos.append,
    )

    avisos = [e["mensaje"] for e in eventos if e.get("tipo") == "aviso"]
    assert any(
        m.startswith("1 archivo de JavaScript no se prueba en esta corrida")
        for m in avisos
    ), avisos


def test_el_informe_avisa_los_archivos_que_no_prueba(
    proyecto_ts: Path, config, ia_con_grabaciones, tmp_path: Path
) -> None:
    """results.json, la pantalla Resultados y el informe exportado dicen qué quedó
    fuera, sin cambiar los conteos de objetivos."""
    (proyecto_ts / "vite.config.js").write_text("export default {};\n", "utf-8")
    almacen = AlmacenProyecto(proyecto_ts)
    almacen.inicializar()

    resumen = ejecutar_corrida(
        proyecto_ts,
        "deep",
        config,
        None,
        simulado=True,
        run_id=almacen.crear_run(tipos_prueba=["funcion"])["run_id"],
        preparar_imagen=lambda _ruta: "qagent-sandbox:node-prueba",
        ejecutor=ejecutor_exitoso,
        mutador=mutador_vacio,
    )

    results = json.loads(
        (Path(resumen.carpeta) / "results.json").read_text(encoding="utf-8")
    )
    assert contracts.es_valido("run_log", results)
    fuera = results["fuera_de_la_corrida"]
    assert [(f["lenguaje"], f["archivos"], f["rutas"]) for f in fuera] == [
        ("javascript", 1, ["vite.config.js"])
    ]
    mensaje = fuera[0]["mensaje"]
    assert mensaje.startswith("1 archivo de JavaScript no se prueba en esta corrida")
    # Es un aviso: los .js no entran en los objetivos ni en los omitidos.
    assert results["total_seleccionados"] == resumen.total_seleccionados
    assert all(o["modulo"] != "vite.config.js" for o in results.get("omitidos", []))

    assert vista_ejecucion(results)["fuera_de_la_corrida"] == fuera

    for formato in ("md", "html", "json"):
        exportado = exportar_informe(
            proyecto_ts,
            run_id=results["run_id"],
            formato=formato,
            carpeta_destino=tmp_path / "informes",
        )
        texto = Path(exportado["ruta"]).read_text(encoding="utf-8")
        assert "1 archivo de JavaScript no se prueba en esta corrida" in texto, formato
    pdf = exportar_informe(
        proyecto_ts,
        run_id=results["run_id"],
        formato="pdf",
        carpeta_destino=tmp_path / "informes",
    )
    assert (
        b"1 archivo de JavaScript no se prueba en esta corrida"
        in Path(pdf["ruta"]).read_bytes()
    )


def test_el_informe_de_una_corrida_sin_archivos_fuera_no_avisa(
    proyecto_ts: Path, config, ia_con_grabaciones, tmp_path: Path
) -> None:
    almacen = AlmacenProyecto(proyecto_ts)
    almacen.inicializar()

    resumen = ejecutar_corrida(
        proyecto_ts,
        "deep",
        config,
        None,
        simulado=True,
        run_id=almacen.crear_run(tipos_prueba=["funcion"])["run_id"],
        preparar_imagen=lambda _ruta: "qagent-sandbox:node-prueba",
        ejecutor=ejecutor_exitoso,
        mutador=mutador_vacio,
    )

    results = json.loads(
        (Path(resumen.carpeta) / "results.json").read_text(encoding="utf-8")
    )
    assert "fuera_de_la_corrida" not in results
    assert vista_ejecucion(results)["fuera_de_la_corrida"] == []
    exportado = exportar_informe(
        proyecto_ts,
        run_id=results["run_id"],
        formato="md",
        carpeta_destino=tmp_path / "informes",
    )
    assert "**Aviso:**" not in Path(exportado["ruta"]).read_text(encoding="utf-8")


def test_los_avisos_ignoran_entradas_sin_mensaje() -> None:
    """Markdown, HTML y PDF toman el texto del mismo lugar."""
    from qagent.storage.exportar_informe import avisos_fuera_de_la_corrida

    datos = {
        "fuera_de_la_corrida": [
            {"mensaje": "2 archivos de TypeScript no se prueban en esta corrida."},
            {"sin_mensaje": True},
            "no es un dict",
        ]
    }
    assert avisos_fuera_de_la_corrida(datos) == [
        "2 archivos de TypeScript no se prueban en esta corrida."
    ]
    assert avisos_fuera_de_la_corrida({}) == []


def test_el_schema_rechaza_un_aviso_mal_formado() -> None:
    base = {
        "lenguaje": "javascript",
        "nombre": "JavaScript",
        "archivos": 1,
        "rutas": ["a.js"],
        "mensaje": "1 archivo de JavaScript no se prueba en esta corrida.",
    }
    esquema = contracts.cargar_schema("run_log")["properties"]["fuera_de_la_corrida"]
    from jsonschema import Draft202012Validator

    validador = Draft202012Validator(esquema)
    assert validador.is_valid([base])
    assert not validador.is_valid([{**base, "archivos": 0}])
    assert not validador.is_valid([{**base, "lenguaje": "ruby"}])
    assert not validador.is_valid([{**base, "extra": 1}])

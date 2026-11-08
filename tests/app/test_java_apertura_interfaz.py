"""La entrada del escritorio admite Java y conserva los objetivos de la corrida."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from qagent.app import desktop
from qagent.lenguajes import JavaAdapter, LenguajeNoSoportado, adaptador_del_proyecto
from qagent.proyectos.proyecto_local import inspeccionar_carpeta
from qagent.proyectos.seleccion import filtrar_modulos
from tests.lenguajes.en_desarrollo import simular_node_en_desarrollo

BANCO = Path(__file__).resolve().parents[2] / "bench_java"


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> desktop.DesktopAPI:
    """Aísla recientes para no alterar los proyectos guardados del usuario."""
    monkeypatch.setattr(
        desktop.recientes, "ruta_por_defecto", lambda: tmp_path / "recientes.json"
    )
    return desktop.DesktopAPI()


def test_banco_java_se_abre_previsualiza_y_reabre(
    tmp_path: Path, api: desktop.DesktopAPI
) -> None:
    """Reproduce la apertura rechazada y conserva los seis objetivos Java reales."""
    proyecto = tmp_path / "banco-java"
    shutil.copytree(BANCO, proyecto, ignore=shutil.ignore_patterns("target", ".qagent"))
    inspeccion = api.inspeccionar_carpeta(str(proyecto))
    assert inspeccion["ok"] is True
    assert inspeccion["lenguaje"] == "java"
    assert inspeccion["nombre_lenguaje"] == "Java"
    assert inspeccion["cantidad_fuentes"] == 2
    assert inspeccion["cantidad_py"] == 0
    assert inspeccion["extensiones"] == [".java"]
    assert api.abrir_proyecto(str(proyecto))["ok"] is True
    assert api.abrir_reciente(str(proyecto))["lenguaje"] == "java"
    vista = api.obtener_vista_previa(str(proyecto))
    assert vista["ok"] is True
    assert vista["lenguaje"] == "java"
    assert vista["framework_pruebas"] == "junit5"
    assert vista["resumen"]["total_funciones_publicas"] == 6
    seleccion = [
        {
            "ruta": m["ruta"],
            "funciones": [f["nombre"] for f in m["funciones"]],
            "endpoints": [],
        }
        for m in vista["modulos"]
    ]
    filtrados = filtrar_modulos(JavaAdapter().analizar(proyecto)["modulos"], seleccion)
    assert sum(len(m["funciones"]) for m in filtrados) == 6
    assert {f["nombre"] for m in filtrados for f in m["funciones"]} == {
        "BancoCorrecto.sumarPrecios",
        "BancoCorrecto.aplicarDescuento",
        "BancoCorrecto.esMayorDeEdad",
        "BancoDefectuoso.calcularPromedio",
        "BancoDefectuoso.calcularEnvio",
        "BancoDefectuoso.calcularTotalConImpuesto",
    }


def test_spring_llega_a_seleccion_como_endpoints(
    tmp_path: Path, api: desktop.DesktopAPI
) -> None:
    """La vista del controlador conserva rutas HTTP, sin duplicarlas como unitarias."""
    proyecto = tmp_path / "spring"
    shutil.copytree(BANCO / "src/test/resources/spring", proyecto)
    assert api.abrir_proyecto(str(proyecto))["ok"] is True
    vista = api.obtener_vista_previa(str(proyecto))
    assert vista["resumen"]["total_endpoints"] == 3
    controlador = next(m for m in vista["modulos"] if m["endpoints"])
    assert controlador["funciones"] == []
    objetivos = [e["objetivo"] for e in controlador["endpoints"]]
    assert set(objetivos) == {
        "POST /api/articulos",
        "POST /api/articulos-defecto",
        "POST /api/sin-contrato",
    }
    seleccion = [{"ruta": controlador["ruta"], "funciones": [], "endpoints": objetivos}]
    filtrados = filtrar_modulos(JavaAdapter().analizar(proyecto)["modulos"], seleccion)
    assert [e["objetivo"] for e in filtrados[0]["endpoints"]] == objetivos


@pytest.mark.parametrize(
    "relativa",
    [
        "src/test/java/Ejemplo.java",
        "target/Ejemplo.java",
        "build/Ejemplo.java",
        ".qagent/Ejemplo.java",
    ],
)
def test_solo_pruebas_o_generados_no_habilitan_apertura(
    tmp_path: Path, relativa: str
) -> None:
    """No ofrece una carpeta que el analizador Java dejaría sin fuentes."""
    archivo = tmp_path / relativa
    archivo.parent.mkdir(parents=True)
    archivo.write_text("public class Ejemplo {}", encoding="utf-8")
    assert inspeccionar_carpeta(tmp_path)["ok"] is False


def test_java_con_sintaxis_invalida_se_muestra_como_error(
    tmp_path: Path, api: desktop.DesktopAPI
) -> None:
    """Un archivo roto no se confunde con un lenguaje incompatible."""
    (tmp_path / "Roto.java").write_text(
        "public class Roto { public int f( }", encoding="utf-8"
    )
    assert api.inspeccionar_carpeta(str(tmp_path))["ok"] is True
    vista = api.obtener_vista_previa(str(tmp_path))
    assert vista["resumen"]["total_errores"] == 1
    assert vista["errores"][0]["ruta"] == "Roto.java"


@pytest.mark.parametrize(
    "extension,lenguaje", [("js", "JavaScript"), ("ts", "TypeScript")]
)
def test_lenguaje_incompleto_se_abre_solo_para_e2e(
    tmp_path: Path,
    api: desktop.DesktopAPI,
    extension: str,
    lenguaje: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un lenguaje en desarrollo accede a E2E sin prometer la corrida de agentes."""
    simular_node_en_desarrollo(monkeypatch)
    (tmp_path / f"main.{extension}").write_text(
        "export function f() { return 1; }", encoding="utf-8"
    )
    inspeccion = api.inspeccionar_carpeta(str(tmp_path))
    assert inspeccion["ok"] is True
    assert inspeccion["nombre_lenguaje"] == lenguaje
    assert inspeccion["solo_e2e"] is True
    vista = api.obtener_vista_previa(str(tmp_path))
    assert vista["ok"] is True
    assert vista["solo_e2e"] is True
    with pytest.raises(LenguajeNoSoportado):
        adaptador_del_proyecto(tmp_path)

"""JaCoCo XML #182: cobertura parcial y por método sin ejecutar Java ni Docker."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_cobertura import (
    LIMITE_XML_JACOCO,
    CoberturaJacocoInvalida,
    cobertura_de_metodo,
    interpretar_jacoco,
)

RUTA = "src/main/java/ejemplo/Banco.java"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/java/jacoco-controlado.xml"


def test_informe_real_del_promedio_obtenido_en_docker() -> None:
    """El XML real conserva cobertura del método aun cuando su aserción falló."""
    ruta = FIXTURE.with_name("jacoco-sandbox-promedio.xml")
    cobertura = interpretar_jacoco(ruta.read_text(encoding="utf-8"))
    modulo = "src/main/java/org/qagent/bench/BancoDefectuoso.java"
    assert cobertura_de_metodo(
        cobertura, modulo, "BancoDefectuoso.calcularPromedio"
    ) == {"lineas": 100.0, "ramas": 100.0}


def _xml() -> str:
    """Carga el ejemplo sintético, identificado como tal en su comentario XML."""
    return FIXTURE.read_text(encoding="utf-8")


def test_archivo_y_metodos_conservan_contadores_distintos(tmp_path: Path) -> None:
    """La cobertura del archivo es 80 %, la del método calculado 66.67 % y 50 % de ramas."""
    (tmp_path / "jacoco.xml").write_text(_xml(), encoding="utf-8")
    cobertura = JavaAdapter().leer_cobertura(tmp_path)
    assert cobertura["totals"]["percent_covered"] == 80.0
    assert cobertura["totals"]["num_branches"] == 2
    datos = cobertura["files"][RUTA]
    assert datos["executed_lines"] == [5, 10, 12, 20]
    assert datos["missing_lines"] == [11]
    assert datos["executed_branches"] == [10]
    assert datos["missing_branches"] == [10]
    assert cobertura_de_metodo(cobertura, RUTA, "Banco.calcular") == {
        "lineas": 66.67,
        "ramas": 50.0,
    }
    assert cobertura_de_metodo(cobertura, RUTA, "Banco.constante") == {
        "lineas": 100.0,
        "ramas": None,
    }
    assert cobertura_de_metodo(cobertura, RUTA, "Banco.noExiste") is None
    assert json.loads(json.dumps(cobertura)) == cobertura


def test_linea_parcial_cuenta_como_ejecutada() -> None:
    """La línea 10 tiene instrucciones pendientes, pero no se cuenta también como faltante."""
    datos = interpretar_jacoco(_xml())["files"][RUTA]
    assert 10 in datos["executed_lines"]
    assert 10 not in datos["missing_lines"]
    assert set(datos["executed_lines"]).isdisjoint(datos["missing_lines"])


def test_dos_metodos_en_una_linea_conservan_su_cobertura() -> None:
    """No se suma dos veces una línea ni se le atribuye al otro método su ejecución."""
    xml = """<report name="mismo renglón"><package name="">
      <class name="Banco" sourcefilename="Banco.java">
        <method name="uno" desc="()I" line="1"><counter type="LINE" missed="0" covered="1"/></method>
        <method name="dos" desc="()I" line="1"><counter type="LINE" missed="1" covered="0"/></method>
      </class><sourcefile name="Banco.java"><line nr="1" ci="2" mi="2"/></sourcefile>
    </package></report>"""
    cobertura = interpretar_jacoco(xml)
    assert cobertura["totals"]["num_statements"] == 1
    assert (
        cobertura_de_metodo(cobertura, "src/main/java/Banco.java", "Banco.uno")[
            "lineas"
        ]
        == 100.0
    )
    assert (
        cobertura_de_metodo(cobertura, "src/main/java/Banco.java", "Banco.dos")[
            "lineas"
        ]
        == 0.0
    )


def test_sobrecargas_no_se_eligen_por_nombre() -> None:
    """Conserva descriptores y evita atribuir a f() la cobertura de f(int)."""
    xml = _xml().replace(
        '<method name="constante" desc="()I" line="20">',
        '<method name="calcular" desc="()I" line="20">',
    )
    cobertura = interpretar_jacoco(xml)
    assert cobertura_de_metodo(cobertura, RUTA, "Banco.calcular") is None
    assert cobertura_de_metodo(cobertura, RUTA, "Banco.calcular(I)I")["lineas"] == 66.67
    assert cobertura_de_metodo(cobertura, RUTA, "Banco.calcular()I")["lineas"] == 100.0


def test_dtd_estandar_no_se_descarga(monkeypatch) -> None:
    """El parser acepta la declaración oficial después de retirarla, sin resolverla."""
    import urllib.request

    def prohibida(*args, **kwargs):
        raise AssertionError("No debe acceder a red para leer la cobertura")

    monkeypatch.setattr(urllib.request, "urlopen", prohibida)
    assert interpretar_jacoco(_xml())["totals"]["percent_covered"] == 80.0


def test_grupos_con_fuentes_distintas_no_pierden_archivos() -> None:
    """Un grupo del reporte conserva su paquete sin modificar la ruta estándar de fuente."""
    xml = (
        _xml()
        .replace(
            '<package name="ejemplo">', '<group name="modulo"><package name="ejemplo">'
        )
        .replace("</package>", "</package></group>")
    )
    assert RUTA in interpretar_jacoco(xml)["files"]


@pytest.mark.parametrize(
    ("original", "nuevo"),
    [
        ('nr="10"', 'nr="0"'),
        ('mi="4"', 'mi="-1"'),
        ('cb="1"', 'cb="1.5"'),
        ('mb="1"', 'mb="999999999"'),
        ('name="ejemplo"', 'name="../ejemplo"'),
        ('name="Banco.java"', 'name="../Banco.java"'),
        ('sourcefilename="Banco.java"', 'sourcefilename="C:\\Banco.java"'),
        ('name="ejemplo/Banco"', 'name="otro/Banco"'),
        ('type="LINE" missed="1" covered="4"', 'type="LINE" missed="0" covered="4"'),
        ('type="LINE" missed="1" covered="2"', 'type="LINE" missed="-1" covered="2"'),
    ],
)
def test_datos_invalidos_no_generan_porcentajes(original: str, nuevo: str) -> None:
    """Rutas, líneas, contadores y cantidades abusivas se rechazan sin fabricar métricas."""
    with pytest.raises(CoberturaJacocoInvalida):
        interpretar_jacoco(_xml().replace(original, nuevo))


@pytest.mark.parametrize(
    "xml",
    [
        "",
        "<report>",
        "<otra/>",
        '<!DOCTYPE report SYSTEM "https://example.com/report.dtd"><report/>',
        '<!DOCTYPE report [<!ENTITY secreto "x">]><report/>',
    ],
)
def test_xml_invalido_o_dtd_distinta_se_rechaza(xml: str) -> None:
    """No acepta XML mal formado, entidades ni referencias externas distintas de la estándar."""
    with pytest.raises(CoberturaJacocoInvalida):
        interpretar_jacoco(xml)


@pytest.mark.parametrize(
    "elemento", ["line", "sourcefile", "method", "class", "counter"]
)
def test_duplicados_se_rechazan(elemento: str) -> None:
    """No cuenta dos veces líneas, archivos, métodos, clases ni métricas repetidas."""
    raiz = ET.fromstring(_xml())
    nodo = raiz.find(".//" + elemento)
    padre = next(p for p in raiz.iter() if nodo in list(p))
    padre.append(ET.fromstring(ET.tostring(nodo)))
    with pytest.raises(CoberturaJacocoInvalida):
        interpretar_jacoco(ET.tostring(raiz, encoding="unicode"))


def test_informe_sin_lineas_y_archivo_faltante_no_es_cero(tmp_path: Path) -> None:
    """Ausencia de datos de depuración produce None, sin inventar 0 % ni 100 %."""
    assert JavaAdapter().leer_cobertura(tmp_path) is None
    assert (
        interpretar_jacoco(
            '<report name="sin debug"><package name="p"><class name="p/Banco"/></package></report>'
        )
        is None
    )
    (tmp_path / "jacoco.xml").write_text("no es XML", encoding="utf-8")
    assert JavaAdapter().leer_cobertura(tmp_path) is None
    (tmp_path / "jacoco.xml").write_bytes(b"\xff")
    assert JavaAdapter().leer_cobertura(tmp_path) is None


def test_xml_excesivo_no_se_lee(tmp_path: Path) -> None:
    """Se limita tanto la lectura del archivo como la entrada directa de texto XML."""
    xml = "<report>" + " " * LIMITE_XML_JACOCO + "</report>"
    with pytest.raises(CoberturaJacocoInvalida):
        interpretar_jacoco(xml)
    (tmp_path / "jacoco.xml").write_text(xml, encoding="utf-8")
    assert JavaAdapter().leer_cobertura(tmp_path) is None


def test_metodo_sin_contador_de_lineas_no_inventa_porcentaje() -> None:
    """Un método sin datos de línea no produce lineas=None dentro de un porcentaje."""
    cobertura = {
        "files": {
            RUTA: {
                "functions": {
                    "Banco.f": {
                        "summary": {
                            "percent_covered": None,
                            "percent_branches_covered": None,
                        }
                    }
                }
            }
        }
    }
    assert cobertura_de_metodo(cobertura, RUTA, "Banco.f") is None


def test_formato_comun_permite_recortar_por_rango(tmp_path: Path) -> None:
    """El cálculo compartido del Reviewer puede filtrar líneas y ramas por método."""
    from qagent.agents.reviewer import ReviewerAgent
    from qagent.llm import TokenTracker

    cobertura = interpretar_jacoco(_xml())
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "qagent-sandbox:java", es_simulado=True
    )
    resultado = reviewer._cobertura_de_funcion(cobertura, RUTA, (10, 12))
    assert resultado == {"lineas": 66.67, "ramas": 50.0}

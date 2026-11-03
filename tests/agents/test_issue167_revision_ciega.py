"""Revisión a ciegas de las explicaciones (SPK #167), sobre una medición con IA simulada."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

CARPETA = Path(__file__).resolve().parents[2] / "bench_explicador"


@pytest.fixture(scope="module")
def revision():
    spec = importlib.util.spec_from_file_location(
        "revision_ciega", CARPETA / "revision_ciega.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    yield modulo
    sys.modules.pop(spec.name, None)


@pytest.fixture
def resultados(revision, tmp_path, monkeypatch) -> Path:
    """Una medición simulada: 6 hallazgos, plantilla y 2 modelos, 1 repetición."""
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    salida = tmp_path / "resultados"
    revision.medir.main(
        [
            "--salida",
            str(salida),
            "--config-local",
            str(tmp_path / "no-existe.toml"),
            "--repeticiones",
            "1",
        ]
    )
    return salida


def _leer(ruta: Path) -> list[dict[str, str]]:
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=";"))


def _escribir(ruta: Path, filas: list[dict[str, str]]) -> None:
    with open(ruta, "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]), delimiter=";")
        escritor.writeheader()
        escritor.writerows(filas)


def _llenar(revision, ruta: Path, clave: dict, preferida_ia: bool) -> None:
    """IA con 3 en todo y plantilla con 2; preferida la IA o «igual»."""
    filas = _leer(ruta)
    for fila in filas:
        par = clave["pares"][fila["par"]]
        for lado in ("A", "B"):
            puntaje = "2" if par[lado]["origen"] == "plantilla" else "3"
            for criterio in revision.CRITERIOS:
                fila[f"{lado}_{criterio}"] = puntaje
        ia = "A" if par["A"]["origen"] == "ia" else "B"
        fila["preferida"] = ia if preferida_ia else "Igual"
    _escribir(ruta, filas)


def test_exporta_una_planilla_por_persona_sin_decir_que_es_cada_explicacion(
    revision, resultados
) -> None:
    carpeta = revision.exportar(resultados, ["ana", "rodrigo"], semilla=7)

    ana = _leer(carpeta / "planilla-ana.csv")
    assert ana == _leer(carpeta / "planilla-rodrigo.csv")
    assert len(ana) == 12  # 6 hallazgos × 2 modelos
    assert list(ana[0]) == revision.columnas()
    texto = (carpeta / "planilla-ana.csv").read_text(encoding="utf-8-sig")
    metricas = json.loads((resultados / "metricas.json").read_text(encoding="utf-8"))
    for fila in metricas["por_modelo"]:
        if fila["origen"] == "ia":
            assert fila["modelo"] not in texto
    assert '"origen"' not in texto and "modelo" not in texto


def test_cada_par_es_la_plantilla_contra_un_modelo_en_orden_al_azar(
    revision, resultados
) -> None:
    carpeta = revision.exportar(resultados, ["ana", "rodrigo"], semilla=7)
    clave = json.loads((carpeta / "clave.json").read_text(encoding="utf-8"))

    lados = [
        (par["A"]["origen"], par["B"]["origen"]) for par in clave["pares"].values()
    ]
    assert all(sorted(lado) == ["ia", "plantilla"] for lado in lados)
    assert {lado[0] for lado in lados} == {"ia", "plantilla"}  # no siempre A
    assert clave["semilla"] == 7


def test_la_misma_semilla_da_las_mismas_planillas(
    revision, resultados, tmp_path
) -> None:
    primera = _leer(
        revision.exportar(resultados, ["ana"], semilla=3) / "planilla-ana.csv"
    )
    segunda = _leer(
        revision.exportar(resultados, ["ana"], semilla=3) / "planilla-ana.csv"
    )

    assert primera == segunda


def test_los_hechos_traen_todos_los_intentos(revision, resultados) -> None:
    carpeta = revision.exportar(resultados, ["ana"], semilla=7)
    filas = _leer(carpeta / "planilla-ana.csv")

    envio = next(f for f in filas if f["objetivo"] == "calcular_envio")
    assert "Intento 1: retry, error_test: ImportError" in envio["hechos"]
    assert "Intento 3: stalled, error_test, debilitó la prueba" in envio["hechos"]
    assert "Assertion Laundering detectado: sí" in envio["hechos"]
    assert "/work/" not in envio["hechos"]


def test_puntuar_revela_y_promedia_las_planillas(revision, resultados) -> None:
    carpeta = revision.exportar(resultados, ["ana", "rodrigo"], semilla=7)
    clave = json.loads((carpeta / "clave.json").read_text(encoding="utf-8"))
    _llenar(revision, carpeta / "planilla-ana.csv", clave, preferida_ia=True)
    _llenar(revision, carpeta / "planilla-rodrigo.csv", clave, preferida_ia=False)

    datos = revision.puntuar(resultados)

    assert datos["revisores"] == ["ana", "rodrigo"]
    assert datos["por_origen"]["plantilla"]["general"] == 2.0
    modelos = [m for m in datos["por_origen"] if m != "plantilla"]
    assert len(modelos) == 2
    for modelo in modelos:
        assert datos["por_origen"][modelo]["general"] == 3.0
        assert datos["por_origen"][modelo]["unos_en_riesgo"] == {
            "no_inventa": 0,
            "no_contradice": 0,
        }
        assert datos["preferencias"][modelo] == {"ia": 6, "igual": 6}
    assert datos["acuerdo_preferida"] == {"coinciden": 0, "pares": 12, "pct": 0.0}
    resultado = (carpeta / "resultado.md").read_text(encoding="utf-8")
    assert "| plantilla | 2.00" in resultado
    assert json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))


def test_una_planilla_incompleta_dice_que_falta(revision, resultados) -> None:
    carpeta = revision.exportar(resultados, ["ana", "rodrigo"], semilla=7)
    clave = json.loads((carpeta / "clave.json").read_text(encoding="utf-8"))
    _llenar(revision, carpeta / "planilla-ana.csv", clave, preferida_ia=True)
    _llenar(revision, carpeta / "planilla-rodrigo.csv", clave, preferida_ia=True)
    filas = _leer(carpeta / "planilla-rodrigo.csv")
    filas[0]["A_correcta"] = "5"
    filas[1]["preferida"] = ""
    _escribir(carpeta / "planilla-rodrigo.csv", filas)

    with pytest.raises(SystemExit) as error:
        revision.puntuar(resultados)

    mensaje = str(error.value)
    assert "planilla-rodrigo.csv" in mensaje
    assert f"{filas[0]['par']} A_correcta" in mensaje
    assert f"{filas[1]['par']} preferida" in mensaje


def test_hacen_falta_dos_planillas(revision, resultados) -> None:
    carpeta = revision.exportar(resultados, ["ana"], semilla=7)
    clave = json.loads((carpeta / "clave.json").read_text(encoding="utf-8"))
    _llenar(revision, carpeta / "planilla-ana.csv", clave, preferida_ia=True)

    with pytest.raises(SystemExit, match="al menos 2 planillas"):
        revision.puntuar(resultados)


def test_las_explicaciones_de_ia_descartadas_no_entran_y_quedan_anotadas(
    revision,
) -> None:
    explicacion = {"resumen": "r", "que_se_esperaba": "e", "que_paso": "p"}
    base = {"objetivo": "f", "tipo": "bug_detectado", "repeticion": 1, "motivo": None}
    respuestas = [
        {
            **base,
            "origen": "plantilla",
            "modelo": "plantilla",
            "explicacion": explicacion,
        },
        {**base, "origen": "ia", "modelo": "m1", "explicacion": explicacion},
        {
            **base,
            "origen": "ia",
            "modelo": "m2",
            "explicacion": None,
            "motivo": "la respuesta no es JSON",
        },
    ]

    filas, clave, omitidas = revision.armar_pares(respuestas, {"f": "hechos"}, 1, 0)

    assert len(filas) == len(clave) == 1
    assert omitidas == ["m2 / f: la respuesta no es JSON"]
    assert "Qué hacer: —" in filas[0]["A"]


@pytest.mark.parametrize(
    ("feedback", "linea"),
    [
        (
            (
                "collected 1 item\nFAILED ../tests/test_generado.py::test_a - "
                "assert 20.0 == 80.0\n=== 1 failed in 0.1s ==="
            ),
            "assert 20.0 == 80.0",
        ),
        (
            "tabla\n\n🔴 ASSERTION LAUNDERING DETECTADO:\n  ⚠ Rigor debilitado: eq → rango",
            "Rigor debilitado: eq → rango",
        ),
        ("Error de entorno: falta pytest.", "Error de entorno: falta pytest."),
        (None, "sin detalle"),
    ],
)
def test_resume_el_error_de_cada_intento(revision, feedback, linea) -> None:
    assert revision.linea_de_error(feedback) == linea

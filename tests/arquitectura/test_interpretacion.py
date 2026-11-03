from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent.arquitectura.ejecucion import _interpretar
from qagent.lenguajes.base import PlanArquitectura
from qagent.sandbox.modelos import ResultadoSandbox

REGLA = {
    "id": "capas",
    "tipo": "dependencia_prohibida",
    "nombre": "Capas",
    "origen": "usuario",
    "confirmada": True,
    "desde": "dominio",
    "hacia": "interfaz",
}


def plan(herramienta: str = "herramienta") -> PlanArquitectura:
    return PlanArquitectura(REGLA, herramienta, ["tool"], {})


def test_cumplimiento_y_violacion_python_con_linea_real(tmp_path: Path) -> None:
    archivo = tmp_path / "app/dominio/servicio.py"
    archivo.parent.mkdir(parents=True)
    archivo.write_text("from app.interfaz import Vista\n", encoding="utf-8")
    ok = _interpretar(plan(), "python", tmp_path, ResultadoSandbox(0, "", ""))
    fallo = _interpretar(
        plan(),
        "python",
        tmp_path,
        ResultadoSandbox(1, "app.dominio -> app.interfaz\n", ""),
    )
    assert ok["estado"] == "cumple"
    assert fallo["estado"] == "incumple"
    assert fallo["hallazgos"][0]["archivo"] == "app/dominio/servicio.py"
    assert fallo["hallazgos"][0]["linea"] == 1


def test_node_varias_violaciones_y_resultado_malformado(tmp_path: Path) -> None:
    salida = json.dumps(
        {
            "modules": [],
            "summary": {
                "violations": [
                    {"from": "src/dominio/a.ts", "to": "src/interfaz/b.ts"},
                    {"from": "src/dominio/c.ts", "to": "src/interfaz/d.ts"},
                ]
            },
        }
    )
    resultado = _interpretar(
        plan(), "typescript", tmp_path, ResultadoSandbox(2, salida, "")
    )
    assert resultado["estado"] == "incumple"
    assert len(resultado["hallazgos"]) == 2
    ilegible = _interpretar(
        plan(), "javascript", tmp_path, ResultadoSandbox(2, "no-json", "")
    )
    assert ilegible["estado"] == "sin_veredicto"


@pytest.mark.parametrize(
    "resultado,motivo",
    [
        (ResultadoSandbox(137, "", "", timed_out=True), "tiempo"),
        (ResultadoSandbox(137, "", "", oom_killed=True), "memoria"),
        (ResultadoSandbox(2, "", "herramienta ausente"), "código 2"),
    ],
)
def test_errores_de_infraestructura_son_sin_veredicto(
    tmp_path: Path, resultado: ResultadoSandbox, motivo: str
) -> None:
    dato = _interpretar(plan(), "python", tmp_path, resultado)
    assert dato["estado"] == "sin_veredicto"
    assert motivo in dato["motivo_sin_veredicto"]


def test_java_no_inventa_linea_y_recupera_linea_si_existe(tmp_path: Path) -> None:
    sin = _interpretar(
        plan(),
        "java",
        tmp_path,
        ResultadoSandbox(1, "QAGENT_STATUS\tincumple\nviolación", ""),
    )
    con = _interpretar(
        plan(),
        "java",
        tmp_path,
        ResultadoSandbox(1, "QAGENT_STATUS\tincumple\n(Servicio.java:12)", ""),
    )
    assert sin["hallazgos"][0]["linea"] is None
    assert con["hallazgos"][0] == {
        "desde": "dominio",
        "hacia": "interfaz",
        "archivo": "Servicio.java",
        "linea": 12,
    }


def test_python_error_de_sintaxis_queda_sin_veredicto(tmp_path: Path) -> None:
    resultado = _interpretar(
        plan(),
        "python",
        tmp_path,
        ResultadoSandbox(
            1,
            "Syntax error in /work/proyecto/app/a.py, line 2: <unavailable>\n",
            "",
        ),
    )

    assert resultado["estado"] == "sin_veredicto"
    assert resultado["hallazgos"] == []

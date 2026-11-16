"""Preparación Java desde la aplicación con inferencia configurable."""

import pytest

from qagent.config import carga
from qagent.proyectos.vista_previa import generar_vista_previa
from tests.lenguajes.test_issue292_java_inferencia import escribir


@pytest.mark.parametrize("activa", [True, False])
def test_previa_java_ofrece_inferencia_y_respeta_configuracion(
    tmp_path, monkeypatch, activa
):
    escribir(
        tmp_path, "pom.xml", "<project><modelVersion>4.0.0</modelVersion></project>"
    )
    escribir(
        tmp_path,
        "src/main/java/demo/Calc.java",
        "package demo; public class Calc { public static int doble(int n) { return n*2; } /** Devuelve tres. */ public static int tres() { return 3; } }",
    )
    local = tmp_path / "config.local.toml"
    local.write_text(
        f"[inferencia]\nactiva = {str(activa).lower()}\n", encoding="utf-8"
    )
    monkeypatch.setattr(carga, "RUTA_CONFIG_LOCAL", local)
    vista = generar_vista_previa(tmp_path)
    assert vista["ok"], vista
    assert vista["lenguaje"] == "java"
    assert vista["inferencia_activa"] is activa
    funciones = {f["nombre"]: f for m in vista["modulos"] for f in m["funciones"]}
    assert funciones["Calc.doble"]["inferible"] is True
    assert bool(funciones["Calc.doble"]["aviso_inferencia"]) is activa
    assert funciones["Calc.tres"]["inferible"] is False
    assert funciones["Calc.tres"]["aviso_inferencia"] is None

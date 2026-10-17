"""Integracion estructural del perfil Regresion en las pantallas de HU-25."""

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"


def leer(relativa: str) -> str:
    return (FRONTEND / relativa).read_text(encoding="utf-8")


def test_configuracion_habilita_regresion_por_pruebas_aprobadas():
    perfiles = leer("js/estado.js")
    previa = leer("componentes/vista-previa/vista-previa.js")
    config = leer("componentes/config-pruebas/config-pruebas.js")
    assert "k:'reg'" in perfiles
    assert "tiene_pruebas_aprobadas" in previa
    assert "sin IA" in config


def test_ejecucion_y_reporte_muestran_requiere_corrida_nueva():
    for archivo in (
        "componentes/ejecucion/ejecucion.js",
        "componentes/informe/informe.js",
    ):
        contenido = leer(archivo)
        assert "requiere_corrida_nueva" in contenido
        assert "REQUIERE CORRIDA NUEVA" in contenido


def test_historial_distingue_regresion_sin_ia():
    historial = leer("componentes/historial/historial.js")
    assert "h.estrategia_prueba === 'regresion'" in historial
    assert "— (sin IA)" in historial
    assert "requieren corrida nueva" in historial

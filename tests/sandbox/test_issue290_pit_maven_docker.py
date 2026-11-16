"""PIT real en reactor Maven: módulos auxiliares sin mutaciones ni tests propios."""

import pytest

from qagent.config import cargar_configuracion
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.sandbox.pit_ejecucion import ejecutar_pit

pytest_plugins = ("tests.lenguajes.test_issue290_maven_ejecucion",)

pytestmark = pytest.mark.docker


def test_pit_mutacion_solo_de_metodo_seleccionado_en_reactor(
    cliente_docker, reactor, monkeypatch
):
    """Compila core pero PIT solo informa mutantes de Banco.sumar en api."""
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta la imagen base Java.")
    raiz, pruebas = reactor
    originales = {
        p.relative_to(raiz): p.read_bytes() for p in raiz.rglob("*") if p.is_file()
    }
    config = cargar_configuracion(simulado=True).config
    informes = []
    from qagent.sandbox import pit_ejecucion

    salidas = []
    ejecutar_real = pit_ejecucion.ejecutar_en_sandbox

    def capturar(*args, **kwargs):
        resultado_real = ejecutar_real(*args, **kwargs)
        salidas.append(resultado_real.stdout + resultado_real.stderr)
        return resultado_real

    monkeypatch.setattr(pit_ejecucion, "ejecutar_en_sandbox", capturar)
    resultado = ejecutar_pit(
        IMAGEN_JAVA,
        raiz,
        pruebas,
        "api/src/main/java/demo/Banco.java",
        ["Banco.sumar"],
        limites=config.limites_sandbox("java"),
        cliente=cliente_docker,
        al_informe=informes.append,
    )
    assert set(resultado.funciones) == {"Banco.sumar"}
    funcion = resultado.funciones["Banco.sumar"]
    if funcion.estado == "error":
        print(
            "\n".join(salidas)
            .encode("ascii", errors="backslashreplace")
            .decode("ascii")
        )
    assert funcion.estado != "error", (funcion.mensaje, salidas)
    assert informes, (funcion.estado, funcion.mensaje, resultado.salida)
    assert "demo.Banco" in informes[0]
    assert "demo.Core" not in informes[0]
    assert all(
        (raiz / p).read_bytes() == contenido for p, contenido in originales.items()
    )
    print(
        f"Maven PIT: api/Banco.sumar; estado={funcion.estado}; core sin mutaciones; originales intactos; sin red; 0 tokens"
    )

"""Issue 142: el entorno aislado instala las librerías del sistema que faltan.

Caso real: APP-RF declara opencv-python; `import cv2` fallaba en el sandbox por
`libGL.so.1` y el Generator terminaba simulando `cv2`. Docker se simula aquí; la
prueba con Docker real está en test_issue142_librerias_docker.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import BuildError, ImageNotFound

from qagent.sandbox import librerias, verificar_entorno
from qagent.sandbox.librerias import (
    AVISO_COMPROBANDO,
    AVISO_INFORME_ILEGIBLE,
    RUTA_INFORME,
    TABLA_LIBRERIAS,
    EntornoVerificado,
    asegurar_librerias_sistema,
    describir_faltantes,
    dockerfile_final,
    etiqueta_final,
    leer_informe,
    paquete_del_sistema,
    paquetes_para,
)
from qagent.sandbox.modelos import IMAGEN_BASE

DEPENDENCIAS = "qagent-sandbox:req-0123456789ab"
LIBGL = {
    "libreria": "libGL.so.1",
    "modulos": ["cv2"],
    "paquetes_python": ["opencv-python"],
}


def _informe(*faltantes: dict) -> bytes:
    return json.dumps(
        {"version": 1, "revisados": 5, "faltantes": list(faltantes)}
    ).encode()


# --- Tabla ------------------------------------------------------------------------


def test_la_tabla_usa_los_nombres_de_debian_13() -> None:
    """En trixie varios paquetes llevan `t64`; los nombres viejos ya no existen."""
    assert TABLA_LIBRERIAS["libGL.so.1"] == "libgl1"
    assert TABLA_LIBRERIAS["libglib-2.0.so.0"] == "libglib2.0-0t64"
    assert "libglib2.0-0" not in TABLA_LIBRERIAS.values()
    assert "libasound2" not in TABLA_LIBRERIAS.values()


@pytest.mark.parametrize(
    ("libreria", "paquete"),
    [
        ("libGL.so.1", "libgl1"),
        ("libGL.so", "libgl1"),  # otra versión de la misma librería
        ("libsndfile.so.1", "libsndfile1"),
        ("libdesconocida.so.3", None),
    ],
)
def test_paquete_del_sistema(libreria: str, paquete: str | None) -> None:
    assert paquete_del_sistema(libreria) == paquete


def test_paquetes_para_ignora_las_desconocidas() -> None:
    faltantes = [LIBGL, {"libreria": "libgthread-2.0.so.0"}, {"libreria": "libx.so"}]

    assert paquetes_para(faltantes) == {"libgl1", "libglib2.0-0t64"}


# --- Dockerfile y etiqueta --------------------------------------------------------


def test_sin_paquetes_solo_comprueba_el_entorno() -> None:
    texto = dockerfile_final(DEPENDENCIAS, set())

    assert texto.startswith(f"FROM {DEPENDENCIAS}\nUSER root\n")
    assert "apt-get" not in texto
    assert f"RUN python /opt/qagent/verificar_entorno.py {RUTA_INFORME}" in texto
    assert texto.rstrip().endswith("USER sandbox")


def test_con_paquetes_los_instala_uno_por_uno_sin_cortar_la_construccion() -> None:
    texto = dockerfile_final(DEPENDENCIAS, {"libglib2.0-0t64", "libgl1"})

    assert "apt-get update" in texto
    assert "for p in libgl1 libglib2.0-0t64; do" in texto  # orden estable
    assert '|| echo "QAgent: no se pudo instalar $p"' in texto
    assert "rm -rf /var/lib/apt/lists/*" in texto
    assert texto.index("apt-get") < texto.index("verificar_entorno.py")


def test_la_etiqueta_final_depende_de_la_tabla(monkeypatch) -> None:
    antes = etiqueta_final(DEPENDENCIAS)
    assert antes.startswith(f"{DEPENDENCIAS}-sis")

    monkeypatch.setitem(librerias.TABLA_LIBRERIAS, "libnueva.so.1", "libnueva1")

    assert librerias._version() != librerias.VERSION_LIBRERIAS


# --- Construcción -----------------------------------------------------------------


def _cliente(informes: list[bytes], final_existe: bool = False) -> MagicMock:
    """Cliente simulado: guarda cada Dockerfile construido y devuelve los informes vía logs()."""
    cliente = MagicMock()
    cliente.dockerfiles = []
    cola_informes = list(informes)

    def obtener(etiqueta):
        if etiqueta.endswith(librerias.VERSION_LIBRERIAS) and not final_existe:
            raise ImageNotFound(etiqueta)
        return MagicMock()

    def construir(path=None, **kwargs):
        cliente.dockerfiles.append((Path(path) / "Dockerfile").read_text("utf-8"))
        assert (Path(path) / "verificar_entorno.py").is_file()

    def correr(_imagen, _comando, **kwargs):
        assert kwargs.get("detach") is True
        assert kwargs.get("network_mode") == "none"
        contenedor = MagicMock()
        informe = cola_informes.pop(0) if cola_informes else b"{}"
        contenedor.logs.return_value = informe
        return contenedor

    cliente.images.get.side_effect = obtener
    cliente.images.build.side_effect = construir
    cliente.containers.run.side_effect = correr
    return cliente


def test_sin_requirements_no_se_comprueba_nada() -> None:
    cliente = MagicMock()

    assert asegurar_librerias_sistema(IMAGEN_BASE, cliente) == EntornoVerificado(
        IMAGEN_BASE
    )
    cliente.images.build.assert_not_called()


def test_si_falta_libgl_se_instala_libgl1_y_se_vuelve_a_comprobar() -> None:
    cliente = _cliente([_informe(LIBGL), _informe(), _informe()])
    avances: list[str] = []

    entorno = asegurar_librerias_sistema(DEPENDENCIAS, cliente, avances.append)

    assert entorno == EntornoVerificado(etiqueta_final(DEPENDENCIAS), [])
    primera, segunda = cliente.dockerfiles
    assert "apt-get" not in primera
    assert "for p in libgl1; do" in segunda
    assert avances[0] == AVISO_COMPROBANDO
    assert any("libgl1" in a for a in avances)
    # El informe se lee sin red y con detach=True.
    assert cliente.containers.run.call_args.kwargs["network_mode"] == "none"
    assert cliente.containers.run.call_args.kwargs["detach"] is True


def test_si_no_falta_nada_se_construye_una_sola_vez() -> None:
    cliente = _cliente([_informe(), _informe()])

    entorno = asegurar_librerias_sistema(DEPENDENCIAS, cliente)

    assert entorno.faltantes == []
    assert len(cliente.dockerfiles) == 1


def test_una_libreria_desconocida_se_devuelve_con_su_mensaje() -> None:
    raro = {
        "libreria": "libraro.so.2",
        "modulos": ["raro"],
        "paquetes_python": ["raro"],
    }
    cliente = _cliente([_informe(raro), _informe(raro)])

    entorno = asegurar_librerias_sistema(DEPENDENCIAS, cliente)

    [faltante] = entorno.faltantes
    assert faltante["paquete_sistema"] is None
    assert "QAgent no sabe qué paquete del sistema la instala" in faltante["mensaje"]
    assert len(cliente.dockerfiles) == 1  # nada que instalar: no hay otra ronda


def test_las_rondas_tienen_un_limite() -> None:
    sigue = {"libreria": "libGL.so.1", "modulos": ["cv2"], "paquetes_python": []}
    otra = {"libreria": "libSM.so.6", "modulos": ["cv2"], "paquetes_python": []}
    tercera = {"libreria": "libXext.so.6", "modulos": ["cv2"], "paquetes_python": []}
    cliente = _cliente(
        [_informe(sigue), _informe(otra), _informe(tercera), _informe(tercera)]
    )

    asegurar_librerias_sistema(DEPENDENCIAS, cliente)

    assert len(cliente.dockerfiles) == librerias.MAX_RONDAS


def test_si_la_imagen_final_existe_solo_se_lee_su_informe() -> None:
    cliente = _cliente([_informe(LIBGL)], final_existe=True)

    entorno = asegurar_librerias_sistema(DEPENDENCIAS, cliente)

    cliente.images.build.assert_not_called()
    [faltante] = entorno.faltantes
    assert faltante["paquete_sistema"] == "libgl1"
    assert "no se pudo instalar el paquete libgl1" in faltante["mensaje"]
    assert "opencv-python-headless" in faltante["mensaje"]


def test_si_no_se_puede_construir_la_corrida_sigue_con_las_dependencias() -> None:
    cliente = _cliente([])
    cliente.images.build.side_effect = BuildError("falló", [])

    entorno = asegurar_librerias_sistema(DEPENDENCIAS, cliente)

    assert entorno == EntornoVerificado(DEPENDENCIAS)


def test_si_falla_la_ronda_con_paquetes_queda_la_anterior() -> None:
    cliente = _cliente([_informe(LIBGL), _informe(LIBGL)])
    construidas = []

    def construir(path, **_):
        construidas.append(path)
        if len(construidas) == 2:
            raise BuildError("apt sin red", [])

    cliente.images.build.side_effect = construir

    entorno = asegurar_librerias_sistema(DEPENDENCIAS, cliente)

    assert entorno.imagen == etiqueta_final(DEPENDENCIAS)
    assert [f["libreria"] for f in entorno.faltantes] == ["libGL.so.1"]


@pytest.mark.parametrize(
    "salida", [b"no es json", b"[1, 2]", b"", None, RuntimeError("caido")]
)
def test_un_informe_ilegible_no_frena_la_corrida(salida) -> None:
    cliente = MagicMock()
    contenedor = MagicMock()
    if isinstance(salida, Exception):
        cliente.containers.run.side_effect = salida
    else:
        contenedor.logs.return_value = salida
        cliente.containers.run.return_value = contenedor

    avances: list[str] = []
    assert leer_informe(cliente, "imagen", avanzar=avances.append) == {"faltantes": []}
    assert AVISO_INFORME_ILEGIBLE in avances
    if not isinstance(salida, Exception):
        contenedor.wait.assert_called_once()
        contenedor.logs.assert_called_once_with(stdout=True, stderr=False)
        contenedor.remove.assert_called_once_with(force=True)


def test_leer_informe_quita_el_contenedor_tambien_si_falla() -> None:
    cliente = MagicMock()
    contenedor = MagicMock()
    contenedor.wait.side_effect = RuntimeError("error en wait")
    cliente.containers.run.return_value = contenedor

    resultado = leer_informe(cliente, "imagen")

    assert resultado == {"faltantes": []}
    contenedor.remove.assert_called_once_with(force=True)


def test_cliente_simulado_detecta_faltantes_y_pide_paquetes_por_logs() -> None:
    """Con un cliente simulado que devuelve el informe por logs(),
    se detectan los faltantes y se piden los paquetes correctos.
    """
    cliente = _cliente([_informe(LIBGL), _informe()])
    entorno = asegurar_librerias_sistema(DEPENDENCIAS, cliente)

    assert entorno.imagen == etiqueta_final(DEPENDENCIAS)
    assert entorno.faltantes == []
    assert len(cliente.dockerfiles) == 2
    assert "for p in libgl1; do" in cliente.dockerfiles[1]


def test_no_quedan_containers_run_sin_detach_en_src() -> None:
    """Verifica que toda invocación a containers.run en src/ use detach=True."""
    import ast

    raiz_src = Path(__file__).resolve().parents[2] / "src" / "qagent"
    llamadas_sin_detach = []
    for py_file in raiz_src.rglob("*.py"):
        arbol = ast.parse(py_file.read_text("utf-8"), filename=str(py_file))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call):
                func = nodo.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "run"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "containers"
                ):
                    tiene_detach = any(
                        kw.arg == "detach" and getattr(kw.value, "value", None) is True
                        for kw in nodo.keywords
                    )
                    if not tiene_detach:
                        llamadas_sin_detach.append(f"{py_file.name}:{nodo.lineno}")

    assert not llamadas_sin_detach, (
        f"Se encontraron containers.run sin detach=True: {llamadas_sin_detach}"
    )


def test_describir_faltantes_ignora_entradas_sin_libreria() -> None:
    assert describir_faltantes([{"modulos": ["x"]}]) == []


# --- Script que corre dentro de la imagen -----------------------------------------


def test_el_script_anota_solo_las_librerias_del_sistema(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        verificar_entorno.metadata,
        "packages_distributions",
        lambda: {
            "cv2": ["opencv-python"],
            "roto": ["roto"],
            "bien": ["bien"],
            "tests": ["algo"],
            "_privado": ["algo"],
        },
    )
    importados = []

    def importar(nombre):
        importados.append(nombre)
        if nombre == "cv2":
            raise ImportError(
                "libGL.so.1: cannot open shared object file: No such file or directory"
            )
        if nombre == "roto":
            raise ValueError("otro problema que no es de librerías")

    monkeypatch.setattr(verificar_entorno.importlib, "import_module", importar)
    destino = tmp_path / "entorno.json"

    assert verificar_entorno.main(["script", str(destino)]) == 0

    informe = json.loads(destino.read_text("utf-8"))
    assert sorted(importados) == ["bien", "cv2", "roto"]  # ni tests ni privados
    assert informe["revisados"] == 3
    assert informe["faltantes"] == [
        {
            "libreria": "libGL.so.1",
            "modulos": ["cv2"],
            "paquetes_python": ["opencv-python"],
        }
    ]

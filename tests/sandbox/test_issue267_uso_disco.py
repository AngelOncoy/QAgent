"""#267 Capa 3: cuánto ocupa QAgent en Docker y «Liberar espacio», con Docker simulado.

Lo importante es lo que NO se borra: las imágenes base, lo reciente (la corrida en curso) y
lo que no es de QAgent. La caché de compilación solo se poda si se pide.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from docker.errors import APIError

from qagent.config.disco import BYTES_POR_GB, LimitesDisco
from qagent.sandbox import uso_disco
from qagent.sandbox.modelos import ETIQUETA_CONSTRUCCION, IMAGEN_BASE, IMAGEN_NODE

AHORA = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc).timestamp()
DIA = 24 * 60 * 60
GB = BYTES_POR_GB
CAPAS_BASE = ["sha256:b1"]
LIMITES = LimitesDisco(
    tope_imagenes_derivadas_gb=10, cache_antiguedad_dias=7, espacio_libre_minimo_gb=10
)
FILTRO_CONSTRUCCION = [f"{k}={v}" for k, v in ETIQUETA_CONSTRUCCION.items()]


def _fecha(segundos: float) -> str:
    base = datetime.fromtimestamp(segundos, tz=timezone.utc)
    return base.strftime("%Y-%m-%dT%H:%M:%S.123456789Z")


def _base(etiqueta: str = IMAGEN_BASE, gb: float = 1.0) -> MagicMock:
    imagen = MagicMock(tags=[etiqueta])
    imagen.attrs = {
        "Created": int(AHORA - 300 * DIA),
        "Size": int(gb * GB),
        "RootFS": {"Layers": CAPAS_BASE},
    }
    return imagen


def _derivada(nombre: str, hace_dias: float, propio_gb: float) -> MagicMock:
    imagen = MagicMock(tags=[f"qagent-sandbox:{nombre}"])
    imagen.attrs = {
        "Created": int(AHORA - hace_dias * DIA),
        "Size": int((1.0 + propio_gb) * GB),
        "RootFS": {"Layers": [*CAPAS_BASE, f"sha256:{nombre}"]},
    }
    return imagen


def _capa(gb: float, hace_s: float) -> MagicMock:
    capa = MagicMock(tags=[])
    capa.attrs = {"Created": int(AHORA - hace_s), "Size": int(gb * GB)}
    return capa


def _contenedor(hace_s: float, estado: str = "exited") -> MagicMock:
    contenedor = MagicMock(status=estado)
    contenedor.attrs = {"Created": _fecha(AHORA - hace_s)}
    return contenedor


def _cliente(derivadas=(), capas=(), sandbox=(), construccion=(), cache_gb=0.0):
    """Docker simulado: las imágenes borradas dejan de aparecer en el listado."""
    imagenes = [_base(), _base(IMAGEN_NODE, 0.5), *derivadas]
    quitadas: set[str] = set()
    cliente = MagicMock()
    cliente.images.remove.side_effect = quitadas.add

    def listar(**opciones):
        if opciones.get("filters", {}).get("dangling"):
            return list(capas)
        return [i for i in imagenes if not quitadas.intersection(i.tags)]

    cliente.images.list.side_effect = listar

    def contenedores(**opciones):
        if opciones["filters"]["label"] == FILTRO_CONSTRUCCION:
            return list(construccion)
        return list(sandbox)

    cliente.containers.list.side_effect = contenedores
    cliente.images.prune.return_value = {
        "ImagesDeleted": [{"Deleted": "x"} for _ in capas],
        "SpaceReclaimed": sum(c.attrs["Size"] for c in capas),
    }
    cliente.api.prune_builds.return_value = {"SpaceReclaimed": int(cache_gb * GB)}
    cliente.df.return_value = {"BuildCache": [{"Size": int(cache_gb * GB)}]}
    return cliente


def _medir(cliente, tmp_path: Path, libre_gb: float | None = 50) -> dict:
    return uso_disco.medir_uso(
        cliente,
        tmp_path / "usos.json",
        LIMITES,
        libre=lambda: None if libre_gb is None else int(libre_gb * GB),
        ahora=AHORA,
    )


# ---------- medir_uso ----------


def test_mide_bases_derivadas_restos_cache_y_espacio_libre(tmp_path):
    cliente = _cliente(
        derivadas=[
            _derivada("req-aaaaaaaaaaaa", 20, 4),
            _derivada("node-bbbbbbbbbbbb", 10, 2),
        ],
        capas=[_capa(1.5, hace_s=3 * DIA), _capa(9, hace_s=60)],  # la 2.ª es reciente
        sandbox=[_contenedor(30)],
        construccion=[_contenedor(2 * 3600), _contenedor(60)],
        cache_gb=1.2,
    )

    uso = _medir(cliente, tmp_path)

    assert uso["ok"] is True
    assert uso["bases"] == {"cantidad": 2, "bytes": int(1.5 * GB)}
    assert uso["derivadas"] == {
        "cantidad": 2,
        "bytes": 6 * GB,  # solo lo propio: la base compartida no se cuenta
        "tope_bytes": 10 * GB,
    }
    assert uso["restos"] == {
        "contenedores": 2,  # el de construcción reciente no cuenta: puede estar en uso
        "capas": 1,
        "bytes": int(1.5 * GB),
    }
    assert uso["cache"] == {"bytes": int(1.2 * GB), "dias": 7}
    assert uso["total_bytes"] == int(1.5 * GB) + 6 * GB + int(1.5 * GB)
    assert uso["libre_bytes"] == 50 * GB
    assert uso["minimo_bytes"] == 10 * GB


def test_sin_docker_igual_dice_cuanto_espacio_libre_queda(tmp_path):
    cliente = MagicMock()
    cliente.images.list.side_effect = ConnectionError("Docker cerrado")

    uso = _medir(cliente, tmp_path, libre_gb=7)

    assert uso["ok"] is False
    assert "Docker no responde" in uso["mensaje"]
    assert uso["libre_bytes"] == 7 * GB


def test_si_la_cache_no_se_puede_leer_se_dice_que_no_se_sabe(tmp_path):
    cliente = _cliente()
    cliente.df.side_effect = APIError("sin BuildKit")

    assert _medir(cliente, tmp_path)["cache"]["bytes"] is None


def test_si_no_se_puede_medir_el_disco_libre_es_none(tmp_path):
    assert _medir(_cliente(), tmp_path, libre_gb=None)["libre_bytes"] is None


# ---------- liberar_espacio ----------


def _liberar(cliente, tmp_path: Path, incluir_cache=False, usos=None) -> dict:
    ruta = tmp_path / "usos.json"
    if usos is not None:
        ruta.write_text(json.dumps(usos), encoding="utf-8")
    return uso_disco.liberar_espacio(
        cliente, ruta, LIMITES, incluir_cache=incluir_cache, ahora=AHORA
    )


def _borradas(cliente) -> list[str]:
    return [c.args[0] for c in cliente.images.remove.call_args_list]


def test_borra_todas_las_derivadas_y_conserva_las_bases(tmp_path):
    cliente = _cliente(
        derivadas=[
            _derivada("req-aaaaaaaaaaaa", 20, 4),
            _derivada("java-bbbbbbbbbbbb", 3, 2),
            _derivada("browser-cccccccccccc", 40, 1),
        ]
    )

    resultado = _liberar(cliente, tmp_path)

    assert resultado["ok"] is True
    assert sorted(resultado["imagenes"]) == [
        "qagent-sandbox:browser-cccccccccccc",
        "qagent-sandbox:java-bbbbbbbbbbbb",
        "qagent-sandbox:req-aaaaaaaaaaaa",
    ]
    assert IMAGEN_BASE not in _borradas(cliente)
    assert IMAGEN_NODE not in _borradas(cliente)
    assert resultado["liberado_bytes"] == 7 * GB
    assert "7,0 GB" in resultado["mensaje"]
    assert "compactar" in resultado["mensaje"]


def test_no_borra_la_imagen_de_una_corrida_en_curso(tmp_path):
    en_curso = _derivada("req-aaaaaaaaaaaa", 90, 4)
    vieja = _derivada("req-bbbbbbbbbbbb", 90, 4)
    cliente = _cliente(derivadas=[en_curso, vieja])

    resultado = _liberar(
        cliente, tmp_path, usos={"qagent-sandbox:req-aaaaaaaaaaaa": AHORA - 120}
    )

    assert resultado["imagenes"] == ["qagent-sandbox:req-bbbbbbbbbbbb"]
    assert resultado["liberado_bytes"] == 4 * GB


def test_una_imagen_que_docker_no_deja_borrar_se_salta(tmp_path):
    cliente = _cliente(
        derivadas=[
            _derivada("req-aaaaaaaaaaaa", 20, 4),
            _derivada("req-bbbbbbbbbbbb", 30, 4),
        ]
    )
    cliente.images.remove.side_effect = [APIError("en uso"), None]

    resultado = _liberar(cliente, tmp_path)

    assert len(resultado["imagenes"]) == 1
    assert resultado["liberado_bytes"] == 4 * GB


def test_borra_los_restos_de_construcciones_y_corridas_cortadas(tmp_path):
    sandbox = _contenedor(30)
    cortado = _contenedor(2 * 3600)
    reciente = _contenedor(60, estado="running")
    cliente = _cliente(
        capas=[_capa(2, hace_s=3 * DIA)],
        sandbox=[sandbox],
        construccion=[cortado, reciente],
    )

    resultado = _liberar(cliente, tmp_path)

    assert resultado["contenedores"] == 1 and resultado["construcciones"] == 1
    assert resultado["capas"] == 1
    sandbox.remove.assert_called_once_with(force=True)
    cortado.remove.assert_called_once_with(force=True)
    reciente.remove.assert_not_called()  # puede ser el build de otra ventana
    assert resultado["liberado_bytes"] == 2 * GB


def test_la_cache_de_compilacion_no_se_toca_sin_pedirlo(tmp_path):
    cliente = _cliente(cache_gb=3)

    resultado = _liberar(cliente, tmp_path)

    cliente.api.prune_builds.assert_not_called()
    assert resultado["cache_bytes"] == 0


def test_con_cache_pedida_se_poda_por_la_antiguedad_de_config(tmp_path):
    cliente = _cliente(cache_gb=3)

    resultado = _liberar(cliente, tmp_path, incluir_cache=True)

    cliente.api.prune_builds.assert_called_once_with(filters={"until": "168h"})
    assert resultado["cache_bytes"] == 3 * GB
    assert resultado["liberado_bytes"] == 3 * GB


def test_sin_antiguedad_de_cache_en_config_no_se_poda_aunque_se_pida(tmp_path):
    cliente = _cliente(cache_gb=3)

    uso_disco.liberar_espacio(
        cliente,
        tmp_path / "usos.json",
        LimitesDisco(),
        incluir_cache=True,
        ahora=AHORA,
    )

    cliente.api.prune_builds.assert_not_called()


def test_olvida_el_uso_de_las_imagenes_borradas(tmp_path):
    cliente = _cliente(derivadas=[_derivada("req-aaaaaaaaaaaa", 20, 4)])

    _liberar(
        cliente,
        tmp_path,
        usos={
            "qagent-sandbox:req-aaaaaaaaaaaa": AHORA - 5 * DIA,
            "qagent-sandbox:req-otra": AHORA - 1,
        },
    )

    guardado = json.loads((tmp_path / "usos.json").read_text(encoding="utf-8"))
    assert list(guardado) == ["qagent-sandbox:req-otra"]


def test_sin_nada_que_borrar_lo_dice_en_lenguaje_simple(tmp_path):
    resultado = _liberar(_cliente(), tmp_path)

    assert resultado["ok"] is True
    assert resultado["mensaje"].startswith("No había nada que borrar")


def test_nunca_borra_nada_sin_filtro_de_qagent(tmp_path):
    cliente = _cliente(derivadas=[_derivada("req-aaaaaaaaaaaa", 20, 4)])

    _liberar(cliente, tmp_path, incluir_cache=True)

    cliente.containers.prune.assert_not_called()
    cliente.volumes.prune.assert_not_called()
    cliente.networks.prune.assert_not_called()
    assert cliente.images.prune.call_args.kwargs["filters"]["label"]
    cliente.images.list.assert_called_with(name="qagent-sandbox")
    for llamada in cliente.containers.list.call_args_list:
        assert llamada.kwargs["filters"]["label"]


def test_si_docker_falla_a_mitad_no_lanza(tmp_path):
    cliente = MagicMock()
    cliente.containers.list.side_effect = ConnectionError("Docker cerrado")
    cliente.images.list.side_effect = ConnectionError("Docker cerrado")
    cliente.images.prune.side_effect = ConnectionError("Docker cerrado")

    resultado = _liberar(cliente, tmp_path)

    assert resultado["ok"] is True  # cada paso falla por separado
    assert resultado["liberado_bytes"] == 0


def test_si_docker_no_responde_al_conectar_devuelve_un_mensaje(monkeypatch, tmp_path):
    def falla(**_):
        raise ConnectionError("Docker cerrado")

    monkeypatch.setattr("docker.from_env", falla)

    assert uso_disco.liberar_espacio(None, tmp_path / "u.json", LIMITES)["ok"] is False
    assert uso_disco.medir_uso(None, tmp_path / "u.json", LIMITES)["ok"] is False

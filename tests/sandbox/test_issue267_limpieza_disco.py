"""#267 Capa 1: la limpieza borra lo que QAgent deja a medias y acota el espacio que ocupa.

Docker se simula con un cliente falso: ninguna prueba necesita Docker Desktop ni red. Lo que
se verifica es sobre todo lo que NO se borra (la base, lo ajeno, lo reciente, lo protegido).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import APIError

from qagent.config.disco import BYTES_POR_GB, LimitesDisco
from qagent.sandbox import imagen as modulo_imagen
from qagent.sandbox import limpieza
from qagent.sandbox.modelos import (
    ETIQUETA_CONSTRUCCION,
    IMAGEN_BASE,
    IMAGEN_JAVA,
    IMAGEN_NODE,
)

AHORA = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc).timestamp()
DIA = 24 * 60 * 60
GB = BYTES_POR_GB
BASE_CAPAS = ["sha256:b1", "sha256:b2"]
FILTRO_CONSTRUCCION = [f"{k}={v}" for k, v in ETIQUETA_CONSTRUCCION.items()]


def _fecha(segundos: float) -> str:
    base = datetime.fromtimestamp(segundos, tz=timezone.utc)
    return base.strftime("%Y-%m-%dT%H:%M:%S.123456789Z")


def _contenedor(hace_s: float, estado: str = "exited") -> MagicMock:
    contenedor = MagicMock(status=estado)
    contenedor.attrs = {"Created": _fecha(AHORA - hace_s)}
    return contenedor


def _derivada(
    nombre: str, hace_dias: float, propio_gb: float, base_gb: float = 1.0
) -> MagicMock:
    """Imagen derivada: su `Size` incluye la base, como en Docker."""
    imagen = MagicMock(tags=[f"qagent-sandbox:{nombre}"])
    imagen.attrs = {
        "Created": int(AHORA - hace_dias * DIA),  # el listado de Docker da segundos
        "Size": int((base_gb + propio_gb) * GB),
        "RootFS": {"Layers": [*BASE_CAPAS, f"sha256:{nombre}"]},
    }
    return imagen


def _base(base_gb: float = 1.0) -> MagicMock:
    imagen = MagicMock(tags=[IMAGEN_BASE])
    imagen.attrs = {
        "Created": int(AHORA - 400 * DIA),
        "Size": int(base_gb * GB),
        "RootFS": {"Layers": BASE_CAPAS},
    }
    return imagen


def _cliente(imagenes=(), contenedores=()) -> MagicMock:
    cliente = MagicMock()
    cliente.images.list.return_value = list(imagenes)
    cliente.containers.list.return_value = list(contenedores)
    cliente.images.prune.return_value = {"ImagesDeleted": None, "SpaceReclaimed": 0}
    cliente.api.prune_builds.return_value = {"SpaceReclaimed": 0}
    return cliente


def _borradas(cliente: MagicMock) -> list[str]:
    return [llamada.args[0] for llamada in cliente.images.remove.call_args_list]


# ---------- etiqueta propia en toda construcción ----------


def test_toda_construccion_lleva_la_etiqueta_de_construccion():
    assert modulo_imagen._opciones_build(None, None)["labels"] == ETIQUETA_CONSTRUCCION


def test_la_etiqueta_de_construccion_se_suma_a_la_receta_sin_perderla():
    opciones = modulo_imagen._opciones_build({"X": "1"}, {"qagent.receta": "abc"})

    assert opciones["labels"] == {**ETIQUETA_CONSTRUCCION, "qagent.receta": "abc"}
    assert opciones["buildargs"] == {"X": "1"}


@pytest.mark.parametrize("con_avance", [False, True])
def test_el_build_real_recibe_la_etiqueta(tmp_path: Path, con_avance: bool):
    cliente = MagicMock()
    cliente.api.build.return_value = iter([{"stream": "ok\n"}])

    modulo_imagen._construir(
        cliente,
        tmp_path,
        "qagent-sandbox:req-aaaaaaaaaaaa",
        "falló",
        (lambda texto: None) if con_avance else None,
    )

    llamada = cliente.api.build if con_avance else cliente.images.build
    assert llamada.call_args.kwargs["labels"] == ETIQUETA_CONSTRUCCION


# ---------- contenedores de construcción huérfanos ----------


def test_busca_los_contenedores_de_construccion_solo_por_su_etiqueta():
    cliente = _cliente()

    limpieza.eliminar_contenedores_construccion(cliente, ahora=AHORA)

    cliente.containers.list.assert_called_once_with(
        all=True, filters={"label": FILTRO_CONSTRUCCION}
    )


def test_borra_el_contenedor_de_una_construccion_cortada_aunque_siga_corriendo():
    """El `pip install` de 6,26 GB de #267 quedó así: sin terminar y sin dueño."""
    cortado = _contenedor(limpieza.ANTIGUEDAD_CONSTRUCCION_S + 60, estado="running")
    detenido = _contenedor(limpieza.ANTIGUEDAD_CONSTRUCCION_S + 60, estado="exited")
    cliente = _cliente(contenedores=[cortado, detenido])

    assert limpieza.eliminar_contenedores_construccion(cliente, ahora=AHORA) == 2
    cortado.remove.assert_called_once_with(force=True)
    detenido.remove.assert_called_once_with(force=True)


def test_no_borra_el_contenedor_de_una_construccion_reciente():
    """Puede ser el build que otra ventana de QAgent está haciendo ahora mismo."""
    reciente = _contenedor(120, estado="running")
    sin_fecha = MagicMock(status="exited", attrs={})
    cliente = _cliente(contenedores=[reciente, sin_fecha])

    assert limpieza.eliminar_contenedores_construccion(cliente, ahora=AHORA) == 0
    reciente.remove.assert_not_called()
    sin_fecha.remove.assert_not_called()


def test_un_contenedor_de_construccion_que_no_se_borra_no_detiene_los_demas():
    falla = _contenedor(limpieza.ANTIGUEDAD_CONSTRUCCION_S + 60)
    falla.remove.side_effect = APIError("en uso")
    otro = _contenedor(limpieza.ANTIGUEDAD_CONSTRUCCION_S + 60)
    cliente = _cliente(contenedores=[falla, otro])

    assert limpieza.eliminar_contenedores_construccion(cliente, ahora=AHORA) == 1


# ---------- capas sin etiqueta ----------


def test_las_capas_se_podan_solo_con_la_etiqueta_de_qagent_y_con_antiguedad():
    cliente = _cliente()
    cliente.images.prune.return_value = {
        "ImagesDeleted": [{"Deleted": "sha256:a"}, {"Deleted": "sha256:b"}],
        "SpaceReclaimed": 3 * GB,
    }

    assert limpieza.eliminar_capas_sin_etiqueta(cliente) == (2, 3 * GB)

    filtros = cliente.images.prune.call_args.kwargs["filters"]
    assert filtros["dangling"] is True
    assert filtros["label"] == FILTRO_CONSTRUCCION  # sin label, nunca se poda
    assert filtros["until"] == "60m"  # no toca las capas de un build en curso


def test_sin_capas_que_borrar_devuelve_ceros():
    cliente = _cliente()
    cliente.images.prune.return_value = {"ImagesDeleted": None, "SpaceReclaimed": 0}

    assert limpieza.eliminar_capas_sin_etiqueta(cliente) == (0, 0)


# ---------- caché de compilación ----------


def test_la_cache_de_compilacion_se_poda_por_antiguedad_maxima():
    cliente = _cliente()
    cliente.api.prune_builds.return_value = {"SpaceReclaimed": 2 * GB}

    assert limpieza.podar_cache_compilacion(cliente, dias=7) == 2 * GB

    cliente.api.prune_builds.assert_called_once_with(filters={"until": "168h"})


# ---------- tope de espacio de las imágenes derivadas ----------


def test_el_tope_borra_primero_las_menos_usadas_hasta_quedar_bajo_el_limite():
    vieja = _derivada("req-aaaaaaaaaaaa", hace_dias=20, propio_gb=4)
    media = _derivada("node-bbbbbbbbbbbb", hace_dias=10, propio_gb=4)
    reciente = _derivada("java-cccccccccccc", hace_dias=3, propio_gb=4)
    cliente = _cliente([_base(), reciente, vieja, media])  # desordenadas a propósito

    borradas = limpieza.aplicar_tope_imagenes(cliente, {}, 10 * GB, ahora=AHORA)

    # 12 GB propios > 10 GB: con borrar la más vieja (8 GB quedan) ya alcanza.
    assert borradas == ["qagent-sandbox:req-aaaaaaaaaaaa"]
    assert _borradas(cliente) == ["qagent-sandbox:req-aaaaaaaaaaaa"]


def test_el_tope_sigue_borrando_mientras_no_baje_del_limite():
    imagenes = [
        _derivada(f"req-{n:012d}", hace_dias=30 - n, propio_gb=4) for n in range(4)
    ]
    cliente = _cliente([_base(), *imagenes])

    borradas = limpieza.aplicar_tope_imagenes(cliente, {}, 5 * GB, ahora=AHORA)

    # 16 GB propios; hay que dejar ≤ 5 GB: quedan solo una (4 GB), la más reciente.
    assert borradas == [f"qagent-sandbox:req-{n:012d}" for n in range(3)]


def test_el_ultimo_uso_manda_sobre_la_fecha_de_creacion():
    creada_hace_mucho_usada_ayer = _derivada("req-aaaaaaaaaaaa", 90, propio_gb=6)
    creada_hace_poco_sin_usar = _derivada("req-bbbbbbbbbbbb", 5, propio_gb=6)
    usos = {
        "qagent-sandbox:req-aaaaaaaaaaaa": AHORA - 2 * DIA,
        "qagent-sandbox:req-bbbbbbbbbbbb": AHORA - 40 * DIA,
    }
    cliente = _cliente([creada_hace_mucho_usada_ayer, creada_hace_poco_sin_usar])

    borradas = limpieza.aplicar_tope_imagenes(cliente, usos, 8 * GB, ahora=AHORA)

    assert borradas == ["qagent-sandbox:req-bbbbbbbbbbbb"]


def test_el_tope_cuenta_solo_lo_propio_de_cada_imagen_no_la_base_compartida():
    """Con base de 5 GB, tres derivadas de 1 GB suman 3 GB, no 18 GB."""
    imagenes = [
        _derivada(f"req-{n:012d}", hace_dias=10 + n, propio_gb=1, base_gb=5)
        for n in range(3)
    ]
    cliente = _cliente([_base(base_gb=5), *imagenes])

    assert limpieza.aplicar_tope_imagenes(cliente, {}, 10 * GB, ahora=AHORA) == []
    cliente.images.remove.assert_not_called()


def test_el_tope_nunca_borra_la_base_aunque_sola_supere_el_limite():
    cliente = _cliente([_base(base_gb=20)])

    assert limpieza.aplicar_tope_imagenes(cliente, {}, 1 * GB, ahora=AHORA) == []
    cliente.images.remove.assert_not_called()


@pytest.mark.parametrize("base", [IMAGEN_BASE, IMAGEN_NODE, IMAGEN_JAVA])
def test_el_tope_nunca_borra_ninguna_imagen_base(base: str):
    otra_base = MagicMock(tags=[base])
    otra_base.attrs = {"Created": 1, "Size": 30 * GB}
    cliente = _cliente([otra_base])

    limpieza.aplicar_tope_imagenes(cliente, {}, 1, ahora=AHORA)

    cliente.images.remove.assert_not_called()


def test_el_tope_respeta_la_imagen_de_la_corrida_en_curso():
    en_curso = _derivada("req-aaaaaaaaaaaa", hace_dias=90, propio_gb=9)
    otra = _derivada("req-bbbbbbbbbbbb", hace_dias=20, propio_gb=9)
    cliente = _cliente([en_curso, otra])

    borradas = limpieza.aplicar_tope_imagenes(
        cliente,
        {},
        5 * GB,
        ahora=AHORA,
        protegidas={"qagent-sandbox:req-aaaaaaaaaaaa"},
    )

    assert borradas == ["qagent-sandbox:req-bbbbbbbbbbbb"]


def test_el_tope_respeta_lo_que_se_uso_hace_menos_de_una_hora():
    """Otra corrida (otra ventana) puede estar usándola ahora mismo."""
    usada_ahora = _derivada("req-aaaaaaaaaaaa", hace_dias=90, propio_gb=20)
    cliente = _cliente([usada_ahora])
    usos = {"qagent-sandbox:req-aaaaaaaaaaaa": AHORA - 120}

    assert limpieza.aplicar_tope_imagenes(cliente, usos, 1 * GB, ahora=AHORA) == []


def test_el_tope_ignora_las_imagenes_ajenas_al_repositorio_de_qagent():
    """Solo se listan las del repositorio `qagent-sandbox`; el resto ni se mira."""
    cliente = _cliente([])

    limpieza.aplicar_tope_imagenes(cliente, {}, 1, ahora=AHORA)

    cliente.images.list.assert_called_once_with(name="qagent-sandbox")


def test_el_tope_ignora_los_tags_de_otro_repositorio_con_prefijo_parecido():
    ajena = MagicMock(tags=["postgres:req-1", "otro/qagent-sandbox:req-x"])
    ajena.attrs = {"Created": 1, "Size": 30 * GB}
    cliente = _cliente([ajena])

    assert limpieza.aplicar_tope_imagenes(cliente, {}, 1, ahora=AHORA) == []
    cliente.images.remove.assert_not_called()


def test_una_imagen_en_uso_se_salta_y_el_tope_sigue_con_la_siguiente():
    en_uso = _derivada("req-aaaaaaaaaaaa", hace_dias=40, propio_gb=6)
    libre = _derivada("req-bbbbbbbbbbbb", hace_dias=30, propio_gb=6)
    reciente = _derivada("req-cccccccccccc", hace_dias=2, propio_gb=6)
    cliente = _cliente([en_uso, libre, reciente])
    cliente.images.remove.side_effect = [APIError("conflict"), None]

    borradas = limpieza.aplicar_tope_imagenes(cliente, {}, 10 * GB, ahora=AHORA)

    assert borradas == ["qagent-sandbox:req-bbbbbbbbbbbb"]


def test_sin_capas_conocidas_se_cuenta_la_imagen_entera():
    """Si no se puede inspeccionar, es mejor contar de más que dejarla crecer sin tope."""
    imagen = MagicMock(tags=["qagent-sandbox:req-aaaaaaaaaaaa"])
    imagen.attrs = {"Created": int(AHORA - 40 * DIA), "Size": 12 * GB}
    cliente = _cliente([imagen])
    cliente.images.get.side_effect = APIError("no se pudo inspeccionar")

    borradas = limpieza.aplicar_tope_imagenes(cliente, {}, 10 * GB, ahora=AHORA)

    assert borradas == ["qagent-sandbox:req-aaaaaaaaaaaa"]


# ---------- registrar_uso cuenta todos los prefijos derivados ----------


@pytest.mark.parametrize("prefijo", limpieza.PREFIJOS_DERIVADAS)
def test_registrar_uso_cuenta_cada_prefijo_derivado(tmp_path: Path, prefijo: str):
    ruta = tmp_path / "usos.json"
    etiqueta = f"qagent-sandbox:{prefijo}aaaaaaaaaaaa"

    limpieza.registrar_uso(etiqueta, ruta, ahora=AHORA)

    assert json.loads(ruta.read_text(encoding="utf-8")) == {etiqueta: AHORA}


def test_los_prefijos_derivados_incluyen_los_cuatro_tipos():
    assert set(limpieza.PREFIJOS_DERIVADAS) == {"req-", "node-", "java-", "browser-"}


@pytest.mark.parametrize(
    "etiqueta",
    [IMAGEN_BASE, IMAGEN_NODE, IMAGEN_JAVA, "postgres:16", "node:20", "req-aaaa"],
)
def test_registrar_uso_ignora_bases_y_ajenas(tmp_path: Path, etiqueta: str):
    ruta = tmp_path / "usos.json"

    limpieza.registrar_uso(etiqueta, ruta, ahora=AHORA)

    assert not ruta.exists()


# ---------- limpiar_al_iniciar: todo junto ----------


def test_la_limpieza_completa_hace_todos_los_pasos_y_olvida_lo_borrado(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(limpieza.time, "time", lambda: AHORA)
    ruta = tmp_path / "usos.json"
    ruta.write_text(
        json.dumps(
            {
                "qagent-sandbox:req-aaaaaaaaaaaa": AHORA - 60 * DIA,  # sin uso 60 días
                "qagent-sandbox:req-bbbbbbbbbbbb": AHORA - 20 * DIA,  # la menos usada
                "qagent-sandbox:req-cccccccccccc": AHORA - 5 * DIA,
            }
        ),
        encoding="utf-8",
    )
    imagenes = [
        _base(),
        _derivada("req-aaaaaaaaaaaa", 60, propio_gb=1),
        _derivada("req-bbbbbbbbbbbb", 20, propio_gb=8),
        _derivada("req-cccccccccccc", 5, propio_gb=8),
    ]
    cliente = _cliente(imagenes)
    quitadas: set[str] = set()
    cliente.images.remove.side_effect = quitadas.add
    cliente.images.list.side_effect = lambda **_: [
        i for i in imagenes if not quitadas.intersection(i.tags)
    ]
    cliente.containers.list.side_effect = [
        [_contenedor(30)],  # huérfanos de corrida
        [_contenedor(limpieza.ANTIGUEDAD_CONSTRUCCION_S + 1)],  # de construcción
    ]
    cliente.images.prune.return_value = {
        "ImagesDeleted": [{"Deleted": "sha256:x"}],
        "SpaceReclaimed": GB,
    }
    limites = LimitesDisco(tope_imagenes_derivadas_gb=10, cache_antiguedad_dias=7)

    resultado = limpieza.limpiar_al_iniciar(cliente, ruta, limites=limites)

    assert resultado["contenedores"] == 1
    assert resultado["construcciones"] == 1
    assert resultado["capas"] == 1
    assert resultado["capas_bytes"] == GB
    assert "cache_bytes" not in resultado
    cliente.api.prune_builds.assert_not_called()  # la caché no es automática
    assert resultado["imagenes_tope"] == ["qagent-sandbox:req-bbbbbbbbbbbb"]
    assert "qagent-sandbox:req-aaaaaaaaaaaa" in resultado["imagenes"]
    assert list(json.loads(ruta.read_text(encoding="utf-8"))) == [
        "qagent-sandbox:req-cccccccccccc"
    ]


def test_sin_limites_configurados_no_se_aplica_el_tope(
    tmp_path: Path,
):
    cliente = _cliente([_base(), _derivada("req-aaaaaaaaaaaa", 1, propio_gb=50)])

    resultado = limpieza.limpiar_al_iniciar(
        cliente, tmp_path / "usos.json", limites=LimitesDisco()
    )

    assert resultado["imagenes_tope"] == []
    cliente.images.remove.assert_not_called()


def test_un_paso_que_falla_no_impide_los_demas(tmp_path: Path):
    cliente = _cliente([_base(), _derivada("req-aaaaaaaaaaaa", 40, propio_gb=20)])
    cliente.images.prune.side_effect = APIError("prune no disponible")
    limites = LimitesDisco(tope_imagenes_derivadas_gb=5, cache_antiguedad_dias=7)

    resultado = limpieza.limpiar_al_iniciar(
        cliente, tmp_path / "usos.json", limites=limites
    )

    assert resultado["capas"] == 0
    assert resultado["imagenes_tope"] == ["qagent-sandbox:req-aaaaaaaaaaaa"]


def test_la_limpieza_completa_nunca_lanza_aunque_docker_falle(tmp_path: Path):
    cliente = MagicMock()
    cliente.containers.list.side_effect = ConnectionError("Docker cerrado")

    assert (
        limpieza.limpiar_al_iniciar(
            cliente, tmp_path / "usos.json", limites=LimitesDisco()
        )
        == {}
    )


def test_la_limpieza_solo_usa_filtros_de_qagent_para_borrar(tmp_path: Path):
    """Ningún borrado masivo sin el label de QAgent: nada de `containers.prune()`."""
    cliente = _cliente()

    limpieza.limpiar_al_iniciar(
        cliente,
        tmp_path / "usos.json",
        limites=LimitesDisco(tope_imagenes_derivadas_gb=1, cache_antiguedad_dias=7),
    )

    cliente.containers.prune.assert_not_called()
    cliente.volumes.prune.assert_not_called()
    cliente.api.prune_builds.assert_not_called()  # la caché de otros builds no es nuestra
    cliente.networks.prune.assert_not_called()
    for llamada in cliente.containers.list.call_args_list:
        assert llamada.kwargs["filters"]["label"]  # siempre filtrado por label
    assert cliente.images.prune.call_args.kwargs["filters"]["label"]
    cliente.images.list.assert_called_with(name="qagent-sandbox")

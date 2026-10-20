"""Limpieza del sandbox al abrir la app: contenedores huérfanos e imágenes `req-` viejas.

Docker se simula: ninguna prueba necesita Docker Desktop.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from docker.errors import APIError

from qagent.sandbox import limpieza
from qagent.sandbox.modelos import ETIQUETA_CONTENEDOR, IMAGEN_BASE

AHORA = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc).timestamp()
DIA = 24 * 60 * 60


def _fecha(segundos: float) -> str:
    """Fecha en el formato de Docker, con nanosegundos."""
    base = datetime.fromtimestamp(segundos, tz=timezone.utc)
    return base.strftime("%Y-%m-%dT%H:%M:%S.123456789Z")


def _contenedor(estado: str, hace_s: float) -> MagicMock:
    contenedor = MagicMock(status=estado)
    contenedor.attrs = {"Created": _fecha(AHORA - hace_s)}
    return contenedor


def _imagen(etiquetas: list[str], hace_dias: float) -> MagicMock:
    imagen = MagicMock(tags=etiquetas)
    imagen.attrs = {"Created": _fecha(AHORA - hace_dias * DIA)}
    return imagen


def _cliente(contenedores=(), imagenes=()) -> MagicMock:
    cliente = MagicMock()
    cliente.containers.list.return_value = list(contenedores)
    cliente.images.list.return_value = list(imagenes)
    return cliente


# ---------- contenedores ----------


def test_busca_solo_los_contenedores_con_la_etiqueta_del_sandbox():
    cliente = _cliente()

    limpieza.eliminar_contenedores_huerfanos(cliente, ahora=AHORA)

    cliente.containers.list.assert_called_once_with(
        all=True,
        filters={"label": [f"{k}={v}" for k, v in ETIQUETA_CONTENEDOR.items()]},
    )


def test_borra_los_detenidos_y_los_que_corren_hace_demasiado():
    detenido = _contenedor("exited", hace_s=30)
    creado = _contenedor("created", hace_s=30)
    colgado = _contenedor("running", hace_s=limpieza.ANTIGUEDAD_HUERFANO_S + 60)
    cliente = _cliente([detenido, creado, colgado])

    borrados = limpieza.eliminar_contenedores_huerfanos(cliente, ahora=AHORA)

    assert borrados == 3
    for contenedor in (detenido, creado, colgado):
        contenedor.remove.assert_called_once_with(force=True)


def test_no_borra_un_contenedor_que_corre_desde_hace_poco():
    """Puede ser de otra ventana de QAgent que está corriendo pruebas ahora mismo."""
    reciente = _contenedor("running", hace_s=60)
    sin_fecha = MagicMock(status="running", attrs={})
    cliente = _cliente([reciente, sin_fecha])

    assert limpieza.eliminar_contenedores_huerfanos(cliente, ahora=AHORA) == 0
    reciente.remove.assert_not_called()
    sin_fecha.remove.assert_not_called()


def test_si_un_contenedor_no_se_puede_borrar_sigue_con_los_demas():
    falla = _contenedor("exited", hace_s=30)
    falla.remove.side_effect = APIError("en uso")
    otro = _contenedor("exited", hace_s=30)
    cliente = _cliente([falla, otro])

    assert limpieza.eliminar_contenedores_huerfanos(cliente, ahora=AHORA) == 1
    otro.remove.assert_called_once_with(force=True)


# ---------- imágenes ----------


def test_borra_las_imagenes_req_sin_uso_y_nunca_la_base():
    vieja = _imagen(["qagent-sandbox:req-aaaaaaaaaaaa"], hace_dias=90)
    nueva = _imagen(["qagent-sandbox:req-bbbbbbbbbbbb"], hace_dias=2)
    base = _imagen([IMAGEN_BASE], hace_dias=400)
    cliente = _cliente(imagenes=[vieja, nueva, base])

    borradas = limpieza.eliminar_imagenes_sin_uso(cliente, {}, ahora=AHORA)

    assert borradas == ["qagent-sandbox:req-aaaaaaaaaaaa"]
    cliente.images.remove.assert_called_once_with("qagent-sandbox:req-aaaaaaaaaaaa")


def test_el_ultimo_uso_registrado_manda_sobre_la_fecha_de_creacion():
    creada_hace_mucho = _imagen(["qagent-sandbox:req-aaaaaaaaaaaa"], hace_dias=90)
    creada_hace_poco = _imagen(["qagent-sandbox:req-bbbbbbbbbbbb"], hace_dias=1)
    usos = {
        "qagent-sandbox:req-aaaaaaaaaaaa": AHORA - 3 * DIA,
        "qagent-sandbox:req-bbbbbbbbbbbb": AHORA - 60 * DIA,
    }
    cliente = _cliente(imagenes=[creada_hace_mucho, creada_hace_poco])

    borradas = limpieza.eliminar_imagenes_sin_uso(cliente, usos, ahora=AHORA)

    assert borradas == ["qagent-sandbox:req-bbbbbbbbbbbb"]


def test_una_imagen_en_uso_no_se_borra_ni_detiene_la_limpieza():
    en_uso = _imagen(["qagent-sandbox:req-aaaaaaaaaaaa"], hace_dias=90)
    libre = _imagen(["qagent-sandbox:req-bbbbbbbbbbbb"], hace_dias=90)
    cliente = _cliente(imagenes=[en_uso, libre])
    cliente.images.remove.side_effect = [APIError("conflict"), None]

    borradas = limpieza.eliminar_imagenes_sin_uso(cliente, {}, ahora=AHORA)

    assert borradas == ["qagent-sandbox:req-bbbbbbbbbbbb"]


# ---------- registro de uso ----------


def test_registrar_uso_guarda_la_fecha_solo_de_las_imagenes_req(tmp_path: Path):
    ruta = tmp_path / "imagenes_sandbox.json"

    limpieza.registrar_uso("qagent-sandbox:req-aaaaaaaaaaaa", ruta, ahora=AHORA)
    limpieza.registrar_uso(IMAGEN_BASE, ruta, ahora=AHORA)

    assert json.loads(ruta.read_text(encoding="utf-8")) == {
        "qagent-sandbox:req-aaaaaaaaaaaa": AHORA
    }


def test_leer_usos_tolera_un_archivo_danado_o_ausente(tmp_path: Path):
    ruta = tmp_path / "imagenes_sandbox.json"
    assert limpieza.leer_usos(ruta) == {}
    ruta.write_text("{no es json", encoding="utf-8")
    assert limpieza.leer_usos(ruta) == {}
    ruta.write_text('["lista"]', encoding="utf-8")
    assert limpieza.leer_usos(ruta) == {}


# ---------- al iniciar ----------


def test_limpiar_al_iniciar_hace_las_dos_cosas_y_olvida_las_imagenes_borradas(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(limpieza.time, "time", lambda: AHORA)
    ruta = tmp_path / "imagenes_sandbox.json"
    ruta.write_text(
        json.dumps(
            {
                "qagent-sandbox:req-aaaaaaaaaaaa": AHORA - 90 * DIA,
                "qagent-sandbox:req-bbbbbbbbbbbb": AHORA - DIA,
            }
        ),
        encoding="utf-8",
    )
    cliente = _cliente(
        contenedores=[_contenedor("exited", hace_s=30)],
        imagenes=[
            _imagen(["qagent-sandbox:req-aaaaaaaaaaaa"], hace_dias=90),
            _imagen(["qagent-sandbox:req-bbbbbbbbbbbb"], hace_dias=90),
        ],
    )

    resultado = limpieza.limpiar_al_iniciar(cliente, ruta)

    assert resultado == {
        "contenedores": 1,
        "imagenes": ["qagent-sandbox:req-aaaaaaaaaaaa"],
    }
    assert list(json.loads(ruta.read_text(encoding="utf-8"))) == [
        "qagent-sandbox:req-bbbbbbbbbbbb"
    ]


def test_limpiar_al_iniciar_sin_docker_no_falla(tmp_path: Path):
    cliente = MagicMock()
    cliente.containers.list.side_effect = ConnectionError("Docker cerrado")

    assert limpieza.limpiar_al_iniciar(cliente, tmp_path / "usos.json") == {}

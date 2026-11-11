"""#267 Capa 2: antes de construir o descargar una imagen se comprueba el espacio libre.

Sin Docker ni red: el cliente de Docker es falso y el espacio libre se fija en cada prueba
(el `conftest.py` raíz hace que, por defecto, siempre sobre).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import ImageNotFound

from qagent.config.disco import BYTES_POR_GB, LimitesDisco, leer_limites_disco
from qagent.orchestrator import corrida
from qagent.sandbox import EspacioInsuficiente, espacio
from qagent.sandbox import imagen as modulo_imagen
from qagent.sandbox.modelos import IMAGEN_BASE

GB = BYTES_POR_GB
#: La función real, guardada antes de que el `conftest.py` raíz la sustituya en cada prueba.
ESPACIO_LIBRE_REAL = espacio.espacio_libre_bytes
MINIMO = LimitesDisco(espacio_libre_minimo_gb=10)


def _con_libre(monkeypatch: pytest.MonkeyPatch, gb: float | None) -> None:
    monkeypatch.setattr(
        espacio, "espacio_libre_bytes", lambda: None if gb is None else int(gb * GB)
    )


def _sin_imagenes() -> MagicMock:
    cliente = MagicMock()
    cliente.images.get.side_effect = ImageNotFound("no existe")
    return cliente


# ---------- el mínimo sale de config.toml, no del código ----------


def test_el_minimo_de_espacio_libre_esta_en_el_config_del_equipo():
    limites = leer_limites_disco()

    assert limites.espacio_libre_minimo_gb is not None
    assert limites.espacio_libre_minimo_bytes == int(
        limites.espacio_libre_minimo_gb * GB
    )


# ---------- verificar_espacio_libre ----------


def test_con_espacio_de_sobra_no_pasa_nada():
    espacio.verificar_espacio_libre(MINIMO, libre=lambda: 50 * GB)
    espacio.verificar_espacio_libre(MINIMO, libre=lambda: 10 * GB)  # justo el mínimo


def test_por_debajo_del_minimo_falla_con_un_mensaje_para_personas():
    with pytest.raises(EspacioInsuficiente) as error:
        espacio.verificar_espacio_libre(MINIMO, libre=lambda: int(4.2 * GB))

    mensaje = str(error.value)
    assert "4,2 GB libres" in mensaje  # cuánto queda
    assert "al menos 10,0 GB" in mensaje  # cuánto necesita
    assert "faltan 5,8 GB" in mensaje  # cuánto falta
    assert "Libera espacio" in mensaje and "vuelve a intentar" in mensaje  # qué hacer
    for jerga in ("vhdx", "Traceback", "OSError", "bytes"):
        assert jerga not in mensaje


def test_el_error_es_un_error_del_sandbox_con_mensaje_para_mostrar():
    from qagent.sandbox.modelos import ErrorSandbox

    assert issubclass(EspacioInsuficiente, ErrorSandbox)


def test_si_no_se_puede_medir_el_espacio_no_se_bloquea():
    espacio.verificar_espacio_libre(MINIMO, libre=lambda: None)


def test_sin_minimo_configurado_no_se_bloquea():
    espacio.verificar_espacio_libre(LimitesDisco(), libre=lambda: 0)


def test_por_defecto_usa_el_config_del_equipo_y_el_espacio_del_disco(monkeypatch):
    _con_libre(monkeypatch, 0.5)

    with pytest.raises(EspacioInsuficiente):
        espacio.verificar_espacio_libre()

    _con_libre(monkeypatch, 500)
    espacio.verificar_espacio_libre()


# ---------- dónde se mide ----------


def test_el_espacio_libre_real_es_un_numero_positivo():
    libre = ESPACIO_LIBRE_REAL()

    assert libre is None or libre > 0


def test_si_el_disco_no_se_deja_medir_devuelve_none(monkeypatch):
    def falla(_ruta):
        raise OSError("sin acceso")

    monkeypatch.setattr(espacio.shutil, "disk_usage", falla)

    assert ESPACIO_LIBRE_REAL() is None


def test_en_windows_se_mide_el_disco_de_docker_desktop(tmp_path):
    local = tmp_path / "Local"
    (local / "Docker" / "wsl").mkdir(parents=True)

    carpeta = espacio.carpeta_datos_docker(
        {"LOCALAPPDATA": str(local)}, plataforma="win32"
    )

    assert carpeta == local / "Docker" / "wsl"


def test_en_windows_respeta_el_disco_elegido_en_los_ajustes_de_docker_desktop(tmp_path):
    roaming = tmp_path / "Roaming"
    (roaming / "Docker").mkdir(parents=True)
    otro_disco = tmp_path / "D-docker"
    otro_disco.mkdir()
    (roaming / "Docker" / "settings-store.json").write_text(
        json.dumps({"CustomWslDistroDir": str(otro_disco)}), encoding="utf-8"
    )

    carpeta = espacio.carpeta_datos_docker(
        {"APPDATA": str(roaming), "LOCALAPPDATA": str(tmp_path)}, plataforma="win32"
    )

    assert carpeta == otro_disco


def test_en_windows_con_ajustes_dañados_cae_a_la_carpeta_por_defecto(tmp_path):
    roaming = tmp_path / "Roaming"
    (roaming / "Docker").mkdir(parents=True)
    (roaming / "Docker" / "settings.json").write_text("{no es json", encoding="utf-8")

    carpeta = espacio.carpeta_datos_docker(
        {"APPDATA": str(roaming), "LOCALAPPDATA": str(tmp_path)}, plataforma="win32"
    )

    assert (
        carpeta == tmp_path
    )  # no existe Docker\wsl: sube a la primera carpeta que existe


@pytest.mark.parametrize("plataforma", ["linux", "darwin", "win32"])
def test_siempre_hay_una_carpeta_que_medir(plataforma):
    carpeta = espacio.carpeta_datos_docker({}, plataforma=plataforma)

    assert carpeta.exists()


# ---------- estado para el entorno (EN-06) ----------


def test_estado_espacio_ok_dice_cuanto_queda():
    estado = espacio.estado_espacio(MINIMO, libre=lambda: 80 * GB)

    assert estado["estado"] == "ok"
    assert "80,0 GB libres" in estado["mensaje"]


def test_estado_espacio_poco_explica_que_hacer():
    estado = espacio.estado_espacio(MINIMO, libre=lambda: 3 * GB)

    assert estado["estado"] == "poco"
    assert "faltan 7,0 GB" in estado["mensaje"]
    assert "la primera vez" in estado["mensaje"]


def test_estado_espacio_desconocido_no_inventa_nada():
    estado = espacio.estado_espacio(MINIMO, libre=lambda: None)

    assert estado["estado"] == "desconocido"


def test_estado_espacio_nunca_lanza():
    def falla():
        raise RuntimeError("boom")

    assert espacio.estado_espacio(MINIMO, libre=falla)["estado"] == "desconocido"


# ---------- las construcciones no empiezan sin espacio ----------


def test_construir_no_toca_docker_si_falta_espacio(monkeypatch, tmp_path):
    _con_libre(monkeypatch, 2)
    cliente = MagicMock()

    with pytest.raises(EspacioInsuficiente):
        modulo_imagen._construir(cliente, tmp_path, "qagent-sandbox:req-x", "falló")
    with pytest.raises(EspacioInsuficiente):
        modulo_imagen._construir(
            cliente, tmp_path, "qagent-sandbox:req-x", "falló", lambda texto: None
        )

    cliente.images.build.assert_not_called()
    cliente.api.build.assert_not_called()


def test_construir_sigue_igual_si_hay_espacio(monkeypatch, tmp_path):
    _con_libre(monkeypatch, 200)
    cliente = MagicMock()

    modulo_imagen._construir(cliente, tmp_path, "qagent-sandbox:req-x", "falló")

    cliente.images.build.assert_called_once()


def test_la_imagen_base_no_se_construye_sin_espacio(monkeypatch):
    _con_libre(monkeypatch, 1)
    cliente = MagicMock()

    with pytest.raises(EspacioInsuficiente) as error:
        modulo_imagen.construir_imagen_base(cliente)

    assert "faltan" in str(error.value)
    cliente.images.build.assert_not_called()


def test_las_dependencias_del_proyecto_no_se_instalan_sin_espacio(
    monkeypatch, tmp_path
):
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    _con_libre(monkeypatch, 1)
    cliente = MagicMock()
    cliente.images.get.side_effect = [MagicMock(), ImageNotFound("no hay derivada")]

    with pytest.raises(EspacioInsuficiente):
        modulo_imagen.preparar_imagen(tmp_path, cliente)

    cliente.images.build.assert_not_called()


def test_con_la_imagen_ya_construida_un_disco_justo_no_impide_correr(
    monkeypatch, tmp_path
):
    """Solo hace falta espacio para construir; reutilizar una imagen no gasta disco."""
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    _con_libre(monkeypatch, 0.1)
    cliente = MagicMock()  # `images.get` encuentra la base y la derivada

    etiqueta = modulo_imagen.preparar_imagen(tmp_path, cliente)

    assert etiqueta.startswith("qagent-sandbox:req-")
    cliente.images.build.assert_not_called()


# ---------- construccion_pendiente: cuándo hace falta el espacio ----------


def test_pendiente_si_falta_la_imagen_base(tmp_path):
    assert modulo_imagen.construccion_pendiente(tmp_path, _sin_imagenes()) is True


def test_pendiente_si_falta_la_imagen_de_las_dependencias(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    cliente = MagicMock()
    cliente.images.get.side_effect = [MagicMock(), ImageNotFound("no hay derivada")]

    assert modulo_imagen.construccion_pendiente(tmp_path, cliente) is True


def test_no_pendiente_si_las_imagenes_ya_existen(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")

    assert modulo_imagen.construccion_pendiente(tmp_path, MagicMock()) is False


def test_no_pendiente_si_no_hay_dependencias_y_existe_la_base(tmp_path):
    assert modulo_imagen.construccion_pendiente(tmp_path, MagicMock()) is False


# ---------- la corrida no empieza ----------


class _Adaptador:
    def entorno_sandbox(self, _ruta):
        return MagicMock(imagen=IMAGEN_BASE)


def _con_docker(monkeypatch, pendiente: bool) -> None:
    monkeypatch.setattr(
        "qagent.sandbox.cliente.obtener_cliente", lambda: MagicMock(name="cliente")
    )
    monkeypatch.setattr(
        modulo_imagen, "construccion_pendiente", lambda *_a, **_k: pendiente
    )


def test_la_corrida_se_detiene_si_hay_que_construir_y_no_hay_espacio(
    monkeypatch, tmp_path
):
    _con_docker(monkeypatch, pendiente=True)
    _con_libre(monkeypatch, 3)

    motivo = corrida._motivo_sin_espacio(tmp_path, _Adaptador())

    assert motivo is not None
    assert "3,0 GB libres" in motivo and "faltan 7,0 GB" in motivo


def test_la_corrida_sigue_si_no_hay_nada_que_construir(monkeypatch, tmp_path):
    _con_docker(monkeypatch, pendiente=False)
    _con_libre(monkeypatch, 0.1)

    assert corrida._motivo_sin_espacio(tmp_path, _Adaptador()) is None


def test_la_corrida_sigue_si_hay_espacio(monkeypatch, tmp_path):
    _con_docker(monkeypatch, pendiente=True)
    _con_libre(monkeypatch, 100)

    assert corrida._motivo_sin_espacio(tmp_path, _Adaptador()) is None


def test_si_docker_no_responde_la_comprobacion_no_frena_la_corrida(
    monkeypatch, tmp_path
):
    def sin_docker():
        raise ConnectionError("Docker cerrado")

    monkeypatch.setattr("qagent.sandbox.cliente.obtener_cliente", sin_docker)
    _con_libre(monkeypatch, 0.1)

    assert corrida._motivo_sin_espacio(tmp_path, _Adaptador()) is None


def test_ejecutar_corrida_no_empieza_y_dice_cuanto_falta(monkeypatch, tmp_path: Path):
    """La corrida termina antes de analizar o llamar a la IA, con el motivo en lenguaje simple."""
    from qagent.config import cargar_configuracion
    from qagent.config.carga import RUTA_CONFIG

    (tmp_path / "util.py").write_text(
        'def doble(x: int) -> int:\n    """Duplica."""\n    return x * 2\n',
        encoding="utf-8",
    )
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    mensaje = espacio.mensaje_espacio_insuficiente(3 * GB, 10 * GB)
    monkeypatch.setattr(corrida, "_motivo_sin_espacio", lambda *_a: mensaje)
    eventos: list[dict] = []

    resumen = corrida.ejecutar_corrida(
        tmp_path, "deep", config, None, simulado=True, al_evento=eventos.append
    )

    assert resumen.estado == "fallo_controlado"
    assert resumen.motivo == mensaje
    assert resumen.total_funciones == 0
    assert any(mensaje in str(e.get("mensaje", "")) for e in eventos)


def test_con_una_imagen_inyectada_no_se_comprueba_el_disco(monkeypatch, tmp_path):
    """Las pruebas y los flujos con `preparar_imagen` propio no consultan Docker."""
    from qagent.config import cargar_configuracion
    from qagent.config.carga import RUTA_CONFIG

    (tmp_path / "vacio.py").write_text("X = 1\n", encoding="utf-8")
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    def no_debe_llamarse(*_a):
        raise AssertionError("no se debe comprobar el disco")

    monkeypatch.setattr(corrida, "_motivo_sin_espacio", no_debe_llamarse)

    resumen = corrida.ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        preparar_imagen=lambda ruta: "imagen",
    )

    assert "funciones públicas" in resumen.motivo  # llegó al análisis normal

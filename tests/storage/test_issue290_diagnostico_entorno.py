"""Detalle persistido de preparación: conserva la causa y oculta credenciales."""

from qagent.almacenamiento import AlmacenProyecto
from qagent.sandbox.modelos import ErrorConstruccionImagen
from qagent.storage.diagnostico_entorno import guardar_diagnostico


def test_detalle_tecnico_conserva_causa_sin_credenciales(tmp_path, monkeypatch):
    """El log accesible desde el mensaje no divulga URL con contraseña ni parámetros."""
    monkeypatch.setattr("qagent.config.carga.RUTA_ENV", tmp_path / "sin-claves.env")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run()["run_id"]
    error = ErrorConstruccionImagen(
        "No se resolvió el padre",
        "[ERROR] Non-resolvable parent POM: https://persona:clave-prueba@example.com/maven?token=secreto-prueba\n"
        "Authorization: Basic valor-basico-prueba\npassword=abc\ntoken=xyz\n",
    )
    relativa = guardar_diagnostico(tmp_path, run_id, error)
    assert relativa == f".qagent/runs/{run_id}/entorno.log"
    texto = (tmp_path / relativa).read_text(encoding="utf-8")
    assert "Non-resolvable parent POM" in texto
    assert "example.com/maven" in texto
    assert "clave-prueba" not in texto
    assert "secreto-prueba" not in texto
    assert "valor-basico-prueba" not in texto
    assert "password=abc" not in texto
    assert "token=xyz" not in texto


def test_error_sin_log_no_crea_detalle_y_run_invalido_no_reemplaza_error(tmp_path):
    assert guardar_diagnostico(tmp_path, None, RuntimeError("original")) is None
    error = ErrorConstruccionImagen("original", "detalle")
    assert guardar_diagnostico(tmp_path, "../externo", error) is None
    assert not (tmp_path / ".qagent").exists()


def test_log_utf8_se_acota_por_bytes_sin_romper_caracteres(tmp_path, monkeypatch):
    monkeypatch.setattr("qagent.config.carga.RUTA_ENV", tmp_path / "sin-claves.env")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run()["run_id"]
    error = ErrorConstruccionImagen("original", "[ERROR] causa\n" + "€" * 200_000)
    relativa = guardar_diagnostico(tmp_path, run_id, error)
    contenido = (tmp_path / relativa).read_bytes()
    assert len(contenido) <= 524_288
    assert contenido.decode("utf-8").startswith("[ERROR] causa")

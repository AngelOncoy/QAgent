"""Pruebas del recorrido determinista y detección de truncamiento (ADR-008).

Verifica:
1. Caso positivo: repositorio con < 20.000 archivos elegibles (resultado completo).
2. Caso límite: repositorio con exactamente 20.000 archivos elegibles (completo solo si no hay pendientes).
3. Caso negativo: repositorio con 20.001 archivos elegibles (truncado y con aviso).
4. Determinismo: el orden relativo de recorrido es reproducible.
5. Seguridad en symlinks: no sigue enlaces fuera de la raíz ni entra en ciclos.
6. Continuación por módulos y consolidación sin duplicados.
7. Detección de lenguajes en carpetas no exploradas inicialmente.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qagent.lenguajes import REGISTRO
from qagent.lenguajes.exploracion import (
    ESTADO_CANCELADO,
    ESTADO_COMPLETO,
    ESTADO_PARCIAL_ERROR,
    ESTADO_TRUNCADO,
    MAX_ARCHIVOS_DETECCION,
    ResultadoExploracion,
    explorar_archivos,
)
from qagent.lenguajes.registro import listar_archivos


def _crear(raiz: Path, ruta_relativa: str, contenido: str = "") -> Path:
    """Crea un archivo asegurando sus carpetas intermedias."""
    destino = raiz / ruta_relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    return destino


# --- 1. Determinismo y Reproducibilidad ---


def test_recorrido_determinista_mismo_orden_independiente_de_creacion(
    tmp_path: Path,
) -> None:
    """Para un mismo conjunto de archivos, el recorrido devuelve siempre el mismo orden."""
    # Creamos archivos en orden desordenado a propósito
    archivos = [
        "src/z_util.py",
        "src/a_main.py",
        "docs/guia.md",
        "config/settings.json",
        "src/core/b_module.py",
        "src/core/a_base.py",
    ]
    for rel in archivos:
        _crear(tmp_path, rel)

    res1 = explorar_archivos(tmp_path)
    res2 = explorar_archivos(tmp_path)

    esperado = (
        "config/settings.json",
        "docs/guia.md",
        "src/a_main.py",
        "src/core/a_base.py",
        "src/core/b_module.py",
        "src/z_util.py",
    )
    assert res1.archivos == esperado
    assert res2.archivos == esperado
    assert res1.estado == ESTADO_COMPLETO
    assert res1.total_procesados == len(esperado)
    assert res1.limite_alcanzado is False


def test_listar_archivos_mantiene_compatibilidad_determinista(tmp_path: Path) -> None:
    """listar_archivos conserva su contrato devolviendo list[str] ordenado."""
    _crear(tmp_path, "b.py")
    _crear(tmp_path, "a.py")
    _crear(tmp_path, "sub/c.py")

    lista = listar_archivos(tmp_path)
    assert isinstance(lista, list)
    assert lista == ["a.py", "b.py", "sub/c.py"]


# --- 2. Exclusiones y Seguridad con Enlaces Simbólicos ---


def test_ignora_carpetas_excluidas_y_ocultas(tmp_path: Path) -> None:
    _crear(tmp_path, "app.py")
    _crear(tmp_path, ".git/HEAD")
    _crear(tmp_path, ".venv/lib/site.py")
    _crear(tmp_path, "node_modules/pkg/index.js")
    _crear(tmp_path, "target/classes/App.class")
    _crear(tmp_path, "dist/bundle.js")
    _crear(tmp_path, "tests/test_app.py")
    _crear(tmp_path, "paquete.egg-info/PKG-INFO")

    resultado = explorar_archivos(tmp_path)
    assert resultado.archivos == ("app.py",)
    assert resultado.estado == ESTADO_COMPLETO


def test_enlaces_simbolicos_a_directorios_no_se_recorren_evitando_ciclos(
    tmp_path: Path,
) -> None:
    """Evita ciclos provocados por enlaces simbólicos a directorios."""
    _crear(tmp_path, "src/main.py")
    carpeta_externa = tmp_path.parent / "externa"
    carpeta_externa.mkdir(exist_ok=True)
    (carpeta_externa / "peligro.py").write_text("secret = 1", encoding="utf-8")

    enlace_dir = tmp_path / "link_externo"
    try:
        enlace_dir.symlink_to(carpeta_externa, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip(
            "El sistema operativo no permite crear enlaces simbólicos sin privilegios"
        )

    # Crear enlace cíclico
    enlace_ciclo = tmp_path / "src" / "ciclo"
    try:
        enlace_ciclo.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pass

    resultado = explorar_archivos(tmp_path)
    assert "src/main.py" in resultado.archivos
    # No debe haber ingresado ni a la carpeta externa ni al ciclo
    assert not any("peligro.py" in a for a in resultado.archivos)
    assert not any("ciclo" in a for a in resultado.archivos)


def test_enlaces_simbolicos_a_archivos_fuera_de_la_raiz_son_ignorados(
    tmp_path: Path,
) -> None:
    """No seguir enlaces que permitan salir de la raíz autorizada."""
    _crear(tmp_path, "app.py")
    fuera = tmp_path.parent / "archivo_fuera.py"
    fuera.write_text("fuera = True", encoding="utf-8")

    enlace_archivo = tmp_path / "enlace.py"
    try:
        enlace_archivo.symlink_to(fuera)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks no permitidos en este entorno")

    resultado = explorar_archivos(tmp_path)
    assert resultado.archivos == ("app.py",)


# --- 3. Casos Positivo, Límite y Negativo con Límite Parametrizado ---


def test_caso_positivo_menos_de_limite_archivos(tmp_path: Path) -> None:
    """Caso positivo: Un repositorio con menos de limite archivos debe considerarse completo."""
    for i in range(5):
        _crear(tmp_path, f"src/m{i}.py")

    resultado = explorar_archivos(tmp_path, limite=10)
    assert resultado.estado == ESTADO_COMPLETO
    assert resultado.total_procesados == 5
    assert resultado.limite_alcanzado is False
    assert resultado.carpetas_pendientes == ()
    assert resultado.incompleto is False


def test_caso_limite_exactamente_limite_archivos_sin_pendientes(tmp_path: Path) -> None:
    """Caso límite: Exactamente N archivos es completo solo si se comprueba que no quedan pendientes."""
    for i in range(10):
        _crear(tmp_path, f"src/m{i}.py")

    resultado = explorar_archivos(tmp_path, limite=10)
    assert resultado.total_procesados == 10
    assert resultado.estado == ESTADO_COMPLETO
    assert resultado.limite_alcanzado is False
    assert resultado.carpetas_pendientes == ()


def test_caso_limite_con_directorios_vacios_adicionales_es_completo(
    tmp_path: Path,
) -> None:
    """Si hay directorios restantes pero están vacíos o ignorados, no son archivos pendientes."""
    for i in range(10):
        _crear(tmp_path, f"src/m{i}.py")
    (tmp_path / "vacio").mkdir()
    (tmp_path / "vacio_sub" / "vacio").mkdir(parents=True)

    resultado = explorar_archivos(tmp_path, limite=10)
    assert resultado.total_procesados == 10
    assert resultado.estado == ESTADO_COMPLETO
    assert resultado.limite_alcanzado is False


def test_caso_negativo_mas_de_limite_archivos_provoca_truncado(tmp_path: Path) -> None:
    """Caso negativo: N + 1 archivos provoca estado truncado con carpetas pendientes."""
    for i in range(11):
        _crear(tmp_path, f"src/m{i:02d}.py")
    _crear(tmp_path, "extra/otro.py")

    resultado = explorar_archivos(tmp_path, limite=10)
    assert resultado.estado == ESTADO_TRUNCADO
    assert resultado.limite_alcanzado is True
    assert resultado.total_procesados == 10
    assert resultado.incompleto is True
    assert len(resultado.carpetas_pendientes) > 0


# --- 4. Casos Reales con 19.999, 20.000 y 20.001 Archivos (Simulados/Estructurales) ---


def _simular_escaneo_n_archivos(total: int, tmp_path: Path) -> ResultadoExploracion:
    """Simula una estructura con `total` archivos elegibles para verificar los límites de 20.000."""
    # Para ser extremadamente rápido y no saturar I/O de disco, usamos un mock de os.scandir
    carpeta = tmp_path / f"repo_{total}"
    carpeta.mkdir(parents=True, exist_ok=True)

    # Creamos carpetas lógicas
    sub_backend = carpeta / "backend"
    sub_backend.mkdir(exist_ok=True)
    sub_frontend = carpeta / "frontend"
    sub_frontend.mkdir(exist_ok=True)

    archivos_backend = [
        MagicMock(
            name=f"f_{i:05d}.py",
            path=str(sub_backend / f"f_{i:05d}.py"),
            is_file=lambda follow_symlinks=False: True,
            is_dir=lambda follow_symlinks=False: False,
            is_symlink=lambda: False,
        )
        for i in range(min(total, 20_000))
    ]
    # Asignar .name a cada mock
    for idx, m in enumerate(archivos_backend):
        m.name = f"f_{idx:05d}.py"

    archivos_frontend = []
    if total > 20_000:
        archivos_frontend = [
            MagicMock(
                name=f"ui_{i:05d}.ts",
                path=str(sub_frontend / f"ui_{i:05d}.ts"),
                is_file=lambda follow_symlinks=False: True,
                is_dir=lambda follow_symlinks=False: False,
                is_symlink=lambda: False,
            )
            for i in range(total - 20_000)
        ]
        for idx, m in enumerate(archivos_frontend):
            m.name = f"ui_{idx:05d}.ts"

    class MockIter:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    original_scandir = os.scandir

    def _scandir_mock(path_obj):
        p = Path(path_obj).resolve()
        if p == carpeta.resolve():
            d_backend = MagicMock(
                name="backend",
                path=str(sub_backend),
                is_file=lambda follow_symlinks=False: False,
                is_dir=lambda follow_symlinks=False: True,
                is_symlink=lambda: False,
            )
            d_backend.name = "backend"
            d_frontend = MagicMock(
                name="frontend",
                path=str(sub_frontend),
                is_file=lambda follow_symlinks=False: False,
                is_dir=lambda follow_symlinks=False: True,
                is_symlink=lambda: False,
            )
            d_frontend.name = "frontend"
            return MockIter([d_backend, d_frontend])
        elif p == sub_backend.resolve():
            return MockIter(archivos_backend)
        elif p == sub_frontend.resolve():
            return MockIter(archivos_frontend)
        return original_scandir(path_obj)

    import unittest.mock

    with unittest.mock.patch("os.scandir", side_effect=_scandir_mock):
        return explorar_archivos(carpeta, limite=MAX_ARCHIVOS_DETECCION)


def test_regresion_19999_archivos_positivo(tmp_path: Path) -> None:
    """19.999 archivos elegibles: debe considerarse completo sin errores."""
    res = _simular_escaneo_n_archivos(19_999, tmp_path)
    assert res.total_procesados == 19_999
    assert res.estado == ESTADO_COMPLETO
    assert res.limite_alcanzado is False
    assert res.carpetas_pendientes == ()


def test_regresion_20000_archivos_limite_exhaustivo(tmp_path: Path) -> None:
    """Exactamente 20.000 archivos elegibles: debe ser completo al comprobar que no quedan pendientes."""
    res = _simular_escaneo_n_archivos(20_000, tmp_path)
    assert res.total_procesados == 20_000
    assert res.estado == ESTADO_COMPLETO
    assert res.limite_alcanzado is False
    assert res.carpetas_pendientes == ()


def test_regresion_20001_archivos_negativo_truncado(tmp_path: Path) -> None:
    """20.001 archivos elegibles: debe provocar estado truncado y registrar carpetas pendientes."""
    res = _simular_escaneo_n_archivos(20_001, tmp_path)
    assert res.total_procesados == 20_000
    assert res.estado == ESTADO_TRUNCADO
    assert res.limite_alcanzado is True
    assert res.incompleto is True
    assert "frontend" in res.carpetas_pendientes


# --- 5. Continuación por Módulos y Consolidación sin Duplicados ---


def test_continuacion_por_modulos_y_consolidacion_sin_duplicados(
    tmp_path: Path,
) -> None:
    """El usuario puede continuar la exploración por módulos y consolidar sin duplicados."""
    # Creamos un proyecto grande donde backend tiene 5 archivos y frontend tiene 5
    for i in range(5):
        _crear(tmp_path, f"backend/api_{i}.py")
    for i in range(5):
        _crear(tmp_path, f"frontend/comp_{i}.ts")

    # Exploración inicial con límite de 5 archivos: alcanza el límite en backend
    res_inicial = explorar_archivos(tmp_path, limite=5)
    assert res_inicial.estado == ESTADO_TRUNCADO
    assert res_inicial.total_procesados == 5
    assert "frontend" in res_inicial.carpetas_pendientes

    # Continuación explorando solo la carpeta pendiente 'frontend'
    res_continuacion = explorar_archivos(
        tmp_path,
        limite=10,
        subcarpetas=["frontend"],
    )
    assert res_continuacion.estado == ESTADO_COMPLETO
    assert len(res_continuacion.archivos) == 5

    # Consolidación de ambos resultados
    consolidado = res_inicial.consolidar(res_continuacion)
    assert consolidado.estado == ESTADO_COMPLETO
    assert consolidado.total_procesados == 10
    assert len(set(consolidado.archivos)) == 10  # Sin duplicados
    assert consolidado.carpetas_pendientes == ()  # Frontend ya no está pendiente


def test_lenguaje_en_carpeta_no_recorrida_no_queda_descartado_silenciosamente(
    tmp_path: Path,
) -> None:
    """Verifica que un lenguaje en una carpeta pendiente no queda descartado tras continuar."""
    # 5 archivos python en backend y 3 archivos java en service_java
    for i in range(5):
        _crear(tmp_path, f"backend/modulo_{i}.py")
    for i in range(3):
        _crear(tmp_path, f"service_java/App_{i}.java")

    # Con límite 5, la exploración inicial solo ve backend (Python)
    res_inicial = explorar_archivos(tmp_path, limite=5)
    assert res_inicial.estado == ESTADO_TRUNCADO
    assert "service_java" in res_inicial.carpetas_pendientes

    # En la exploración inicial, Java no apareció porque estaba truncado
    detecciones_iniciales = REGISTRO.detectar_en(res_inicial.archivos)
    assert [d.lenguaje for d in detecciones_iniciales] == ["python"]

    # Al continuar la exploración sobre la carpeta pendiente:
    res_java = explorar_archivos(tmp_path, subcarpetas=["service_java"])
    consolidado = res_inicial.consolidar(res_java)

    # Ahora la evaluación global detecta ambos lenguajes correctamente
    detecciones_consolidadas = REGISTRO.detectar_en(consolidado.archivos)
    lenguajes = [d.lenguaje for d in detecciones_consolidadas]
    assert "python" in lenguajes
    assert "java" in lenguajes


# --- 6. Manejo de Errores Parciales y Cancelación ---


def test_error_de_lectura_provoca_estado_parcial_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _crear(tmp_path, "publico/app.py")
    carpeta_restringida = tmp_path / "privado"
    carpeta_restringida.mkdir()
    (carpeta_restringida / "secret.py").write_text("", encoding="utf-8")

    real_scandir = os.scandir

    def _scandir_con_error(ruta):
        if Path(ruta).resolve() == carpeta_restringida.resolve():
            raise PermissionError("Permiso denegado")
        return real_scandir(ruta)

    monkeypatch.setattr("os.scandir", _scandir_con_error)

    resultado = explorar_archivos(tmp_path)
    assert resultado.estado == ESTADO_PARCIAL_ERROR
    assert len(resultado.errores) == 1
    assert resultado.errores[0]["ruta"] == "privado"
    assert "publico/app.py" in resultado.archivos


def test_cancelacion_por_token(tmp_path: Path) -> None:
    for i in range(5):
        _crear(tmp_path, f"src/m{i}.py")

    llamadas = 0

    def _cancelar():
        nonlocal llamadas
        llamadas += 1
        return llamadas >= 2

    resultado = explorar_archivos(tmp_path, cancel_token=_cancelar)
    assert resultado.estado == ESTADO_CANCELADO

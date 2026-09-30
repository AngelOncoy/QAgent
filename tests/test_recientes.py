import json
from datetime import datetime, timedelta

import pytest

from pyagent.app import recientes
from pyagent.app.api import Api


def _proyecto(base, nombre):
    carpeta = base / nombre
    carpeta.mkdir()
    (carpeta / "main.py").write_text("x = 1\n", encoding="utf-8")
    return carpeta


def test_lista_vacia_si_no_hay_archivo(tmp_path):
    assert recientes.listar(archivo=tmp_path / "r.json") == []


def test_archivo_danado_no_rompe(tmp_path):
    f = tmp_path / "r.json"
    f.write_text("{no es json", encoding="utf-8")
    assert recientes.listar(archivo=f) == []


def test_registrar_no_duplica_y_sube_al_inicio(tmp_path):
    f = tmp_path / "r.json"
    a, b = _proyecto(tmp_path, "a"), _proyecto(tmp_path, "b")
    recientes.registrar("a", "local", a, archivo=f)
    recientes.registrar("b", "git", b, url="https://github.com/u/b.git", archivo=f)
    recientes.registrar("a", "local", a, archivo=f)
    assert [p["nombre"] for p in recientes.listar(archivo=f)] == ["a", "b"]


def test_origen_invalido(tmp_path):

    with pytest.raises(ValueError):
        recientes.registrar("x", "ftp", tmp_path, archivo=tmp_path / "r.json")


def test_evidencia_11_proyectos_lista_los_10_mas_recientes(tmp_path):
    f = tmp_path / "r.json"
    t0 = datetime(2026, 10, 1, 9, 0)
    for i in range(11):
        carpeta = _proyecto(tmp_path, f"p{i}")
        recientes.registrar(f"p{i}", "local", carpeta, archivo=f, ahora=t0 + timedelta(minutes=i))
    nombres = [p["nombre"] for p in recientes.listar(archivo=f)]
    assert len(nombres) == 10
    assert nombres[0] == "p10" and "p0" not in nombres


def test_evidencia_carpeta_renombrada_se_marca_no_encontrada(tmp_path):
    f = tmp_path / "r.json"
    carpeta = _proyecto(tmp_path, "viejo")
    recientes.registrar("viejo", "local", carpeta, archivo=f)
    carpeta.rename(tmp_path / "nuevo")
    p = recientes.listar(archivo=f)[0]
    assert p["estado"] == "no_encontrada" and p["ultima_corrida"] is None
    assert recientes.abrir(carpeta, archivo=f) == {"ok": False, "error": "no_encontrada"}


def test_quitar_solo_saca_de_la_lista(tmp_path):
    f = tmp_path / "r.json"
    carpeta = _proyecto(tmp_path, "a")
    recientes.registrar("a", "local", carpeta, archivo=f)
    assert recientes.quitar(carpeta, archivo=f) is True
    assert recientes.quitar(carpeta, archivo=f) is False
    assert carpeta.exists() and recientes.listar(archivo=f) == []


def test_ultima_corrida_lee_carpeta_runs(tmp_path):
    carpeta = _proyecto(tmp_path, "a")
    assert recientes.ultima_corrida(carpeta) is None
    (carpeta / ".pyagent" / "runs" / "8841-B").mkdir(parents=True)
    assert recientes.ultima_corrida(carpeta) is not None


def test_abrir_reciente_ok_actualiza_orden(tmp_path):
    f = tmp_path / "r.json"
    a, b = _proyecto(tmp_path, "a"), _proyecto(tmp_path, "b")
    recientes.registrar("a", "local", a, archivo=f)
    recientes.registrar("b", "local", b, archivo=f)
    api = Api(f)
    assert api.abrir_reciente(str(a))["ok"] is True
    assert api.listar_recientes()[0]["nombre"] == "a"
    assert json.loads(f.read_text(encoding="utf-8"))[0]["nombre"] == "a"
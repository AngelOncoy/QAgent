from __future__ import annotations

from pathlib import Path

from qagent.app.desktop import DesktopAPI


def _regla() -> dict:
    return {
        "version": "1",
        "reglas": [
            {
                "id": "capas-001",
                "tipo": "dependencia_prohibida",
                "nombre": "Dominio no importa interfaz",
                "origen": "usuario",
                "confirmada": True,
                "desde": "dominio",
                "hacia": "interfaz",
            }
        ],
    }


def test_api_guarda_y_recupera_reglas_sin_persistir_universal(tmp_path: Path) -> None:
    api = DesktopAPI()
    guardado = api.guardar_reglas_arquitectura(str(tmp_path), _regla())
    recuperado = api.obtener_reglas_arquitectura(str(tmp_path))

    assert guardado["ok"] is True
    assert recuperado["ok"] is True
    assert [r["id"] for r in recuperado["reglas"]] == [
        "universal-sin-ciclos",
        "capas-001",
    ]
    texto = (tmp_path / ".qagent/reglas_arquitectura.json").read_text(encoding="utf-8")
    assert "universal-sin-ciclos" not in texto


def test_api_rechaza_documento_invalido(tmp_path: Path) -> None:
    resultado = DesktopAPI().guardar_reglas_arquitectura(
        str(tmp_path), {"version": "1", "reglas": [{"command": "rm -rf /"}]}
    )

    assert resultado["ok"] is False
    assert not (tmp_path / ".qagent/reglas_arquitectura.json").exists()

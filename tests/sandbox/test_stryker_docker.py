"""Stryker real acotado a funciones críticas dentro de qagent-sandbox:node (#179)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.lenguajes import TypeScriptAdapter
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_NODE
from qagent.sandbox.mutacion import OK

pytestmark = pytest.mark.docker


def test_stryker_real_solo_funcion_critica(cliente_docker, tmp_path: Path) -> None:
    """Una prueba real en el sandbox Node muta solo la función crítica seleccionada."""
    if not _imagen_existe(cliente_docker, IMAGEN_NODE):
        pytest.skip("Falta qagent-sandbox:node; no se ha validado Stryker real.")

    proyecto = tmp_path / "proyecto"
    src = proyecto / "src"
    src.mkdir(parents=True)
    modulo = "src/precios.ts"
    fuente = proyecto / modulo

    codigo = """export function calcularDescuento(precio: number, tipo: string): number {
  if (precio > 100) {
    return precio * 0.9;
  }
  return precio;
}

export function funcionNoCritica(x: number): number {
  return x + 1;
}
"""
    fuente.write_text(codigo, encoding="utf-8")
    (proyecto / "package.json").write_text("{}", encoding="utf-8")

    pruebas = tmp_path / "aprobadas"
    pruebas.mkdir()
    codigo_prueba = """import { describe, it, expect } from 'vitest';
import { calcularDescuento } from '../proyecto/src/precios';

describe('calcularDescuento', () => {
  it('aplica descuento normal', () => {
    expect(calcularDescuento(200, 'normal')).toBe(180);
  });
});
"""
    (pruebas / "test_descuento.ts").write_text(codigo_prueba, encoding="utf-8")

    informes = []
    adaptador = TypeScriptAdapter()
    resultado = adaptador.ejecutar_mutacion(
        IMAGEN_NODE,
        proyecto,
        pruebas,
        modulo,
        ["calcularDescuento"],
        cliente=cliente_docker,
        al_informe=informes.append,
    )

    funcion = resultado.funciones["calcularDescuento"]
    assert funcion.estado == OK, f"{funcion.mensaje}\n{resultado.salida}"
    assert funcion.detectados >= 1, resultado.salida
    assert not (proyecto / ".qagent-stryker.json").exists()
    assert fuente.read_text(encoding="utf-8") == codigo

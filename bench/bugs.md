# Registro de Bugs Sembrados en el Banco de Pruebas (MVP)

Este documento detalla los defectos intencionales introducidos en `bench/banco_mvp.py`.
Cada bug presenta un docstring correcto (que define el contrato esperado para el Planner) y un código defectuoso para evaluar la capacidad de detección de los agentes y las pruebas generadas.

---

## Resumen de Funciones y Bugs

| Función | Tipo de Lógica | ¿Tiene Bug? | Tipo de Defecto |
|---|---|:---:|---|
| `calcular_descuento` | Condicional / Aritmética | **Sí** (Bug 1) | Cálculo erróneo: retorna el descuento en vez del total |
| `clasificar_edad` | Condicional / Frontera | **Sí** (Bug 2) | Error de límite (Off-by-one): `<=` en lugar de `<` |
| `buscar_elemento_mayor` | Condicional / Iterativa | **Sí** (Bug 3) | Inicialización inválida para valores negativos |
| `es_palindromo` | Normalización de cadenas | No | Función de control correcta |
| `invertir_palabras` | Manipulación de listas | No | Función de control correcta |
| `formatear_moneda` | Formateo de strings | No | Función de control correcta |

---

## Detalle de Bugs Sembrados

### Bug 1: `calcular_descuento`
* **Archivo:** `bench/banco_mvp.py`
* **Línea:** 28–30
* **Descripción del error:** La función calcula `monto_descuento = precio * (porcentaje / 100.0)` y retorna directamente esa variable, olvidando restar el descuento del precio original.
* **Comportamiento esperado (según docstring):** Con `precio=100.0` y `porcentaje=20.0`, el precio final con descuento debe ser `80.0`.
* **Comportamiento real (código actual):** Retorna `20.0`.
* **Caso de prueba que lo detecta:**
  ```python
  def test_calcular_descuento_normal():
      assert calcular_descuento(100.0, 20.0) == 80.0
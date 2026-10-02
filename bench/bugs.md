# Registro de Bugs Sembrados en el Banco de Pruebas (MVP)

Este documento detalla los defectos intencionales introducidos en `bench/banco_mvp.py`.
Cada bug presenta un docstring correcto (que define el contrato esperado para el agente/planner) y un código defectuoso para evaluar la capacidad de detección de las pruebas generadas.

---

## Resumen de Funciones y Bugs

| Función | Tipo de Lógica | ¿Tiene Bug? | Tipo de Defecto |
|---|---|:---:|---|
| `calcular_descuento` | Condicional / Aritmética | **Sí** (Bug 1) | Cálculo erróneo: retorna el descuento en vez del precio final |
| `clasificar_edad` | Condicional / Frontera | **Sí** (Bug 2) | Error de límite (Off-by-one): `<=` en lugar de `<` |
| `buscar_elemento_mayor` | Condicional / Iterativa | **Sí** (Bug 3) | Inicialización inválida para valores negativos |
| `es_palindromo` | Normalización de cadenas | No | Función de control correcta |
| `invertir_palabras` | Manipulación de listas | No | Función de control correcta |
| `formatear_moneda` | Formateo de strings | No | Función de control correcta |

---

## Detalle de Bugs Sembrados

### Bug 1: `calcular_descuento`
* **Archivo:** `bench/banco_mvp.py`
* **Función:** `calcular_descuento`
* **Descripción del error:** La función calcula `monto_descuento = precio * (porcentaje / 100.0)` y retorna directamente esa variable, olvidando restar el descuento del precio original (`precio - monto_descuento`).
* **Comportamiento esperado (según docstring):** Con `precio=100.0` y `porcentaje=20.0`, el precio final debe ser `80.0`.
* **Comportamiento real (código actual):** Retorna `20.0`.
* **Caso de prueba que lo detecta:**
  ```python
  def test_calcular_descuento_normal():
      assert calcular_descuento(100.0, 20.0) == 80.0
  ```

---

### Bug 2: `clasificar_edad`
* **Archivo:** `bench/banco_mvp.py`
* **Función:** `clasificar_edad`
* **Descripción del error:** Condición de frontera incorrecta (`if edad <= 18:`). Según las reglas de negocio, 18 años cumplidos pertenece a la categoría "adulto", pero la condición lo clasifica como "menor".
* **Comportamiento esperado (según docstring):** Con `edad=18`, debe retornar `"adulto"`.
* **Comportamiento real (código actual):** Retorna `"menor"`.
* **Caso de prueba que lo detecta:**
  ```python
  def test_clasificar_edad_frontera_18():
      assert clasificar_edad(18) == "adulto"
  ```

---

### Bug 3: `buscar_elemento_mayor`
* **Archivo:** `bench/banco_mvp.py`
* **Función:** `buscar_elemento_mayor`
* **Descripción del error:** La variable acumuladora `maximo` se inicializa con el literal `0`. Si la lista está compuesta exclusivamente por números negativos, la condición `num > maximo` nunca se cumple y la función retorna `0`, el cual ni siquiera pertenece a la lista de entrada.
* **Comportamiento esperado (según docstring):** Con `numeros=[-10, -5, -20]`, debe retornar `-5`.
* **Comportamiento real (código actual):** Retorna `0`.
* **Caso de prueba que lo detecta:**
  ```python
  def test_buscar_elemento_mayor_todos_negativos():
      assert buscar_elemento_mayor([-10, -5, -20]) == -5
  ```
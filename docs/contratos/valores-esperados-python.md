# Valores esperados Python no nativos de JSON

## Tuplas (`planner_contract.v2` y `planner_contract.v3`)

JSON no distingue una lista Python de una tupla: ambas se serializan como un array.
Cuando el Planner dispone de una tupla explícita respaldada por el docstring, conserva
los elementos en `valor_esperado` y agrega la metadata opcional:

```json
{
  "id": "dimensiones",
  "entrada": {"alto": 4, "ancho": 3},
  "valor_esperado": [4, 3],
  "tipo_valor_esperado": "tuple",
  "origen": "docstring"
}
```

La anotación `tuple[int, int]` o `typing.Tuple[int, int]` respalda el tipo del
resultado, pero no determina por sí sola los valores `4` y `3`. Para conservar la
metadata, el valor concreto debe aparecer como tupla literal después de `->` en el
docstring. La lectura se realiza con `ast.literal_eval`; nunca se usa `eval` ni se
ejecuta código del proyecto.

## Compatibilidad

- `tipo_valor_esperado` solo admite `"tuple"` y exige que `valor_esperado` sea un
  array JSON.
- Un array sin metadata conserva el significado histórico de lista.
- El campo no se admite en casos de endpoints: sus cuerpos continúan siendo JSON.
- El Generator reconstruye la tupla exterior y genera una igualdad exacta; una tupla
  unitaria se escribe con coma (`(4,)`).
- Reviewer exige que el literal esté comparado con el resultado completo de la función.
  No acepta una lista, longitud, elemento aislado, `is not None` ni un literal ajeno.
- Los intentos con un oráculo inválido no se convierten en referencia para Assertion
  Laundering. Una comparación válida con tupla no se bloquea, pero cambiar una tupla
  por lista o reducir la aserción sigue detectándose como debilitamiento.

La metadata actual describe la tupla exterior. Si en el futuro se necesitan tuplas
anidadas mezcladas con listas, el contrato deberá incorporar metadata recursiva antes
de reconstruir esos niveles; QAgent no los adivina a partir de arrays JSON.

## Otros tipos

`set`, `frozenset`, `bytes`, `Decimal` y `datetime` siguen fuera del alcance de la
issue #145. El campo explícito evita convertirlos implícitamente y deja abierta una
extensión versionada sin cambiar el significado de contratos históricos.

# Rúbrica del Agente Recomendador (SPK #201)

La usa al menos una persona del equipo, por su cuenta, para comparar **a ciegas** la recomendación de las reglas (paso 1) con la del LLM (paso 2) sobre los mismos proyectos. Cada fila de la planilla tiene dos recomendaciones, **A** y **B**, en orden al azar. Quien revisa no sabe cuál es de las reglas ni qué modelo escribió la otra hasta que se puntúan (`medir_recomendador.py --puntuar`).

## Antes de empezar

- Lee primero la columna **hechos** de la fila: es lo que QAgent sabe del proyecto (cuántas funciones y endpoints hay, cuántos con tipos y documentación, cuántos objetivos con decisiones). Es la referencia para decidir si una recomendación sirve o inventa algo.
- Puntúa cada recomendación por sí misma, sin compararla con la otra. La comparación va al final, en **preferida**.
- Imagina a quien la va a leer: alguien que abre un proyecto que no conoce y debe decidir qué pruebas hacer primero.

## Criterio

**Utilidad** (`util_A` y `util_B`), con **1**, **2** o **3**:

| Puntos | Significa |
|---|---|
| **3** | El orden tiene sentido para este proyecto y cada motivo explica, con los hechos, por qué conviene. Me ayuda a decidir |
| **2** | Sirve, pero el orden es discutible o algún motivo es genérico o poco claro |
| **1** | Me confunde, afirma algo que no está en los hechos, deja fuera algo importante o el orden no tiene sentido |

Al final de la fila:

- **Preferida** (`preferida`): `A`, `B` o `igual`. ¿Cuál le darías a la persona del ejemplo?
- **Comentario** (`comentario`): opcional. Una frase sobre lo que más pesó, sobre todo si pusiste un 1.

## Cómo se decide

`--puntuar` junta las planillas, revela qué era cada recomendación y calcula la utilidad promedio y las preferencias de las reglas y de la IA.

Para recomendar `modo = "ia"` por defecto, la IA debería:

1. no tener ningún **1** (un solo caso ya es un riesgo para quien no puede comprobar el motivo);
2. superar a las reglas en utilidad promedio y ser la preferida en la mayoría de las filas;
3. tener un costo y una latencia aceptables para algo que ocurre cada vez que se abre un proyecto (`resumen.md` de la medición);
4. no descartarse con frecuencia (si se descarta casi siempre, se paga la llamada y se usan las reglas).

Si no cumple el punto 1, las reglas siguen por defecto aunque la IA sea la preferida.

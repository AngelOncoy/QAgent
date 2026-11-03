# Rúbrica de calidad del Agente Explicador (SPK #167)

La usan al menos dos integrantes, cada uno por su cuenta, para comparar **a ciegas** la explicación de la plantilla (paso 1) con la del LLM (paso 2) sobre los mismos hallazgos. Cada fila de la planilla tiene dos explicaciones, **A** y **B**, en orden al azar. Quien revisa no sabe cuál es la de la plantilla ni qué modelo escribió la otra hasta que se juntan las planillas (`revision_ciega.py puntuar`).

## Antes de empezar

- Lee primero la columna **Hechos** de la fila: es lo que QAgent sabe del hallazgo (decisión, cada intento con su error y lo que prometía la documentación). Es la referencia para decidir si una explicación es correcta o si inventa algo.
- Puntúa cada explicación por sí misma, sin compararla con la otra. La comparación va al final, en **Preferida**.
- Imagina a quien va a leerla: alguien que programa con ayuda de una IA y no conoce pytest ni lo que es una aserción.
- No consultes con quien revisa en paralelo hasta terminar tu planilla.

## Criterios

Cada criterio se puntúa con **1**, **2** o **3**.

| Criterio | Columna | 3 = bien | 2 = a medias | 1 = mal |
|---|---|---|---|---|
| **Correcta** | `correcta` | Lo que dice coincide con los hechos: qué se esperaba, qué pasó y qué hacer | Tiene una imprecisión menor que no cambia lo que hay que hacer | Dice algo falso de los hechos, o lleva a hacer lo que no corresponde |
| **Se entiende sin saber programar** | `se_entiende` | Frases cortas, sin jerga (pytest, aserción, traceback, fixture, mock…) o con la jerga explicada | Se entiende, pero con alguna palabra técnica sin explicar o una frase confusa | Hace falta saber programar o conocer QAgent para entenderla |
| **No inventa** | `no_inventa` | Todo lo que afirma está en los hechos | Agrega una suposición razonable y la presenta como tal («probablemente…») | Afirma datos, causas, líneas o valores que no están en los hechos |
| **No contradice el veredicto** | `no_contradice` | Explica la decisión de QAgent tal como es | La matiza de una forma que puede confundir (por ejemplo, sugiere que quizá no es un bug cuando la decisión es `bug_detectado`) | La contradice, la pone en duda o propone relajar una comprobación o cambiar el valor esperado |
| **Usa toda la traza de intentos** | `usa_traza` | Tiene en cuenta todos los intentos (por ejemplo: «falló dos veces por lo mismo»), o solo hubo uno | Menciona varios intentos pero se queda sobre todo con el último | Solo habla del último error y omite lo que pasó antes |

Al final de la fila:

- **Preferida** (`preferida`): `A`, `B` o `igual`. ¿Cuál le darías a la persona del ejemplo?
- **Comentario** (`comentario`): opcional. Una frase sobre lo que más pesó, sobre todo si pusiste un 1.

## Cómo se decide

`revision_ciega.py puntuar` junta las planillas, revela qué era cada explicación y calcula, por modelo y para la plantilla:

- el promedio de cada criterio y el promedio general;
- cuántas veces se prefirió la IA, la plantilla o ninguna;
- cuántas veces coincidieron quienes revisaron en la preferida.

Para recomendar `modo = "ia"` por defecto, la IA debería:

1. no tener ningún 1 en **No contradice el veredicto** ni en **No inventa** (un solo caso ya es un riesgo para usuarios que no pueden comprobarlo);
2. superar a la plantilla en **Se entiende** y en **Usa toda la traza**, y además ser la preferida en la mayoría de las filas;
3. tener un costo y una latencia aceptables (`resumen.md` de la medición).

Si la IA no cumple el punto 1, la plantilla sigue por defecto aunque la IA sea la preferida.

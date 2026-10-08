# Lenguaje sencillo para el informe

El informe lo puede leer alguien que no programa (un profesor, un cliente, otro integrante del equipo que no
tocó esa parte). Si una frase obliga a saber programación, no cumple su trabajo. La regla práctica: **di qué
cambia para la persona o para el equipo, no cómo se hizo por dentro.**

## Cambios de palabra habituales

| En vez de… | Escribe… |
|---|---|
| componente, módulo | pieza, parte |
| refactorizar, reestructurar | ordenar, reorganizar |
| interfaz, frontend | pantalla del programa |
| backend | la parte que trabaja por dentro |
| token de diseño, variable CSS | un solo lugar para los colores y letras |
| paleta unificada, ΔE | colores casi iguales que se unieron (sin diferencia que se note) |
| pruebas unitarias, suite, pytest | pruebas automáticas |
| lint, formato | revisión de estilo del código |
| CI, pipeline | revisión automática |
| dependencia | programa o librería que necesita |
| sandbox, contenedor, Docker | entorno aislado donde se ejecutan las pruebas (Docker) — nómbralo una vez y explícalo |
| servidor HTTP interno, petición, conexión rechazada | al abrir, pedía muchos archivos a la vez y algunos no llegaban |
| regresión, merge, rebase, conflicto | cambio que rompe algo antes sano; unir los cambios de otra persona; choque entre cambios |
| cold start | abrir el programa desde cero |
| commit, PR | guardar el cambio; propuesta de cambio para revisión |
| ruta, `src/`, `.env` | carpeta, archivo de configuración (menciona el nombre real solo si ayuda a encontrarlo) |

Los nombres propios del proyecto (un comando, una carpeta, un ID como `ADR-003`) sí pueden aparecer cuando el
lector necesita encontrarlos o ejecutarlos; acompáñalos de una explicación corta la primera vez.

## Cómo escribir cada punto «Se revisó / Se hizo»

- **Se revisó:** el estado de antes, con una cifra medida cuando exista («2070 líneas en un solo archivo»,
  «333 colores escritos uno por uno»). Una frase.
- **Se hizo:** la acción y la mejora, en una o dos frases («se separó en piezas pequeñas… así un cambio toca
  solo la pieza que corresponde»).
- Si una cifra no se midió, no la pongas. Es mejor «varias» que un número inventado.

## Revisión final del texto (antes de entregar)

1. ¿Alguna frase usa un término de la tabla? Reemplázalo.
2. ¿Cada punto se entiende sin haber leído el resto?
3. ¿Hay más de 9 puntos o más de 4 pruebas? Quita lo que no cambie la conclusión.
4. ¿Cada cifra viene de un comando que se ejecutó? Si no, bórrala o mídela.
5. ¿La sección «Para qué» habla del beneficio y no de la técnica?

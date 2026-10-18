# Rediseño de la interfaz de QAgent

Contexto, requerimientos funcionales y prompt para generar propuestas de diseño (Figma, Stitch, Gemini, ChatGPT).

---

## 1. Contexto breve

**QAgent es una aplicación de escritorio que ayuda a los desarrolladores a hacer QA.** Abre un proyecto de código, lo analiza sin ejecutarlo y, con IA, escribe pruebas automatizadas. Luego las ejecuta en un entorno aislado y seguro y entrega un informe claro: qué funciona, qué falla, dónde hay posibles bugs y qué tan buenas son esas pruebas.

Lo que la hace distinta:

- **Las pruebas son confiables.** La IA no puede "hacer trampa" debilitando una prueba para que pase. Si una prueba falla porque el código está mal, QAgent lo reporta como posible bug en lugar de esconderlo.
- **El código del usuario nunca se ejecuta en su máquina.** Todo corre aislado y sin internet.
- **Recuerda el trabajo hecho.** Si el código no cambió, reutiliza lo anterior y gasta menos tokens.
- **Es multi-lenguaje (alcance ampliado).** Python, Java, JavaScript y TypeScript. Las pruebas son unitarias de funciones y de endpoints de APIs, y luego vendrán más tipos.

---

## 2. Requerimientos funcionales (lo que el usuario hace y ve)

### A. Proyectos

1. Abrir un proyecto desde una carpeta local.
2. Clonar un proyecto desde una URL Git (GitHub, GitLab…).
3. Ver los proyectos recientes, reabrirlos y quitarlos de la lista.
4. Saber si un proyecto reciente ya no existe en el disco.
5. Ver el lenguaje (o los lenguajes) que se detectó en el proyecto.

### B. Entender el proyecto antes de probarlo

6. Ver un resumen: cuántos archivos, funciones y endpoints de API hay.
7. Navegar el árbol del proyecto y elegir qué carpetas o archivos incluir.
8. Ver la lista de funciones y endpoints que se pueden probar, con una señal de complejidad (simple o con muchas ramas).
9. Marcar o desmarcar qué se prueba ("seleccionar todo" incluido).
10. Ver qué ya se probó antes y sigue igual, y qué cambió desde la última vez.
11. Ver qué archivos no se pudieron leer y por qué, en lenguaje simple.

### C. Preparar la prueba

12. Elegir qué hacer: generar pruebas nuevas, volver a correr las guardadas (regresión) o hacer un análisis a fondo de las funciones críticas.
13. Elegir el tipo de prueba: unitarias o de endpoints de API.
14. Marcar funciones como críticas. En ellas se mide además qué tan fuertes son las pruebas.
15. Antes de empezar, ver si todo está listo (motor de ejecución activo, IA configurada) y, si falta algo, qué hacer para arreglarlo.

### D. Seguir la corrida en vivo

16. Ver el progreso: en qué paso va (analizando, escribiendo pruebas, ejecutando, revisando) y sobre qué función.
17. Ver los reintentos automáticos (hasta 3) y el motivo de cada uno.
18. Recibir un aviso si la IA intentó debilitar una prueba y eso se bloqueó.
19. Pausar o cancelar la corrida.
20. Ver los tokens gastados acumulados en tiempo real.

### E. Resultados

21. Ver el resultado general: pruebas que pasan, posibles bugs encontrados y cobertura del código.
22. Ver el resultado por función o endpoint: pasó, falló por un posible bug, no se pudo generar, o se acabó el tiempo.
23. Filtrar y buscar resultados por estado, archivo o nombre.
24. En cada función:
    - ver la prueba generada;
    - ver qué se esperaba frente a lo que ocurrió;
    - ver las líneas de código que quedaron sin probar;
    - ver el error completo si hace falta (oculto por defecto).
25. Recibir recomendaciones priorizadas, por ejemplo: "Corrige X en `calcular_total`" o "Agrega casos para el caso vacío".
26. Copiar o guardar las pruebas generadas dentro del proyecto.

### F. Informe

27. Exportar el informe en HTML interactivo, PDF o Markdown, y los datos en JSON.
28. Elegir qué incluir en el informe y dónde guardarlo.
29. Abrir la carpeta de resultados.

### G. Historial

30. Ver las corridas anteriores del proyecto: fecha, tipo, resultado y tokens.
31. Reabrir el informe de una corrida pasada.
32. Comparar con la corrida anterior (mejoró o empeoró).
33. Ver y descargar las pruebas guardadas.

### H. Configuración

34. Conectar el proveedor de IA (clave enmascarada y validada).
35. Ver qué modelo usa cada etapa.
36. Ver el estado del motor de ejecución (activo o inactivo) y cómo iniciarlo.
37. Ajustar límites simples, como el máximo de reintentos y el tiempo máximo por prueba.

### I. Transversal

38. Mensajes de error en lenguaje humano, con una acción para resolverlos.
39. Estados vacíos útiles, como "Aún no hay corridas: empieza aquí".
40. Tokens visibles por corrida y por función. **Nada de costos.**

---

## 3. Lo que debe desaparecer de la vista del usuario

| Hoy se ve | Qué hacer |
|---|---|
| IDs de backlog (`EN-02`, `RN-07`, "metas de la carta") | Eliminar |
| Rutas `.qagent/…`, `~/.qagent/`, `.toml`, `.env` | Eliminar. Como mucho, un botón "Abrir carpeta" |
| Comando `docker run…`, `qagent-sandbox:base`, `pytest 7.4.x` | Eliminar, o dejarlo en un detalle técnico plegado |
| `planner_contract.v2`, "schema", "spec", "huella del código" | "Plan de pruebas", "sin cambios desde la última vez" |
| Planner / Generator / Reviewer | "Analizando → Escribiendo pruebas → Verificando" |
| Assertion Laundering | "Se bloqueó un intento de debilitar una prueba" |
| Mutation Score | "Fortaleza de las pruebas" (con un tooltip que lo explique) |
| Pass Rate | "Pruebas que pasan" |
| Sandbox | "Entorno aislado" |
| Costo por agente, costo total | **Eliminar completamente** |
| "Python 3.11", "Análisis AST", "pytest" fijos | Que dependa del lenguaje detectado |

---

## 4. Prompt para Figma, Stitch, Gemini o ChatGPT

```text
Actúa como diseñador senior de UX/UI especializado en herramientas para desarrolladores (estilo Linear, Vercel, GitHub Desktop, Raycast, Postman). Diseña la interfaz completa de una aplicación de escritorio llamada QAgent. Si puedes generar código, entrega un demo HTML navegable (HTML + CSS + JS en un solo archivo, sin dependencias externas, con datos de ejemplo realistas) donde se pueda recorrer todo el flujo.

## Qué es QAgent
QAgent es una aplicación de escritorio que ayuda a los desarrolladores a hacer QA. El usuario abre un proyecto de código; QAgent lo analiza sin ejecutarlo, usa IA para escribir pruebas automatizadas, las ejecuta en un entorno aislado y seguro (sin internet, sin tocar la máquina del usuario) y entrega un informe claro: qué funciona, qué falla, dónde hay posibles bugs y qué tan buenas son las pruebas.

Diferenciadores que la interfaz debe transmitir:
- Confianza: la IA no puede "hacer trampa" debilitando una prueba para que pase. Si el código está mal, se reporta como posible bug, no se esconde.
- Seguridad: el código se ejecuta aislado.
- Eficiencia: si el código no cambió, se reutiliza el trabajo anterior y se gastan menos tokens.

## Usuario objetivo
Desarrolladores (junior a senior) y equipos de QA. Saben programar, pero NO conocen cómo funciona QAgent por dentro. Quieren respuestas rápidas: "¿mi código está bien? ¿qué arreglo primero?".

## Multi-lenguaje (importante)
La interfaz NO debe estar centrada en Python. Soporta Python, Java, JavaScript y TypeScript, y debe poder crecer a más lenguajes y más tipos de prueba sin rediseñarse. Tipos de prueba actuales: unitarias de funciones y de endpoints de API (por ejemplo FastAPI, Spring, Express/NestJS). Muestra el lenguaje detectado con su ícono y el framework de pruebas correspondiente (pytest, JUnit, Jest/Vitest) como dato secundario. En los datos de ejemplo, mezcla proyectos de varios lenguajes.

## Flujo principal
1. Inicio → 2. Abrir o clonar un proyecto → 3. Explorar el proyecto y elegir qué probar → 4. Preparar la prueba → 5. Seguir el progreso en vivo → 6. Resultados → 7. Exportar el informe. Además, siempre accesibles: Historial y Configuración.

## Funcionalidades que deben verse

Proyectos:
- Abrir una carpeta local o clonar desde una URL Git.
- Proyectos recientes (reabrir, quitar de la lista, aviso si la carpeta ya no existe), con el lenguaje y el resultado de la última corrida.

Explorar el proyecto:
- Resumen: archivos, funciones y endpoints detectados.
- Árbol de carpetas para incluir o excluir partes.
- Lista de funciones y endpoints con una señal de complejidad (simple o con muchas ramas), seleccionables, con "seleccionar todo".
- Indicador de "sin cambios desde la última vez" (se reutiliza) frente a "cambió" (se vuelve a analizar).
- Archivos que no se pudieron leer, con el motivo en lenguaje simple.

Preparar la prueba:
- Elegir qué hacer: "Generar pruebas nuevas", "Volver a correr las pruebas guardadas" (regresión) o "Análisis a fondo de funciones críticas".
- Elegir el tipo de prueba: unitarias o de endpoints de API.
- Marcar funciones como críticas (en ellas se mide además la fortaleza de las pruebas).
- Verificación previa: si falta algo (el motor de ejecución no está activo, la IA no está configurada), mostrar qué falta y un botón para resolverlo. Bloquear el inicio hasta que esté listo.

Progreso en vivo:
- Etapas claras: Analizando → Escribiendo pruebas → Verificando, indicando la función actual.
- Reintentos automáticos (máximo 3) con su motivo.
- Aviso destacado cuando se bloquea un intento de debilitar una prueba.
- Pausar o cancelar.
- Tokens gastados acumulados en tiempo real.

Resultados:
- Resumen arriba: pruebas que pasan, posibles bugs encontrados, cobertura del código y tokens usados.
- Estado por función o endpoint: Pasó / Posible bug en tu código / No se pudo generar la prueba / Tiempo agotado.
- Filtros y búsqueda por estado, archivo o nombre.
- Detalle de cada función: la prueba generada (con resaltado de sintaxis según el lenguaje), lo esperado frente a lo obtenido, las líneas sin probar resaltadas sobre el código, los reintentos y el error técnico completo (plegado por defecto).
- Recomendaciones priorizadas y accionables ("1. Corrige la lógica en calcular_total…").
- Acciones: copiar la prueba, guardar las pruebas en el proyecto, volver a ejecutar solo las fallidas.

Informe:
- Exportar en HTML interactivo, PDF o Markdown, y los datos en JSON. Elegir el contenido y la ubicación. Abrir la carpeta de resultados.

Historial:
- Corridas anteriores (fecha, tipo, resultado, tokens), reabrir un informe, comparar con la corrida anterior (tendencia), ver y descargar las pruebas guardadas.

Configuración:
- Conectar el proveedor de IA (la clave nunca se muestra completa; validar la conexión).
- Modelo usado en cada etapa.
- Estado del motor de ejecución y cómo iniciarlo.
- Límites simples (reintentos máximos, tiempo máximo por prueba).

## Reglas de contenido (obligatorias)
- Lenguaje natural para desarrolladores, nunca jerga interna. PROHIBIDO mostrar: códigos de requerimientos o de backlog, rutas de archivos internos de configuración, nombres de esquemas o versiones de contratos, comandos de terminal, nombres internos de agentes (en lugar de "Planner/Generator/Reviewer", usa "Analizando/Escribiendo/Verificando").
- NO mostrar ningún costo en dinero en ninguna pantalla. Solo tokens gastados (por corrida y por función).
- Términos técnicos inevitables (cobertura, fortaleza de las pruebas/mutación, regresión) llevan un tooltip de una línea.
- La información técnica avanzada existe, pero está plegada ("Ver detalle técnico"), nunca en primer plano.
- Los mensajes de error dicen qué pasó y qué hacer, con un botón de acción.
- Estados vacíos con guía ("Aún no hay corridas. Prueba tu primer proyecto").
- La interfaz está en español.

## Principios de UX/UI
- Divulgación progresiva: primero la respuesta ("3 posibles bugs, empieza por aquí") y luego el detalle.
- Una acción principal clara por pantalla.
- Estados con color + ícono + texto (accesible para daltonismo): éxito, posible bug, error de generación, advertencia, en progreso.
- Modo oscuro por defecto y modo claro opcional, contraste AA, tipografía legible y monoespaciada para el código.
- Navegación persistente (barra lateral o superior) con: Inicio, Proyecto actual, Historial y Configuración. Indicador de estado del motor de ejecución siempre visible.
- Feedback inmediato: skeletons al cargar, progreso visible, nada de pantallas congeladas.
- Diseño de escritorio (ventana de 1280×800 como mínimo) que se adapte a ventanas más pequeñas.
- La identidad debe transmitir confianza y precisión, no "juguete de IA".

## Entregables
1. Mapa de pantallas y flujo de navegación.
2. Diseño de cada pantalla: Inicio, Abrir/Clonar, Exploración del proyecto, Preparar prueba, Progreso en vivo, Resultados (resumen + detalle de función), Exportar informe, Historial, Configuración, y estados de error y vacíos.
3. Sistema visual: paleta como tokens con nombre, tipografía, espaciado, componentes (botones, chips de estado, tarjetas, tablas, modales, toasts).
4. Propón 2 o 3 enfoques de layout distintos para la pantalla de Resultados (por ejemplo: dashboard, lista + panel lateral, vista tipo "bandeja de problemas") y justifica cuál recomiendas.
5. Si generas HTML: navegable de punta a punta con datos de ejemplo de un proyecto TypeScript y otro Python, incluyendo al menos un posible bug, una prueba que no se pudo generar y un intento de debilitar una prueba bloqueado.
```

---

**Consejo para comparar ideas:** pasa el mismo prompt a 2 o 3 herramientas distintas, para comparar enfoques sobre la misma base y no ideas que nacen de instrucciones diferentes.

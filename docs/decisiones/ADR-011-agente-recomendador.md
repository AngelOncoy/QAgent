# ADR-011: Agente Recomendador de pruebas antes de la corrida

- **Estado:** Propuesto (pendiente de aprobación del equipo)
- **Fecha:** 2026-10-29
- **Ítem:** #199 — EN: ADR-011: Agente Recomendador de pruebas y su contrato
- **Responsable:** bel001
- **Relacionado:** ADR-001 (modelos y costos), ADR-007 (adaptadores por lenguaje), ADR-008 (orquestador determinista y Agente Explicador), ADR-010 (arquitectura del Sprint 2), #168 (conectar adaptadores), #197, #200, #201 y EP-15 (#202)

> **Alcance de este ADR.** Define la frontera arquitectónica y el contrato `recommendation.v1`. No implementa el Recomendador, no cambia Vista previa, no agrega llamadas a LLM y no modifica la máquina de estados.

---

## 1. Contexto

Vista previa ya obtiene por análisis estático las funciones, los endpoints, las rutas HTTP resolubles, las ramas y la propuesta de objetivos críticos. Sin embargo, una persona que abre un proyecto nuevo todavía debe decidir qué clases de prueba conviene ejecutar y en qué orden. La elección se vuelve más difícil en proyectos mixtos y cuando cada adaptador de lenguaje tiene capacidades distintas.

El futuro Agente Recomendador —denominado quinto agente por EP-15— cubrirá ese hueco: convertirá un resumen mínimo de Vista previa en una lista priorizada y explicada. No debe vivir dentro del Planner, porque el Planner diseña casos y oráculos después de que el usuario ya eligió qué probar. Tampoco debe entrar en la máquina de estados: ADR-008 reserva las decisiones de flujo al orquestador determinista.

Una recomendación producida por IA introduce riesgos de alucinación, tipos no soportados, costo, latencia, fuga de datos y *prompt injection* desde nombres o rutas controlados por el proyecto. El resultado solo puede orientar la selección; nunca puede ejecutar una acción ni adquirir más autoridad por tener `origen: "ia"`.

La auditoría de `LanguageAdapter` encontró que hoy declara lenguajes y frameworks, pero todavía no expone un conjunto formal de tipos de prueba soportados. Python es el único flujo completo; JavaScript/TypeScript y Java tienen piezas de análisis o sandbox, pero no un flujo operativo completo. La implementación de #197 deberá añadir esa capacidad explícita sin suponer que todos los adaptadores son equivalentes.

## 2. Pregunta

¿Cómo recomienda QAgent tipos de prueba después del análisis estático y antes de una corrida, con razones útiles, sin delegar el flujo a un LLM, sin ofrecer capacidades inexistentes y sin exponer el proyecto completo?

## 3. Opciones evaluadas

| Opción | Cómo funciona |
|---|---|
| **A. Reglas deterministas** | Reglas puras ordenan tipos permitidos a partir del resumen estático y las capacidades declaradas por los adaptadores. |
| **B. Agente LLM independiente** | Un LLM recibe contexto del proyecto y genera directamente tipos y motivos. |
| **C. Híbrida con reglas como autoridad** | Las reglas producen la lista válida y el respaldo; un LLM opcional puede reordenar o redactar motivos solo dentro de esa lista. Toda salida vuelve a validarse. |

### 3.1 Comparación

| Criterio | A · Reglas | B · LLM independiente | C · Híbrida controlada |
|---|---|---|---|
| Seguridad y privacidad | Mejor: no envía datos a terceros | Peor: amplía el contexto y la superficie de inyección | Controlada: resumen mínimo, sanitización y lista cerrada |
| Costo y latencia | 0 tokens e inmediata | Variables en cada Vista previa | 0 tokens por defecto; costo solo en modo opcional |
| Determinismo | Total | Bajo | Total para capacidades y respaldo; variable solo en orden o redacción |
| Compatibilidad multilenguaje | Sigue las capacidades de cada adaptador | Puede inventar soporte | Sigue las capacidades de cada adaptador |
| Testabilidad | Alta, con funciones puras | Requiere dobles y casos de fallos del modelo | Alta para reglas; IA probada con cliente simulado |
| Mantenibilidad | Reglas explícitas que deben evolucionar | Menos reglas, más validación y fallos externos | Mayor complejidad, separada en dos pasos |
| Integración con ADR-008 | Compatible | Incompatible si decide selección o flujo | Compatible porque la autoridad sigue siendo determinista |
| Calidad de motivos complejos | Limitada a plantillas | Flexible | Flexible cuando se habilita IA, con plantilla de respaldo |

La opción A es suficiente para el primer paso (#197). La B se descarta: un resultado libre no puede ser autoridad sobre capacidades ni ejecución. Se adopta la arquitectura C como diseño completo de EP-15, implementada por etapas: reglas obligatorias primero y LLM opcional después (#200), desactivado por defecto hasta medirlo (#201).

## 4. Evidencia

### 4.1 Auditoría arquitectónica

| Componente | Estado actual | Restricción aplicable | Implicación para ADR-011 |
|---|---|---|---|
| Vista previa | `generar_vista_previa()` devuelve módulos, funciones, endpoints, resumen y `critica_propuesta` antes de la corrida | El resumen contiene también `ruta`, que puede ser absoluta y no debe reenviarse | Construir una proyección nueva y mínima; no entregar el objeto completo |
| Orquestador | Máquina de estados determinista para Planner → Generator → Reviewer | ADR-008 impide delegar transiciones, reintentos o cancelación a un LLM | El Recomendador actúa antes de `start_run` y fuera del orquestador |
| ADR-008 | Solo el Reviewer tiene un punto híbrido cerrado para clasificar un fallo | Ningún LLM decide el flujo | La recomendación informa; el usuario confirma y la corrida conserva sus guardas |
| Adaptadores | Declaran lenguaje y frameworks; solo Python tiene flujo completo | Lo específico de lenguaje vive en el adaptador; no existe aún una propiedad formal de tipos soportados | #197 debe añadir una declaración explícita; adaptadores incompletos no anuncian capacidades operativas |
| Contratos | JSON Schema Draft 2020-12, `validar()` y familias en `VERSIONES` | Propiedades cerradas y compatibilidad de versiones | `recommendation.v1` se registra sin cambiar contratos existentes |
| Explicador | Lee resultados cerrados después de la corrida; no altera decisiones | Responsabilidad distinta y posterior al veredicto | El Recomendador no explica fallos: solo prioriza tipos antes de ejecutar |
| Seguridad | Análisis local, claves fuera del repositorio y sanitización antes de un LLM | Mínimo privilegio; no código completo, secretos ni rutas absolutas | La entrada se construye por lista permitida y se trata como datos no confiables |

### 4.2 Identificadores y capacidades comprobadas

El código actual usa `funcion` y `endpoint` para los objetivos y `mutacion` para la capa de profundidad sobre objetivos críticos. Por eso `recommendation.v1` admite exactamente esos tres identificadores. Los tipos aprobados para el futuro —componentes, arquitectura o E2E de humo— no se agregan a v1 hasta que exista un identificador y una capacidad operativa declarada por un adaptador.

Un framework disponible en una imagen o una función parcial del adaptador no equivale a soporte de extremo a extremo. #168 ya conectó el registro y los contratos versionados a la corrida, pero JavaScript, TypeScript y Java continúan con `completo = False`; no deben anunciar capacidades operativas al Recomendador hasta que las épicas de cada lenguaje completen su flujo.

## 5. Decisión

1. **Se adopta la opción C por etapas.** #197 implementará reglas deterministas y será el respaldo permanente. #200 podrá añadir IA opcional. #201 decidirá, con mediciones, si conviene cambiar el modo predeterminado.
2. **El punto de integración es Vista previa:** después de detectar los lenguajes y obtener el resumen de análisis estático, y antes de que el usuario confirme la selección o llame a `start_run`.
3. **El Recomendador queda fuera de la máquina de estados.** No agrega estados ni transiciones y no controla Planner, Generator, Reviewer, reintentos, cancelaciones, presupuesto o veredictos.
4. **El usuario conserva la decisión.** La lista precarga o informa la selección en Vista previa, pero la persona puede aceptarla o cambiarla. Ninguna recomendación inicia una corrida.
5. **Las capacidades son deterministas.** Cada adaptador deberá declarar de forma explícita los tipos de prueba operativos que soporta. La integración compara cada recomendación contra el conjunto elegible del proyecto antes de mostrarla.
6. **`origen: "ia"` no concede privilegios.** Se aplican el mismo schema, la misma validación dinámica y los mismos límites que a `origen: "reglas"`.

### 5.1 Entrada permitida

No se crea un contrato de entrada en #199. La implementación futura debe construir una proyección conceptual con esta información y nada más:

```json
{
  "lenguajes": [
    {
      "lenguaje": "python",
      "tipos_prueba_soportados": ["funcion", "endpoint", "mutacion"]
    }
  ],
  "objetivos": {
    "funciones": {"cantidad": 8},
    "endpoints": {"cantidad": 3, "rutas_http": ["GET /items/{item_id}"]}
  },
  "hay_objetivos_critical": true
}
```

Se permiten lenguajes detectados, tipos y cantidades de objetivos, identificadores mínimos cuando una regla los necesite, rutas **HTTP** de endpoints, existencia de objetivos `critical` y capacidades declaradas por cada adaptador. Los valores controlados por el proyecto se limitan en longitud, se serializan como datos y nunca se interpolan como instrucciones.

Se prohíben código fuente o archivos completos, docstrings o documentación arbitraria, archivos `.env`, variables sensibles, claves, contraseñas, tokens, credenciales, rutas absolutas del sistema, contenido privado innecesario e instrucciones obtenidas del proyecto. Se construye la proyección por lista permitida; no se “limpia” el objeto completo de Vista previa para reutilizarlo. Si se habilita IA, la proyección pasa además por `sanitizar_secretos` antes del cliente LLM.

Una ruta HTTP como `GET /items/{item_id}` es un dato del dominio. No es una ruta de archivos ni una instrucción. Nombres, identificadores y rutas HTTP se delimitan como datos no confiables en el prompt futuro.

### 5.2 Salida versionada

La salida valida contra `recommendation.v1.schema.json`:

```json
{
  "version": "1",
  "origen": "reglas",
  "recomendaciones": [
    {
      "tipo_prueba": "endpoint",
      "motivo": "El análisis estático identificó rutas FastAPI resolubles."
    }
  ]
}
```

- `version` es siempre `"1"`.
- `origen` admite solo `reglas` o `ia`.
- El orden del arreglo representa prioridad; no hay un campo redundante de posición.
- `tipo_prueba` admite los identificadores operativos actuales: `funcion`, `endpoint` o `mutacion`.
- `motivo` es texto no vacío. Describe evidencia del resumen; no contiene órdenes.
- La lista puede estar vacía cuando ningún tipo es elegible.
- Un tipo aparece como máximo una vez. El schema rechaza duplicados aunque cambie el motivo.
- `additionalProperties: false` en ambos niveles impide adjuntar código, veredictos, configuración o acciones como `start_run`.

El schema prueba forma y vocabulario, no capacidades dinámicas. El consumidor de #197 debe calcular el conjunto elegible como la unión de capacidades operativas declaradas por los adaptadores detectados que tengan objetivos aplicables, y rechazar cualquier `tipo_prueba` fuera de él. Para el modo IA de #200, la salida admitida será además un subconjunto de la lista producida por las reglas.

### 5.3 Tratamiento seguro de fallos

1. Se valida primero el JSON con `validar_versionado("recommendation", dato)`.
2. Se comprueba después cada tipo contra las capacidades dinámicas y los objetivos elegibles.
3. Si las reglas producen una salida inválida, se registra el error y se muestra una lista vacía; nunca se inicia una corrida.
4. Si la IA falla, excede el tiempo, devuelve JSON inválido, repite tipos o propone una capacidad no autorizada, se descarta toda su salida y se usa el resultado íntegro de las reglas.
5. Ningún fallo cambia la selección confirmada por el usuario ni bloquea el uso manual de Vista previa.

### 5.4 Límites de responsabilidad

| El Recomendador puede | El Recomendador no puede |
|---|---|
| Priorizar tipos de prueba elegibles y explicar el motivo | Llamar a `start_run`, ejecutar pruebas o escribir archivos del proyecto |
| Usar cantidades, tipos, rutas HTTP y señales `critical` del resumen | Leer el proyecto completo, rutas absolutas, secretos o credenciales |
| Proponer una selección que el usuario confirma o cambia | Cambiar la selección del usuario o la configuración sin confirmación |
| Fallar y volver a reglas o lista vacía | Crear oráculos, aserciones, código de prueba o valores esperados |
| Declarar `origen` para trazabilidad | Modificar veredictos, resultados, cobertura o decisiones del Reviewer |

## 6. Consecuencias

### Positivas

- Vista previa puede orientar a una persona sin introducir decisiones no deterministas en la corrida.
- Las capacidades permanecen en los adaptadores, coherente con ADR-007, y el flujo sigue protegido por ADR-008.
- El contrato cerrado hace auditable la prioridad, el origen y el motivo, sin campos de ejecución.
- El modo de reglas funciona sin red, con 0 tokens y como respaldo ante cualquier fallo futuro del LLM.
- Los contratos existentes y la persistencia histórica no cambian.

### Negativas y compromisos

- #197 debe ampliar la interfaz de adaptadores para declarar capacidades; hoy esa fuente de verdad todavía no existe.
- Mantener reglas y capacidades exige coordinación cuando se agregue un tipo de prueba o un adaptador.
- `recommendation.v1` solo representa los tres identificadores operativos actuales. Los tipos futuros exigirán una evolución explícita del vocabulario y pruebas de compatibilidad.
- La opción híbrida agrega configuración, validación, telemetría y pruebas de fallos en #200.
- Un motivo de reglas puede ser menos natural que uno redactado por IA.
- La utilidad, el costo y la latencia del modo IA no están medidos; #201 debe resolverlo antes de activarlo por defecto.

### Fuera de alcance de #199

- Implementar las reglas, la declaración de capacidades o la integración con Vista previa (#197).
- Agregar clientes, prompts, configuración o llamadas LLM (#200).
- Medir un modelo real o elegir el modo predeterminado (#201).
- Crear pantallas, iniciar corridas, generar pruebas o modificar Planner, Generator, Reviewer u orquestador.

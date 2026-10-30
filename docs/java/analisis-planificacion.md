# Análisis y planificación Java (#181)

## Base reutilizada

El prototipo de #132 ya incorporó `tree-sitter-java==0.23.5`, su carga mediante
`cargar_gramatica`, `JavaAdapter.analizar`, la extracción de parámetros/tipos y
Javadoc literal, y el diagnóstico de fuentes inválidas. Se conserva esa base y
el formato común `Estructura`. No hace falta instalar un JDK ni ejecutar Java
para analizar las fuentes.

#168 aportó los puntos de extensión del adaptador y un Planner compartido que
construye `planner_contract.v3`. El campo de framework del contrato vigente es
`framework_pruebas`; para Java debe valer `junit5`.

## Estructura ampliada

Cada clase conserva una lista `constructores` con las declaraciones explícitas:
firma, línea, parámetros, visibilidad, Javadoc y ramas. Se admiten constructores
sobrecargados como metadatos, distinguibles por su firma. El constructor compacto
de un record toma los parámetros declarados en el record. No se inventan
constructores implícitos ni se convierten los privados en objetivos.

Los métodos públicos permanecen en `funciones`, con las claves del prototipo.
Se añaden `es_static`, `javadoc`, `ramas` y `critical`. `docstring` conserva el
comentario literal; `javadoc` separa descripción, parámetros, retorno, excepciones
y otras etiquetas. `@exception` se trata como alias de `@throws`. El desglose
conserva el texto y no deduce resultados esperados.

`ramas` cuenta if, ternarios, for/for-each, while, do, catch y etiquetas case;
default no añade otra decisión. Cada operador de cortocircuito &&/|| añade un
punto de decisión. No se desciende a clases locales, cuerpos de objetos anónimos
ni lambdas. El conteo describe sintaxis, no cobertura de ejecución.

`critical` vale true cuando `ramas > 0`, tanto en el método como en la salida de
`JavaAdapter.objetivos`. Los seis métodos públicos de TA-01 se conservan, mientras
que sus constructores privados se registran dentro de las clases.

Se mantienen las exclusiones de `target/`, `build/`, `src/test/`, carpetas ocultas
y enlaces simbólicos. Las sobrecargas de métodos públicos siguen rechazándose
con un diagnóstico explícito para evitar objetivos `Clase.metodo` ambiguos.

## Validación del primer bloque

```powershell
python -m pytest tests/lenguajes/test_java.py tests/lenguajes/test_java_estructura.py -q
```

Resultado: 29 pruebas aprobadas. Comprueban la conservación del prototipo,
Javadoc multilínea, constructores públicos/privados/sobrecargados y compactos,
decisiones, criticidad, exclusión de ámbitos internos y de fuentes generadas,
y análisis del banco real TA-01. No usan Docker, JDK ni servicios de IA.

## Mapa de llamadas

`java_llamadas.py` añade `llama_a` después de analizar los archivos válidos del
proyecto. Usa el mismo formato que Python: `ruta/Archivo.java::Clase.metodo`.
Cada lista se ordena y no repite destinos. Se conservan exclusivamente métodos
públicos que figuren en el análisis; la recursión directa se omite.

Se resuelven llamadas de la propia clase y `this`, nombres de tipos del mismo
paquete, clases calificadas e imports explícitos normales y estáticos. También
se reconocen receptores con tipos escritos en parámetros, campos o variables
locales. El índice distingue paquetes y nombres de clases anidadas. La aridad
se contrasta con los parámetros declarados, incluidos varargs; no se eligen
sobrecargas según tipos supuestos.

La resolución es conservadora: variables, parámetros genéricos y tipos locales
pueden ocultar un nombre importado. Un import externo no se sustituye por una
clase homónima del proyecto. No se infieren tipos de `var`, arrays ni llamadas
encadenadas; no se resuelven imports comodín, `super`, referencias de métodos
con `::` ni despacho dinámico. Las llamadas propias de una clase con superclass
explícita se omiten para no elegir entre posibles sobrecargas heredadas.

El mapa expresa destinos declarados que pudieron identificarse, no demuestra
que una lista vacía signifique ausencia de dependencias. Tampoco constituye un
análisis de tipos completo ni sustituye a javac. Las llamadas de lambdas,
clases locales y objetos anónimos no se atribuyen al método exterior.

```powershell
python -m pytest tests/lenguajes/test_java_llamadas.py -q
```

Resultado: 22 pruebas aprobadas. Con las pruebas anteriores de análisis Java,
51 aprobadas. Incluyen llamadas propias y entre archivos, paquetes homónimos,
imports, tipos declarados, sombreado, arrays, varargs, ámbitos internos y el
banco real TA-01. No se compila ni se ejecuta ninguna fuente Java.

## Planificación mediante el adaptador

`JavaAdapter.reglas_planificacion()` entrega `ReglasPlanificacionJava` al
`PlannerAgent` común de #168. No se duplicó el agente ni se añadieron condiciones
por lenguaje a `agents/` u `orchestrator/`. El agente construye los encabezados
`version: "3"`, `lenguaje: "java"` y `framework_pruebas: "junit5"`, conserva
critical y llama_a del análisis y valida con el contrato existente.

El prompt envía nombre, firma, parámetros, retorno y Javadoc funcional. Excluye
el cuerpo del método, comentarios de implementación y etiquetas como @implNote,
que en el banco describen defectos intencionales. Usa los marcadores compartidos
MODULO y OBJETIVOS_JSON para que FakeLLMClient responda con grabaciones controladas.

El modelo propone casos a partir de las reglas naturales del Javadoc. Los filtros
deterministas comprueban la procedencia, la forma de invocación y las
incompatibilidades evidentes de tipos. Un tipo general (int, double, boolean,
String o List) no determina un valor concreto; las propuestas con origen tipo
o firma se omiten si no ofrecen un oráculo verificable. El Javadoc que solo
describe parámetros tampoco respalda un retorno inventado. Una excepción debe
estar documentada en @throws/@exception con sus condiciones.

Las entradas son objetos por nombre de parámetro o listas posicionales; []
representa una llamada sin argumentos. Los arrays se representan con listas.
Para varargs se admite una lista posicional expandida o una lista bajo el nombre
del último parámetro. Se comprueban rangos de enteros, números finitos,
booleanos, strings, char (una unidad UTF-16), arrays y colecciones reconocidas.
Los tipos propios o genéricos no resueltos requieren la especificación funcional;
no se afirma haber comprobado todas sus reglas de construcción.

La validación de procedencia no es una demostración matemática de toda descripción
natural: la interpretación funcional sigue correspondiendo al Planner. No se
calcula el resultado ejecutando ni reinterpretando el cuerpo Java. Cuando no hay
casos respaldados, se utiliza la omisión y su motivo del Planner común, sin forzar
un contrato ni detener los demás objetivos. Humo mantiene un único caso normal.

## Verificación de la planificación

```powershell
python -m pytest tests/agents/test_planner_java.py -q
python -m pytest tests/lenguajes tests/agents/test_planner_java.py -q
```

Resultados: **35 pruebas del Planner Java** y **191 pruebas conjuntas** aprobadas.
Sobre TA-01 se obtuvieron seis contratos válidos, con IA simulada, cero tokens y
costo cero. Los métodos defectuosos conservaron los resultados correctos declarados
en Javadoc: promedio de [2, 3] igual a 2.5, envío desde 100 igual a 0 y total de
100 con impuesto de 18 % igual a 118. No se ejecutaron sus implementaciones.

También se comprobaron omisiones por falta de especificación, argumentos
incompatibles, retornos incompatibles, excepciones no documentadas, perfil Humo
y conservación de critical/llama_a en los contratos.

La revisión general `python test.py -m "not docker and not red"` produjo
**2399 aprobadas, 31 deseleccionadas y dos fallos** en Python 3.10. Lint y formato
pasaron. Los fallos son los casos de comprensión de diccionario y `Generic[*Ts]`
de `tests/analysis/test_texto_ts.py`, ya reproducidos en el commit base `6d761ce`
durante #180 y comunicados al equipo. No se modificaron ni se omitieron esas
aserciones. No se presenta esta revisión general como totalmente satisfactoria.

## Alcance de #181

Se completan análisis y planificación Java. El adaptador continúa con
`completo=False`: generación con guardrail, ejecución y revisión pertenecen a las
otras partes de EP-12a. No se requieren JDK, Maven, Docker ni una API real de IA
para las comprobaciones de esta entrega. No se añaden reglas para endpoints Spring.

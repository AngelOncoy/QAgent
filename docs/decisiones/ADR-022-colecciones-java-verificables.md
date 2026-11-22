# ADR-022: Unificar las colecciones Java verificables

- Fecha: 2026-11-21.
- Estado: Propuesta implementada para revisión mediante PR; requiere aprobación del equipo.
- Issue: #300. Épica histórica EP-12 (#174), sin reabrirla.
- Relacionados: ADR-007/008/009, ADR-018/019; #295 y #298.

## Problema

El Planner aceptaba un array JSON como esperado de Set, pero el guardrail solo
reconocía List.of. El Generator no disponía de una representación común. Aceptar
cualquier expresión que parezca una colección permitiría cambiar sus miembros,
su orden significativo o los tipos boxed y presentar un fallo artificial.

## Decisión y matriz de capacidades

La capacidad reside en el adaptador Java. `java_colecciones.py` define tipos,
compatibilidad y representación; planificación, contexto del Generator y oráculo
consultan esa misma matriz. El orquestador sigue siendo determinista y los
agentes siguen comunicándose por contratos JSON.

| Tipo declarado | Representación JSON no nula | Igualdad demostrable |
|---|---|---|
| `java.util.List<T>` | Array ordenado; permite duplicados | `assertEquals` con una List |
| `java.util.Set<T>` | Array de miembros únicos según igualdad del tipo; orden irrelevante | `assertEquals` con un Set |
| `java.util.Collection<T>` / `java.lang.Iterable<T>` | Array en orden de iteración documentado | `assertIterableEquals` con una List |

Los nombres simples requieren origen estándar demostrable; se rechazan imports
que los sustituyan, homónimos locales o vecinos y comodines ajenos no resueltos.
Para Collection/Iterable con más de un elemento se exige una declaración de
orden en Javadoc y se rechaza su negación explícita. Este filtro conservador de
texto no demuestra automáticamente toda especificación en lenguaje natural.

`T` admite String, Boolean, Byte, Short, Integer, Long, Character, Float y Double
de java.lang. List y Set pueden anidarse con igualdad de valor Java. Bajo
Collection/Iterable se admiten List anidadas, pero no Set: JUnit compara
recursivamente la iteración de los elementos Iterable y no probaría igualdad de
conjunto. No se habilitan Map, colecciones crudas, wildcards, arrays u objetos
arbitrarios dentro de colecciones, ni Collection/Iterable anidadas.

`null` de colección conserva el JSON null y exige assertNull sobre la llamada.
Cada colección puede contener null, salvo duplicados de null en Set. La matriz
solo construye fábricas cuya semántica admite sus elementos: List.of/Set.of sin
null; Collections.singletonList/singleton para un único null; Arrays.asList y
HashSet(Arrays.asList(...)) para múltiples elementos con null. Arrays.asList(null)
sin tipo explícito no representa una lista de un null: se rechaza. Vacíos usan
List.of()/Set.of(). No se ordena ni deduplica el contrato.

Los enteros respetan su rango. Long, Float y Double conservan sus sufijos; Byte
y Short solo admiten casts primitivos acotados; Character exige un literal char
BMP válido. Se rechazan NaN, infinitos, desbordamientos, subdesbordamiento a cero
y cero flotante negativo en el subconjunto de colecciones. El guardrail compara
el literal con el JSON y su tipo nominal, no solo su valor decimal. Una fábrica
con tipo cambiado, identidad (`assertSame`), sujeto distinto, entradas cambiadas
o miembros modificados sigue siendo inválida.

El AST reconoce únicamente fábricas declaradas de java.util y constructores
HashSet/LinkedHashSet con una List verificable. Los nombres de las fábricas
también requieren imports coherentes y no pueden ser variables que oculten el
paquete. No se ejecutan helpers, constructores ni fuentes para deducir esperados.
Las sobrecargas List/Set requieren imports explícitos o tipos calificados e
invocaciones de tipo exacto verificable bajo ADR-019. No se ofrecen los Set de
entrada sobrecargados cuya fábrica canónica necesita HashSet por contener null
con varios miembros: no demuestra el despacho a Set frente a HashSet. Tampoco
se ofrecen Collection/Iterable sobrecargados ni varargs de colecciones. Los
nombres de firmas históricos con comodines conservan sus claves sin calificarse.

## Contratos y compatibilidad

Set se representa mediante el array JSON existente, interpretado con la firma.
No cambian schemas, versiones ni datos históricos. La representación Java
canónica se añade al contexto estático del Generator y no modifica los casos del
Planner. Un tipo no representable se filtra antes de generar pruebas.

Las reglas previas de arrays, String/CharSequence y builders permanecen bajo sus
guardrails. No se amplía inferencia a endpoints Spring ni se cambia su plantilla.
Los casos inferidos Java conservan su clasificación de regresión/hallazgo a
revisar. No cambian límites, presupuestos, configuración, JDK ni dependencias.

## Validación y consecuencias

La regresión mínima conserva List y permite Set. La matriz se contrasta en las
tres etapas y con pruebas negativas de entradas, miembros, orden, tipos y
procedencia. JUnit se ejecuta en Docker offline con las restricciones actuales,
fuentes originales intactas e IA grabada sin tokens. Las pruebas reales incluyen
colección correcta, defecto de contenido, null, vacíos, tipos boxed y anidación;
el informe de #300 registra comandos y resultados ejecutados.

El subconjunto es intencionalmente conservador: expresiones equivalentes fuera
de las fábricas declaradas pueden rechazarse. No se promete soporte de cualquier
implementación de Collection ni prueba matemática de su Javadoc.

## Referencias

- [Java 25: Set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html).
- [Java 25: List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html).
- [JUnit 5.14.4: Assertions](https://docs.junit.org/5.14.4/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html), semántica de assertIterableEquals.

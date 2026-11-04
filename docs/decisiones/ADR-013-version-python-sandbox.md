# ADR-013: Selección de la versión de Python del sandbox según el proyecto

- **Estado:** Propuesto (Sprint 2)
- **Fecha:** 2026-11-03
- **Ítem:** EN — Elegir la versión de Python del sandbox según el proyecto
- **Responsable:** Equipo QAgent
- **Relacionado:** ADR-003 (frontend modular), ADR-007 (adaptadores por lenguaje, EN-17), ADR-008 (orquestador determinista y Agente Explicador), ADR-010 (arquitectura del Sprint 2), ADR-012 (#231), `docs/arquitectura.md`

---

## 1. Contexto

Hasta ahora el sandbox de Python de QAgent utilizaba de manera fija la imagen `python:3.11-slim` (`qagent-sandbox:base`), independientemente de la versión requerida por el proyecto del usuario. Esto causaba dos problemas graves:

1. **Incompatibilidad sintáctica:** Proyectos modernos que usan sintaxis de Python 3.12 o posterior (ej. `type Alias = ...`, genéricos en funciones `def f[T](x: T) -> T`) fallaban dentro del contenedor con `SyntaxError`, haciendo que el Reviewer y el usuario percibieran un error de la prueba o del código cuando en realidad el proyecto era válido.
2. **Incompatibilidad de dependencias:** Dependencias con especificaciones estrictas (`requires-python >= 3.12`) no podían instalarse con `pip` durante el Paso 1 (`preparar_imagen`).

Por otro lado, no es viable admitir cualquier versión arbitraria de Python sin restricciones: cada versión exige una imagen base Docker de cientos de MB en disco, debe validarse en CI y bancos de pruebas, y tree-sitter debe entender su sintaxis.

## 2. Pregunta

¿Cómo seleccionar y aprovisionar la versión de Python adecuada para el contenedor de pruebas del sandbox de manera predecible, determinista y estática, sin romper las imágenes existentes ni requerir múltiples JDKs en Java?

## 3. Opciones evaluadas

| Opción | Descripción | A favor | En contra |
|---|---|---|---|
| **A. Rango soportado declarado (Python 3.10–3.14) con detección estática** | Configurar en `config.toml` un rango soportado (3.10–3.14), detectar la versión en el proyecto (.python-version, pyproject.toml, setup.cfg) y usar la imagen base correspondiente. Detener la corrida antes de construir si no está en el rango. | Control total del tamaño en disco, validación estática temprana, reproducibilidad, sin falsos positivos en el Monitor. | Requiere etiquetado de imágenes base (`base-py3.12`) e incorporar la versión en el hash de dependencias. |
| **B. Aceptar cualquier versión de Python de Docker Hub** | Tomar cualquier versión encontrada y construir `python:<versión>-slim`. | Máxima flexibilidad aparente. | Descargas inesperadas de versiones no probadas (ej. Python 3.8 o 3.15 alpha), posibles fallos en librerías nativas y falta de soporte en la gramática. |
| **C. Mantener imagen única fija en 3.11** | La solución previa. | No requiere cambios en la infraestructura Docker. | Incompatible con Python 3.12+ y dependencias modernas. |

## 4. Decisión

**Se adopta la Opción A.** Se implementan las siguientes reglas y mecanismos:

### 4.1 Rango soportado y versión por defecto

- **Rango soportado:** Python **3.10, 3.11, 3.12, 3.13 y 3.14**.
- **Versión por defecto:** **3.11** (preserva la compatibilidad exacta con instalaciones existentes).
- **Configuración centralizada:** La lista de versiones soportadas y la versión por defecto se declaran en `src/qagent/config/config.toml` bajo `[sandbox]` (`versiones_python = [...]`, `version_python_por_defecto = "3.11"`) y `[sandbox.python]`. Ningún valor está hardcodeado en la lógica de decisión.

### 4.2 Orden de detección de la versión

La detección es **exclusivamente estática** (sin ejecutar código del usuario) y se implementa en el adaptador de Python (`qagent.lenguajes.python_version`), respetando el orden de precedencia:

1. `.python-version` (archivo de pyenv, uv, asdf, mise, etc.). Se extrae el major.minor (ej. `3.12.3` -> `3.12`).
2. `requires-python` en la sección `[project]` de `pyproject.toml` (PEP 621).
3. `python_requires` en la sección `[options]` de `setup.cfg`.
4. Si ninguno de los archivos anteriores está presente o define la versión, se adopta la versión por defecto (**3.11**).

### 4.3 Regla de elección para rangos

Cuando el proyecto declara un rango o especificador de versión (ej. `>=3.10`, `>=3.10, <3.13`, `~=3.11.0`):
- Se filtran las versiones de la lista soportada que satisfacen el especificador.
- **Se elige la versión más alta de la lista que lo cumpla.** Por ejemplo:
  - Para `>=3.10`: cumple `[3.10, 3.11, 3.12, 3.13, 3.14]` -> se elige **3.14**.
  - Para `>=3.10, <3.13`: cumple `[3.10, 3.11, 3.12]` -> se elige **3.12**.
  - Para `>=3.12`: cumple `[3.12, 3.13, 3.14]` -> se elige **3.14**.
- Para evaluar los especificadores PEP 440 de forma canónica y robusta, se incorpora la dependencia `packaging>=21.0` en `pyproject.toml`.

### 4.4 Tratamiento de versiones fuera de rango

Si la versión detectada no está en la lista soportada o si ninguna versión soportada satisface el rango requerido (ej. `<3.10` o `>=3.15`):
- La corrida se **detiene inmediatamente antes de intentar construir imágenes Docker o invocar a los agentes LLM**.
- El Monitor emite un evento con estado de error claro indicando la versión que pidió el proyecto y el rango soportado por QAgent:
  `El proyecto requiere Python <versión>, pero QAgent soporta Python 3.10–3.14 (3.10, 3.11, 3.12, 3.13, 3.14).`
- QAgent **nunca cae silenciosamente a 3.11** si el proyecto pidió otra versión fuera del rango.

### 4.5 Etiquetado de imágenes base y hash de imágenes derivadas

- **Imagen base por defecto (3.11):** Conserva la etiqueta `qagent-sandbox:base` para no invalidar las imágenes ya existentes en los entornos de los desarrolladores.
- **Imágenes base versionadas:** Se etiquetan como `qagent-sandbox:base-py<versión>` (ej. `qagent-sandbox:base-py3.12`, `qagent-sandbox:base-py3.10`).
- **Construcción:** `Dockerfile` utiliza `ARG PYTHON_VERSION=3.11` y `FROM python:${PYTHON_VERSION}-slim`, pasando `buildargs={"PYTHON_VERSION": version}` durante la construcción.
- **Aislamiento de caché en derivadas:** El hash de la imagen con dependencias (`etiqueta_para_dependencias` y `etiqueta_para_requirements`) incluye la versión de Python cuando no es la por defecto, asegurando que proyectos con idéntico `requirements.txt` pero distinta versión de Python no compartan ni reutilicen indebidamente la misma imagen derivada.

### 4.6 Por qué Java no cambia

A diferencia de Python (cuyo intérprete cambia su gramática y comportamiento sintáctico en cada release menor), Java utiliza una única imagen base con JDK 25 (`eclipse-temurin:25-jdk-noble`). Gracias a la opción `--release` del compilador `javac` (`maven.compiler.release` en `pom.xml`), el JDK 25 puede compilar y ejecutar código dirigido a Java 8 hasta 25 de forma nativa sin requerir múltiples imágenes base en el sandbox. Si en el futuro apareciera un proyecto con incompatibilidades estrictas a nivel de JVM, se abordará mediante un ADR específico.

---

## 5. Consecuencias

### Positivas
- Soporte nativo para proyectos que utilizan características modernas de Python 3.12+ (tipos `type`, generic functions, etc.).
- Sin fallos crípticos por dependencias que exigen Python 3.12+.
- Mensajes de error claros y pedagógicos en el Monitor cuando un proyecto pide una versión incompatible, sin consumir tokens ni compilar innecesariamente.
- Preservación total de compatibilidad con imágenes base e imágenes de dependencias existentes de Python 3.11.

### Negativas / Mitigaciones
- Un equipo que ejecute proyectos con múltiples versiones de Python descargará una imagen base por versión requerida. Se mitiga porque cada imagen base se construye solo bajo demanda (la primera vez que un proyecto de esa versión la necesita).
- Se incorpora la dependencia `packaging>=21.0` en `pyproject.toml`. Se mitiga porque `packaging` es una librería sin dependencias externas, estándar en el ecosistema PyPA y ampliamente probada.

# Desarrollo de QAgent

Guía para el equipo: preparar el entorno, ejecutar las pruebas, construir el instalador y publicar una versión. La portada para usuarios es el [README](../README.md); las reglas del proyecto están en [AGENTS.md](../AGENTS.md).

## Preparar el entorno

Requisitos: Windows 10/11, Python 3.10+, Git y Docker Desktop.

```bash
git clone https://github.com/AngelOncoy/QAgent.git
cd QAgent
python -m venv .venv
.venv\Scripts\activate          # en Linux: source .venv/bin/activate
pip install -e .[dev]           # en Linux, para la ventana: pip install "pywebview[qt]"
python test.py
```

### Versión de Python del equipo

El equipo desarrolla, construye y publica con **Python 3.13.17** (`.python-version` en la raíz; los workflows de CI usan la misma). Es la última 3.13 con instalador de Windows: no subas a la 3.13.18 sin comprobar que lo trae. Esto es solo el entorno del equipo: QAgent sigue admitiendo Python 3.10+ (`requires-python = ">=3.10"`), así que en el código no uses APIs que 3.10 no tiene (`tomllib`, `StrEnum`, `ExceptionGroup`…) y no agregues `target-version = "py313"` a Ruff.

Un `.venv` no se actualiza en el lugar: se recrea.

```bash
deactivate                      # si está activo
rmdir /s /q .venv               # Linux: rm -rf .venv
py -3.13 -m venv .venv          # confirma con: .venv\Scripts\python --version  → 3.13.17
.venv\Scripts\activate
pip install -e .[dev]
python test.py
```

`scripts/construir_windows.py` avisa si se ejecuta con otra versión.

`pip install -e` deja el programa instalado apuntando a esta carpeta: los cambios en el código se ven sin reinstalar. Si vienes de una versión anterior a TA-06, desinstala antes el nombre viejo: `pip uninstall -y qagent`.

### Tus datos viven en `~/.qagent/`

| Archivo | Para qué sirve |
|---|---|
| `.env` | Claves de API (una variable por agente, p. ej. `GEMINI_API_KEY_PLANNER` u `OPENAI_API_KEY_EXPLICADOR`; las cuatro son obligatorias con la IA real). Se crea solo, vacío, la primera vez. `.env.example`, en la raíz del repositorio, lista las variables de cada proveedor sin valores. |
| `config.local.toml` | Modelos que eligió cada uno en la pantalla Configuración; reemplazan a los del `config.toml` del equipo. |
| `recientes.json` | Proyectos recientes de la pantalla de inicio. |
| `registro.log` | Bitácora de la corrida cuando la app se abre sin consola (el ejecutable de Windows). |
| `demo/` | Corrida de demostración. |

`~` es tu carpeta de usuario (`C:\Users\<tú>`). El programa nunca escribe en su propia carpeta (ADR-005). Si antes tenías `.env` o `config.local.toml` en la raíz del repositorio, se mueven solos a `~/.qagent/` al abrir `qagent`.

Los modelos y precios del equipo están en `src/qagent/config/config.toml` (se versiona, sin claves). Para probar los modelos y las claves: `python -m qagent.llm.validar` (`--gratis` lista los modelos sin costo de OpenRouter).

## Pruebas

`python test.py` ejecuta **todas** las pruebas, siempre con la IA simulada (no gasta tokens ni llama a ninguna API):

```bash
python test.py                 # lint (ruff) + formato + todas las pruebas, menos las de Docker real
python test.py --docker        # también las de Docker real (ver abajo)
python test.py --rapido        # sin lint y sin las pruebas de Docker ni de internet
python test.py --sin-lint      # solo pytest
python test.py -k clonador     # cualquier otro argumento se pasa a pytest
```

Las de `tests/frontend/` comprueban que la interfaz esté bien armada.

### Pruebas con Docker real (#250)

Las pruebas marcadas `docker` son las únicas que comprueban el sandbox de verdad: aislamiento sin red, JUnit y JaCoCo, PIT y Stryker, Playwright y las librerías del sistema. Por eso son caras: con todas, la suite pasa de unos 100 segundos a unos **15 minutos** y construye cerca de **10 GB** de imágenes (`req-…`, `java-…`, `node-…`, `browser-…`, `qagent-sandbox:java`, `node`, `navegador`…). No corren solas aunque Docker Desktop esté abierto: se piden.

```bash
python test.py --docker                       # todo, incluidas las de Docker real
python test.py --sin-lint --docker -m docker  # solo las de Docker real
python test.py --docker --conservar-imagenes  # no borra las imágenes: la próxima corrida es más rápida
pytest --docker tests/sandbox/test_pit_docker.py   # también con pytest; -m docker las activa igual
```

**Cuándo correrlas:** al tocar `src/qagent/sandbox/` (ejecución, imágenes, Dockerfiles, límites), los adaptadores de Java o JS/TS en lo que llega al contenedor, la mutación (mutmut, PIT, Stryker) o el E2E con Playwright. Para el resto de los cambios basta `python test.py`.

Antes de empezar, pytest avisa cuántas son y cuánto tardan. Antes de la primera, **reconstruye las imágenes base que tengas y estén viejas**: cada imagen base guarda en el label `qagent.receta` la huella de su Dockerfile y sus recursos, y si la receta cambió desde que se construyó (o la imagen es anterior a #250 y no tiene el label), se vuelve a construir. Sin esto, una `qagent-sandbox:java` de antes de #185 no trae ArchUnit y Maven offline falla al compilar: las pruebas de Java, PIT y arquitectura fallaban por el entorno, no por el código. La primera corrida con `--docker` tras #250 reconstruye todas las imágenes base que tengas (una sola vez); el resumen final lista las que reconstruyó. Las imágenes derivadas (`java-…`, `req-…`) no se revisan: si una falla tras reconstruir su base, bórrala con `docker rmi`. Al terminar borra las imágenes de `qagent-sandbox` que **esa corrida creó** (compara las de antes y las de después) y lista cuáles borró. Nunca borra las que ya existían, ni `qagent-sandbox:base`, ni imágenes de otros repositorios (`node`, `eclipse-temurin`… que Docker descargó). Si Docker no responde, las pruebas se omiten y no se borra nada.

El workflow **Pruebas con Docker real** (`.github/workflows/pruebas-docker.yml`) las corre cada lunes sobre `develop` y a mano desde Actions > Run workflow, en un runner que se descarta al terminar.

**Limpiar Docker a mano.** Para ver qué ocupa espacio y borrar lo que sobra:

```bash
docker system df                              # imágenes, contenedores y caché de build
docker images qagent-sandbox                  # imágenes del sandbox
docker rmi qagent-sandbox:req-<hash>          # borra una imagen derivada (se reconstruye si hace falta)
docker builder prune                          # caché de build
```

Borrar imágenes no achica el disco virtual de Docker Desktop (`docker_data.vhdx`, en `%LOCALAPPDATA%\Docker\wsl\disk\`): el espacio queda libre dentro, pero el archivo no se reduce solo. Para recuperarlo en Windows, cierra Docker Desktop, ejecuta `wsl --shutdown` y compáctalo con `Optimize-VHD -Path <ruta>\docker_data.vhdx -Mode Full` (PowerShell como administrador, requiere Hyper-V) o con `diskpart` (`select vdisk file="<ruta>\docker_data.vhdx"`, `attach vdisk readonly`, `compact vdisk`, `detach vdisk`).

Para abrir la aplicación con la IA simulada (sin claves ni gasto), agrega `QAGENT_FAKE_LLM=1` a `~/.qagent/.env` o define `set QAGENT_FAKE_LLM=1` (Linux: `export QAGENT_FAKE_LLM=1`) antes de abrirla. El nombre anterior, `PYAGENT_FAKE_LLM`, se sigue aceptando.

### Lo que la app pone al día sin reiniciar (#251)

Con QAgent abierto, estos cambios se notan solos, sin reabrir el proyecto:

| Si cambias… | Cuándo se nota |
|---|---|
| Docker Desktop (lo abres o lo cierras) | En la siguiente consulta del motor (cada 15 s) o al volver a la ventana; Preparar vuelve a comprobar el entorno y se desbloquea. |
| `QAGENT_FAKE_LLM` en `~/.qagent/.env` | Igual que el motor. No cambia a mitad de una corrida. Si la variable está definida en el sistema (`set`/`export`), manda el sistema y el `.env` no la cambia: para eso hay que cerrar la terminal y abrir QAgent de nuevo. |
| Claves escritas a mano en el `.env` | Igual que el motor: la consola las oculta desde que se guarda el archivo. |
| Git instalado con la app abierta | Al pulsar Comprobar de nuevo o volver a la ventana: QAgent lo busca en `Program Files\Git\cmd`, `%LOCALAPPDATA%\Programs\Git\cmd` y el `PATH` del registro, aunque el proceso no lo herede. Si lo instalaste en otra carpeta que no está en el `PATH`, reinicia QAgent. |
| El código del proyecto | Con **Volver a analizar** en Explorar (conserva la selección, la pestaña y la búsqueda). |
| Las pruebas guardadas | Al terminar una corrida, «Volver a correr las guardadas» se habilita solo. |
| Docker apagado al abrir QAgent | La limpieza del sandbox (ver «Espacio en disco y limpieza del sandbox») se hace cuando Docker responde, nunca durante una corrida. |

### Compatibilidad de las pruebas del analizador con Python (#214)

`texto_ts` normaliza expresiones con el formato de Python 3.11, independientemente
del intérprete que ejecute QAgent. Sus pruebas conservan las comparaciones exactas
con `ast.unparse`, salvo los dos casos con comprobaciones propias por versión:

- La comprensión `{k: v for k, v in d.items()}` mantiene ese texto exacto en
  tree-sitter. Python 3.10 añade paréntesis a `(k, v)` al usar `ast.unparse`;
  se verifica el texto esperado de cada versión y la igualdad de los árboles AST
  del original, de la salida normalizada y de la referencia.
- `Generic[*Ts]` siempre se valida con tree-sitter y debe producir
  `Generic[*Ts,]`. En Python 3.10 se exige `SyntaxError` al analizar ambas formas
  con `ast.parse`; desde 3.11 se exige igualdad con `ast.unparse` y equivalencia
  de los árboles AST. No se omite el caso con `skip` ni `xfail`.

La documentación de [ast.unparse](https://docs.python.org/3.11/library/ast.html#ast.unparse)
define la equivalencia del AST, sin garantizar el mismo texto original. Los
[subíndices desempaquetados](https://docs.python.org/3.11/reference/expressions.html#subscriptions)
se admiten en Python desde 3.11.

Validación del 30 de octubre de 2026, sobre la rama `fix/214-compatibilidad-python310`:

| Intérprete | pytest | tree-sitter / tree-sitter-python | `tests/analysis` |
|---|---|---|---|
| CPython 3.10.10 | 9.1.1 | 0.24.0 / 0.23.6 | 125 aprobadas en 31.48 s |
| CPython 3.11.17 | 9.2.0 | 0.24.0 / 0.23.6 | 125 aprobadas en 17.04 s |
| CPython 3.12.10 | 9.2.0 | 0.24.0 / 0.23.6 | 125 aprobadas en 27.78 s |

La ejecución posterior capturada por el integrante confirmó 125 aprobadas en cada
versión: 10.62 s en 3.10.10, 7.54 s en 3.11.17 y 6.54 s en 3.12.10.

El archivo afectado conserva sus 50 casos: antes daba 2 fallidas y 48 aprobadas en
Python 3.10; después produjo 50 aprobadas (también confirmado por el integrante,
27.25 s). La regresión de 125 pruebas incluye esos 50 casos. No se modificó el
analizador ni se elevó la versión mínima de Python del proyecto.

Para reproducir, activar un entorno con las dependencias `.[dev]` en cada versión:

```powershell
python --version
python -m pytest tests/analysis/test_texto_ts.py -q
python -m pytest tests/analysis -q
```

Se usó `.venv` para 3.10 y entornos aislados `.qagent/venv311` y
`.qagent/venv312` para 3.11 y 3.12. Son locales, están ignorados por Git y no se
distribuyen con QAgent. Lint, formato del archivo corregido y `git diff --check`
también aprobaron. No se ejecutaron Docker, APIs de IA ni código del usuario.

## Sandbox Docker

Las pruebas generadas se ejecutan solo dentro de un contenedor efímero: sin red, con 4 CPU (o los que tenga Docker, si son menos), 3 GB de memoria y 120 s como máximo (EN-03). Esos límites los define el equipo en `[sandbox]` de `src/qagent/config/config.toml`, con memoria y tiempo propios de JavaScript, TypeScript y Java en `[sandbox.<lenguaje>]` (#169; ver `docs/arquitectura.md`, sección 7); no son un ajuste del usuario final, así que `~/.qagent/config.local.toml` no los cambia. La imagen base `qagent-sandbox:base` se construye sola en la primera corrida real (necesita internet). Para construirla antes, con Docker Desktop abierto:

```bash
python -c "from qagent.sandbox import construir_imagen_base; construir_imagen_base()"
```

Una imagen base que ya existe no se reconstruye sola al cambiar su Dockerfile durante una corrida de la app (las pruebas con `--docker` sí lo hacen, ver «Pruebas con Docker real»). Para saber si la tuya está vieja: `python -c "from qagent.sandbox import obtener_cliente; from qagent.sandbox.imagen import imagen_desactualizada; print(imagen_desactualizada(obtener_cliente(), 'qagent-sandbox:java'))"`. Tras #171 (componentes React), `qagent-sandbox:node` debe traer jsdom y Testing Library; si es anterior, se reconstruye con:

```bash
python -c "from qagent.sandbox import construir_imagen_base; from qagent.sandbox.modelos import IMAGEN_NODE; construir_imagen_base(imagen=IMAGEN_NODE)"
```

## Espacio en disco y limpieza del sandbox (#267)

Docker guarda imágenes, capas y caché en un disco virtual. En Windows ese disco (`docker_data.vhdx`) **no se achica solo**: crece en `C:` y, aunque se borre contenido dentro de Docker, `C:` no recupera el espacio hasta compactarlo. En una prueba real con IA y un proyecto de `bench/` llegó a 23,4 GB y Docker dejó de responder. La causa eran cinco huecos; esta es la política que los cierra.

### Qué se limpia y cuándo

`qagent.sandbox.limpieza.limpiar_al_iniciar` (la limpieza automática) corre en segundo plano **al abrir la app y al terminar cada corrida** (aunque haya fallado), nunca durante una corrida. Una sola a la vez. Si Docker no responde, queda pendiente y se reintenta cuando el motor responda (#251). Nunca lanza excepciones ni bloquea el arranque, y un paso que falla se anota en el registro sin impedir los demás. Sus pasos, en orden:

| Paso | Qué borra | Cómo reconoce lo suyo |
|---|---|---|
| 1. Corridas interrumpidas | Contenedores de ejecución detenidos, o que siguen corriendo hace más de 1 h | label `qagent=sandbox` |
| 2. Construcciones cortadas | Contenedores intermedios de un `docker build` cancelado, con la app cerrada o con Docker caído (en la prueba real, uno de 6,26 GB por un `pip install`) | label `qagent=construccion`, y solo si tienen más de 1 h (pueden ser de otra ventana de QAgent) |
| 3. Capas sin nombre | Imágenes sin tag que dejaron esas construcciones | label `qagent=construccion`, sin tag y de más de 1 h |
| 4. Imágenes sin uso | Imágenes derivadas (`req-`, `node-`, `java-`, `browser-`) sin uso en 30 días | repositorio `qagent-sandbox` |
| 5. Tope de espacio | Imágenes derivadas, de la menos usada a la más usada, hasta quedar bajo `tope_imagenes_derivadas_gb` | repositorio `qagent-sandbox` |

Toda construcción de QAgent lleva el label `qagent=construccion` (`ETIQUETA_CONSTRUCCION` en `sandbox/modelos.py`); Docker lo copia a los contenedores y capas intermedios del build, y así se reconocen los que quedan a medias. Las que se construyeron antes de #267 no lo tienen y no se pueden reconocer: no se tocan.

### Qué nunca se borra

- Lo que no lleve un label de QAgent ni esté en el repositorio `qagent-sandbox`: el usuario tiene otras imágenes, contenedores y volúmenes (postgres, node, etc.) en el mismo Docker. No se usa `docker system prune` ni ningún `prune` de contenedores, volúmenes o redes.
- Las imágenes base (`base`, `base-pyX.Y`, `node`, `java`, `navegador`): se reconstruyen con internet y varios minutos.
- Una imagen derivada que la corrida en curso usa, o que se usó o creó hace menos de 1 h (puede ser de otra ventana). Si Docker rechaza borrar una (la usa un contenedor), se salta y se sigue con la siguiente.
- La **caché de compilación** de Docker: no admite labels, así que no se puede saber de quién es cada entrada y podarla alcanzaría también la de los `docker build` del usuario. Por eso **la limpieza automática no la toca**; solo se poda a petición de la persona y con confirmación (ver «Liberar espacio»).

### Límites (`[disco]` de `config.toml`)

Los define el equipo en `src/qagent/config/config.toml`, nunca en el código; `~/.qagent/config.local.toml` no los cambia. Un valor que falte o no sea un número mayor que 0 desactiva ese límite (y se avisa en el registro): ante la duda no se borra nada.

| Clave | Valor | Qué hace |
|---|---|---|
| `tope_imagenes_derivadas_gb` | 10 | Espacio total máximo de las imágenes derivadas. Cuenta lo propio de cada imagen, sin las capas de la imagen base que comparten. |
| `cache_antiguedad_dias` | 7 | Antigüedad mínima de la caché de compilación para podarla; solo se usa en la poda manual de «Liberar espacio». |
| `espacio_libre_minimo_gb` | 10 | Espacio libre mínimo del disco de Docker para construir o descargar una imagen (ver abajo). |

El tope se aplica al abrir la app y al terminar cada corrida, no a mitad de una: una corrida que necesita una imagen grande puede pasarse del tope hasta que termine. El orden de «menos usada» sale de `~/.qagent/imagenes_sandbox.json` (`registrar_uso`, que reconoce las cuatro familias de prefijos y se llama al preparar la imagen de una corrida); si una imagen no tiene registro (por ejemplo, las que preparan solo el humo E2E o la verificación de corrección), cuenta su fecha de creación.

### Espacio libre antes de construir

Antes de construir o descargar una imagen (la base, las dependencias del proyecto o las librerías del sistema) se mide el espacio libre del disco que usa Docker (`qagent.sandbox.espacio`): en Windows, el de `%LOCALAPPDATA%\Docker\wsl` o el disco elegido en los ajustes de Docker Desktop; en Linux, `/var/lib/docker`; si no se sabe, la carpeta personal. No hace falta que Docker responda. Si queda menos de `espacio_libre_minimo_gb`:

- la corrida **no empieza**: se detiene antes del análisis y de gastar tokens, con un mensaje en lenguaje simple («Queda poco espacio en el disco que usa Docker: 4,2 GB libres y QAgent necesita al menos 10,0 GB… faltan 5,8 GB. Libera espacio… y vuelve a intentar»);
- solo pasa si hace falta construir algo: con las imágenes ya hechas un disco justo no impide correr (`construccion_pendiente`);
- la comprobación vive en `_construir`, el único punto por el que pasan todas las construcciones, así que también protege la regresión, el humo E2E y la verificación de corrección.

El estado del entorno (EN-06, `verificar_entorno`) incluye el espacio libre como la comprobación `espacio`. Con poco espacio sale como **no ok con `advertencia`**, pero no bloquea el entorno (no entra en `problemas`): lo que detiene la corrida es la comprobación de arriba, y solo cuando de verdad hay que construir. Si no se puede medir, no cuenta como fallo.

Las pruebas no dependen del disco donde corren: `tests/conftest.py` fija siempre espacio de sobra, y las pruebas de la comprobación fijan su propio valor.

### Configuración → «Espacio en disco» y «Liberar espacio»

La pantalla Configuración muestra cuánto ocupa QAgent en Docker (imágenes base, imágenes de proyectos con el tope, restos de construcciones cortadas, y la caché de compilación aparte) y cuánto espacio libre queda en el disco de Docker (con aviso si está bajo el mínimo). La lógica está en `qagent.sandbox.uso_disco` (`medir_uso`, `liberar_espacio`); `desktop.py` solo hace de puente (`obtener_espacio_disco`, `liberar_espacio`) y el componente es `frontend/componentes/configuracion/espacio-disco.js` (+ `modal-espacio.js`).

El botón **Liberar espacio** pide confirmación y lista qué se borra y qué se conserva:

- Se borra lo que QAgent puede volver a crear: **todas** las imágenes de proyectos (`req-`, `node-`, `java-`, `browser-`), los contenedores sobrantes de corridas y construcciones interrumpidas y las capas sin etiqueta de QAgent. Lo reciente (menos de 1 h) no se toca.
- Se conservan las imágenes base, todo lo que no sea de QAgent, y los proyectos, pruebas y resultados del usuario.
- No se libera espacio con una corrida en curso (su imagen no se puede borrar): el puente lo rechaza con un mensaje.
- La **caché de compilación de Docker** es opcional (casilla sin marcar de antemano). Como no admite labels, afecta a toda la caché de compilación de Docker, no solo a la de QAgent: la confirmación lo dice explícitamente. Se poda la que lleva más de `cache_antiguedad_dias` días sin usarse. Es la única poda de caché que existe; la limpieza automática nunca la hace.

Borrar contenido libera espacio *dentro* de Docker, pero `C:` no lo recupera hasta compactar `docker_data.vhdx`: la sección lo explica con los pasos (`wsl --shutdown` y `diskpart` → `select vdisk file=…`, `attach vdisk readonly`, `compact vdisk`, `detach vdisk`).

## Versiones de Python soportadas en el sandbox (ADR-013)

El sandbox de Docker de QAgent ejecuta pruebas para proyectos en el rango **Python 3.10–3.14** (3.10, 3.11, 3.12, 3.13 y 3.14), con **3.11** como versión por defecto.

### Detección y reglas de elección
1. **Detección estática:** La versión se detecta en este orden de precedencia:
   - `.python-version`
   - `requires-python` de `pyproject.toml`
   - `python_requires` de `setup.cfg`
   - Si no hay declaración, se usa la versión por defecto (3.11).
2. **Rangos:** Si la especificación es un rango (ej. `>=3.10` o `>=3.10, <3.13`), se elige la versión más alta de la lista soportada que lo cumpla (ej. 3.14 y 3.12 respectivamente).
3. **Fuera del rango:** Si el proyecto pide una versión incompatible (ej. `<3.10` o `>=3.15`), la corrida se detiene de inmediato antes de construir imágenes o gastar tokens, y el Monitor muestra qué versión pidió el proyecto y qué rango soporta QAgent.
4. **Imágenes base:** Cada versión tiene su imagen base etiquetada (`qagent-sandbox:base-py<versión>`), manteniendo `qagent-sandbox:base` como la versión por defecto (3.11). El hash de la imagen derivada con dependencias incluye la versión de Python para aislar la caché de dependencias entre versiones.

## Ejecutar la aplicación

```bash
qagent                  # o: python -m qagent · qagent --version
```

La aplicación imprime cada paso de la corrida, con hora, en la terminal donde la abriste:

```text
17:57:20 INFO    Corrida iniciada en 'C:/proyectos/demo' con perfil 'deep' (IA simulada)
17:57:27 WARNING [Reviewer / Sandbox Guard] services/inventory.py :: reserve_stock_atomic() — Aserciones rechazadas… (1/9)
```

`INFO` son los pasos normales y `WARNING` las alertas (aserciones debilitadas, valor esperado no trazable, intentos agotados). Las claves nunca aparecen: el registro pasa por el filtro de claves de EN-06. Sin consola (el ejecutable de Windows) la bitácora va a `~/.qagent/registro.log`.

Para ver solo la interfaz, sin Python, abre `src/qagent/frontend/index.html` en el navegador: funciona en modo demostración. La guía de la interfaz (componentes, colores, logo) está en [`src/qagent/frontend/README.md`](../src/qagent/frontend/README.md).

## Distribución

| Qué | Cómo |
|---|---|
| Probar el paquete instalado, limpio y fuera del repositorio | `python scripts/verificar_paquete.py` |
| Construir `QAgent.exe` y el instalador de Windows | `pip install -e .[dev,empaquetar]`, instalar Inno Setup 6.6 o superior (`winget install JRSoftware.InnoSetup`) y `python scripts/construir_windows.py` → `dist\windows\` |
| Publicar una versión | Ver abajo |

### Publicar una versión

1. Sube `version` en `pyproject.toml` (la única fuente: la usan `qagent --version`, la interfaz, los informes y el instalador).
2. Une los cambios a la rama principal y crea una **Release** en GitHub con la etiqueta `v<versión>` (por ejemplo `v0.1.0`) y las notas de `docs/releases/`.
3. Al publicarla, GitHub Actions:
   - `publicar.yml`: verifica el paquete y lo sube a PyPI como `qagent-pytest`.
   - `instalador.yml`: construye `QAgent-<versión>-instalador.exe` en Windows y lo adjunta a la Release.

Para practicar sin publicar de verdad: Actions → **Publicar en PyPI** → *Run workflow* → `testpypi`. La configuración de PyPI (Trusted Publishing, sin contraseñas) está en [ADR-005](decisiones/ADR-005-distribucion.md).

## Estructura del repositorio

```text
QAgent/
├── .github/
│   ├── workflows/          publicar.yml (PyPI) e instalador.yml (Windows), al publicar una Release
│   └── pull_request_template.md
├── bench/ · bench_api/     Bancos de prueba con bugs sembrados a propósito (excluidos de ruff)
├── docs/
│   ├── arquitectura.md     Arquitectura, pipeline y modelo GAIA (EN-01)
│   ├── decisiones/         ADR-001 a ADR-005
│   ├── desarrollo.md       Esta guía
│   ├── imagenes/           Capturas de la portada
│   └── releases/           Notas de cada versión
├── packaging/windows/      Receta de PyInstaller, instalador de Inno Setup, ícono, imágenes del asistente y requisitos
├── scripts/                verificar_paquete.py y construir_windows.py
├── src/qagent/
│   ├── agents/             Planner, Generator, Reviewer (EN-04), Explicador (EP-10) y Recomendador (#197)
│   ├── almacenamiento/     .qagent/ del proyecto y ~/.qagent/recientes.json (EN-07)
│   ├── analysis/           Analizador estático con tree-sitter (EN-02, EN-14, TA-16)
│   ├── app/                Puente pywebview y bitácora (EN-08); sin lógica de negocio
│   ├── config/             config.toml del equipo, carga de .env, auditoría de claves, entorno (EN-06)
│   ├── contracts/          JSON Schema de los mensajes entre agentes y validar() (EN-01)
│   ├── frontend/           Interfaz HTML/CSS/JS sin compilación (ADR-003)
│   ├── llm/                Cliente LLM real y simulado, tokens y costo (EN-05, EN-11)
│   ├── orchestrator/       Máquina de estados de la corrida (EN-04)
│   ├── proyectos/          Abrir, clonar y vista previa (HU-01 a HU-04)
│   ├── sandbox/            Ejecución en Docker, sin red (EN-03)
│   ├── storage/            log.json y results.json de cada corrida (EN-05)
│   └── usuario.py          Carpeta de datos del usuario: ~/.qagent/
├── tests/                  Pruebas del sistema, siempre con la IA simulada; reflejan src/
├── AGENTS.md · CLAUDE.md   Reglas para el equipo y para asistentes de IA
├── LICENSE                 MIT
├── pyproject.toml          Versión, dependencias, extras dev y empaquetar, comando qagent
└── test.py                 python test.py
```

Dentro de cada proyecto que QAgent analiza se crea `.qagent/` con sus corridas, specs y pruebas aprobadas (EN-07). Las pruebas que detectan bugs se conservan aparte en `evidencias_bugs/<run_id>/`, con código, huella, firma y procedencia; nunca habilitan por sí solas la regresión de HU-25. Las comparaciones inmutables entre una corrida de origen y otra de verificación viven en `comparaciones/<run_verificacion>/` (#193). Todos estos JSON se escriben atómicamente en UTF-8 y las carpetas nuevas son aditivas, por lo que los proyectos históricos siguen siendo legibles.

Desde Historial, «Verificar corrección» (#194) crea una corrida `verify_fix` sin IA a partir de una sola corrida de origen. Reutiliza exactamente sus pruebas aprobadas y evidencias de bugs; antes del sandbox compara de forma estática la identidad y la firma. Las pruebas no comparables no se ejecutan y su motivo se conserva en `run_comparison.v1`. Esta ruta no sustituye la regresión HU-25: HU-25 exige que la implementación siga intacta, mientras #194 permite cambiar el cuerpo para validar una corrección.

La presentación de #195 no vuelve a ejecutar ni clasificar esas pruebas: Resultados, Historial y los informes MD, HTML, JSON y PDF usan una proyección común del `run_comparison.v1` persistido. Una corrida normal conserva su vista anterior; una verificación histórica sin comparación válida muestra el motivo de indisponibilidad sin fabricar totales.

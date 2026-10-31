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

`pip install -e` deja el programa instalado apuntando a esta carpeta: los cambios en el código se ven sin reinstalar. Si vienes de una versión anterior a TA-06, desinstala antes el nombre viejo: `pip uninstall -y qagent`.

### Tus datos viven en `~/.qagent/`

| Archivo | Para qué sirve |
|---|---|
| `.env` | Claves de API (una variable por agente, p. ej. `GEMINI_API_KEY_PLANNER`). Se crea solo, vacío, la primera vez. `.env.example`, en la raíz del repositorio, lista las variables de cada proveedor sin valores. |
| `config.local.toml` | Modelos que eligió cada uno en la pantalla Configuración; reemplazan a los del `config.toml` del equipo. |
| `recientes.json` | Proyectos recientes de la pantalla de inicio. |
| `registro.log` | Bitácora de la corrida cuando la app se abre sin consola (el ejecutable de Windows). |
| `demo/` | Corrida de demostración. |

`~` es tu carpeta de usuario (`C:\Users\<tú>`). El programa nunca escribe en su propia carpeta (ADR-005). Si antes tenías `.env` o `config.local.toml` en la raíz del repositorio, se mueven solos a `~/.qagent/` al abrir `qagent`.

Los modelos y precios del equipo están en `src/qagent/config/config.toml` (se versiona, sin claves). Para probar los modelos y las claves: `python -m qagent.llm.validar` (`--gratis` lista los modelos sin costo de OpenRouter).

## Pruebas

`python test.py` ejecuta **todas** las pruebas, siempre con la IA simulada (no gasta tokens ni llama a ninguna API):

```bash
python test.py                 # lint (ruff) + formato + todas las pruebas
python test.py --rapido        # sin lint y sin las pruebas de Docker ni de internet
python test.py --sin-lint      # solo pytest
python test.py -k clonador     # cualquier otro argumento se pasa a pytest
```

Las pruebas que necesitan Docker (`-m docker`) se omiten solas si Docker Desktop no está iniciado. Las de `tests/frontend/` comprueban que la interfaz esté bien armada.

Para abrir la aplicación con la IA simulada (sin claves ni gasto), agrega `QAGENT_FAKE_LLM=1` a `~/.qagent/.env` o define `set QAGENT_FAKE_LLM=1` (Linux: `export QAGENT_FAKE_LLM=1`) antes de abrirla. El nombre anterior, `PYAGENT_FAKE_LLM`, se sigue aceptando.

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
│   ├── agents/             Planner, Generator y Reviewer (EN-04)
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

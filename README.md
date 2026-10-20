<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-logo-oscuro.png">
  <img alt="QAgent" src="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-logo-claro.png" width="300">
</picture>

<br>

[![Versión](https://img.shields.io/github/v/release/AngelOncoy/QAgent?label=versi%C3%B3n&color=0e3aae)](https://github.com/AngelOncoy/QAgent/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/qagent-pytest?label=PyPI&color=0e3aae)](https://pypi.org/project/qagent-pytest/)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-1b1e23)
![Windows 10 | 11](https://img.shields.io/badge/Windows-10%20%7C%2011-1b1e23)
[![Licencia MIT](https://img.shields.io/badge/licencia-MIT-1b1e23)](https://github.com/AngelOncoy/QAgent/blob/develop/LICENSE)

### Encuentra lo que falla. Conserva lo que funciona.

QAgent escribe pruebas **pytest** para tu código Python con un equipo de agentes de IA,<br>
las ejecuta en un entorno aislado y te dice qué falla y por qué, sin debilitar una sola prueba.

[![Descargar para Windows](https://img.shields.io/badge/Descargar_para_Windows-0e3aae?style=for-the-badge&logoColor=white)](https://github.com/AngelOncoy/QAgent/releases/latest)
&nbsp;
[![pip install qagent-pytest](https://img.shields.io/badge/pip_install_qagent--pytest-1b1e23?style=for-the-badge&logo=python&logoColor=white)](https://pypi.org/project/qagent-pytest/)

[Por qué QAgent](#por-qué-qagent) · [Cómo funciona](#cómo-funciona) · [Qué incluye](#qué-incluye) · [Instalación](#instalación) · [Primeros pasos](#primeros-pasos)

<br>

<picture>
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-inicio-claro.png">
  <img alt="Pantalla de inicio de QAgent" src="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-inicio.png" width="100%">
</picture>

</div>

## Por qué QAgent

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🛡️ Tu máquina, protegida</h3>
      Tu código y las pruebas generadas solo se ejecutan dentro de un contenedor Docker, sin internet ni acceso a tus archivos. El análisis de tu proyecto es estático: QAgent lo lee, no lo ejecuta.
    </td>
    <td width="33%" valign="top">
      <h3>⚖️ La evidencia no se negocia</h3>
      Si una prueba solo pasa porque la IA quitó o relajó una aserción, QAgent la rechaza. El valor esperado sale de la firma, los tipos y el docstring, nunca de lo que el código devuelve hoy. Un posible bug no se esconde.
    </td>
    <td width="33%" valign="top">
      <h3>♻️ Sin repetir trabajo</h3>
      Lo que no cambió desde la última corrida se reutiliza. Las pruebas aprobadas se guardan en tu proyecto y puedes volver a correrlas sin IA para detectar regresiones.
    </td>
  </tr>
</table>

## Cómo funciona

Abres un proyecto, eliges qué probar y QAgent hace el resto en cuatro pasos.

<table>
  <tr>
    <td width="50%" valign="top">
      <b>1 · Explorar</b><br>
      QAgent analiza el proyecto y lista sus funciones y endpoints FastAPI, con su complejidad y lo que cambió desde la última vez. Tú eliges qué probar.
      <br><br>
      <img alt="Explorar: elegir funciones y endpoints" src="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-explorar.png" width="100%">
    </td>
    <td width="50%" valign="top">
      <b>2 · Preparar</b><br>
      Decides qué hacer: generar pruebas nuevas, volver a correr las guardadas o analizar a fondo las funciones críticas. Antes de empezar ves el uso de IA y la duración estimados.
      <br><br>
      <img alt="Preparar la corrida" src="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-preparar.png" width="100%">
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <b>3 · En curso</b><br>
      Sigues en vivo cómo los agentes analizan, escriben y verifican cada prueba. Si la IA intenta debilitar una prueba, lo verás bloqueado aquí.
      <br><br>
      <img alt="Progreso en vivo de la corrida" src="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-en-curso.png" width="100%">
    </td>
    <td width="50%" valign="top">
      <b>4 · Resultados</b><br>
      Primero lo que requiere atención: cada posible bug llega con su explicación y el valor esperado según el contrato. Puedes exportar el informe.
      <br><br>
      <img alt="Resultados de la corrida" src="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-resultados.png" width="100%">
    </td>
  </tr>
</table>

Detrás de cada corrida trabajan tres agentes coordinados, que solo se comunican por contratos JSON:

| Agente | Qué hace |
|---|---|
| **Planner** | Lee tu código (funciones, firmas, tipos, docstrings y rutas FastAPI) y decide qué casos hay que probar. |
| **Generator** | Escribe la prueba pytest de cada caso. |
| **Reviewer** | La ejecuta en el entorno aislado, revisa que las aserciones sean legítimas y pide hasta 3 intentos de corrección. |

## Qué incluye

- **Pruebas unitarias** de funciones Python y **pruebas de endpoints FastAPI** con `TestClient`, sin red y simulando `Depends`.
- **Casos clasificados** como normales, límite o de error.
- **Perfiles de prueba:** *Humo*, con un caso normal por objetivo para una revisión rápida; y *análisis a fondo*, que además mide la fortaleza de las pruebas en las funciones críticas.
- **Mutation testing** acotado a las funciones que marques como críticas, nunca al repositorio completo.
- **Pruebas de regresión:** vuelve a correr las pruebas guardadas sin gastar IA y ve qué empeoró y por qué.
- **Métricas por prueba:** si pasó, cobertura de líneas y ramas, intentos, tokens por agente y Mutation Score.
- **Historial** de corridas, con la comparación frente a la anterior.
- **Informes exportables** en HTML interactivo, PDF, Markdown o JSON.
- **Tu IA, por etapa:** cada agente puede usar su propio proveedor y modelo (Anthropic, OpenAI, Google Gemini, Groq, DeepSeek, OpenRouter o Xiaomi MiMo).
- **Tema oscuro y claro.**

<table>
  <tr>
    <td width="50%"><img alt="Historial de corridas" src="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-historial.png" width="100%"></td>
    <td width="50%"><img alt="Configuración de la IA por etapa" src="https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-configuracion.png" width="100%"></td>
  </tr>
  <tr>
    <td align="center"><sub>Historial: el trabajo anterior, a mano</sub></td>
    <td align="center"><sub>Configuración: un proveedor y modelo por etapa</sub></td>
  </tr>
</table>

## Instalación

### Windows: instalador (recomendado)

1. Descarga `QAgent-<versión>-instalador.exe` desde la [última versión publicada](https://github.com/AngelOncoy/QAgent/releases/latest).
2. Ejecútalo. No necesita permisos de administrador ni tener Python instalado.
3. Si Windows muestra «Windows protegió tu PC», elige **Más información → Ejecutar de todas formas** (el instalador aún no está firmado digitalmente).

### Con pip (si ya usas Python 3.10 o superior)

```bash
pip install qagent-pytest
qagent
```

En PyPI se llama `qagent-pytest` porque el nombre `qagent` ya lo usaba otro proyecto; el programa, el comando y la marca siguen siendo **QAgent**.

### Antes de la primera corrida

- **Docker Desktop**, abierto: las pruebas se ejecutan solo dentro de un contenedor aislado. La primera corrida prepara ese entorno sola (necesita internet y tarda unos minutos, una sola vez). [Descargar Docker Desktop](https://www.docker.com/products/docker-desktop/).
- **Claves de API** de los modelos de IA: se agregan en la pantalla **Configuración** del programa.
- **Git**, si vas a clonar repositorios por su URL.

¿Quieres probarlo sin claves ni costo? Agrega la línea `QAGENT_FAKE_LLM=1` al archivo `.env` de la carpeta `.qagent` de tu usuario (`C:\Users\<tú>\.qagent\.env`): QAgent usará una IA simulada con respuestas grabadas.

Tus claves, tu configuración y la lista de proyectos recientes se guardan en esa carpeta `.qagent` de tu usuario, nunca junto al programa. Desinstalar QAgent no las borra.

## Primeros pasos

1. Abre **QAgent** desde el menú Inicio (o con el comando `qagent`).
2. En **Configuración**, agrega la API de cada etapa: *Analizando*, *Escribiendo pruebas* y *Verificando*.
3. En **Inicio**, elige **Abrir carpeta** (un proyecto Python en tu equipo) o **Clonar URL Git**.
4. En **Explorar**, elige las funciones y endpoints a probar y pulsa **Preparar**.
5. En **Preparar**, elige qué hacer y los tipos de prueba, y pulsa **Iniciar prueba**.
6. Sigue el avance en **En curso** y revisa **Resultados**; desde ahí puedes **Exportar informe**.

## Alcance

QAgent genera pruebas **unitarias** para código **Python 3.10+** y pruebas de **endpoints FastAPI**. Integración contra servicios reales, extremo a extremo, carga y estrés quedan fuera de esta versión.

## Para el equipo de desarrollo

Cómo preparar el entorno, ejecutar las pruebas, construir el instalador y publicar una versión: [`docs/desarrollo.md`](https://github.com/AngelOncoy/QAgent/blob/develop/docs/desarrollo.md). Las reglas del proyecto están en [`AGENTS.md`](https://github.com/AngelOncoy/QAgent/blob/develop/AGENTS.md), las decisiones técnicas en [`docs/decisiones/`](https://github.com/AngelOncoy/QAgent/tree/develop/docs/decisiones) y las notas de cada versión en [`docs/releases/`](https://github.com/AngelOncoy/QAgent/tree/develop/docs/releases).

## Equipo

Proyecto del curso Taller Integrador I, Ingeniería de Sistemas e Inteligencia Artificial, Universidad Privada Antenor Orrego (UPAO).

Castillo Pezo, Mateo · Oncoy Patricio, Angel · Rodríguez Malca, Rodrigo · Sanchez Vargas, Adrián

## Licencia

[MIT](https://github.com/AngelOncoy/QAgent/blob/develop/LICENSE).

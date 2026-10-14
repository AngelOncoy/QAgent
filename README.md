# QAgent

**Genera y valida automáticamente pruebas unitarias (pytest) para tu código Python, con un equipo de tres agentes de IA.**

Abres tu proyecto, eliges qué probar y QAgent escribe las pruebas, las ejecuta en un entorno aislado y te entrega un informe con lo que pasó, lo que falló y por qué. No acepta pruebas «arregladas a la fuerza»: si una prueba solo pasa porque se le quitó o relajó una aserción, la rechaza.

![Pantalla de inicio de QAgent](https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-inicio.png)

## Cómo funciona

| Agente | Qué hace |
|---|---|
| **Planner** | Lee tu código (funciones, firmas, docstrings) y decide qué casos hay que probar. |
| **Generator** | Escribe la prueba pytest de cada caso. |
| **Reviewer** | La ejecuta en un contenedor Docker sin internet ni acceso a tus archivos, revisa que las aserciones sean legítimas y pide hasta 3 intentos de corrección. |

Por cada prueba registra si pasó, la cobertura de líneas y ramas, cuántos intentos necesitó, los tokens que gastó cada agente y, en las funciones críticas, el Mutation Score.

![Informe de una corrida](https://raw.githubusercontent.com/AngelOncoy/QAgent/develop/docs/imagenes/qagent-informe.png)

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

## Antes de la primera corrida

- **Docker Desktop**, abierto: las pruebas se ejecutan solo dentro de un contenedor aislado. La primera corrida prepara ese entorno sola (necesita internet y tarda unos minutos, una sola vez). [Descargar Docker Desktop](https://www.docker.com/products/docker-desktop/).
- **Claves de API** de los modelos de IA: se agregan en la pantalla **Configuración** del programa, una por agente.
- **Git**, si vas a abrir repositorios por su URL.

¿Quieres probarlo sin claves ni costo? Agrega la línea `QAGENT_FAKE_LLM=1` al archivo `.env` de la carpeta `.qagent` de tu usuario (`C:\Users\<tú>\.qagent\.env`): QAgent usará una IA simulada con respuestas grabadas.

Tus claves, tu configuración y la lista de proyectos recientes se guardan en esa carpeta `.qagent` de tu usuario, nunca junto al programa. Desinstalar QAgent no las borra.

## Primeros pasos

1. Abre **QAgent** desde el menú Inicio (o con el comando `qagent`).
2. En **Configuración**, agrega la API de cada agente.
3. En **Proyectos**, elige **Abrir proyecto** (una carpeta con código Python) o **Abrir repositorio** (una URL de Git).
4. Revisa la **Vista previa**, elige el perfil en **Configuración de pruebas** e inicia la corrida.
5. Sigue el avance en el **Monitor** y revisa el **Reporte final**; puedes exportarlo.

## Alcance

QAgent genera pruebas **unitarias** para código **Python 3.10+** y pruebas de endpoints FastAPI. Integración contra servicios reales, extremo a extremo, carga y estrés quedan fuera de esta versión.

## Para el equipo de desarrollo

Cómo preparar el entorno, ejecutar las pruebas, construir el instalador y publicar una versión: [`docs/desarrollo.md`](https://github.com/AngelOncoy/QAgent/blob/develop/docs/desarrollo.md). Las reglas del proyecto están en [`AGENTS.md`](https://github.com/AngelOncoy/QAgent/blob/develop/AGENTS.md) y las decisiones técnicas en [`docs/decisiones/`](https://github.com/AngelOncoy/QAgent/tree/develop/docs/decisiones).

## Equipo

Proyecto del curso Taller Integrador I, Ingeniería de Sistemas e Inteligencia Artificial, Universidad Privada Antenor Orrego (UPAO).

Castillo Pezo, Mateo · Oncoy Patricio, Angel · Rodríguez Malca, Rodrigo · Sanchez Vargas, Adrián

## Licencia

[MIT](https://github.com/AngelOncoy/QAgent/blob/develop/LICENSE).

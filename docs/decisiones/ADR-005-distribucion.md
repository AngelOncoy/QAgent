# ADR-005: Distribución de QAgent (instalador de Windows y PyPI)

- **Estado:** Aceptado
- **Fecha:** 2026-10-14
- **Ítem:** TA-06
- **Responsable:** Oncoy Patricio, Angel
- **Relacionado:** ADR-003 (frontend), ADR-004 (nombre QAgent), EN-03 (sandbox), EN-06 (configuración), EN-07 (almacenamiento), HU-30 (API por agente)

## 1. Contexto

El profesor pidió poder usar QAgent en su propia máquina. QAgent es una aplicación de escritorio (pywebview) y un monolito: no abre ningún puerto, así que exponerla con un túnel (ngrok) no sirve, porque la interfaz solo habla con Python dentro de la ventana. Lo que corresponde es distribuirla para que se instale.

Hasta TA-06 el programa solo funcionaba desde una copia del repositorio con `pip install -e`: la interfaz, los contratos, `config.toml`, las respuestas de la IA simulada, el `.env` y `config.local.toml` se buscaban subiendo carpetas hasta la raíz del repositorio. Instalado, abría sin interfaz. Además la pantalla Configuración escribía en el `config.toml` versionado del equipo.

## 2. Decisión

1. **Recursos dentro del paquete.** `frontend/`, `contracts/`, `config.toml` y `ia_simulada.json` pasan a `src/qagent/` y se declaran como datos del paquete. Cada módulo encuentra su recurso junto a sí mismo; una prueba impide volver a buscarlos en la raíz del repositorio.
2. **Datos del usuario en `~/.qagent/`** (`qagent.usuario`): `.env`, `config.local.toml`, recientes, `registro.log` y la corrida de demostración. El programa nunca escribe en su propia carpeta. Los `.env` y `config.local.toml` que estaban en la raíz del repositorio se mueven solos al abrir la app (nunca sobrescribe).
3. **La pantalla Configuración guarda en `config.local.toml`** del usuario, no en el `config.toml` del equipo. «Eliminar» deja `configurado = false` en ese archivo, que tapa la sección del equipo (cambia el comportamiento de HU-30).
4. **Ejecutable e instalador para Windows**: PyInstaller en modo carpeta (abre más rápido y los antivirus lo marcan menos que un único .exe) e Inno Setup, instalable sin permisos de administrador. Sin consola, la bitácora va a `~/.qagent/registro.log`; las herramientas de desarrollo de la ventana se desactivan en el ejecutable.
5. **PyPI como `qagent-pytest`**: el nombre `qagent` ya pertenecía a otro proyecto. Solo cambia lo que se escribe en `pip install`; el producto, el comando `qagent` y `import qagent` siguen igual.
6. **Publicación automática con GitHub Actions** al publicar una Release: `publicar.yml` (PyPI, con Trusted Publishing: sin contraseñas ni tokens guardados) e `instalador.yml` (construye el instalador en Windows y lo adjunta a la Release).
7. **Una sola versión**: `version` de `pyproject.toml`. La usan `qagent --version`, la interfaz, los informes exportados y el instalador. Antes la interfaz y los informes decían «v2.4».
8. **La imagen de Docker faltante ya no bloquea la corrida**: la primera corrida real la construye. Con el programa instalado no existe otro modo de construirla (cambia el criterio de EN-06, que bloqueaba).
9. **Licencia MIT**, a nombre de los cuatro integrantes.

## 3. Alternativas evaluadas

| Alternativa | Por qué no |
|---|---|
| Exponer la app con ngrok | La app no abre puertos y la interfaz depende del puente nativo de pywebview |
| Convertirla en aplicación web | Amplía el alcance (backend REST) y expondría las claves y el sandbox del equipo |
| Dejar los recursos en la raíz y copiarlos al construir | Dos formas de encontrarlos (desarrollo e instalado): más frágil |
| Un único `.exe` (onefile) | Abre más lento (se descomprime en cada arranque) y lo marcan más los antivirus |
| Instalador `.msi` (WiX) | Pensado para instalaciones masivas en empresas; mucho más complejo que Inno Setup |
| Publicar en PyPI como `qagent` | Ya lo usa otro proyecto: `pip install qagent` instalaría ese |
| Mantener el bloqueo sin imagen de Docker | Instalado, el usuario quedaría sin forma de correr pruebas reales |

## 4. Consecuencias

- **Cada integrante, una vez:** `pip uninstall -y qagent` y `pip install -e .[dev]` (el paquete ahora se llama `qagent-pytest`). Al abrir `qagent`, su `.env` y `config.local.toml` pasan a `~/.qagent/`.
- **La interfaz está en `src/qagent/frontend/`** (antes `frontend/`).
- **HU-30 y EN-06 cambian de comportamiento** (puntos 3 y 8); sus pruebas se actualizaron con el criterio nuevo.
- Windows muestra «Windows protegió tu PC» la primera vez: el instalador no está firmado (un certificado de firma tiene costo).
- `pip install qagent-pytest` y `import qagent` comparten nombre con el paquete `qagent` de PyPI: si alguien tuviera ambos instalados en el mismo entorno, uno pisaría al otro.

### Configuración de PyPI (una vez)

1. Cuentas en [pypi.org](https://pypi.org) y [test.pypi.org](https://test.pypi.org), con verificación en dos pasos.
2. En cada una: *Account settings → Publishing → Add a new pending publisher* (GitHub): proyecto `qagent-pytest`, owner `AngelOncoy`, repositorio `QAgent`, workflow `publicar.yml`, environment `pypi` (o `testpypi` en TestPyPI).
3. En GitHub: *Settings → Environments* → crear `pypi` (con *Required reviewers*) y `testpypi`.

## 5. Seguimiento

- Firmar el instalador si el proyecto se distribuye fuera del curso.
- Publicar también en winget cuando haya usuarios fuera del equipo.
- Retirar la migración de `.env`/`config.local.toml` desde la raíz del repositorio cuando todo el equipo haya actualizado.

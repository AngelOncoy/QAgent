# ADR-004: Un solo nombre técnico, QAgent (`pyagent` → `qagent`)

- **Estado:** Aceptado
- **Fecha:** 2026-10-14
- **Ítem:** TA-05
- **Responsable:** Oncoy Patricio, Angel
- **Relacionado:** EN-03 (sandbox), EN-07 (almacenamiento), EN-11 (IA simulada), ADR-003; reemplaza la regla de `AGENTS.md` que fijaba `pyagent` como nombre interno

## 1. Contexto

El producto se llama QAgent, pero el código conservaba el nombre anterior, PyAgent, en todo lo técnico: el paquete `src/pyagent/`, la carpeta `.pyagent/` que se crea dentro del proyecto del usuario, `~/.pyagent/` en su carpeta personal, la imagen Docker `pyagent-sandbox:base`, la variable `PYAGENT_FAKE_LLM` y el evento `window.onPyAgentEvent`. La regla de `AGENTS.md` lo justificaba "para no romper imports".

Varios de esos nombres sí los ve quien usa la aplicación: `.pyagent/` aparece en su explorador y en su `git status`, y la imagen en Docker Desktop. Además, el objetivo de distribuir la aplicación (`pip install qagent`, instalador para Windows) choca con instalar `qagent` e importar `pyagent`.

Al decidirlo no había ninguna rama remota sin integrar a `develop`, así que el cambio no generaba conflictos a nadie.

## 2. Decisión

Todo identificador técnico usa el nombre del producto:

| Antes | Ahora |
|---|---|
| `src/pyagent/` (`import pyagent`) | `src/qagent/` (`import qagent`) |
| `<proyecto>/.pyagent/` | `<proyecto>/.qagent/` |
| `~/.pyagent/recientes.json` | `~/.qagent/recientes.json` |
| `pyagent-sandbox:base`, `pyagent-sandbox:req-<hash>` | `qagent-sandbox:base`, `qagent-sandbox:req-<hash>` |
| etiqueta de contenedor `pyagent=sandbox` | `qagent=sandbox` (constante `ETIQUETA_CONTENEDOR`) |
| `PYAGENT_FAKE_LLM` | `QAGENT_FAKE_LLM` |
| `window.onPyAgentEvent` | `window.onQAgentEvent` |

Para no hacer perder datos ni romper configuraciones existentes, el nombre anterior solo sobrevive en código de compatibilidad:

- **Carpetas:** al abrir un proyecto, si solo existe `.pyagent/` se renombra a `.qagent/` (`almacenamiento.proyecto.migrar_carpeta_anterior`); al arrancar la aplicación pasa lo mismo con `~/.pyagent/` (`almacenamiento.recientes.migrar_carpeta_anterior`). Si `.qagent/` ya existe, no se toca nada.
- **Sandbox:** no copia ni `.qagent/` ni `.pyagent/` al contenedor.
- **IA simulada:** `PYAGENT_FAKE_LLM` se sigue aceptando, en el sistema o en el `.env`; si están las dos, manda `QAGENT_FAKE_LLM` (`llm.cliente.valor_simulado`).

Código nuevo no debe usar `pyagent`.

## 3. Alternativas evaluadas

| Alternativa | Por qué no |
|---|---|
| Mantener `pyagent` como nombre interno (regla anterior) | Deja nombres visibles para el usuario con la marca vieja y no encaja con publicar el paquete como `qagent` |
| Renombrar solo lo visible (carpetas, imagen, variable) y dejar el módulo | Mitad y mitad: el módulo igual tendría que cambiar al empaquetar, con más ramas abiertas para entonces |
| Renombrar sin migración | Quien ya usó la aplicación perdería sus corridas, specs y proyectos recientes |

## 4. Consecuencias

- Después de integrar el cambio, cada integrante debe correr `pip install -e .[dev]` (la instalación editable apuntaba a `src/pyagent/`) y reconstruir la imagen: `python -c "from qagent.sandbox import construir_imagen_base; construir_imagen_base()"`. La imagen `pyagent-sandbox:base` se puede borrar con `docker image rm pyagent-sandbox:base`.
- Las ramas creadas antes del cambio tendrán conflictos en casi todos los archivos de `src/` y `tests/`; conviene crearlas de nuevo desde `develop`.
- Los informes de evidencia ya entregados (`docs/evidencias/`) y los ADR anteriores conservan los nombres de su fecha; son registro histórico.
- Se corrigió una prueba de HU-13 que, tras cambiar la etiqueta de los contenedores, filtraba por la etiqueta anterior y pasaba sin verificar nada. Ahora usa `ETIQUETA_CONTENEDOR`, y una prueba sin Docker verifica la etiqueta.

## 5. Seguimiento

- Retirar el código de compatibilidad (`CARPETA_ANTERIOR`, `CARPETA_HOME_ANTERIOR`, `VARIABLE_SIMULADA_ANTERIOR` y la exclusión de `.pyagent` en el sandbox) cuando todo el equipo haya migrado, como pronto al cerrar la Fase 1.
- Actualizar el `README.md` (pendiente, se hará junto con la portada del repositorio).

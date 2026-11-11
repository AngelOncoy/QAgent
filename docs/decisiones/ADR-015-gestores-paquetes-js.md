# ADR-015: Dependencias de proyectos JS con su gestor de paquetes, workspaces y sin scripts

- **Estado:** Propuesto (Sprint 2)
- **Fecha:** 2026-11-11
- **Ítem:** FIX — Instalar dependencias de proyectos JS con pnpm, yarn y workspaces sin ejecutar sus scripts (#272)
- **Responsable:** Equipo QAgent
- **Relacionado:** ADR-007 (adaptadores por lenguaje), ADR-010 (arquitectura del Sprint 2), `docs/arquitectura.md` (sección 7)

---

## 1. Contexto

La imagen derivada de Node copiaba solo `package.json` (y `package-lock.json`) y ejecutaba `npm ci` o `npm install`. Al probar `marktext/marktext` la corrida se detuvo con un error crudo de Docker. Hubo dos causas:

1. npm ejecutó el `postinstall` del proyecto (`tsx scripts/postinstall.ts`), y `scripts/` no estaba en el contexto de build. Además, ejecutar `postinstall` o `prepare` del usuario al construir la imagen es correr su código **con red**, fuera del sandbox de ejecución.
2. marktext es un monorepo de **pnpm** (`packageManager`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`). npm no entiende sus workspaces: aunque no fallara, no instalaría las dependencias de `packages/*`.

## 2. Decisión

1. **El gestor sale del proyecto.** Manda el lockfile (`pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn, `package-lock.json`/`npm-shrinkwrap.json` → npm). Si hay varios, gana el que coincide con `packageManager`; sin lockfile, se usa `packageManager` y, si falta, npm. Yarn es berry (2+) si lo dice `packageManager`, si hay `.yarnrc.yml` o si el lockfile tiene `__metadata:`.
2. **pnpm y yarn se instalan con corepack fijado (`0.36.0`)** solo durante la construcción de la derivada (Node 25+ ya no trae corepack), en la versión de `packageManager` o en una versión por defecto fija (`gestores_js.VERSIONES_POR_DEFECTO`). La imagen base `qagent-sandbox:node` no cambia. La versión que viene del proyecto se valida con una expresión regular antes de entrar al Dockerfile.
3. **Nunca se ejecutan scripts del proyecto:** `--ignore-scripts` (npm, pnpm, yarn classic), `--mode=skip-build` y `YARN_ENABLE_SCRIPTS=0` (berry), `--ignore-pnpmfile` (pnpm), y en `.yarnrc.yml` se quitan `yarnPath` y `plugins`.
4. **Se respeta el lockfile** (`npm ci`, `--frozen-lockfile`, `--immutable`). Si no coincide con el `package.json`, se instala sin bloquear versiones y el log lo marca (`QAGENT: lockfile desactualizado`).
5. **Workspaces:** se leen `pnpm-workspace.yaml` y el campo `workspaces` de `package.json` (con comodines y exclusiones `!`, sin salir del proyecto). Se copia solo el `package.json` de cada workspace, nunca código. Se instala de forma plana (`node-linker=hoisted` en pnpm, `nodeLinker: node-modules` en berry) y `sandbox/node/reubicar_workspaces.cjs` sube a `/work/node_modules` lo que quedó en los `node_modules` de cada workspace y reescribe los enlaces de los paquetes del monorepo para que apunten a `/work/proyecto/<ruta>`.
6. **Sin credenciales en la imagen:** `.npmrc`, `.yarnrc` y `.yarnrc.yml` se copian sin las líneas de autenticación. Un registro privado falla con un mensaje que lo explica.
7. **Mensaje para personas:** si la instalación falla, el error nombra el gestor y el lockfile, la causa probable (red, credenciales, versión de Node, lockfile de otra versión, versión inexistente, workspace no encontrado, disco) y las últimas líneas de error del gestor, en lugar de la orden `RUN` de Docker.

## 3. Opciones descartadas

| Opción | Por qué no |
|---|---|
| Solo añadir `--ignore-scripts` a npm | Resuelve el `postinstall` de marktext, pero un monorepo pnpm o yarn seguiría sin sus dependencias. |
| Instalar pnpm y yarn en la imagen base | Obliga a reconstruir `qagent-sandbox:node` y fija una versión que no coincide con `packageManager`. |
| Montar los `node_modules` de cada workspace con volúmenes al ejecutar | Docker no tapa un *bind mount* con contenido de la imagen sin volúmenes anónimos por corrida, que copian cientos de MB cada vez. |

## 4. Consecuencias y límites

- La etiqueta de la derivada incluye la marca `js-gestores-v1`: las derivadas `node-` y `browser-` anteriores, que ejecutaban scripts, no se reutilizan.
- Si un workspace usa **otra versión** de un paquete que ya está en la raíz, queda la de la raíz (el log lo cuenta). Es raro con `hoisted`, pero puede pasar.
- Sin scripts, los paquetes que se compilan o descargan binarios al instalarse (`esbuild`, `sharp`, `electron`, módulos nativos) pueden quedar sin su binario. Las pruebas unitarias con Vitest no suelen necesitarlos.
- Los parches declarados (`patchedDependencies` de pnpm, `.yarn/patches` de berry) se copian; los de `patch-package` (que corren en `postinstall`) no se aplican.
- Bun y Deno no se soportan: un `packageManager` con otro gestor se ignora y se usa npm.

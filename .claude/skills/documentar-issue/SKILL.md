---
name: documentar-issue
description: Redacta el informe de una tarea terminada de QAgent (issue, HU, EN, SPK, TA, FIX, DOC, BU…) como un .md listo para subir a Notion, con el formato del equipo (Resumen, Objetivo, tabla de qué se revisó y qué se hizo, Pruebas e Imprevistos) en docs/evidencias/. Úsala siempre que pidan documentar, informar, dejar evidencia o «hacer el informe» de una tarea, issue, historia de usuario o spike, o que pasen al siguiente ítem y falte su informe, aunque no digan «Notion» ni «evidencia».
---

# Documentar una tarea terminada (informe para Notion)

Un informe por tarea terminada, en `docs/evidencias/`, en español, con un formato fijo para que todo el equipo documente igual y rápido.

## Reglas

- **Un `.md` por tarea.** Cinco issues terminadas = cinco archivos. Si la tarea es una épica, su informe resume las sub-issues y enlaza a sus informes.
- **En `docs/evidencias/` solo van `.md`.** Nada de carpetas `img/`, scripts, JSON ni tests generados. La carpeta está en `.gitignore`: los informes no se suben a git, se suben a Notion. Nunca hagas commit de esa carpeta.
- **Nombre del archivo = título del informe**, por ejemplo `FIX-### - Recuperar la opción Humo en la pantalla Preparar.md`.
- **Título:** `<TIPO>-<NN> - <Título en español>`.
  - `<TIPO>`: `HU`, `EN`, `SPK`, `TA`, `FIX`, `DOC`, `BU`, `EV`… según el ítem.
  - `<NN>`: el número **del backlog** si lo tiene (por ejemplo `HU-24`, `EN-07`, `FIX-01`). Si no tiene número de backlog (solo issue de GitHub), usa `###` para que el equipo lo complete: `FIX-### - …`. El número de la issue de GitHub va en la línea de datos, no en el título.
- **Sin firmas de IA:** nada de «Generado con…», «Co-Authored-By» ni menciones a la IA como autora. El autor es quien entrega la tarea.
- **No hay sección «Pendiente» ni «Otra tarea».** Lo que quedó para después se nombra dentro de *Imprevistos* (si surgió al trabajar) o no va.
- Escribe para alguien que no vio el trabajo: frases cortas, sin jerga inventada, con los nombres reales de pantallas, archivos y corridas.

## Pasos

1. **Identifica la tarea:** tipo, número de backlog (o `###`), número de issue de GitHub, épica, rama y PR. Si falta algo que no puedas averiguar (`git log`, `git branch`, el texto de la issue), pon `—` en vez de inventarlo.
2. **Reúne la evidencia real:**
   - el texto y los criterios de la issue;
   - los commits y el diff de la tarea (`git log --oneline develop..HEAD`, `git show --stat <commit>`);
   - el resultado de `python test.py` (cuántas pruebas, si pasó);
   - las corridas de QAgent usadas como prueba (`.qagent/runs/<run_id>/results.json`): `run_id`, antes y después;
   - las capturas que existan (de la sesión, de la persona o del navegador de la app).
3. **Escribe el informe** copiando `plantilla.md` (en esta misma carpeta) y completando cada sección:
   - **Resumen:** 2 a 4 frases: qué problema había y qué cambió.
   - **Objetivo:** a qué se quería llegar con la tarea (el resultado, no la lista de cambios).
   - **Qué se revisó y qué se hizo:** una fila por área tocada (backend, interfaz, contrato, pruebas…). *Qué se revisó* = lo que se encontró o el problema; *Qué se hizo* = el cambio concreto.
   - **Pruebas:** una subsección por prueba, con qué se hizo, el resultado y su imagen (ver *Imágenes*).
   - **Imprevistos:** lo que salió distinto de lo esperado (fallos de pruebas, hallazgos nuevos, decisiones que hubo que tomar), con su imagen si la hay y en qué terminó (corregido, issue aparte…). Si no hubo, escribe «Sin imprevistos».
4. **Guarda** el archivo en `docs/evidencias/<título>.md` y avisa a la persona dónde quedó y qué capturas le faltan.

## Imágenes

Por defecto, **marcador con instrucciones**: en el lugar de la imagen va un recuadro que dice qué captura poner y cómo reproducirla. La persona arrastra la imagen al pegarlo en Notion.

```markdown
> 📷 **Captura:** Resultados de bench con «1 posible bug» en calcular_descuento.
> **Cómo obtenerla:** abrir `qagent` → bench → Revisión rápida (humo) → Unitarias → Iniciar prueba → Ver resultados.
```

Si hay capturas en disco y la persona quiere el `.md` autocontenido, escribe la imagen con su ruta local y después incrústala:

```markdown
![Resultados de bench](C:/ruta/a/la/captura.png)
```

```bash
python .claude/skills/documentar-issue/incrustar_imagenes.py "docs/evidencias/<título>.md"
```

El script reemplaza cada `![…](ruta-local)` por la imagen dentro del `.md` (base64) y avisa de las rutas que no encontró. Las imágenes incrustadas se ven en VS Code, PyCharm y GitHub; al importar en Notion pueden no mostrarse: en ese caso, usa el marcador.

## Referencia rápida de la línea de datos

```markdown
**Issue:** #133 · **Épica:** FIX-01 (#126) · **Rama:** fix/issue-133-humo-preparar · **PR:** #134 · **Fecha:** 2026-10-26
```

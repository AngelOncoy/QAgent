---
name: informe-de-trabajo
description: Redacta un informe corto y en lenguaje sencillo de lo que se hizo en una tarea («se revisó X y se hizo Y», y para qué se hizo), con pruebas numeradas respaldadas por imágenes reales (resultado de las pruebas, antes y después, la aplicación funcionando), guardado en docs/evidencias/ID-del-ítem/. Úsala siempre que el usuario pida documentar lo que se hizo, dejar evidencia, un informe de avance o de cierre de tarea, adjuntar fotos o capturas de las pruebas, redactar la evidencia de aceptación de un ítem del backlog, o explicar un trabajo técnico a alguien que no programa (profesor, cliente, compañero de otra área), aunque no diga «informe» ni «skill». También cuando pida la ficha del backlog (nombre, descripción, criterios de aceptación) de una tarea ya hecha.
compatibility: Los scripts de imágenes necesitan Node 22 o superior y Microsoft Edge o Chrome instalado (el resto de la skill no necesita nada).
---

# Informe de trabajo con evidencias

Convierte un trabajo técnico ya hecho en un documento que cualquiera entiende y que se puede comprobar: texto
corto en lenguaje sencillo, y unas pocas pruebas con imágenes **reales**. Existe porque quien revisa una tarea
(un profesor, el equipo, un cliente) casi nunca lee el código; lee el informe, y lo que necesita es poder
confiar en él.

## Qué se entrega

Una carpeta `docs/evidencias/<ID>/` con:

```
informe-<id>.md        el informe (plantilla en assets/plantilla-informe.md)
img/prueba-N-….png     una imagen por prueba (o par antes/después)
```

`<ID>` es el del ítem del backlog (por ejemplo `ta-01`, `hu-14`). Si la persona no lo dijo, pregúntalo; si no
lo sabe, deja el marcador `<!-- COMPLETAR: ID del ítem -->` en vez de inventar uno.

## Principios (y por qué)

- **Lenguaje sencillo.** El lector no programa. Cada frase debe decir qué cambia para la persona o el equipo,
  no cómo se hizo por dentro. La tabla de cambios de palabra está en `references/lenguaje-sencillo.md`; léela
  antes de redactar.
- **Resumido.** Entre 5 y 9 puntos «se revisó / se hizo» y de 2 a 4 pruebas. Un informe largo no se lee y
  diluye lo importante.
- **Honesto.** Toda cifra sale de un comando ejecutado ahora, y cada imagen es real o se dice cómo se generó.
  Las cifras de conversaciones anteriores pueden estar desactualizadas, y un número inventado destruye la
  confianza en todo el informe. Lo que no se pudo comprobar o queda fuera, se dice en «Pendiente».
- **Solo las pruebas necesarias.** Cada prueba responde a «¿cómo sé que esto es cierto?». Si una prueba no
  cambia la conclusión, quítala.
- **Sin guardar cambios en Git.** Deja los archivos sin commitear: guardar y subir es decisión de la persona.
  Puedes sugerir el mensaje del commit.

## Proceso

### 1. Entender el alcance
Averigua qué trabajo se documenta, el ID del ítem, quién lo lee y dónde se va a usar (backlog, entrega, PR).
Si el trabajo ocurrió en esta misma conversación, extrae de ahí lo que se hizo y lo que la persona corrigió o
pidió (esas correcciones suelen ser lo más valioso de contar).

### 2. Reunir los hechos, midiéndolos
Ejecuta los comandos de `references/evidencias.md` («Qué medir») para obtener: qué cambió, fechas reales, tamaños
antes y después, y el resultado de las pruebas. Anota cada cifra junto con el comando que la dio.

### 3. Escribir los puntos «Se revisó / Se hizo»
Un punto por cada cosa revisada, con el mismo molde: *Se revisó:* cómo estaba (con una cifra medida) y *Se hizo:*
qué cambió y qué mejora trae. Ordénalos de lo más visible para el lector a lo más interno. Si un punto no tiene
nada que revisar ni que mostrar, no lo incluyas.

### 4. Elegir las pruebas
Elige de 2 a 4 entre estos patrones (detalle de cómo conseguir cada una en `references/evidencias.md`):

| Quiero demostrar… | Evidencia |
|---|---|
| que todo sigue en orden | imagen con el resultado de las pruebas automáticas |
| que se ve o funciona igual que antes | captura antes / después con los mismos pasos |
| que se corrigió un fallo | captura del fallo, captura corregida y cuántas veces fallaba antes y después |
| que muestra datos reales | captura de la aplicación real con un proyecto real |

Si la persona ya mandó una captura (por ejemplo del fallo), úsala como «antes»: es la que ella vio.

### 5. Producir las imágenes
- **Resultado de comandos:** guarda la salida completa en un `.txt` y conviértela con
  `scripts/terminal_a_imagen.js`. El texto debe ser el que el comando devolvió; solo se acorta lo que identifique
  a una persona (rutas personales) con `--reemplazar`.
- **Pantallas:** `scripts/capturar_pantalla.js`, con los mismos pasos para «antes» y «después». La versión
  anterior sale de Git (`git show <base>:<ruta>`).
- **Aplicación de escritorio:** conéctate a la ventana real por su puerto de depuración (ver
  `references/evidencias.md`).
- **Fallos intermitentes:** una sola prueba no demuestra nada; repite la acción desde cero 8 veces o más y cuenta.
- Mira cada imagen antes de usarla. Una captura con una etiqueta vacía o un aviso que quedó a medias hace dudar
  de todo lo demás.

### 6. Redactar con la plantilla
Copia `assets/plantilla-informe.md` y rellénala. Al terminar, pasa la revisión final de
`references/lenguaje-sencillo.md`: sin términos técnicos, cada cifra con su comando, sin exceso de puntos.

### 7. Verificar antes de entregar
- Todas las imágenes enlazadas existen (`img/…`) y los enlaces a otros documentos resuelven.
- Las cifras del texto coinciden con la corrida actual.
- Ninguna imagen ni texto lleva claves ni datos personales sin advertirlo.
- Si el proyecto tiene pruebas, ejecútalas: el informe no debe afirmar «todo en orden» sin que sea cierto ahora.

### 8. Entregar
Resume a la persona, en pocas líneas: dónde quedó el informe, las pruebas incluidas, qué imágenes son capturas
reales y cuáles se generaron a partir de la salida de un comando, y cualquier límite (por ejemplo, que las
capturas muestran la ruta de su carpeta). Ofrece pasarlo a otro formato (Word, PDF o Notion) si lo necesita.

## Ficha del backlog (si la piden)

Cuando pidan «cómo lo pondría en el backlog», entrega una tabla campo → valor con el estilo de las otras filas:
nombre (`ID Verbo + qué`), descripción corta, criterios numerados (verificables, el último es la **evidencia de
aceptación**: el PR o el informe), fechas tomadas de `git log`, y puntos de historia **solo como propuesta** con
el razonamiento, porque la escala es del equipo. Si el prefijo del ID (por ejemplo `TA`) no figura en las
convenciones del repositorio, señálalo.

## Archivos de la skill

- `assets/plantilla-informe.md`: estructura exacta del informe.
- `references/lenguaje-sencillo.md`: tabla de palabras y revisión final del texto.
- `references/evidencias.md`: comandos para medir, patrones de prueba y cómo capturar la ventana real.
- `scripts/terminal_a_imagen.js`: salida de un comando a imagen con aspecto de terminal.
- `scripts/capturar_pantalla.js`: captura de una pantalla web o de una ventana real tras ejecutar unos pasos.

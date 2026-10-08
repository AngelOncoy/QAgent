# Cómo conseguir cada evidencia

Referencia para el paso «Producir las imágenes». Los scripts están en `scripts/` y necesitan Node 22+ y
Microsoft Edge o Chrome (o la variable `NAVEGADOR` con la ruta del ejecutable).

## Qué medir antes de escribir (y con qué comando)

| Dato | Cómo obtenerlo |
|---|---|
| Qué cambió | `git log --oneline origin/<base>..HEAD`, `git diff --stat <base> HEAD` |
| Fechas reales del trabajo | `git log origin/<base>..HEAD --no-merges --format='%ad' --date=format:'%Y-%m-%d %H:%M'` |
| Tamaño de archivos antes y después | `git show <base>:<ruta> \| wc -l` frente a `wc -l <ruta>` |
| Cuántas veces aparece algo (colores, textos) | `grep -rc`, o un script corto; nunca estimar a ojo |
| Resultado de las pruebas | ejecutar el comando de pruebas del proyecto y guardar toda su salida en un `.txt` |

Ejecuta los comandos **ahora**, no te fíes de cifras de conversaciones anteriores: pueden estar desactualizadas.

## Patrones de prueba

| Lo que quieres demostrar | Evidencia | Cómo |
|---|---|---|
| «Todo sigue en orden» | Imagen de la terminal con el resultado de las pruebas | `<comando> > salida.txt 2>&1` y luego `scripts/terminal_a_imagen.js` |
| «Se ve igual que antes» | Dos capturas (antes / después) con los **mismos pasos** | Versión anterior con `git show <base>:<ruta> > carpeta-antes/index.html`; mismos `--pasos` en `capturar_pantalla.js` para ambas |
| «Se corrigió un fallo» | La captura del fallo (la que mandó la persona, o una reproducida) y la captura corregida, más la cifra de repeticiones | Repite la acción varias veces antes y después y cuenta cuántas fallan |
| «Muestra datos reales» | Captura de la aplicación real con un proyecto real | Ver «Aplicación de escritorio» más abajo |

Si dos capturas se van a comparar, fíjate en que arranquen del mismo estado: un usuario real abre un proyecto
antes de ir al informe, y la captura debe hacer lo mismo (una etiqueta vacía puede parecer un error que no es).

## Capturas con `capturar_pantalla.js`

El archivo de `--pasos` contiene el cuerpo de una función `async` que se ejecuta dentro de la página; puedes
llamar a las funciones de la propia aplicación y usar `await`:

```js
handleOpenFolder(); document.querySelector('#fsList div').click(); confirmOpen();
await new Promise(r => setTimeout(r, 900));
go('report'); await new Promise(r => setTimeout(r, 600));
```

Espera un poco después de cada acción que cambie la pantalla (animaciones, datos que llegan tarde).

## Aplicación de escritorio (ventana real)

Una aplicación de escritorio con navegador integrado (pywebview, Electron, WebView2) se puede inspeccionar si
se abre con un puerto de depuración:

- pywebview: antes de iniciar, `webview.settings["REMOTE_DEBUGGING_PORT"] = 9411` (en un lanzador temporal;
  no hace falta tocar el código del proyecto).
- Electron / Chromium: `--remote-debugging-port=9411`.

Luego `node capturar_pantalla.js --puerto 9411 --pasos pasos.js --salida img/prueba-N.png`. Los pasos pueden
llamar a la API real de la aplicación (por ejemplo abrir un proyecto) para que la captura muestre datos reales.

Cuando el fallo es intermitente (por ejemplo, «a veces abre mal»), una sola prueba no demuestra nada: abre la
aplicación **varias veces desde cero** (8 o más) y cuenta. «Funcionó una vez» es justo lo que suele esconder el
problema.

## Ocultar datos personales

Revisa las capturas y la salida de la terminal antes de guardarlas: rutas de carpetas personales, nombres de
usuario, claves o correos. En la imagen de la terminal usa `--reemplazar "ruta=>python"`; eso solo acorta
esa ruta y deja el resto de la salida tal cual. Nunca incluyas valores de claves. Si una captura no se puede
limpiar, avisa a la persona en la entrega para que decida.

## Imágenes que envía la persona

Si la persona pegó una captura (por ejemplo, el fallo), cópiala a `img/` con un nombre descriptivo
(`prueba-3a-antes-...png`). Es la mejor evidencia del «antes» porque es la que ella vio.

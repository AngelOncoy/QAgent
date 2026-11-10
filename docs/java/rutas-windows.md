# Rutas de almacenamiento en Windows (#268)

Las evidencias de bugs, las specs y las pruebas aprobadas se guardan dentro de
`.qagent/` del proyecto. Sus nombres no deben repetir indefinidamente el paquete
Java y el método: una ruta temporal de 267 caracteres detuvo una corrida en un
equipo con `LongPathsEnabled = 0`.

## Comportamiento

- La escritura atómica utiliza un temporal con prefijo fijo `.qa-` y sufijo
  `.tmp`, en la misma carpeta de destino. Sigue reemplazando el archivo con
  `os.replace` y limpiando el temporal si la escritura falla.
- Los IDs de objetivos y módulos tienen como máximo 64 caracteres. Los que ya
  son cortos mantienen su nombre. Los largos conservan un prefijo legible y
  reciben 16 dígitos hexadecimales de SHA-256 de su identidad completa.
- El hash no depende de la carpeta raíz ni del proceso: un mismo objetivo conserva
  su ID entre corridas. Nombres que difieren al final no quedan identificados
  únicamente por el prefijo recortado.
- Las pruebas aprobadas conservan el formato `test_<id>.py` del almacenamiento;
  el adaptador sigue disponiendo el archivo Java correspondiente para ejecutarlo
  en el sandbox. No se cambia el lenguaje ni el contenido del test por el nombre
  usado en el almacén.

## Compatibilidad

Las specs y pruebas antiguas no se borran ni se renombran. Se pueden seguir
encontrando por sus IDs anteriores y por la identidad del contrato. Si se guarda
una spec actual del mismo objetivo, esa versión prevalece en los listados y la
regresión: no se ejecutan ambos archivos ni se recupera una aprobación antigua
cuando la spec actual ya no enlaza una prueba aprobada.

La lectura de planes modulares también contempla su nombre anterior. Las
evidencias existentes mantienen su código, contrato, firma, fecha y procedencia:
volver a guardar el mismo bug de la misma corrida no lo duplica ni sobrescribe.

## Aviso en la aplicación

Si falla el guardado de una evidencia, el orquestador conserva los veredictos y
emite un evento `aviso` que el puente de escritorio transmite al Monitor. El texto
indica que el bug se detectó, pero su evidencia no pudo guardarse, y recomienda
revisar el espacio y los permisos. Continúa con los siguientes objetivos.

Este manejo está limitado al guardado de evidencias: no anuncia que un archivo
se guardó cuando falló y no oculta errores generales que impidan escribir todos
los resultados del proyecto.

## Validación reproducible

Sin Docker ni API real, desde el entorno virtual del proyecto:

```powershell
python -m pytest tests/almacenamiento/test_issue268_rutas_windows.py tests/orchestrator/test_issue268_evidencia_no_detiene.py -q -s
python test.py -m "not docker and not red"
```

Los escenarios comprueban temporales cortos, atomicidad, IDs estables, lectura
histórica, regresión Java con ejecutor simulado y fallos de evidencia enviados
al Monitor sin detener la corrida. El escenario de carpeta profunda exige que
las rutas finales y temporales observadas sean menores de 260 caracteres; no
modifica el registro. Esa comprobación no sustituye la prueba real con la
configuración de Windows del equipo afectado.

Para la aceptación en Windows, comprobar primero el valor real:

```powershell
Get-ItemPropertyValue -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled
python -m pytest tests/sandbox/test_ep174_java_integrado_docker.py --docker -q -s
```

La validación específica exige `LongPathsEnabled = 0`, Docker iniciado y la imagen
del banco preparada. El test debe terminar aprobado, detectar tres bugs y aceptar
tres métodos, conservar el POM y repetir los tres aprobados sin tokens de IA.
Un resultado omitido no cuenta como aprobación. No abrir nuevas instancias de
QAgent mientras ese test usa contenedores del sandbox.

No se cambia automáticamente la configuración de Windows. Si se desactiva
temporalmente el soporte de rutas largas para verificar el arreglo, registrar
antes el valor original y restaurarlo al terminar. No es un requisito para los
usuarios del producto.

El límite de los nombres reduce el problema reportado, pero no vuelve ilimitada
la profundidad de carpetas: si la ruta base ya agota el margen de Windows, ningún
nombre abreviado garantiza que todas las escrituras puedan realizarse.

## Resultados de aceptación (9 de noviembre de 2026)

- Casos específicos: 13 aprobados. En la ejecución documentada por Alejo,
  7,51 segundos y máximo observado de 243 caracteres, tanto para destinos como
  para temporales del escenario de carpeta profunda.
- Regresión general sin Docker ni red: 3743 aprobados, 1 omitido y 68 excluidos,
  en 521,24 segundos. Lint y formato también aprobados.
- Prueba integrada real ejecutada por Alejo en Windows después de reiniciar
  con `LongPathsEnabled = 0`: 1 aprobado en 416,64 segundos. Detectó los tres
  bugs sembrados, aceptó los tres métodos correctos y repitió tres aprobados
  en regresión. JaCoCo al 100 %, POM original intacto, contenedores eliminados,
  ejecución sin red e IA grabada con 0 tokens.
- Alejo restauró el valor original a `1`, lo comprobó en PowerShell y confirmó
  el reinicio posterior. Las capturas de estas comprobaciones acompañan el
  informe de la tarea en Notion.

El aviso ante un fallo de guardado se verificó mediante errores controlados y
el puente real de eventos del escritorio; no se presenta como una captura de un
fallo de disco provocado manualmente en la aplicación.

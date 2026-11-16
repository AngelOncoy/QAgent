# ADR-017: Preparación Maven de proyectos externos

- Estado: Implementado; validación automatizada aprobada, comprobación visual y aceptación final pendientes.
- Issue: #290.
- Fecha: 2026-11-16.

## Contexto

La preparación copiaba solo el POM raíz y mostraba el código de salida de Docker
en lugar de la causa Maven. El ejecutor admitía un módulo sin herencia. Copiar un
repositorio Git no garantiza que su configuración de construcción sea compatible.

## Decisión

Ampliar explícitamente el soporte a Maven con padres públicos o locales y módulos
internos. Inspeccionar estáticamente sus descriptores, preservando sus rutas y la
configuración declarada. La imagen de dependencias y el ejecutor deben utilizar
la misma estructura; no basta con quitar el rechazo de parent/modules.

Mantener JDK 25 como entorno actual. Las incompatibilidades del JDK y las
dependencias privadas deben diagnosticarse, sin cambiar versiones del proyecto
silenciosamente ni copiar credenciales. No se habilita Gradle con esta decisión.

El análisis local no ejecuta Maven, plugins ni fuentes. La resolución y ejecución
ocurren en Docker: red durante preparación de dependencias y sin red durante las
pruebas. Los archivos originales no se modifican. Solo se ejecuta la prueba
generada seleccionada, aunque se necesiten otros módulos para compilarla.

La caché incluye todos los descriptores usados y la versión de la receta. Un
cambio en un POM hijo invalida la imagen derivada. Las causas de Maven se muestran
en lenguaje claro, con detalles técnicos, sin atribuir un error de entorno al
código auditado.

## Implementación y validación por etapas

1. Inspección de POM, padres locales, módulos y perfiles; contexto acotado y
   diagnóstico de errores de construcción. No demuestra aún ejecución multimódulo.
2. Preparación coherente de compilación, pruebas y dependencias entre módulos;
   comprobaciones previas a las llamadas de IA.
3. Ejecución con Docker de fixtures distintos, perfiles Java y apertura/clonación
   desde la aplicación; regresiones Java/Python y documentación de límites.

La inferencia Java sin Javadoc pertenece a otra issue. Los fixtures de esta tarea
tienen contratos verificables para no confundir la omisión del Planner con un
fallo Maven. No se declara compatibilidad universal con plugins, activaciones de
perfil, servicios externos ni proyectos arbitrarios.

## Hallazgo durante la validación real

El fixture con padre público `org.apache:apache:35` y Commons Lang 3.17.0
reprodujo una preparación aparentemente correcta seguida de un fallo offline:
`apache-jar-resource-bundle:1.7` no había sido descargado. Es un recurso declarado
por `maven-remote-resources-plugin` en la herencia, no una dependencia de código.
`dependency:go-offline` y `dependency:resolve` no bastaban para ese proyecto.

La preparación obtiene el POM efectivo con Maven Help 3.5.1 dentro de Docker y
descarga los `resourceBundles` declarados mediante Dependency Plugin. El lector
es una herramienta Java de QAgent, sin bibliotecas externas y sin ejecutar fuentes
del usuario. Rechaza XML con DTD y coordenadas sin resolver. La prueba conserva
el mismo padre público que expuso el fallo; no se sustituye por un padre más simple.
La comprobación posterior sigue usando `--offline` y un contenedor sin red.

La clasificación de dependencias internas compara grupo, artefacto y versión,
resolviendo propiedades locales y gestión de versiones. Otra versión publicada
del mismo artefacto sigue tratándose como dependencia externa. BOM internos y
artefactos internos con classifier necesitan preparación adicional y se rechazan
explícitamente por ahora.

Los fallos de preparación con log técnico guardan un `entorno.log` acotado en
la carpeta de la corrida. El Monitor indica su ruta relativa. URLs con usuario,
contraseña o parámetros se limpian y se aplica el saneamiento habitual de secretos.

La comprobación previa es estática: admitir la estructura no garantiza que todos
sus plugins o bibliotecas admitan JDK 25. Las opciones `.mvn/jvm.config`, las
extensiones de Maven, `systemPath` y fuentes fuera de `src/main/java` se rechazan
con un motivo explícito. La preparación admite perfiles explícitos `-P` y
propiedades de versión `revision`, `changelist`, `sha1`; no ignora otras opciones.

Referencia: [configuración oficial de recursos remotos de Maven](https://maven.apache.org/plugins/maven-remote-resources-plugin/usage.html).

## Validación registrada (2026-11-16)

- Tres pruebas Docker de dependencias externas y PIT: aprobadas también en la
  terminal del usuario, 196,30 segundos. Incluyen padre público, módulos internos,
  ejecución sin red y conservación de originales.
- Cinco pruebas Docker de perfiles: aprobadas, 748,32 segundos. Humo aprueba el
  caso normal; Estándar detecta el límite defectuoso; el banco integrado detecta
  tres bugs y aprueba tres funciones, con regresión de las tres aprobadas.
- Profundo informa PIT del 60 % únicamente para el método crítico; `reg_deep`
  reutiliza ese resultado. Spring comprueba un endpoint correcto, otro con estado
  201/200 defectuoso y una omisión justificada, con JaCoCo del 100 %.
- Los proveedores de IA son grabaciones: cero tokens en estas comprobaciones.
  Los contenedores de ejecución no tienen red y se eliminan al finalizar.
- El wheel se construyó y se comprobó que incluye el lector de recursos Maven,
  la preparación y el diagnóstico técnico. Ruff y formato aprobados.

Estos resultados no sustituyen la comprobación visual pendiente de Preparar y
Resultados al abrir una carpeta y un repositorio GitHub desde el escritorio.

### Comprobación visual con ARD-BACKEND

La pantalla Preparar mostró la estructura Maven admitida (1 POM, JDK 25) y
aclaró que las dependencias se comprobarían al preparar Docker. Humo de funciones
terminó con 13 omisiones por falta de oráculo. La corrida de endpoints
`20261116-020748-22ce` registró 7 seleccionados, 4 sin prueba por planificación y
3 omitidos por falta de resultado verificable. No produjo casos planificados ni
pruebas ejecutadas: no se interpreta como compilación o ejecución aprobada.

El diagnóstico mostró IDs como `crearPago_sin_body_400`, rechazados por el
contrato `^[a-z0-9_]+$`. El flujo de endpoints no utiliza la normalización que
ya aplica el flujo de funciones Java. Además, un caso negativo 400 no satisface
el requisito de caso normal de Humo. Corregir solo el ID no crea ese oráculo.
Estos hallazgos pertenecen a planificación, no a la descarga Maven, y requieren
seguimiento separado. El PDF exportado también rotuló el proyecto como Python
aunque la interfaz lo identifica como Java; es un defecto de presentación.

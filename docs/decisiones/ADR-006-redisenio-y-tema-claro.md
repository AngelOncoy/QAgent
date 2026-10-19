# ADR-006: Rediseño visual «Precisión serena», sistema de tokens y activación del tema claro

- **Estado:** Aceptado
- **Fecha:** 2026-10-18
- **Ítem:** Cierre de la migración visual, alineación de informes y activación del tema claro
- **Relacionado:** ADR-001 (modelos y costos), ADR-003 (frontend modular), ADR-004 (nombre único QAgent), ADR-005 (distribución)

---

## 1. Contexto

La interfaz original de QAgent acumuló con el tiempo componentes heterogéneos, paletas dispares (Tailwind ad-hoc, clases utilitarias sobrantes) y pantallas que exponían conceptos técnicos internos en lugar de centrarse en el valor para la persona usuaria:

1. **Exposición de costos monetarios en la interfaz e informes:** El cálculo en US$ generaba ruido cognitivo y confusión sobre gasto en entornos donde se utiliza IA local o cuotas incluidas.
2. **Nombres de agentes internos:** Se mostraban directamente "Planner", "Generator" y "Reviewer", y términos técnicos como "Assertion Laundering" o "mutación", en lugar de etapas y diagnósticos claros («Análisis», «Generación», «Verificación», «Aserciones debilitadas», «Posible bug»).
3. **Inconsistencia entre formatos de exportación:** Mientras el informe PDF había sido rediseñado con métricas canónicas y diagnósticos directos, los formatos Markdown, HTML interactivo y JSON todavía exportaban columnas de US$, topes de gasto y tablas no unificadas.
4. **Falta de soporte para tema claro:** El tema oscuro inicial utilizaba colores fijos o alias duplicados (`--blue`, `--panel`, `--line2`, `--mut`), impidiendo conmutar limpiamente a un tema claro con contraste accesible.
5. **Reglas CSS muertas y componentes obsoletos:** Pantallas antiguas como el selector de perfiles tipo radio («planes de prueba»), modales antiguos (`.fs`, `.card`, `.progress`, `.opts`, `.checks`) y 66 pruebas de frontend comprobaban estructuras ya reemplazadas.

---

## 2. Decisión

### 2.1 Sistema de tokens semánticos («tokens.css»)
- Se consolida `tokens.css` como la **única fuente de verdad visual** de QAgent.
- **Sección 1 (Tema Oscuro por defecto):** Superficies (`--fondo`, `--superficie`, `--superficie-2`, `--hundido`, `--borde`, `--velo`), texto (`--texto`, `--texto-2`, `--texto-3`), acción (`--accion`, `--enlace`, `--foco-anillo`) y estados (`--exito`, `--bug`, `--error`, `--aviso`, `--progreso`).
- **Sección 2 (Tema Claro con contraste WCAG AA):** Activado mediante `data-theme="claro"` / `data-tema="claro"`. Superficies claras de grafito sereno, texto oscuro de alto contraste (> 7:1) y estados cromáticos con legibilidad garantizada.
- **Logos adaptativos:** Logo vectorial claro (`qagent-icono-claro.svg` y `qagent-logo-claro.svg`) con trazo en grafito (`#1B1E23`) para el tema claro, y blanco suave (`#F1F3F6`) para el tema oscuro.
- **Depuración de la paleta heredada:** Se eliminan todas las variables obsoletas y alias antiguos (`--blue`, `--panel`, `--line2`, `--mut`, `--card`, etc.). Solo se conservan en tokens las variables requeridas por datos dinámicos de demostración y logos de proveedores.

### 2.2 Conmutación y persistencia de apariencia
- El selector de **Apariencia** en la pantalla Configuración ofrece las opciones «Oscuro» y «Claro».
- La preferencia se persiste en el `config.local.toml` del usuario (`~/.qagent/config.local.toml`, nunca en la carpeta de instalación del programa) mediante `DesktopAPI.guardar_tema(tema)`.
- Se almacena adicionalmente en `localStorage` del navegador/WebView para evitar parpadeos visuales al arrancar la ventana.

### 2.3 Unificación de informes (PDF, Markdown, HTML, JSON)
- Todos los formatos de exportación se alinean con la estructura de «respuesta primero»:
  1. Conclusión directa (cuántos posibles bugs y por dónde empezar).
  2. Cuatro cifras de resumen: *Pasaron*, *Posibles bugs*, *Cobertura* y *Tokens de la corrida*.
  3. Metas de calidad y Salud del proyecto (`METRICA` e `indice_salud`).
  4. Por dónde empezar (prioridades numeradas con sugerencias accionables).
  5. Resultado por función clasificado en bandejas legibles (`BANDEJA`).
  6. Anexos técnicos: incidentes, suites pytest generadas, contratos del análisis y entorno.
- **Eliminación de costos:** Se eliminan los campos monetarios (`US$`, `costo_usd`, `costo_total_usd`, `tope_por_corrida_usd`). La métrica informa únicamente el volumen total de tokens consumidos.

### 2.4 Funcionalidades retiradas
- Se eliminan definitivamente las vistas de comparación de planes/perfiles tipo tarjeta y la estimación de costos en dólares.
- Se retira la leyenda de «caja negra» en la pantalla de Preparar (dejando la etiqueta precisa de caja blanca únicamente en Profundizar).
- Se borran las reglas muertas de `componentes.css` (`.fs`, `.card`, `.progress`, `.footbar`, `.pill`, `.p-*`) y de `config-pruebas.css` (`.opts`, `.checks`).

---

## 3. Alternativas evaluadas

| Alternativa | Evaluación |
|---|---|
| **Detección automática solo por `@media (prefers-color-scheme)`** | Descartada como mecanismo único: en entornos de escritorio corporativos o Windows con modo mixto, la persona usuaria debe poder fijar su preferencia independientemente del sistema. |
| **Persistir el tema solo en `localStorage`** | Descartada: `localStorage` se limpia si se borra la caché del WebView2 o si el usuario corre perfiles limpios; la regla del proyecto exige que las opciones de Configuración se guarden en `~/.qagent/config.local.toml`. |
| **Mantener costos en US$ como columna secundaria** | Descartada: la dispersión de modelos y APIs locales hacía inexacta la conversión fija a dólares. Centrarse en tokens consumidos es consistente y honesto en todos los entornos. |

---

## 4. Consecuencias

### Positivas
- Coherencia visual completa en toda la aplicación de escritorio y en los cuatro formatos exportados.
- El tema claro cumple estándares de accesibilidad WCAG AA en todas las pantallas.
- Reducción de código muerto y simplificación de las pruebas de frontend (172 pruebas limpias sin aserciones relajadas).
- La preferencia de tema sobrevive a cierres, reinicios y reinstalaciones en `~/.qagent/config.local.toml`.

### Mitigaciones
- Para evitar parpadeo de tema oscuro al iniciar WebView2 mientras se conecta la API de Python, el script inicial lee `localStorage` e inmediatamente aplica los atributos `data-theme` y `data-tema` en la etiqueta `<html>`.

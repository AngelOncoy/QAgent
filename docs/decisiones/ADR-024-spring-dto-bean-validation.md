# ADR-024: Escenarios Spring verificables con DTO y Bean Validation

- Fecha: 2026-11-25.
- Estado: Aprobada por el equipo (escenario elegido el 25/11/2026) e implementada para revisión mediante PR.
- Issue: #306. Épica histórica EP-12 (#174), sin reabrirla. Extiende #183 y convive con #302.
- Relacionados: ADR-007/008/009, ADR-016/018 (inferencia, que **no** se extiende a endpoints Spring).

## Problema

La plantilla MockMvc de #183 solo verifica el estado de `@ResponseStatus` y el 400
por la falta de un `@RequestParam`, `@RequestBody` o `@RequestHeader` requerido.
Los backends externos validan casi siempre sus cuerpos con un DTO anotado con
Bean Validation (`@Valid @RequestBody PedidoDto`). Hoy esas restricciones no llegan
al Planner, así que no hay casos positivos y negativos con una procedencia
verificable, y un caso que las use se rechazaría o sería un esperado inventado.

## Escenarios evaluados

| Escenario | Decisión | Motivo |
|---|---|---|
| DTO con `@Valid @RequestBody` y restricciones Bean Validation | **Admitido** | El estado sale de declaraciones: el 400 de una violación lo fija la especificación de Bean Validation y el binding de Spring MVC; el caso válido usa el `@ResponseStatus` declarado. |
| JSON mal formado y tipos incompatibles en ruta/query | No admitido todavía | Verificable, pero no aprobado en esta iteración. |
| `consumes`/`produces` con 415/406 | No admitido todavía | Igual que el anterior. |
| Seguridad, CSRF y autenticación | No admitido | Ver «Seguridad» más abajo. |
| Inferencia de esperados en endpoints | Fuera de alcance | ADR-018 no se extiende a Spring. |

## Decisión

### Qué se lee (análisis estático con tree-sitter)

- Un parámetro `@RequestBody` con `@Valid` (`jakarta.validation.Valid` o
  `javax.validation.Valid`) o con `@Validated` de Spring marca el endpoint como
  validado. Sin una de esas anotaciones las restricciones del DTO no se aplican y
  no se planifican violaciones.
- El tipo del cuerpo se resuelve por import o por paquete a una clase o record
  **del proyecto** analizado. Un tipo genérico, de una biblioteca o ambiguo no es
  representable.
- Del DTO se leen sus campos (o componentes del record) de tipo escalar
  (`String`, primitivos y sus envoltorios, `BigDecimal`/`BigInteger`) con estas
  restricciones de `jakarta.validation.constraints` o `javax.validation.constraints`:
  `NotNull`, `NotBlank`, `NotEmpty`, `Size(min, max)`, `Min`, `Max`, `Positive`,
  `PositiveOrZero`, `Negative`, `NegativeOrZero`. Los valores deben ser literales
  enteros.
- Cualquier otra cosa hace el DTO **no representable** y no se planifican casos
  de validación, con su motivo: `groups`, restricciones de clase o propias,
  `@Pattern`, `@Email`, `@Valid` anidado, campos de tipo objeto o colección,
  anotaciones de Jackson (`@JsonProperty`, `@JsonIgnore`, `@JsonCreator`…) que
  cambian el nombre o la forma del JSON, y herencia del DTO.
- Bean Validation solo actúa si hay un proveedor en el classpath. Se acepta como
  evidencia estática un `spring-boot-starter-validation` o `hibernate-validator`
  declarado en el POM del módulo o en el POM raíz. Sin él, `@Valid` no valida y no
  se planifican violaciones.
- Si el controlador declara `@ExceptionHandler` o el proyecto tiene una clase
  `@ControllerAdvice`/`@RestControllerAdvice`, el manejo de errores puede cambiar
  el 400 (por ejemplo a 422). `@WebMvcTest` con el controlador aislado no cargaría
  ese consejo y la prueba aprobaría un estado que la aplicación real no devuelve.
  En ese caso no se planifican violaciones y se registra el motivo.

### Contrato del Planner (planner_contract.v3)

Se añade el origen `bean_validation`. Igual que `inferido`, exige `evidencia`:
la lista exacta de restricciones del DTO que el caso usa, con la forma
`Dto.campo@Restriccion` (por ejemplo `PedidoDto.cantidad@Max`). Un caso con otro
origen sigue sin poder llevar `evidencia`. No cambia ningún otro contrato.

### Reglas que el adaptador comprueba antes de aceptar un caso

Las comprobaciones son deterministas y no ejecutan Java:

1. **Caso válido**: el JSON tiene exactamente los campos del DTO (sin campos
   desconocidos), del tipo JSON compatible con el tipo Java, y cumple todas las
   restricciones. Espera el `@ResponseStatus` declarado con origen `status_code`.
   Sin un estado declarado no hay caso válido (como en #183).
2. **Caso de violación**: el JSON incumple **una sola** restricción de un campo y
   cumple las demás. Espera 400, con origen `bean_validation`, categoría `error`
   y `evidencia` igual a la restricción incumplida. Una violación que no
   corresponde al DTO, varias a la vez o una evidencia que no coincide se rechazan.
3. **No se afirma un cuerpo de respuesta**: ni el JSON de error de Spring ni el
   mensaje de la restricción; la respuesta de error es configuración de la
   aplicación.

La plantilla MockMvc no cambia: el cuerpo ya se envía con
`contentType("application/json")` y el guardrail AST vuelve a aplicar estas reglas
antes de ejecutar y entre intentos. Los mocks siguen siendo solo los `@MockBean`
de las dependencias declaradas, nunca el controlador ni MockMvc.

### Seguridad, CSRF y autenticación

No se admiten en esta iteración y no se desactivan filtros (`addFilters = false`,
`excludeAutoConfiguration` de seguridad) ni se fabrica un usuario
(`@WithMockUser`) para forzar una aprobación. Con Spring Security en el classpath,
`@WebMvcTest` aplica la configuración de seguridad por defecto de Spring Boot y no
la del proyecto (el controlador se carga aislado), así que el resultado no
representa a la aplicación. Esta limitación queda documentada en
`docs/java/spring-mockmvc.md`; omitir esos endpoints con un motivo de
configuración requiere su propia aprobación.

## Consecuencias

- Los backends con DTO validados obtienen casos positivos y negativos cuyo
  esperado se puede rastrear a una restricción concreta del commit analizado.
- Un fallo de un caso de violación es un bug confirmado como los de #183: la
  procedencia es una declaración, no una inferencia.
- La configuración no representable (sin proveedor de validación, consejo global,
  DTO complejo) se omite con su motivo en vez de convertirse en un bug falso.
- No se cubren mensajes de error, grupos de validación, validación de parámetros
  de ruta/query con `@Validated` en la clase ni seguridad.

package org.qagent.bench.spring;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** Pedido recibido como JSON; sus restricciones son el contrato de validación (#306). */
public record PedidoDto(
        @NotBlank String cliente,
        @Min(1) @Max(10) int cantidad,
        @Size(max = 20) String nota) {
}

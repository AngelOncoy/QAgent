package org.qagent.bench;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.opentest4j.AssertionFailedError;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Comprueba que los defectos sembrados incumplen los contratos de casos.md.
 *
 * <p>Cada prueba exige que la comparación con el resultado correcto falle.
 * Si el método empieza a cumplir el contrato, esta verificación avisará.
 */
class BancoDefectuosoTest {

    private static final double TOLERANCIA = 0.000001;

    /** D01: detecta la pérdida de decimales por división entera. */
    @Test
    void detectaDivisionEntera() {
        double resultado =
                BancoDefectuoso.calcularPromedio(List.of(2, 3));

        assertThrowsExactly(
                AssertionFailedError.class,
                () -> assertEquals(
                        2.5, resultado, TOLERANCIA,
                        "D01: el promedio debe conservar los decimales"
                )
        );
    }

    /** D02: detecta la exclusión del límite de envío gratuito. */
    @Test
    void detectaLimiteDeEnvioIncorrecto() {
        double resultado = BancoDefectuoso.calcularEnvio(100.0);

        assertThrowsExactly(
                AssertionFailedError.class,
                () -> assertEquals(
                        0.0, resultado, TOLERANCIA,
                        "D02: una compra de 100 debe tener envío gratuito"
                )
        );
    }

    /** D03: detecta que el impuesto se resta en lugar de sumarse. */
    @Test
    void detectaImpuestoRestado() {
        double resultado =
                BancoDefectuoso.calcularTotalConImpuesto(100.0, 18.0);

        assertThrowsExactly(
                AssertionFailedError.class,
                () -> assertEquals(
                        118.0, resultado, TOLERANCIA,
                        "D03: el impuesto debe sumarse al subtotal"
                )
        );
    }
}
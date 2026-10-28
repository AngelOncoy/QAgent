package org.qagent.bench;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Comprueba los casos correctos según las reglas de casos.md.
 */
class BancoCorrectoTest {

    private static final double TOLERANCIA = 0.000001;

    /** C01: sumar los precios de una lista. */
    @Test
    void sumaLosPrecios() {
        assertEquals(
                30.0,
                BancoCorrecto.sumarPrecios(List.of(10.0, 20.0)),
                TOLERANCIA
        );
    }

    /** C01: una lista vacía tiene suma cero. */
    @Test
    void listaVaciaDevuelveCero() {
        assertEquals(
                0.0,
                BancoCorrecto.sumarPrecios(List.of()),
                TOLERANCIA
        );
    }

    /** C02: descontar el 20 % de 100 deja 80. */
    @Test
    void aplicaElDescuento() {
        assertEquals(
                80.0,
                BancoCorrecto.aplicarDescuento(100.0, 20.0),
                TOLERANCIA
        );
    }

    /** C02: un descuento de cero conserva el precio. */
    @Test
    void descuentoCeroConservaElPrecio() {
        assertEquals(
                100.0,
                BancoCorrecto.aplicarDescuento(100.0, 0.0),
                TOLERANCIA
        );
    }

    /** C02: un descuento del 100 % deja el precio en cero. */
    @Test
    void descuentoTotalDevuelveCero() {
        assertEquals(
                0.0,
                BancoCorrecto.aplicarDescuento(100.0, 100.0),
                TOLERANCIA
        );
    }

    /** C03: los 18 años están incluidos en la mayoría de edad. */
    @Test
    void dieciochoEsMayorDeEdad() {
        assertTrue(BancoCorrecto.esMayorDeEdad(18));
    }

    /** C03: una edad inferior al límite no es mayoría de edad. */
    @Test
    void diecisieteEsMenorDeEdad() {
        assertFalse(BancoCorrecto.esMayorDeEdad(17));
    }

    /** C03: una edad superior al límite es mayoría de edad. */
    @Test
    void edadSuperiorEsMayorDeEdad() {
        assertTrue(BancoCorrecto.esMayorDeEdad(25));
    }
}
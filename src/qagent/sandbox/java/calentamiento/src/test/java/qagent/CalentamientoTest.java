package qagent;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class CalentamientoTest {

    @Test
    void sumaDosEnteros() {
        assertEquals(5, Calentamiento.sumar(2, 3));
    }
}

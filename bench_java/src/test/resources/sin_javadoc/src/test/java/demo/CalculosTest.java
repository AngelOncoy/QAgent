package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculosTest {
    @Test void sumaNormal() { assertEquals(5, Calculos.sumar(2, 3)); }
    @Test void dobleNormal() { assertEquals(8, Calculos.doble(4)); }
}

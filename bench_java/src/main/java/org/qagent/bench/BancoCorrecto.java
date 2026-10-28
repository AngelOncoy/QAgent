package org.qagent.bench;

import java.util.List;

/**
 * Casos correctos del banco Java de QAgent.
 *
 * <p>Las reglas se definen en casos.md. Las entradas deben cumplir
 * las precondiciones documentadas en cada método.
 */
public final class BancoCorrecto {

    private BancoCorrecto() {
        // Clase de utilidades: no necesita instancias.
    }

    /**
     * Suma los precios recibidos. Una lista vacía devuelve cero.
     *
     * @param precios lista no nula con precios finitos y no negativos
     * @return suma de los precios; por ejemplo, [10, 20] devuelve 30
     */
    public static double sumarPrecios(List<Double> precios) {
        double total = 0.0;
        for (double precio : precios) {
            total += precio;
        }
        return total;
    }

    /**
     * Aplica un descuento: precio final = precio × (1 - porcentaje / 100).
     *
     * @param precio importe finito y no negativo
     * @param porcentaje descuento entre 0 y 100, inclusive
     * @return precio con descuento; por ejemplo, 100 con 20 % devuelve 80
     */
    public static double aplicarDescuento(double precio, double porcentaje) {
        return precio * (1.0 - porcentaje / 100.0);
    }

    /**
     * Determina si la edad es mayor o igual a 18 años.
     *
     * @param edad edad entera no negativa
     * @return true desde los 18 años, inclusive; false para edades menores
     */
    public static boolean esMayorDeEdad(int edad) {
        return edad >= 18;
    }
}
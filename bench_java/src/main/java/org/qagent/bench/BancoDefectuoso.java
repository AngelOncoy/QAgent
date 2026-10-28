package org.qagent.bench;

import java.util.List;

/**
 * Banco con tres defectos intencionales para TA-01.
 *
 * <p>Los contratos describen el comportamiento correcto de casos.md.
 * Las implementaciones incumplen esos contratos deliberadamente.
 */
public final class BancoDefectuoso {

    private BancoDefectuoso() {
        // Clase de utilidades: no necesita instancias.
    }

    /**
     * Calcula el promedio conservando la parte decimal.
     *
     * @param numeros lista no nula y no vacía de enteros;
     *                su suma debe caber en un int
     * @return promedio aritmético; por ejemplo, [2, 3] devuelve 2.5
     * @implNote D01: contiene una división entera intencional.
     */
    public static double calcularPromedio(List<Integer> numeros) {
        int suma = 0;
        for (int numero : numeros) {
            suma += numero;
        }

        // D01: pierde los decimales antes de convertir a double.
        return suma / numeros.size();
    }

    /**
     * Calcula el envío: cuesta 10 para compras menores a 100
     * y es gratuito desde 100, inclusive.
     *
     * @param importe importe de compra finito y no negativo
     * @return costo del envío; para una compra de 100 devuelve 0
     * @implNote D02: excluye intencionalmente el límite de 100.
     */
    public static double calcularEnvio(double importe) {
        // D02: debería incluir la igualdad.
        return importe > 100.0 ? 0.0 : 10.0;
    }

    /**
     * Añade el impuesto: total = subtotal × (1 + porcentaje / 100).
     *
     * @param subtotal importe finito y no negativo
     * @param porcentaje porcentaje de impuesto finito y no negativo
     * @return total con impuesto; 100 con 18 % devuelve 118
     * @implNote D03: resta intencionalmente el impuesto.
     */
    public static double calcularTotalConImpuesto(
            double subtotal, double porcentaje) {
        // D03: resta el impuesto en lugar de sumarlo.
        return subtotal * (1.0 - porcentaje / 100.0);
    }
}
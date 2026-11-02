package com.qagent.bench;

import java.util.List;
import java.util.Map;
import java.util.HashMap;

/**
 * Módulo de cálculo comercial y clasificación para benchmark multilenguaje.
 *
 * Implementación de referencia en Java para evaluar la extracción estática
 * con Tree-sitter y parsers de Java frente a la especificación de QAgent.
 */
public class Calculadora {

    /**
     * Calcula el monto final tras aplicar un porcentaje de descuento.
     *
     * @param precio Monto original del producto, debe ser mayor o igual a 0.
     * @param porcentaje Porcentaje de descuento, valor entre 0 y 100 inclusive.
     * @return Precio final con el descuento aplicado.
     * @throws IllegalArgumentException Si el precio o porcentaje están fuera de rango.
     */
    public static double calcularDescuento(double precio, double porcentaje) {
        if (precio < 0) {
            throw new IllegalArgumentException("El precio no puede ser negativo.");
        }
        if (porcentaje < 0 || porcentaje > 100) {
            throw new IllegalArgumentException("El porcentaje debe estar entre 0 y 100.");
        }

        double descuento = precio * (porcentaje / 100.0);
        return precio - descuento;
    }

    /**
     * Clasifica a una persona según su rango etario.
     *
     * @param edad Años cumplidos, debe ser mayor o igual a 0.
     * @return Categoría ("menor", "adulto", "adulto mayor").
     * @throws IllegalArgumentException Si la edad es menor a 0.
     */
    public static String clasificarEdad(int edad) {
        if (edad < 0) {
            throw new IllegalArgumentException("La edad no puede ser negativa.");
        }

        if (edad < 18) {
            return "menor";
        } else if (edad <= 64) {
            return "adulto";
        } else {
            return "adulto mayor";
        }
    }

    /**
     * Calcula mínimo, máximo y promedio de una lista de valores numéricos.
     *
     * @param numeros Lista de números, no debe ser nula ni vacía.
     * @return Mapa con claves "minimo", "maximo" y "promedio".
     * @throws IllegalArgumentException Si la lista está vacía.
     */
    public static Map<String, Double> calcularEstadisticas(List<Double> numeros) {
        if (numeros == null || numeros.isEmpty()) {
            throw new IllegalArgumentException("La lista no puede estar vacía.");
        }

        double minimo = numeros.get(0);
        double maximo = numeros.get(0);
        double suma = 0.0;

        for (double n : numeros) {
            if (n < minimo) {
                minimo = n;
            }
            if (n > maximo) {
                maximo = n;
            }
            suma += n;
        }

        double promedio = suma / numeros.size();
        Map<String, Double> resultado = new HashMap<>();
        resultado.put("minimo", minimo);
        resultado.put("maximo", maximo);
        resultado.put("promedio", promedio);
        return resultado;
    }

    /**
     * Gestiona cálculos de impuestos y recargos comerciales.
     */
    public static class GestorImpuestos {
        private final double tasaIgv;

        /**
         * Inicializa el gestor con una tasa configurada.
         * @param tasaIgv Tasa de impuesto.
         */
        public GestorImpuestos(double tasaIgv) {
            if (tasaIgv < 0) {
                throw new IllegalArgumentException("La tasa de IGV no puede ser negativa.");
            }
            this.tasaIgv = tasaIgv;
        }

        /**
         * Constructor por defecto con tasa IGV estándar (0.18).
         */
        public GestorImpuestos() {
            this(0.18);
        }

        /**
         * Calcula el importe total incluyendo el IGV.
         * @param baseImponible Monto base sin impuesto.
         * @return Monto con impuesto.
         */
        public double aplicarIgv(double baseImponible) {
            if (baseImponible < 0) {
                throw new IllegalArgumentException("La base imponible no puede ser negativa.");
            }
            return baseImponible * (1.0 + this.tasaIgv);
        }

        /**
         * Calcula el total con IGV y propina voluntaria.
         * @param subtotal Monto base.
         * @param porcentajePropina Porcentaje de propina.
         * @return Total con IGV y propina.
         */
        public double calcularTotalConPropina(double subtotal, double porcentajePropina) {
            double conIgv = this.aplicarIgv(subtotal);
            double propina = subtotal * (porcentajePropina / 100.0);
            return conIgv + propina;
        }
    }
}

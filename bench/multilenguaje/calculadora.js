/**
 * Módulo de cálculo comercial y clasificación para benchmark multilenguaje.
 *
 * Versión JavaScript con anotaciones JSDoc completas para evaluación de tipos
 * y documentación en parsers estáticos sin compilador de TypeScript.
 */

/**
 * Calcula el monto final tras aplicar un porcentaje de descuento.
 *
 * @param {number} precio - Monto original del producto, debe ser mayor o igual a 0.
 * @param {number} porcentaje - Porcentaje de descuento, valor entre 0 y 100 inclusive.
 * @returns {number} Precio final con el descuento aplicado.
 * @throws {Error} Si el precio es negativo o el porcentaje no está entre 0 y 100.
 */
function calcularDescuento(precio, porcentaje) {
    if (precio < 0) {
        throw new Error("El precio no puede ser negativo.");
    }
    if (porcentaje < 0 || porcentaje > 100) {
        throw new Error("El porcentaje debe estar entre 0 y 100.");
    }

    const descuento = precio * (porcentaje / 100.0);
    return precio - descuento;
}

/**
 * Clasifica a una persona según su rango etario.
 *
 * @param {number} edad - Años cumplidos, debe ser mayor o igual a 0.
 * @returns {string} Categoría ('menor', 'adulto', 'adulto mayor').
 * @throws {Error} Si la edad es menor a 0.
 */
function clasificarEdad(edad) {
    if (edad < 0) {
        throw new Error("La edad no puede ser negativa.");
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
 * @param {number[]} numeros - Lista de números, no debe estar vacía.
 * @returns {{minimo: number, maximo: number, promedio: number}} Estadísticas calculadas.
 * @throws {Error} Si la lista está vacía.
 */
function calcularEstadisticas(numeros) {
    if (!numeros || numeros.length === 0) {
        throw new Error("La lista no puede estar vacía.");
    }

    let minimo = numeros[0];
    let maximo = numeros[0];
    let suma = 0.0;

    for (const n of numeros) {
        if (n < minimo) {
            minimo = n;
        }
        if (n > maximo) {
            maximo = n;
        }
        suma += n;
    }

    const promedio = suma / numeros.length;
    return { minimo, maximo, promedio };
}

/**
 * Gestiona cálculos de impuestos y recargos comerciales.
 */
class GestorImpuestos {
    /**
     * Inicializa el gestor con una tasa de impuesto configurada.
     * @param {number} [tasaIgv=0.18] - Tasa de impuesto.
     */
    constructor(tasaIgv = 0.18) {
        if (tasaIgv < 0) {
            throw new Error("La tasa de IGV no puede ser negativa.");
        }
        this.tasaIgv = tasaIgv;
    }

    /**
     * Calcula el importe total incluyendo el IGV.
     * @param {number} baseImponible - Monto base sin impuesto.
     * @returns {number}
     */
    aplicarIgv(baseImponible) {
        if (baseImponible < 0) {
            throw new Error("La base imponible no puede ser negativa.");
        }
        return baseImponible * (1.0 + this.tasaIgv);
    }

    /**
     * Calcula el total con IGV y propina voluntaria.
     * @param {number} subtotal - Monto base.
     * @param {number} [porcentajePropina=10.0] - Porcentaje de propina.
     * @returns {number}
     */
    calcularTotalConPropina(subtotal, porcentajePropina = 10.0) {
        const conIgv = this.aplicarIgv(subtotal);
        const propina = subtotal * (porcentajePropina / 100.0);
        return conIgv + propina;
    }
}

/**
 * Registra una operación financiera de forma asíncrona.
 * @param {string} tipo
 * @param {number} monto
 * @returns {Promise<boolean>}
 */
async function registrarOperacion(tipo, monto) {
    if (!tipo || monto <= 0) {
        return false;
    }
    return true;
}

module.exports = {
    calcularDescuento,
    clasificarEdad,
    calcularEstadisticas,
    GestorImpuestos,
    registrarOperacion,
};

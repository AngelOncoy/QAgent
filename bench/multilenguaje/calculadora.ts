/**
 * Módulo de cálculo comercial y clasificación para benchmark multilenguaje.
 *
 * Este módulo sirve como referencia para evaluar las capacidades de extracción
 * de parsers estáticos (TypeScript AST, Tree-sitter y parsers nativos).
 */

export interface Estadisticas {
    minimo: number;
    maximo: number;
    promedio: number;
}

/**
 * Calcula el monto final tras aplicar un porcentaje de descuento.
 *
 * @param precio - Monto original del producto, debe ser mayor o igual a 0.
 * @param porcentaje - Porcentaje de descuento, valor entre 0 y 100 inclusive.
 * @returns Precio final con el descuento aplicado.
 * @throws {Error} Si el precio es negativo o el porcentaje no está entre 0 y 100.
 */
export function calcularDescuento(precio: number, porcentaje: number): number {
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
 * @param edad - Años cumplidos, debe ser mayor o igual a 0.
 * @returns Categoría ('menor', 'adulto', 'adulto mayor').
 * @throws {Error} Si la edad es menor a 0.
 */
export function clasificarEdad(edad: number): string {
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
 * @param numeros - Lista de números, no debe estar vacía.
 * @returns Objeto con las claves minimo, maximo y promedio.
 * @throws {Error} Si la lista está vacía.
 */
export function calcularEstadisticas(numeros: number[]): Estadisticas {
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
export class GestorImpuestos {
    private tasaIgv: number;

    /**
     * Inicializa el gestor con una tasa de impuesto configurada.
     * @param tasaIgv - Tasa de impuesto (por defecto 0.18).
     */
    constructor(tasaIgv: number = 0.18) {
        if (tasaIgv < 0) {
            throw new Error("La tasa de IGV no puede ser negativa.");
        }
        this.tasaIgv = tasaIgv;
    }

    /**
     * Calcula el importe total incluyendo el IGV.
     * @param baseImponible - Monto base sin impuesto.
     */
    public aplicarIgv(baseImponible: number): number {
        if (baseImponible < 0) {
            throw new Error("La base imponible no puede ser negativa.");
        }
        return baseImponible * (1.0 + this.tasaIgv);
    }

    /**
     * Calcula el total con IGV y propina voluntaria.
     * @param subtotal - Monto base.
     * @param porcentajePropina - Porcentaje de propina (por defecto 10.0).
     */
    public calcularTotalConPropina(subtotal: number, porcentajePropina: number = 10.0): number {
        const conIgv = this.aplicarIgv(subtotal);
        const propina = subtotal * (porcentajePropina / 100.0);
        return conIgv + propina;
    }
}

/**
 * Registra una operación financiera de forma asíncrona.
 */
export async function registrarOperacion(tipo: string, monto: number): Promise<boolean> {
    if (!tipo || monto <= 0) {
        return false;
    }
    return true;
}

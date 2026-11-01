/**
 * Verifica si una palabra o frase es un palíndromo.
 * Ignora mayúsculas, minúsculas, espacios y signos.
 *
 * @param {string} texto Cadena a evaluar.
 * @returns {boolean} true si se lee igual en ambos sentidos.
 * @example
 * esPalindromo("Anita lava la tina") // => true
 * esPalindromo("QAgent") // => false
 */
export function esPalindromo(texto: string): boolean {
  const limpio = texto.toLowerCase().replace(/[^a-z0-9ñáéíóú]/g, "");
  return limpio === [...limpio].reverse().join("");
}

/**
 * Invierte el orden de las palabras de una oración, separadas por un espacio.
 *
 * @param {string} frase Oración de entrada.
 * @returns {string} La frase con las palabras en orden inverso.
 * @example
 * invertirPalabras("hola  mundo cruel") // => "cruel mundo hola"
 */
export const invertirPalabras = (frase: string): string =>
  frase.split(/\s+/).filter(Boolean).reverse().join(" ");

export class Formateador {
  /**
   * Formatea una cantidad como moneda con dos decimales.
   *
   * @param {number} cantidad Valor a formatear.
   * @param {string} [simbolo="$"] Prefijo de la moneda.
   * @returns {string} El texto formateado.
   * @example
   * new Formateador().moneda(12.5) // => "$12.50"
   * new Formateador().moneda(3, "S/ ") // => "S/ 3.00"
   */
  moneda(cantidad: number, simbolo = "$"): string {
    return `${simbolo}${cantidad.toFixed(2)}`;
  }
}

/** Versión del formato de los informes. */
export function versionFormato(): "v1" {
  return "v1";
}

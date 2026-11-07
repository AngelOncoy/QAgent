/**
 * Precio con dos decimales y el símbolo de soles.
 * @param {number} monto
 * @returns {string}
 * @example formatearPrecio(5) // => "S/ 5.00"
 */
export function formatearPrecio(monto: number): string {
  return `S/ ${monto.toFixed(2)}`;
}

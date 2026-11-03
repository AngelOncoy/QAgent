/**
 * Calcula el precio final tras aplicar un porcentaje de descuento.
 *
 * @param {number} precio Monto original del producto; debe ser mayor o igual a 0.
 * @param {number} porcentaje Porcentaje de descuento, entre 0 y 100 inclusive.
 * @returns {number} Precio final con el descuento aplicado.
 * @throws {RangeError} si el precio es negativo o el porcentaje no está entre 0 y 100.
 * @example
 * calcularDescuento(100, 20) // => 80
 * calcularDescuento(50, 0) // => 50
 * calcularDescuento(-1, 10) // throws RangeError
 */
export function calcularDescuento(precio: number, porcentaje: number): number {
  if (precio < 0) {
    throw new RangeError("El precio no puede ser negativo.");
  }
  if (porcentaje < 0 || porcentaje > 100) {
    throw new RangeError("El porcentaje debe estar entre 0 y 100.");
  }
  // Bug 1: devuelve el monto del descuento, no el precio final.
  const montoDescuento = precio * (porcentaje / 100);
  return montoDescuento;
}

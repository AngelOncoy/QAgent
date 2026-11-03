/**
 * Clasifica a una persona según su rango etario.
 *
 * - "menor": de 0 a 17 años.
 * - "adulto": de 18 a 64 años inclusive.
 * - "adulto mayor": 65 años o más.
 *
 * @param {number} edad Años cumplidos; debe ser mayor o igual a 0.
 * @returns {"menor" | "adulto" | "adulto mayor"} La categoría correspondiente.
 * @throws {RangeError} si la edad es negativa.
 * @example
 * clasificarEdad(10) // => "menor"
 * clasificarEdad(18) // => "adulto"
 * clasificarEdad(64) // => "adulto"
 * clasificarEdad(65) // => "adulto mayor"
 */
export function clasificarEdad(edad) {
  if (edad < 0) {
    throw new RangeError("La edad no puede ser negativa.");
  }
  // Bug 2: frontera incorrecta; 18 años ya es "adulto".
  if (edad <= 18) {
    return "menor";
  } else if (edad <= 64) {
    return "adulto";
  }
  return "adulto mayor";
}

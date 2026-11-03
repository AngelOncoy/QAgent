/**
 * Encuentra el valor numérico máximo en una lista.
 *
 * @param {number[]} numeros Lista de números; no debe estar vacía.
 * @returns {number} El número de mayor valor de la lista.
 * @throws {RangeError} si la lista está vacía.
 * @example
 * buscarElementoMayor([3, 9, 2]) // => 9
 * buscarElementoMayor([-10, -5, -20]) // => -5
 */
function buscarElementoMayor(numeros) {
  if (numeros.length === 0) {
    throw new RangeError("La lista no puede estar vacía.");
  }
  // Bug 3: empezar en 0 falla si todos los números son negativos.
  let maximo = 0;
  for (const numero of numeros) {
    if (numero > maximo) {
      maximo = numero;
    }
  }
  return maximo;
}

module.exports = { buscarElementoMayor };

// Sin JSDoc ni tipos: QAgent no puede saber el resultado esperado y no le planifica
// casos («sin resultado esperado verificable»).
export function mezclar(a, b) {
  return a > b ? a - b : b * 2;
}

/**
 * Promedio de los valores.
 * @param {number[]} valores
 * @returns {number} el promedio aritmético
 */
export function promedio(valores) {
  return valores.reduce((total, v) => total + v, 0) / valores.length;
}

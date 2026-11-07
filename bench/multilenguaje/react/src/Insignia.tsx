type InsigniaProps = {
  /** Si el producto tiene stock. */
  disponible: boolean;
};

/**
 * Insignia de stock de un producto.
 * Muestra el texto "Agotado" cuando disponible es false y no muestra nada si hay stock.
 */
export default function Insignia({ disponible }: InsigniaProps) {
  // BUG sembrado: el JSDoc promete "Agotado".
  return disponible ? null : <span role="status">Sin stock</span>;
}

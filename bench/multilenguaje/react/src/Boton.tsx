import { useState } from "react";

interface BotonProps {
  /** Texto visible del botón. */
  etiqueta: string;
  deshabilitado?: boolean;
  /** Se llama una vez cada vez que se pulsa el botón. */
  onPulsar: () => void;
}

/** Botón de pago: muestra su etiqueta y avisa con onPulsar al pulsarlo. */
export function Boton({ etiqueta, deshabilitado = false, onPulsar }: BotonProps) {
  const [pulsaciones, setPulsaciones] = useState(0);
  return (
    <button
      type="button"
      disabled={deshabilitado}
      data-pulsaciones={pulsaciones}
      onClick={() => {
        setPulsaciones(pulsaciones + 1);
        onPulsar();
      }}
    >
      {etiqueta}
    </button>
  );
}

"""Diagnóstico de construcción previo a los agentes, independiente del lenguaje."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.disco import escribir_json_atomico, escribir_texto_atomico
from qagent.lenguajes.base import ResultadoConstruccion
from qagent.storage.diagnostico_entorno import sanear_diagnostico


def guardar_construccion(
    raiz: Path, run_id: str, resultado: ResultadoConstruccion
) -> dict[str, Any]:
    """Guarda metadatos y log saneado en la corrida; nunca modifica históricos."""
    carpeta = AlmacenProyecto(raiz).carpeta_run(run_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = {"version": "1", **resultado.metadatos()}
    archivo_log = carpeta / "construccion.log"
    cabecera = json.dumps(datos, ensure_ascii=False, indent=2)
    escribir_texto_atomico(
        archivo_log, sanear_diagnostico(cabecera + "\n\n" + resultado.log)
    )
    datos["log"] = archivo_log.relative_to(raiz).as_posix()
    escribir_json_atomico(carpeta / "construccion.json", datos)
    return datos

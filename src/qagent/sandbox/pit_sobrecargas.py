"""Exclusión por declaración en la copia desechable de PIT, sin cambiar cuerpos."""

from pathlib import Path

from qagent.lenguajes.java_firmas import indexar_metodos, separar_objetivo
from qagent.lenguajes.treesitter import obtener_parser

ANOTACION = "qagent.internal.exclusion299.QAgentNoMutar"
FUENTE_ANOTACION = """package qagent.internal.exclusion299;
@java.lang.annotation.Retention(java.lang.annotation.RetentionPolicy.CLASS)
@java.lang.annotation.Target(java.lang.annotation.ElementType.METHOD)
public @interface QAgentNoMutar {}
"""


def excluir_sobrecargas(
    copia: Path, modulo: str, fuente: str, funciones: list[str]
) -> None:
    """Marca las sobrecargas no seleccionadas para FANN antes de generar mutantes.

    Solo se llama sobre la copia que ya creó el ejecutor. Conserva cuerpos,
    aserciones y números de línea; rechaza una colisión con la ruta reservada.
    """
    anotacion = copia / "src/main/java" / (ANOTACION.replace(".", "/") + ".java")
    if (
        anotacion.exists()
        or anotacion.is_symlink()
        or not anotacion.resolve().is_relative_to(copia.resolve())
        or any(p.is_symlink() for p in anotacion.parents if p != copia.parent)
    ):
        raise ValueError("El proyecto ocupa la ruta reservada de exclusión PIT.")
    raiz = obtener_parser("java").parse(fuente.encode("utf-8")).root_node
    indice = indexar_metodos(raiz)
    seleccionados = {separar_objetivo(f) for f in funciones}
    inserciones = [
        n.start_byte
        for nombre, n in indice.items()
        if nombre not in funciones and separar_objetivo(nombre) in seleccionados
    ]
    contenido = fuente.encode("utf-8")
    for inicio in sorted(inserciones, reverse=True):
        contenido = (
            contenido[:inicio]
            + ("@" + ANOTACION + " ").encode("utf-8")
            + contenido[inicio:]
        )
    anotacion.parent.mkdir(parents=True, exist_ok=True)
    anotacion.write_text(FUENTE_ANOTACION, encoding="utf-8")
    (copia / modulo).write_bytes(contenido)

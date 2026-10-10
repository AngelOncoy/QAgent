"""Almacenamiento de QAgent dentro del proyecto del usuario: `.pyagent/` (EN-07).

Estructura::

    <proyecto>/.pyagent/
        .gitignore          ignora runs/ (specs y pruebas aprobadas sí se pueden versionar)
        runs/<run_id>/      una carpeta por corrida
        specs/              specs de cada prueba, para el modo regresión
        tests/              solo las pruebas aprobadas (test_*.py)

Es el único lugar que crea esta estructura. No depende de la interfaz.
"""

from __future__ import annotations

from pathlib import Path

from pyagent.almacenamiento.disco import escribir_texto_atomico

CARPETA = ".pyagent"
CONTENIDO_GITIGNORE = (
    "# Generado por QAgent: las corridas no se versionan.\n"
    "# specs/ y tests/ (pruebas aprobadas) sí se pueden subir al repositorio.\n"
    "runs/\n"
)


class AlmacenProyecto:
    """Acceso a `.pyagent/` de un proyecto. Cada instancia lee del disco: no guarda caché.

    Atributos:
        raiz: carpeta del proyecto del usuario.
        carpeta: `<raiz>/.pyagent`.
        carpeta_runs, carpeta_specs, carpeta_tests: subcarpetas de `carpeta`.
    """

    def __init__(self, ruta_proyecto: str | Path) -> None:
        """Prepara las rutas; no toca el disco hasta `inicializar()` o un `guardar_*`."""
        self.raiz = Path(ruta_proyecto)
        self.carpeta = self.raiz / CARPETA
        self.carpeta_runs = self.carpeta / "runs"
        self.carpeta_specs = self.carpeta / "specs"
        self.carpeta_tests = self.carpeta / "tests"

    def existe(self) -> bool:
        """Indica si el proyecto ya tiene la carpeta `.pyagent/`."""
        return self.carpeta.is_dir()

    def inicializar(self) -> None:
        """Crea `.pyagent/`, sus subcarpetas y el `.gitignore` si faltan (idempotente).

        Nunca borra ni sobrescribe nada: un `.gitignore` editado por el usuario se respeta.

        Raises:
            OSError: si no se puede escribir en la carpeta del proyecto.
        """
        for carpeta in (self.carpeta_runs, self.carpeta_specs, self.carpeta_tests):
            carpeta.mkdir(parents=True, exist_ok=True)
        gitignore = self.carpeta / ".gitignore"
        if not gitignore.exists():
            escribir_texto_atomico(gitignore, CONTENIDO_GITIGNORE)

"""Almacenamiento de QAgent dentro del proyecto del usuario: `.pyagent/` (EN-07).

Estructura::

    <proyecto>/.pyagent/
        .gitignore          ignora runs/ (specs y pruebas aprobadas sí se pueden versionar)
        runs/<run_id>/      una carpeta por corrida: run.json, y log.json y
                            results.json (EN-05, `pyagent.storage`)
        specs/<id>.json     spec de cada prueba (contrato del Planner), para regresión
        tests/test_*.py     solo las pruebas aprobadas

El historial son los `run.json` ordenados por `run_id` (empieza con la fecha), sin un
archivo de índice aparte. Es el único lugar que crea esta estructura. No depende de la
interfaz ni del orquestador.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from pyagent import contracts
from pyagent.almacenamiento.disco import (
    DatoCorrupto,
    DatoNoEncontrado,
    ErrorAlmacen,
    escribir_json_atomico,
    escribir_texto_atomico,
    leer_json_objeto,
)
from pyagent.storage.registro import nuevo_run_id

CARPETA = ".pyagent"
CONTENIDO_GITIGNORE = (
    "# Generado por QAgent: las corridas no se versionan.\n"
    "# specs/ y tests/ (pruebas aprobadas) sí se pueden subir al repositorio.\n"
    "runs/\n"
)
ARCHIVO_RUN = "run.json"

# Estados de una corrida: "en_curso" hasta que termina; luego el estado final del
# orquestador ("fin" o "fallo_controlado"). Si la app se cierra a mitad, queda "en_curso".
ESTADOS_RUN = ("en_curso", "fin", "fallo_controlado")
# "vigente" se reutiliza en regresión; "obsoleta" cuando el código cambió (HU-24).
ESTADOS_SPEC = ("vigente", "obsoleta")
TIPOS_PRUEBA = ("funcion", "endpoint")
CAMPOS_RUN = (
    "run_id",
    "inicio",
    "fin",
    "tipos_prueba",
    "imagen_docker",
    "estado",
    "resumen",
)
CAMPOS_SPEC = ("id", "creado", "run_origen", "estado", "archivo_prueba", "contrato")

PATRON_RUN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
PATRON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
PATRON_PRUEBA = re.compile(r"^test_[A-Za-z0-9_]+\.py$")


def _iso(momento: datetime | None = None) -> str:
    return (momento or datetime.now().astimezone()).isoformat(timespec="seconds")


def _nombre(ruta: Path) -> str:
    """Clave de orden: el nombre como texto. `Path` ordena distinto en Windows
    (sin distinguir mayúsculas) que en Linux; así el orden es el mismo en ambos."""
    return ruta.name


def id_de_spec(modulo: str, objetivo: str) -> str:
    """Identificador estable de la spec de un objetivo: `<modulo>__<objetivo>`.

    Solo letras, números y `_`, para usarlo como nombre de archivo en cualquier
    sistema. Ej.: `("tienda/precios.py", "calcular")` -> `tienda_precios_py__calcular`;
    `("api.py", "GET /items/{id}")` -> `api_py__GET_items_id` (endpoint).
    """

    def limpiar(texto: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_")

    return f"{limpiar(modulo)}__{limpiar(objetivo)}"


def nombre_prueba(spec_id: str) -> str:
    """Nombre del archivo de la prueba aprobada de una spec: `test_<spec_id>.py`."""
    return f"test_{spec_id.replace('-', '_')}.py"


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

    # --- Corridas -------------------------------------------------------------------

    def carpeta_run(self, run_id: str) -> Path:
        """Carpeta de una corrida; ahí van también sus resultados y logs.

        Raises:
            ErrorAlmacen: si `run_id` no tiene el formato `AAAAMMDD-HHMMSS-xxxx`.
        """
        if not isinstance(run_id, str) or not PATRON_RUN_ID.match(run_id):
            raise ErrorAlmacen(f"run_id no válido: {run_id!r}")
        return self.carpeta_runs / run_id

    def crear_run(
        self,
        tipos_prueba: Iterable[str] = (),
        imagen_docker: str | None = None,
        ahora: datetime | None = None,
    ) -> dict[str, Any]:
        """Crea la carpeta y el `run.json` de una corrida nueva, en estado `en_curso`.

        Args:
            tipos_prueba: "funcion" y/o "endpoint" (se puede completar al terminar).
            imagen_docker: imagen del sandbox usada (versión del entorno), o None si
                la corrida no usa Docker (IA simulada).
            ahora: momento de inicio; por defecto, la hora local actual.

        Returns:
            El contenido de `run.json`.

        Raises:
            ErrorAlmacen: si algún tipo de prueba no es válido.
            OSError: si no se puede escribir.
        """
        momento = ahora or datetime.now().astimezone()
        run = {
            "run_id": nuevo_run_id(momento),
            "inicio": _iso(momento),
            "fin": None,
            "tipos_prueba": list(tipos_prueba),
            "imagen_docker": imagen_docker,
            "estado": "en_curso",
            "resumen": None,
        }
        self.guardar_run(run)
        return run

    def guardar_run(self, run: dict[str, Any]) -> Path:
        """Valida y escribe `runs/<run_id>/run.json` (lo reemplaza si ya existía).

        Raises:
            ErrorAlmacen: si a `run` le faltan campos o tienen valores no válidos.
            OSError: si no se puede escribir.
        """
        _validar_run(run)
        self.inicializar()
        ruta = self.carpeta_run(run["run_id"]) / ARCHIVO_RUN
        escribir_json_atomico(ruta, {c: run[c] for c in CAMPOS_RUN})
        return ruta

    def finalizar_run(
        self,
        run_id: str,
        estado: str,
        pasaron: int,
        fallaron: int,
        tipos_prueba: Iterable[str] | None = None,
        ahora: datetime | None = None,
    ) -> dict[str, Any]:
        """Marca el fin de una corrida con su estado final y el resumen.

        Returns:
            El `run.json` actualizado.

        Raises:
            DatoNoEncontrado, DatoCorrupto: si el `run.json` no existe o está dañado.
            ErrorAlmacen: si `estado` o los demás valores no son válidos.
        """
        run = self.leer_run(run_id)
        run.update(
            fin=_iso(ahora),
            estado=estado,
            resumen={"pasaron": pasaron, "fallaron": fallaron},
        )
        if tipos_prueba is not None:
            run["tipos_prueba"] = list(tipos_prueba)
        self.guardar_run(run)
        return run

    def leer_run(self, run_id: str) -> dict[str, Any]:
        """Lee el `run.json` de una corrida.

        Raises:
            DatoNoEncontrado: si la corrida no existe.
            DatoCorrupto: si el `run.json` está dañado o no tiene el formato esperado.
        """
        ruta = self.carpeta_run(run_id) / ARCHIVO_RUN
        run = leer_json_objeto(ruta)
        try:
            _validar_run(run)
        except ErrorAlmacen as exc:
            raise DatoCorrupto(f"{ruta}: {exc}") from exc
        if run["run_id"] != run_id:
            raise DatoCorrupto(f"{ruta}: el run_id no coincide con la carpeta.")
        return run

    def listar_runs(self) -> list[dict[str, Any]]:
        """Historial: los `run.json` en orden cronológico (el más antiguo primero).

        Las corridas sin `run.json` o con uno dañado se omiten; nunca lanza por eso.
        """
        if not self.carpeta_runs.is_dir():
            return []
        runs = []
        for carpeta in sorted(self.carpeta_runs.iterdir(), key=_nombre):
            if not carpeta.is_dir() or not PATRON_RUN_ID.match(carpeta.name):
                continue
            try:
                runs.append(self.leer_run(carpeta.name))
            except ErrorAlmacen:
                continue
        return runs

    # --- Specs ----------------------------------------------------------------------

    def guardar_spec(
        self,
        contrato: dict[str, Any],
        run_origen: str,
        archivo_prueba: str | None = None,
        estado: str = "vigente",
        ahora: datetime | None = None,
    ) -> dict[str, Any]:
        """Guarda la spec de un objetivo: el contrato del Planner y de dónde salió.

        La spec se identifica por módulo y objetivo (`id_de_spec`): volver a guardarla
        la reemplaza, de modo que hay una sola spec por función o endpoint.

        Args:
            contrato: contrato `planner_contract.v2` tal como lo produjo el Planner.
            run_origen: `run_id` de la corrida que la generó.
            archivo_prueba: nombre de su prueba aprobada en `tests/`, si ya la hay.
            estado: "vigente" u "obsoleta".
            ahora: momento de creación; por defecto, la hora local actual.

        Returns:
            El contenido de `specs/<id>.json`.

        Raises:
            ContratoInvalido: si `contrato` no cumple su schema (no se escribe nada).
            ErrorAlmacen: si algún otro campo no es válido.
            OSError: si no se puede escribir.
        """
        contracts.validar(contracts.PLANNER, contrato)
        spec = {
            "id": id_de_spec(contrato["modulo"], contrato["objetivo"]),
            "creado": _iso(ahora),
            "run_origen": run_origen,
            "estado": estado,
            "archivo_prueba": archivo_prueba,
            "contrato": contrato,
        }
        _validar_spec(spec)
        self.inicializar()
        escribir_json_atomico(self._ruta_spec(spec["id"]), spec)
        return spec

    def leer_spec(self, spec_id: str) -> dict[str, Any]:
        """Lee una spec por su id.

        Raises:
            DatoNoEncontrado: si no existe.
            DatoCorrupto: si está dañada o no tiene el formato esperado.
        """
        ruta = self._ruta_spec(spec_id)
        spec = leer_json_objeto(ruta)
        try:
            _validar_spec(spec)
            contracts.validar(contracts.PLANNER, spec["contrato"])
        except (ErrorAlmacen, contracts.ContratoInvalido) as exc:
            raise DatoCorrupto(f"{ruta}: {exc}") from exc
        return spec

    def listar_specs(self) -> list[dict[str, Any]]:
        """Todas las specs válidas, ordenadas por id. Las dañadas se omiten."""
        if not self.carpeta_specs.is_dir():
            return []
        specs = []
        for ruta in sorted(self.carpeta_specs.glob("*.json"), key=_nombre):
            try:
                specs.append(self.leer_spec(ruta.stem))
            except ErrorAlmacen:
                continue
        return specs

    def tiene_specs(self) -> bool:
        """Indica si hay al menos una spec válida (habilita el modo regresión)."""
        return bool(self.listar_specs())

    def _ruta_spec(self, spec_id: str) -> Path:
        if not isinstance(spec_id, str) or not PATRON_ID.match(spec_id):
            raise ErrorAlmacen(f"id de spec no válido: {spec_id!r}")
        return self.carpeta_specs / f"{spec_id}.json"

    # --- Pruebas aprobadas ----------------------------------------------------------

    def guardar_prueba_aprobada(self, nombre_archivo: str, codigo: str) -> Path:
        """Guarda en `tests/` una prueba que el Reviewer aprobó (la reemplaza si existía).

        Args:
            nombre_archivo: `test_*.py`, sin carpetas (ver `nombre_prueba`).
            codigo: código pytest de la prueba.

        Returns:
            Ruta del archivo escrito.

        Raises:
            ErrorAlmacen: si el nombre no es `test_*.py`.
            OSError: si no se puede escribir.
        """
        ruta = self._ruta_prueba(nombre_archivo)
        self.inicializar()
        escribir_texto_atomico(ruta, codigo)
        return ruta

    def leer_prueba_aprobada(self, nombre_archivo: str) -> str:
        """Devuelve el código de una prueba aprobada.

        Raises:
            DatoNoEncontrado: si no existe.
            DatoCorrupto: si no se puede leer.
        """
        ruta = self._ruta_prueba(nombre_archivo)
        try:
            return ruta.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise DatoNoEncontrado(f"No existe la prueba aprobada: {ruta}") from exc
        except (OSError, UnicodeDecodeError) as exc:
            raise DatoCorrupto(f"No se pudo leer {ruta}: {exc}") from exc

    def listar_pruebas_aprobadas(self) -> list[Path]:
        """Rutas de las pruebas aprobadas (`tests/test_*.py`), ordenadas por nombre."""
        if not self.carpeta_tests.is_dir():
            return []
        return sorted(
            (
                p
                for p in self.carpeta_tests.glob("test_*.py")
                if p.is_file() and PATRON_PRUEBA.match(p.name)
            ),
            key=_nombre,
        )

    def _ruta_prueba(self, nombre_archivo: str) -> Path:
        if not isinstance(nombre_archivo, str) or not PATRON_PRUEBA.match(
            nombre_archivo
        ):
            raise ErrorAlmacen(
                f"Nombre de prueba no válido: {nombre_archivo!r} (se espera test_*.py)."
            )
        return self.carpeta_tests / nombre_archivo


# --- Validación ------------------------------------------------------------------------


def _validar_run(run: dict[str, Any]) -> None:
    faltan = [c for c in CAMPOS_RUN if c not in run]
    if faltan:
        raise ErrorAlmacen(f"Al run le faltan campos: {', '.join(faltan)}")
    if not isinstance(run["run_id"], str) or not PATRON_RUN_ID.match(run["run_id"]):
        raise ErrorAlmacen(f"run_id no válido: {run['run_id']!r}")
    if run["estado"] not in ESTADOS_RUN:
        raise ErrorAlmacen(f"Estado de corrida no válido: {run['estado']!r}")
    tipos = run["tipos_prueba"]
    if not isinstance(tipos, list) or any(t not in TIPOS_PRUEBA for t in tipos):
        raise ErrorAlmacen(f"tipos_prueba no válido: {tipos!r}")
    if not isinstance(run["inicio"], str) or not (
        run["fin"] is None or isinstance(run["fin"], str)
    ):
        raise ErrorAlmacen("inicio y fin deben ser fechas ISO 8601.")
    if not (run["imagen_docker"] is None or isinstance(run["imagen_docker"], str)):
        raise ErrorAlmacen("imagen_docker debe ser texto o null.")
    resumen = run["resumen"]
    if resumen is not None and not (
        isinstance(resumen, dict)
        and all(isinstance(resumen.get(c), int) for c in ("pasaron", "fallaron"))
    ):
        raise ErrorAlmacen("resumen debe ser {pasaron, fallaron} o null.")


def _validar_spec(spec: dict[str, Any]) -> None:
    faltan = [c for c in CAMPOS_SPEC if c not in spec]
    if faltan:
        raise ErrorAlmacen(f"A la spec le faltan campos: {', '.join(faltan)}")
    if not isinstance(spec["id"], str) or not PATRON_ID.match(spec["id"]):
        raise ErrorAlmacen(f"id de spec no válido: {spec['id']!r}")
    if spec["estado"] not in ESTADOS_SPEC:
        raise ErrorAlmacen(f"Estado de spec no válido: {spec['estado']!r}")
    origen = spec["run_origen"]
    if not isinstance(origen, str) or not PATRON_RUN_ID.match(origen):
        raise ErrorAlmacen(f"run_origen no válido: {origen!r}")
    archivo = spec["archivo_prueba"]
    if archivo is not None and not (
        isinstance(archivo, str) and PATRON_PRUEBA.match(archivo)
    ):
        raise ErrorAlmacen(f"archivo_prueba no válido: {archivo!r}")
    if not isinstance(spec["contrato"], dict):
        raise ErrorAlmacen("contrato debe ser un objeto.")

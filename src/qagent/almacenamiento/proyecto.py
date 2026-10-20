"""Almacenamiento de QAgent dentro del proyecto del usuario: `.qagent/` (EN-07).

Estructura::

    <proyecto>/.qagent/
        .gitignore          ignora runs/ (specs y pruebas aprobadas sí se pueden versionar)
        runs/<run_id>/      una carpeta por corrida: run.json, y log.json y
                            results.json (EN-05, `qagent.storage`)
        specs/<id>.json     spec de cada prueba (contrato del Planner), para regresión
        specs/<modulo>.spec.json  plan completo y huella para reutilización (HU-24)
        tests/test_*.py     solo las pruebas aprobadas
        mutacion/<id>.json  último Mutation Score de una función crítica, con las huellas
                            de la función y de su prueba, para reutilizarlo (#70)

El historial son los `run.json` ordenados por `run_id` (empieza con la fecha), sin un
archivo de índice aparte. Es el único lugar que crea esta estructura. No depende de la
interfaz ni del orquestador.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from qagent import contracts
from qagent.almacenamiento.disco import (
    DatoCorrupto,
    DatoNoEncontrado,
    ErrorAlmacen,
    escribir_json_atomico,
    escribir_texto_atomico,
    leer_json_objeto,
)
from qagent.storage.registro import nuevo_run_id

CARPETA = ".qagent"
#: Nombre de la carpeta en versiones anteriores (cuando el producto se llamaba PyAgent).
CARPETA_ANTERIOR = ".pyagent"
CONTENIDO_GITIGNORE = (
    "# Generado por QAgent: las corridas no se versionan.\n"
    "# specs/ y tests/ (pruebas aprobadas) sí se pueden subir al repositorio.\n"
    "runs/\n"
)
ARCHIVO_RUN = "run.json"

# Estados de una corrida: "en_curso" hasta que termina; luego el estado final del
# orquestador ("fin" o "fallo_controlado"). Si la app se cierra a mitad, queda "en_curso".
ESTADOS_RUN = ("en_curso", "fin", "fallo_controlado")


def migrar_carpeta_anterior(raiz: str | Path) -> bool:
    """Renombra `<raiz>/.pyagent/` a `<raiz>/.qagent/` si solo existe la anterior.

    Conserva las corridas, specs y pruebas aprobadas de versiones previas. Si ya existe
    `.qagent/` no toca nada: nunca mezcla ni sobrescribe carpetas.

    Returns:
        True si se renombró la carpeta.

    Raises:
        OSError: si la carpeta anterior existe pero no se puede renombrar.
    """
    raiz = Path(raiz)
    anterior, nueva = raiz / CARPETA_ANTERIOR, raiz / CARPETA
    if not anterior.is_dir() or nueva.exists():
        return False
    anterior.rename(nueva)
    return True


# "vigente" se reutiliza en regresión; "obsoleta" cuando el código cambió (HU-24).
ESTADOS_SPEC = ("vigente", "obsoleta")
ACCIONES_SPEC_MODULO = ("generado", "reutilizado", "regenerado")
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
PATRON_HUELLA = re.compile(r"^[0-9a-f]{64}$")
#: Identificador de un perfil de corrida guardado con cada spec (#75), ej. "humo".
PATRON_PERFIL = re.compile(r"^[a-z][a-z_]*$")


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


def id_de_modulo(modulo: str) -> str:
    """Identificador seguro y estable de un módulo para su caché HU-24."""
    ruta = PurePosixPath(modulo)
    if ruta.is_absolute() or ".." in ruta.parts or ruta.suffix != ".py":
        raise ErrorAlmacen(f"Ruta de módulo no válida: {modulo!r}")
    partes = [
        re.sub(r"[^A-Za-z0-9_-]+", "_", parte) for parte in ruta.with_suffix("").parts
    ]
    identificador = "__".join(parte.strip("_") for parte in partes if parte.strip("_"))
    if not identificador or not PATRON_ID.match(identificador):
        raise ErrorAlmacen(f"Ruta de módulo no válida: {modulo!r}")
    # Los módulos sencillos conservan un nombre legible (`banco_mvp.py`), mientras
    # que rutas anidadas o nombres que requieren normalización reciben una huella.
    # Así `a/b.py` y `a__b.py` nunca terminan en el mismo archivo de caché.
    base_original = ruta.with_suffix("").as_posix()
    es_nombre_directo = (
        len(ruta.parts) == 1
        and re.fullmatch(r"[A-Za-z0-9_]+", base_original) is not None
    )
    if not es_nombre_directo:
        sufijo = hashlib.sha256(modulo.encode("utf-8")).hexdigest()[:12]
        identificador = f"{identificador}--{sufijo}"
    return identificador


def huella_de_prueba(codigo: str) -> str:
    """SHA-256 del código de una prueba aprobada (para la caché de mutación, #70)."""
    return hashlib.sha256(codigo.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def nombre_spec_modulo(modulo: str) -> str:
    """Nombre de `.qagent/specs/<modulo>.spec.json` sin colisiones por carpetas."""
    return f"{id_de_modulo(modulo)}.spec.json"


class AlmacenProyecto:
    """Acceso a `.qagent/` de un proyecto. Cada instancia lee del disco: no guarda caché.

    Atributos:
        raiz: carpeta del proyecto del usuario.
        carpeta: `<raiz>/.qagent`.
        carpeta_runs, carpeta_specs, carpeta_tests, carpeta_mutacion: subcarpetas de
            `carpeta`.
    """

    def __init__(self, ruta_proyecto: str | Path) -> None:
        """Prepara las rutas; no toca el disco hasta `inicializar()` o un `guardar_*`."""
        self.raiz = Path(ruta_proyecto)
        self.carpeta = self.raiz / CARPETA
        self.carpeta_runs = self.carpeta / "runs"
        self.carpeta_specs = self.carpeta / "specs"
        self.carpeta_tests = self.carpeta / "tests"
        self.carpeta_mutacion = self.carpeta / "mutacion"

    def existe(self) -> bool:
        """Indica si el proyecto ya tiene la carpeta `.qagent/`."""
        return self.carpeta.is_dir()

    def inicializar(self) -> None:
        """Crea `.qagent/`, sus subcarpetas y el `.gitignore` si faltan (idempotente).

        Nunca borra ni sobrescribe nada: un `.gitignore` editado por el usuario se respeta.

        Raises:
            OSError: si no se puede escribir en la carpeta del proyecto.
        """
        migrar_carpeta_anterior(self.raiz)
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
        datos = {c: run[c] for c in CAMPOS_RUN}
        if "specs" in run:
            datos["specs"] = run["specs"]
        if run.get("duracion_s") is not None:
            datos["duracion_s"] = run["duracion_s"]
        escribir_json_atomico(ruta, datos)
        return ruta

    def finalizar_run(
        self,
        run_id: str,
        estado: str,
        pasaron: int,
        fallaron: int,
        tipos_prueba: Iterable[str] | None = None,
        ahora: datetime | None = None,
        duracion_s: float | None = None,
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
        if duracion_s is not None:
            run["duracion_s"] = round(float(duracion_s), 3)
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
        huella_objetivo: str | None = None,
        perfil: str | None = None,
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
            perfil: perfil con que se creó el contrato (ej. "humo", #75).

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
        if huella_objetivo is not None:
            spec["huella_objetivo"] = huella_objetivo
        if perfil is not None:
            spec["perfil"] = perfil
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
            if ruta.name.endswith(".spec.json"):
                continue
            try:
                specs.append(self.leer_spec(ruta.stem))
            except ErrorAlmacen:
                continue
        return specs

    def tiene_specs(self) -> bool:
        """Indica si hay al menos una spec válida (habilita el modo regresión)."""
        return bool(self.listar_specs())

    def tiene_pruebas_aprobadas(self) -> bool:
        """True si hay una spec vigente enlazada a una prueba aprobada real."""
        return any(
            spec["estado"] == "vigente"
            and spec["archivo_prueba"] is not None
            and (self.carpeta_tests / spec["archivo_prueba"]).is_file()
            for spec in self.listar_specs()
        )

    # --- Mutation testing (#70) ----------------------------------------------------

    def guardar_mutacion(
        self,
        spec_id: str,
        huella_objetivo: str,
        huella_prueba: str,
        mutacion: dict[str, Any],
        run_id: str,
        ahora: datetime | None = None,
    ) -> dict[str, Any]:
        """Guarda el último Mutation Score de una función para reutilizarlo.

        Solo se guardan resultados con puntuación (estado "ok"): un tiempo agotado o un
        error se vuelve a intentar en la próxima corrida.

        Args:
            spec_id: id de la spec de la función (`id_de_spec`).
            huella_objetivo: huella AST de la función cuando se mutó.
            huella_prueba: `huella_de_prueba()` de la prueba usada contra los mutantes.
            mutacion: resultado de mutmut (forma `mutacion` de `run_log.schema.json`).
            run_id: corrida que lo calculó.

        Raises:
            ErrorAlmacen: si algún campo no es válido (no se escribe nada).
        """
        datos = {
            "version": "1",
            "id": spec_id,
            "huella_objetivo": huella_objetivo,
            "huella_prueba": huella_prueba,
            "run_id": run_id,
            "fecha": _iso(ahora),
            "mutacion": mutacion,
        }
        _validar_mutacion(datos)
        self.carpeta_mutacion.mkdir(parents=True, exist_ok=True)
        escribir_json_atomico(self._ruta_mutacion(spec_id), datos)
        return datos

    def mutacion_vigente(
        self, spec_id: str, huella_objetivo: str | None, huella_prueba: str | None
    ) -> dict[str, Any] | None:
        """Último Mutation Score guardado si la función y su prueba no cambiaron.

        Returns:
            El registro guardado (con `run_id` y `mutacion`), o None si no hay, está
            dañado o alguna de las dos huellas es distinta.
        """
        if not huella_objetivo or not huella_prueba:
            return None
        try:
            datos = leer_json_objeto(self._ruta_mutacion(spec_id))
            _validar_mutacion(datos)
        except ErrorAlmacen:
            return None
        if (datos["huella_objetivo"], datos["huella_prueba"]) != (
            huella_objetivo,
            huella_prueba,
        ):
            return None
        return datos

    def _ruta_mutacion(self, spec_id: str) -> Path:
        if not isinstance(spec_id, str) or not PATRON_ID.match(spec_id):
            raise ErrorAlmacen(f"id de spec no válido: {spec_id!r}")
        return self.carpeta_mutacion / f"{spec_id}.json"

    def _ruta_spec(self, spec_id: str) -> Path:
        if not isinstance(spec_id, str) or not PATRON_ID.match(spec_id):
            raise ErrorAlmacen(f"id de spec no válido: {spec_id!r}")
        return self.carpeta_specs / f"{spec_id}.json"

    # --- Planes por módulo (HU-24) -------------------------------------------------

    def guardar_plan_modulo(
        self,
        modulo: str,
        huella: str,
        contratos: list[dict[str, Any]],
        run_actual: str,
        accion: str,
        ahora: datetime | None = None,
        perfiles: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Guarda el plan completo de un módulo para reutilizarlo en otra corrida.

        En una reutilización conserva `creado` y `run_origen`; solo actualiza la
        última corrida y su acción. Si el módulo cambió, la nueva spec reemplaza la
        anterior y la acción queda como `regenerado`. `perfiles` dice con qué perfil
        se creó el contrato de cada objetivo (#75); los planes anteriores no lo traen.
        """
        previo: dict[str, Any] | None = None
        if accion == "reutilizado":
            try:
                previo = self.leer_plan_modulo(modulo)
            except ErrorAlmacen:
                previo = None
            if previo is None or previo["huella"] != huella:
                raise ErrorAlmacen(
                    "No se puede reutilizar una spec ausente o con otra huella."
                )
        plan = {
            "version": "1",
            "modulo": modulo,
            "huella": huella,
            "creado": previo["creado"] if previo else _iso(ahora),
            "run_origen": previo["run_origen"] if previo else run_actual,
            "estado": "vigente",
            "ultima_accion": accion,
            "ultima_corrida": run_actual,
            "contratos": contratos,
        }
        if perfiles:
            plan["perfiles"] = dict(perfiles)
        _validar_plan_modulo(plan)
        self.inicializar()
        escribir_json_atomico(self._ruta_plan_modulo(modulo), plan)
        return plan

    def leer_plan_modulo(self, modulo: str) -> dict[str, Any]:
        """Lee y valida la spec modular usada como caché del Planner."""
        ruta = self._ruta_plan_modulo(modulo)
        plan = leer_json_objeto(ruta)
        try:
            _validar_plan_modulo(plan)
        except (ErrorAlmacen, contracts.ContratoInvalido) as exc:
            raise DatoCorrupto(f"{ruta}: {exc}") from exc
        if plan["modulo"] != modulo:
            raise DatoCorrupto(f"{ruta}: el módulo no coincide con el archivo.")
        return plan

    def buscar_plan_vigente(self, modulo: str, huella: str) -> dict[str, Any] | None:
        """Devuelve la spec solo cuando sigue vigente y la huella coincide."""
        try:
            plan = self.leer_plan_modulo(modulo)
        except ErrorAlmacen:
            return None
        if plan["estado"] != "vigente" or plan["huella"] != huella:
            return None
        return plan

    def listar_planes_modulo(self) -> list[dict[str, Any]]:
        """Lista las specs modulares válidas, ordenadas por nombre de archivo."""
        if not self.carpeta_specs.is_dir():
            return []
        planes = []
        for ruta in sorted(self.carpeta_specs.glob("*.spec.json"), key=_nombre):
            try:
                dato = leer_json_objeto(ruta)
                _validar_plan_modulo(dato)
            except (ErrorAlmacen, contracts.ContratoInvalido):
                continue
            planes.append(dato)
        return planes

    def registrar_specs_run(
        self, run_id: str, registros: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Agrega al historial de una corrida cómo se obtuvo cada spec modular."""
        _validar_registros_specs(registros)
        run = self.leer_run(run_id)
        run["specs"] = registros
        self.guardar_run(run)
        return run

    def crear_zip_specs(self, modulo: str | None = None) -> tuple[str, bytes]:
        """Devuelve un ZIP con una spec modular o con todas las specs vigentes."""
        if modulo is None:
            rutas = sorted(self.carpeta_specs.glob("*.spec.json"), key=_nombre)
            nombre = f"specs_{self.raiz.name}.zip"
        else:
            ruta = self._ruta_plan_modulo(modulo)
            if not ruta.is_file():
                raise DatoNoEncontrado(f"No existe la spec del módulo: {modulo}")
            rutas = [ruta]
            nombre = f"{id_de_modulo(modulo)}.spec.zip"
        if not rutas:
            raise DatoNoEncontrado("El proyecto no tiene specs modulares guardadas.")

        salida = BytesIO()
        with ZipFile(salida, "w", ZIP_DEFLATED) as archivo:
            for ruta in rutas:
                archivo.write(ruta, arcname=ruta.name)
        return nombre, salida.getvalue()

    def _ruta_plan_modulo(self, modulo: str) -> Path:
        return self.carpeta_specs / nombre_spec_modulo(modulo)

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

    def crear_zip_pruebas(self) -> tuple[str, bytes]:
        """Devuelve un ZIP con todas las pruebas aprobadas guardadas del proyecto."""
        rutas = self.listar_pruebas_aprobadas()
        if not rutas:
            raise DatoNoEncontrado("El proyecto no tiene pruebas guardadas.")
        salida = BytesIO()
        with ZipFile(salida, "w", ZIP_DEFLATED) as archivo:
            for ruta in rutas:
                archivo.write(ruta, arcname=ruta.name)
        return f"pruebas_{self.raiz.name}.zip", salida.getvalue()

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
    if "specs" in run:
        _validar_registros_specs(run["specs"])
    duracion = run.get("duracion_s")
    if duracion is not None and (
        isinstance(duracion, bool)
        or not isinstance(duracion, (int, float))
        or duracion < 0
    ):
        raise ErrorAlmacen("duracion_s debe ser un número no negativo o null.")


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
    huella = spec.get("huella_objetivo")
    if huella is not None and not (
        isinstance(huella, str) and PATRON_HUELLA.fullmatch(huella)
    ):
        raise ErrorAlmacen("huella_objetivo debe ser SHA-256 hexadecimal o null.")
    if "perfil" in spec and not _es_perfil(spec["perfil"]):
        raise ErrorAlmacen(f"perfil de spec no válido: {spec['perfil']!r}")


def _es_perfil(valor: Any) -> bool:
    """Identificador de perfil (#75): minúsculas y guion bajo, ej. "humo"."""
    return isinstance(valor, str) and PATRON_PERFIL.fullmatch(valor) is not None


def _validar_mutacion(datos: dict[str, Any]) -> None:
    """Valida un registro de `mutacion/<id>.json` (#70)."""
    if not isinstance(datos.get("id"), str) or not PATRON_ID.match(datos["id"]):
        raise ErrorAlmacen(f"id de spec no válido: {datos.get('id')!r}")
    for campo in ("huella_objetivo", "huella_prueba"):
        valor = datos.get(campo)
        if not (isinstance(valor, str) and PATRON_HUELLA.fullmatch(valor)):
            raise ErrorAlmacen(f"{campo} debe ser SHA-256 hexadecimal.")
    run_id = datos.get("run_id")
    if not (isinstance(run_id, str) and PATRON_RUN_ID.match(run_id)):
        raise ErrorAlmacen(f"run_id no válido: {run_id!r}")
    mutacion = datos.get("mutacion")
    if not isinstance(mutacion, dict) or mutacion.get("estado") != "ok":
        raise ErrorAlmacen("Solo se guarda una mutación terminada (estado ok).")
    puntuacion = mutacion.get("puntuacion")
    if not isinstance(puntuacion, (int, float)) or isinstance(puntuacion, bool):
        raise ErrorAlmacen("La mutación guardada debe tener puntuación.")


def _validar_plan_modulo(plan: dict[str, Any]) -> None:
    campos = {
        "version",
        "modulo",
        "huella",
        "creado",
        "run_origen",
        "estado",
        "ultima_accion",
        "ultima_corrida",
        "contratos",
    }
    faltan = campos - plan.keys()
    if faltan:
        raise ErrorAlmacen(
            f"A la spec modular le faltan campos: {', '.join(sorted(faltan))}"
        )
    if plan["version"] != "1":
        raise ErrorAlmacen(f"Versión de spec modular no válida: {plan['version']!r}")
    id_de_modulo(plan["modulo"])
    if not isinstance(plan["huella"], str) or not PATRON_HUELLA.match(plan["huella"]):
        raise ErrorAlmacen("La huella de la spec modular no es un SHA-256 válido.")
    if plan["estado"] != "vigente":
        raise ErrorAlmacen(f"Estado de spec modular no válido: {plan['estado']!r}")
    if plan["ultima_accion"] not in ACCIONES_SPEC_MODULO:
        raise ErrorAlmacen(
            f"Acción de spec modular no válida: {plan['ultima_accion']!r}"
        )
    for campo in ("run_origen", "ultima_corrida"):
        valor = plan[campo]
        if not isinstance(valor, str) or not PATRON_RUN_ID.match(valor):
            raise ErrorAlmacen(f"{campo} no válido: {valor!r}")
    if not isinstance(plan["creado"], str):
        raise ErrorAlmacen("creado debe ser una fecha ISO 8601.")
    contratos = plan["contratos"]
    if not isinstance(contratos, list) or not contratos:
        raise ErrorAlmacen("contratos debe ser una lista no vacía.")
    perfiles = plan.get("perfiles", {})
    if not isinstance(perfiles, dict) or not all(
        isinstance(o, str) and _es_perfil(p) for o, p in perfiles.items()
    ):
        raise ErrorAlmacen("perfiles debe asociar cada objetivo con su perfil.")
    for contrato in contratos:
        contracts.validar(contracts.PLANNER, contrato)
        if contrato["modulo"] != plan["modulo"] or contrato["huella"] != plan["huella"]:
            raise ErrorAlmacen(
                "Un contrato no coincide con el módulo o la huella de la spec."
            )


def _validar_registros_specs(registros: Any) -> None:
    if not isinstance(registros, list):
        raise ErrorAlmacen("specs debe ser una lista.")
    for registro in registros:
        if not isinstance(registro, dict):
            raise ErrorAlmacen("Cada registro de spec debe ser un objeto.")
        if set(registro) != {"modulo", "huella", "run_origen", "estado"}:
            raise ErrorAlmacen("Registro de spec incompleto.")
        id_de_modulo(registro["modulo"])
        if not isinstance(registro["huella"], str) or not PATRON_HUELLA.match(
            registro["huella"]
        ):
            raise ErrorAlmacen("Huella inválida en el historial de specs.")
        if registro["estado"] not in ACCIONES_SPEC_MODULO:
            raise ErrorAlmacen("Estado inválido en el historial de specs.")
        origen = registro["run_origen"]
        if not isinstance(origen, str) or not PATRON_RUN_ID.match(origen):
            raise ErrorAlmacen("run_origen inválido en el historial de specs.")

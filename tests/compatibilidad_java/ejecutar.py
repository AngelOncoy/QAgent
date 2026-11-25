"""Ejecuta filas de la matriz Java en Docker y conserva su evidencia (#309).

- Externos: se descarga el commit fijado con `git fetch` (sin hooks ni credenciales),
  se comprueba el SHA y la licencia, se copia a una carpeta de trabajo, se aplica el
  defecto sembrado si la fila lo declara y se usa la corrida productiva
  (`ejecutar_corrida`) con la IA grabada de `proveedor.py`. Maven, JUnit y el código
  del proyecto solo corren en Docker; la red se usa únicamente al preparar la imagen.
- Fixtures: se ejecuta su prueba `docker` existente con pytest y se lee su JUnit.

Cada fila deja en `<salida>/<id>/` su `fila.json`, los archivos de la corrida
(`results.json`, `detalle.json`, `construccion.log`, `entorno.log`, pruebas
generadas…) o el JUnit/log de pytest, todo con los secretos saneados, también
cuando la fila no aprueba.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from tests.compatibilidad_java.matriz import (
    FALLO_TECNICO,
    MARCAS_LICENCIA,
    NO_EJECUTADO,
    RAIZ_REPO,
    Fila,
    comparar,
    resultado_de_pytest,
)

#: Extensiones de texto que se sanean antes de guardarlas como evidencia.
_TEXTO = {".json", ".log", ".txt", ".xml", ".java", ".md", ".properties"}
_LIMITE_TEXTO = 2_000_000


class ErrorTecnico(RuntimeError):
    """Fallo de infraestructura: descarga, commit, licencia, parche o Docker."""

    def __init__(self, mensaje: str, log: str | None = None) -> None:
        super().__init__(mensaje)
        self.log = log


def _sanear(texto: str) -> str:
    from qagent.storage.diagnostico_entorno import sanear_diagnostico
    from qagent.storage.exportar_informe import sanitizar_secretos

    if len(texto) <= 524_288:
        return sanear_diagnostico(texto)
    return sanitizar_secretos(texto[:_LIMITE_TEXTO])


def guardar_texto(destino: Path, texto: str) -> None:
    """Escribe evidencia de texto con los secretos saneados."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(_sanear(texto), encoding="utf-8")


def copiar_evidencia(origen: Path, destino: Path) -> list[str]:
    """Copia una carpeta saneando los archivos de texto; devuelve lo copiado."""
    copiados = []
    if not origen.is_dir():
        return copiados
    for archivo in sorted(origen.rglob("*")):
        if not archivo.is_file() or archivo.is_symlink():
            continue
        relativo = archivo.relative_to(origen)
        objetivo = destino / relativo
        objetivo.parent.mkdir(parents=True, exist_ok=True)
        if archivo.suffix.lower() in _TEXTO:
            guardar_texto(
                objetivo, archivo.read_text(encoding="utf-8", errors="replace")
            )
        else:
            shutil.copy2(archivo, objetivo)
        copiados.append(relativo.as_posix())
    return copiados


def _git(*argumentos: str, cwd: Path) -> str:
    """Git sin hooks, sin credenciales interactivas y sin configuración global."""
    entorno = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    proceso = subprocess.run(
        ["git", "-c", "core.hooksPath=" + os.devnull, *argumentos],
        cwd=cwd,
        env=entorno,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    if proceso.returncode != 0:
        raise ErrorTecnico(
            f"git {argumentos[0]} falló ({proceso.returncode})",
            proceso.stdout + proceso.stderr,
        )
    return proceso.stdout.strip()


def obtener_fuente(fila: Fila, cache: Path) -> Path:
    """Descarga solo el commit fijado y comprueba SHA y licencia."""
    nombre = fila.url.rstrip("/").rsplit("/", 1)[-1]
    destino = cache / f"{nombre}-{fila.commit[:12]}"
    if not (destino / ".git").is_dir():
        if destino.exists():
            shutil.rmtree(destino)
        destino.mkdir(parents=True)
        _git("init", "-q", cwd=destino)
        _git("remote", "add", "origin", fila.url + ".git", cwd=destino)
        _git("fetch", "-q", "--depth", "1", "origin", fila.commit, cwd=destino)
        _git(
            "-c",
            "advice.detachedHead=false",
            "checkout",
            "-q",
            "FETCH_HEAD",
            cwd=destino,
        )
    actual = _git("rev-parse", "HEAD", cwd=destino)
    if actual != fila.commit:
        raise ErrorTecnico(f"el checkout está en {actual}, no en {fila.commit}")
    licencia = destino / fila.archivo_licencia
    if not licencia.is_file():
        raise ErrorTecnico(f"falta el archivo de licencia {fila.archivo_licencia}")
    if MARCAS_LICENCIA[fila.licencia] not in licencia.read_text(
        encoding="utf-8", errors="replace"
    ):
        raise ErrorTecnico(f"{fila.archivo_licencia} no corresponde a {fila.licencia}")
    return destino


def preparar_copia(fila: Fila, checkout: Path, trabajo: Path) -> Path:
    """Copia el subdirectorio declarado y aplica el defecto sembrado, si lo hay."""
    origen = checkout / fila.subdirectorio if fila.subdirectorio else checkout
    if not origen.is_dir():
        raise ErrorTecnico(f"no existe el subdirectorio {fila.subdirectorio}")
    proyecto = trabajo / fila.id
    if proyecto.exists():
        shutil.rmtree(proyecto)
    shutil.copytree(origen, proyecto, ignore=shutil.ignore_patterns(".git"))
    for parche in fila.parches:
        archivo = proyecto / parche["archivo"]
        texto = archivo.read_text(encoding="utf-8")
        if texto.count(parche["buscar"]) != 1:
            raise ErrorTecnico(
                f"el parche de {parche['archivo']} no coincide exactamente una vez"
            )
        archivo.write_text(
            texto.replace(parche["buscar"], parche["reemplazar"]), encoding="utf-8"
        )
    return proyecto


def seleccion_de(fila: Fila) -> list[dict[str, Any]]:
    """Selección de la corrida agrupada por módulo, como la envía la interfaz."""
    por_modulo: dict[str, dict[str, Any]] = {}
    for objetivo in fila.objetivos:
        modulo = por_modulo.setdefault(
            objetivo.modulo,
            {"ruta": objetivo.modulo, "funciones": [], "endpoints": [], "criticas": []},
        )
        clave = "endpoints" if objetivo.tipo == "endpoint" else "funciones"
        modulo[clave].append(objetivo.objetivo)
    return list(por_modulo.values())


def objetivos_analizados(proyecto: Path) -> dict[str, set[str]]:
    """Objetivos que el análisis estático encuentra en cada módulo."""
    from qagent.lenguajes import JavaAdapter

    estructura = JavaAdapter().analizar(proyecto)
    return {
        m["ruta"]: {f["nombre"] for f in m.get("funciones", [])}
        | {e["objetivo"] for e in m.get("endpoints", [])}
        for m in estructura.get("modulos", [])
    }


def observar(resumen: Any, fila: Fila) -> dict[str, dict[str, Any]]:
    """Estado observado de cada objetivo a partir del resumen y de results.json."""
    construccion = resumen.construccion or {}
    if construccion and construccion.get("estado") != "aprobado":
        motivo = " ".join(
            str(construccion.get(k))
            for k in ("categoria", "motivo", "mensaje")
            if construccion.get(k)
        )
        return {
            o.objetivo: {"estado": "construccion_bloqueada", "motivo": motivo}
            for o in fila.objetivos
        }
    carpeta = Path(resumen.carpeta) if resumen.carpeta else None
    if carpeta is None or not (carpeta / "results.json").is_file():
        return {
            o.objetivo: {"estado": "sin_veredicto", "motivo": resumen.motivo}
            for o in fila.objetivos
        }
    from qagent.storage.vista_ejecucion import estado_de

    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    detalle_ruta = carpeta / "detalle.json"
    detalle = (
        json.loads(detalle_ruta.read_text(encoding="utf-8"))
        if detalle_ruta.is_file()
        else {}
    )
    inferidos = {
        f["funcion"]
        for f in detalle.get("funciones", [])
        if any(
            c.get("origen") == "inferido"
            for c in (f.get("contrato") or {}).get("casos", [])
        )
    }
    observados: dict[str, dict[str, Any]] = {}
    for objetivo in results.get("objetivos", []):
        estado = estado_de(objetivo)
        if estado == "bug_detectado" and objetivo["funcion"] in inferidos:
            estado = "hallazgo_inferido"
        observados[objetivo["funcion"]] = {
            "estado": estado,
            "decision": objetivo.get("decision"),
            "inferido": objetivo["funcion"] in inferidos,
            "cobertura_lineas": (objetivo.get("metricas") or {}).get(
                "cobertura_lineas"
            ),
        }
    for omitido in results.get("omitidos", []):
        observados.setdefault(
            omitido.get("objetivo"),
            {"estado": "omitido", "motivo": omitido.get("motivo")},
        )
    return observados


def _limites(config: Any) -> dict[str, Any]:
    limites = config.limites_sandbox("java")
    return {
        "memoria": limites.memoria,
        "timeout_s": limites.timeout_s,
        "cpus": getattr(limites, "cpus", None),
    }


def ejecutar_externo(
    fila: Fila,
    *,
    cache: Path,
    trabajo: Path,
    salida: Path,
    cliente: Any,
    avanzar: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Ejecuta una fila externa y devuelve su registro, sin lanzar excepciones."""
    from qagent.almacenamiento import AlmacenProyecto
    from qagent.config import cargar_configuracion
    from qagent.orchestrator.corrida import ejecutar_corrida
    from qagent.sandbox.imagen import preparar_imagen
    from qagent.sandbox.modelos import IMAGEN_JAVA
    from tests.compatibilidad_java.proveedor import ProveedorMatriz

    carpeta = salida / fila.id
    registro = _registro_base(fila)
    etapas: dict[str, float] = {}
    inicio = time.monotonic()
    proyecto: Path | None = None
    resumen = None
    try:
        t = time.monotonic()
        checkout = obtener_fuente(fila, cache)
        proyecto = preparar_copia(fila, checkout, trabajo)
        etapas["descarga_s"] = round(time.monotonic() - t, 2)

        t = time.monotonic()
        encontrados = objetivos_analizados(proyecto)
        registro["analisis"] = {
            o.objetivo: o.objetivo in encontrados.get(o.modulo, set())
            for o in fila.objetivos
        }
        etapas["analisis_s"] = round(time.monotonic() - t, 2)

        t = time.monotonic()
        try:
            imagen = preparar_imagen(
                proyecto, cliente, avanzar=avanzar, imagen=IMAGEN_JAVA
            )
        except Exception as error:
            raise ErrorTecnico(
                f"preparación de la imagen: {error}", getattr(error, "log", None)
            ) from error
        etapas["imagen_s"] = round(time.monotonic() - t, 2)
        registro["imagen"] = {
            "etiqueta": imagen,
            "id": cliente.images.get(imagen).id,
        }

        AlmacenProyecto(proyecto).inicializar()
        config = cargar_configuracion(simulado=True).config
        registro["limites_sandbox"] = _limites(config)
        proveedor = ProveedorMatriz(fila, proyecto)
        t = time.monotonic()
        with mock.patch(
            "qagent.orchestrator.corrida.crear_cliente",
            lambda *a, **k: proveedor,
        ):
            resumen = ejecutar_corrida(
                proyecto,
                fila.perfil,
                config,
                None,
                simulado=True,
                seleccion=seleccion_de(fila),
                preparar_imagen=lambda _: imagen,
                inferir=True if fila.inferir else None,
            )
        etapas["corrida_s"] = round(time.monotonic() - t, 2)
        registro["corrida"] = {
            "estado": resumen.estado,
            "motivo": resumen.motivo,
            "aceptadas": resumen.aceptadas,
            "bugs_detectados": resumen.bugs_detectados,
            "objetivos_omitidos": resumen.objetivos_omitidos,
            "sin_veredicto": resumen.sin_veredicto,
            "estancadas": resumen.estancadas,
            "tokens": resumen.tokens,
            "construccion": resumen.construccion,
            "llamadas_ia": proveedor.llamadas,
        }
        if resumen.tokens:
            raise ErrorTecnico("la corrida consumió tokens: debía usar IA grabada")
        registro["observados"] = observar(resumen, fila)
        resultado, diferencias = comparar(fila, registro["observados"])
        registro["resultado"], registro["diferencias"] = resultado, diferencias
    except Exception as error:  # noqa: BLE001 - toda fila termina con un registro
        registro["resultado"] = FALLO_TECNICO
        registro["diferencias"] = [str(error)]
        guardar_texto(carpeta / "error.log", traceback.format_exc())
        log = getattr(error, "log", None)
        if log:
            guardar_texto(carpeta / "tecnico.log", log)
    finally:
        registro["etapas"] = etapas
        registro["duracion_s"] = round(time.monotonic() - inicio, 2)
        if resumen is not None and resumen.carpeta:
            registro["evidencia"] = copiar_evidencia(
                Path(resumen.carpeta), carpeta / "corrida"
            )
        _escribir_fila(carpeta, registro)
    return registro


def ejecutar_fixture(
    fila: Fila,
    *,
    salida: Path,
    cliente: Any,
    avanzar: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Ejecuta la prueba `docker` de un fixture y clasifica su JUnit."""
    from qagent.sandbox.imagen import preparar_imagen
    from qagent.sandbox.modelos import IMAGEN_JAVA

    carpeta = salida / fila.id
    carpeta.mkdir(parents=True, exist_ok=True)
    registro = _registro_base(fila)
    inicio = time.monotonic()
    try:
        ruta = RAIZ_REPO / fila.ruta
        if ruta.is_dir() and (ruta / "pom.xml").is_file():
            # Las pruebas del banco se omiten sin su imagen derivada: se prepara antes
            # para que un `skipped` no oculte la falta de ejecución.
            preparar_imagen(ruta, cliente, avanzar=avanzar, imagen=IMAGEN_JAVA)
        junit = carpeta / "junit.xml"
        comando = [
            sys.executable,
            "-m",
            "pytest",
            fila.prueba,
            "--docker",
            "--conservar-imagenes",
            "-q",
            "-rs",
            "-s",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
        ]
        entorno = {**os.environ, "QAGENT_FAKE_LLM": "1"}
        entorno.pop("PYAGENT_FAKE_LLM", None)
        proceso = subprocess.run(
            comando,
            cwd=RAIZ_REPO,
            env=entorno,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
            check=False,
        )
        guardar_texto(carpeta / "pytest.log", proceso.stdout + proceso.stderr)
        registro["comando"] = " ".join(comando[1:])
        registro["codigo_pytest"] = proceso.returncode
        totales = totales_junit(junit) if junit.is_file() else {}
        if junit.is_file():
            guardar_texto(junit, junit.read_text(encoding="utf-8", errors="replace"))
        registro["pytest"] = totales
        registro["resultado"], registro["diferencias"] = resultado_de_pytest(totales)
    except Exception as error:  # noqa: BLE001
        registro["resultado"] = FALLO_TECNICO
        registro["diferencias"] = [str(error)]
        guardar_texto(carpeta / "error.log", traceback.format_exc())
    registro["duracion_s"] = round(time.monotonic() - inicio, 2)
    _escribir_fila(carpeta, registro)
    return registro


def totales_junit(ruta: Path) -> dict[str, int]:
    """Totales de un JUnit XML de pytest (una o varias testsuite)."""
    raiz = ET.parse(ruta).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else raiz.findall("testsuite")
    totales = {"total": 0, "fallos": 0, "errores": 0, "omitidas": 0}
    for suite in suites:
        totales["total"] += int(suite.get("tests", 0))
        totales["fallos"] += int(suite.get("failures", 0))
        totales["errores"] += int(suite.get("errors", 0))
        totales["omitidas"] += int(suite.get("skipped", 0))
    return totales


def no_ejecutada(fila: Fila, motivo: str) -> dict[str, Any]:
    """Registro de una fila que no se llegó a ejecutar (nunca cuenta como éxito)."""
    return {**_registro_base(fila), "resultado": NO_EJECUTADO, "diferencias": [motivo]}


def _registro_base(fila: Fila) -> dict[str, Any]:
    return {
        "id": fila.id,
        "tipo": fila.tipo,
        "nivel": fila.nivel,
        "soporte": fila.soporte,
        "configuraciones": list(fila.configuraciones),
        "descripcion": fila.descripcion,
        "url": fila.url,
        "licencia": fila.licencia,
        "commit": fila.commit,
        "subdirectorio": fila.subdirectorio or None,
        "defecto_sembrado": fila.defecto_sembrado,
        "motivo_no_admitido": fila.motivo_no_admitido,
        "prueba": fila.prueba,
        "esperados": {
            o.objetivo: {"estado": o.esperado, "motivo": o.motivo}
            for o in fila.objetivos
        },
    }


def _escribir_fila(carpeta: Path, registro: dict[str, Any]) -> None:
    guardar_texto(
        carpeta / "fila.json",
        json.dumps(registro, ensure_ascii=False, indent=2, default=str),
    )


def entorno_de_ejecucion(cliente: Any) -> dict[str, Any]:
    """Versiones que hacen reproducible el resultado: QAgent, Python, Docker, JDK, Maven."""
    import qagent
    from qagent.sandbox.modelos import IMAGEN_JAVA

    entorno: dict[str, Any] = {
        "qagent": qagent.__version__,
        "python": platform.python_version(),
        "sistema": platform.platform(),
        "fecha_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        entorno["commit_repositorio"] = _git("rev-parse", "HEAD", cwd=RAIZ_REPO)
        entorno["cambios_sin_commit"] = bool(
            _git("status", "--porcelain", cwd=RAIZ_REPO)
        )
    except ErrorTecnico:
        entorno["commit_repositorio"] = None
    try:
        entorno["docker"] = cliente.version().get("Version")
        imagen = cliente.images.get(IMAGEN_JAVA)
        entorno["imagen_java"] = {"etiqueta": IMAGEN_JAVA, "id": imagen.id}
        # Solo se ejecutan las herramientas de la imagen, sin red ni proyecto.
        salida = cliente.containers.run(
            IMAGEN_JAVA,
            ["sh", "-c", "java -version 2>&1; mvn -v 2>&1 | head -n 1"],
            network_mode="none",
            remove=True,
        )
        entorno["herramientas"] = salida.decode("utf-8", errors="replace").strip()
    except Exception as error:  # noqa: BLE001
        entorno["docker_error"] = str(error)
    return entorno

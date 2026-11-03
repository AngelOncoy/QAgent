"""Ejecución de verificaciones arquitectónicas en el sandbox autorizado."""

from __future__ import annotations

import itertools
import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.almacenamiento.disco import escribir_json_atomico
from qagent.almacenamiento.proyecto import AlmacenProyecto
from qagent.arquitectura.modelo import reglas_ejecutables, resultado_no_ejecutado
from qagent.lenguajes import REGISTRO
from qagent.lenguajes.base import NoImplementado, PlanArquitectura
from qagent.sandbox.ejecucion import ejecutar_en_sandbox
from qagent.sandbox.modelos import ErrorSandbox, LimitesSandbox, ResultadoSandbox

ARCHIVO_RESULTADO_ARQUITECTURA = "architecture.json"


def verificar_arquitectura(
    ruta_proyecto: str | Path,
    *,
    limites: LimitesSandbox | None = None,
    cliente: Any = None,
) -> dict[str, Any]:
    """Verifica las reglas del proyecto sin LLM y persiste un resultado consultable."""
    raiz = Path(ruta_proyecto).resolve()
    almacen = AlmacenProyecto(raiz)
    documento = almacen.leer_reglas_arquitectura()
    lenguaje = REGISTRO.lenguaje_principal(raiz)
    if lenguaje is None:
        raise ValueError("No se detectó un lenguaje soportado en el proyecto.")
    adaptador = REGISTRO.adaptador_para(lenguaje)
    entorno = adaptador.entorno_sandbox()
    run = almacen.crear_run(["arquitectura"], entorno.imagen)
    inicio = time.monotonic()
    ejecutables = reglas_ejecutables(documento)
    resultados: list[dict[str, Any]] = []
    try:
        planes = adaptador.traducir_reglas_arquitectura(ejecutables, raiz)
        for plan in planes:
            resultados.append(
                _ejecutar_plan(plan, lenguaje, entorno.imagen, raiz, limites, cliente)
            )
    except (NoImplementado, ValueError, ErrorSandbox) as error:
        resultados.extend(
            _sin_veredicto(r, _herramienta(lenguaje), str(error)) for r in ejecutables
        )
    ejecutados = {r["id"] for r in resultados}
    resultados.extend(
        resultado_no_ejecutado(regla, _herramienta(lenguaje))
        for regla in documento["reglas"]
        if regla["id"] not in ejecutados
    )
    estado = _estado_global(resultados)
    duracion = round(time.monotonic() - inicio, 3)
    dato = {
        "version": "1",
        "run_id": run["run_id"],
        "lenguaje": lenguaje,
        "estado": estado,
        "duracion_s": duracion,
        "reglas": resultados,
    }
    contracts.validar_versionado(contracts.FAMILIA_ARCHITECTURE_RESULT, dato)
    carpeta = almacen.carpeta_run(run["run_id"])
    escribir_json_atomico(carpeta / ARCHIVO_RESULTADO_ARQUITECTURA, dato)
    # `results.json` mantiene la corrida visible en el Historial. El lector específico
    # de arquitectura usa architecture.json y no la confunde con resultados Reviewer.
    escribir_json_atomico(carpeta / "results.json", dato)
    cumple = sum(r["estado"] == "cumple" for r in resultados)
    no_cumple = sum(r["estado"] in {"incumple", "sin_veredicto"} for r in resultados)
    almacen.finalizar_run(
        run["run_id"],
        "fin" if estado != "sin_veredicto" else "fallo_controlado",
        cumple,
        no_cumple,
        tipos_prueba=["arquitectura"],
        duracion_s=duracion,
        total_seleccionados=len(resultados),
        total_procesados=len(resultados),
        tipo_terminacion="arquitectura",
    )
    return dato


def leer_resultado_arquitectura(
    ruta_proyecto: str | Path, run_id: str
) -> dict[str, Any]:
    """Lee y valida un resultado de arquitectura por su Run ID."""
    almacen = AlmacenProyecto(ruta_proyecto)
    ruta = almacen.carpeta_run(run_id) / ARCHIVO_RESULTADO_ARQUITECTURA
    try:
        dato = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"No se pudo leer el resultado de arquitectura: {error}"
        ) from error
    return contracts.validar_versionado(contracts.FAMILIA_ARCHITECTURE_RESULT, dato)


def _ejecutar_plan(
    plan: PlanArquitectura,
    lenguaje: str,
    imagen: str,
    raiz: Path,
    limites: LimitesSandbox | None,
    cliente: Any,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="qagent-arquitectura-") as temporal:
        carpeta = Path(temporal)
        for nombre, contenido in plan.archivos.items():
            destino = carpeta / nombre
            destino.write_text(contenido, encoding="utf-8", newline="\n")
            if nombre.endswith(".sh"):
                destino.chmod(0o755)
        opciones: dict[str, Any] = {"cliente": cliente}
        if limites is not None:
            opciones["limites"] = limites
        try:
            resultado = ejecutar_en_sandbox(
                imagen, plan.comando, raiz, carpeta, **opciones
            )
        except ErrorSandbox as error:
            return _sin_veredicto(plan.regla, plan.herramienta, str(error))
    return _interpretar(plan, lenguaje, raiz, resultado)


def _interpretar(
    plan: PlanArquitectura,
    lenguaje: str,
    raiz: Path,
    resultado: ResultadoSandbox,
) -> dict[str, Any]:
    if resultado.timed_out:
        return _sin_veredicto(
            plan.regla, plan.herramienta, "La herramienta excedió el tiempo límite."
        )
    if resultado.oom_killed:
        return _sin_veredicto(
            plan.regla,
            plan.herramienta,
            "La herramienta excedió la memoria disponible.",
        )
    if lenguaje in {"javascript", "typescript"}:
        return _interpretar_node(plan, raiz, resultado)
    if lenguaje == "java":
        return _interpretar_java(plan, raiz, resultado)
    return _interpretar_python(plan, raiz, resultado)


def _base(
    plan: PlanArquitectura,
    estado: str,
    hallazgos: list[dict[str, Any]],
    motivo: str | None = None,
) -> dict[str, Any]:
    regla = plan.regla
    return {
        "id": regla["id"],
        "nombre": regla["nombre"],
        "tipo": regla["tipo"],
        "origen": regla["origen"],
        "estado": estado,
        "herramienta": plan.herramienta,
        "hallazgos": hallazgos,
        "motivo_sin_veredicto": motivo,
    }


def _interpretar_python(
    plan: PlanArquitectura, raiz: Path, r: ResultadoSandbox
) -> dict[str, Any]:
    if r.exit_code == 0:
        return _base(plan, "cumple", [])
    if r.exit_code != 1:
        return _sin_veredicto(plan.regla, plan.herramienta, _error_herramienta(r))
    salida = f"{r.stdout}\n{r.stderr}".lower()
    if "syntax error in " in salida:
        return _sin_veredicto(
            plan.regla,
            plan.herramienta,
            "import-linter no pudo analizar el proyecto por un error de sintaxis.",
        )
    pares = re.findall(r"(?m)^\s*-?\s*([.\w]+)\s+->\s+([.\w]+)", r.stdout)
    if not pares and plan.regla["tipo"] == "dependencia_prohibida":
        pares = [(plan.regla["desde"], plan.regla["hacia"])]
    hallazgos = [_hallazgo(raiz, "python", a, b) for a, b in pares]
    if not hallazgos:
        hallazgos = [_hallazgo(raiz, "python", "ciclo", "ciclo")]
    return _base(plan, "incumple", hallazgos)


def _interpretar_node(
    plan: PlanArquitectura, raiz: Path, r: ResultadoSandbox
) -> dict[str, Any]:
    try:
        dato = json.loads(r.stdout)
        violaciones = dato["summary"]["violations"]
    except (ValueError, KeyError, TypeError):
        return _sin_veredicto(
            plan.regla,
            plan.herramienta,
            "dependency-cruiser devolvió un resultado ilegible.",
        )
    problemas_entorno = (dato.get("summary", {}).get("environment") or {}).get(
        "issues", []
    )
    if problemas_entorno:
        detalle = "; ".join(
            str(p.get("description") or p.get("name") or "entorno incompleto")
            for p in problemas_entorno
            if isinstance(p, dict)
        )
        return _sin_veredicto(plan.regla, plan.herramienta, detalle)
    errores_resolucion = [
        d
        for m in dato.get("modules", [])
        for d in m.get("dependencies", [])
        if d.get("couldNotResolve")
    ]
    if errores_resolucion:
        return _sin_veredicto(
            plan.regla,
            plan.herramienta,
            "No se pudieron resolver todas las dependencias internas.",
        )
    if not violaciones:
        return _base(plan, "cumple", [])
    hallazgos = [
        _hallazgo(
            raiz, "node", str(v.get("from", "?")), str(v.get("to", "?")), v.get("cycle")
        )
        for v in violaciones
    ]
    return _base(plan, "incumple", hallazgos)


def _interpretar_java(
    plan: PlanArquitectura, raiz: Path, r: ResultadoSandbox
) -> dict[str, Any]:
    if "QAGENT_STATUS\tcumple" in r.stdout and r.exit_code == 0:
        return _base(plan, "cumple", [])
    if "QAGENT_STATUS\tincumple" not in r.stdout:
        return _sin_veredicto(plan.regla, plan.herramienta, _error_herramienta(r))
    desde = plan.regla.get("desde", "ciclo")
    hacia = plan.regla.get("hacia", "ciclo")
    if plan.regla["tipo"] == "ciclos_importacion":
        resumen_ciclo = r.stdout.split("Dependencies of Slice", 1)[0]
        cadena = re.findall(r"Slice\s+([A-Za-z0-9_$.-]+)", resumen_ciclo)
        pares = list(itertools.pairwise(cadena))
        hallazgos = [
            _hallazgo(raiz, "java", origen, destino, cadena)
            for origen, destino in pares
        ]
    else:
        hallazgos = [_hallazgo(raiz, "java", desde, hacia)]
    if not hallazgos or all(h["archivo"] is None for h in hallazgos):
        ubicaciones = re.findall(r"([A-Za-z0-9_$-]+\.java):(\d+)", r.stdout)
        if ubicaciones:
            hallazgos = [
                {
                    "desde": desde,
                    "hacia": hacia,
                    "archivo": archivo,
                    "linea": int(linea) if int(linea) > 0 else None,
                }
                for archivo, linea in dict.fromkeys(ubicaciones)
            ]
        elif not hallazgos:
            hallazgos = [
                {"desde": desde, "hacia": hacia, "archivo": None, "linea": None}
            ]
    return _base(plan, "incumple", hallazgos)


def _hallazgo(
    raiz: Path, lenguaje: str, desde: str, hacia: str, cadena: Any = None
) -> dict[str, Any]:
    archivo, linea = _localizar_importacion(raiz, lenguaje, desde, hacia)
    dato: dict[str, Any] = {
        "desde": desde,
        "hacia": hacia,
        "archivo": archivo,
        "linea": linea,
    }
    if isinstance(cadena, list) and all(isinstance(x, str) for x in cadena):
        dato["cadena"] = cadena
    return dato


def _localizar_importacion(
    raiz: Path, lenguaje: str, desde: str, hacia: str
) -> tuple[str | None, int | None]:
    extensiones = {
        "python": (".py",),
        "node": (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts"),
        "java": (".java",),
    }[lenguaje]
    pista_origen = desde.strip(".").split(".")[-1].split("/")[-1]
    pistas_destino = {
        hacia.strip(".").split(".")[-1].split("/")[-1],
        hacia.rsplit("/", 1)[-1].split(".")[0],
    }
    for archivo in sorted(raiz.rglob("*")):
        if (
            not archivo.is_file()
            or archivo.suffix.lower() not in extensiones
            or archivo.is_symlink()
        ):
            continue
        relativa = archivo.relative_to(raiz).as_posix()
        if (
            pista_origen not in relativa
            and pista_origen not in archivo.stem
            and pista_origen not in {"ciclo", "?"}
        ):
            continue
        try:
            lineas = archivo.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError):
            continue
        for numero, texto in enumerate(lineas, 1):
            if any(p and p in texto for p in pistas_destino) and re.search(
                r"\b(import|from|require)\b", texto
            ):
                return relativa, numero
    return None, None


def _sin_veredicto(
    regla: dict[str, Any], herramienta: str, motivo: str
) -> dict[str, Any]:
    return {
        "id": regla["id"],
        "nombre": regla["nombre"],
        "tipo": regla["tipo"],
        "origen": regla["origen"],
        "estado": "sin_veredicto",
        "herramienta": herramienta,
        "hallazgos": [],
        "motivo_sin_veredicto": motivo[:1000],
    }


def _error_herramienta(resultado: ResultadoSandbox) -> str:
    texto = (resultado.stderr or resultado.stdout or "sin detalle").strip()
    return f"La herramienta terminó con código {resultado.exit_code}: {texto[:800]}"


def _estado_global(resultados: list[dict[str, Any]]) -> str:
    estados = {r["estado"] for r in resultados}
    if "incumple" in estados:
        return "incumple"
    if "sin_veredicto" in estados:
        return "sin_veredicto"
    return "cumple"


def _herramienta(lenguaje: str) -> str:
    return {
        "python": "import-linter 2.15",
        "javascript": "dependency-cruiser 18.6.0",
        "typescript": "dependency-cruiser 18.6.0",
        "java": "ArchUnit 1.5.1",
    }[lenguaje]

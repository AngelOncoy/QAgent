"""Reejecucion sin IA de pruebas aprobadas (HU-25), con mutación opcional (#70)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.llm.tracker import TokenTracker
from qagent.orchestrator.estados import Estado
from qagent.orchestrator.eventos import Evento
from qagent.orchestrator.mutacion import mutar_modulo
from qagent.orchestrator.orquestador import ResultadoCorrida, ResultadoObjetivo
from qagent.proyectos.proyecto_local import detectar_rama
from qagent.sandbox import clasificar_resultado, ejecutar_pruebas
from qagent.storage import escribir_corrida
from qagent.storage.registro import PERFIL_REGRESION_PROFUNDA


def huellas_de_objetivos(raiz: str | Path) -> dict[tuple[str, str], str]:
    """Calcula huellas AST por funcion/endpoint sin importar codigo del usuario."""
    raiz = Path(raiz)
    resultado: dict[tuple[str, str], str] = {}
    ignorados = {"tests", "venv", "node_modules", "__pycache__"}
    for ruta in sorted(raiz.rglob("*.py")):
        partes = ruta.relative_to(raiz).parts
        if any(p.startswith(".") or p in ignorados for p in partes[:-1]):
            continue
        relativa = ruta.relative_to(raiz).as_posix()
        try:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=relativa)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
            continue
        for nodo in arbol.body:
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            huella = hashlib.sha256(
                ast.dump(nodo, annotate_fields=True, include_attributes=False).encode()
            ).hexdigest()
            if not nodo.name.startswith("_"):
                resultado[(relativa, nodo.name)] = huella
            for decorador in nodo.decorator_list:
                llamada = decorador if isinstance(decorador, ast.Call) else None
                atributo = llamada.func if llamada else None
                if not isinstance(atributo, ast.Attribute) or not llamada.args:
                    continue
                metodo = atributo.attr.upper()
                if metodo not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    continue
                try:
                    camino = ast.literal_eval(llamada.args[0])
                except (ValueError, TypeError):
                    continue
                if isinstance(camino, str):
                    resultado[(relativa, f"{metodo} {camino}")] = huella
    return resultado


def _cobertura(datos: dict[str, Any] | None) -> dict[str, float | None] | None:
    totales = (datos or {}).get("totals")
    if not isinstance(totales, dict):
        return None
    ramas = totales.get("num_branches", 0)
    return {
        "lineas": float(totales.get("percent_covered", 0.0)),
        "ramas": round(float(totales.get("covered_branches", 0)) / ramas * 100, 1)
        if ramas
        else None,
    }


def _specs_aprobadas(almacen: AlmacenProyecto) -> list[dict[str, Any]]:
    """Lee candidatas aprobadas y conserva hashes corruptos para bloquearlos."""
    candidatas: list[dict[str, Any]] = []
    if not almacen.carpeta_specs.is_dir():
        return candidatas
    for ruta in sorted(almacen.carpeta_specs.glob("*.json")):
        if ruta.name.endswith(".spec.json"):
            continue
        try:
            spec = json.loads(ruta.read_text(encoding="utf-8"))
            contrato = spec["contrato"]
            contracts.validar(contracts.PLANNER, contrato)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            contracts.ContratoInvalido,
        ):
            continue
        archivo = spec.get("archivo_prueba")
        if spec.get("estado") != "vigente" or not isinstance(archivo, str):
            continue
        huella = spec.get("huella_objetivo")
        if huella is not None and not (
            isinstance(huella, str) and re.fullmatch(r"[0-9a-f]{64}", huella)
        ):
            spec["_motivo_regresion"] = "metadatos_corruptos"
        candidatas.append(spec)
    return candidatas


def ejecutar_regresion(
    ruta_proyecto: str | Path,
    perfil: str,
    configuracion: Any,
    *,
    al_evento: Any = None,
    run_id: str | None = None,
    preparar_imagen: Any = None,
    ejecutor: Any = ejecutar_pruebas,
    seleccion: list[dict[str, Any]] | None = None,
    mutador: Any = None,
) -> Any:
    """Reejecuta una vez cada prueba aprobada vigente; nunca crea clientes LLM.

    Con el perfil `reg_deep` (#70), al final aplica mutmut a las funciones críticas
    cuya prueba guardada volvió a pasar, sin IA. Las críticas son las marcadas en la
    Vista previa (`criticas` de la selección, HU-06); sin selección, las del contrato
    guardado.
    """
    from qagent.orchestrator.corrida import ResumenCorrida, _cerrar_run, metas_de

    inicio = time.monotonic()
    raiz = Path(ruta_proyecto)
    almacen = AlmacenProyecto(raiz)
    resumen = ResumenCorrida(run_id, "fin", None, 0)
    tracker = TokenTracker(configuracion.agentes)
    resultados: list[ResultadoCorrida] = []
    huellas = huellas_de_objetivos(raiz)
    marcadas = (
        None
        if seleccion is None
        else {e["ruta"]: set(e.get("criticas") or []) for e in seleccion}
    )

    def es_critica(modulo: str, objetivo: str, contrato: dict[str, Any]) -> bool:
        if marcadas is None:
            return bool(contrato.get("critical"))
        return objetivo in marcadas.get(modulo, set())

    def emitir(
        mensaje: str,
        archivo: str | None = None,
        tipo: str = "agente",
        datos: dict[str, Any] | None = None,
    ) -> None:
        if al_evento:
            evento = Evento(
                "orquestador",
                archivo,
                (datos or {}).get("objetivo"),
                mensaje,
                "regresion",
                tipo,
                datos=datos,
            )
            al_evento(
                {
                    **evento.a_dict(),
                    "progreso": {
                        "hechos": len(resultados),
                        "total": resumen.total_funciones,
                    },
                }
            )

    try:
        specs = _specs_aprobadas(almacen)
        if seleccion is not None:
            elegidos = {
                (entrada["ruta"], objetivo)
                for entrada in seleccion
                for objetivo in entrada["funciones"] + entrada["endpoints"]
            }
            specs = [
                spec
                for spec in specs
                if (
                    spec["contrato"]["modulo"],
                    spec["contrato"]["objetivo"],
                )
                in elegidos
            ]
        resumen.total_funciones = len(specs)
        if not specs:
            raise RuntimeError("No hay pruebas aprobadas vigentes para Regresion.")
        emitir("Regresion sin IA: comprobando huellas de pruebas aprobadas")
        imagen: str | None = None
        for spec in specs:
            contrato = spec["contrato"]
            modulo, objetivo = contrato["modulo"], contrato["objetivo"]
            ruta_test = almacen.carpeta_tests / spec["archivo_prueba"]
            try:
                codigo = ruta_test.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                codigo = None
            esperada = spec.get("huella_objetivo")
            actual = huellas.get((modulo, objetivo))
            motivo = spec.get("_motivo_regresion")
            if motivo is None and not esperada:
                motivo = "huella_ausente"
            elif motivo is None and actual is None:
                motivo = "objetivo_ausente"
            elif motivo is None and actual != esperada:
                motivo = "huella_distinta"
            elif motivo is None and codigo is None:
                motivo = "prueba_ausente"
            if motivo:
                obj = ResultadoObjetivo(
                    objetivo,
                    es_critica(modulo, objetivo, contrato),
                    decision="requiere_corrida_nueva",
                    contrato=contrato,
                    codigo=codigo,
                    motivo_regresion=motivo,
                )
                resultados.append(
                    ResultadoCorrida(
                        modulo,
                        Estado.FIN,
                        None,
                        [obj],
                        [Estado.PLANIFICAR, Estado.FIN],
                        {},
                        0.0,
                    )
                )
                emitir(
                    f"{objetivo}: requiere corrida nueva ({motivo})",
                    modulo,
                    "veredicto",
                    {
                        "decision": "requiere_corrida_nueva",
                        "objetivo": objetivo,
                    },
                )
                continue
            if imagen is None:
                emitir("Preparando sandbox Docker sin red; no se llamara a ninguna IA")
                imagen = (preparar_imagen or _preparar_imagen)(raiz)
            emitir(f"Reejecutando prueba aprobada: {objetivo} (sin IA)", modulo)
            t0 = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="qagent-regresion-") as temporal:
                shutil.copy2(ruta_test, Path(temporal) / ruta_test.name)
                modulo_cov = Path(modulo).with_suffix("").as_posix().replace("/", ".")
                salida = ejecutor(imagen, raiz, temporal, modulo_cov)
            estado = clasificar_resultado(salida)
            decision = (
                "accept"
                if estado == "ok"
                else "bug_detectado"
                if estado == "fallo"
                else "stalled"
            )
            texto = "\n".join(x for x in (salida.stdout, salida.stderr) if x).strip()
            revision = {
                "intento": 1,
                "decision": decision,
                "estado_sandbox": estado,
                "tipo_fallo": "bug_codigo" if estado == "fallo" else None,
                "feedback": texto
                or (
                    "Test aprobado en el sandbox."
                    if estado == "ok"
                    else f"Sandbox: {estado}"
                ),
                "laundering_detectado": False,
            }
            obj = ResultadoObjetivo(
                objetivo,
                es_critica(modulo, objetivo, contrato),
                decision=decision,
                intentos=1,
                cobertura=_cobertura(salida.coverage),
                revisiones=[revision],
                contrato=contrato,
                codigo=codigo,
                duracion_s=round(time.monotonic() - t0, 3),
                reutilizada=True,
                motivo_estancado="limite_intentos" if decision == "stalled" else None,
            )
            resultados.append(
                ResultadoCorrida(
                    modulo,
                    Estado.FIN,
                    None,
                    [obj],
                    [Estado.PLANIFICAR, Estado.FIN],
                    {},
                    obj.duracion_s,
                )
            )
            emitir(
                f"{objetivo}: {'aprobada' if decision == 'accept' else 'fallo detectado'}",
                modulo,
                "veredicto",
                {"decision": decision, "intento": 1, "objetivo": objetivo},
            )
        if perfil == PERFIL_REGRESION_PROFUNDA:
            _mutar_criticas(
                raiz,
                imagen,
                resultados,
                configuracion,
                mutador,
                almacen,
                resumen.run_id,
                huellas,
                emitir,
            )
        decisiones = [o.decision for r in resultados for o in r.objetivos]
        resumen.total_funciones = len(decisiones)
        resumen.aceptadas = decisiones.count("accept")
        resumen.bugs_detectados = decisiones.count("bug_detectado")
        resumen.estancadas = decisiones.count("stalled")
        resumen.requieren_corrida_nueva = decisiones.count("requiere_corrida_nueva")
        rutas = escribir_corrida(
            raiz,
            resultados,
            tracker,
            configuracion.agentes,
            perfil,
            run_id=resumen.run_id,
            metas=metas_de(configuracion),
            rama=detectar_rama(raiz),
        )
        resumen.run_id, resumen.carpeta = rutas.run_id, str(rutas.carpeta)
    except Exception as error:  # noqa: BLE001
        resumen.estado = "fallo_controlado"
        resumen.motivo = f"{type(error).__name__}: {error}"
        emitir(f"Regresion detenida: {resumen.motivo}", tipo="fallo")
    resumen.tokens = 0
    resumen.costo_usd = 0.0
    resumen.duracion_s = round(time.monotonic() - inicio, 3)
    _cerrar_run(almacen, resumen, ["funcion", "endpoint"])
    emitir(
        f"Regresion terminada sin IA: {resumen.aceptadas} aprobadas, "
        f"{resumen.requieren_corrida_nueva} requieren corrida nueva",
        tipo="fin",
    )
    return resumen


def _mutar_criticas(
    raiz: Path,
    imagen: str | None,
    resultados: list[ResultadoCorrida],
    configuracion: Any,
    mutador: Any,
    almacen: AlmacenProyecto,
    run_id: str | None,
    huellas: dict[tuple[str, str], str],
    emitir: Any,
) -> None:
    """#70: mutmut sobre las críticas cuya prueba guardada volvió a pasar.

    Las que requieren corrida nueva o fallaron no se mutan: su prueba no sirve hoy
    para juzgar a los mutantes. Reutiliza el resultado guardado si la función y las
    pruebas usadas no cambiaron, y guarda los nuevos.
    """
    from qagent.config.carga import Mutacion

    tiempo = getattr(configuracion, "mutacion", Mutacion()).tiempo_maximo_por_funcion_s
    por_modulo: dict[str, list[ResultadoObjetivo]] = {}
    for resultado in resultados:
        por_modulo.setdefault(resultado.modulo, []).extend(resultado.objetivos)
    for modulo, objetivos in por_modulo.items():
        mutar_modulo(
            raiz,
            imagen,
            {"ruta": modulo, "funciones": _lineas_de(raiz, modulo)},
            ResultadoCorrida(modulo, Estado.FIN, None, objetivos, [], {}, 0.0),
            tiempo,
            mutador,
            lambda mensaje, archivo=modulo: emitir(mensaje, archivo),
            almacen=almacen if almacen.existe() else None,
            run_id=run_id,
            huellas=huellas,
        )


def _lineas_de(raiz: Path, modulo: str) -> list[dict[str, Any]]:
    """Línea del `def` de cada función de primer nivel del módulo (solo `ast`)."""
    try:
        arbol = ast.parse((raiz / modulo).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return []
    return [
        {"nombre": nodo.name, "linea": nodo.lineno}
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _preparar_imagen(ruta: Path) -> str:
    from qagent.orchestrator.corrida import _preparar_imagen as preparar

    return preparar(ruta)

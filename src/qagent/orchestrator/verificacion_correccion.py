"""Verificación determinista de correcciones con pruebas de una corrida anterior (#194).

Este flujo es distinto de la regresión HU-25: permite que cambie la implementación,
pero exige la misma identidad y firma. Nunca crea agentes ni clientes LLM y ejecuta el
código de prueba original únicamente dentro del sandbox.
"""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.agents.planner import contrato_sin_triviales
from qagent.almacenamiento import (
    AlmacenProyecto,
    ErrorAlmacen,
    id_de_spec,
    nombre_prueba,
)
from qagent.almacenamiento.proyecto import huella_de_prueba
from qagent.lenguajes import adaptador_de_contrato, adaptador_del_proyecto
from qagent.llm.tracker import TokenTracker
from qagent.orchestrator.comparacion import clasificar_comparacion
from qagent.orchestrator.estados import Estado
from qagent.orchestrator.eventos import Evento
from qagent.orchestrator.orquestador import ResultadoCorrida, ResultadoObjetivo
from qagent.orchestrator.tiempos import etapas_vacias, iso_utc, segundos, sumar_etapa
from qagent.proyectos.proyecto_local import detectar_rama
from qagent.sandbox import clasificar_resultado, ejecutar_pruebas
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.storage import escribir_corrida
from qagent.storage.registro import PERFIL_VERIFICAR_CORRECCION


@dataclass(frozen=True)
class PruebaOrigen:
    """Prueba y procedencia recuperadas exclusivamente de la corrida elegida."""

    modulo: str
    objetivo: str
    tipo: str
    decision: str
    contrato: dict[str, Any] | None
    codigo: str | None
    huella: str | None
    firma: str | None
    archivo: str
    motivo_no_comparable: str | None = None

    @property
    def id(self) -> str:
        return id_de_spec(self.modulo, self.objetivo)


def inspeccionar_verificacion(
    ruta_proyecto: str | Path, run_origen_id: str
) -> dict[str, Any]:
    """Valida la corrida elegida y anticipa qué pruebas son comparables.

    Solo analiza archivos estáticamente. No prepara Docker ni ejecuta pruebas.
    """
    raiz = Path(ruta_proyecto).resolve()
    almacen = AlmacenProyecto(raiz)
    pruebas = _pruebas_de_origen(almacen, run_origen_id)
    firmas, errores = _firmas_actuales(raiz)
    ejecutables = 0
    motivos: list[str] = []
    for prueba in pruebas:
        motivo = _motivo_no_comparable(prueba, firmas, errores)
        if motivo is None:
            ejecutables += 1
        else:
            motivos.append(f"{prueba.modulo}::{prueba.objetivo}: {motivo}")
    return {
        "run_origen_id": run_origen_id,
        "total": len(pruebas),
        "ejecutables": ejecutables,
        "no_comparables": len(pruebas) - ejecutables,
        "motivos": motivos,
    }


def ejecutar_verificacion_correccion(
    ruta_proyecto: str | Path,
    run_origen_id: str,
    configuracion: Any,
    *,
    al_evento: Any = None,
    run_id: str | None = None,
    preparar_imagen: Any = None,
    ejecutor: Any = ejecutar_pruebas,
    reloj: Any = time.monotonic,
    ahora: Any = iso_utc,
    cancelado: Any = None,
) -> Any:
    """Reejecuta pruebas originales comparables y guarda ``run_comparison.v1``.

    La prueba no se regenera ni se modifica. Una firma incompatible, un objetivo
    ausente o metadatos insuficientes producen ``no_comparable`` sin entrar al sandbox.
    """
    from qagent.orchestrator.corrida import (
        ResumenCorrida,
        _cerrar_run,
        limites_del_lenguaje,
        metas_de,
    )

    inicio = reloj()
    inicio_utc = ahora()
    raiz = Path(ruta_proyecto).resolve()
    almacen = AlmacenProyecto(raiz)
    if run_id is None:
        run_id = almacen.crear_run(tipos_prueba=["funcion", "endpoint"])["run_id"]
    resumen = ResumenCorrida(
        run_id,
        "fin",
        None,
        0,
        inicio=inicio_utc,
        duracion_etapas=etapas_vacias(),
    )
    tracker = TokenTracker(configuracion.agentes)
    resultados: list[ResultadoCorrida] = []
    comparaciones: list[dict[str, Any]] = []
    imagen: str | None = None
    ejecutor_propio = None if ejecutor is ejecutar_pruebas else ejecutor

    def emitir(
        mensaje: str,
        prueba: PruebaOrigen | None = None,
        tipo: str = "agente",
        datos: dict[str, Any] | None = None,
    ) -> None:
        if al_evento is None:
            return
        evento = Evento(
            "orquestador",
            prueba.modulo if prueba else None,
            prueba.objetivo if prueba else None,
            mensaje,
            "verificacion_correccion",
            tipo,
            datos=datos,
        )
        al_evento(
            {
                **evento.a_dict(),
                "progreso": {
                    "hechos": len(resultados),
                    "total": resumen.total_seleccionados,
                },
                "run_origen_id": run_origen_id,
                "inicio_corrida": inicio_utc,
                "transcurrido_s": segundos(inicio, reloj()),
                "etapas_s": dict(resumen.duracion_etapas),
                "tokens_acumulados": 0,
                "tokens_reales": 0,
                "tokens_estimados": 0,
            }
        )

    try:
        pruebas = _pruebas_de_origen(almacen, run_origen_id)
        firmas, errores_firma = _firmas_actuales(raiz)
        resumen.total_seleccionados = len(pruebas)
        resumen.total_elegibles = len(pruebas)
        resumen.total_funciones = len(pruebas)
        emitir(
            f"Verificando corrección de {run_origen_id} con pruebas originales y sin IA"
        )

        for indice, prueba in enumerate(pruebas):
            inicio_objetivo = reloj()
            inicio_objetivo_utc = ahora()
            motivo = _motivo_no_comparable(prueba, firmas, errores_firma)
            if cancelado is not None and cancelado():
                motivo = (
                    "Verificación cancelada por el usuario antes de ejecutar la prueba."
                )
                resumen.cancelada = True
                resumen.estado = "fallo_controlado"
                resumen.tipo_terminacion = "cancelada"
                resumen.motivo = "Corrida detenida por el usuario."

            firma_actual = firmas.get((prueba.modulo, prueba.objetivo))
            if motivo is not None:
                objeto = _resultado_no_comparable(
                    prueba,
                    motivo,
                    inicio_objetivo_utc,
                    ahora(),
                    segundos(inicio_objetivo, reloj()),
                )
                resultados.append(_resultado_modulo(prueba.modulo, objeto))
                comparaciones.append(
                    _comparacion(
                        prueba,
                        run_origen_id,
                        run_id,
                        firma_actual,
                        "requiere_corrida_nueva",
                        False,
                        "no_comparable",
                        motivo,
                        None,
                    )
                )
                emitir(
                    f"{prueba.objetivo}: no comparable ({motivo})",
                    prueba,
                    "veredicto",
                    {"decision": "requiere_corrida_nueva", "objetivo": prueba.objetivo},
                )
                if resumen.cancelada:
                    for pendiente in pruebas[indice + 1 :]:
                        motivo_pendiente = (
                            "No se ejecutó porque la verificación fue cancelada."
                        )
                        objeto = _resultado_no_comparable(
                            pendiente,
                            motivo_pendiente,
                            ahora(),
                            ahora(),
                            0.0,
                        )
                        resultados.append(_resultado_modulo(pendiente.modulo, objeto))
                        comparaciones.append(
                            _comparacion(
                                pendiente,
                                run_origen_id,
                                run_id,
                                firmas.get((pendiente.modulo, pendiente.objetivo)),
                                "requiere_corrida_nueva",
                                False,
                                "no_comparable",
                                motivo_pendiente,
                                None,
                            )
                        )
                    break
                continue

            if imagen is None:
                emitir("Preparando sandbox Docker sin red y sin clientes LLM")
                imagen = (preparar_imagen or _preparar_imagen)(raiz)
            emitir(f"Ejecutando la prueba original: {prueba.objetivo}", prueba)
            t0 = reloj()
            with tempfile.TemporaryDirectory(
                prefix="qagent-verificar-correccion-"
            ) as temporal:
                ruta_temporal = Path(temporal) / prueba.archivo
                ruta_temporal.write_text(prueba.codigo or "", encoding="utf-8")
                huella_temporal = huella_de_prueba(
                    ruta_temporal.read_text(encoding="utf-8")
                )
                if huella_temporal != prueba.huella:
                    raise RuntimeError(
                        "La copia temporal no conserva la prueba original."
                    )
                adaptador = adaptador_de_contrato(prueba.contrato or {})
                modulo_cov = adaptador.modulo_cobertura(prueba.modulo)
                if ejecutor_propio is not None:
                    salida = ejecutor_propio(imagen, raiz, temporal, modulo_cov)
                else:
                    salida = ejecutar_comando_pruebas(
                        imagen,
                        adaptador.comando_pruebas(
                            modulo_cov,
                            contracts.normalizar_planner(prueba.contrato or {})[
                                "framework_pruebas"
                            ],
                        ),
                        raiz,
                        temporal,
                        leer_cobertura=adaptador.leer_cobertura,
                        archivo_informe=adaptador.entorno_sandbox().informe,
                        variables=adaptador.variables_pruebas(),
                        limites=limites_del_lenguaje(configuracion, adaptador.lenguaje),
                    )
            duracion_sandbox = segundos(t0, reloj())
            estado_sandbox = clasificar_resultado(salida)
            confiable = estado_sandbox in {"ok", "fallo"}
            decision = (
                "accept"
                if estado_sandbox == "ok"
                else "bug_detectado"
                if estado_sandbox == "fallo"
                else "stalled"
            )
            texto = "\n".join(x for x in (salida.stdout, salida.stderr) if x).strip()
            resultado_comparacion, motivo_comparacion = clasificar_comparacion(
                decision_anterior=prueba.decision,
                decision_posterior=decision,
                firma_origen=prueba.firma,
                firma_verificacion=firma_actual,
                huella_prueba_origen=prueba.huella,
                huella_prueba_verificacion=huella_temporal,
                estado_posterior_confiable=confiable,
            )
            revision = {
                "intento": 1,
                "decision": decision,
                "estado_sandbox": estado_sandbox,
                "tipo_fallo": "bug_codigo" if estado_sandbox == "fallo" else None,
                "feedback": texto
                or (
                    "Prueba original aprobada en el sandbox."
                    if estado_sandbox == "ok"
                    else f"Sandbox: {estado_sandbox}"
                ),
                "laundering_detectado": False,
            }
            objeto = ResultadoObjetivo(
                prueba.objetivo,
                bool((prueba.contrato or {}).get("critical")),
                decision=decision,
                intentos=1,
                revisiones=[revision],
                contrato=prueba.contrato,
                codigo=prueba.codigo,
                duracion_s=segundos(inicio_objetivo, reloj()),
                reutilizada=True,
                motivo_estancado="error_repetido" if not confiable else None,
                inicio=inicio_objetivo_utc,
                fin=ahora(),
                duracion_sandbox_s=duracion_sandbox,
                tiempos_intentos=[
                    {
                        "intento": 1,
                        "duracion_s": duracion_sandbox,
                        "generacion_s": 0.0,
                        "revision_s": 0.0,
                        "sandbox_s": duracion_sandbox,
                        "pytest_s": 0.0,
                    }
                ],
            )
            resultados.append(_resultado_modulo(prueba.modulo, objeto))
            sumar_etapa(resumen.duracion_etapas, "sandbox", duracion_sandbox)
            comparaciones.append(
                _comparacion(
                    prueba,
                    run_origen_id,
                    run_id,
                    firma_actual,
                    decision,
                    confiable,
                    resultado_comparacion,
                    motivo_comparacion,
                    huella_temporal,
                    texto or None,
                )
            )
            emitir(
                f"{prueba.objetivo}: {resultado_comparacion}",
                prueba,
                "veredicto",
                {"decision": decision, "objetivo": prueba.objetivo},
            )

        decisiones = [o.decision for r in resultados for o in r.objetivos]
        resumen.total_procesados = len(decisiones)
        resumen.total_pendientes = 0
        resumen.aceptadas = decisiones.count("accept")
        resumen.bugs_detectados = decisiones.count("bug_detectado")
        resumen.estancadas = decisiones.count("stalled")
        resumen.requieren_corrida_nueva = decisiones.count("requiere_corrida_nueva")
        if resumen.estado == "fin":
            resumen.tipo_terminacion = (
                "completada_con_errores"
                if resumen.estancadas or resumen.requieren_corrida_nueva
                else "completada"
            )
        resumen.duracion_s = segundos(inicio, reloj())
        resumen.fin = ahora()
        rutas = escribir_corrida(
            raiz,
            resultados,
            tracker,
            configuracion.agentes,
            PERFIL_VERIFICAR_CORRECCION,
            run_id=run_id,
            metas=metas_de(configuracion),
            rama=detectar_rama(raiz),
            inicio=resumen.inicio,
            fin=resumen.fin,
            duracion_s=resumen.duracion_s,
            duracion_etapas=resumen.duracion_etapas,
            total_seleccionados=resumen.total_seleccionados,
            total_elegibles=resumen.total_elegibles,
            total_procesados=resumen.total_procesados,
            total_pendientes=resumen.total_pendientes,
            tipo_terminacion=resumen.tipo_terminacion,
        )
        resumen.run_id, resumen.carpeta = rutas.run_id, str(rutas.carpeta)
        comparacion = {
            "version": "1",
            "run_origen_id": run_origen_id,
            "run_verificacion_id": run_id,
            "creado": resumen.fin,
            "comparaciones": comparaciones,
        }
        almacen.guardar_comparacion(comparacion)
    except Exception as error:  # noqa: BLE001
        resumen.estado = "fallo_controlado"
        resumen.tipo_terminacion = "detenida_error"
        resumen.motivo = f"{type(error).__name__}: {error}"
        resumen.fin = ahora()
        resumen.duracion_s = segundos(inicio, reloj())
        emitir(f"Verificación detenida: {resumen.motivo}", tipo="fallo")

    resumen.tokens = 0
    resumen.tokens_reales = 0
    resumen.tokens_estimados = 0
    resumen.costo_usd = 0.0
    _cerrar_run(almacen, resumen, ["funcion", "endpoint"])
    emitir(
        "Verificación terminada sin IA: "
        f"{resumen.aceptadas} aprobadas, {resumen.bugs_detectados} con fallo y "
        f"{resumen.requieren_corrida_nueva} no comparables",
        tipo="fin",
    )
    return resumen


def _pruebas_de_origen(
    almacen: AlmacenProyecto, run_origen_id: str
) -> list[PruebaOrigen]:
    """Recupera accept y bug_detectado sin mezclar otras corridas."""
    almacen.leer_run(run_origen_id)
    carpeta = almacen.carpeta_run(run_origen_id)
    results = _leer_json(carpeta / "results.json", "resultados de la corrida de origen")
    if results.get("run_id") != run_origen_id:
        raise ErrorAlmacen(
            "El run_id de results.json no coincide con la corrida elegida."
        )
    detalle = _leer_json_opcional(carpeta / "detalle.json")
    detalles = {
        (f.get("modulo"), f.get("funcion")): f
        for f in detalle.get("funciones", [])
        if isinstance(f, dict)
    }
    pruebas: list[PruebaOrigen] = []
    for objetivo in results.get("objetivos", []):
        decision = objetivo.get("decision")
        if decision not in {"accept", "bug_detectado"}:
            continue
        modulo = objetivo.get("modulo")
        nombre = objetivo.get("funcion")
        tipo = objetivo.get("tipo", "funcion")
        if not all(isinstance(v, str) and v for v in (modulo, nombre, tipo)):
            continue
        evidencia_id = id_de_spec(modulo, nombre)
        archivo = nombre_prueba(evidencia_id)
        contrato = codigo = firma = huella = None
        motivo = None
        if decision == "bug_detectado":
            try:
                evidencia = almacen.leer_evidencia_bug(run_origen_id, evidencia_id)
                contrato = evidencia["spec"]
                codigo = evidencia["codigo_prueba"]
                firma = evidencia["firma"]
                huella = evidencia["huella_prueba"]
                archivo = evidencia["archivo_prueba"]
            except ErrorAlmacen as error:
                motivo = f"La evidencia original de bug no está disponible o es inválida: {error}"
        else:
            registro = detalles.get((modulo, nombre), {})
            contrato = registro.get("contrato")
            codigo = registro.get("codigo")
            firma = contrato.get("firma") if isinstance(contrato, dict) else None
            if not isinstance(codigo, str) or not codigo.strip():
                codigo = None
                motivo = (
                    "La corrida original no conserva el código de la prueba aprobada."
                )
            else:
                huella = huella_de_prueba(codigo)
            if isinstance(contrato, dict) and contrato_sin_triviales(contrato) is None:
                motivo = (
                    "La prueba histórica solo verifica un TypeError trivial de la firma "
                    "y se conserva excluida por #149."
                )
        if contrato is not None:
            try:
                contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)
            except contracts.ContratoInvalido as error:
                motivo = f"La spec original es inválida: {error}"
                contrato = None
        pruebas.append(
            PruebaOrigen(
                modulo,
                nombre,
                tipo,
                decision,
                contrato,
                codigo,
                huella,
                firma,
                archivo,
                motivo,
            )
        )
    if not pruebas:
        raise ErrorAlmacen(
            "La corrida elegida no contiene pruebas aprobadas ni evidencias de bugs verificables."
        )
    return pruebas


def _firmas_actuales(
    raiz: Path,
) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """Extrae firmas con el adaptador; nunca importa ni ejecuta el proyecto."""
    analisis = adaptador_del_proyecto(raiz).analizar(raiz)
    firmas: dict[tuple[str, str], str] = {}
    for modulo in analisis.get("modulos", []):
        ruta = modulo.get("ruta")
        for funcion in modulo.get("funciones", []):
            if funcion.get("nombre") and funcion.get("firma"):
                firmas[(ruta, funcion["nombre"])] = funcion["firma"]
        for endpoint in modulo.get("endpoints", []):
            if endpoint.get("objetivo") and endpoint.get("firma"):
                firmas[(ruta, endpoint["objetivo"])] = endpoint["firma"]
    errores = {
        e.get("ruta", ""): e.get("mensaje", "No se pudo analizar el módulo.")
        for e in analisis.get("errores", [])
        if isinstance(e, dict)
    }
    return firmas, errores


def _motivo_no_comparable(
    prueba: PruebaOrigen,
    firmas: dict[tuple[str, str], str],
    errores: dict[str, str],
) -> str | None:
    if prueba.motivo_no_comparable:
        return prueba.motivo_no_comparable
    if not prueba.codigo or not prueba.huella:
        return "La prueba original está ausente o no tiene una identidad verificable."
    if prueba.contrato is None or not prueba.firma:
        return "La spec o la firma original no están disponibles."
    clave = (prueba.modulo, prueba.objetivo)
    actual = firmas.get(clave)
    if actual is None:
        if prueba.modulo in errores:
            return f"No se pudo determinar la firma actual: {errores[prueba.modulo]}"
        return "El objetivo original ya no existe en el mismo módulo (eliminado o renombrado)."
    if actual != prueba.firma:
        return f"La firma cambió: antes {prueba.firma}; ahora {actual}."
    if huella_de_prueba(prueba.codigo) != prueba.huella:
        return "El código original no coincide con su SHA-256 guardado."
    return None


def _comparacion(
    prueba: PruebaOrigen,
    run_origen_id: str,
    run_verificacion_id: str,
    firma_actual: str | None,
    decision_posterior: str,
    confiable: bool,
    resultado: str,
    motivo: str | None,
    huella_verificacion: str | None,
    observado: str | None = None,
) -> dict[str, Any]:
    return {
        "objetivo": {
            "modulo": prueba.modulo,
            "nombre": prueba.objetivo,
            "tipo": prueba.tipo,
        },
        "prueba": {
            "id": prueba.id,
            "archivo": prueba.archivo,
            "run_origen_id": run_origen_id,
            "huella_origen": prueba.huella,
            "huella_verificacion": huella_verificacion,
        },
        "firma_origen": prueba.firma,
        "firma_verificacion": firma_actual,
        "estado_anterior": {
            "decision": prueba.decision,
            "confiable": True,
            "referencia_resultado": f"runs/{run_origen_id}/results.json",
        },
        "estado_posterior": {
            "decision": decision_posterior,
            "confiable": confiable,
            "referencia_resultado": f"runs/{run_verificacion_id}/results.json",
            "observado": observado,
        },
        "resultado": resultado,
        "motivo": motivo,
    }


def _resultado_no_comparable(
    prueba: PruebaOrigen, motivo: str, inicio: str, fin: str, duracion: float
) -> ResultadoObjetivo:
    return ResultadoObjetivo(
        prueba.objetivo,
        bool((prueba.contrato or {}).get("critical")),
        decision="requiere_corrida_nueva",
        contrato=prueba.contrato,
        codigo=prueba.codigo,
        reutilizada=True,
        motivo_regresion="metadatos_corruptos",
        motivo_estancado=None,
        inicio=inicio,
        fin=fin,
        duracion_s=duracion,
    )


def _resultado_modulo(modulo: str, objetivo: ResultadoObjetivo) -> ResultadoCorrida:
    return ResultadoCorrida(
        modulo,
        Estado.FIN,
        None,
        [objetivo],
        [Estado.PLANIFICAR, Estado.FIN],
        {},
        objetivo.duracion_s,
        inicio=objetivo.inicio,
        fin=objetivo.fin,
    )


def _leer_json(ruta: Path, descripcion: str) -> dict[str, Any]:
    try:
        dato = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ErrorAlmacen(f"No se pudieron leer {descripcion}: {error}") from error
    if not isinstance(dato, dict):
        raise ErrorAlmacen(f"{descripcion.capitalize()} no tienen un formato válido.")
    return dato


def _leer_json_opcional(ruta: Path) -> dict[str, Any]:
    try:
        return _leer_json(ruta, ruta.name)
    except ErrorAlmacen:
        return {}


def _preparar_imagen(raiz: Path) -> str:
    from qagent.sandbox import preparar_imagen

    return preparar_imagen(raiz)

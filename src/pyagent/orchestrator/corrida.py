"""Corrida completa sobre un proyecto: análisis → agentes → registro (EN-04, EN-05, EN-07).

Une las piezas que ya existían por separado:

1. Analiza el proyecto con `ast` (EN-02) y cuenta las funciones a revisar.
2. Crea el cliente LLM de cada agente desde `config.toml` y `.env` (o la IA simulada).
3. Ejecuta el orquestador módulo por módulo; cada `Evento` llega a `al_evento` con el
   progreso (`hechos` / `total`), para el Monitor en vivo (HU-09).
4. Corta antes del siguiente módulo si se alcanzó el tope de gasto de `config.toml`.
5. Escribe `log.json` y `results.json` (EN-05) en la carpeta de la corrida, guarda las
   specs y las pruebas aprobadas en `.pyagent/` y cierra el `run.json` (EN-07).

No depende de la interfaz: la app la llama en un hilo y le pasa una función para los
eventos. Nunca lanza excepciones: cualquier problema termina en `fallo_controlado` con
el motivo en el resumen.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pyagent.agents import GeneratorAgent, PlannerAgent, ReviewerAgent
from pyagent.agents.reviewer import Ejecutor
from pyagent.almacenamiento import AlmacenProyecto, id_de_spec, nombre_prueba
from pyagent.analysis.analyzer import analizar_proyecto
from pyagent.llm import TokenTracker, crear_cliente
from pyagent.llm.fabrica import FuenteClaves
from pyagent.orchestrator.eventos import BusEventos, Evento
from pyagent.orchestrator.orquestador import Orquestador, ResultadoCorrida
from pyagent.sandbox import ejecutar_pruebas
from pyagent.storage import escribir_corrida

AlEvento = Callable[[dict[str, Any]], None]
PrepararImagen = Callable[[Path], str]

FIN = "fin"
_registro = logging.getLogger("qagent.corrida")
FALLO = "fallo_controlado"


@dataclass
class ResumenCorrida:
    """Lo que la interfaz necesita saber cuando la corrida termina."""

    run_id: str | None
    estado: str
    motivo: str | None
    total_funciones: int
    aceptadas: int = 0
    bugs_detectados: int = 0
    estancadas: int = 0
    sin_veredicto: int = 0
    tokens: int = 0
    costo_usd: float = 0.0
    carpeta: str | None = None
    duracion_s: float = 0.0

    def a_dict(self) -> dict[str, Any]:
        """Versión serializable a JSON (evento `corrida_fin` de la interfaz)."""
        return asdict(self)


def ejecutar_corrida(
    ruta_proyecto: str | Path,
    perfil: str,
    configuracion: Any,
    claves: FuenteClaves | None,
    *,
    simulado: bool,
    al_evento: AlEvento | None = None,
    run_id: str | None = None,
    preparar_imagen: PrepararImagen | None = None,
    ejecutor: Ejecutor = ejecutar_pruebas,
    timeout_paso_s: float | None = None,
) -> ResumenCorrida:
    """Ejecuta la corrida completa de un proyecto y devuelve su resumen.

    Args:
        ruta_proyecto: carpeta del proyecto abierto.
        perfil: perfil elegido en la interfaz (se registra en log.json).
        configuracion: `Configuracion` de `cargar_configuracion()` (agentes, tope de
            gasto y reintentos).
        claves: claves de `.env`; no se usan con la IA simulada.
        simulado: True con `PYAGENT_FAKE_LLM=1` (0 tokens).
        al_evento: recibe cada evento como dict (`Evento.a_dict()` + `progreso`).
        run_id: corrida creada al pulsar «Iniciar» (`run.json`); si es None se crea una
            si el proyecto tiene `.pyagent/`.
        preparar_imagen: devuelve la imagen Docker del sandbox para el proyecto; por
            defecto `sandbox.preparar_imagen` (construye la base si falta).
        ejecutor: cómo ejecuta el Reviewer las pruebas (Docker; reemplazable en pruebas).
        timeout_paso_s: tiempo máximo por paso de un agente (por defecto el del
            orquestador).
    """
    inicio = time.monotonic()
    ruta = Path(ruta_proyecto)
    progreso = {"hechos": 0, "total": 0}

    def emitir(evento: Evento) -> None:
        if evento.tipo == "veredicto":
            progreso["hechos"] += 1
        if al_evento is not None:
            al_evento({**evento.a_dict(), "progreso": dict(progreso)})

    def avisar(mensaje: str, tipo: str = "agente", archivo: str | None = None) -> None:
        emitir(Evento("orquestador", archivo, None, mensaje, "preparacion", tipo))

    almacen = AlmacenProyecto(ruta)
    resumen = ResumenCorrida(run_id=run_id, estado=FIN, motivo=None, total_funciones=0)
    try:
        if not ruta.is_dir():
            raise ErrorCorrida(f"La carpeta del proyecto no existe: {ruta}")
        if resumen.run_id is None and almacen.existe():
            resumen.run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]

        analisis = analizar_proyecto(ruta)
        modulos = [m for m in analisis["modulos"] if m["funciones"]]
        progreso["total"] = resumen.total_funciones = sum(
            len(m["funciones"]) for m in modulos
        )
        avisar(
            f"Análisis estático: {len(modulos)} módulo(s) con "
            f"{resumen.total_funciones} función(es) pública(s)"
        )
        if not modulos:
            raise ErrorCorrida("El proyecto no tiene funciones públicas que revisar.")

        tracker = TokenTracker(configuracion.agentes)
        clientes = {
            agente: crear_cliente(precio, claves, simulado=simulado)
            for agente, precio in configuracion.agentes.items()
        }
        avisar("Preparando el entorno aislado (Docker) para ejecutar las pruebas")
        imagen = (preparar_imagen or _preparar_imagen)(ruta)

        bus = BusEventos()
        bus.suscribir(emitir)
        opciones: dict[str, Any] = {"max_intentos": configuracion.max_intentos}
        if timeout_paso_s is not None:
            opciones["timeout_paso_s"] = timeout_paso_s
        orquestador = Orquestador(
            PlannerAgent(clientes["planner"], tracker, es_simulado=simulado),
            GeneratorAgent(clientes["generator"], tracker, es_simulado=simulado),
            ReviewerAgent(
                tracker,
                ruta,
                imagen,
                cliente=clientes["reviewer"],
                ejecutor=ejecutor,
                es_simulado=simulado,
            ),
            bus=bus,
            tracker=tracker,
            **opciones,
        )

        resultados: list[ResultadoCorrida] = []
        tope = configuracion.presupuesto.tope_por_corrida_usd
        for modulo in modulos:
            if tracker.total_costo_usd >= tope:
                resumen.estado = FALLO
                resumen.motivo = (
                    f"Se alcanzó el tope de gasto por corrida (US$ {tope:.2f}); "
                    "los módulos restantes no se revisaron."
                )
                avisar(resumen.motivo, "fallo")
                break
            resultado = orquestador.ejecutar(modulo)
            resultados.append(resultado)
            if resultado.estado_final.value == FALLO and resumen.motivo is None:
                resumen.estado = FALLO
                resumen.motivo = f"{resultado.modulo}: {resultado.motivo_fallo}"

        _contar(resumen, resultados, tracker)
        _registrar(ruta, almacen, resumen, resultados, tracker, configuracion, perfil)
    except Exception as error:  # noqa: BLE001 — la corrida nunca debe tumbar la app
        resumen.estado = FALLO
        resumen.motivo = resumen.motivo or _texto_error(error)
        avisar(f"Corrida detenida: {resumen.motivo}", "fallo")
        _cerrar_run(almacen, resumen)

    resumen.duracion_s = round(time.monotonic() - inicio, 3)
    avisar(
        f"Corrida terminada: {resumen.aceptadas} aceptada(s), "
        f"{resumen.bugs_detectados} bug(s) detectado(s), {resumen.estancadas} "
        f"estancada(s)",
        "fin",
    )
    return resumen


class ErrorCorrida(RuntimeError):
    """La corrida no puede seguir (motivo legible para la interfaz)."""


# --- Partes de la corrida ---------------------------------------------------------


def _preparar_imagen(ruta: Path) -> str:
    """Imagen del sandbox del proyecto; construye la imagen base si todavía no existe."""
    from pyagent.sandbox import (
        ImagenNoEncontrada,
        construir_imagen_base,
        preparar_imagen,
    )

    try:
        return preparar_imagen(ruta)
    except ImagenNoEncontrada:
        construir_imagen_base()  # una sola vez por PC; necesita internet
        return preparar_imagen(ruta)


def _contar(
    resumen: ResumenCorrida,
    resultados: list[ResultadoCorrida],
    tracker: TokenTracker,
) -> None:
    decisiones = [o.decision for r in resultados for o in r.objetivos]
    resumen.aceptadas = decisiones.count("accept")
    resumen.bugs_detectados = decisiones.count("bug_detectado")
    resumen.estancadas = decisiones.count("stalled")
    resumen.sin_veredicto = decisiones.count(None)
    resumen.tokens = tracker.total_tokens
    resumen.costo_usd = round(tracker.total_costo_usd, 8)


def _registrar(
    ruta: Path,
    almacen: AlmacenProyecto,
    resumen: ResumenCorrida,
    resultados: list[ResultadoCorrida],
    tracker: TokenTracker,
    configuracion: Any,
    perfil: str,
) -> None:
    """log.json y results.json, specs y pruebas aprobadas, y cierre del run.json."""
    if resultados:
        rutas = escribir_corrida(
            ruta,
            resultados,
            tracker,
            configuracion.agentes,
            perfil,
            run_id=resumen.run_id,
        )
        resumen.run_id = rutas.run_id
        resumen.carpeta = str(rutas.carpeta)

    if resumen.run_id is not None and almacen.existe():
        for resultado in resultados:
            for objetivo in resultado.objetivos:
                if objetivo.contrato is None:
                    continue
                archivo = None
                if objetivo.decision == "accept" and objetivo.codigo:
                    spec_id = id_de_spec(resultado.modulo, objetivo.objetivo)
                    archivo = nombre_prueba(spec_id)
                    almacen.guardar_prueba_aprobada(archivo, objetivo.codigo)
                almacen.guardar_spec(objetivo.contrato, resumen.run_id, archivo)
    _cerrar_run(almacen, resumen)


def _cerrar_run(almacen: AlmacenProyecto, resumen: ResumenCorrida) -> None:
    """Marca el `run.json` como terminado. Si no se puede, la corrida no se pierde."""
    if resumen.run_id is None or not almacen.existe():
        return
    try:
        almacen.finalizar_run(
            resumen.run_id,
            resumen.estado,
            pasaron=resumen.aceptadas,
            fallaron=resumen.bugs_detectados
            + resumen.estancadas
            + resumen.sin_veredicto,
            tipos_prueba=["funcion"],
        )
    except Exception as error:  # noqa: BLE001 — run.json dañado: no es motivo de fallo
        _registro.warning(
            "No se pudo cerrar el run.json de %s: %s", resumen.run_id, error
        )


def _texto_error(error: Exception) -> str:
    if isinstance(error, ErrorCorrida):
        return str(error)
    return f"{type(error).__name__}: {error}"

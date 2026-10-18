"""Corrida completa sobre un proyecto: análisis → agentes → registro (EN-04, EN-05, EN-07).

Une las piezas que ya existían por separado:

1. Analiza el proyecto con `ast` (EN-02) y cuenta las funciones a revisar.
2. Crea el cliente LLM de cada agente desde `config.toml` y `.env` (o la IA simulada).
3. Ejecuta el orquestador módulo por módulo; cada `Evento` llega a `al_evento` con el
   progreso (`hechos` / `total`), para el Monitor en vivo (HU-09).
4. Corta antes del siguiente módulo si se alcanzó el tope de gasto de `config.toml`.
5. En el perfil Profundo, aplica mutmut a las funciones críticas aprobadas (EN-09).
6. Reutiliza la spec modular si su huella sigue vigente, solo para los objetivos
   elegidos en la Vista previa; si cambió o le falta alguno, llama al Planner. La
   spec guardada conserva los contratos de los objetivos que no se eligieron.
   Cada spec recuerda el perfil con que se creó (#75): una de Humo (un solo caso) no
   se reutiliza en Estándar ni Profundo, y una Estándar en Humo usa su primer caso
   normal.
7. Escribe `log.json` y `results.json` (EN-05) en la carpeta de la corrida, guarda las
   specs y las pruebas aprobadas en `.qagent/` y cierra el `run.json` (EN-07).

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

from qagent.agents import GeneratorAgent, PlannerAgent, ReviewerAgent
from qagent.agents.planner import contrato_humo
from qagent.agents.reviewer import Ejecutor
from qagent.almacenamiento import (
    AlmacenProyecto,
    ErrorAlmacen,
    id_de_spec,
    nombre_prueba,
)
from qagent.analysis.analyzer import analizar_proyecto
from qagent.config.carga import Mutacion
from qagent.llm import TokenTracker, crear_cliente
from qagent.llm.fabrica import FuenteClaves
from qagent.orchestrator.eventos import BusEventos, Evento
from qagent.orchestrator.mutacion import PERFIL_PROFUNDO, Mutador, mutar_modulo
from qagent.orchestrator.orquestador import (
    Orquestador,
    ResultadoCorrida,
    timeout_paso_para,
)
from qagent.orchestrator.regresion import huellas_de_objetivos
from qagent.proyectos.proyecto_local import detectar_rama
from qagent.sandbox import LIMITES_POR_DEFECTO, ejecutar_mutacion, ejecutar_pruebas
from qagent.storage import escribir_corrida
from qagent.storage.registro import PERFIL_HUMO, PERFILES_REGRESION

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
    requieren_corrida_nueva: int = 0

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
    seleccion: list[dict[str, Any]] | None = None,
    mutador: Mutador = ejecutar_mutacion,
) -> ResumenCorrida:
    """Ejecuta la corrida completa de un proyecto y devuelve su resumen.

    Args:
        ruta_proyecto: carpeta del proyecto abierto.
        perfil: perfil elegido en la interfaz (se registra en log.json). Con `humo`
            el Planner pide un solo caso normal por objetivo (#75).
        configuracion: `Configuracion` de `cargar_configuracion()` (agentes, tope de
            gasto y reintentos).
        claves: claves de `.env`; no se usan con la IA simulada.
        simulado: True con `QAGENT_FAKE_LLM=1` (0 tokens).
        al_evento: recibe cada evento como dict (`Evento.a_dict()` + `progreso`).
        run_id: corrida creada al pulsar «Iniciar» (`run.json`); si es None se crea una
            si el proyecto tiene `.qagent/`.
        preparar_imagen: devuelve la imagen Docker del sandbox para el proyecto; por
            defecto `sandbox.preparar_imagen` (construye la base si falta).
        ejecutor: cómo ejecuta el Reviewer las pruebas (Docker; reemplazable en pruebas).
        timeout_paso_s: tiempo máximo por paso de un agente; por defecto el del
            orquestador, alargado si `[sandbox] timeout_s` lo pide.
        seleccion: módulos, funciones y endpoints elegidos en la Vista previa. Si es
            ``None``, se conservan todos los objetivos analizables.
        mutador: cómo se ejecuta mutmut en el perfil Profundo (EN-09; Docker,
            reemplazable en pruebas).
    """
    if perfil in PERFILES_REGRESION:
        from qagent.orchestrator.regresion import ejecutar_regresion

        return ejecutar_regresion(
            ruta_proyecto,
            perfil,
            configuracion,
            al_evento=al_evento,
            run_id=run_id,
            preparar_imagen=preparar_imagen,
            ejecutor=ejecutor,
            seleccion=seleccion,
            mutador=mutador,
        )

    inicio = time.monotonic()
    ruta = Path(ruta_proyecto)
    progreso = {"hechos": 0, "total": 0}
    estimados_por_modulo: dict[str, int] = {}
    planificados_por_modulo: dict[str, int] = {}

    def emitir(evento: Evento) -> None:
        datos = evento.datos or {}
        planificados = datos.get("objetivos_planificados")
        if evento.archivo and isinstance(planificados, int):
            anterior = planificados_por_modulo.get(
                evento.archivo, estimados_por_modulo.get(evento.archivo, 0)
            )
            progreso["total"] += planificados - anterior
            planificados_por_modulo[evento.archivo] = planificados
        if evento.tipo == "veredicto":
            progreso["hechos"] += 1
        if al_evento is not None:
            al_evento({**evento.a_dict(), "progreso": dict(progreso)})

    def avisar(mensaje: str, tipo: str = "agente", archivo: str | None = None) -> None:
        emitir(Evento("orquestador", archivo, None, mensaje, "preparacion", tipo))

    almacen = AlmacenProyecto(ruta)
    resumen = ResumenCorrida(run_id=run_id, estado=FIN, motivo=None, total_funciones=0)
    tipos: list[str] = ["funcion"]
    try:
        if not ruta.is_dir():
            raise ErrorCorrida(f"La carpeta del proyecto no existe: {ruta}")
        if resumen.run_id is None and almacen.existe():
            resumen.run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]

        from qagent.proyectos.seleccion import filtrar_modulos

        analisis = analizar_proyecto(ruta)
        modulos = [
            _con_fuente(ruta, m)
            for m in filtrar_modulos(analisis["modulos"], seleccion)
        ]
        n_funciones = sum(len(m["funciones"]) for m in modulos)
        n_endpoints = sum(len(m.get("endpoints") or []) for m in modulos)
        estimados_por_modulo.update(
            {
                m["ruta"]: len(m["funciones"]) + len(m.get("endpoints") or [])
                for m in modulos
            }
        )
        progreso["total"] = resumen.total_funciones = n_funciones + n_endpoints
        if n_endpoints:
            tipos = ["funcion", "endpoint"] if n_funciones else ["endpoint"]
            avisar(
                f"Análisis estático: {len(modulos)} módulo(s) con {n_funciones} "
                f"función(es) pública(s) y {n_endpoints} endpoint(s)"
            )
        else:
            avisar(
                f"Análisis estático: {len(modulos)} módulo(s) con "
                f"{n_funciones} función(es) pública(s)"
            )
        if not modulos:
            raise ErrorCorrida(
                "El proyecto no tiene funciones públicas ni endpoints que revisar."
            )

        tracker = TokenTracker(configuracion.agentes)
        clientes = {
            agente: crear_cliente(precio, claves, simulado=simulado)
            for agente, precio in configuracion.agentes.items()
        }
        avisar("Preparando el entorno aislado (Docker) para ejecutar las pruebas")
        imagen = (preparar_imagen or _preparar_imagen)(ruta)

        bus = BusEventos()
        bus.suscribir(emitir)
        limites = getattr(configuracion, "sandbox", LIMITES_POR_DEFECTO)
        opciones: dict[str, Any] = {
            "max_intentos": configuracion.max_intentos,
            "timeout_paso_s": timeout_paso_s
            if timeout_paso_s is not None
            else timeout_paso_para(limites.timeout_s),
        }
        orquestador = Orquestador(
            PlannerAgent(
                clientes["planner"], tracker, es_simulado=simulado, perfil=perfil
            ),
            GeneratorAgent(clientes["generator"], tracker, es_simulado=simulado),
            ReviewerAgent(
                tracker,
                ruta,
                imagen,
                cliente=clientes["reviewer"],
                ejecutor=ejecutor,
                es_simulado=simulado,
                limites=limites,
            ),
            bus=bus,
            tracker=tracker,
            **opciones,
        )

        resultados: list[ResultadoCorrida] = []
        planes_specs: list[dict[str, Any]] = []
        # #70: con las huellas, el Mutation Score de esta corrida queda guardado para
        # reutilizarlo al repetir las pruebas sin cambios.
        huellas = huellas_de_objetivos(ruta) if perfil == PERFIL_PROFUNDO else None
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
            plan_guardado = almacen.buscar_plan_vigente(
                modulo["ruta"], modulo["huella"]
            )
            habia_spec = _existe_plan_modulo(almacen, modulo["ruta"])
            perfiles: dict[str, str] = dict((plan_guardado or {}).get("perfiles") or {})
            # La spec vigente se usa solo para los objetivos elegidos en la Vista
            # previa; si le falta alguno, se vuelve a planificar el módulo.
            elegidos: list[dict[str, Any]] = []
            completos: dict[str, dict[str, Any]] = {}
            faltan: set[str] = set()
            de_humo: set[str] = set()
            if plan_guardado is not None:
                objetivos = _objetivos_de(modulo)
                elegidos = [
                    c for c in plan_guardado["contratos"] if c["objetivo"] in objetivos
                ]
                if perfil == PERFIL_HUMO:
                    # #75: de una spec completa, Humo toma el primer caso normal.
                    completos = {c["objetivo"]: c for c in elegidos}
                    elegidos = [h for h in map(contrato_humo, elegidos) if h]
                else:
                    # #75: una spec de Humo tiene un solo caso; no sirve aquí.
                    de_humo = {
                        c["objetivo"]
                        for c in elegidos
                        if perfiles.get(c["objetivo"]) == PERFIL_HUMO
                    }
                    elegidos = [c for c in elegidos if c["objetivo"] not in de_humo]
                faltan = objetivos - {c["objetivo"] for c in elegidos}
            if plan_guardado is not None and elegidos and not faltan:
                accion = "reutilizado"
                avisar(
                    "Spec vigente: se omite el Planner (0 tokens)",
                    archivo=modulo["ruta"],
                )
                resultado = orquestador.ejecutar(modulo, plan_reutilizado=elegidos)
            else:
                accion = "regenerado" if habia_spec else "generado"
                if de_humo:
                    avisar(
                        f"La spec vigente de {len(de_humo)} objetivo(s) se creó con "
                        "Humo (un solo caso): regenerando spec",
                        archivo=modulo["ruta"],
                    )
                elif plan_guardado is not None:
                    avisar(
                        f"La spec vigente no incluye {len(faltan)} objetivo(s) "
                        "seleccionado(s): regenerando spec",
                        archivo=modulo["ruta"],
                    )
                elif accion == "regenerado":
                    avisar(
                        "El código o docstring cambió: regenerando spec",
                        archivo=modulo["ruta"],
                    )
                resultado = orquestador.ejecutar(modulo)
            if perfil == PERFIL_PROFUNDO:
                mutar_modulo(
                    ruta,
                    imagen,
                    modulo,
                    resultado,
                    getattr(
                        configuracion, "mutacion", Mutacion()
                    ).tiempo_maximo_por_funcion_s,
                    mutador,
                    lambda mensaje, archivo=modulo["ruta"]: avisar(
                        mensaje, archivo=archivo
                    ),
                    almacen=almacen if almacen.existe() else None,
                    run_id=resumen.run_id,
                    huellas=huellas,
                    limites=limites,
                )
            resultados.append(resultado)
            contratos = resultado.plan_completo
            if accion == "reutilizado":
                # En Humo se probó un solo caso, pero la spec guardada sigue completa;
                # solo se actualiza la marca Profundizar de esta corrida.
                contratos = [
                    {**completos.get(c["objetivo"], c), "critical": c["critical"]}
                    for c in contratos
                ]
            else:
                perfiles.update({c["objetivo"]: perfil for c in contratos})
            if contratos and plan_guardado is not None:
                contratos = _combinar_plan(plan_guardado["contratos"], contratos)
            if contratos:
                planes_specs.append(
                    {
                        "modulo": modulo["ruta"],
                        "huella": modulo["huella"],
                        "contratos": contratos,
                        "accion": accion,
                        "perfiles": {
                            c["objetivo"]: perfiles[c["objetivo"]]
                            for c in contratos
                            if c["objetivo"] in perfiles
                        },
                    }
                )
            if resultado.estado_final.value == FALLO and resumen.motivo is None:
                resumen.estado = FALLO
                resumen.motivo = f"{resultado.modulo}: {resultado.motivo_fallo}"

        _contar(resumen, resultados, tracker)
        progreso["total"] = resumen.total_funciones
        _registrar(
            ruta,
            almacen,
            resumen,
            resultados,
            tracker,
            configuracion,
            perfil,
            planes_specs,
            tipos,
        )
    except Exception as error:  # noqa: BLE001 — la corrida nunca debe tumbar la app
        resumen.estado = FALLO
        resumen.motivo = resumen.motivo or _texto_error(error)
        avisar(f"Corrida detenida: {resumen.motivo}", "fallo")
        _cerrar_run(almacen, resumen, tipos)

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
    from qagent.sandbox import (
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
    resumen.total_funciones = len(decisiones)
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
    planes_specs: list[dict[str, Any]],
    tipos: list[str] | None = None,
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
            metas=metas_de(configuracion),
            rama=detectar_rama(ruta),
        )
        resumen.run_id = rutas.run_id
        resumen.carpeta = str(rutas.carpeta)

    if resumen.run_id is not None and almacen.existe():
        huellas_objetivos = huellas_de_objetivos(ruta)
        # La spec de cada objetivo es la del plan del módulo (completa aunque en Humo se
        # haya probado un solo caso) con el perfil con que se creó (#75).
        guardadas = {
            (plan["modulo"], contrato["objetivo"]): (
                contrato,
                plan["perfiles"].get(contrato["objetivo"]),
            )
            for plan in planes_specs
            for contrato in plan["contratos"]
        }
        for resultado in resultados:
            for objetivo in resultado.objetivos:
                if objetivo.contrato is None:
                    continue
                archivo = None
                if objetivo.decision == "accept" and objetivo.codigo:
                    spec_id = id_de_spec(resultado.modulo, objetivo.objetivo)
                    archivo = nombre_prueba(spec_id)
                    almacen.guardar_prueba_aprobada(archivo, objetivo.codigo)
                huella = huellas_objetivos.get((resultado.modulo, objetivo.objetivo))
                contrato, perfil_spec = guardadas.get(
                    (resultado.modulo, objetivo.objetivo), (objetivo.contrato, None)
                )
                almacen.guardar_spec(
                    contrato,
                    resumen.run_id,
                    archivo,
                    huella_objetivo=huella,
                    perfil=perfil_spec,
                )
        registros = []
        for plan in planes_specs:
            guardado = almacen.guardar_plan_modulo(
                plan["modulo"],
                plan["huella"],
                plan["contratos"],
                resumen.run_id,
                plan["accion"],
                perfiles=plan["perfiles"],
            )
            registros.append(
                {
                    "modulo": guardado["modulo"],
                    "huella": guardado["huella"],
                    "run_origen": guardado["run_origen"],
                    "estado": guardado["ultima_accion"],
                }
            )
        if registros:
            try:
                almacen.registrar_specs_run(resumen.run_id, registros)
            except ErrorAlmacen as error:
                _registro.warning(
                    "No se pudo registrar las specs en la corrida %s: %s",
                    resumen.run_id,
                    error,
                )
    _cerrar_run(almacen, resumen, tipos)


def _objetivos_de(modulo: dict[str, Any]) -> set[str]:
    """Funciones y endpoints planificables que la selección dejó en el módulo.

    Un endpoint sin ruta resuelta no se planifica (el Planner lo omite), así que no
    cuenta como faltante en la spec.
    """
    funciones = {f["nombre"] for f in modulo.get("funciones") or []}
    endpoints = {
        e["objetivo"]
        for e in modulo.get("endpoints") or []
        if e.get("objetivo") and e.get("resuelta", True)
    }
    return funciones | endpoints


def _combinar_plan(
    guardados: list[dict[str, Any]], nuevos: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Plan a guardar cuando la huella no cambió.

    Los contratos de esta corrida reemplazan a los guardados del mismo objetivo; los
    de objetivos que no se eligieron se conservan para reutilizarlos más adelante.
    """
    por_objetivo = {c["objetivo"]: c for c in nuevos}
    combinado = [por_objetivo.pop(c["objetivo"], c) for c in guardados]
    return [*combinado, *por_objetivo.values()]


def _existe_plan_modulo(almacen: AlmacenProyecto, modulo: str) -> bool:
    """Distingue la primera generación de una regeneración por cambio de huella."""
    try:
        almacen.leer_plan_modulo(modulo)
    except ErrorAlmacen:
        return False
    return True


def metas_de(configuracion: Any) -> dict[str, float]:
    """Metas de la carta (`[umbrales]`) y tope de gasto por corrida de config.toml."""
    umbrales = configuracion.umbrales
    return {
        "pass_rate_min": umbrales.pass_rate_min,
        "cobertura_lineas_min": umbrales.cobertura_lineas_min,
        "iteraciones_promedio_max": umbrales.iteraciones_promedio_max,
        "tope_por_corrida_usd": configuracion.presupuesto.tope_por_corrida_usd,
    }


def _con_fuente(ruta: Path, modulo: dict[str, Any]) -> dict[str, Any]:
    """Agrega el código del módulo si tiene endpoints: el Planner recorta sus rutas."""
    if not modulo.get("endpoints"):
        return modulo
    try:
        fuente = (ruta / modulo["ruta"]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return modulo
    return {**modulo, "fuente": fuente}


def _cerrar_run(
    almacen: AlmacenProyecto,
    resumen: ResumenCorrida,
    tipos: list[str] | None = None,
) -> None:
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
            + resumen.sin_veredicto
            + resumen.requieren_corrida_nueva,
            tipos_prueba=tipos or ["funcion"],
        )
    except Exception as error:  # noqa: BLE001 — run.json dañado: no es motivo de fallo
        _registro.warning(
            "No se pudo cerrar el run.json de %s: %s", resumen.run_id, error
        )


def _texto_error(error: Exception) -> str:
    if isinstance(error, ErrorCorrida):
        return str(error)
    return f"{type(error).__name__}: {error}"

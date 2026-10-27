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
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import TimeoutError as EsperaAgotada
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.agents import GeneratorAgent, PlannerAgent, ReviewerAgent
from qagent.agents.planner import contrato_humo, contrato_sin_triviales
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
    LIMITE_TOKENS,
    FalloControlado,
    Orquestador,
    PlanModulo,
    ResultadoCorrida,
    timeout_paso_para,
)
from qagent.orchestrator.regresion import huellas_de_objetivos
from qagent.orchestrator.tiempos import iso_utc, segundos
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
    tokens_reales: int = 0
    tokens_estimados: int = 0
    costo_usd: float = 0.0
    carpeta: str | None = None
    duracion_s: float = 0.0
    requieren_corrida_nueva: int = 0
    inicio: str | None = None
    fin: str | None = None
    duracion_etapas: dict[str, float] = field(default_factory=dict)
    cancelada: bool = False
    total_seleccionados: int = 0
    total_elegibles: int = 0
    total_procesados: int = 0
    total_pendientes: int = 0
    tipo_terminacion: str = "completada"
    objetivos_omitidos: int = 0

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
    reloj: Callable[[], float] = time.monotonic,
    ahora: Callable[[], str] = iso_utc,
    cancelado: Callable[[], bool] | None = None,
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
        reloj: reloj monotónico inyectable para medir duraciones (#115).
        ahora: marca UTC ISO inyectable para inicio y fin (#115).
        cancelado: consulta inyectable para detener la corrida de forma controlada.
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
            reloj=reloj,
            ahora=ahora,
            cancelado=cancelado,
        )

    inicio = reloj()
    inicio_utc = ahora()
    ruta = Path(ruta_proyecto)
    progreso = {"hechos": 0, "total": 0}
    estimados_por_modulo: dict[str, int] = {}
    planificados_por_modulo: dict[str, int] = {}

    # #148: la construcción del entorno aislado avisa desde otro hilo.
    candado = threading.RLock()

    def emitir(evento: Evento) -> None:
        with candado:
            _emitir(evento)

    def _emitir(evento: Evento) -> None:
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
            datos_evento = dict(evento.datos or {})
            if "tracker" in locals():
                datos_evento.setdefault("tokens_acumulados", tracker.total_tokens)
                datos_evento.setdefault("tokens_reales", tracker.total_tokens_reales)
                datos_evento.setdefault(
                    "tokens_estimados", tracker.total_tokens_estimados
                )
            if "tope_tokens" in locals() and tope_tokens:
                datos_evento.setdefault("limite_tokens", tope_tokens)
            al_evento(
                {
                    **evento.a_dict(),
                    "datos": datos_evento,
                    "progreso": dict(progreso),
                    "tokens_acumulados": tracker.total_tokens
                    if "tracker" in locals()
                    else 0,
                    "tokens_reales": tracker.total_tokens_reales
                    if "tracker" in locals()
                    else 0,
                    "tokens_estimados": tracker.total_tokens_estimados
                    if "tracker" in locals()
                    else 0,
                    "limite_tokens": tope_tokens if "tope_tokens" in locals() else None,
                    "inicio_corrida": inicio_utc,
                    "transcurrido_s": segundos(inicio, reloj()),
                    "etapas_s": dict(resumen.duracion_etapas),
                }
            )

    def avisar(mensaje: str, tipo: str = "agente", archivo: str | None = None) -> None:
        emitir(Evento("orquestador", archivo, None, mensaje, "preparacion", tipo))

    almacen = AlmacenProyecto(ruta)
    resumen = ResumenCorrida(
        run_id=run_id,
        estado=FIN,
        motivo=None,
        total_funciones=0,
        inicio=inicio_utc,
    )
    resultados: list[ResultadoCorrida] = []
    tipos: list[str] = ["funcion"]
    #: Segundos construyendo el entorno aislado y los que la corrida lo esperó (#148).
    etapas_entorno: dict[str, float] = {}
    try:
        if not ruta.is_dir():
            raise ErrorCorrida(f"La carpeta del proyecto no existe: {ruta}")
        if cancelado is not None and cancelado():
            resumen.estado = FALLO
            resumen.cancelada = True
            resumen.tipo_terminacion = "cancelada"
            resumen.motivo = "Corrida cancelada por el usuario."
            avisar(resumen.motivo, "fallo")
            _cerrar_run(almacen, resumen, tipos)
            return resumen
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
        resumen.total_seleccionados = n_funciones + n_endpoints
        progreso["total"] = resumen.total_funciones = resumen.total_seleccionados
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
        # #148: construir la imagen puede tardar minutos (APP-RF: 11 de 13). Se
        # construye en segundo plano mientras el Planner, que no necesita Docker,
        # planifica los módulos; su avance va al Monitor.
        if preparar_imagen is not None:
            preparar = preparar_imagen
        else:

            def preparar(ruta_imagen: Path) -> str:
                return _preparar_imagen(
                    ruta_imagen,
                    avanzar=avance_limitado(avisar),
                    avisar_faltante=lambda mensaje: avisar(mensaje, "aviso"),
                )

        entorno = EntornoEnPreparacion(lambda: preparar(ruta), reloj)

        bus = BusEventos()
        bus.suscribir(emitir)
        limites = getattr(configuracion, "sandbox", LIMITES_POR_DEFECTO)
        tope_tokens = getattr(configuracion.presupuesto, "max_tokens_por_corrida", None)
        opciones: dict[str, Any] = {
            "max_intentos": configuracion.max_intentos,
            "timeout_paso_s": timeout_paso_s
            if timeout_paso_s is not None
            else timeout_paso_para(limites.timeout_s),
            "reloj": reloj,
            "ahora": ahora,
            "limite_tokens": tope_tokens,
            "cancelado": cancelado,
        }
        orquestador = Orquestador(
            PlannerAgent(
                clientes["planner"], tracker, es_simulado=simulado, perfil=perfil
            ),
            GeneratorAgent(
                clientes["generator"], tracker, es_simulado=simulado, ruta_proyecto=ruta
            ),
            # El Reviewer necesita la imagen: se asigna cuando el entorno está listo.
            _ReviewerSinEntorno(),
            bus=bus,
            tracker=tracker,
            **opciones,
        )

        planes_specs: list[dict[str, Any]] = []
        # #70: con las huellas, el Mutation Score de esta corrida queda guardado para
        # reutilizarlo al repetir las pruebas sin cambios.
        huellas = huellas_de_objetivos(ruta) if perfil == PERFIL_PROFUNDO else None
        tope = configuracion.presupuesto.tope_por_corrida_usd

        def preparar_modulo(modulo: dict[str, Any]) -> _ModuloPreparado:
            """Decide si se reutiliza la spec vigente y planifica el módulo."""
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
                # #138: una spec anterior puede traer casos triviales de TypeError; sin
                # ellos, la que queda vacía se vuelve a planificar.
                elegidos = [h for h in map(contrato_sin_triviales, elegidos) if h]
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
                plan = orquestador.planificar(modulo, plan_reutilizado=elegidos)
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
                plan = orquestador.planificar(modulo)
            return _ModuloPreparado(plan, accion, plan_guardado, perfiles, completos)

        def sin_recursos() -> bool:
            return tracker.total_costo_usd >= tope or (
                tope_tokens is not None and tracker.total_tokens >= tope_tokens
            )

        # #148: mientras se construye el entorno se planifican los módulos en orden.
        # Los cortes por cancelación o presupuesto se avisan después, en el bucle de
        # ejecución, al llegar a ese módulo.
        preparados: dict[str, _ModuloPreparado] = {}
        for modulo in modulos:
            if (
                entorno.listo()
                or (cancelado is not None and cancelado())
                or sin_recursos()
            ):
                break
            preparado = preparar_modulo(modulo)
            preparados[modulo["ruta"]] = preparado
            if preparado.plan.error is not None:
                break  # un error de la cuenta se repetiría en los demás módulos

        inicio_espera = reloj()
        imagen = entorno.esperar(cancelado)
        etapas_entorno.update(
            {
                "entorno": entorno.duracion_s,
                "espera_entorno": segundos(inicio_espera, reloj()),
            }
        )
        if imagen is not None:
            orquestador.reviewer = ReviewerAgent(
                tracker,
                ruta,
                imagen,
                cliente=clientes["reviewer"],
                ejecutor=ejecutor,
                es_simulado=simulado,
                limites=limites,
            )

        for modulo in modulos:
            if cancelado is not None and cancelado():
                resumen.estado = FALLO
                resumen.cancelada = True
                resumen.tipo_terminacion = "cancelada"
                resumen.motivo = "Corrida cancelada por el usuario."
                avisar(resumen.motivo, "fallo")
                break
            if tracker.total_costo_usd >= tope:
                resumen.estado = FALLO
                resumen.tipo_terminacion = "limitada_recursos"
                resumen.motivo = (
                    f"Se alcanzó el tope de gasto por corrida (US$ {tope:.2f}); "
                    "los módulos restantes no se revisaron."
                )
                avisar(resumen.motivo, "fallo")
                break
            if tope_tokens is not None and tracker.total_tokens >= tope_tokens:
                resumen.estado = FALLO
                resumen.tipo_terminacion = "limitada_recursos"
                resumen.motivo = (
                    f"Se alcanzó el presupuesto de tokens por corrida ({tope_tokens} tokens); "
                    "los módulos restantes no se revisaron."
                )
                avisar(resumen.motivo, "fallo")
                break
            preparado = preparados.pop(modulo["ruta"], None) or preparar_modulo(modulo)
            accion, plan_guardado = preparado.accion, preparado.plan_guardado
            perfiles, completos = preparado.perfiles, preparado.completos
            resultado = orquestador.ejecutar(modulo, plan_previo=preparado.plan)
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
                contratos_validos_spec = [
                    c for c in contratos if contracts.es_valido(contracts.PLANNER, c)
                ]
                if contratos_validos_spec:
                    planes_specs.append(
                        {
                            "modulo": modulo["ruta"],
                            "huella": modulo["huella"],
                            "contratos": contratos_validos_spec,
                            "accion": accion,
                            "perfiles": {
                                c["objetivo"]: perfiles[c["objetivo"]]
                                for c in contratos_validos_spec
                                if c["objetivo"] in perfiles
                            },
                        }
                    )
            if resultado.estado_final.value == FALLO and resumen.motivo is None:
                resumen.estado = FALLO
                resumen.motivo = f"{resultado.modulo}: {resultado.motivo_fallo}"
                if (cancelado is not None and cancelado()) or any(
                    p in (resultado.motivo_fallo or "").lower()
                    for p in ("cancelad", "por el usuario")
                ):
                    resumen.cancelada = True
                    resumen.tipo_terminacion = "cancelada"
            if resultado.error_global:
                # FIX-02: falta de crédito o clave rechazada; los demás módulos
                # fallarían igual, así que no se sigue.
                resumen.tipo_terminacion = "detenida_error"
                avisar(
                    "Error de la cuenta del proveedor de IA: no se procesarán más "
                    "módulos.",
                    "fallo",
                )
                break
            if _registrar_limite_tokens(resumen, resultado, tope_tokens):
                avisar(resumen.motivo, "fallo")
                break

        _contar(resumen, resultados, tracker)
        resumen.duracion_etapas.update(etapas_entorno)
        if (
            resumen.estado == FIN
            and resumen.sin_veredicto > 0
            and resumen.motivo is None
        ):
            resumen.motivo = (
                f"Corrida completada con errores: {resumen.sin_veredicto} objetivo(s) "
                "quedaron sin veredicto."
            )
        if not resumen.tipo_terminacion or resumen.tipo_terminacion == "completada":
            resumen.tipo_terminacion = tipo_terminacion(resumen)
            if resumen.tipo_terminacion == "cancelada":
                resumen.cancelada = True
        progreso["total"] = resumen.total_seleccionados or resumen.total_funciones
        resumen.duracion_s = segundos(inicio, reloj())
        resumen.fin = ahora()
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
        if "tracker" in locals():
            _contar(resumen, resultados, tracker)
            resumen.duracion_etapas.update(etapas_entorno)
        else:
            resumen.total_elegibles = max(
                0, resumen.total_seleccionados - resumen.objetivos_omitidos
            )
            resumen.total_pendientes = max(
                0, resumen.total_elegibles - resumen.total_procesados
            )
        resumen.estado = FALLO
        resumen.tipo_terminacion = "detenida_error"
        resumen.motivo = resumen.motivo or _texto_error(error)
        resumen.duracion_s = segundos(inicio, reloj())
        resumen.fin = ahora()
        avisar(f"Corrida detenida: {resumen.motivo}", "fallo")
        _cerrar_run(almacen, resumen, tipos)

    resumen.duracion_s = resumen.duracion_s or segundos(inicio, reloj())
    resumen.fin = resumen.fin or ahora()
    partes_terminacion = [
        f"{resumen.aceptadas} aceptada(s)",
        f"{resumen.bugs_detectados} bug(s) detectado(s)",
        f"{resumen.estancadas} estancada(s)",
    ]
    if resumen.sin_veredicto:
        partes_terminacion.append(f"{resumen.sin_veredicto} sin veredicto")
    if resumen.objetivos_omitidos:
        partes_terminacion.append(f"{resumen.objetivos_omitidos} sin probar")
    texto_resumen = ", ".join(partes_terminacion)

    if resumen.cancelada or (resumen.motivo and "cancelad" in resumen.motivo.lower()):
        titulo_fin = "Corrida cancelada"
    elif resumen.estado == FIN:
        titulo_fin = (
            "Corrida completada con errores"
            if resumen.sin_veredicto
            else "Corrida terminada"
        )
    else:
        titulo_fin = "Corrida detenida"

    avisar(f"{titulo_fin}: {texto_resumen}", "fin")
    return resumen


class ErrorCorrida(RuntimeError):
    """La corrida no puede seguir (motivo legible para la interfaz)."""


#: Cada cuánto se revisa la cancelación mientras se espera el entorno aislado (#148).
INTERVALO_ESPERA_ENTORNO_S = 0.2


class EntornoEnPreparacion:
    """Construye la imagen del sandbox en segundo plano mientras se planifica (#148).

    Usa un hilo daemon: si el usuario cancela o cierra la app mientras `docker build`
    sigue, el proceso no queda esperando a que termine.
    """

    def __init__(
        self,
        preparar: Callable[[], str],
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._reloj = reloj
        #: Segundos que tomó preparar la imagen (etapa `entorno`).
        self.duracion_s = 0.0
        self._futuro: Future[str] = Future()
        threading.Thread(
            target=self._preparar, args=(preparar,), name="qagent-entorno", daemon=True
        ).start()

    def _preparar(self, preparar: Callable[[], str]) -> None:
        inicio = self._reloj()
        try:
            imagen = preparar()
        except BaseException as error:  # noqa: BLE001 — se relanza en `esperar`
            self.duracion_s = segundos(inicio, self._reloj())
            self._futuro.set_exception(error)
        else:
            self.duracion_s = segundos(inicio, self._reloj())
            self._futuro.set_result(imagen)

    def listo(self) -> bool:
        """True cuando la imagen está lista o su preparación falló."""
        return self._futuro.done()

    def esperar(self, cancelado: Callable[[], bool] | None = None) -> str | None:
        """Espera la imagen; None si el usuario cancela mientras tanto.

        Si la preparación falló, relanza su error.
        """
        while True:
            try:
                return self._futuro.result(timeout=INTERVALO_ESPERA_ENTORNO_S)
            except EsperaAgotada:
                if cancelado is not None and cancelado():
                    return None


class _ReviewerSinEntorno:
    """Reviewer provisional mientras se construye el entorno aislado (#148).

    La corrida lo reemplaza por el `ReviewerAgent` real antes de ejecutar un módulo;
    si se llegara a usar, el módulo termina en fallo controlado.
    """

    def revisar(self, *_args: Any) -> dict[str, Any]:
        raise FalloControlado("El entorno aislado todavía no está listo")


@dataclass
class _ModuloPreparado:
    """Plan de un módulo y lo que la corrida necesita para guardar su spec (#148)."""

    plan: PlanModulo
    accion: str
    plan_guardado: dict[str, Any] | None
    perfiles: dict[str, str]
    completos: dict[str, dict[str, Any]]


def tipo_terminacion(resumen: ResumenCorrida) -> str:
    """Cómo terminó una corrida, a partir de su resumen ya contado.

    Los objetivos omitidos (sin resultado esperado verificable o con ruta sin
    resolver) no la vuelven «detenida»: solo los pendientes, que son lo que una
    detención dejó sin revisar (`_contar`).
    """
    motivo = (resumen.motivo or "").lower()
    if resumen.cancelada or any(p in motivo for p in ("cancelad", "por el usuario")):
        return "cancelada"
    if any(p in motivo for p in ("token", "presupuesto", "gasto", "tiempo")):
        return "limitada_recursos"
    if resumen.estado == FALLO:
        return "detenida_error"
    if resumen.sin_veredicto > 0 or resumen.estancadas > 0:
        return "completada_con_errores"
    if resumen.total_pendientes > 0:
        return "detenida_error"
    return "completada"


def _registrar_limite_tokens(
    resumen: ResumenCorrida,
    resultado: ResultadoCorrida,
    limite_tokens: int | None,
) -> bool:
    """Marca como detenida una corrida cuyo objetivo agotó el presupuesto."""
    if not any(
        objetivo.motivo_estancado == LIMITE_TOKENS for objetivo in resultado.objetivos
    ):
        return False
    resumen.estado = FALLO
    resumen.tipo_terminacion = "limitada_recursos"
    resumen.motivo = (
        f"Se alcanzó el presupuesto de tokens por corrida ({limite_tokens} tokens); "
        "no se procesarán más objetivos."
    )
    return True


# --- Partes de la corrida ---------------------------------------------------------


def _preparar_imagen(
    ruta: Path,
    avanzar: Callable[[str], None] | None = None,
    avisar_faltante: Callable[[str], None] | None = None,
) -> str:
    """Imagen del sandbox del proyecto; construye la imagen base si todavía no existe.

    Sobre la imagen de dependencias se comprueba el entorno e instala las librerías del
    sistema que faltan (issue 142). Las que no se pudieron resolver se avisan.

    Args:
        ruta: carpeta del proyecto.
        avanzar: recibe el avance de la construcción en textos para personas.
        avisar_faltante: recibe un aviso por cada librería del sistema sin resolver.
    """
    from qagent.sandbox import (
        ImagenNoEncontrada,
        construir_imagen_base,
        preparar_imagen,
    )
    from qagent.sandbox.cliente import obtener_cliente
    from qagent.sandbox.librerias import asegurar_librerias_sistema
    from qagent.sandbox.limpieza import registrar_uso

    try:
        imagen = preparar_imagen(ruta, avanzar=avanzar)
    except ImagenNoEncontrada:
        construir_imagen_base(avanzar=avanzar)  # una sola vez por PC; necesita internet
        imagen = preparar_imagen(ruta, avanzar=avanzar)
    # Las imágenes req- sin uso se borran al abrir la app. Se anota también la de
    # dependencias: la final se construye encima y reinstalar pip puede tardar minutos.
    registrar_uso(imagen)
    try:
        entorno = asegurar_librerias_sistema(imagen, obtener_cliente(), avanzar)
    except Exception as error:  # noqa: BLE001 — comprobar el entorno nunca frena la corrida
        _registro.warning("No se comprobaron las librerías del sistema: %s", error)
        return imagen
    if entorno.imagen != imagen:
        registrar_uso(entorno.imagen)
    for faltante in entorno.faltantes:
        if avisar_faltante is not None:
            avisar_faltante(faltante["mensaje"])
    return entorno.imagen


#: Segundos mínimos entre dos avisos de avance de la construcción de la imagen.
INTERVALO_AVANCE_S = 2.0


def avance_limitado(
    avisar: Callable[[str], None],
    intervalo_s: float = INTERVALO_AVANCE_S,
    reloj: Callable[[], float] = time.monotonic,
) -> Callable[[str], None]:
    """Reenvía el avance de la construcción a `avisar`, sin saturar el Monitor.

    Las fases (empezar a instalar, terminar, comprobar las librerías del sistema)
    siempre pasan; los pasos de pip («Descargando torch…») como mucho uno cada
    `intervalo_s`. Un texto igual al anterior no se repite.
    """
    from qagent.sandbox.imagen import AVISO_BASE, AVISO_DEPENDENCIAS, AVISO_LISTO
    from qagent.sandbox.librerias import (
        AVISO_COMPROBANDO,
        AVISO_INSTALANDO,
        AVISO_LISTAS,
    )

    fases = {
        AVISO_BASE,
        AVISO_DEPENDENCIAS,
        AVISO_LISTO,
        AVISO_COMPROBANDO,
        AVISO_LISTAS,
    }
    estado: dict[str, Any] = {"ultimo": None, "momento": None}

    def avanzar(texto: str) -> None:
        if texto == estado["ultimo"]:
            return
        ahora = reloj()
        reciente = (
            estado["momento"] is not None and ahora - estado["momento"] < intervalo_s
        )
        es_fase = texto in fases or texto.startswith(AVISO_INSTALANDO)  # issue 142
        if reciente and not es_fase:
            return
        estado["ultimo"], estado["momento"] = texto, ahora
        avisar(texto)

    return avanzar


def _contar(
    resumen: ResumenCorrida,
    resultados: list[ResultadoCorrida],
    tracker: TokenTracker,
) -> None:
    decisiones = [o.decision for r in resultados for o in r.objetivos]
    resumen.total_procesados = len(decisiones)
    # Omitido (sin resultado esperado verificable o ruta sin resolver) no es pendiente:
    # pendiente es solo lo que una detención dejó sin revisar.
    resumen.objetivos_omitidos = sum(len(r.omitidos) for r in resultados)
    resumen.total_elegibles = max(
        0, resumen.total_seleccionados - resumen.objetivos_omitidos
    )
    resumen.total_pendientes = max(
        0,
        resumen.total_elegibles - resumen.total_procesados,
    )
    resumen.total_funciones = len(decisiones)
    resumen.aceptadas = decisiones.count("accept")
    resumen.bugs_detectados = decisiones.count("bug_detectado")
    resumen.estancadas = decisiones.count("stalled")
    resumen.sin_veredicto = decisiones.count(None)
    resumen.tokens = tracker.total_tokens
    resumen.tokens_reales = tracker.total_tokens_reales
    resumen.tokens_estimados = tracker.total_tokens_estimados
    resumen.costo_usd = round(tracker.total_costo_usd, 8)
    etapas = {
        "planner": 0.0,
        "generator": 0.0,
        "reviewer": 0.0,
        "sandbox": 0.0,
        "pytest": 0.0,
    }
    for resultado in resultados:
        for etapa, segundos_etapa in (resultado.duracion_etapas or {}).items():
            etapas[etapa] = round(etapas.get(etapa, 0.0) + segundos_etapa, 3)
    resumen.duracion_etapas = etapas


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
            inicio=resumen.inicio,
            fin=resumen.fin,
            duracion_s=resumen.duracion_s,
            duracion_etapas=resumen.duracion_etapas,
            total_seleccionados=resumen.total_seleccionados,
            total_elegibles=resumen.total_elegibles,
            total_procesados=resumen.total_procesados,
            total_pendientes=resumen.total_pendientes,
            tipo_terminacion=resumen.tipo_terminacion,
            objetivos_omitidos=resumen.objetivos_omitidos,
            omitidos=[
                {"modulo": r.modulo, **omitido}
                for r in resultados
                for omitido in r.omitidos
            ],
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
                if contrato is not None and contracts.es_valido(
                    contracts.PLANNER, contrato
                ):
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


def metas_de(configuracion: Any) -> dict[str, Any]:
    """Metas de la carta (`[umbrales]`) y tope de gasto por corrida de config.toml."""
    umbrales = configuracion.umbrales
    metas: dict[str, Any] = {
        "pass_rate_min": umbrales.pass_rate_min,
        "cobertura_lineas_min": umbrales.cobertura_lineas_min,
        "iteraciones_promedio_max": umbrales.iteraciones_promedio_max,
        "tope_por_corrida_usd": configuracion.presupuesto.tope_por_corrida_usd,
    }
    tope_tokens = getattr(configuracion.presupuesto, "max_tokens_por_corrida", None)
    if tope_tokens is not None:
        metas["tope_tokens_por_corrida"] = tope_tokens
    return metas


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
            duracion_s=resumen.duracion_s,
            total_seleccionados=resumen.total_seleccionados,
            total_elegibles=resumen.total_elegibles,
            total_procesados=resumen.total_procesados,
            total_pendientes=resumen.total_pendientes,
            objetivos_omitidos=resumen.objetivos_omitidos,
            tipo_terminacion=resumen.tipo_terminacion,
            motivo=resumen.motivo,
        )
    except Exception as error:  # noqa: BLE001 — run.json dañado: no es motivo de fallo
        _registro.warning(
            "No se pudo cerrar el run.json de %s: %s", resumen.run_id, error
        )


def _texto_error(error: Exception) -> str:
    if isinstance(error, ErrorCorrida):
        return str(error)
    return f"{type(error).__name__}: {error}"

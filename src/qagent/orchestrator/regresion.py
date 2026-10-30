"""Reejecucion sin IA de pruebas aprobadas (HU-25), con mutación opcional (#70)."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
import tokenize
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.agents.planner import contrato_sin_triviales
from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.proyecto import VERSION_HUELLA_OBJETIVO
from qagent.analysis.analyzer import calcular_huella
from qagent.lenguajes import REGISTRO, LanguageAdapter, adaptador_de_contrato
from qagent.llm.tracker import TokenTracker
from qagent.orchestrator.estados import Estado
from qagent.orchestrator.eventos import Evento
from qagent.orchestrator.mutacion import mutar_modulo
from qagent.orchestrator.orquestador import ResultadoCorrida, ResultadoObjetivo
from qagent.orchestrator.tiempos import (
    etapas_vacias,
    iso_utc,
    segundos,
    sumar_etapa,
)
from qagent.proyectos.proyecto_local import detectar_rama
from qagent.sandbox import LIMITES_POR_DEFECTO, clasificar_resultado, ejecutar_pruebas
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.storage import escribir_corrida
from qagent.storage.registro import PERFIL_REGRESION_PROFUNDA


def huellas_de_objetivos(raiz: str | Path) -> dict[tuple[str, str], str]:
    """Calcula la huella de cada función y endpoint sin importar código del usuario.

    Recorre los archivos fuente de los lenguajes con huellas disponibles
    (``es_fuente``, #168) y pide a su adaptador la huella de cada objetivo
    (``huellas_de_archivo``). Las specs guardadas con la huella anterior
    (``ast.dump``) se migran aquí mismo si su módulo no cambió (ver
    :func:`_migrar_huellas_guardadas`).
    """
    raiz = Path(raiz)
    resultado: dict[tuple[str, str], str] = {}
    ignorados = {"tests", "venv", "node_modules", "__pycache__"}
    adaptadores = [
        a
        for nombre in REGISTRO.lenguajes
        if (a := REGISTRO.adaptador_para(nombre)).completo or a.huellas_disponibles
    ]
    for ruta in sorted(raiz.rglob("*")):
        adaptador = _adaptador_de_archivo(adaptadores, ruta.name)
        if adaptador is None or not ruta.is_file():
            continue
        partes = ruta.relative_to(raiz).parts
        if any(p.startswith(".") or p in ignorados for p in partes[:-1]):
            continue
        relativa = ruta.relative_to(raiz).as_posix()
        try:
            fuente = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        huellas = adaptador.huellas_de_archivo(fuente, relativa)
        for objetivo, huella in (huellas or {}).items():
            resultado[(relativa, objetivo)] = huella
    _migrar_huellas_guardadas(raiz, resultado)
    return resultado


def _adaptadores_completos() -> list[LanguageAdapter]:
    """Adaptadores con los que se puede correr y repetir pruebas (#168)."""
    adaptadores = (REGISTRO.adaptador_para(nombre) for nombre in REGISTRO.lenguajes)
    return [a for a in adaptadores if a.completo]


def _adaptador_de_archivo(
    adaptadores: list[LanguageAdapter], nombre: str
) -> LanguageAdapter | None:
    """El adaptador cuyo lenguaje tiene a `nombre` como archivo fuente."""
    return next((a for a in adaptadores if a.es_fuente(nombre)), None)


def _migrar_huellas_guardadas(raiz: Path, huellas: dict[tuple[str, str], str]) -> None:
    """Pasa a la huella de tree-sitter las specs guardadas con la de ``ast.dump``.

    Una spec vieja sigue sirviendo si su módulo no cambió (misma huella de módulo
    que en su contrato): la función tampoco cambió. Si el módulo cambió, la spec se
    queda como está y la función se trata como modificada, igual que antes.
    """
    almacen = AlmacenProyecto(raiz)
    huellas_modulo: dict[str, str | None] = {}
    for spec in almacen.listar_specs():
        if spec.get("version_huella_objetivo", 1) == VERSION_HUELLA_OBJETIVO:
            continue
        anterior = spec.get("huella_objetivo")
        contrato = spec["contrato"]
        nueva = huellas.get((contrato["modulo"], contrato["objetivo"]))
        if not anterior or nueva is None:
            continue
        modulo = contrato["modulo"]
        if modulo not in huellas_modulo:
            try:
                with tokenize.open(raiz / modulo) as archivo:
                    huellas_modulo[modulo] = calcular_huella(archivo.read())
            except (OSError, SyntaxError, UnicodeDecodeError):
                huellas_modulo[modulo] = None
        if huellas_modulo[modulo] == contrato.get("huella"):
            almacen.migrar_huella_objetivo(spec["id"], anterior, nueva)


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
            contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)
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


def _contrato_para_regresion(spec: dict[str, Any]) -> dict[str, Any] | None:
    """Contrato guardado sin casos triviales de firma (#149).

    Reutiliza el mismo detector determinista de #138. No inspecciona el texto del
    test, no ejecuta código del proyecto y no modifica la spec persistida.
    """
    return contrato_sin_triviales(spec["contrato"])


def _omision_typeerror_trivial(spec: dict[str, Any]) -> dict[str, str]:
    """Traza visible de una prueba histórica excluida, sin rutas absolutas."""
    contrato = spec["contrato"]
    archivo = spec["archivo_prueba"]
    referencia = spec.get("id") or contrato["objetivo"]
    return {
        "modulo": contrato["modulo"],
        "objetivo": contrato["objetivo"],
        "tipo": contrato["tipo"],
        "motivo": (
            "Requiere corrida nueva: la prueba guardada "
            f"{archivo} (spec {referencia}) solo comprueba un TypeError provocado "
            "por argumentos incorrectos y no ejercita el cuerpo de la función. "
            "El archivo se conservó sin cambios."
        ),
    }


def objetivos_repetibles(ruta_proyecto: str | Path) -> list[dict[str, str]]:
    """Objetivos cuya prueba aprobada guardada se puede repetir hoy (#70).

    Son los de una spec vigente, con su archivo de prueba presente y la misma huella
    AST que cuando se aprobó. La Configuración los usa para contar las funciones
    prioritarias que se pueden profundizar al repetir pruebas guardadas.
    """
    raiz = Path(ruta_proyecto)
    almacen = AlmacenProyecto(raiz)
    huellas = huellas_de_objetivos(raiz)
    repetibles = []
    for spec in _specs_aprobadas(almacen):
        contrato = _contrato_para_regresion(spec)
        if contrato is None:
            continue
        clave = (contrato["modulo"], contrato["objetivo"])
        esperada = spec.get("huella_objetivo")
        if (
            spec.get("_motivo_regresion")
            or not esperada
            or huellas.get(clave) != esperada
        ):
            continue
        if not (almacen.carpeta_tests / spec["archivo_prueba"]).is_file():
            continue
        repetibles.append({"modulo": clave[0], "objetivo": clave[1]})
    return repetibles


def funciones_criticas_repetibles(
    ruta_proyecto: str | Path,
    seleccion: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Funciones críticas seleccionadas aptas para `reg_deep` (#150).

    La elegibilidad reutiliza :func:`objetivos_repetibles`, incluida la exclusión de
    contratos triviales de #149. Los endpoints no habilitan esta opción de Preparar.
    Una selección ausente o incompleta se considera no elegible.
    """
    if not seleccion:
        return []
    criticas = {
        (entrada.get("ruta"), objetivo)
        for entrada in seleccion
        if isinstance(entrada, dict)
        for objetivo in (entrada.get("criticas") or [])
        if isinstance(objetivo, str)
    }
    if not criticas:
        return []
    tipos_funcion = {
        (contrato["modulo"], contrato["objetivo"])
        for spec in _specs_aprobadas(AlmacenProyecto(ruta_proyecto))
        if (contrato := _contrato_para_regresion(spec)) is not None
        and contrato["tipo"] == "funcion"
    }
    return [
        objetivo
        for objetivo in objetivos_repetibles(ruta_proyecto)
        if (objetivo["modulo"], objetivo["objetivo"]) in criticas & tipos_funcion
    ]


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
    reloj: Any = time.monotonic,
    ahora: Any = iso_utc,
    cancelado: Any = None,
) -> Any:
    """Reejecuta una vez cada prueba aprobada vigente; nunca crea clientes LLM.

    Con el perfil `reg_deep` (#70), al final aplica mutmut a las funciones críticas
    cuya prueba guardada volvió a pasar, sin IA. Las críticas son las marcadas en la
    Vista previa (`criticas` de la selección, HU-06); sin selección, las del contrato
    guardado.
    """
    from qagent.orchestrator.corrida import (
        ResumenCorrida,
        _cerrar_run,
        limites_del_lenguaje,
        metas_de,
    )

    inicio = reloj()
    inicio_utc = ahora()
    raiz = Path(ruta_proyecto)
    # #168: sin un doble de prueba, cada prueba corre con el comando de su adaptador
    # y los límites de `[sandbox]`.
    ejecutor_propio = None if ejecutor is ejecutar_pruebas else ejecutor
    almacen = AlmacenProyecto(raiz)
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
    huellas = huellas_de_objetivos(raiz)
    marcadas = (
        None
        if seleccion is None
        else {e["ruta"]: set(e.get("criticas") or []) for e in seleccion}
    )
    objetivo_inicio_reloj: float | None = None
    objetivo_inicio_utc: str | None = None

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
                    "inicio_corrida": inicio_utc,
                    "transcurrido_s": segundos(inicio, reloj()),
                    "etapas_s": dict(resumen.duracion_etapas),
                    "inicio_objetivo": objetivo_inicio_utc,
                    "duracion_objetivo_s": (
                        segundos(objetivo_inicio_reloj, reloj())
                        if objetivo_inicio_reloj is not None
                        else None
                    ),
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
        if not specs:
            raise RuntimeError("No hay pruebas aprobadas vigentes para Regresion.")
        resumen.total_seleccionados = len(specs)
        resumen.total_funciones = len(specs)
        omitidos: list[dict[str, str]] = []
        elegibles: list[dict[str, Any]] = []
        for spec in specs:
            contrato = _contrato_para_regresion(spec)
            if contrato is None:
                omitidos.append(_omision_typeerror_trivial(spec))
                continue
            elegibles.append(
                spec
                if contrato is spec["contrato"]
                else {**spec, "_contrato_regresion": contrato}
            )
        specs = elegibles
        resumen.objetivos_omitidos = len(omitidos)
        resumen.total_elegibles = len(specs)
        emitir("Regresion sin IA: comprobando huellas de pruebas aprobadas")
        for omitido in omitidos:
            emitir(
                f"{omitido['objetivo']}: {omitido['motivo']}",
                omitido["modulo"],
                "veredicto",
                {
                    "decision": "requiere_corrida_nueva",
                    "objetivo": omitido["objetivo"],
                },
            )
        imagen: str | None = None
        for spec in specs:
            if cancelado is not None and cancelado():
                resumen.estado = "fallo_controlado"
                resumen.cancelada = True
                resumen.tipo_terminacion = "cancelada"
                resumen.motivo = "Corrida detenida por el usuario."
                emitir(resumen.motivo, tipo="fallo")
                break
            contrato = spec.get("_contrato_regresion", spec["contrato"])
            modulo, objetivo = contrato["modulo"], contrato["objetivo"]
            objetivo_inicio_reloj = reloj()
            objetivo_inicio_utc = ahora()
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
                fin_objetivo = ahora()
                obj = ResultadoObjetivo(
                    objetivo,
                    es_critica(modulo, objetivo, contrato),
                    decision="requiere_corrida_nueva",
                    contrato=contrato,
                    codigo=codigo,
                    motivo_regresion=motivo,
                    inicio=objetivo_inicio_utc,
                    fin=fin_objetivo,
                    duracion_s=segundos(objetivo_inicio_reloj, reloj()),
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
                        inicio=objetivo_inicio_utc,
                        fin=fin_objetivo,
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
            t0 = reloj()
            with tempfile.TemporaryDirectory(prefix="qagent-regresion-") as temporal:
                shutil.copy2(ruta_test, Path(temporal) / ruta_test.name)
                adaptador = adaptador_de_contrato(contrato)
                modulo_cov = adaptador.modulo_cobertura(modulo)
                if ejecutor_propio is not None:
                    salida = ejecutor_propio(imagen, raiz, temporal, modulo_cov)
                else:
                    salida = ejecutar_comando_pruebas(
                        imagen,
                        adaptador.comando_pruebas(
                            modulo_cov,
                            contracts.normalizar_planner(contrato)["framework_pruebas"],
                        ),
                        raiz,
                        temporal,
                        leer_cobertura=adaptador.leer_cobertura,
                        archivo_informe=adaptador.entorno_sandbox().informe,
                        variables=adaptador.variables_pruebas(),
                        limites=limites_del_lenguaje(configuracion, adaptador.lenguaje),
                    )
            duracion_sandbox = segundos(t0, reloj())
            duracion_pytest = 0.0
            if salida.junit_xml:
                try:
                    duracion_pytest = adaptador.interpretar_resultados(
                        salida.junit_xml
                    )["duracion_s"]
                except ValueError:  # informe dañado (JUnitInvalido en Python)
                    duracion_pytest = 0.0
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
                duracion_s=segundos(objetivo_inicio_reloj, reloj()),
                reutilizada=True,
                motivo_estancado="limite_intentos" if decision == "stalled" else None,
                inicio=objetivo_inicio_utc,
                fin=ahora(),
                duracion_sandbox_s=duracion_sandbox,
                duracion_pytest_s=duracion_pytest,
                tiempos_intentos=[
                    {
                        "intento": 1,
                        "duracion_s": duracion_sandbox,
                        "generacion_s": 0.0,
                        "revision_s": 0.0,
                        "sandbox_s": duracion_sandbox,
                        "pytest_s": duracion_pytest,
                    }
                ],
            )
            dur_etapas = etapas_vacias()
            sumar_etapa(dur_etapas, "sandbox", duracion_sandbox)
            sumar_etapa(dur_etapas, "pytest", duracion_pytest)
            for etapa, valor in dur_etapas.items():
                sumar_etapa(resumen.duracion_etapas, etapa, valor)
            resultados.append(
                ResultadoCorrida(
                    modulo,
                    Estado.FIN,
                    None,
                    [obj],
                    [Estado.PLANIFICAR, Estado.FIN],
                    {},
                    obj.duracion_s,
                    inicio=obj.inicio,
                    fin=obj.fin,
                    duracion_etapas=dur_etapas,
                )
            )
            emitir(
                f"{objetivo}: {'aprobada' if decision == 'accept' else 'fallo detectado'}",
                modulo,
                "veredicto",
                {"decision": decision, "intento": 1, "objetivo": objetivo},
            )
        if perfil == PERFIL_REGRESION_PROFUNDA and resumen.estado == "fin":
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
        resumen.total_procesados = len(decisiones)
        resumen.total_pendientes = max(
            0, resumen.total_elegibles - resumen.total_procesados
        )
        resumen.total_funciones = len(decisiones)
        resumen.aceptadas = decisiones.count("accept")
        resumen.bugs_detectados = decisiones.count("bug_detectado")
        resumen.estancadas = decisiones.count("stalled")
        resumen.requieren_corrida_nueva = decisiones.count("requiere_corrida_nueva")
        if not resumen.tipo_terminacion or resumen.tipo_terminacion == "completada":
            if resumen.cancelada or (
                resumen.motivo and "cancelad" in resumen.motivo.lower()
            ):
                resumen.tipo_terminacion = "cancelada"
            elif resumen.estado == "fallo_controlado":
                resumen.tipo_terminacion = "detenida_error"
            elif resumen.sin_veredicto > 0 or resumen.estancadas > 0:
                resumen.tipo_terminacion = "completada_con_errores"
            elif resumen.total_pendientes > 0:
                resumen.tipo_terminacion = "detenida_error"
            else:
                resumen.tipo_terminacion = "completada"
        resumen.duracion_s = segundos(inicio, reloj())
        resumen.fin = ahora()
        rutas = escribir_corrida(
            raiz,
            resultados,
            tracker,
            configuracion.agentes,
            perfil,
            run_id=resumen.run_id,
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
            objetivos_omitidos=resumen.objetivos_omitidos,
            omitidos=omitidos,
        )
        resumen.run_id, resumen.carpeta = rutas.run_id, str(rutas.carpeta)
    except Exception as error:  # noqa: BLE001
        resumen.estado = "fallo_controlado"
        resumen.motivo = f"{type(error).__name__}: {error}"
        emitir(f"Regresion detenida: {resumen.motivo}", tipo="fallo")
    resumen.tokens = 0
    resumen.costo_usd = 0.0
    resumen.duracion_s = resumen.duracion_s or segundos(inicio, reloj())
    resumen.fin = resumen.fin or ahora()
    _cerrar_run(almacen, resumen, ["funcion", "endpoint"])
    emitir(
        f"Regresion terminada sin IA: {resumen.aceptadas} aprobadas, "
        f"{resumen.requieren_corrida_nueva} requieren corrida nueva, "
        f"{resumen.objetivos_omitidos} excluidas por TypeError trivial",
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
            con_endpoints=False,
            limites=getattr(configuracion, "sandbox", LIMITES_POR_DEFECTO),
        )


def _lineas_de(raiz: Path, modulo: str) -> list[dict[str, Any]]:
    """Línea de cada función de primer nivel del módulo, según su adaptador (#168)."""
    adaptador = _adaptador_de_archivo(_adaptadores_completos(), Path(modulo).name)
    if adaptador is None:
        return []
    return adaptador.funciones_de_modulo(raiz, modulo)


def _preparar_imagen(ruta: Path) -> str:
    from qagent.orchestrator.corrida import _preparar_imagen as preparar

    return preparar(ruta)

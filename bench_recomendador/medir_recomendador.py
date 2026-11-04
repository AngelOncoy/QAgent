"""Mide el Agente Recomendador con un LLM real frente a las reglas (SPK #201, ADR-011).

Es, junto con `bench_explicador/`, el único lugar de QAgent que llama a una API real:
lo corre una persona con su clave en `~/.qagent/.env`. Ninguna prueba de `tests/` lo
hace con la IA real. Uso, desde la raíz del repositorio:

    python bench_recomendador/medir_recomendador.py                      # todos los modelos
    python bench_recomendador/medir_recomendador.py --modelos planner reviewer
    python bench_recomendador/medir_recomendador.py --modelo deepseek/deepseek-flash
    python bench_recomendador/medir_recomendador.py --puntuar resultados/<fecha>

Por cada proyecto de `proyectos/` (solo funciones, FastAPI y mixto), cada modelo y
cada repetición, pide al Recomendador con IA (`RecomendadorIA`) que ordene y justifique
los tipos que propusieron las reglas (paso 1, 0 tokens, la línea base) y registra:

- tokens de entrada y salida, costo en USD y latencia (p50 y p95);
- si la respuesta se descartó (y por qué) o se usó;
- si la IA cambia el orden, omite tipos o cambia el motivo respecto de las reglas;
- que la entrada no lleva claves ni rutas absolutas.

También deja una planilla a ciegas (`revision/`) para que una persona del equipo diga
qué recomendación le resulta más útil en cada caso; `--puntuar` la junta y la revela.

Cada modelo candidato es el de un agente de `config.toml` (`config.local.toml` encima,
como en la aplicación) o, con `--modelo`, uno del catálogo `llm/proveedores.toml`. Se
usa como Recomendador: la clave se busca como para él
(`<PROVEEDOR>_API_KEY_RECOMENDADOR` o la del proveedor). Con `QAGENT_FAKE_LLM=1` todo
corre con la IA simulada (0 tokens) y las cifras salen marcadas [SIMULADO].

Deja en `resultados/<fecha>/` (o en `--salida`) `metricas.json`, `respuestas.json` y
`resumen.md`. Ninguno lleva claves: todo pasa por `sanitizar_secretos` al escribirse.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import random
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from qagent.agents.recomendador import (
    AGENTE,
    SinRecomendacionIA,
    proyectar,
    recomendar,
)
from qagent.agents.recomendador_ia import RecomendadorIA, entrada_ia
from qagent.config import carga as config_carga
from qagent.config import cargar_configuracion
from qagent.lenguajes import REGISTRO
from qagent.llm.fabrica import ConfiguracionLLMIncompleta, crear_cliente
from qagent.llm.precios import PrecioAgente
from qagent.llm.proveedores import catalogo
from qagent.llm.tracker import TokenTracker
from qagent.proyectos.vista_previa import generar_vista_previa
from qagent.storage.exportar_informe import sanitizar_secretos

CARPETA = Path(__file__).resolve().parent
PROYECTOS = CARPETA / "proyectos"
AGENTES_CANDIDATOS = ("planner", "generator", "reviewer", AGENTE)
REPETICIONES = 3
TIEMPO_MAXIMO_S = 30.0

#: Motivo de descarte según el texto de `SinRecomendacionIA`; la IA no se usó y quedaron
#: las reglas. El orden importa: gana el primero que coincide.
DESCARTES = (
    ("tiempo_agotado", ("tiempo agotado",)),
    ("error_llm", ("el LLM falló",)),
    ("tipo_no_permitido", ("no propusieron",)),
    ("sin_recomendaciones", ("ningún tipo",)),
    ("json_invalido", ("no es JSON", "«recomendaciones»")),
    ("contrato_invalido", ("contrato",)),
)

#: Rutas absolutas de Windows o de Unix que no deben viajar al LLM.
_RUTA_ABSOLUTA = re.compile(r"[A-Za-z]:[\\/]|(?<![\w.])/(?:home|Users|tmp|var|etc)/")

COLUMNAS_PLANILLA = (
    "caso",
    "proyecto",
    "hechos",
    "A",
    "B",
    "util_A",
    "util_B",
    "preferida",
    "comentario",
)


@dataclasses.dataclass
class Medicion:
    """Una llamada al Recomendador con IA sobre un proyecto."""

    proyecto: str
    modelo: str
    repeticion: int
    simulado: bool
    estimado: bool = False
    usada: bool = False
    descarte: str | None = None
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0
    latencia_s: float = 0.0
    orden_cambia: bool = False
    tipos_omitidos: list[str] = dataclasses.field(default_factory=list)
    motivo_cambia: bool = False
    tipos: list[str] = dataclasses.field(default_factory=list)
    recomendacion: dict[str, Any] | None = None
    respuesta_descartada: str | None = None


# --- Proyectos -----------------------------------------------------------------------


class _SoloReglas:
    """Recomendador nulo: la Vista previa devuelve las reglas sin consultar la config."""

    def __init__(self) -> None:
        self.tracker = TokenTracker()

    def recomendar(self, proyeccion: Any, reglas: dict[str, Any]) -> dict[str, Any]:
        return reglas


def leer_proyectos(carpeta: Path = PROYECTOS) -> dict[str, tuple[dict, dict]]:
    """Proyección y recomendación de las reglas de cada proyecto de muestra."""
    proyectos: dict[str, tuple[dict, dict]] = {}
    for ruta in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        vista = generar_vista_previa(ruta, recomendador=_SoloReglas())  # type: ignore[arg-type]
        proyeccion = proyectar(vista, REGISTRO.detectar(ruta))
        proyectos[ruta.name] = (proyeccion, recomendar(proyeccion))
    if not proyectos:
        raise SystemExit(f"No hay proyectos de muestra en {carpeta}.")
    return proyectos


# --- Modelos -------------------------------------------------------------------------


def candidatos(
    config: Any, agentes: list[str] | None = None
) -> list[tuple[str, PrecioAgente]]:
    """Modelos a medir: el de cada agente de `config.toml`, sin repetir modelo.

    Cada uno se usa como Recomendador (`agente = "recomendador"`), así que la clave se
    busca como la suya.
    """
    disponibles: dict[str, PrecioAgente] = dict(config.agentes)
    recomendador = getattr(config, "recomendador", None)
    if recomendador is not None and recomendador.precio is not None:
        disponibles[AGENTE] = recomendador.precio
    elegidos: list[tuple[str, PrecioAgente]] = []
    vistos: set[tuple[str, str]] = set()
    for agente in agentes or AGENTES_CANDIDATOS:
        precio = disponibles.get(agente)
        if precio is None:
            if agentes:
                raise SystemExit(f"No hay modelo para '{agente}' en config.toml.")
            continue
        clave = (precio.proveedor, precio.modelo)
        if clave in vistos:
            continue
        vistos.add(clave)
        elegidos.append((agente, dataclasses.replace(precio, agente=AGENTE)))
    return elegidos


def del_catalogo(modelos: list[str]) -> list[tuple[str, PrecioAgente]]:
    """Modelos `proveedor/modelo` del catálogo, con sus precios, usados como Recomendador."""
    proveedores = catalogo()
    elegidos: list[tuple[str, PrecioAgente]] = []
    for texto in dict.fromkeys(modelos):
        proveedor_id, _, modelo_id = texto.partition("/")
        proveedor = proveedores.get(proveedor_id)
        if proveedor is None or not proveedor.genera_texto:
            raise SystemExit(
                f"'{texto}': el proveedor '{proveedor_id}' no está en el catálogo. "
                f"Proveedores: {', '.join(sorted(proveedores))}."
            )
        modelo = proveedor.modelo(modelo_id)
        if modelo is None:
            ids = ", ".join(m.id for m in proveedor.modelos)
            raise SystemExit(
                f"'{texto}': {proveedor.nombre} no tiene el modelo '{modelo_id}' en el "
                f"catálogo. Modelos: {ids}."
            )
        if not modelo.precio_confirmado:
            raise SystemExit(
                f"'{texto}' no tiene precio en el catálogo: el costo saldría en 0."
            )
        elegidos.append(
            (
                "catálogo",
                PrecioAgente(
                    agente=AGENTE,
                    proveedor=proveedor.id,
                    modelo=modelo.id,
                    entrada_usd_m=modelo.entrada_usd_m,
                    salida_usd_m=modelo.salida_usd_m,
                ),
            )
        )
    return elegidos


# --- Medición ------------------------------------------------------------------------


def problemas_de_entrada(entrada: dict[str, Any], claves: Any = None) -> list[str]:
    """Rutas absolutas o claves en lo que se enviaría al LLM; vacío si está limpia."""
    texto = json.dumps(entrada, ensure_ascii=False)
    problemas = []
    if _RUTA_ABSOLUTA.search(texto):
        problemas.append("lleva una ruta absoluta")
    if sanitizar_secretos(texto, claves) != texto:
        problemas.append("lleva un texto con forma de clave")
    return problemas


def clasificar_descarte(motivo: str) -> str:
    """Motivo corto de descarte según el texto de `SinRecomendacionIA`."""
    for nombre, pistas in DESCARTES:
        if any(pista in motivo for pista in pistas):
            return nombre
    return "otro"


def _tipos(recomendacion: dict[str, Any]) -> list[str]:
    return [r["tipo_prueba"] for r in recomendacion["recomendaciones"]]


def medir_una(
    proyecto: str,
    proyeccion: dict[str, Any],
    reglas: dict[str, Any],
    modelo: str,
    repeticion: int,
    recomendador: RecomendadorIA,
) -> Medicion:
    """Una llamada: tokens, costo, latencia y diferencias con las reglas."""
    problemas = problemas_de_entrada(entrada_ia(proyeccion, reglas))
    if problemas:
        raise SystemExit(f"{proyecto}: la entrada al LLM {' y '.join(problemas)}.")
    medicion = Medicion(proyecto, modelo, repeticion, recomendador.es_simulado)
    inicio = time.perf_counter()
    try:
        recomendacion = recomendador.recomendar(proyeccion, reglas)
    except SinRecomendacionIA as error:
        medicion.descarte = clasificar_descarte(str(error))
        medicion.respuesta_descartada = str(error)
    else:
        medicion.usada = True
        medicion.recomendacion = recomendacion
        medicion.tipos = _tipos(recomendacion)
    medicion.latencia_s = time.perf_counter() - inicio

    consumo = recomendador.tracker.totales_por_agente().get(AGENTE)
    if consumo:
        medicion.tokens_entrada = consumo["prompt_tokens"]
        medicion.tokens_salida = consumo["completion_tokens"]
        medicion.costo_usd = consumo["costo_usd"]
        medicion.estimado = bool(consumo["tokens_estimados"])
    if medicion.usada:
        base = _tipos(reglas)
        medicion.tipos_omitidos = [t for t in base if t not in medicion.tipos]
        medicion.orden_cambia = medicion.tipos != [
            t for t in base if t in medicion.tipos
        ]
        motivos_reglas = {
            r["tipo_prueba"]: r["motivo"] for r in reglas["recomendaciones"]
        }
        medicion.motivo_cambia = any(
            r["motivo"] != motivos_reglas.get(r["tipo_prueba"])
            for r in medicion.recomendacion["recomendaciones"]  # type: ignore[index]
        )
    return medicion


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    if len(valores) == 1:
        return valores[0]
    return statistics.quantiles(valores, n=100, method="inclusive")[int(p) - 1]


def resumir(mediciones: list[Medicion]) -> dict[str, Any]:
    """Cifras de un conjunto de mediciones (de un modelo o de todo el proyecto)."""
    n = len(mediciones)
    if not n:
        return {"llamadas": 0}
    usadas = [m for m in mediciones if m.usada]
    latencias = [m.latencia_s for m in mediciones]
    return {
        "llamadas": n,
        "usadas": len(usadas),
        "descartes": dict(Counter(m.descarte for m in mediciones if m.descarte)),
        "tokens_entrada": sum(m.tokens_entrada for m in mediciones),
        "tokens_salida": sum(m.tokens_salida for m in mediciones),
        "costo_usd": round(sum(m.costo_usd for m in mediciones), 8),
        "costo_por_llamada_usd": round(sum(m.costo_usd for m in mediciones) / n, 8),
        "latencia_p50_s": round(_percentil(latencias, 50), 3),
        "latencia_p95_s": round(_percentil(latencias, 95), 3),
        "cambia_orden": sum(m.orden_cambia for m in usadas),
        "omite_tipos": sum(bool(m.tipos_omitidos) for m in usadas),
        "cambia_motivo": sum(m.motivo_cambia for m in usadas),
    }


# --- Planilla a ciegas ----------------------------------------------------------------


def _texto_recomendacion(recomendacion: dict[str, Any]) -> str:
    return "\n".join(
        f"{i}. {r['tipo_prueba']}: {r['motivo']}"
        for i, r in enumerate(recomendacion["recomendaciones"], 1)
    )


def _hechos(proyecto: str, proyeccion: dict[str, Any]) -> str:
    objetivos = proyeccion["objetivos"]
    funciones, endpoints = objetivos["funciones"], objetivos["endpoints"]
    return (
        f"Proyecto «{proyecto}»: {funciones['cantidad']} funciones públicas "
        f"({funciones['documentadas']} con tipos y documentación), "
        f"{endpoints['cantidad']} endpoints con ruta resuelta "
        f"({', '.join(endpoints['rutas_http']) or 'ninguno'}), "
        f"{proyeccion['objetivos_critical']} objetivos con decisiones."
    )


def exportar_planilla(
    carpeta: Path,
    proyectos: dict[str, tuple[dict, dict]],
    mediciones: list[Medicion],
    repeticion: int,
    semilla: int,
) -> int:
    """Planilla `revision/planilla.csv` y `revision/clave.json`; devuelve cuántas filas."""
    azar = random.Random(semilla)
    filas: list[dict[str, str]] = []
    clave: dict[str, dict[str, str]] = {}
    for m in mediciones:
        if m.repeticion != repeticion or not m.usada or m.recomendacion is None:
            continue
        proyeccion, reglas = proyectos[m.proyecto]
        opciones = [
            ("reglas", _texto_recomendacion(reglas)),
            (f"ia:{m.modelo}", _texto_recomendacion(m.recomendacion)),
        ]
        azar.shuffle(opciones)
        caso = f"{m.proyecto} · {m.modelo}"
        filas.append(
            {
                "caso": caso,
                "proyecto": m.proyecto,
                "hechos": _hechos(m.proyecto, proyeccion),
                "A": opciones[0][1],
                "B": opciones[1][1],
                "util_A": "",
                "util_B": "",
                "preferida": "",
                "comentario": "",
            }
        )
        clave[caso] = {"A": opciones[0][0], "B": opciones[1][0]}
    revision = carpeta / "revision"
    revision.mkdir(exist_ok=True)
    with open(revision / "planilla.csv", "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, COLUMNAS_PLANILLA, delimiter=";")
        escritor.writeheader()
        escritor.writerows(filas)
    (revision / "clave.json").write_text(
        json.dumps(clave, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return len(filas)


def puntuar(carpeta: Path) -> dict[str, Any]:
    """Junta las planillas llenadas, revela qué era cada opción y cuenta preferencias."""
    revision = carpeta / "revision"
    try:
        clave = json.loads((revision / "clave.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Falta {revision / 'clave.json'}: corre primero la medición.")
    planillas = sorted(revision.glob("planilla-*.csv"))
    if not planillas:
        raise SystemExit(
            f"No hay planillas llenadas en {revision} "
            "(copia planilla.csv como planilla-<nombre>.csv y complétala)."
        )
    utilidad: dict[str, list[int]] = {"reglas": [], "ia": []}
    preferencias: Counter[str] = Counter()
    por_caso: dict[str, list[str]] = {}
    for ruta in planillas:
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            for fila in csv.DictReader(f, delimiter=";"):
                caso = fila["caso"]
                lado = clave[caso]
                for letra in ("A", "B"):
                    puntos = (fila.get(f"util_{letra}") or "").strip()
                    if puntos not in {"1", "2", "3"}:
                        raise SystemExit(
                            f"{ruta.name}: falta un 1, 2 o 3 en util_{letra} de «{caso}»."
                        )
                    origen = "reglas" if lado[letra] == "reglas" else "ia"
                    utilidad[origen].append(int(puntos))
                elegida = (fila.get("preferida") or "").strip()
                if elegida not in {"A", "B", "igual"}:
                    raise SystemExit(
                        f"{ruta.name}: «preferida» de «{caso}» debe ser A, B o igual."
                    )
                if elegida == "igual":
                    resultado = "igual"
                else:
                    resultado = "reglas" if lado[elegida] == "reglas" else "ia"
                preferencias[resultado] += 1
                por_caso.setdefault(caso, []).append(resultado)
    datos = {
        "revisores": len(planillas),
        "utilidad_promedio": {
            k: round(statistics.mean(v), 2) if v else None for k, v in utilidad.items()
        },
        "preferencias": dict(preferencias),
        "por_caso": por_caso,
    }
    (carpeta / "revision" / "resultado.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (carpeta / "revision" / "resultado.md").write_text(
        resumen_revision(datos), encoding="utf-8"
    )
    return datos


def resumen_revision(datos: dict[str, Any]) -> str:
    util = datos["utilidad_promedio"]
    pref = datos["preferencias"]
    lineas = [
        "# Revisión a ciegas del Recomendador (SPK #201)",
        "",
        f"Revisores: {datos['revisores']}.",
        "",
        "| | Reglas | IA |",
        "|---|---|---|",
        f"| Utilidad promedio (1 a 3) | {util['reglas']} | {util['ia']} |",
        f"| Veces preferida | {pref.get('reglas', 0)} | {pref.get('ia', 0)} |",
        "",
        f"Empates («igual»): {pref.get('igual', 0)}.",
        "",
        "## Preferencia por caso",
        "",
    ]
    for caso, votos in datos["por_caso"].items():
        lineas.append(f"- {caso}: {', '.join(votos)}")
    return "\n".join(lineas) + "\n"


# --- Resumen -------------------------------------------------------------------------


def _etiqueta(simulado: bool, estimado: bool = False) -> str:
    return "[SIMULADO]" if simulado else "[ESTIMADO]" if estimado else "[MEDIDO]"


def resumen_md(datos: dict[str, Any]) -> str:
    """`resumen.md`: cifras por modelo y por proyecto, y las diferencias con las reglas."""
    simulado = datos["simulado"]
    lineas = [
        "# Medición del Agente Recomendador (SPK #201)",
        "",
        (
            f"Fecha: {datos['fecha']} · repeticiones: {datos['repeticiones']} · "
            f"tiempo máximo: {datos['tiempo_maximo_s']:g} s."
        ),
        "",
        "Línea base: las reglas del paso 1 (0 tokens, sin red, determinista).",
        "",
    ]
    if simulado:
        lineas += [
            (
                "> **[SIMULADO]** IA simulada (0 tokens): solo prueba que el script "
                "funciona. Estas cifras no sirven para decidir."
            ),
            "",
        ]
    for modelo, bloque in datos["modelos"].items():
        total = bloque["total"]
        etiqueta = _etiqueta(simulado, bloque["estimado"])
        lineas += [
            f"## {modelo}",
            "",
            (
                f"{etiqueta} Llamadas: {total['llamadas']} · usadas: {total['usadas']} · "
                f"descartes: {total['descartes'] or 'ninguno'}."
            ),
            "",
            (
                "| Proyecto | Llamadas | Usadas | Tokens (ent./sal.) | Costo (US$) | "
                "Latencia p50 / p95 | Cambia orden | Omite tipos | Cambia motivo |"
            ),
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for proyecto, r in bloque["por_proyecto"].items():
            lineas.append(
                f"| {proyecto} | {r['llamadas']} | {r['usadas']} | "
                f"{r['tokens_entrada']} / {r['tokens_salida']} | {r['costo_usd']:.6f} | "
                f"{r['latencia_p50_s']} s / {r['latencia_p95_s']} s | "
                f"{r['cambia_orden']} | {r['omite_tipos']} | {r['cambia_motivo']} |"
            )
        lineas += [
            "",
            (
                f"Costo total: US$ {total['costo_usd']:.6f} · por llamada: "
                f"US$ {total['costo_por_llamada_usd']:.6f} · latencia p50 / p95: "
                f"{total['latencia_p50_s']} s / {total['latencia_p95_s']} s."
            ),
            "",
        ]
    descartadas = [
        f"- {m['proyecto']} · {m['modelo']} (rep. {m['repeticion']}): "
        f"{m['descarte']} — {m['respuesta_descartada']}"
        for m in datos["respuestas"]
        if m["descarte"]
    ]
    if descartadas:
        lineas += [
            "## Respuestas descartadas (se usaron las reglas)",
            "",
            *descartadas,
            "",
        ]
    lineas += [
        "## Pendiente",
        "",
        "- Revisión a ciegas de una persona del equipo (`revision/planilla.csv`).",
        "- Conclusión sobre el modo por defecto, anotada en ADR-011.",
        "",
    ]
    return "\n".join(lineas)


def escribir(carpeta: Path, nombre: str, texto: str, claves: Any) -> None:
    """Escribe un resultado sin ninguna clave (`sanitizar_secretos`)."""
    limpio = sanitizar_secretos(texto, claves)
    if limpio != texto:
        print(f"Aviso: se quitó un texto con forma de clave de {nombre}.")
    (carpeta / nombre).write_text(limpio, encoding="utf-8")


# --- Programa ------------------------------------------------------------------------


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    elegir = parser.add_mutually_exclusive_group()
    elegir.add_argument(
        "--modelos",
        nargs="+",
        choices=AGENTES_CANDIDATOS,
        help="agentes de config.toml cuyo modelo se prueba como Recomendador "
        "(por omisión, todos los modelos distintos)",
    )
    elegir.add_argument(
        "--modelo",
        nargs="+",
        metavar="PROVEEDOR/MODELO",
        help="modelos del catálogo (llm/proveedores.toml) que se prueban como "
        "Recomendador, con sus precios; p. ej. deepseek/deepseek-flash",
    )
    parser.add_argument("--repeticiones", type=int, default=REPETICIONES)
    parser.add_argument("--tiempo-maximo", type=float, default=TIEMPO_MAXIMO_S)
    parser.add_argument("--proyectos", type=Path, default=PROYECTOS)
    parser.add_argument("--salida", type=Path, help="carpeta de resultados")
    parser.add_argument(
        "--config-local",
        type=Path,
        default=config_carga.RUTA_CONFIG_LOCAL,
        help="config.local.toml que se superpone a config.toml",
    )
    parser.add_argument(
        "--puntuar",
        type=Path,
        metavar="CARPETA",
        help="junta las planillas llenadas de una medición y revela el resultado",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = argumentos(argv)
    if args.puntuar:
        datos = puntuar(args.puntuar)
        print((args.puntuar / "revision" / "resultado.md").read_text(encoding="utf-8"))
        return datos

    carga = cargar_configuracion(ruta_local=args.config_local)
    if carga.config is None:
        raise SystemExit(
            "config.toml no se pudo usar: " + "; ".join(carga.avisos_config)
        )
    config, claves, simulado = carga.config, carga.claves, carga.simulado
    proyectos = leer_proyectos(args.proyectos)
    modelos = (
        del_catalogo(args.modelo) if args.modelo else candidatos(config, args.modelos)
    )
    if not modelos:
        raise SystemExit(
            "No hay modelos para medir: configura agentes en config.local.toml "
            "o usa --modelo proveedor/modelo."
        )

    mediciones: list[Medicion] = []
    for origen, precio in modelos:
        nombre = f"{precio.proveedor}/{precio.modelo}"
        try:
            cliente = crear_cliente(
                precio, claves, simulado=simulado, timeout_s=args.tiempo_maximo
            )
        except ConfiguracionLLMIncompleta as error:
            print(f"Se omite {nombre} ({origen}): {error}", file=sys.stderr)
            continue
        print(f"== {nombre} ({'simulado' if simulado else 'real'}) ==", flush=True)
        for repeticion in range(1, args.repeticiones + 1):
            for proyecto, (proyeccion, reglas) in proyectos.items():
                recomendador = RecomendadorIA(
                    cliente,
                    TokenTracker(),
                    precio,
                    tiempo_maximo_s=args.tiempo_maximo,
                    es_simulado=simulado,
                )
                medicion = medir_una(
                    proyecto, proyeccion, reglas, nombre, repeticion, recomendador
                )
                mediciones.append(medicion)
                print(
                    f"  rep. {repeticion} · {proyecto}: "
                    f"{'usada' if medicion.usada else 'descartada (' + str(medicion.descarte) + ')'}"
                    f" · {medicion.latencia_s:.2f} s · US$ {medicion.costo_usd:.6f}",
                    flush=True,
                )
    if not mediciones:
        raise SystemExit("No se pudo medir ningún modelo (ver los avisos de arriba).")

    por_modelo: dict[str, Any] = {}
    for nombre in dict.fromkeys(m.modelo for m in mediciones):
        propias = [m for m in mediciones if m.modelo == nombre]
        por_modelo[nombre] = {
            "estimado": any(m.estimado for m in propias),
            "total": resumir(propias),
            "por_proyecto": {
                p: resumir([m for m in propias if m.proyecto == p]) for p in proyectos
            },
        }
    datos = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "simulado": simulado,
        "repeticiones": args.repeticiones,
        "tiempo_maximo_s": args.tiempo_maximo,
        "proyectos": {
            p: {"reglas": _tipos(reglas)} for p, (_, reglas) in proyectos.items()
        },
        "modelos": por_modelo,
        "respuestas": [
            {
                k: v
                for k, v in dataclasses.asdict(m).items()
                if k not in {"recomendacion"} or m.usada
            }
            for m in mediciones
        ],
    }
    carpeta = args.salida or CARPETA / "resultados" / datetime.now().strftime(
        "%Y%m%d-%H%M"
    )
    carpeta.mkdir(parents=True, exist_ok=True)
    escribir(
        carpeta,
        "metricas.json",
        _json({k: datos[k] for k in datos if k != "respuestas"}),
        claves,
    )
    escribir(carpeta, "respuestas.json", _json(datos["respuestas"]), claves)
    escribir(carpeta, "resumen.md", resumen_md(datos), claves)
    filas = exportar_planilla(carpeta, proyectos, mediciones, 1, semilla=201)
    print(f"\nResultados en {carpeta} ({filas} filas en la planilla a ciegas).")
    return datos


def _json(datos: Any) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    main()

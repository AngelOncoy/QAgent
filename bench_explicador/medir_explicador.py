"""Mide el Agente Explicador con un LLM real frente a las plantillas (SPK #167, ADR-008).

Es el único script de QAgent que llama a una API real: lo corre una persona con su
clave en `~/.qagent/.env`. Ninguna prueba de `tests/` lo hace con la IA real. Uso,
desde la raíz del repositorio:

    python bench_explicador/medir_explicador.py                      # todos los modelos
    python bench_explicador/medir_explicador.py --modelos planner reviewer
    python bench_explicador/medir_explicador.py --modelo deepseek/deepseek-flash deepseek/deepseek-v4-pro
    python bench_explicador/medir_explicador.py --log-corrida <log.json de una corrida>

Lee los casos fijos de `casos/` (los 4 tipos de hallazgo) y, por cada modelo y
repetición, pide al Explicador con IA (`RedactorIA`) una explicación de cada hallazgo:

- por explicación y por corrida: tokens de entrada y salida, costo en USD, latencia y
  respuestas descartadas por motivo (JSON inválido, `decision` distinta, sugerencia de
  relajar una aserción, tiempo agotado...);
- el paso 1 (plantillas, 0 tokens) como línea base;
- que la entrada no lleva claves ni rutas absolutas, y que el Explicador nunca pasa
  `max_tokens_por_corrida` ni el tope en USD (también con topes mínimos a propósito);
- con `--log-corrida`, cuánto suma el Explicador al costo de una corrida real del banco.

Cada modelo candidato es el de un agente de `config.toml` (`config.local.toml`
encima, como en la aplicación) o, con `--modelo`, uno del catálogo
`llm/proveedores.toml` con sus precios. Se usa como Explicador: la clave se busca como
para el Explicador (`<PROVEEDOR>_API_KEY_EXPLICADOR` o la del proveedor). Con
`QAGENT_FAKE_LLM=1` todo corre con la IA simulada (0 tokens) y las cifras salen
marcadas [SIMULADO].

Deja en `resultados/<fecha>/` (o en `--salida`) `metricas.json`, `respuestas.json` (las
explicaciones, para la revisión a ciegas) y `resumen.md`. Ninguno lleva claves: todo
pasa por `sanitizar_secretos` antes de escribirse.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from qagent.agents.explicador import (
    _RUTA_ABSOLUTA,
    AGENTE,
    RedactorIA,
    SinExplicacionIA,
    entrada_ia,
    explicar_objetivo,
    tipo_de_hallazgo,
)
from qagent.analysis import analizar_proyecto
from qagent.config import carga as config_carga
from qagent.config import cargar_configuracion
from qagent.llm.fabrica import ConfiguracionLLMIncompleta, crear_cliente
from qagent.llm.precios import PrecioAgente
from qagent.llm.proveedores import catalogo
from qagent.llm.tracker import TokenTracker
from qagent.storage.exportar_informe import sanitizar_secretos

CARPETA = Path(__file__).resolve().parent
RAIZ = CARPETA.parent
CASOS = CARPETA / "casos"
#: Carpetas con el código de los objetivos de los casos, para leer sus docstrings.
BANCOS = (RAIZ / "bench", CARPETA)
AGENTES_CANDIDATOS = ("planner", "generator", "reviewer", AGENTE)
REPETICIONES = 3
TIEMPO_MAXIMO_S = 60.0

#: Motivo de descarte o de respaldo con plantilla, según el texto de SinExplicacionIA.
DESCARTES = (
    ("json_invalido", ("no es JSON", "no es un objeto JSON", "le falta")),
    # Antes que la decisión: si hay los dos errores, cuenta el de seguridad.
    ("relaja_asercion", ("relajar una aserción",)),
    # Distinta de results.json o fuera del enum del contrato (p. ej. "accept").
    ("decision_distinta", ("decision: ",)),
    ("tiempo_agotado", ("tiempo agotado",)),
    ("presupuesto", ("presupuesto de tokens", "tope de gasto")),
    ("error_llm", ("el LLM falló",)),
)


# --- Datos ---------------------------------------------------------------------------


@dataclasses.dataclass
class Medicion:
    """Una explicación pedida: de la IA (un modelo y una repetición) o de la plantilla."""

    origen: str
    modelo: str
    proveedor: str
    repeticion: int
    objetivo: str
    tipo: str
    latencia_s: float
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0
    tokens_estimados: bool = False
    descarte: str | None = None
    motivo: str | None = None
    explicacion: dict[str, Any] | None = None


def leer_casos(carpeta: Path = CASOS) -> tuple[dict[str, Any], dict[str, Any]]:
    """`results.json` y `detalle.json` de los casos fijos."""
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    detalle = json.loads((carpeta / "detalle.json").read_text(encoding="utf-8"))
    return results, detalle


def hallazgos(
    results: dict[str, Any], detalle: dict[str, Any]
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Cada objetivo no aceptado con su función de `detalle.json`."""
    funciones = {
        (f.get("modulo"), f.get("funcion")): f for f in detalle.get("funciones") or []
    }
    return [
        (objetivo, funciones.get((objetivo.get("modulo"), objetivo.get("funcion"))))
        for objetivo in results.get("objetivos") or []
        if tipo_de_hallazgo(objetivo) is not None
    ]


def leer_docstrings() -> dict[tuple[str, str], str | None]:
    """Docstring de cada función de los bancos, como los pasa la corrida."""
    docstrings: dict[tuple[str, str], str | None] = {}
    for banco in BANCOS:
        for modulo in analizar_proyecto(banco)["modulos"]:
            for funcion in modulo.get("funciones") or []:
                clave = (modulo["ruta"], funcion["nombre"])
                docstrings[clave] = funcion.get("docstring")
    return docstrings


def candidatos(
    config: Any, agentes: list[str] | None = None
) -> list[tuple[str, PrecioAgente]]:
    """Modelos a medir: el de cada agente de `config.toml`, sin repetir modelo.

    Cada uno se usa como Explicador (`agente = "explicador"`), así que la clave se
    busca como la del Explicador.
    """
    disponibles: dict[str, PrecioAgente] = dict(config.agentes)
    explicador = getattr(config, "explicador", None)
    if explicador is not None and explicador.precio is not None:
        disponibles[AGENTE] = explicador.precio
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
    """Modelos `proveedor/modelo` del catálogo, con sus precios, usados como Explicador.

    Sirve para medir modelos que no están en `config.toml`, por ejemplo dos del mismo
    proveedor. En OpenRouter el id del modelo lleva `/`: se separa solo en la primera.
    """
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


# --- Comprobaciones ------------------------------------------------------------------


def _textos(dato: Any) -> Iterator[str]:
    if isinstance(dato, str):
        yield dato
    elif isinstance(dato, dict):
        for valor in dato.values():
            yield from _textos(valor)
    elif isinstance(dato, list):
        for valor in dato:
            yield from _textos(valor)


def problemas_de_entrada(entrada: dict[str, Any], claves: Any = None) -> list[str]:
    """Rutas absolutas o secretos en lo que se enviaría al LLM; vacío si está limpia."""
    problemas = []
    for texto in _textos(entrada):
        if _RUTA_ABSOLUTA.search(texto):
            problemas.append(f"ruta absoluta en {texto[:60]!r}")
        if sanitizar_secretos(texto, claves) != texto:
            problemas.append("un texto con forma de clave o secreto")
    return problemas


def clasificar_descarte(motivo: str) -> str:
    """Categoría del motivo por el que no se usó la respuesta del LLM."""
    for categoria, marcas in DESCARTES:
        if any(marca in motivo for marca in marcas):
            return categoria
    return "contrato_invalido"


class ClienteQueNoDebeLlamarse:
    """Cliente que falla si lo llaman: prueba que los topes cortan antes de llamar."""

    def __init__(self) -> None:
        self.llamadas = 0

    def generar(self, prompt: str, rol: str = "") -> Any:
        self.llamadas += 1
        raise AssertionError("el Explicador llamó al LLM pasando el tope")


def probar_topes(
    precio: PrecioAgente,
    casos: list[tuple[dict[str, Any], dict[str, Any] | None]],
    docstrings: dict[tuple[str, str], str | None],
) -> dict[str, Any]:
    """Con topes mínimos, el Explicador no llama al LLM y deja la plantilla (0 tokens)."""
    resultado = {}
    for nombre, topes in (
        ("max_tokens_por_corrida", {"max_tokens": 1}),
        ("tope_por_corrida_usd", {"tope_usd": 1e-9}),
    ):
        cliente = ClienteQueNoDebeLlamarse()
        tracker = TokenTracker()
        redactor = RedactorIA(
            cliente,  # type: ignore[arg-type]
            tracker,
            precio,
            tiempo_maximo_s=5,
            **topes,  # type: ignore[arg-type]
        )
        cortes = 0
        for objetivo, funcion in casos:
            try:
                redactor.redactar(
                    objetivo, funcion, None, _docstring(docstrings, objetivo)
                )
            except SinExplicacionIA as motivo:
                cortes += clasificar_descarte(str(motivo)) == "presupuesto"
        resultado[nombre] = {
            "llamadas_al_llm": cliente.llamadas,
            "cortes_por_tope": cortes,
            "hallazgos": len(casos),
            "respeta_tope": cliente.llamadas == 0
            and cortes == len(casos)
            and tracker.total_tokens == 0,
        }
    return resultado


def _docstring(
    docstrings: dict[tuple[str, str], str | None], objetivo: dict[str, Any]
) -> str | None:
    return docstrings.get((objetivo.get("modulo"), objetivo.get("funcion")))  # type: ignore[arg-type]


# --- Mediciones ----------------------------------------------------------------------


def medir_plantillas(
    casos: list[tuple[dict[str, Any], dict[str, Any] | None]], run_id: str | None
) -> list[Medicion]:
    """Paso 1: una explicación con plantilla por hallazgo, 0 tokens."""
    mediciones = []
    for objetivo, funcion in casos:
        inicio = time.perf_counter()
        explicacion = explicar_objetivo(objetivo, funcion, run_id)
        mediciones.append(
            Medicion(
                origen="plantilla",
                modelo="plantilla",
                proveedor="-",
                repeticion=1,
                objetivo=str(objetivo["funcion"]),
                tipo=str(tipo_de_hallazgo(objetivo)),
                latencia_s=time.perf_counter() - inicio,
                explicacion=explicacion,
            )
        )
    return mediciones


def medir_modelo(
    precio: PrecioAgente,
    casos: list[tuple[dict[str, Any], dict[str, Any] | None]],
    docstrings: dict[tuple[str, str], str | None],
    *,
    claves: Any,
    simulado: bool,
    repeticiones: int,
    tiempo_maximo_s: float,
    presupuesto: Any,
    run_id: str | None,
) -> tuple[list[Medicion], list[dict[str, Any]]]:
    """Paso 2 con un modelo: cada hallazgo, `repeticiones` veces.

    Cada repetición es una corrida: un `TokenTracker` nuevo con los topes de
    `[presupuesto]`, como en `ejecutar_corrida`.
    """
    max_tokens = getattr(presupuesto, "max_tokens_por_corrida", None)
    tope_usd = getattr(presupuesto, "tope_por_corrida_usd", None)
    mediciones: list[Medicion] = []
    corridas: list[dict[str, Any]] = []
    for repeticion in range(1, repeticiones + 1):
        tracker = TokenTracker()
        cliente = crear_cliente(
            precio, claves, simulado=simulado, timeout_s=tiempo_maximo_s
        )
        redactor = RedactorIA(
            cliente,
            tracker,
            precio,
            tiempo_maximo_s=tiempo_maximo_s,
            max_tokens=max_tokens,
            tope_usd=tope_usd,
            es_simulado=simulado,
        )
        inicio_corrida = time.perf_counter()
        for objetivo, funcion in casos:
            docstring = _docstring(docstrings, objetivo)
            problemas = problemas_de_entrada(
                entrada_ia(objetivo, funcion, docstring), claves
            )
            if problemas:
                raise SystemExit(
                    f"No se envía {objetivo['funcion']}: " + "; ".join(problemas)
                )
            antes = len(tracker.llamadas)
            inicio = time.perf_counter()
            medicion = Medicion(
                origen="ia",
                modelo=precio.modelo,
                proveedor=precio.proveedor,
                repeticion=repeticion,
                objetivo=str(objetivo["funcion"]),
                tipo=str(tipo_de_hallazgo(objetivo)),
                latencia_s=0.0,
            )
            try:
                medicion.explicacion = redactor.redactar(
                    objetivo, funcion, run_id, docstring
                )
            except SinExplicacionIA as motivo:
                medicion.motivo = str(motivo)
                medicion.descarte = clasificar_descarte(str(motivo))
            medicion.latencia_s = time.perf_counter() - inicio
            for llamada in tracker.llamadas[antes:]:
                medicion.tokens_entrada += llamada.tokens_entrada
                medicion.tokens_salida += llamada.tokens_salida
                medicion.costo_usd += llamada.costo_usd
                medicion.tokens_estimados |= llamada.es_estimado
            mediciones.append(medicion)
        corridas.append(
            {
                "modelo": precio.modelo,
                "repeticion": repeticion,
                "latencia_s": round(time.perf_counter() - inicio_corrida, 3),
                "tokens": tracker.total_tokens,
                "costo_usd": round(tracker.total_costo_usd, 8),
                "max_tokens_por_corrida": max_tokens,
                "tope_por_corrida_usd": tope_usd,
                "respeta_topes": (not max_tokens or tracker.total_tokens <= max_tokens)
                and (not tope_usd or tracker.total_costo_usd <= tope_usd),
            }
        )
    return mediciones, corridas


def costo_corrida_real(ruta_log: Path) -> dict[str, Any]:
    """Tokens y costo de una corrida real (su `log.json`), sin contar al Explicador."""
    log = json.loads(ruta_log.read_text(encoding="utf-8"))
    llamadas = [ll for ll in log.get("llamadas") or [] if ll.get("agente") != AGENTE]
    por_agente: dict[str, dict[str, float]] = {}
    for llamada in llamadas:
        agente = por_agente.setdefault(
            llamada["agente"], {"llamadas": 0, "tokens": 0, "costo_usd": 0.0}
        )
        agente["llamadas"] += 1
        agente["tokens"] += llamada["prompt_tokens"] + llamada["completion_tokens"]
        agente["costo_usd"] += llamada["costo_usd"]
    return {
        "run_id": log.get("run_id"),
        "es_simulado": bool(log.get("es_simulado")),
        "tokens_estimados": any(ll.get("es_estimado") for ll in llamadas),
        "tokens": sum(a["tokens"] for a in por_agente.values()),
        "costo_usd": round(sum(a["costo_usd"] for a in por_agente.values()), 8),
        "por_agente": por_agente,
    }


# --- Resumen -------------------------------------------------------------------------


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    if len(valores) == 1:
        return valores[0]
    return statistics.quantiles(valores, n=100, method="inclusive")[int(p) - 1]


def resumir(
    mediciones: list[Medicion],
    corridas: list[dict[str, Any]],
    corrida_real: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Cifras por modelo (y la plantilla): por explicación, por corrida y descartes."""
    filas = []
    for modelo in dict.fromkeys(m.modelo for m in mediciones):
        propias = [m for m in mediciones if m.modelo == modelo]
        latencias = [m.latencia_s for m in propias]
        de_corridas = [c for c in corridas if c["modelo"] == modelo]
        descartes = Counter(m.descarte for m in propias if m.descarte)
        n = len(propias)
        fila: dict[str, Any] = {
            "modelo": modelo,
            "origen": propias[0].origen,
            "proveedor": propias[0].proveedor,
            "explicaciones": n,
            "tokens_entrada_prom": round(sum(m.tokens_entrada for m in propias) / n),
            "tokens_salida_prom": round(sum(m.tokens_salida for m in propias) / n),
            "costo_usd_prom": sum(m.costo_usd for m in propias) / n,
            "latencia_s_p50": round(_percentil(latencias, 50), 3),
            "latencia_s_p95": round(_percentil(latencias, 95), 3),
            "tokens_estimados": any(m.tokens_estimados for m in propias),
            "descartadas_pct": round(100 * sum(descartes.values()) / n, 1),
            "descartes": dict(descartes),
        }
        if de_corridas:
            costo = statistics.mean(c["costo_usd"] for c in de_corridas)
            fila["por_corrida"] = {
                "tokens_prom": round(statistics.mean(c["tokens"] for c in de_corridas)),
                "costo_usd_prom": costo,
                "latencia_s_prom": round(
                    statistics.mean(c["latencia_s"] for c in de_corridas), 3
                ),
                "respeta_topes": all(c["respeta_topes"] for c in de_corridas),
            }
            if corrida_real and corrida_real["costo_usd"] > 0:
                total = corrida_real["costo_usd"] + costo
                fila["por_corrida"]["pct_del_costo_total"] = round(
                    100 * costo / total, 2
                )
        filas.append(fila)
    return filas


def _etiqueta(simulado: bool, estimado: bool = False) -> str:
    if simulado:
        return "[SIMULADO]"
    return "[ESTIMADO]" if estimado else "[MEDIDO]"


def resumen_md(datos: dict[str, Any]) -> str:
    """El `resumen.md` de la medición."""
    simulado = datos["es_simulado"]
    lineas = [
        "# Medición del Agente Explicador (SPK #167)",
        "",
        f"- **Fecha:** {datos['fecha']}",
        (
            f"- **Casos:** {datos['hallazgos']} hallazgos ({', '.join(datos['tipos'])}), "
            f"{datos['repeticiones']} repeticiones por modelo"
        ),
        f"- **Tiempo máximo por explicación:** {datos['tiempo_maximo_s']:g} s",
        f"- **IA:** {'simulada (0 tokens)' if simulado else 'real'}",
        "",
        (
            "> [MEDIDO]: cifras de esta corrida con un LLM real, con los tokens que "
            "informó el proveedor. [ESTIMADO]: el proveedor no informó tokens y se "
            "calcularon como caracteres / 4. [SIMULADO]: IA simulada, solo comprueba "
            "que el script funciona."
        ),
        "",
        "## Por explicación",
        "",
        (
            "| Modelo | Tokens entrada | Tokens salida | Costo US$ | Latencia p50 / p95 (s) "
            "| Descartadas | Etiqueta |"
        ),
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for fila in datos["por_modelo"]:
        etiqueta = (
            "[MEDIDO]"
            if fila["origen"] == "plantilla"
            else _etiqueta(simulado, fila["tokens_estimados"])
        )
        descartes = ", ".join(f"{k}: {v}" for k, v in fila["descartes"].items())
        lineas.append(
            f"| {fila['modelo']} | {fila['tokens_entrada_prom']} "
            f"| {fila['tokens_salida_prom']} | {fila['costo_usd_prom']:.6f} "
            f"| {fila['latencia_s_p50']:.3f} / {fila['latencia_s_p95']:.3f} "
            f"| {fila['descartadas_pct']} %{f' ({descartes})' if descartes else ''} "
            f"| {etiqueta} |"
        )
    lineas += [
        "",
        "## Por corrida (todos los hallazgos de los casos)",
        "",
        (
            "| Modelo | Tokens | Costo US$ | Latencia (s) | % del costo de la corrida "
            "| Respeta los topes |"
        ),
        "|---|---:|---:|---:|---:|---|",
    ]
    real = datos.get("corrida_real")
    sin_pct = "sin --log-corrida" if real is None else "la corrida no tuvo costo"
    for fila in datos["por_modelo"]:
        corrida = fila.get("por_corrida")
        if corrida is None:
            continue
        pct = corrida.get("pct_del_costo_total")
        lineas.append(
            f"| {fila['modelo']} | {corrida['tokens_prom']} "
            f"| {corrida['costo_usd_prom']:.6f} | {corrida['latencia_s_prom']:.3f} "
            f"| {f'{pct} %' if pct is not None else sin_pct} "
            f"| {'sí' if corrida['respeta_topes'] else 'NO'} |"
        )
    if real:
        lineas += [
            "",
            (
                f"Corrida de referencia `{real['run_id']}`: {real['tokens']} tokens y "
                f"US$ {real['costo_usd']:.6f} sin el Explicador "
                f"{_etiqueta(real['es_simulado'], real['tokens_estimados'])}."
            ),
        ]
    lineas += ["", "## Comprobaciones", ""]
    lineas.append(
        "- Entrada sin claves ni rutas absolutas: sí, en todos los hallazgos "
        "(si no, el script se detiene antes de enviar)."
    )
    for modelo, topes in datos["prueba_topes"].items():
        for tope, r in topes.items():
            lineas.append(
                f"- {modelo}, `{tope}` mínimo: {r['llamadas_al_llm']} llamadas al LLM, "
                f"{r['cortes_por_tope']} de {r['hallazgos']} con plantilla "
                f"({'respeta el tope' if r['respeta_tope'] else 'NO respeta el tope'})."
            )
    return "\n".join(lineas) + "\n"


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
        help="agentes de config.toml cuyo modelo se prueba como Explicador "
        "(por omisión, todos los modelos distintos)",
    )
    elegir.add_argument(
        "--modelo",
        nargs="+",
        metavar="PROVEEDOR/MODELO",
        help="modelos del catálogo (llm/proveedores.toml) que se prueban como "
        "Explicador, con sus precios; p. ej. deepseek/deepseek-flash",
    )
    parser.add_argument("--repeticiones", type=int, default=REPETICIONES)
    parser.add_argument("--tiempo-maximo", type=float, default=TIEMPO_MAXIMO_S)
    parser.add_argument(
        "--log-corrida",
        type=Path,
        help="log.json de una corrida real del banco, para el % del costo total",
    )
    parser.add_argument("--casos", type=Path, default=CASOS)
    parser.add_argument("--salida", type=Path, help="carpeta de resultados")
    parser.add_argument(
        "--config-local",
        type=Path,
        default=config_carga.RUTA_CONFIG_LOCAL,
        help="config.local.toml que se superpone a config.toml",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = argumentos(argv)
    carga = cargar_configuracion(ruta_local=args.config_local)
    if carga.config is None:
        raise SystemExit(
            "config.toml no se pudo usar: " + "; ".join(carga.avisos_config)
        )
    config, claves, simulado = carga.config, carga.claves, carga.simulado

    results, detalle = leer_casos(args.casos)
    casos = hallazgos(results, detalle)
    docstrings = leer_docstrings()
    run_id = results.get("run_id")

    mediciones = medir_plantillas(casos, run_id)
    corridas: list[dict[str, Any]] = []
    prueba_topes: dict[str, Any] = {}
    omitidos: dict[str, str] = {}
    elegidos = (
        del_catalogo(args.modelo) if args.modelo else candidatos(config, args.modelos)
    )
    for agente, precio in elegidos:
        de = "del catálogo" if agente == "catálogo" else f"de [agentes.{agente}]"
        print(f"Midiendo {precio.modelo} ({precio.proveedor}, {de})…")
        prueba_topes[precio.modelo] = probar_topes(precio, casos, docstrings)
        try:
            propias, de_corridas = medir_modelo(
                precio,
                casos,
                docstrings,
                claves=claves,
                simulado=simulado,
                repeticiones=args.repeticiones,
                tiempo_maximo_s=args.tiempo_maximo,
                presupuesto=config.presupuesto,
                run_id=run_id,
            )
        except ConfiguracionLLMIncompleta as error:
            print(f"  Se omite: {error}")
            omitidos[precio.modelo] = str(error)
            continue
        mediciones += propias
        corridas += de_corridas

    corrida_real = costo_corrida_real(args.log_corrida) if args.log_corrida else None
    fecha = datetime.now().astimezone()
    datos = {
        "version": "1",
        "spk": 167,
        "fecha": fecha.isoformat(timespec="seconds"),
        "es_simulado": simulado,
        "casos": str(args.casos.resolve().relative_to(RAIZ))
        if args.casos.resolve().is_relative_to(RAIZ)
        else args.casos.name,
        "hallazgos": len(casos),
        "tipos": sorted({str(tipo_de_hallazgo(o)) for o, _ in casos}),
        "repeticiones": args.repeticiones,
        "tiempo_maximo_s": args.tiempo_maximo,
        "presupuesto": {
            "max_tokens_por_corrida": getattr(
                config.presupuesto, "max_tokens_por_corrida", None
            ),
            "tope_por_corrida_usd": getattr(
                config.presupuesto, "tope_por_corrida_usd", None
            ),
        },
        "modelos_omitidos": omitidos,
        "por_modelo": resumir(mediciones, corridas, corrida_real),
        "corridas": corridas,
        "corrida_real": corrida_real,
        "prueba_topes": prueba_topes,
    }
    sufijo = "-simulado" if simulado else ""
    salida = args.salida or CARPETA / "resultados" / (
        fecha.strftime("%Y%m%d-%H%M") + sufijo
    )
    salida.mkdir(parents=True, exist_ok=True)
    respuestas = [
        {k: v for k, v in dataclasses.asdict(m).items() if k != "explicacion"}
        | {"explicacion": m.explicacion}
        for m in mediciones
    ]
    escribir(salida, "metricas.json", _json(datos), claves)
    escribir(salida, "respuestas.json", _json(respuestas), claves)
    escribir(salida, "resumen.md", resumen_md(datos), claves)
    print(f"Resultados en {salida}")
    return datos


def _json(datos: Any) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

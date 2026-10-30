"""Revisión a ciegas de las explicaciones: plantilla frente a IA (SPK #167, `rubrica.md`).

Uso, desde la raíz del repositorio, sobre la carpeta que dejó `medir_explicador.py`:

    python bench_explicador/revision_ciega.py exportar bench_explicador/resultados/<fecha> --revisores ana rodrigo
    python bench_explicador/revision_ciega.py puntuar bench_explicador/resultados/<fecha>

`exportar` arma en `<carpeta>/revision/` una planilla por persona
(`planilla-<nombre>.csv`, separada por `;`, se abre en Excel o en Google Sheets). Cada
fila es un hallazgo con dos explicaciones, A y B: la de la plantilla y la de un modelo,
en orden al azar y sin decir cuál es cuál. El orden queda en `clave.json`, que **no** se
comparte con quienes revisan.

`puntuar` lee las planillas completas, revela qué era cada explicación y deja
`resultado.json` y `resultado.md` con los promedios por criterio, las preferencias y
el acuerdo entre quienes revisaron.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # medir_explicador

import medir_explicador as medir

from qagent.agents.explicador import entrada_ia

CARPETA_REVISION = "revision"
CLAVE = "clave.json"
CRITERIOS = ("correcta", "se_entiende", "no_inventa", "no_contradice", "usa_traza")
#: Criterios en los que un solo 1 de la IA ya impide activarla por defecto.
CRITERIOS_DE_RIESGO = ("no_inventa", "no_contradice")
PREFERIDAS = ("A", "B", "igual")
PUNTAJES = ("1", "2", "3")
SEPARADOR = ";"
PLANTILLA = "plantilla"
CAMPOS_TEXTO = (
    ("resumen", "Resumen"),
    ("que_se_esperaba", "Qué se esperaba"),
    ("que_paso", "Qué pasó"),
    ("que_hacer", "Qué hacer"),
)
LARGO_LINEA_ERROR = 200
_LINEA_RESUMEN_PYTEST = re.compile(r"^(?:FAILED|ERROR) \S+ - (.+)$")


def columnas() -> list[str]:
    """Encabezado de la planilla."""
    puntajes = [f"{lado}_{c}" for lado in ("A", "B") for c in CRITERIOS]
    return ["par", "objetivo", "hechos", "A", "B", *puntajes, "preferida", "comentario"]


# --- Exportar ------------------------------------------------------------------------


def texto_explicacion(explicacion: dict[str, Any]) -> str:
    """Lo que lee quien revisa: los cuatro campos, sin `origen` ni `modelo`."""
    return "\n".join(
        f"{titulo}: {explicacion.get(campo) or '—'}" for campo, titulo in CAMPOS_TEXTO
    )


def linea_de_error(feedback: str | None) -> str:
    """La línea que resume el fallo de un intento: lo que dice pytest o el Reviewer."""
    if not feedback:
        return "sin detalle"
    lineas = [linea.strip() for linea in feedback.splitlines() if linea.strip()]
    for linea in lineas:
        coincidencia = _LINEA_RESUMEN_PYTEST.match(linea)
        if coincidencia:
            return coincidencia.group(1)[:LARGO_LINEA_ERROR]
    avisos = [linea.lstrip("⚠ ") for linea in lineas if linea.startswith("⚠")]
    if avisos:
        return "; ".join(avisos)[:LARGO_LINEA_ERROR]
    return lineas[-1][:LARGO_LINEA_ERROR]


def hechos(entrada: dict[str, Any]) -> str:
    """Los hechos del hallazgo, tal como los recibe el LLM, en texto para revisar."""
    decision = entrada.get("decision") or "sin veredicto"
    motivo = entrada.get("motivo_estancado") or entrada.get("motivo_sin_veredicto")
    partes = [
        f"Decisión de QAgent: {decision}" + (f" (motivo: {motivo})" if motivo else ""),
        "Assertion Laundering detectado: "
        + ("sí" if entrada.get("laundering_detectado") else "no"),
        f"Intentos: {entrada.get('intentos') or len(entrada.get('traza') or [])}",
    ]
    if entrada.get("docstring"):
        partes.append(f"Documentación: {entrada['docstring']}")
    for caso in entrada.get("casos") or []:
        esperado = (
            f"lanza {caso['excepcion']}"
            if caso.get("excepcion")
            else f"devuelve {caso.get('valor_esperado')!r}"
        )
        partes.append(f"Caso {caso.get('id')}: con {caso.get('entrada')} {esperado}")
    for paso in entrada.get("traza") or []:
        laundering = ", debilitó la prueba" if paso.get("laundering_detectado") else ""
        partes.append(
            f"Intento {paso.get('intento')}: {paso.get('decision')}, "
            f"{paso.get('tipo_fallo') or 'sin tipo'}{laundering}: "
            f"{linea_de_error(paso.get('feedback'))}"
        )
    fallido = entrada.get("primer_caso_fallido")
    if fallido and (fallido.get("esperado") or fallido.get("obtenido")):
        partes.append(
            f"Primer caso que falló: {fallido.get('caso')}, se esperaba "
            f"{fallido.get('esperado')} y se obtuvo {fallido.get('obtenido')}"
        )
    return "\n".join(partes)


def armar_pares(
    respuestas: list[dict[str, Any]],
    contexto: dict[str, str],
    repeticion: int,
    semilla: int,
) -> tuple[list[dict[str, str]], dict[str, Any], list[str]]:
    """Filas de la planilla, la clave para revelarlas y las explicaciones de IA omitidas.

    Un par es la plantilla frente a la explicación de un modelo para un hallazgo. Se
    omiten las de IA descartadas: en la corrida real se habría mostrado la plantilla.
    """
    azar = random.Random(semilla)
    plantillas = {r["objetivo"]: r for r in respuestas if r["origen"] == PLANTILLA}
    pares: list[tuple[dict[str, Any], dict[str, Any]]] = []
    omitidas: list[str] = []
    for respuesta in respuestas:
        if respuesta["origen"] == PLANTILLA or respuesta["repeticion"] != repeticion:
            continue
        if respuesta["explicacion"] is None:
            omitidas.append(
                f"{respuesta['modelo']} / {respuesta['objetivo']}: {respuesta['motivo']}"
            )
            continue
        pares.append((plantillas[respuesta["objetivo"]], respuesta))
    azar.shuffle(pares)

    filas: list[dict[str, str]] = []
    clave: dict[str, Any] = {}
    for numero, (plantilla, ia) in enumerate(pares, start=1):
        par = f"P{numero:02d}"
        lados = [plantilla, ia]
        azar.shuffle(lados)
        clave[par] = {
            "objetivo": ia["objetivo"],
            "tipo": ia["tipo"],
            **{
                lado: {"origen": r["origen"], "modelo": r["modelo"]}
                for lado, r in zip(("A", "B"), lados)
            },
        }
        fila = dict.fromkeys(columnas(), "")
        fila.update(
            par=par,
            objetivo=ia["objetivo"],
            hechos=contexto[ia["objetivo"]],
            A=texto_explicacion(lados[0]["explicacion"]),
            B=texto_explicacion(lados[1]["explicacion"]),
        )
        filas.append(fila)
    return filas, clave, omitidas


def contexto_de_casos(metricas: dict[str, Any]) -> dict[str, str]:
    """Los hechos de cada hallazgo de los casos que se midieron."""
    carpeta = Path(metricas["casos"])
    if not carpeta.is_absolute():
        carpeta = medir.RAIZ / carpeta
    results, detalle = medir.leer_casos(carpeta)
    docstrings = medir.leer_docstrings()
    contexto = {}
    for objetivo, funcion in medir.hallazgos(results, detalle):
        docstring = docstrings.get((objetivo.get("modulo"), objetivo.get("funcion")))
        contexto[objetivo["funcion"]] = hechos(entrada_ia(objetivo, funcion, docstring))
    return contexto


def exportar(
    resultados: Path,
    revisores: list[str],
    repeticion: int = 1,
    semilla: int | None = None,
) -> Path:
    """Arma las planillas y la clave en `<resultados>/revision/`."""
    metricas = json.loads((resultados / "metricas.json").read_text(encoding="utf-8"))
    respuestas = json.loads(
        (resultados / "respuestas.json").read_text(encoding="utf-8")
    )
    semilla = random.SystemRandom().randrange(10**9) if semilla is None else semilla
    filas, clave, omitidas = armar_pares(
        respuestas, contexto_de_casos(metricas), repeticion, semilla
    )
    if not filas:
        raise SystemExit("No hay explicaciones de IA para comparar en esa repetición.")
    carpeta = resultados / CARPETA_REVISION
    carpeta.mkdir(exist_ok=True)
    for revisor in revisores:
        with open(
            carpeta / f"planilla-{revisor}.csv", "w", encoding="utf-8-sig", newline=""
        ) as archivo:
            escritor = csv.DictWriter(
                archivo, fieldnames=columnas(), delimiter=SEPARADOR
            )
            escritor.writeheader()
            escritor.writerows(filas)
    (carpeta / CLAVE).write_text(
        json.dumps(
            {
                "semilla": semilla,
                "repeticion": repeticion,
                "revisores": revisores,
                "omitidas": omitidas,
                "pares": clave,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(filas)} pares en {carpeta} para {', '.join(revisores)}.")
    if omitidas:
        print(f"Se omitieron {len(omitidas)} explicaciones de IA descartadas.")
    return carpeta


# --- Puntuar -------------------------------------------------------------------------


def leer_planilla(ruta: Path, pares: dict[str, Any]) -> list[dict[str, str]]:
    """Filas de una planilla completa; si falta algo, se detiene diciendo qué."""
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.DictReader(archivo, delimiter=SEPARADOR))
    faltan = []
    for fila in filas:
        par = fila.get("par", "")
        if par not in pares:
            faltan.append(f"par desconocido {par!r}")
            continue
        for lado in ("A", "B"):
            for criterio in CRITERIOS:
                if (fila.get(f"{lado}_{criterio}") or "").strip() not in PUNTAJES:
                    faltan.append(f"{par} {lado}_{criterio}")
        if _preferida(fila) not in PREFERIDAS:
            faltan.append(f"{par} preferida")
    if len(filas) != len(pares):
        faltan.append(f"tiene {len(filas)} filas y deberían ser {len(pares)}")
    if faltan:
        raise SystemExit(
            f"{ruta.name} está incompleta (1, 2 o 3; preferida A, B o igual): "
            + ", ".join(faltan[:20])
        )
    return filas


def _preferida(fila: dict[str, str]) -> str:
    valor = (fila.get("preferida") or "").strip()
    return valor.lower() if valor.lower() == "igual" else valor.upper()


def _etiqueta(lado: dict[str, str]) -> str:
    return PLANTILLA if lado["origen"] == PLANTILLA else lado["modelo"]


def puntuar_planillas(
    planillas: dict[str, list[dict[str, str]]], pares: dict[str, Any]
) -> dict[str, Any]:
    """Revela cada planilla y junta los puntajes por modelo y para la plantilla."""
    puntajes: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    preferencias: dict[str, Counter[str]] = defaultdict(Counter)
    por_par: dict[str, dict[str, str]] = defaultdict(dict)
    for revisor, filas in planillas.items():
        for fila in filas:
            clave = pares[fila["par"]]
            for lado in ("A", "B"):
                etiqueta = _etiqueta(clave[lado])
                for criterio in CRITERIOS:
                    puntajes[etiqueta][criterio].append(int(fila[f"{lado}_{criterio}"]))
            ia = next(lado for lado in ("A", "B") if clave[lado]["origen"] != PLANTILLA)
            modelo = clave[ia]["modelo"]
            preferida = _preferida(fila)
            eleccion = (
                "igual"
                if preferida == "igual"
                else ("ia" if preferida == ia else PLANTILLA)
            )
            preferencias[modelo][eleccion] += 1
            por_par[fila["par"]][revisor] = eleccion

    por_origen = {}
    for etiqueta, criterios in puntajes.items():
        promedios = {c: round(sum(v) / len(v), 2) for c, v in criterios.items()}
        por_origen[etiqueta] = {
            "promedios": promedios,
            "general": round(sum(promedios.values()) / len(promedios), 2),
            "unos_en_riesgo": {c: criterios[c].count(1) for c in CRITERIOS_DE_RIESGO},
        }
    coinciden = sum(len(set(e.values())) == 1 for e in por_par.values())
    return {
        "revisores": sorted(planillas),
        "pares": len(pares),
        "por_origen": por_origen,
        "preferencias": {m: dict(c) for m, c in preferencias.items()},
        "acuerdo_preferida": {
            "coinciden": coinciden,
            "pares": len(por_par),
            "pct": round(100 * coinciden / len(por_par), 1) if por_par else 0.0,
        },
    }


def resultado_md(datos: dict[str, Any]) -> str:
    """El `resultado.md` de la revisión."""
    lineas = [
        "# Revisión a ciegas del Explicador (SPK #167)",
        "",
        f"- **Revisaron:** {', '.join(datos['revisores'])}",
        f"- **Pares:** {datos['pares']} (plantilla frente a un modelo, mismo hallazgo)",
        "- **Escala:** 1 a 3 por criterio (`rubrica.md`). Cifras [MEDIDO].",
        "",
        "## Promedios por criterio",
        "",
        "| Origen | "
        + " | ".join(CRITERIOS)
        + " | General | 1 en no_inventa / no_contradice |",
        "|---|" + "---:|" * (len(CRITERIOS) + 1) + "---:|",
    ]
    for etiqueta, fila in datos["por_origen"].items():
        unos = fila["unos_en_riesgo"]
        lineas.append(
            f"| {etiqueta} | "
            + " | ".join(f"{fila['promedios'][c]:.2f}" for c in CRITERIOS)
            + f" | {fila['general']:.2f} | "
            + f"{unos['no_inventa']} / {unos['no_contradice']} |"
        )
    lineas += [
        "",
        "## Preferida",
        "",
        "| Modelo | Prefirieron la IA | Prefirieron la plantilla | Igual |",
        "|---|---:|---:|---:|",
    ]
    for modelo, conteo in datos["preferencias"].items():
        lineas.append(
            f"| {modelo} | {conteo.get('ia', 0)} | {conteo.get(PLANTILLA, 0)} "
            f"| {conteo.get('igual', 0)} |"
        )
    acuerdo = datos["acuerdo_preferida"]
    lineas += [
        "",
        (
            f"Quienes revisaron eligieron la misma preferida en {acuerdo['coinciden']} de "
            f"{acuerdo['pares']} pares ({acuerdo['pct']} %)."
        ),
    ]
    return "\n".join(lineas) + "\n"


def puntuar(resultados: Path) -> dict[str, Any]:
    """Junta las planillas de `<resultados>/revision/` y deja `resultado.json` y `.md`."""
    carpeta = resultados / CARPETA_REVISION
    clave = json.loads((carpeta / CLAVE).read_text(encoding="utf-8"))
    pares = clave["pares"]
    rutas = sorted(carpeta.glob("planilla-*.csv"))
    planillas = {
        ruta.stem.removeprefix("planilla-"): leer_planilla(ruta, pares)
        for ruta in rutas
    }
    if len(planillas) < 2:
        raise SystemExit("Hacen falta al menos 2 planillas completas (rubrica.md).")
    datos = puntuar_planillas(planillas, pares)
    datos["omitidas"] = clave.get("omitidas", [])
    (carpeta / "resultado.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (carpeta / "resultado.md").write_text(resultado_md(datos), encoding="utf-8")
    print(f"Resultado en {carpeta / 'resultado.md'}")
    return datos


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    comandos = parser.add_subparsers(dest="comando", required=True)
    exp = comandos.add_parser("exportar", help="arma las planillas a ciegas")
    exp.add_argument("resultados", type=Path)
    exp.add_argument("--revisores", nargs="+", default=["revisor1", "revisor2"])
    exp.add_argument("--repeticion", type=int, default=1)
    exp.add_argument("--semilla", type=int)
    pun = comandos.add_parser("puntuar", help="junta las planillas y las revela")
    pun.add_argument("resultados", type=Path)
    args = parser.parse_args(argv)
    if args.comando == "exportar":
        exportar(args.resultados, args.revisores, args.repeticion, args.semilla)
    else:
        puntuar(args.resultados)


if __name__ == "__main__":
    main()

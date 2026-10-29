"""Sincroniza los issues de GitHub con el backlog del equipo en Notion.

GitHub manda y Notion refleja: cada issue tiene una fila en la base «Backlog fixeado»,
encontrada por su enlace en la columna «GitHub». El script crea la fila si no existe y,
si existe, actualiza solo lo que viene de GitHub:

- Tareas (título «TIPO - Título»; las épicas, «EP-NN · Título»), Tipo, Descripción,
  Criterios de Aceptación y GitHub.
- Responsable, solo si alguna persona asignada en GitHub está en ``EQUIPO``.
- Épica y Tipo PBI, si el issue es sub-issue de una épica que ya tiene fila.
- Status: al crear, «Open» o «Closed» según el issue; después solo cambia al cerrar o
  reabrir, para no pisar «Doing» o «En revision» puestos a mano.
- Fecha Inicio al crear; Fecha Fin al cerrar (y se borra si el issue se reabre).

De una fila que ya existe y cuyo issue está cerrado solo se actualizan Status y Fecha Fin:
así no se pisa el texto que el equipo escribió a mano en las filas del Sprint 1. Con
``--todos``, un issue cerrado que no tiene fila se omite (no se traen tareas viejas).

Nunca toca SP ni Prioridad, que se llenan a mano. No usa dependencias externas.

Uso:
    python scripts/sincronizar_notion.py --issue 193            # un issue
    python scripts/sincronizar_notion.py --todos                # abiertos y cerrados hace poco
    python scripts/sincronizar_notion.py --todos --en-seco      # muestra qué haría, sin escribir

Variables de entorno: ``NOTION_TOKEN``, ``NOTION_DATABASE_ID``, ``GITHUB_TOKEN``,
``GITHUB_REPOSITORY`` (``dueño/repo``) y, opcional, ``SPRINT_ACTUAL`` (por defecto
«Sprint 2»).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

#: Usuario de GitHub → id de la persona en Notion. Quien no está aquí no se asigna.
EQUIPO = {
    "AngelOncoy": "1cad872b-594c-8125-a53c-00028a8f9d9f",
    "bel001": "3cfd872b-594c-8149-9e73-0002d00c43f5",
    "Mateo-SV": "2a7d872b-594c-811d-a42e-00027eb67276",
    "Cronos7898": "3cfd872b-594c-81c4-9327-0002d5d9b89c",
}

TIPOS = ("HU", "EN", "SPK", "TA", "BU", "FIX", "DO", "EV")
#: Prefijos que el equipo usó en títulos de GitHub y el tipo que les corresponde.
SINONIMOS = {"FEAT": "TA", "REFACTOR": "TA", "TAREA": "TA", "BUG": "BU"}
ETIQUETA_EPICA = "Epic History"
ABIERTO, CERRADO = "Open (Abierto)", "Closed (Cerrado)"
#: Notion acepta como máximo 2000 caracteres por bloque de texto.
LIMITE_TEXTO = 2000
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


# --- Funciones puras (se prueban sin red) ------------------------------------------


def normalizar_titulo(titulo: str, etiquetas: list[str]) -> tuple[str, str]:
    """Devuelve ``(tipo, título)`` sin numeración: «EN-21 - X» → («EN», «EN - X»).

    Las épicas conservan su número: «EP-14 - X» → («Épica», «EP-14 · X»).
    """
    t = re.sub(
        r"^\s*(t[ií]tulo:\s*|\(pre_issue\)\s*)", "", titulo.strip(), flags=re.IGNORECASE
    )
    epica = re.match(r"EP-?(\d+)\s*[-—:·.]*\s*(.+)", t, re.IGNORECASE)
    if epica:
        return "Épica", f"EP-{int(epica.group(1)):02d} · {epica.group(2).strip()}"
    m = re.match(r"([A-Za-z]+)(?:[-\s]*\d+)?(?:/[A-Za-z]+)?\s*[-—:·.]+\s*", t)
    tipo = None
    if m:
        palabra = m.group(1).upper()
        tipo = palabra if palabra in TIPOS else SINONIMOS.get(palabra)
    if tipo:
        resto = t[m.end() :]
    else:
        tipo = next((e for e in etiquetas if e in TIPOS), "TA")
        resto = t
    resto = resto.strip()
    resto = resto[:1].upper() + resto[1:]
    return tipo, f"{tipo} - {resto}"


def numero_de_epica(titulo: str) -> int | None:
    """Número de una épica a partir de su título («EP-12 - Java» → 12)."""
    m = re.match(r"\s*EP-?(\d+)", titulo, re.IGNORECASE)
    return int(m.group(1)) if m else None


def a_markdown(cuerpo: str) -> str:
    """Pasa a texto con encabezados ``###`` los issues escritos en HTML."""
    if "<p>" not in cuerpo and "<h3>" not in cuerpo:
        return cuerpo
    t = re.sub(r"<h\d>(.*?)</h\d>", r"\n### \1\n", cuerpo)
    t = re.sub(r"<li>", "- ", t)
    t = re.sub(r"</(p|li|ul|ol)>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t)


def seccion(cuerpo: str, nombre: str) -> str:
    """Texto de la sección ``## nombre`` o ``### nombre`` hasta la siguiente."""
    patron = r"#{2,3}\s*" + nombre + r"[^\n]*\n(.*?)(?=\n---|\n##|\Z)"
    m = re.search(patron, cuerpo or "", re.DOTALL | re.IGNORECASE)
    texto = (m.group(1) if m else "").strip()
    texto = re.sub(r"\*\*(.*?)\*\*", r"\1", texto)
    return re.sub(r"\n{3,}", "\n\n", texto)


def descripcion_y_criterios(cuerpo: str) -> tuple[str, str]:
    """Descripción y criterios de aceptación del cuerpo de un issue."""
    cuerpo = a_markdown(cuerpo or "")
    desc = seccion(cuerpo, "Descripci[oó]n")
    if not desc:
        partes = [seccion(cuerpo, "Problema"), seccion(cuerpo, "Objetivo")]
        desc = "\n\n".join(p for p in partes if p)
    return desc, seccion(cuerpo, "Criterios")


def texto_notion(texto: str, maximo: int = 3 * LIMITE_TEXTO) -> list[dict[str, Any]]:
    """Rich text de Notion en bloques de 2000 caracteres, recortado a ``maximo``."""
    if len(texto) > maximo:
        texto = texto[: maximo - 1].rsplit(" ", 1)[0] + "…"
    return [
        {"type": "text", "text": {"content": texto[i : i + LIMITE_TEXTO]}}
        for i in range(0, len(texto), LIMITE_TEXTO)
    ]


def fecha(iso: str | None) -> dict[str, Any] | None:
    """Fecha de Notion (solo el día) a partir de una fecha ISO de GitHub."""
    return {"start": iso[:10]} if iso else None


def propiedades(
    issue: dict[str, Any],
    actual: dict[str, Any] | None,
    epica_id: str | None,
    sprint: str,
) -> dict[str, Any]:
    """Propiedades de Notion para ``issue``; ``actual`` son las de la fila si existe."""
    etiquetas = [e["name"] for e in issue["labels"]["nodes"]]
    tipo, titulo = normalizar_titulo(issue["title"], etiquetas)
    desc, criterios = descripcion_y_criterios(issue.get("body") or "")
    cerrado = issue["state"] == "CLOSED"
    props: dict[str, Any] = {
        "Tareas": {"title": texto_notion(titulo, LIMITE_TEXTO)},
        "Tipo": {"select": {"name": tipo}},
        "GitHub": {"url": issue["url"]},
        "Descripción": {"rich_text": texto_notion(desc)},
        "Criterios de Aceptación": {"rich_text": texto_notion(criterios)},
    }
    personas = [
        EQUIPO[a["login"]] for a in issue["assignees"]["nodes"] if a["login"] in EQUIPO
    ]
    if personas:
        props["Responsable"] = {"people": [{"id": p} for p in personas]}
    padre = issue.get("parent") or {}
    numero = numero_de_epica(padre.get("title", ""))
    if epica_id and numero is not None:
        props["Épica"] = {"relation": [{"id": epica_id}]}
        props["Tipo PBI"] = {"select": {"name": f"Epica {numero}"}}

    if actual is None:
        props["Status"] = {"select": {"name": CERRADO if cerrado else ABIERTO}}
        props["Sprint"] = {"select": {"name": sprint}}
        props["Fecha Inicio"] = {"date": fecha(issue["createdAt"])}
        if cerrado:
            props["Fecha Fin"] = {"date": fecha(issue["closedAt"])}
        return props

    status = ((actual.get("Status") or {}).get("select") or {}).get("name")
    fin = (actual.get("Fecha Fin") or {}).get("date")
    if cerrado:
        # Una fila cerrada ya existente puede tener texto escrito a mano (Sprint 1):
        # solo se actualizan su estado y su fecha de cierre.
        props = {}
    if cerrado and status != CERRADO:
        props["Status"] = {"select": {"name": CERRADO}}
    if not cerrado and status == CERRADO:
        props["Status"] = {"select": {"name": ABIERTO}}
    if cerrado and not fin:
        props["Fecha Fin"] = {"date": fecha(issue["closedAt"])}
    if not cerrado and fin:
        props["Fecha Fin"] = {"date": None}
    return props


# --- GitHub y Notion -------------------------------------------------------------

CAMPOS_ISSUE = """
number title url state createdAt closedAt body
labels(first: 10) { nodes { name } }
assignees(first: 10) { nodes { login } }
parent { number title url }
"""


def _pedir(
    url: str, token: str, datos: Any = None, metodo: str = "POST", extra=None
) -> Any:
    cabeceras = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    cabeceras.update(extra or {})
    cuerpo = None if datos is None else json.dumps(datos).encode("utf-8")
    pedido = urllib.request.Request(url, data=cuerpo, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=30) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detalle = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"{metodo} {url} -> {error.code}: {detalle}") from None


def github(consulta: str, variables: dict[str, Any]) -> dict[str, Any]:
    datos = _pedir(
        "https://api.github.com/graphql",
        os.environ["GITHUB_TOKEN"],
        {"query": consulta, "variables": variables},
    )
    if datos.get("errors"):
        raise RuntimeError(f"GitHub: {datos['errors']}")
    return datos["data"]


def issue_de_github(dueno: str, repo: str, numero: int) -> dict[str, Any]:
    consulta = (
        "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r)"
        "{issue(number:$n){" + CAMPOS_ISSUE + "}}}"
    )
    return github(consulta, {"o": dueno, "r": repo, "n": numero})["repository"]["issue"]


def issues_recientes(dueno: str, repo: str, dias: int) -> list[dict[str, Any]]:
    """Issues abiertos y los cerrados en los últimos ``dias`` días."""
    consulta = (
        "query($o:String!,$r:String!,$c:String){repository(owner:$o,name:$r)"
        "{issues(first:100,after:$c,orderBy:{field:CREATED_AT,direction:ASC})"
        "{pageInfo{hasNextPage endCursor} nodes{" + CAMPOS_ISSUE + "}}}}"
    )
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    resultado, cursor = [], None
    while True:
        datos = github(consulta, {"o": dueno, "r": repo, "c": cursor})["repository"][
            "issues"
        ]
        for i in datos["nodes"]:
            cerrado = i["closedAt"] and datetime.fromisoformat(
                i["closedAt"].replace("Z", "+00:00")
            )
            if i["state"] == "OPEN" or (cerrado and cerrado >= limite):
                resultado.append(i)
        if not datos["pageInfo"]["hasNextPage"]:
            return resultado
        cursor = datos["pageInfo"]["endCursor"]


def notion(ruta: str, datos: Any = None, metodo: str = "POST") -> Any:
    return _pedir(
        f"{NOTION_API}/{ruta}",
        os.environ["NOTION_TOKEN"],
        datos,
        metodo,
        {"Notion-Version": NOTION_VERSION},
    )


def fila_por_enlace(base: str, enlace: str) -> dict[str, Any] | None:
    filtro = {
        "filter": {"property": "GitHub", "url": {"equals": enlace}},
        "page_size": 2,
    }
    filas = notion(f"databases/{base}/query", filtro)["results"]
    return filas[0] if filas else None


def sincronizar(
    issue: dict[str, Any],
    base: str,
    sprint: str,
    en_seco: bool,
    crear_cerrados: bool = True,
) -> str:
    """Crea o actualiza la fila de ``issue`` y devuelve qué hizo.

    Con ``crear_cerrados=False`` un issue cerrado sin fila se omite: la sincronización
    diaria no debe llenar el backlog con tareas viejas que el equipo decidió no traer.
    """
    fila = fila_por_enlace(base, issue["url"])
    if fila is None and issue["state"] == "CLOSED" and not crear_cerrados:
        return f"omitir #{issue['number']}: cerrado y sin fila en Notion"
    padre = issue.get("parent")
    epica = fila_por_enlace(base, padre["url"]) if padre else None
    props = propiedades(
        issue,
        fila["properties"] if fila else None,
        epica["id"] if epica else None,
        sprint,
    )
    accion = "actualizar" if fila else "crear"
    if en_seco:
        return f"[en seco] {accion} #{issue['number']}: {sorted(props)}"
    if fila:
        notion(f"pages/{fila['id']}", {"properties": props}, "PATCH")
    else:
        notion("pages", {"parent": {"database_id": base}, "properties": props})
    return f"{accion} #{issue['number']}"


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--issue", type=int, help="número del issue a sincronizar")
    grupo.add_argument(
        "--todos", action="store_true", help="abiertos y cerrados hace poco"
    )
    parser.add_argument(
        "--dias", type=int, default=30, help="con --todos: cerrados en N días"
    )
    parser.add_argument(
        "--en-seco", action="store_true", help="muestra qué haría, sin escribir"
    )
    args = parser.parse_args(argumentos)

    dueno, repo = os.environ["GITHUB_REPOSITORY"].split("/")
    base = os.environ["NOTION_DATABASE_ID"]
    sprint = os.environ.get("SPRINT_ACTUAL", "Sprint 2")
    if args.issue:
        issues = [issue_de_github(dueno, repo, args.issue)]
    else:
        issues = issues_recientes(dueno, repo, args.dias)
    # Las épicas van primero para que sus sub-issues las encuentren al enlazarse.
    issues.sort(
        key=lambda i: ETIQUETA_EPICA not in [e["name"] for e in i["labels"]["nodes"]]
    )
    fallos = 0
    for issue in issues:
        try:
            print(
                sincronizar(
                    issue, base, sprint, args.en_seco, crear_cerrados=bool(args.issue)
                )
            )
        except RuntimeError as error:
            fallos += 1
            print(f"error en #{issue['number']}: {error}", file=sys.stderr)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())

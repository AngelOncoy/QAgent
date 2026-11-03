"""Lectura estática de JaCoCo XML y conversión a la cobertura común (#182).

Los contadores de método se preservan: sus líneas no se suman para calcular
las del archivo, porque varios métodos pueden compartir una línea de fuente.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

LIMITE_XML_JACOCO = 5_000_000
LIMITE_DATOS = 200_000
_DOCTYPE = re.compile(
    r"""<!DOCTYPE\s+report\s+PUBLIC\s+(?P<a>['"])-//JACOCO//DTD Report 1\.1//EN(?P=a)\s+(?P<b>['"])report\.dtd(?P=b)\s*>"""
)
_TIPOS = frozenset({"INSTRUCTION", "BRANCH", "LINE", "COMPLEXITY", "METHOD", "CLASS"})


class CoberturaJacocoInvalida(ValueError):
    """El XML o los datos usados de cobertura no son válidos o son ambiguos."""


def leer_jacoco(dir_salida: str | Path) -> dict[str, Any] | None:
    """Lee jacoco.xml dentro de la salida del sandbox; None si falta o es inválido.

    No sigue enlaces a informes externos ni descarga report.dtd. Limita la lectura
    antes de decodificar y no ejecuta ni abre fuentes mencionadas por el XML.
    """
    raiz = Path(dir_salida)
    archivo = raiz / "jacoco.xml"
    try:
        if archivo.is_symlink() or not archivo.resolve().is_relative_to(raiz.resolve()):
            return None
        with archivo.open("rb") as entrada:
            datos = entrada.read(LIMITE_XML_JACOCO + 1)
        if len(datos) > LIMITE_XML_JACOCO:
            return None
        return interpretar_jacoco(datos.decode("utf-8-sig"))
    except (OSError, UnicodeError, CoberturaJacocoInvalida):
        return None


def interpretar_jacoco(xml: str) -> dict[str, Any] | None:
    """Convierte sourcefile/line y class/method sin inferir destinos de ramas.

    Las fuentes se identifican con la ruta Maven estándar src/main/java. La
    forma común files/totals incluye líneas ejecutadas/faltantes y una entrada
    de rama por contador con su línea de origen, sin inventar la línea destino.
    functions conserva los contadores exactos por método y descriptor JVM.
    None significa que el informe no ofrece líneas de fuente utilizables.

    Raises:
        CoberturaJacocoInvalida: XML inseguro, rutas, contadores o duplicados inválidos.
    """
    if not xml.strip() or len(xml.encode("utf-8")) > LIMITE_XML_JACOCO:
        raise CoberturaJacocoInvalida("El XML JaCoCo está vacío o supera el límite.")
    # Solo se elimina la declaración estándar; nunca se resuelve su DTD externa.
    xml = _DOCTYPE.sub("", xml, count=1)
    if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        raise CoberturaJacocoInvalida("JaCoCo declara entidades o una DTD no admitida.")
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as error:
        raise CoberturaJacocoInvalida("XML JaCoCo mal formado.") from error
    if raiz.tag != "report":
        raise CoberturaJacocoInvalida("Se esperaba la raíz report de JaCoCo.")
    archivos: dict[str, dict[str, Any]] = {}
    clases_vistas = set()
    presupuesto = 0
    for paquete in raiz.findall(".//package"):
        nombre = paquete.get("name")
        if nombre is None:
            raise CoberturaJacocoInvalida("Paquete JaCoCo sin nombre.")
        if nombre:
            _ruta_segura(nombre)
        for fuente in paquete.findall("sourcefile"):
            archivo = fuente.get("name", "")
            _ruta_segura(archivo, local=True)
            if not archivo.endswith(".java"):
                continue
            ruta = "/".join(p for p in ("src/main/java", nombre, archivo) if p)
            if ruta in archivos:
                raise CoberturaJacocoInvalida(
                    "Dos fuentes JaCoCo tienen la misma ruta."
                )
            ejecutadas, faltantes, ramas_ok, ramas_no = [], [], [], []
            lineas_vistas = set()
            for linea in fuente.findall("line"):
                numero = _entero(linea.get("nr"), positivo=True)
                if numero in lineas_vistas:
                    raise CoberturaJacocoInvalida(
                        "Una fuente repite el número de línea."
                    )
                lineas_vistas.add(numero)
                mi, ci, mb, cb = (
                    _entero(linea.get(k, "0")) for k in ("mi", "ci", "mb", "cb")
                )
                presupuesto += 1 + mb + cb
                if presupuesto > LIMITE_DATOS:
                    raise CoberturaJacocoInvalida(
                        "Demasiados datos de cobertura JaCoCo."
                    )
                if ci:
                    ejecutadas.append(numero)
                elif mi:
                    faltantes.append(numero)
                if cb and not ci:
                    raise CoberturaJacocoInvalida(
                        "Ramas cubiertas sin instrucciones cubiertas."
                    )
                if (mb or cb) and not (mi or ci):
                    raise CoberturaJacocoInvalida("Ramas sin instrucciones de fuente.")
                # La repetición representa cantidad de ramas, no arcos ni destinos.
                ramas_ok.extend([numero] * cb)
                ramas_no.extend([numero] * mb)
            resumen = _resumen(
                len(faltantes), len(ejecutadas), len(ramas_no), len(ramas_ok)
            )
            contadores = _contadores(fuente)
            for tipo, usado in (
                ("LINE", (len(faltantes), len(ejecutadas))),
                ("BRANCH", (len(ramas_no), len(ramas_ok))),
            ):
                if tipo in contadores and contadores[tipo] != usado:
                    raise CoberturaJacocoInvalida(
                        "Los contadores no coinciden con las líneas de fuente."
                    )
            archivos[ruta] = {
                "executed_lines": sorted(ejecutadas),
                "missing_lines": sorted(faltantes),
                "executed_branches": sorted(ramas_ok),
                "missing_branches": sorted(ramas_no),
                "summary": resumen,
                "functions": {},
            }
        por_nombre: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for clase in paquete.findall("class"):
            vm = clase.get("name", "")
            _ruta_segura(vm)
            if vm in clases_vistas:
                raise CoberturaJacocoInvalida("Clase JaCoCo duplicada.")
            clases_vistas.add(vm)
            if vm.rpartition("/")[0] != nombre:
                raise CoberturaJacocoInvalida(
                    "La clase no pertenece al paquete indicado."
                )
            archivo = clase.get("sourcefilename")
            if not archivo:
                continue  # Sin datos de depuración no se adivina una fuente.
            _ruta_segura(archivo, local=True)
            ruta = "/".join(p for p in ("src/main/java", nombre, archivo) if p)
            if ruta not in archivos:
                continue
            simple = vm.rsplit("/", 1)[-1]
            base = archivo.removesuffix(".java")
            if simple.startswith(base + "$"):
                simple = base + "." + simple[len(base) + 1 :].replace("$", ".")
            identidades = set()
            for metodo in clase.findall("method"):
                metodo_nombre, descriptor = metodo.get("name"), metodo.get("desc")
                if (
                    not metodo_nombre
                    or not descriptor
                    or not descriptor.startswith("(")
                    or ")" not in descriptor
                ):
                    raise CoberturaJacocoInvalida(
                        "Método JaCoCo sin nombre o descriptor válido."
                    )
                identidad = (metodo_nombre, descriptor)
                if identidad in identidades:
                    raise CoberturaJacocoInvalida("Método JaCoCo duplicado.")
                identidades.add(identidad)
                contadores = _contadores(metodo)
                lineas = contadores.get("LINE")
                ramas = contadores.get("BRANCH", (0, 0))
                clave = simple + "." + metodo_nombre
                por_nombre[ruta + "::" + clave].append(
                    {
                        "descriptor": descriptor,
                        "linea": _entero(metodo.get("line"), positivo=True)
                        if metodo.get("line") is not None
                        else None,
                        "summary": _resumen(*lineas, *ramas)
                        if lineas is not None
                        else None,
                    }
                )
        for clave, metodos in por_nombre.items():
            ruta, objetivo = clave.split("::", 1)
            if len(metodos) == 1:
                archivos[ruta]["functions"][objetivo] = metodos[0]
            else:
                for metodo in metodos:
                    archivos[ruta]["functions"][objetivo + metodo["descriptor"]] = (
                        metodo
                    )
    resumenes = [f["summary"] for f in archivos.values()]
    if not any(r["num_statements"] for r in resumenes):
        return None
    totales = _resumen(
        sum(r["missing_lines"] for r in resumenes),
        sum(r["covered_lines"] for r in resumenes),
        sum(r["missing_branches"] for r in resumenes),
        sum(r["covered_branches"] for r in resumenes),
    )
    return {"files": archivos, "totals": totales, "coverage_format": "jacoco"}


def cobertura_de_metodo(
    cobertura: dict[str, Any] | None, modulo: str, objetivo: str
) -> dict[str, float | None] | None:
    """Selecciona contadores exactos; no atribuye a un método las líneas de otro.

    Una sobrecarga sin descriptor, fuente desconocida o ausencia de datos devuelve
    None. Un método sin ramas conserva ramas=None; no se fabrica un 100 %.
    """
    datos = ((cobertura or {}).get("files") or {}).get(modulo.replace("\\", "/"), {})
    metodo = datos.get("functions", {}).get(objetivo)
    resumen = (metodo or {}).get("summary")
    if resumen is None or resumen["percent_covered"] is None:
        return None
    return {
        "lineas": resumen["percent_covered"],
        "ramas": resumen["percent_branches_covered"],
    }


def _entero(texto: str | None, positivo: bool = False) -> int:
    """Valida contadores y líneas enteras sin signos, decimales ni tamaños abusivos."""
    if texto is None or not re.fullmatch(r"[0-9]{1,9}", texto):
        raise CoberturaJacocoInvalida("Se esperaba un entero JaCoCo no negativo.")
    valor = int(texto)
    if positivo and valor == 0:
        raise CoberturaJacocoInvalida("Se esperaba una línea JaCoCo positiva.")
    return valor


def _ruta_segura(nombre: str, local: bool = False) -> None:
    """Rechaza rutas absolutas y componentes que permitirían salir del árbol lógico."""
    if (
        not nombre
        or any(c in nombre for c in ("\\", ":", "\x00"))
        or any(p in {"", ".", ".."} for p in nombre.split("/"))
        or (local and "/" in nombre)
    ):
        raise CoberturaJacocoInvalida("Ruta JaCoCo no válida.")


def _contadores(elemento: ET.Element) -> dict[str, tuple[int, int]]:
    """Lee métricas del elemento actual, evitando duplicados y contadores negativos."""
    resultado = {}
    for contador in elemento.findall("counter"):
        tipo = contador.get("type")
        if tipo not in _TIPOS or tipo in resultado:
            raise CoberturaJacocoInvalida("Contador JaCoCo desconocido o duplicado.")
        resultado[tipo] = (
            _entero(contador.get("missed")),
            _entero(contador.get("covered")),
        )
    return resultado


def _resumen(
    lineas_no: int, lineas_ok: int, ramas_no: int, ramas_ok: int
) -> dict[str, Any]:
    """Construye las métricas comunes; denominador cero significa dato no disponible."""
    lineas, ramas = lineas_no + lineas_ok, ramas_no + ramas_ok
    return {
        "num_statements": lineas,
        "covered_lines": lineas_ok,
        "missing_lines": lineas_no,
        "percent_covered": round(100 * lineas_ok / lineas, 2) if lineas else None,
        "num_branches": ramas,
        "covered_branches": ramas_ok,
        "missing_branches": ramas_no,
        "percent_branches_covered": round(100 * ramas_ok / ramas, 2) if ramas else None,
    }

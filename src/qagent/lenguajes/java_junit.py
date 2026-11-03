"""Interpreta diagnósticos JUnit/Surefire en el formato común de QAgent (#182).

Los esperado/obtenido son datos del informe, no oráculos para planificar pruebas.
Solo procesa XML y texto: nunca abre archivos de la traza ni ejecuta Java.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Any

from qagent.sandbox.informe_pytest import (
    LIMITE_TRAZA,
    LIMITE_XML,
    JUnitInvalido,
    Marco,
    parsear_junit,
    recortar_salida,
)

_MARCO_JAVA = re.compile(
    r"^\s*at\s+(?P<detalle>[^\s()]+)\((?P<archivo>[^\s():]+\.java):(?P<linea>[1-9]\d*)\)\s*$"
)
_COMPARACION_JAVA = re.compile(
    r"(?:.*? ==> )?expected: <(?P<esperado>.*?)> but was: <(?P<obtenido>.*?)>",
    re.DOTALL,
)
_NO_LANZO = re.compile(r"Expected ([\w.$]+) to be thrown, but nothing was thrown\.")
_ESTADO_MOCKMVC = re.compile(
    r"(?:Response status|Status) expected:<(?P<esperado>[1-5]\d{2})> but was:<(?P<obtenido>[1-5]\d{2})>"
)


def interpretar_junit_java(xml: str) -> dict[str, Any]:
    """Lee suites planas JUnit y añade tipo de error, comparaciones y marcos Java.

    Reutiliza casos y totales del lector común. Rechaza XML inseguro, suites
    anidadas, casos fuera de una suite, duraciones inválidas y estados conflictivos.
    Los números y objetos esperado/obtenido se conservan como texto, sin evaluarlos.
    Una comparación no reconocida mantiene su mensaje y traza sin inventar valores.

    Raises:
        JUnitInvalido: si el contenido no es un informe JUnit válido y acotado.
    """
    if len(xml.encode("utf-8")) > LIMITE_XML:
        raise JUnitInvalido("El junit.xml es demasiado grande.")
    informe = parsear_junit(xml)  # Valida tamaño, sintaxis y ausencia de entidades.
    raiz = ET.fromstring(xml)
    if raiz.tag not in {"testsuite", "testsuites"}:
        raise JUnitInvalido("Se esperaba testsuite o testsuites de JUnit.")
    suites = [raiz] if raiz.tag == "testsuite" else list(raiz)
    if any(s.tag != "testsuite" or s.find(".//testsuite") is not None for s in suites):
        raise JUnitInvalido("Se esperaban suites JUnit planas, sin anidamiento.")
    elementos = [c for suite in suites for c in suite.findall("testcase")]
    if len(elementos) != informe.total:
        raise JUnitInvalido("Hay casos JUnit fuera del nivel permitido de la suite.")
    if not elementos:
        raise JUnitInvalido("El informe JUnit no contiene casos ejecutados u omitidos.")
    if not math.isfinite(informe.duracion_s):
        raise JUnitInvalido("Duración total JUnit inválida.")
    for elemento in [*suites, *elementos]:
        try:
            tiempo = float(elemento.get("time", "0"))
        except ValueError as error:
            raise JUnitInvalido("Duración JUnit inválida.") from error
        if not math.isfinite(tiempo) or tiempo < 0:
            raise JUnitInvalido("Duración JUnit inválida.")
    for elemento, caso in zip(elementos, informe.casos):
        estados = [h for h in elemento if h.tag in {"failure", "error", "skipped"}]
        if len(estados) > 1:
            raise JUnitInvalido("Un caso JUnit declara estados incompatibles.")
        if not estados or estados[0].tag == "skipped":
            continue
        fallo = estados[0]
        caso.esperado = caso.obtenido = caso.operador = None
        caso.archivo = caso.linea = caso.codigo = None
        caso.tipo_error = fallo.get("type") or None
        texto = (fallo.text or "").strip("\n")
        caso.traza = recortar_salida(texto, LIMITE_TRAZA) if texto else None
        caso.pila = _pila(caso.traza or "")
        archivo_test = caso.ruta.rsplit(".", 1)[-1].split("$", 1)[0] + ".java"
        ubicacion = next(
            (m for m in caso.pila if m.archivo.rsplit("/", 1)[-1] == archivo_test), None
        )
        if ubicacion is not None:
            caso.archivo, caso.linea = ubicacion.archivo, ubicacion.linea
        if fallo.tag == "failure":
            mensaje = (caso.mensaje or "").strip()
            comparacion = _COMPARACION_JAVA.fullmatch(mensaje)
            # Más de un separador puede ser texto dentro del valor: no adivinar.
            if comparacion and mensaje.count("> but was: <") == 1:
                caso.esperado = comparacion["esperado"]
                caso.obtenido = comparacion["obtenido"]
                caso.operador = "=="
            estado_http = _ESTADO_MOCKMVC.fullmatch(mensaje)
            if estado_http:
                caso.esperado = estado_http["esperado"]
                caso.obtenido = estado_http["obtenido"]
                caso.operador = "=="
            no_lanzo = _NO_LANZO.fullmatch(mensaje)
            if no_lanzo:
                caso.esperado = "se lanza " + no_lanzo[1]
                caso.obtenido = "no se lanzó ninguna excepción"
                caso.operador = "throws"
    return informe.a_dict()


def _pila(texto: str) -> list[Marco]:
    """Conserva el orden de los marcos con fuente y línea, con un máximo de 128.

    Native Method, Unknown Source y resúmenes como ... N more quedan solo en la
    traza original, pues no ofrecen una ubicación verificable.
    """
    marcos = []
    for linea in texto.splitlines():
        encontrado = _MARCO_JAVA.fullmatch(linea)
        if encontrado:
            marcos.append(
                Marco(
                    encontrado["archivo"],
                    int(encontrado["linea"]),
                    encontrado["detalle"],
                )
            )
            if len(marcos) == 128:
                break
    return marcos

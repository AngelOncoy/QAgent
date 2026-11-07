"""Interpreta resultados de pruebas Vitest (JUnit XML o JSON) al formato común de QAgent (EP-11a).

Los esperado/obtenido se extraen del diagnóstico del informe para visualización,
sin usarlos nunca como oráculo de planificación. Solo procesa texto: nunca ejecuta
código ni abre archivos del host.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from typing import Any

from qagent.sandbox.informe_pytest import (
    LIMITE_TRAZA,
    LIMITE_XML,
    CasoPrueba,
    InformePytest,
    JUnitInvalido,
    Marco,
    parsear_junit,
    recortar_salida,
)

_MARCO_NODE = re.compile(
    r"^\s*at\s+(?:(?P<detalle>[^()\n]+?)\s+\()?(?:file:///)?(?P<archivo>[^\s():]+):(?P<linea>\d+):(?P<col>\d+)\)?$"
)

_COMPARACION_VITEST = re.compile(
    r"^(?:AssertionError:\s+)?expected\s+(?P<obtenido>.*?)\s+to\s+(?:deeply\s+)?(?:be|equal)\s+(?P<esperado>.*?)(?:\s+//.*)?$",
    re.DOTALL,
)
_COMPARACION_CLOSE = re.compile(
    r"^(?:AssertionError:\s+)?expected\s+(?P<obtenido>.*?)\s+to\s+be\s+close\s+to\s+(?P<esperado>.*?)\s+\+/-\s+.*$",
    re.DOTALL,
)
_NO_LANZO_VITEST = re.compile(
    r"^(?:AssertionError:\s+)?expected\s+.*?to\s+throw\s+(?:(?:an?\s+error|['\"]?(?P<esperado>[\w$]+)['\"]?))\s*.*?(?:but\s+(?:nothing|it\s+did\s+not)\s+throw.*)?$",
    re.IGNORECASE | re.DOTALL,
)
_COMPARACION_LENGTH = re.compile(
    r"^(?:AssertionError:\s+)?expected\s+.*?to\s+have\s+a\s+length\s+of\s+(?P<esperado>\d+)\s+but\s+got\s+(?P<obtenido>\d+)",
    re.DOTALL,
)


def _pila_node(texto: str) -> list[Marco]:
    """Extrae los marcos de la pila de una traza de Node / V8."""
    pila: list[Marco] = []
    for linea in texto.splitlines():
        coincidencia = _MARCO_NODE.match(linea)
        if not coincidencia:
            continue
        archivo = re.sub(r"^(?:file:///|\.\./)+", "", coincidencia.group("archivo"))
        linea_num = int(coincidencia.group("linea"))
        detalle = coincidencia.group("detalle") or ""
        pila.append(Marco(archivo, linea_num, detalle.strip()))
    return pila


def _extraer_comparacion(mensaje: str, caso: CasoPrueba) -> None:
    """Extrae esperado, obtenido y operador de los mensajes estándar de Chai/Vitest."""
    if not mensaje:
        return
    texto = mensaje.strip()
    m_igualdad = _COMPARACION_VITEST.match(texto)
    if m_igualdad:
        caso.obtenido = m_igualdad.group("obtenido").strip()
        caso.esperado = m_igualdad.group("esperado").strip()
        caso.operador = "=="
        return

    m_cercano = _COMPARACION_CLOSE.match(texto)
    if m_cercano:
        caso.obtenido = m_cercano.group("obtenido").strip()
        caso.esperado = m_cercano.group("esperado").strip()
        caso.operador = "=="
        return

    m_longitud = _COMPARACION_LENGTH.match(texto)
    if m_longitud:
        caso.obtenido = m_longitud.group("obtenido").strip()
        caso.esperado = m_longitud.group("esperado").strip()
        caso.operador = "=="
        return

    m_throw = _NO_LANZO_VITEST.match(texto)
    if m_throw:
        caso.esperado = m_throw.group("esperado") or "Error"
        caso.obtenido = None
        caso.operador = "throws"
        return


def interpretar_resultados_vitest(informe: str) -> dict[str, Any]:
    """Convierte el informe de Vitest (JUnit XML o JSON) a totales y casos comunes.

    Raises:
        JUnitInvalido: si el informe es inválido, mal formado o excede el límite de tamaño.
    """
    if not informe or not informe.strip():
        raise JUnitInvalido("El informe de pruebas de Vitest está vacío.")

    texto = informe.strip()
    if len(texto.encode("utf-8")) > LIMITE_XML:
        raise JUnitInvalido(
            "El informe de Vitest supera el límite de tamaño permitido."
        )

    if texto.startswith("{"):
        return _interpretar_json_vitest(texto)
    return _interpretar_junit_vitest(texto)


def _interpretar_junit_vitest(xml_texto: str) -> dict[str, Any]:
    """Interpreta un XML JUnit de Vitest."""
    informe = parsear_junit(xml_texto)
    try:
        raiz = ET.fromstring(xml_texto)
    except ET.ParseError as error:
        raise JUnitInvalido("XML JUnit mal formado.") from error

    if raiz.tag not in {"testsuite", "testsuites"}:
        raise JUnitInvalido("Se esperaba testsuite o testsuites en el XML de Vitest.")

    suites = [raiz] if raiz.tag == "testsuite" else list(raiz.findall("testsuite"))
    elementos = [c for suite in suites for c in suite.findall("testcase")]

    for elemento, caso in zip(elementos, informe.casos):
        estados = [h for h in elemento if h.tag in {"failure", "error", "skipped"}]
        if not estados or estados[0].tag == "skipped":
            continue

        fallo = estados[0]
        caso.esperado = caso.obtenido = caso.operador = None
        caso.archivo = caso.linea = caso.codigo = None
        caso.tipo_error = fallo.get("type") or None

        traza_texto = (fallo.text or "").strip("\n")
        caso.traza = recortar_salida(traza_texto, LIMITE_TRAZA) if traza_texto else None
        caso.pila = _pila_node(caso.traza or "")

        ubicacion = next(
            (
                m
                for m in caso.pila
                if any(
                    k in m.archivo.lower()
                    for k in ("generado", ".test.", ".spec.", "tests/")
                )
            ),
            None,
        )
        if ubicacion is not None:
            caso.archivo = PurePosixPath(ubicacion.archivo).name
            caso.linea = ubicacion.linea

        mensaje = (fallo.get("message") or caso.mensaje or "").strip()
        if not caso.tipo_error and mensaje:
            tipo_m = re.match(r"^([A-Za-z_$][\w$]*(?:Error|Exception))\b", mensaje)
            if tipo_m:
                caso.tipo_error = tipo_m.group(1)

        _extraer_comparacion(mensaje, caso)

    return informe.a_dict()


def _interpretar_json_vitest(json_texto: str) -> dict[str, Any]:
    """Interpreta el reporte JSON de Vitest (--reporter=json)."""
    try:
        datos = json.loads(json_texto)
    except json.JSONDecodeError as error:
        raise JUnitInvalido("JSON de Vitest mal formado.") from error

    if not isinstance(datos, dict):
        raise JUnitInvalido("Se esperaba un objeto JSON de Vitest.")

    inicio_ts = datos.get("startTime")
    fin_ts = datos.get("endTime")
    duracion_s = 0.0
    if (
        isinstance(inicio_ts, (int, float))
        and isinstance(fin_ts, (int, float))
        and fin_ts >= inicio_ts
    ):
        duracion_s = round((fin_ts - inicio_ts) / 1000.0, 3)

    casos: list[CasoPrueba] = []
    test_results = datos.get("testResults") or []
    for test_file in test_results:
        archivo_test = PurePosixPath(
            str(test_file.get("name", "")).replace("\\", "/")
        ).name
        for res in test_file.get("assertionResults") or []:
            partes_nombre = [
                *res.get("ancestorTitles", []),
                res.get("title", ""),
            ]
            nombre = " > ".join(p for p in partes_nombre if p).strip()
            status = res.get("status")
            duracion_caso = round(float(res.get("duration", 0.0) or 0.0) / 1000.0, 3)

            resultado_str = "paso"
            if status == "passed":
                resultado_str = "paso"
            elif status == "pending" or status == "skipped":
                resultado_str = "omitido"
            else:
                resultado_str = "fallo"

            mensajes_fallo = res.get("failureMessages") or []
            mensaje_principal = mensajes_fallo[0] if mensajes_fallo else None
            primer_linea = (
                mensaje_principal.splitlines()[0] if mensaje_principal else None
            )

            tipo_error = None
            if primer_linea:
                m_tipo = re.match(
                    r"^([A-Za-z_$][\w$]*(?:Error|Exception))\b", primer_linea
                )
                if m_tipo:
                    tipo_error = m_tipo.group(1)

            caso = CasoPrueba(
                nombre=nombre,
                ruta=archivo_test,
                resultado=resultado_str,
                duracion_s=duracion_caso,
                mensaje=primer_linea,
                tipo_error=tipo_error,
                traza=recortar_salida(mensaje_principal, LIMITE_TRAZA)
                if mensaje_principal
                else None,
            )
            if caso.traza:
                caso.pila = _pila_node(caso.traza)
                ubicacion = next(
                    (
                        m
                        for m in caso.pila
                        if any(
                            k in m.archivo.lower()
                            for k in ("generado", ".test.", ".spec.", "tests/")
                        )
                    ),
                    None,
                )
                if ubicacion is not None:
                    caso.archivo = PurePosixPath(ubicacion.archivo).name
                    caso.linea = ubicacion.linea

            if primer_linea:
                _extraer_comparacion(primer_linea, caso)

            casos.append(caso)

    informe = InformePytest(
        duracion_s=duracion_s,
        casos=casos,
    )
    return informe.a_dict()

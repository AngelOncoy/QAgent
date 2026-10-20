"""Lectura del `junit.xml` de pytest (EN-17): un registro por caso y dónde y por qué falló.

El sandbox deja el `junit.xml` junto a `coverage.json`. Este módulo lo convierte en datos
que el informe puede mostrar: resultado de cada caso, su duración, el archivo y la línea
del fallo, la línea de código que falló, el valor esperado y el obtenido, y la pila.

Solo lee texto: no ejecuta ni importa nada del código del usuario.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from qagent.sandbox.modelos import LimitesSandbox, ResultadoSandbox

#: Resultados posibles de un caso.
PASO, FALLO, ERROR, OMITIDO = "paso", "fallo", "error", "omitido"

#: Tope de caracteres de la traza de un caso y de la salida completa de un intento.
LIMITE_TRAZA = 8000
LIMITE_SALIDA = 20000
#: Tamaño máximo del `junit.xml` que se acepta leer (lo escribe el sandbox).
LIMITE_XML = 2_000_000

_MARCO = re.compile(r"^(?P<archivo>[^\s:][^:]*?\.py):(?P<linea>\d+):\s?(?P<resto>.*)$")
_TIPO_ERROR = re.compile(r"^[A-Za-z_][\w.]*$")
_COMPARACION = re.compile(
    r"^assert\s+(?P<obtenido>.+?)\s+(?P<operador>==|!=|>=|<=|>|<|is not|is|not in|in)\s+"
    r"(?P<esperado>.+)$"
)
_NO_LANZO = re.compile(r"DID NOT RAISE\s+(?:<class\s+')?(?P<tipo>[\w.]+)")


class JUnitInvalido(ValueError):
    """El `junit.xml` no se puede leer (vacío, demasiado grande o mal formado)."""


@dataclass
class Marco:
    """Un paso de la pila: archivo, línea y, si se conoce, la línea de código."""

    archivo: str
    linea: int
    detalle: str = ""
    codigo: str | None = None

    def a_dict(self) -> dict[str, Any]:
        return {
            "archivo": self.archivo,
            "linea": self.linea,
            "detalle": self.detalle,
            "codigo": self.codigo,
        }


@dataclass
class CasoPrueba:
    """Resultado de un caso de prueba (una función `test_*`)."""

    nombre: str
    ruta: str
    resultado: str
    duracion_s: float = 0.0
    mensaje: str | None = None
    tipo_error: str | None = None
    archivo: str | None = None
    linea: int | None = None
    codigo: str | None = None
    operador: str | None = None
    esperado: str | None = None
    obtenido: str | None = None
    traza: str | None = None
    pila: list[Marco] = field(default_factory=list)

    @property
    def paso(self) -> bool:
        return self.resultado == PASO

    def a_dict(self) -> dict[str, Any]:
        return {
            "nombre": self.nombre,
            "ruta": self.ruta,
            "resultado": self.resultado,
            "duracion_s": self.duracion_s,
            "mensaje": self.mensaje,
            "tipo_error": self.tipo_error,
            "archivo": self.archivo,
            "linea": self.linea,
            "codigo": self.codigo,
            "operador": self.operador,
            "esperado": self.esperado,
            "obtenido": self.obtenido,
            "traza": self.traza,
            "pila": [m.a_dict() for m in self.pila],
        }


@dataclass
class InformePytest:
    """Todos los casos de una ejecución de pytest y sus totales."""

    casos: list[CasoPrueba] = field(default_factory=list)
    duracion_s: float = 0.0
    inicio: str | None = None

    def _contar(self, resultado: str) -> int:
        return sum(1 for c in self.casos if c.resultado == resultado)

    @property
    def total(self) -> int:
        return len(self.casos)

    @property
    def pasaron(self) -> int:
        return self._contar(PASO)

    @property
    def fallaron(self) -> int:
        return self._contar(FALLO)

    @property
    def errores(self) -> int:
        return self._contar(ERROR)

    @property
    def omitidos(self) -> int:
        return self._contar(OMITIDO)

    def a_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "pasaron": self.pasaron,
            "fallaron": self.fallaron,
            "errores": self.errores,
            "omitidos": self.omitidos,
            "duracion_s": self.duracion_s,
            "inicio": self.inicio,
            "casos": [c.a_dict() for c in self.casos],
        }


def parsear_junit(xml: str) -> InformePytest:
    """Convierte el `junit.xml` de pytest en un `InformePytest`.

    Args:
        xml: contenido del archivo.

    Raises:
        JUnitInvalido: si está vacío, supera `LIMITE_XML`, declara entidades o no es XML.
    """
    if not xml or not xml.strip():
        raise JUnitInvalido("El junit.xml está vacío.")
    if len(xml) > LIMITE_XML:
        raise JUnitInvalido("El junit.xml es demasiado grande.")
    # El archivo lo escribe un proceso que ejecuta código ajeno: no se aceptan entidades.
    if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        raise JUnitInvalido("El junit.xml declara entidades; no se lee.")
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as error:
        raise JUnitInvalido(f"El junit.xml está mal formado: {error}") from error

    informe = InformePytest()
    for suite in raiz.iter("testsuite"):
        informe.inicio = informe.inicio or suite.get("timestamp")
        informe.duracion_s += _decimal(suite.get("time"))
        for caso in suite.iter("testcase"):
            informe.casos.append(_caso(caso))
    return informe


def _caso(elemento: ET.Element) -> CasoPrueba:
    nombre = elemento.get("name") or "(colección)"
    caso = CasoPrueba(
        nombre=nombre,
        ruta=elemento.get("classname") or "",
        resultado=PASO,
        duracion_s=_decimal(elemento.get("time")),
    )
    for hijo in elemento:
        if hijo.tag in ("failure", "error"):
            caso.resultado = FALLO if hijo.tag == "failure" else ERROR
            _detallar_fallo(caso, hijo.get("message") or "", hijo.text or "")
            break
        if hijo.tag == "skipped":
            caso.resultado = OMITIDO
            caso.mensaje = hijo.get("message") or None
            break
    return caso


def _detallar_fallo(caso: CasoPrueba, mensaje: str, texto: str) -> None:
    texto = texto.strip("\n")
    caso.mensaje = mensaje.strip() or None
    caso.traza = _recortar(texto, LIMITE_TRAZA) if texto else None
    caso.pila = _pila(texto)

    lineas_e = [
        m.group(1).rstrip() for m in re.finditer(r"^E\s{1,}(.*)$", texto, re.MULTILINE)
    ]
    if caso.pila:
        ultimo = caso.pila[-1]
        caso.archivo, caso.linea, caso.codigo = (
            ultimo.archivo,
            ultimo.linea,
            ultimo.codigo,
        )
        if _TIPO_ERROR.match(ultimo.detalle or ""):
            caso.tipo_error = ultimo.detalle
    if caso.tipo_error is None:
        caso.tipo_error = _tipo_desde_mensaje(caso.mensaje, lineas_e)

    primera = (caso.mensaje or (lineas_e[0] if lineas_e else "")).splitlines()
    primera_linea = primera[0].strip() if primera else ""
    comparacion = _COMPARACION.match(primera_linea)
    if comparacion:
        caso.obtenido = comparacion.group("obtenido")
        caso.operador = comparacion.group("operador")
        caso.esperado = comparacion.group("esperado")
        return
    no_lanzo = _NO_LANZO.search(caso.mensaje or "")
    if no_lanzo:
        caso.esperado = f"se lanza {no_lanzo.group('tipo')}"
        caso.obtenido = "no se lanzó ninguna excepción"


def _pila(texto: str) -> list[Marco]:
    """Pasos de la pila en el orden en que aparecen (el último es donde se lanzó)."""
    pila: list[Marco] = []
    pendiente: str | None = None
    lineas = texto.splitlines()
    for indice, linea in enumerate(lineas):
        if linea.startswith(">"):
            pendiente = linea[1:].strip()
            continue
        marco = _MARCO.match(linea.strip())
        if not marco or linea.startswith("E "):
            continue
        detalle = marco.group("resto").strip()
        codigo = pendiente
        if codigo is None and detalle.startswith("in "):
            # Formato corto: el código va en la línea siguiente, sangrado.
            siguiente = lineas[indice + 1] if indice + 1 < len(lineas) else ""
            if siguiente.startswith(" ") and not siguiente.strip().startswith("E "):
                codigo = siguiente.strip()
        archivo = re.sub(r"^(?:\.\./)+", "", marco.group("archivo"))
        pila.append(Marco(archivo, int(marco.group("linea")), detalle, codigo))
        pendiente = None
    return pila


def _tipo_desde_mensaje(mensaje: str | None, lineas_e: list[str]) -> str | None:
    for candidata in ([mensaje] if mensaje else []) + lineas_e[:1]:
        encontrado = re.match(
            r"^([A-Za-z_][\w.]*(?:Error|Exception|Failed|Warning))\b", candidata
        )
        if encontrado:
            return encontrado.group(1)
    return None


def _recortar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    mitad = limite // 2
    omitidos = len(texto) - 2 * mitad
    return f"{texto[:mitad]}\n… ({omitidos} caracteres omitidos) …\n{texto[-mitad:]}"


def recortar_salida(texto: str, limite: int = LIMITE_SALIDA) -> str:
    """Recorta la salida de pytest conservando el inicio y el final (donde está el resumen)."""
    return _recortar(texto or "", limite)


def _decimal(valor: str | None) -> float:
    try:
        return round(float(valor), 3) if valor is not None else 0.0
    except ValueError:
        return 0.0


_PLATAFORMA = re.compile(
    r"platform\s+(?P<plataforma>\S+)\s+--\s+Python\s+(?P<python>[\d.]+\w*),\s+pytest-(?P<pytest>[\d.]+\w*)"
)


def resumir_ejecucion(
    resultado: ResultadoSandbox,
    *,
    imagen: str,
    comando: list[str],
    limites: LimitesSandbox,
    lineas_sin_cubrir: list[int] | None = None,
    codigo_test: str | None = None,
) -> dict[str, Any]:
    """Resume una ejecución del sandbox para el campo `ejecucion` de `review_result`.

    Si el `junit.xml` falta o no es válido, `casos` queda vacío y la salida de pytest
    sigue disponible: el informe nunca depende de que el XML exista.
    """
    try:
        informe = parsear_junit(resultado.junit_xml) if resultado.junit_xml else None
    except JUnitInvalido:
        informe = None
    informe = informe or InformePytest()
    salida = "\n".join(p for p in (resultado.stdout, resultado.stderr) if p).strip()
    cabecera = _PLATAFORMA.search(salida)
    return {
        "exit_code": resultado.exit_code,
        "duracion_s": resultado.duracion_s,
        "timeout": resultado.timed_out,
        "oom": resultado.oom_killed,
        "salida": recortar_salida(salida),
        "codigo_test": codigo_test,
        "totales": {
            "total": informe.total,
            "pasaron": informe.pasaron,
            "fallaron": informe.fallaron,
            "errores": informe.errores,
            "omitidos": informe.omitidos,
        },
        "casos": [caso.a_dict() for caso in informe.casos],
        "lineas_sin_cubrir": lineas_sin_cubrir,
        "entorno": {
            "imagen": imagen,
            "comando": " ".join(resultado.comando or comando),
            "plataforma": cabecera.group("plataforma") if cabecera else None,
            "python": cabecera.group("python") if cabecera else None,
            "pytest": cabecera.group("pytest") if cabecera else None,
            "limites": {
                "cpus": limites.cpus,
                "memoria": limites.memoria,
                "timeout_s": limites.timeout_s,
            },
        },
    }

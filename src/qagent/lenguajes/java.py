"""Prototipo de análisis Java con tree-sitter (EN-19, ADR-009).

Solo lee fuentes UTF-8: no importa, compila ni ejecuta el proyecto analizado.
Extrae clases, constructores, métodos públicos, Javadoc y decisiones (#181). Excluye
src/test, carpetas generadas y enlaces simbólicos. Resuelve llamadas explícitas
del proyecto sin inferir tipos ni despacho dinámico. No extrae
endpoints Spring ni sobrecargas. Lee informes JUnit XML; la ejecución automática
y las demás extensiones siguen pendientes.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from tree_sitter import Node

from qagent.analysis.analyzer import calcular_huella
from qagent.lenguajes.base import (
    AdaptadorEnDesarrollo,
    EntornoSandbox,
    Estructura,
    ReglasPlanificacion,
)
from qagent.lenguajes.java_estructura import contar_decisiones, desglosar_javadoc
from qagent.lenguajes.java_llamadas import agregar_llamadas
from qagent.lenguajes.registro import listar_archivos
from qagent.lenguajes.treesitter import extraer_errores_sintaxis, obtener_parser
from qagent.sandbox.ejecucion import ARCHIVO_JUNIT, DIR_SALIDA, DIR_TESTS
from qagent.sandbox.informe_pytest import JUnitInvalido, parsear_junit
from qagent.sandbox.modelos import IMAGEN_JAVA

#: Herramientas que trae ``qagent-sandbox:java`` (``sandbox/Dockerfile.java``).
PAQUETES_JAVA = ("maven", "gradle", "junit-jupiter", "jacoco", "pitest")


def _texto(nodo: Node | None) -> str | None:
    """Devuelve el texto UTF-8 literal de un nodo, o None cuando no existe."""
    return nodo.text.decode("utf-8") if nodo is not None else None


def _javadoc(nodo: Node) -> str | None:
    """Devuelve solo el comentario Javadoc inmediatamente anterior, sin inferirlo."""
    anterior = nodo.prev_named_sibling
    texto = _texto(anterior)
    if (
        anterior is not None
        and anterior.type == "block_comment"
        and texto.startswith("/**")
    ):
        return texto
    return None


def _parametros(nodo: Node) -> list[dict[str, Any]]:
    """Extrae parámetros en orden; Java no admite valores por defecto.

    Conserva tipos escritos, genéricos, arrays y varargs sin resolver imports.
    """
    parametros = []
    for parametro in nodo.child_by_field_name("parameters").named_children:
        if parametro.type not in {"formal_parameter", "spread_parameter"}:
            continue
        nombre = parametro.child_by_field_name("name")
        tipo = parametro.child_by_field_name("type")
        if parametro.type == "spread_parameter":
            declarador = next(
                h for h in parametro.named_children if h.type == "variable_declarator"
            )
            nombre = declarador.child_by_field_name("name")
            tipo = next(
                h
                for h in parametro.named_children
                if h.type not in {"modifiers", "variable_declarator"}
            )
        texto_tipo = _texto(tipo)
        dimensiones = parametro.child_by_field_name("dimensions")
        if dimensiones is not None:
            texto_tipo += _texto(dimensiones)
        if parametro.type == "spread_parameter":
            texto_tipo += "..."
        parametros.append(
            {"nombre": _texto(nombre), "tipo": texto_tipo, "por_defecto": None}
        )
    return parametros


def _declaraciones(raiz: Node) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extrae clases y métodos públicos, sin entrar en cuerpos de métodos.

    Los constructores se describen dentro de su clase, sin ser objetivos.
    Rechaza nombres de métodos duplicados por sobrecarga para evitar objetivos
    ambiguos en el contrato Clase.metodo.
    """
    clases: list[dict[str, Any]] = []
    funciones: list[dict[str, Any]] = []
    nombres: set[str] = set()

    def visitar(contenedor: Node, prefijo: str = "") -> None:
        for nodo in contenedor.named_children:
            if nodo.type not in {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
            }:
                continue
            nombre = prefijo + (_texto(nodo.child_by_field_name("name")) or "")
            clases.append(
                {
                    "nombre": nombre,
                    "tipo": nodo.type,
                    "linea": nodo.start_point.row + 1,
                    "docstring": _javadoc(nodo),
                    "javadoc": desglosar_javadoc(_javadoc(nodo)),
                    "constructores": _constructores(nodo, nombre),
                }
            )
            cuerpo = nodo.child_by_field_name("body")
            if cuerpo is None:
                continue
            visitar(cuerpo, nombre + ".")
            for metodo in cuerpo.named_children:
                if metodo.type != "method_declaration":
                    continue
                modificadores = next(
                    (h for h in metodo.named_children if h.type == "modifiers"), None
                )
                tokens = (
                    {h.type for h in modificadores.children}
                    if modificadores is not None
                    else set()
                )
                publico = "public" in tokens or (
                    nodo.type == "interface_declaration" and "private" not in tokens
                )
                if not publico:
                    continue
                objetivo = nombre + "." + _texto(metodo.child_by_field_name("name"))
                if objetivo in nombres:
                    raise ValueError(
                        f"Sobrecarga no admitida en el prototipo: {objetivo}"
                    )
                nombres.add(objetivo)
                parametros = _parametros(metodo)
                retorno = _texto(metodo.child_by_field_name("type"))
                cuerpo_metodo = metodo.child_by_field_name("body")
                fin_firma = (
                    cuerpo_metodo.start_byte
                    if cuerpo_metodo is not None
                    else metodo.end_byte
                )
                firma = (
                    metodo.text[: fin_firma - metodo.start_byte]
                    .decode("utf-8")
                    .strip()
                    .rstrip(";")
                )
                ramas = contar_decisiones(metodo)
                funciones.append(
                    {
                        "nombre": objetivo,
                        "clase": nombre,
                        "linea": metodo.start_point.row + 1,
                        "firma": firma,
                        "parametros": parametros,
                        "retorno": retorno,
                        "docstring": _javadoc(metodo),
                        "javadoc": desglosar_javadoc(_javadoc(metodo)),
                        "ramas": ramas,
                        "critical": ramas > 0,
                        "es_static": "static" in tokens,
                        "tipada": retorno is not None
                        and all(p["tipo"] for p in parametros),
                        "es_async": False,
                    }
                )

    visitar(raiz)
    return clases, funciones


def _constructores(clase: Node, nombre: str) -> list[dict[str, Any]]:
    """Describe constructores explícitos de la clase, con visibilidad y Javadoc.

    No inventa el constructor implícito ni convierte constructores privados en
    objetivos. Los constructores sobrecargados se distinguen por su firma.
    """
    cuerpo = clase.child_by_field_name("body")
    if cuerpo is None:
        return []
    constructores = []
    for nodo in cuerpo.named_children:
        if nodo.type not in {
            "constructor_declaration",
            "compact_constructor_declaration",
        }:
            continue
        bloque = nodo.child_by_field_name("body")
        modificadores = next(
            (h for h in nodo.named_children if h.type == "modifiers"), None
        )
        tokens = (
            {h.type for h in modificadores.children}
            if modificadores is not None
            else set()
        )
        visibilidad = next(
            (v for v in ("public", "protected", "private") if v in tokens), "package"
        )
        parametros = nodo if nodo.type == "constructor_declaration" else clase
        fin = bloque.start_byte if bloque is not None else nodo.end_byte
        constructores.append(
            {
                "nombre": nombre,
                "linea": nodo.start_point.row + 1,
                "firma": nodo.text[: fin - nodo.start_byte].decode("utf-8").strip(),
                "parametros": _parametros(parametros),
                "visibilidad": visibilidad,
                "docstring": _javadoc(nodo),
                "javadoc": desglosar_javadoc(_javadoc(nodo)),
                "ramas": contar_decisiones(nodo),
            }
        )
    return constructores


class JavaAdapter(AdaptadorEnDesarrollo):
    """Análisis estático Java; ejecución y endpoints Spring todavía pendientes."""

    lenguaje = "java"
    extensiones = (".java",)
    marcadores = ("pom.xml", "build.gradle", "build.gradle.kts")
    frameworks_pruebas = ("junit5",)
    frameworks_app = ("spring",)

    def reglas_planificacion(self) -> ReglasPlanificacion:
        """Reglas Java/JUnit 5 para los prompts y filtros del Planner compartido (#181)."""
        from qagent.lenguajes.java_planificacion import REGLAS_PLANIFICACION_JAVA

        return REGLAS_PLANIFICACION_JAVA

    def objetivos(self, estructura: Estructura) -> list[dict[str, Any]]:
        """Lista métodos públicos del análisis y su criticidad por decisiones.

        Conserva las claves modulo, tipo y objetivo de la interfaz común y añade
        critical. Un constructor se registra como información de su clase.
        """
        return [
            {
                "modulo": m["ruta"],
                "tipo": "funcion",
                "objetivo": f["nombre"],
                "critical": f["ramas"] > 0,
            }
            for m in estructura.get("modulos", [])
            for f in m.get("funciones", [])
        ]

    def entorno_sandbox(self) -> EntornoSandbox:
        """Imagen ``qagent-sandbox:java`` (#169) y las carpetas comunes del sandbox."""
        return EntornoSandbox(
            imagen=IMAGEN_JAVA,
            paquetes_base=PAQUETES_JAVA,
            dir_tests=DIR_TESTS,
            dir_salida=DIR_SALIDA,
            informe=ARCHIVO_JUNIT,
        )

    def interpretar_resultados(self, informe: str) -> dict[str, Any]:
        """Convierte el contenido XML de Surefire/JUnit en resultados comunes.

        Devuelve total, pasaron, fallaron, errores, omitidos, duracion_s, inicio
        y casos. Reutiliza el lector de EN-17 y sus límites de tamaño y entidades.
        Acepta una testsuite o testsuites con suites planas, como escribe Surefire.
        Conserva mensajes y trazas Java; no infiere valores esperados ni convierte
        fallos en éxitos. La duración corresponde a suites, no al proceso Maven.

        Args:
            informe: contenido del XML, no la ruta del archivo.

        Raises:
            JUnitInvalido: si el XML es inseguro, inválido o tiene otra estructura.
        """
        resultado = parsear_junit(informe).a_dict()
        raiz = ET.fromstring(informe)  # El lector común ya validó tamaño y entidades.
        if raiz.tag not in {"testsuite", "testsuites"}:
            raise JUnitInvalido("Se esperaba testsuite o testsuites de JUnit.")
        suites = [raiz] if raiz.tag == "testsuite" else list(raiz)
        if any(
            s.tag != "testsuite" or s.find(".//testsuite") is not None for s in suites
        ):
            raise JUnitInvalido("Se esperaban suites JUnit planas, sin anidamiento.")
        return resultado

    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Devuelve diagnósticos de tree-sitter, o una lista vacía si es válido.

        No comprueba tipos ni reemplaza la compilación con javac.
        """
        raiz = obtener_parser("java").parse(codigo.encode("utf-8")).root_node
        return extraer_errores_sintaxis(raiz) if raiz.has_error else []

    def analizar(self, raiz: str | os.PathLike[str]) -> Estructura:
        """Lee fuentes Java y devuelve lenguaje, módulos, errores y resumen.

        Cada módulo conserva ruta POSIX, huella SHA-256, clases, funciones y
        endpoints vacíos. llama_a usa referencias ruta.java::Clase.metodo a
        destinos del proyecto resueltos sin inferencia de tipos. docstring
        contiene Javadoc literal o None. Los archivos
        inválidos se reportan en errores y no detienen el análisis de los demás.

        Raises:
            NotADirectoryError: si raiz no es una carpeta existente.
        """
        carpeta = Path(raiz)
        modulos = []
        errores = []
        parser = obtener_parser("java")
        arboles: dict[str, Node] = {}
        for relativa in listar_archivos(carpeta):
            partes = Path(relativa).parts
            if not self.es_fuente(relativa) or "test" in partes:
                continue
            archivo = carpeta / relativa
            if archivo.is_symlink() or any(
                p.is_symlink() for p in archivo.parents if p != carpeta.parent
            ):
                continue
            try:
                fuente = archivo.read_text(encoding="utf-8-sig")
                arbol = parser.parse(fuente.encode("utf-8"))
                if arbol.root_node.has_error:
                    raise ValueError(
                        "; ".join(extraer_errores_sintaxis(arbol.root_node))
                    )
                clases, funciones = _declaraciones(arbol.root_node)
            except (OSError, UnicodeError, ValueError, RecursionError) as error:
                errores.append(
                    {
                        "ruta": relativa,
                        "tipo": type(error).__name__,
                        "linea": None,
                        "mensaje": str(error),
                    }
                )
                continue
            modulos.append(
                {
                    "ruta": relativa,
                    "huella": calcular_huella(fuente),
                    "clases": clases,
                    "funciones": funciones,
                    "endpoints": [],
                }
            )
            arboles[relativa] = arbol.root_node
        agregar_llamadas(modulos, arboles)
        funciones = [f for m in modulos for f in m["funciones"]]
        return {
            "lenguaje": self.lenguaje,
            "modulos": modulos,
            "errores": errores,
            "resumen": {
                "total_modulos": len(modulos),
                "total_clases": sum(len(m["clases"]) for m in modulos),
                "total_funciones_publicas": len(funciones),
                "total_endpoints": 0,
                "total_errores": len(errores),
            },
        }

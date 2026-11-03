"""Preparación estática de PIT sobre una copia desechable del proyecto (#180).

No compila ni ejecuta Java. El llamador debe entregar la copia del sandbox,
nunca la carpeta original. Los POM y pruebas existentes no se sobrescriben.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

from tree_sitter import Node

from qagent.lenguajes.treesitter import obtener_parser
from qagent.sandbox.pit_comando import comando_pit

NS = "http://maven.apache.org/POM/4.0.0"
POM_NOMBRE = ".qagent-pit.xml"
TESTS_NOMBRE = ".qagent-pit-tests"
LIMITE_ARCHIVO = 2_000_000


class ConfiguracionPitPropia(ValueError):
    """El proyecto declara PIT; QAgent debe omitirlo sin reemplazar su configuración."""


def preparar_pit(
    copia: Path, pruebas: Path, modulo: str, funciones: list[str]
) -> dict[str, tuple[str, str]]:
    """Prepara POM y pruebas aprobadas en una copia y devuelve objetivos exactos.

    Args:
        copia: raíz de una copia desechable del proyecto, con pom.xml.
        pruebas: carpeta con el código de las pruebas ya aprobadas. Los nombres
            de entrada pueden ser los hashes del orquestador; se extrae el paquete
            y la clase pública para escribir el nombre .java exigido por javac.
        modulo: fuente estándar src/main/java/paquete/Clase.java.
        funciones: objetivos Clase.metodo críticos aprobados, sin sobrecargas.

    Returns:
        Objetivo -> (clase binaria completa, método), para verificar el XML PIT.
        Genera .qagent-pit.xml y .qagent-pit-tests; nunca cambia pom.xml ni src/test.
        Solo admite un módulo Maven con fuente estándar. Padres Maven, módulos
        y proyectos Gradle requieren resolución adicional; se rechazan explícitamente.

    Raises:
        ConfiguracionPitPropia: si se detecta PIT en POM o scripts Gradle.
        ValueError: si el proyecto, las pruebas o la selección no son inequívocos.
        OSError: si no es posible leer o escribir la copia.
    """
    comando_pit(modulo, funciones)  # Valida la selección antes de crear archivos.
    destino = copia / POM_NOMBRE
    carpeta_tests = copia / TESTS_NOMBRE
    reservados = (destino, carpeta_tests, copia / ".qagent-pit-target")
    if any(p.exists() or p.is_symlink() for p in reservados):
        raise ValueError("La copia ya contiene los archivos reservados de QAgent PIT.")
    pom = _xml_seguro(_leer_dentro(copia, copia / "pom.xml"))
    if pom.tag not in {"project", f"{{{NS}}}project"}:
        raise ValueError("El POM no contiene una raíz project válida.")
    if any(
        (n.text or "").strip() == "pitest-maven"
        for n in pom.findall(".//{*}artifactId")
    ):
        raise ConfiguracionPitPropia(
            "El POM declara PIT; QAgent no sobrescribe su configuración."
        )
    for nombre in (
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
    ):
        archivo = copia / nombre
        if archivo.exists() and "pitest" in _leer_dentro(copia, archivo).lower():
            raise ConfiguracionPitPropia(
                "El proyecto declara PIT en Gradle; se conserva su configuración."
            )
    if pom.find("{*}parent") is not None or pom.find("{*}modules") is not None:
        raise ValueError(
            "PIT requiere resolver herencia o módulos Maven antes de preparar este proyecto."
        )
    fuente = _leer_dentro(copia, copia / modulo.replace("\\", "/"))
    objetivos = _validar_objetivos(fuente, modulo, funciones)
    fuentes_tests: dict[Path, str] = {}
    for archivo in sorted(pruebas.rglob("*")):
        if not archivo.is_file():
            continue
        texto = _leer_dentro(pruebas, archivo)
        paquete, clase, arbol = _estructura(texto)
        clases = [n for n in arbol.named_children if n.type == "class_declaration"]
        if len(clases) != 1 or not clase:
            raise ValueError("Cada prueba aprobada debe declarar una sola clase Java.")
        relativa = (
            Path(*paquete.split("."), clase + ".java")
            if paquete
            else Path(clase + ".java")
        )
        if relativa in fuentes_tests:
            # #184 genera un ClaseTest por objetivo. Se aíslan los artefactos
            # aprobados solo en la copia, conservando cada cuerpo y aserción.
            indice = 2
            while relativa in fuentes_tests:
                nombre = f"{clase}QAgent{indice}Test"
                relativa = relativa.with_name(nombre + ".java")
                indice += 1
            texto = _renombrar_clase_prueba(texto, clases[0], nombre)
        fuentes_tests[relativa] = texto
    if not fuentes_tests:
        raise ValueError("No hay pruebas aprobadas para evaluar los mutantes.")
    preparado = copy.deepcopy(pom)
    ns = f"{{{NS}}}" if pom.tag.startswith("{") else ""
    build = _hijo(preparado, ns + "build")
    # Salidas nuevas: nunca se reutilizan clases compiladas de otra corrida.
    for nombre, sufijo in (
        ("directory", ""),
        ("outputDirectory", "/classes"),
        ("testOutputDirectory", "/test-classes"),
    ):
        _hijo(build, ns + nombre).text = "/work/proyecto/.qagent-pit-target" + sufijo
    _hijo(build, ns + "testSourceDirectory").text = "/work/proyecto/" + TESTS_NOMBRE
    # Mantiene las dependencias del proyecto y añade solo el proveedor JUnit de PIT.
    receta = _xml_seguro(
        (Path(__file__).parent / "java/calentamiento/pom.xml").read_text(
            encoding="utf-8"
        )
    )
    plugin = next(
        n
        for n in receta.findall(".//{*}plugin")
        if n.findtext("{*}artifactId") == "pitest-maven"
    )
    plugin = copy.deepcopy(plugin)
    propiedades = {
        n.tag.rsplit("}", 1)[-1]: n.text for n in receta.find("{*}properties")
    }
    for nodo in plugin.iter():
        if nodo.text and nodo.text.startswith("${") and nodo.text.endswith("}"):
            nodo.text = propiedades[nodo.text[2:-1]]
        if not ns:
            nodo.tag = nodo.tag.rsplit("}", 1)[-1]
    _hijo(build, ns + "plugins").append(plugin)
    # Maven exige project sin prefijo; conservar el namespace como predeterminado
    # sin modificar el registro global de namespaces de ElementTree.
    if ns:
        for nodo in preparado.iter():
            nodo.tag = nodo.tag.removeprefix(ns)
        preparado.set("xmlns", NS)
    for relativa, texto in fuentes_tests.items():
        archivo = carpeta_tests / relativa
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(texto, encoding="utf-8")
    with destino.open("xb") as archivo:
        ET.ElementTree(preparado).write(archivo, encoding="utf-8", xml_declaration=True)
    return objetivos


def _renombrar_clase_prueba(fuente: str, clase: Node, nombre: str) -> str:
    """Aísla una clase JUnit sin cambiar aserciones ni referencias ambiguas.

    Las pruebas directas generadas por #184 no dependen del nombre de su clase.
    Si otra parte del archivo referencia ese nombre, se rechaza la preparación
    para no alterar el significado de tipos, constructores o llamadas propias.
    El cambio usa posiciones de bytes del AST; no reemplaza comentarios o cadenas.
    """
    declaracion = clase.child_by_field_name("name")
    pendientes = [clase.parent]
    while pendientes:
        nodo = pendientes.pop()
        if (
            nodo.type in {"identifier", "type_identifier"}
            and nodo.text == declaracion.text
            and nodo.start_byte != declaracion.start_byte
        ):
            raise ValueError(
                "Una clase de prueba duplicada referencia su propio nombre; "
                "no se puede aislar sin cambiar su significado."
            )
        pendientes.extend(nodo.named_children)
    contenido = fuente.encode("utf-8")
    return (
        contenido[: declaracion.start_byte]
        + nombre.encode("utf-8")
        + contenido[declaracion.end_byte :]
    ).decode("utf-8")


def _leer_dentro(raiz: Path, archivo: Path) -> str:
    """Lee texto UTF-8 acotado; rechaza enlaces y rutas que salen de la raíz."""
    if archivo.is_symlink() or not archivo.resolve().is_relative_to(raiz.resolve()):
        raise ValueError("No se permiten fuentes o configuraciones fuera de la copia.")
    if archivo.stat().st_size > LIMITE_ARCHIVO:
        raise ValueError("El archivo supera el tamaño permitido para preparar PIT.")
    return archivo.read_text(encoding="utf-8-sig")


def _xml_seguro(texto: str) -> ET.Element:
    """Parsea un POM sin resolver entidades ni aceptar declaraciones externas."""
    if "<!DOCTYPE" in texto or "<!ENTITY" in texto:
        raise ValueError("El POM declara entidades no admitidas.")
    return ET.fromstring(texto)


def _hijo(padre: ET.Element, nombre: str) -> ET.Element:
    """Obtiene o crea un hijo del POM preparado, sin modificar el original."""
    existente = padre.find(nombre)
    return existente if existente is not None else ET.SubElement(padre, nombre)


def _estructura(fuente: str) -> tuple[str, str, Node]:
    """Extrae paquete y clase superior desde tree-sitter; rechaza sintaxis inválida."""
    raiz = obtener_parser("java").parse(fuente.encode("utf-8")).root_node
    if raiz.has_error:
        raise ValueError("La fuente Java tiene errores de sintaxis.")
    paquete = ""
    clase = ""
    for nodo in raiz.named_children:
        if nodo.type == "package_declaration":
            paquete = nodo.named_children[-1].text.decode("utf-8")
        if nodo.type == "class_declaration":
            clase = nodo.child_by_field_name("name").text.decode("utf-8")
    return paquete, clase, raiz


def _validar_objetivos(
    fuente: str, modulo: str, funciones: list[str]
) -> dict[str, tuple[str, str]]:
    """Contrasta paquete, clase y métodos con la fuente, rechazando sobrecargas."""
    paquete, clase, raiz = _estructura(fuente)
    esperada = f"{paquete}.{clase}" if paquete else clase
    desde_ruta = modulo.replace("\\", "/")[
        len("src/main/java/") : -len(".java")
    ].replace("/", ".")
    if esperada != desde_ruta:
        raise ValueError("El paquete o la clase no coincide con la ruta seleccionada.")
    clases = [n for n in raiz.named_children if n.type == "class_declaration"]
    if len(clases) != 1:
        raise ValueError("Se requiere una clase superior inequívoca para la mutación.")
    metodos = [
        n
        for n in clases[0].child_by_field_name("body").named_children
        if n.type == "method_declaration"
    ]
    nombres = [n.child_by_field_name("name").text.decode("utf-8") for n in metodos]
    resultado = {}
    for objetivo in funciones:
        metodo = objetivo.split(".")[-1]
        if nombres.count(metodo) != 1:
            raise ValueError(
                "El método crítico no existe o tiene sobrecargas no admitidas."
            )
        resultado[objetivo] = (esperada, metodo)
    return resultado

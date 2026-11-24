"""Ejecutabilidad estática de objetivos Java antes del Planner y el Generator (#301).

Clasifica cada método público como ``ejecutable``, ``no_ejecutable`` o
``pendiente_contexto`` con un motivo legible. Solo lee declaraciones de tree-sitter y
los ``pom.xml`` del proyecto: no compila, no carga clases y no ejecuta Java en el
host. La política vive en el adaptador Java (ADR-007); ningún LLM decide si un
objetivo se intenta (ADR-008).

- ``no_ejecutable``: no hay cuerpo que probar o el lenguaje impide alcanzarlo desde
  una prueba (método abstracto, clase contenedora ``private``, clase interna no
  estática, sin constructor accesible).
- ``pendiente_contexto``: el método tiene cuerpo, pero probarlo exige algo que el
  contrato no aporta y QAgent no inventa (una implementación de la interfaz, una
  subclase de la clase abstracta, una constante del enum o dependencias del
  constructor que no se pueden simular).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

EJECUTABLE = "ejecutable"
NO_EJECUTABLE = "no_ejecutable"
PENDIENTE_CONTEXTO = "pendiente_contexto"

_TIPOS_CONTENEDOR = {
    "class_declaration": "la clase",
    "interface_declaration": "la interfaz",
    "enum_declaration": "el enum",
    "record_declaration": "el record",
}
#: Valores que un caso del contrato aporta como literal; no son dependencias.
_SIMPLES = {
    "byte",
    "short",
    "int",
    "long",
    "float",
    "double",
    "boolean",
    "char",
    "Byte",
    "Short",
    "Integer",
    "Long",
    "Float",
    "Double",
    "Boolean",
    "Character",
    "String",
    "CharSequence",
    "BigDecimal",
    "BigInteger",
}
_COLECCIONES = {
    "List",
    "Set",
    "Map",
    "Collection",
    "Iterable",
    "Optional",
    "ArrayList",
    "HashSet",
    "HashMap",
    "LinkedList",
    "LinkedHashMap",
    "LinkedHashSet",
}
#: Artefactos que ponen Mockito en el classpath de pruebas.
_ARTEFACTOS_MOCKITO = re.compile(r"mockito-[\w.-]+|spring-boot-starter-test")


def resultado(estado: str, motivo: str | None = None) -> dict[str, Any]:
    """Clasificación serializable que viaja con la función del análisis."""
    return {"estado": estado, "motivo": motivo}


def motivo_no_planificable(funcion: dict[str, Any]) -> str | None:
    """Motivo de omisión si la función no es ejecutable; None si se puede intentar."""
    clasificacion = funcion.get("ejecutabilidad") or {}
    if clasificacion.get("estado", EJECUTABLE) == EJECUTABLE:
        return None
    return clasificacion.get("motivo") or "objetivo Java no ejecutable"


def clasificar_local(
    funcion: dict[str, Any], clases: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Reglas que solo dependen del archivo: cuerpo, visibilidad y construcción."""
    clase = clases[funcion["clase"]]
    descripcion = (
        f"{_TIPOS_CONTENEDOR.get(clase['tipo'], 'la clase')} {clase['nombre']}"
    )
    if funcion.get("abstracto"):
        return resultado(
            NO_EJECUTABLE,
            f"declaración abstracta sin cuerpo en {descripcion}: no hay "
            "implementación que probar",
        )
    partes = clase["nombre"].split(".")
    for indice in range(1, len(partes) + 1):
        contenedor = clases.get(".".join(partes[:indice]))
        if contenedor is not None and "private" in contenedor.get("modificadores", ()):
            return resultado(
                NO_EJECUTABLE,
                f"{contenedor['nombre']} es private: una prueba no puede acceder a ella",
            )
    if funcion.get("es_static"):
        return resultado(EJECUTABLE)
    if clase["tipo"] == "interface_declaration":
        return resultado(
            PENDIENTE_CONTEXTO,
            f"método default de {descripcion}: requiere una implementación concreta "
            "que QAgent no inventa",
        )
    if clase["tipo"] == "enum_declaration":
        return resultado(
            PENDIENTE_CONTEXTO,
            f"método de instancia de {descripcion}: requiere elegir una constante del "
            "enum y el contrato no la declara",
        )
    if "abstract" in clase.get("modificadores", ()):
        return resultado(
            PENDIENTE_CONTEXTO,
            f"{descripcion} es abstracta: requiere una subclase concreta que QAgent "
            "no inventa",
        )
    if _es_interna(clase):
        externa = clase["nombre"].rsplit(".", 1)[0]
        return resultado(
            NO_EJECUTABLE,
            f"{clase['nombre']} es una clase interna no estática: requiere una "
            f"instancia de la clase externa {externa}",
        )
    if clase["constructores"] and not constructores_accesibles(clase):
        return resultado(
            NO_EJECUTABLE,
            "la clase no tiene constructor accesible para una prueba en su paquete",
        )
    return resultado(EJECUTABLE)


def constructores_accesibles(clase: dict[str, Any]) -> list[dict[str, Any]]:
    """Constructores explícitos que una prueba del mismo paquete puede invocar."""
    return [
        c
        for c in clase["constructores"]
        if c["visibilidad"] in {"public", "protected", "package"}
    ]


def clasificar_dependencias(
    funcion: dict[str, Any], clase: dict[str, Any], con_mockito: bool | None
) -> dict[str, Any]:
    """Comprueba que algún constructor accesible tenga dependencias permitidas.

    Los valores simples (primitivos, envoltorios, texto y colecciones de ellos) los
    aporta el caso. Cualquier otro parámetro es una dependencia que la prueba solo
    puede simular con Mockito, que el sandbox no añade: debe declararlo el proyecto.
    Con ``con_mockito`` None (sin POM) no se bloquea por Mockito. Un parámetro del
    tipo de la propia clase nunca se acepta, porque simularlo sustituiría al
    objetivo (guardrail de ``java_oraculo``).
    """
    if con_mockito is None:
        con_mockito = True
    if funcion.get("es_static") or not clase["constructores"]:
        return resultado(EJECUTABLE)
    propia = clase["nombre"].rsplit(".", 1)[-1]
    faltantes: list[str] = []
    autorreferencia = False
    for constructor in constructores_accesibles(clase):
        dependencias = [
            p["tipo"]
            for p in constructor["parametros"]
            if not es_valor_simple(p.get("tipo") or "")
        ]
        if any(_base(t) == propia for t in dependencias):
            autorreferencia = True
            continue
        if not dependencias or con_mockito:
            return resultado(EJECUTABLE)
        faltantes.extend(dependencias)
    if autorreferencia and not faltantes:
        return resultado(
            PENDIENTE_CONTEXTO,
            f"el constructor recibe la propia clase ({propia}): simularla sustituiría "
            "al objetivo y el guardrail lo prohíbe",
        )
    tipos = ", ".join(dict.fromkeys(faltantes))
    return resultado(
        PENDIENTE_CONTEXTO,
        f"el constructor requiere dependencias ({tipos}) y el proyecto no declara "
        "Mockito para simularlas",
    )


def es_valor_simple(tipo: str) -> bool:
    """Si el caso puede dar el valor como literal (incluidas colecciones y arrays)."""
    tipo = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", tipo).strip()
    tipo = tipo.removesuffix("...").strip()
    while tipo.endswith("[]"):
        tipo = tipo[:-2].strip()
    base = _base(tipo)
    if base in _SIMPLES:
        return True
    if base in _COLECCIONES and "<" in tipo:
        argumentos = _argumentos_genericos(tipo)
        return bool(argumentos) and all(es_valor_simple(a) for a in argumentos)
    return False


def declara_mockito(raiz: Path, modulo: str) -> bool | None:
    """Si el ``pom.xml`` del módulo Maven o un padre en el proyecto declara Mockito.

    Revisa las dependencias efectivas (no ``dependencyManagement``) del POM del
    módulo y de las carpetas superiores hasta la raíz, que es donde vive el padre
    de un reactor. Un POM ilegible cuenta como «no declara»: nunca se ejecuta Maven.
    Devuelve None si no hay ningún POM: sin descriptor no se puede saber, y la
    corrida ya rechaza antes los proyectos Java que no son Maven.
    """
    from qagent.sandbox.maven import _leer_pom, separar_fuente
    from qagent.sandbox.modelos import ErrorConstruccionImagen

    try:
        carpeta, _ = separar_fuente(modulo)
    except ValueError:
        carpeta = ""
    raiz = raiz.resolve()
    actual = (raiz / carpeta).resolve() if carpeta else raiz
    hay_pom = False
    while True:
        pom = actual / "pom.xml"
        if pom.is_file() and not pom.is_symlink():
            hay_pom = True
            try:
                _, arbol = _leer_pom(pom)
            except ErrorConstruccionImagen:
                arbol = None
            if arbol is not None and _tiene_mockito(arbol):
                return True
        if actual == raiz or raiz not in actual.parents:
            return False if hay_pom else None
        actual = actual.parent


def _tiene_mockito(pom: Any) -> bool:
    dependencias = [
        *pom.findall("{*}dependencies/{*}dependency"),
        *pom.findall("{*}profiles/{*}profile/{*}dependencies/{*}dependency"),
    ]
    return any(
        _ARTEFACTOS_MOCKITO.fullmatch((d.findtext("{*}artifactId") or "").strip())
        for d in dependencias
    )


def _es_interna(clase: dict[str, Any]) -> bool:
    """Clase miembro sin ``static`` dentro de una clase, enum o record.

    Las interfaces, enums y records anidados, y todo lo declarado dentro de una
    interfaz, son implícitamente estáticos.
    """
    return (
        clase["tipo"] == "class_declaration"
        and clase.get("contenedor_tipo")
        in {"class_declaration", "enum_declaration", "record_declaration"}
        and "static" not in clase.get("modificadores", ())
    )


def _base(tipo: str) -> str:
    """Nombre simple sin paquete ni genéricos: ``java.util.List<X>`` → ``List``."""
    return tipo.split("<", 1)[0].strip().rsplit(".", 1)[-1]


def _argumentos_genericos(tipo: str) -> list[str]:
    interior = tipo[tipo.index("<") + 1 : tipo.rindex(">")] if ">" in tipo else ""
    argumentos, profundidad, actual = [], 0, ""
    for caracter in interior:
        if caracter == "<":
            profundidad += 1
        elif caracter == ">":
            profundidad -= 1
        if caracter == "," and profundidad == 0:
            argumentos.append(actual.strip())
            actual = ""
        else:
            actual += caracter
    if actual.strip():
        argumentos.append(actual.strip())
    return [a for a in argumentos if a != "?"]

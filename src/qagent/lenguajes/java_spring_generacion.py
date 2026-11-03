"""Plantilla MockMvc y comprobación AST declarativa, sin ejecutar Java (#183).

El dialecto inicial es deliberadamente acotado: permite formato, comentarios y
orden de imports; exige preservar petición, estado, controlador y mocks. No
acepta helpers, stubs del controlador ni código adicional que fabrique un fallo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from tree_sitter import Node

from qagent import contracts
from qagent.lenguajes.java_spring_planificacion import motivo_rechazo
from qagent.lenguajes.treesitter import obtener_parser

_IMPORTS = (
    "org.junit.jupiter.api.Test",
    "org.springframework.beans.factory.annotation.Autowired",
    "org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest",
    "org.springframework.boot.test.mock.mockito.MockBean",
    "org.springframework.test.context.ContextConfiguration",
    "org.springframework.test.web.servlet.MockMvc",
    "org.springframework.test.web.servlet.request.MockMvcRequestBuilders",
    "org.springframework.test.web.servlet.result.MockMvcResultMatchers",
)


def _cadena(valor: str) -> str:
    """Codifica un string Java sin interpolar instrucciones del contrato."""
    return json.dumps(valor, ensure_ascii=True)


def _valor_http(valor: Any) -> str:
    """Serializa valores escalares HTTP; rechaza objetos que no declara el contrato."""
    if isinstance(valor, bool):
        return str(valor).lower()
    if isinstance(valor, (str, int, float)):
        return str(valor)
    raise ValueError("El parámetro HTTP necesita un valor escalar explícito.")


def codigo_spring(contrato: dict[str, Any], contexto: dict[str, Any]) -> str:
    """Construye una plantilla revisable con los casos exactos del Planner.

    Solo genera texto: Maven/JUnit y la carga de Spring ocurren en Docker. Los
    servicios declarados se sustituyen por @MockBean; no se ejecuta un servicio
    real ni se inventan respuestas de negocio para sus mocks.
    """
    contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)
    endpoint = contexto.get("endpoint")
    if not endpoint:
        raise ValueError("Falta la declaración Spring real del endpoint.")
    for caso in contrato["casos"]:
        if problema := motivo_rechazo(endpoint, caso, {}):
            raise ValueError(problema)
    lineas = [f"package {contexto['paquete']};"] if contexto["paquete"] else []
    lineas += ["import " + nombre + ";" for nombre in _IMPORTS]
    lineas += [
        f"@WebMvcTest(controllers = {contexto['clase']}.class)",
        f"@ContextConfiguration(classes = {contexto['clase']}.class)",
        f"class {contexto['clase_test']} {{",
        "    @Autowired private MockMvc mvc;",
    ]
    for dependencia in endpoint.get("dependencias", []):
        lineas.append(
            f"    @MockBean private {dependencia['reemplazo']} mock_{dependencia['funcion']};"
        )
    for caso in contrato["casos"]:
        entrada = caso["entrada"]
        llamada = f"mvc.perform(MockMvcRequestBuilders.{entrada['metodo'].lower()}({_cadena(entrada['ruta'])})"
        for nombre, valor in sorted(entrada.get("query", {}).items()):
            valores = valor if isinstance(valor, list) else [valor]
            llamada += (
                ".param("
                + ", ".join(
                    [_cadena(nombre), *[_cadena(_valor_http(v)) for v in valores]]
                )
                + ")"
            )
        for nombre, valor in sorted(entrada.get("headers", {}).items()):
            llamada += f".header({_cadena(nombre)}, {_cadena(valor)})"
        if "json" in entrada:
            cuerpo = json.dumps(
                entrada["json"],
                ensure_ascii=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            llamada += f'.contentType("application/json").content({_cadena(cuerpo)})'
        estado = caso["valor_esperado"]["status_code"]
        llamada += f").andExpect(MockMvcResultMatchers.status().is({estado}));"
        lineas += [
            "    /** Comprueba la petición y el estado declarados en el contrato. */",
            f"    @Test void test_{caso['id']}() throws Exception {{",
            "        " + llamada,
            "    }",
        ]
    return "\n".join([*lineas, "}", ""])


def _firma_ast(codigo: str) -> tuple:
    """Representa todos los tokens salvo comentarios; normaliza el orden de imports.

    Incluye puntuación y literales: cambiar un operador, esperado, anotación,
    llamada o cuerpo no puede desaparecer al normalizar espacios.
    """
    if len(codigo.encode("utf-8")) > 2_000_000:
        raise ValueError("La prueba Spring excede el límite de análisis.")
    raiz = obtener_parser("java").parse(codigo.encode("utf-8")).root_node
    if raiz.has_error:
        raise ValueError("La prueba Spring tiene errores de sintaxis.")
    contador = 0

    def firma(nodo: Node) -> tuple:
        nonlocal contador
        contador += 1
        if contador > 30_000:
            raise ValueError("La prueba Spring tiene demasiados nodos.")
        hijos = [
            h for h in nodo.children if h.type not in {"line_comment", "block_comment"}
        ]
        return (
            (nodo.type, tuple(firma(h) for h in hijos))
            if hijos
            else (nodo.type, nodo.text.decode("utf-8"))
        )

    imports, declaraciones = [], []
    for nodo in raiz.named_children:
        if nodo.type in {"line_comment", "block_comment"}:
            continue
        (imports if nodo.type == "import_declaration" else declaraciones).append(
            firma(nodo)
        )
    return tuple(sorted(imports)), tuple(declaraciones)


def validar_spring(
    contrato: dict[str, Any], codigo: str, contexto: dict[str, Any]
) -> str | None:
    """Exige la plantilla segura; no transforma una expectativa para que pase."""
    try:
        if _firma_ast(codigo) != _firma_ast(codigo_spring(contrato, contexto)):
            return "Oráculo inválido: conserva la plantilla MockMvc: controlador, mocks, petición y estado exactos; sin helpers ni instrucciones adicionales."
    except (ValueError, KeyError, TypeError, RecursionError) as error:
        return "Oráculo inválido Spring: " + str(error)
    return None


def es_prueba_spring(codigo: str) -> bool:
    """Identifica el import concreto WebMvcTest para elegir el guardrail específico."""
    raiz = obtener_parser("java").parse(codigo.encode("utf-8")).root_node
    return any(
        n.type == "import_declaration"
        and n.text.decode("utf-8").strip()
        == "import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;"
        for n in raiz.named_children
    )


@dataclass(frozen=True)
class ComparacionSpring:
    """Resultado del guardrail compatible con la interfaz común del Reviewer."""

    es_laundering: bool
    resumen: str


def comparar_spring(original: str, reparado: str) -> ComparacionSpring:
    """Rechaza cambios de petición, esperado, mocks o contexto entre intentos."""
    try:
        cambiado = _firma_ast(original) != _firma_ast(reparado)
    except (ValueError, RecursionError):
        cambiado = True
    return ComparacionSpring(
        cambiado,
        "Assertion Laundering detectado: la reparación cambió la plantilla verificable MockMvc."
        if cambiado
        else "Sin Assertion Laundering: se conservaron petición, esperado y contexto MockMvc.",
    )

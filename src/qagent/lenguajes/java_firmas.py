"""Identidades de métodos Java y descriptores JVM, sin ejecutar fuentes (#299)."""

from __future__ import annotations

import re

from tree_sitter import Node

PRIMITIVOS = dict(
    zip(
        ["void", "boolean", "byte", "char", "short", "int", "long", "float", "double"],
        "VZBCSIJFD",
    )
)
JAVA_LANG = frozenset(
    [
        "String",
        "Object",
        "CharSequence",
        "Boolean",
        "Byte",
        "Character",
        "Short",
        "Integer",
        "Long",
        "Float",
        "Double",
        "Number",
        "Throwable",
        "Exception",
        "RuntimeException",
        "IllegalArgumentException",
        "IllegalStateException",
    ]
)


def separar_objetivo(objetivo: str) -> tuple[str, str]:
    """Separa clase y método tanto en identidades históricas como por firma."""
    return tuple(objetivo.partition("(")[0].rsplit(".", 1))


def tipo_borrado(tipo: str) -> str:
    """Normaliza espacios, genéricos y varargs como su array equivalente."""
    tipo = re.sub(r"\s+", "", tipo).replace("...", "[]")
    while "<" in tipo:
        nuevo = re.sub(r"<[^<>]*>", "", tipo)
        if nuevo == tipo:
            raise ValueError("Tipo Java con genéricos no balanceados.")
        tipo = nuevo
    return tipo


def tipos_de_parametros(metodo: Node) -> list[str]:
    """Extrae tipos declarados, incluidas dimensiones pospuestas y varargs."""
    from qagent.lenguajes.java import _parametros

    return [tipo_borrado(p["tipo"]) for p in _parametros(metodo)]


def sufijo_firma(tipos: list[str]) -> str:
    """Forma la parte estable de una identidad sin nombres de parámetros."""
    return "(" + ",".join(tipo_borrado(t) for t in tipos) + ")"


def tipos_descriptor(descriptor: str) -> list[str] | None:
    """Lee parámetros JVM; conserva tipos completos y dimensiones de arrays."""
    if not descriptor.startswith("(") or ")" not in descriptor:
        return None
    entrada = descriptor[1 : descriptor.index(")")]
    tipos = []
    inversa = {v: k for k, v in PRIMITIVOS.items() if k != "void"}
    while entrada:
        dimensiones = len(entrada) - len(entrada.lstrip("["))
        entrada = entrada[dimensiones:]
        if not entrada:
            return None
        if entrada[0] in inversa:
            tipo, entrada = inversa[entrada[0]], entrada[1:]
        elif entrada.startswith("L") and ";" in entrada:
            tipo, entrada = entrada[1:].split(";", 1)
            tipo = tipo.replace("/", ".").replace("$", ".")
        else:
            return None
        tipos.append(tipo + "[]" * dimensiones)
    return tipos


def coincide_descriptor(objetivo: str, descriptor: str) -> bool:
    """Compara una identidad canónica con parámetros JVM exactos, sin retorno."""
    if "(" not in objetivo or not objetivo.endswith(")"):
        return False
    parametros = objetivo.partition("(")[2][:-1]
    return tipos_descriptor(descriptor) == (parametros.split(",") if parametros else [])


def calificar_tipo(tipo: str, raiz: Node, clases: list[dict]) -> str:
    """Resuelve únicamente primitivos, java.lang, imports explícitos y tipos locales.

    Los imports comodín y variables genéricas se conservan sin adivinar paquetes;
    esas firmas no reciben métricas por descriptor hasta poder demostrarlas.
    """
    tipo = tipo_borrado(tipo)
    base = tipo.removesuffix("[]")
    while base.endswith("[]"):
        base = base[:-2]
    dimensiones = tipo[len(base) :]
    if base in PRIMITIVOS:
        return tipo
    imports = []
    paquete = ""
    for nodo in raiz.named_children:
        if nodo.type == "package_declaration":
            paquete = nodo.named_children[-1].text.decode("utf-8")
        if nodo.type == "import_declaration":
            texto = nodo.text.decode("utf-8")
            if not texto.startswith("import static "):
                imports.append(texto.removeprefix("import ").removesuffix(";").strip())
    candidatos = [i for i in imports if i.rsplit(".", 1)[-1] == base.split(".")[0]]
    if len(candidatos) == 1:
        base = candidatos[0] + base[len(base.split(".")[0]) :]
    elif base in JAVA_LANG and not any(c["nombre"] == base for c in clases):
        base = "java.lang." + base
    elif any(c["nombre"] == base for c in clases):
        base = (paquete + "." if paquete else "") + base
    return base + dimensiones


def indexar_metodos(raiz: Node) -> dict[str, Node]:
    """Indexa declaraciones públicas y privadas sin entrar en cuerpos locales."""
    from collections import Counter

    encontrados = []
    clases = []

    def visitar(contenedor: Node, prefijo: str = "") -> None:
        for clase in contenedor.named_children:
            if clase.type not in {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
            }:
                continue
            nombre = prefijo + clase.child_by_field_name("name").text.decode("utf-8")
            clases.append({"nombre": nombre})
            cuerpo = clase.child_by_field_name("body")
            if cuerpo is None:
                continue
            visitar(cuerpo, nombre + ".")
            for metodo in cuerpo.named_children:
                if metodo.type == "method_declaration":
                    encontrados.append((nombre, metodo))

    visitar(raiz)
    nombres = [
        c + "." + m.child_by_field_name("name").text.decode("utf-8")
        for c, m in encontrados
    ]
    cuentas = Counter(nombres)
    resultado = {}
    for nombre, (_, metodo) in zip(nombres, encontrados):
        if cuentas[nombre] > 1:
            nombre += sufijo_firma(
                [calificar_tipo(t, raiz, clases) for t in tipos_de_parametros(metodo)]
            )
        if nombre in resultado:
            # Dos declaraciones de la misma firma son Java inválido. No escoger
            # arbitrariamente una de ellas; sus vecinos siguen indexados.
            resultado[nombre] = None
        else:
            resultado[nombre] = metodo
    return {n: m for n, m in resultado.items() if m is not None}


def descriptor_metodo(metodo: Node, raiz: Node) -> str:
    """Construye un descriptor solo con tipos resolubles; nunca asume java.lang."""
    clases = [{"nombre": separar_objetivo(n)[0]} for n in indexar_metodos(raiz)]

    def descriptor(tipo: str) -> str:
        tipo = calificar_tipo(tipo, raiz, clases)
        dimensiones = 0
        while tipo.endswith("[]"):
            dimensiones += 1
            tipo = tipo[:-2]
        if tipo in PRIMITIVOS:
            valor = PRIMITIVOS[tipo]
        else:
            locales = [
                c["nombre"]
                for c in clases
                if tipo == c["nombre"] or tipo.endswith("." + c["nombre"])
            ]
            if locales:
                local = max(locales, key=len)
                tipo = tipo[: -len(local)] + local.replace(".", "$")
            elif "." not in tipo:
                raise ValueError("Tipo sin descriptor Java demostrable: " + tipo)
            valor = "L" + tipo.replace(".", "/") + ";"
        return "[" * dimensiones + valor

    retorno = metodo.child_by_field_name("type").text.decode("utf-8")
    dimensiones = metodo.child_by_field_name("dimensions")
    if dimensiones is not None:
        retorno += dimensiones.text.decode("utf-8")
    return (
        "("
        + "".join(descriptor(t) for t in tipos_de_parametros(metodo))
        + ")"
        + descriptor(retorno)
    )

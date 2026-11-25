"""DTO con Bean Validation en endpoints Spring, sin ejecutar Java (#306, ADR-024).

Lee con tree-sitter las restricciones de un DTO `@Valid @RequestBody` del
proyecto y comprueba los casos del Planner contra ellas: un cuerpo válido espera
el estado declarado y un cuerpo que incumple **una** restricción espera 400 con
origen `bean_validation` y esa restricción como evidencia. Todo lo que no se
puede representar sin adivinar (grupos, restricciones propias, Jackson, campos
compuestos, sin proveedor de validación, consejo global de errores) deja el DTO
como no representable, con su motivo, y no se planifican violaciones.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

from tree_sitter import Node

from qagent.lenguajes.java_spring import _atributos, _texto

ORIGEN = "bean_validation"
#: Resultado de `motivo_caso` cuando el caso no usa la validación del DTO.
NO_APLICA = "__no_aplica__"
#: Paquetes de Bean Validation (Jakarta EE 9+ y Java EE).
_PAQUETES = ("jakarta.validation", "javax.validation")
_RESTRICCIONES = {
    "NotNull",
    "NotBlank",
    "NotEmpty",
    "Size",
    "Min",
    "Max",
    "Positive",
    "PositiveOrZero",
    "Negative",
    "NegativeOrZero",
}
#: Atributos de cada restricción que se pueden representar.
_ATRIBUTOS = {
    "Size": {"min", "max", "message"},
    "Min": {"value", "message"},
    "Max": {"value", "message"},
}
_TEXTO = {"String", "CharSequence"}
_ENTEROS = {
    "int",
    "long",
    "short",
    "byte",
    "Integer",
    "Long",
    "Short",
    "Byte",
    "BigInteger",
}
_DECIMALES = {"double", "float", "Double", "Float", "BigDecimal"}
_BOOLEANOS = {"boolean", "Boolean"}
_PRIMITIVOS = {"int", "long", "short", "byte", "double", "float", "boolean"}
_ESCALARES = _TEXTO | _ENTEROS | _DECIMALES | _BOOLEANOS
#: Anotaciones que no cambian ni la forma del JSON ni la validación.
_NEUTRAS = ("lombok.", "io.swagger.")
_LOMBOK_ACCESO = {"Data", "Setter", "Getter", "Value"}
_PROVEEDORES = ("spring-boot-starter-validation", "hibernate-validator")
_LIMITE_POM = 1_000_000
_ENTERO = re.compile(r"-?\d+[lL]?")
# HV NotBlank usa String.trim(): quita los caracteres <= U+0020.
_ESPACIOS = "".join(chr(c) for c in range(33))


def _imports(raiz: Node) -> set[str]:
    return {
        _texto(h).removeprefix("import ").removesuffix(";").strip()
        for h in raiz.named_children
        if h.type == "import_declaration"
    }


def _paquete(raiz: Node) -> str:
    return next(
        (
            _texto(h).removeprefix("package ").removesuffix(";").strip()
            for h in raiz.named_children
            if h.type == "package_declaration"
        ),
        "",
    )


def _calificar(nombre: str, imports: set[str]) -> str:
    """Nombre completo de una anotación según los imports; vacío si no se sabe."""
    if "." in nombre:
        return nombre
    return next((i for i in imports if i.endswith("." + nombre)), "")


def _es_de(nombre: str, imports: set[str], paquetes: tuple[str, ...]) -> bool:
    """True si la anotación pertenece a uno de los paquetes (import o comodín)."""
    completo = _calificar(nombre, imports)
    if completo:
        return completo.startswith(paquetes)
    return any(
        i.endswith(".*") and i.removesuffix("*").startswith(paquetes) for i in imports
    )


def _anotaciones(nodo: Node) -> list[Node]:
    modificadores = next(
        (h for h in nodo.named_children if h.type == "modifiers"), None
    )
    return [
        h
        for h in (modificadores.named_children if modificadores is not None else [])
        if h.type in {"annotation", "marker_annotation"}
    ]


def _modificadores(nodo: Node) -> set[str]:
    modificadores = next(
        (h for h in nodo.named_children if h.type == "modifiers"), None
    )
    return {
        _texto(h)
        for h in (modificadores.children if modificadores is not None else [])
        if h.type not in {"annotation", "marker_annotation"}
    }


def parametro_validado(parametro: Node, imports: set[str]) -> bool:
    """`@Valid` de Bean Validation o `@Validated` de Spring sin grupos."""
    for anotacion in _anotaciones(parametro):
        nombre = _texto(anotacion.child_by_field_name("name"))
        corto = nombre.rsplit(".", 1)[-1]
        if corto == "Valid" and _es_de(nombre, imports, _PAQUETES):
            return True
        if (
            corto == "Validated"
            and anotacion.type == "marker_annotation"
            and _es_de(nombre, imports, ("org.springframework.validation",))
        ):
            return True
    return False


def _restricciones(
    nodo: Node, tipo: str, imports: set[str], dto: str, campo: str
) -> tuple[list[dict[str, Any]], str | None]:
    """Restricciones representables de un campo, o el motivo por el que no lo son."""
    resultado = []
    for anotacion in _anotaciones(nodo):
        nombre = _texto(anotacion.child_by_field_name("name"))
        corto = nombre.rsplit(".", 1)[-1]
        if _es_de(nombre, imports, _NEUTRAS):
            continue
        if corto == "Valid" or not _es_de(nombre, imports, _PAQUETES):
            return (
                [],
                f"{dto}.{campo} tiene @{corto}, que no es una restricción admitida",
            )
        if corto not in _RESTRICCIONES:
            return [], f"{dto}.{campo} usa @{corto}, una restricción aún no admitida"
        atributos = _atributos(anotacion)
        extra = set(atributos) - _ATRIBUTOS.get(corto, {"message"})
        if extra:
            return [], f"{dto}.{campo} usa @{corto} con {sorted(extra)} (p. ej. groups)"
        restriccion: dict[str, Any] = {"tipo": corto}
        for clave in ("min", "max", "value"):
            if clave in atributos:
                literal = _texto(atributos[clave]).replace(" ", "")
                if not _ENTERO.fullmatch(literal):
                    return [], f"{dto}.{campo}: @{corto} no usa un entero literal"
                restriccion[clave] = int(literal.rstrip("lL"))
        if corto in {"Min", "Max"} and "value" not in restriccion:
            return [], f"{dto}.{campo}: @{corto} sin valor"
        if corto in {"NotBlank", "NotEmpty", "Size"} and tipo not in _TEXTO:
            return [], f"{dto}.{campo}: @{corto} sobre {tipo} no es representable"
        if corto in {"Min", "Max"} and tipo not in _ENTEROS | {"BigDecimal"}:
            return [], f"{dto}.{campo}: @{corto} sobre {tipo} no es representable"
        if corto in {
            "Positive",
            "PositiveOrZero",
            "Negative",
            "NegativeOrZero",
        } and tipo not in (_ENTEROS | _DECIMALES):
            return [], f"{dto}.{campo}: @{corto} sobre {tipo} no es representable"
        resultado.append(restriccion)
    return resultado, None


def extraer_dtos(raiz: Node) -> dict[str, dict[str, Any]]:
    """DTO de primer nivel del archivo, por nombre completo, con campos o motivo."""
    imports, paquete = _imports(raiz), _paquete(raiz)
    resultado = {}
    for nodo in raiz.named_children:
        if nodo.type not in {"class_declaration", "record_declaration"}:
            continue
        nombre = _texto(nodo.child_by_field_name("name"))
        completo = f"{paquete}.{nombre}" if paquete else nombre
        resultado[completo] = _dto(nodo, nombre, imports)
    return resultado


def _dto(nodo: Node, nombre: str, imports: set[str]) -> dict[str, Any]:
    def no_representable(motivo: str) -> dict[str, Any]:
        return {"nombre": nombre, "campos": None, "motivo": motivo}

    lombok = set()
    for anotacion in _anotaciones(nodo):
        anotado = _texto(anotacion.child_by_field_name("name"))
        if not _es_de(anotado, imports, _NEUTRAS):
            return no_representable(
                f"{nombre} tiene @{anotado.rsplit('.', 1)[-1]} en la clase"
            )
        if _es_de(anotado, imports, ("lombok.",)):
            lombok.add(anotado.rsplit(".", 1)[-1])
    if nodo.child_by_field_name("type_parameters") is not None:
        return no_representable(f"{nombre} es genérico")
    if nodo.type == "class_declaration" and (
        nodo.child_by_field_name("superclass") is not None
    ):
        return no_representable(f"{nombre} hereda de otra clase")
    cuerpo = nodo.child_by_field_name("body")
    declaraciones = []
    if nodo.type == "record_declaration":
        parametros = nodo.child_by_field_name("parameters")
        for parametro in parametros.named_children if parametros is not None else []:
            if parametro.type != "formal_parameter":
                return no_representable(f"{nombre} tiene componentes variables")
            declaraciones.append(
                (
                    parametro,
                    _texto(parametro.child_by_field_name("type")),
                    _texto(parametro.child_by_field_name("name")),
                )
            )
    else:
        accesores = set()
        constructores = []
        for miembro in cuerpo.named_children if cuerpo is not None else []:
            if miembro.type == "method_declaration":
                accesores.add(_texto(miembro.child_by_field_name("name")))
            elif miembro.type == "constructor_declaration":
                constructores.append(miembro)
        if constructores and not any(
            not c.child_by_field_name("parameters").named_children
            for c in constructores
        ):
            return no_representable(f"{nombre} no tiene constructor sin argumentos")
        for miembro in cuerpo.named_children if cuerpo is not None else []:
            if miembro.type != "field_declaration":
                continue
            modificadores = _modificadores(miembro)
            if "static" in modificadores:
                continue
            tipo = _texto(miembro.child_by_field_name("type"))
            for declarador in miembro.named_children:
                if declarador.type != "variable_declarator":
                    continue
                campo = _texto(declarador.child_by_field_name("name"))
                sufijo = campo[:1].upper() + campo[1:]
                visible = (
                    "public" in modificadores
                    or lombok & _LOMBOK_ACCESO
                    or {"set" + sufijo, "get" + sufijo, "is" + sufijo} & accesores
                )
                if not visible:
                    return no_representable(
                        f"{nombre}.{campo} no es público ni tiene getter/setter: "
                        "Jackson no lo asignaría"
                    )
                declaraciones.append((miembro, tipo, campo))
    campos = []
    for declaracion, tipo, campo in declaraciones:
        simple = tipo.rsplit(".", 1)[-1]
        if simple not in _ESCALARES:
            return no_representable(
                f"{nombre}.{campo} es de tipo {tipo}, aún no representable"
            )
        restricciones, motivo = _restricciones(
            declaracion, simple, imports, nombre, campo
        )
        if motivo:
            return no_representable(motivo)
        campos.append({"nombre": campo, "tipo": simple, "restricciones": restricciones})
    if not any(c["restricciones"] for c in campos):
        return no_representable(f"{nombre} no declara restricciones de Bean Validation")
    return {"nombre": nombre, "campos": campos, "motivo": None}


#: `@ControllerAdvice`/`@RestControllerAdvice` en el texto de una fuente. Se busca
#: por texto, a propósito: una coincidencia de más (un comentario) solo omite casos;
#: una de menos aprobaría un 400 que la aplicación real no devuelve.
_CONSEJO = re.compile(r"@\s*(?:[\w.]+\.)?(?:Rest)?ControllerAdvice\b")
_LIMITE_FUENTE = 2_000_000
_LIMITE_ARCHIVOS = 20_000


def _con_manejador(raiz: Node) -> set[str]:
    """Clases del archivo con algún método `@ExceptionHandler` (nombre corto)."""
    clases = set()
    for nodo in raiz.named_children:
        if nodo.type != "class_declaration":
            continue
        cuerpo = nodo.child_by_field_name("body")
        for miembro in cuerpo.named_children if cuerpo is not None else []:
            if miembro.type == "method_declaration" and any(
                _texto(a.child_by_field_name("name")).rsplit(".", 1)[-1]
                == "ExceptionHandler"
                for a in _anotaciones(miembro)
            ):
                clases.add(_texto(nodo.child_by_field_name("name")))
    return clases


def _carpeta_maven(modulo: str) -> str:
    from qagent.sandbox.maven import separar_fuente

    try:
        return separar_fuente(modulo)[0]
    except ValueError:
        return ""


def _con_proveedor(carpeta: Path, modulo: str) -> bool:
    """Un proveedor de Bean Validation declarado en el POM del módulo o en el raíz."""
    candidatos = {carpeta / "pom.xml"}
    if carpeta_maven := _carpeta_maven(modulo):
        candidatos.add(carpeta / PurePosixPath(carpeta_maven) / "pom.xml")
    for pom in candidatos:
        try:
            if pom.is_symlink() or pom.stat().st_size > _LIMITE_POM:
                continue
            texto = pom.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(f"<artifactId>{p}</artifactId>" in texto for p in _PROVEEDORES):
            return True
    return False


def _cuerpo_validado(endpoint: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            p
            for p in endpoint.get("parametros", [])
            if p.get("vinculacion") == "RequestBody" and p.get("validado")
        ),
        None,
    )


def _nombre_completo(tipo: str, imports: set[str], paquete: str) -> str:
    if "." in tipo:
        return tipo
    return next(
        (i for i in imports if i.endswith("." + tipo)),
        (paquete + "." if paquete else "") + tipo,
    )


def _validacion(
    carpeta: Path,
    modulo: str,
    endpoint: dict[str, Any],
    tipo: str,
    dto: dict[str, Any] | None,
    consejo_global: bool,
    con_manejador: set[str],
) -> dict[str, Any]:
    """Decide si el DTO es representable; el primer motivo que aplica lo impide."""
    motivo = None
    if dto is None:
        motivo = (
            f"el DTO {tipo} no es una clase o record del mismo módulo Maven "
            "del controlador"
        )
    elif dto["motivo"]:
        motivo = dto["motivo"]
    elif endpoint["clase"] in con_manejador:
        motivo = (
            f"{endpoint['clase']} declara @ExceptionHandler: puede cambiar "
            "la respuesta de validación"
        )
    elif consejo_global:
        motivo = (
            "el proyecto tiene @ControllerAdvice: puede cambiar la respuesta "
            "de validación y @WebMvcTest no lo carga con el controlador aislado"
        )
    elif not _con_proveedor(carpeta, modulo):
        motivo = (
            "el POM no declara spring-boot-starter-validation ni "
            "hibernate-validator: @Valid no validaría"
        )
    return {
        "dto": dto["nombre"] if dto else tipo,
        "campos": None if motivo else dto["campos"],
        "motivo": motivo,
    }


def enlazar_validacion(
    carpeta: Path, modulos: list[dict[str, Any]], arboles: dict[str, Node]
) -> None:
    """Añade `validacion` a cada endpoint con un `@RequestBody` validado.

    `validacion` es `{dto, campos, motivo}`: con `campos` se pueden planificar
    violaciones; con `motivo` no, y el motivo explica por qué. El DTO se busca en
    el mismo módulo Maven que el controlador, igual que `revalidar_endpoint`.
    """
    dtos: dict[tuple[str, str], dict[str, Any]] = {}
    consejo_global = False
    for relativa, raiz in arboles.items():
        carpeta_maven = _carpeta_maven(relativa)
        for completo, dto in extraer_dtos(raiz).items():
            dtos[(carpeta_maven, completo)] = dto
        consejo_global = consejo_global or bool(
            _CONSEJO.search(raiz.text.decode("utf-8", errors="replace"))
        )
    for modulo in modulos:
        raiz = arboles.get(modulo["ruta"])
        if raiz is None:
            continue
        imports, carpeta_maven = _imports(raiz), _carpeta_maven(modulo["ruta"])
        con_manejador = _con_manejador(raiz)
        for endpoint in modulo.get("endpoints", []):
            cuerpo = _cuerpo_validado(endpoint)
            if cuerpo is None:
                continue
            completo = _nombre_completo(cuerpo["tipo"], imports, endpoint["paquete"])
            endpoint["validacion"] = _validacion(
                carpeta,
                modulo["ruta"],
                endpoint,
                cuerpo["tipo"],
                dtos.get((carpeta_maven, completo)),
                consejo_global,
                con_manejador,
            )


def _fuentes_java(carpeta: Path):
    """Fuentes .java del proyecto, sin carpetas ocultas ni de construcción."""
    vistos = 0
    for actual, carpetas, archivos in os.walk(carpeta):
        carpetas[:] = [
            c
            for c in carpetas
            if not c.startswith(".") and c not in {"target", "build", "node_modules"}
        ]
        for nombre in archivos:
            if nombre.endswith(".java"):
                vistos += 1
                if vistos > _LIMITE_ARCHIVOS:
                    return
                yield Path(actual) / nombre


def _hay_consejo(carpeta: Path) -> bool:
    for archivo in _fuentes_java(carpeta):
        try:
            if archivo.is_symlink() or archivo.stat().st_size > _LIMITE_FUENTE:
                continue
            if _CONSEJO.search(archivo.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def revalidar_endpoint(
    carpeta: Path, modulo: str, raiz: Node, endpoint: dict[str, Any]
) -> None:
    """Recalcula `validacion` desde las fuentes actuales, para el guardrail.

    Lee el DTO de su archivo en el mismo módulo Maven y busca consejos globales en
    el proyecto con la misma regla que el análisis; nunca confía en el contrato.
    """
    from qagent.lenguajes.treesitter import obtener_parser

    endpoint.pop("validacion", None)
    cuerpo = _cuerpo_validado(endpoint)
    if cuerpo is None:
        return
    completo = _nombre_completo(cuerpo["tipo"], _imports(raiz), endpoint["paquete"])
    relativa = PurePosixPath(
        _carpeta_maven(modulo) or ".", "src/main/java", *completo.split(".")
    )
    archivo = carpeta / (str(relativa) + ".java")
    dto = None
    try:
        dentro = archivo.resolve().is_relative_to(carpeta.resolve())
        if (
            dentro
            and archivo.is_file()
            and not archivo.is_symlink()
            and archivo.stat().st_size <= _LIMITE_FUENTE
        ):
            fuente = archivo.read_text(encoding="utf-8-sig")
            arbol = obtener_parser("java").parse(fuente.encode("utf-8"))
            if not arbol.root_node.has_error:
                dto = extraer_dtos(arbol.root_node).get(completo)
    except (OSError, UnicodeError, ValueError):
        dto = None
    endpoint["validacion"] = _validacion(
        carpeta,
        modulo,
        endpoint,
        cuerpo["tipo"],
        dto,
        _hay_consejo(carpeta),
        _con_manejador(raiz),
    )


def _longitud(texto: str) -> int:
    """Longitud como String.length() de Java (unidades UTF-16)."""
    return len(texto.encode("utf-16-le")) // 2


def _tipo_valido(tipo: str, valor: Any) -> bool:
    """El valor JSON es del tipo que Jackson asigna a ese campo sin coerciones."""
    if valor is None:
        return tipo not in _PRIMITIVOS
    if tipo in _TEXTO:
        return isinstance(valor, str)
    if tipo in _BOOLEANOS:
        return isinstance(valor, bool)
    if isinstance(valor, bool):
        return False
    if tipo in _ENTEROS:
        return isinstance(valor, int)
    return isinstance(valor, (int, float))


def _cumple(restriccion: dict[str, Any], valor: Any) -> bool:
    """Semántica de Hibernate Validator para las restricciones admitidas."""
    tipo = restriccion["tipo"]
    if tipo == "NotNull":
        return valor is not None
    if tipo == "NotBlank":
        return valor is not None and bool(valor.strip(_ESPACIOS))
    if tipo == "NotEmpty":
        return valor is not None and _longitud(valor) > 0
    if valor is None:
        return True  # las demás aceptan null (Bean Validation 2.0, sección 2.4)
    if tipo == "Size":
        return (
            restriccion.get("min", 0)
            <= _longitud(valor)
            <= restriccion.get("max", 2**31 - 1)
        )
    if tipo == "Min":
        return valor >= restriccion["value"]
    if tipo == "Max":
        return valor <= restriccion["value"]
    return {
        "Positive": valor > 0,
        "PositiveOrZero": valor >= 0,
        "Negative": valor < 0,
        "NegativeOrZero": valor <= 0,
    }[tipo]


def violaciones(validacion: dict[str, Any], cuerpo: Any) -> list[str] | str:
    """Restricciones incumplidas por el cuerpo, o el motivo si no es comparable.

    El cuerpo debe ser un objeto con exactamente los campos del DTO y valores del
    tipo JSON de cada campo. Devuelve `Dto.campo@Restriccion` por cada violación.
    """
    if not isinstance(cuerpo, dict):
        return "el cuerpo no es un objeto JSON con los campos del DTO"
    campos = {c["nombre"]: c for c in validacion["campos"]}
    if set(cuerpo) != set(campos):
        return (
            "el cuerpo debe tener exactamente los campos del DTO "
            f"{sorted(campos)}; recibió {sorted(cuerpo)}"
        )
    resultado = []
    for nombre, campo in campos.items():
        valor = cuerpo[nombre]
        if not _tipo_valido(campo["tipo"], valor):
            return f"{nombre}: el valor no es compatible con {campo['tipo']}"
        for restriccion in campo["restricciones"]:
            if not _cumple(restriccion, valor):
                resultado.append(f"{validacion['dto']}.{nombre}@{restriccion['tipo']}")
    return resultado


def motivo_caso(endpoint: dict[str, Any], caso: dict[str, Any]) -> str | None:
    """Contrasta un caso con el DTO validado; None si no le aplica o es correcto.

    Devuelve `NO_APLICA` si el endpoint o el caso no usan validación de DTO, para
    que continúen las reglas de #183.
    """
    validacion = endpoint.get("validacion")
    entrada = caso.get("entrada") or {}
    if caso.get("origen") == ORIGEN:
        if not validacion or not validacion.get("campos"):
            motivo = (validacion or {}).get("motivo") or "el endpoint no valida un DTO"
            return "sin resultado esperado verificable de Bean Validation: " + motivo
        if (caso.get("valor_esperado") or {}).get("status_code") != 400:
            return "una violación de Bean Validation solo respalda un 400"
        if caso.get("categoria") != "error":
            return "una violación de Bean Validation es un caso de categoría error"
        encontradas = violaciones(validacion, entrada.get("json"))
        if isinstance(encontradas, str):
            return "el cuerpo no es comparable con el DTO: " + encontradas
        if len(encontradas) != 1:
            return (
                "el cuerpo debe incumplir exactamente una restricción del DTO; "
                f"incumple {encontradas or 'ninguna'}"
            )
        if caso.get("evidencia") != encontradas:
            return (
                f"la evidencia debe citar la restricción incumplida {encontradas}; "
                f"cita {caso.get('evidencia')}"
            )
        return None
    if validacion and validacion.get("campos") and entrada.get("json") is not None:
        encontradas = violaciones(validacion, entrada["json"])
        if isinstance(encontradas, str):
            return "el cuerpo no es comparable con el DTO: " + encontradas
        if encontradas:
            return (
                f"el cuerpo incumple {encontradas}: solo respalda un 400 de "
                "origen bean_validation"
            )
    return NO_APLICA


def declaracion_para_planner(endpoint: dict[str, Any]) -> dict[str, Any] | None:
    """Restricciones que se envían al Planner; nunca cuerpos ni implementación."""
    validacion = endpoint.get("validacion")
    if not validacion:
        return None
    if not validacion.get("campos"):
        return {"dto": validacion["dto"], "no_representable": validacion["motivo"]}
    return {"dto": validacion["dto"], "campos": validacion["campos"]}

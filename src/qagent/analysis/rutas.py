"""Rutas FastAPI, modelos Pydantic y mapa de llamadas (EN-14).

Segunda pasada del analizador estático (EN-02): recibe el árbol de tree-sitter de
**todos** los módulos del proyecto (TA-16) y extrae, sin ejecutar nada:

* **Endpoints**: cada función decorada con ``@app.<método>`` o
  ``@router.<método>`` (``get``, ``post``, ``put``, ``patch``, ``delete`` y
  ``api_route``) sobre un objeto ``FastAPI()`` o ``APIRouter()``. Por endpoint:
  método, ruta completa (con los prefijos de ``APIRouter(prefix=...)`` y de
  ``include_router(..., prefix=...)``), parámetros de ruta, de consulta y de
  cabecera, modelo del cuerpo, ``response_model``, ``status_code`` (200 si no se
  declara), dependencias ``Depends(...)``, las ``HTTPException`` que lanza, la
  función que la atiende (``manejador``), su rango de líneas y las ``ramas`` del
  manejador (misma regla que en funciones, #74).
* **Modelos Pydantic**: clases que heredan de ``BaseModel`` (directa o
  indirectamente dentro del proyecto), con sus campos, tipos, valores por
  defecto y restricciones de ``Field`` (``gt``, ``ge``, ``min_length``…).
* **llama_a**: funciones públicas del proyecto que llama cada función o
  endpoint, resueltas por nombre (mismo módulo e imports del proyecto, con
  alias), en formato ``ruta/del/modulo.py::funcion`` (ADR-002, opción C).

La resolución es *best-effort*: un prefijo que no es un texto literal, o un
router que no se incluye en ninguna app del proyecto, deja la ruta con
``resuelta: False`` en vez de inventarla.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from tree_sitter import Node, Tree

from qagent.analysis import texto_ts
from qagent.analysis.arbol_ts import (
    POSICIONAL,
    POSICIONAL_SOLO,
    SOLO_NOMBRE,
    campo,
    cuerpo,
    decoradores,
    definicion,
    es_async,
    es_clase,
    es_funcion,
    hijos,
    importacion,
    linea,
    linea_fin,
    nombrados,
    nombre,
    parametros,
    recorrer,
    sentencias,
    sin_envoltura,
    texto,
)
from qagent.analysis.ramas import contar_ramas

#: Métodos HTTP que QAgent prueba (los del contrato planner_contract.v2).
METODOS = ("GET", "POST", "PUT", "PATCH", "DELETE")
#: Parámetros que FastAPI inyecta él mismo: no son datos de la petición.
TIPOS_ESPECIALES = frozenset(
    {"Request", "Response", "BackgroundTasks", "WebSocket", "HTTPConnection"}
)
#: Restricciones de ``Field``/``Query``/``Path`` que sirven de oráculo (casos 422).
RESTRICCIONES = (
    "gt",
    "ge",
    "lt",
    "le",
    "min_length",
    "max_length",
    "pattern",
    "regex",
    "multiple_of",
    "max_digits",
    "decimal_places",
)
_PARAM_RUTA = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)(?::[^}]*)?}")
_NODOS_ANIDADOS = frozenset(
    {"function_definition", "class_definition", "decorated_definition", "lambda"}
)
#: Sentencias compuestas en cuyos bloques se buscan definiciones de módulo.
_COMPUESTAS = frozenset(
    {
        "if_statement",
        "try_statement",
        "with_statement",
        "match_statement",
        "for_statement",
        "while_statement",
    }
)
_CLAUSULAS = frozenset(
    {
        "elif_clause",
        "else_clause",
        "except_clause",
        "except_group_clause",
        "finally_clause",
        "case_clause",
    }
)


# --------------------------------------------------------------------------- #
# Tabla de símbolos del proyecto
# --------------------------------------------------------------------------- #
def sentencias_modulo(raiz: Node) -> Iterator[Node]:
    """Recorre las sentencias a nivel de módulo, entrando en bloques condicionales

    (``try``, ``if``, ``with``, ``match``, etc.), pero sin entrar en funciones ni clases.
    """
    for nodo in sentencias(raiz):
        yield nodo
        if nodo.type in _COMPUESTAS:
            for bloque in _bloques(nodo):
                yield from sentencias_modulo(bloque)


def _bloques(nodo: Node) -> Iterator[Node]:
    """Bloques de una sentencia compuesta y de sus cláusulas, en orden."""
    for hijo in nombrados(nodo):
        if hijo.type == "block" and nodo.type == "match_statement":
            for caso in nombrados(hijo):
                yield from _bloques(caso)
        elif hijo.type == "block":
            yield hijo
        elif hijo.type in _CLAUSULAS:
            yield from _bloques(hijo)


def _desglosar_atributo(expr: Node | None) -> list[str] | None:
    """``a.b.c`` → ``['a', 'b', 'c']``; None si la raíz no es un nombre simple."""
    partes: list[str] = []
    actual = sin_envoltura(expr)
    while actual is not None and actual.type == "attribute":
        partes.append(texto(campo(actual, "attribute")))
        actual = sin_envoltura(campo(actual, "object"))
    if actual is not None and actual.type == "identifier":
        partes.append(texto(actual))
        partes.reverse()
        return partes
    return None


def nombre_punteado(ruta: str) -> str:
    """``pkg/mod.py`` → ``pkg.mod``; ``pkg/__init__.py`` → ``pkg``."""
    partes = ruta.removesuffix(".py").split("/")
    if partes[-1] == "__init__":
        partes.pop()
    return ".".join(partes)


@dataclass
class _Modulo:
    ruta: str
    arbol: Tree
    #: alias local → (ruta del módulo del proyecto, nombre original o None si es el módulo)
    imports: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    funciones: dict[str, Node] = field(default_factory=dict)
    clases: dict[str, Node] = field(default_factory=dict)
    #: nombre → ("app" | "router", prefijo del APIRouter o None si no es literal)
    objetos: dict[str, tuple[str, str | None]] = field(default_factory=dict)


class _Proyecto:
    """Índice de los módulos: imports resueltos, funciones, clases y apps."""

    def __init__(self, arboles: dict[str, Tree]) -> None:
        self.modulos = {ruta: _Modulo(ruta, arbol) for ruta, arbol in arboles.items()}
        self._por_nombre = {nombre_punteado(r): r for r in self.modulos}
        for modulo in self.modulos.values():
            self._indexar(modulo)

    # --- módulos -----------------------------------------------------------
    def buscar_modulo(self, punteado: str) -> str | None:
        """Ruta del módulo del proyecto con ese nombre (admite carpeta ``src/``)."""
        if punteado in self._por_nombre:
            return self._por_nombre[punteado]
        candidatos = [
            ruta
            for nombre_modulo, ruta in self._por_nombre.items()
            if nombre_modulo.endswith("." + punteado)
        ]
        return min(candidatos, key=len) if candidatos else None

    def _base_relativa(self, modulo: _Modulo, nivel: int, origen: str | None) -> str:
        paquete = nombre_punteado(modulo.ruta).split(".")
        if not modulo.ruta.endswith("__init__.py"):
            paquete = paquete[:-1]
        paquete = paquete[: len(paquete) - (nivel - 1)] if nivel > 1 else paquete
        return ".".join([*paquete, *([origen] if origen else [])])

    def _indexar(self, modulo: _Modulo) -> None:
        for nodo in sentencias_modulo(modulo.arbol.root_node):
            importado = importacion(nodo)
            if importado is not None and not importado.desde:
                for nombre_import, alias in importado.nombres:
                    destino = self.buscar_modulo(nombre_import)
                    if destino:
                        modulo.imports[alias or nombre_import.split(".")[0]] = (
                            destino,
                            None,
                        )
            elif importado is not None:
                base = (
                    self._base_relativa(modulo, importado.nivel, importado.modulo)
                    if importado.nivel
                    else importado.modulo or ""
                )
                for nombre_import, alias in importado.nombres:
                    local = alias or nombre_import
                    submodulo = self.buscar_modulo(f"{base}.{nombre_import}".strip("."))
                    destino = self.buscar_modulo(base) if base else None
                    if submodulo:
                        modulo.imports[local] = (submodulo, None)
                    elif destino:
                        modulo.imports[local] = (destino, nombre_import)
            elif es_funcion(nodo):
                funcion = definicion(nodo)
                modulo.funciones.setdefault(nombre(funcion), funcion)
            elif es_clase(nodo):
                clase = definicion(nodo)
                modulo.clases.setdefault(nombre(clase), clase)
            elif nodo.type == "expression_statement":
                asignacion = nombrados(nodo)[:1]
                if asignacion and asignacion[0].type == "assignment":
                    self._registrar_objeto(modulo, asignacion[0])

    @staticmethod
    def _registrar_objeto(modulo: _Modulo, asignacion: Node) -> None:
        objetivos, valor = _asignacion(asignacion)
        valor = sin_envoltura(valor)
        if valor is None or valor.type != "call":
            return
        tipo = _ultimo_nombre(campo(valor, "function"))
        if tipo not in ("FastAPI", "APIRouter"):
            return
        prefijo: str | None = ""
        if tipo == "APIRouter":
            prefijo = _kw_texto(valor, "prefix", "")
        for objetivo in objetivos:
            objetivo = sin_envoltura(objetivo)
            if objetivo is not None and objetivo.type == "identifier":
                existente = modulo.objetos.get(texto(objetivo))
                if existente is None or (not existente[1] and prefijo):
                    modulo.objetos[texto(objetivo)] = (
                        "app" if tipo == "FastAPI" else "router",
                        prefijo,
                    )

    # --- resolución de nombres --------------------------------------------
    def resolver(
        self, modulo: _Modulo, expr: Node | None, profundidad: int = 0
    ) -> tuple[str, str] | None:
        """(ruta del módulo, nombre) del símbolo del proyecto al que apunta ``expr``."""
        expr = sin_envoltura(expr)
        if expr is None:
            return None
        if expr.type == "identifier":
            return self.resolver_nombre(modulo, texto(expr), profundidad)
        if expr.type == "attribute":
            return self._resolver_atributo(modulo, expr, profundidad)
        return None

    def resolver_nombre(
        self, modulo: _Modulo, nombre_simbolo: str, profundidad: int = 0
    ) -> tuple[str, str] | None:
        if profundidad > 5:
            return None
        if (
            nombre_simbolo in modulo.funciones
            or nombre_simbolo in modulo.clases
            or nombre_simbolo in modulo.objetos
        ):
            return modulo.ruta, nombre_simbolo
        if nombre_simbolo in modulo.imports:
            destino, original = modulo.imports[nombre_simbolo]
            if original is None:
                return None  # es un módulo, no un símbolo
            otro = self.modulos[destino]
            return self.resolver_nombre(otro, original, profundidad + 1)
        return None

    def _resolver_atributo(
        self, modulo: _Modulo, expr: Node, profundidad: int
    ) -> tuple[str, str] | None:
        if profundidad > 5:
            return None
        partes = _desglosar_atributo(expr)
        if not partes or len(partes) < 2:
            return None
        primero = partes[0]
        if primero in modulo.imports:
            destino, original = modulo.imports[primero]
            if original is None:
                if len(partes) == 2:
                    otro = self.modulos.get(destino)
                    if otro:
                        return self.resolver_nombre(otro, partes[1], profundidad + 1)
                else:
                    dest_punteado = nombre_punteado(destino)
                    sub = self.buscar_modulo(
                        f"{dest_punteado}.{'.'.join(partes[1:-1])}"
                    )
                    if sub and sub in self.modulos:
                        return self.resolver_nombre(
                            self.modulos[sub], partes[-1], profundidad + 1
                        )
        sub_directo = self.buscar_modulo(".".join(partes[:-1]))
        if sub_directo and sub_directo in self.modulos:
            return self.resolver_nombre(
                self.modulos[sub_directo], partes[-1], profundidad + 1
            )
        return None

    def objeto(self, modulo: _Modulo, expr: Node | None) -> tuple[str, str] | None:
        """Como :meth:`resolver`, pero solo si el símbolo es una app o un router."""
        destino = self.resolver(modulo, expr)
        if destino and destino[1] in self.modulos[destino[0]].objetos:
            return destino
        return None


# --------------------------------------------------------------------------- #
# Ayudas sobre nodos
# --------------------------------------------------------------------------- #
def _asignacion(nodo: Node) -> tuple[list[Node], Node | None]:
    """Destinos y valor de ``a = b = valor`` o ``a: T = valor``."""
    objetivos: list[Node] = []
    actual: Node | None = nodo
    while actual is not None and actual.type == "assignment":
        izquierdo = campo(actual, "left")
        if izquierdo is not None:
            objetivos.append(izquierdo)
        if campo(actual, "type") is not None:
            return objetivos, campo(actual, "right")
        actual = campo(actual, "right")
    return objetivos, actual


def _ultimo_nombre(expr: Node | None) -> str | None:
    """``fastapi.FastAPI`` → ``FastAPI``; ``Depends`` → ``Depends``."""
    expr = sin_envoltura(expr)
    if expr is None:
        return None
    if expr.type == "identifier":
        return texto(expr)
    if expr.type == "attribute":
        return texto(campo(expr, "attribute"))
    return None


def _es_llamada(expr: Node | None) -> bool:
    expr = sin_envoltura(expr)
    return expr is not None and expr.type == "call"


def _argumentos(llamada: Node) -> list[Node]:
    """Argumentos posicionales de una llamada (``ast.Call.args``)."""
    lista = campo(llamada, "arguments")
    if lista is None:
        return []
    if lista.type == "generator_expression":
        return [lista]
    return [
        h
        for h in nombrados(lista)
        if h.type not in ("keyword_argument", "dictionary_splat")
    ]


def _kw(llamada: Node, nombre_argumento: str) -> Node | None:
    lista = campo(llamada, "arguments")
    if lista is None or lista.type != "argument_list":
        return None
    for argumento in nombrados(lista):
        if (
            argumento.type == "keyword_argument"
            and texto(campo(argumento, "name")) == nombre_argumento
        ):
            return campo(argumento, "value")
    return None


def _kw_texto(llamada: Node, nombre_argumento: str, defecto: str | None) -> str | None:
    """Texto literal de un argumento por nombre; ``defecto`` si no está; None si no es literal."""
    valor = _kw(llamada, nombre_argumento)
    if valor is None:
        return defecto
    valor = sin_envoltura(valor)
    if valor is not None and valor.type in ("string", "concatenated_string"):
        try:
            resultado = texto_ts.literal(valor)
        except texto_ts.NoEsLiteral:
            return None
        return resultado if isinstance(resultado, str) else None
    return None


def _literal(nodo: Node | None) -> Any:
    """Valor de un literal simple (número, texto, booleano); None si no lo es."""
    if nodo is None:
        return None
    try:
        return texto_ts.literal(nodo)
    except (texto_ts.NoEsLiteral, TypeError, RecursionError):
        return None


def _codigo_estado(nodo: Node | None) -> int | None:
    """``201`` o ``status.HTTP_201_CREATED`` → 201."""
    valor = _literal(nodo)
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    if nodo is not None:
        nombre_estado = _ultimo_nombre(nodo) or ""
        coincide = re.match(r"HTTP_(\d{3})_", nombre_estado)
        if coincide:
            return int(coincide.group(1))
    return None


def _restricciones(llamada: Node) -> dict[str, Any]:
    return {
        clave: valor
        for clave in RESTRICCIONES
        if (valor := _literal(_kw(llamada, clave))) is not None
    }


def _metadatos(anotacion: Node | None) -> tuple[Node | None, list[Node]]:
    """``Annotated[int, Query(gt=0)]`` → (``int``, [``Query(gt=0)``])."""
    partes = texto_ts.partes_subindice(anotacion)
    if partes is not None:
        valor, es_tupla, indices = partes
        if _ultimo_nombre(valor) == "Annotated" and es_tupla and indices:
            tipo, *extra = indices
            return tipo, extra
    return anotacion, []


def _texto(nodo: Node | None) -> str | None:
    return texto_ts.expresion(nodo)


def _llamadas(funcion: Node) -> Iterable[Node]:
    """Las llamadas del cuerpo de una función, sin entrar en funciones o clases anidadas."""
    bloque = cuerpo(funcion)
    pendientes: list[Node] = [] if bloque is None else list(hijos(bloque))
    while pendientes:
        nodo = pendientes.pop()
        if nodo.type in _NODOS_ANIDADOS:
            continue
        if nodo.type == "call":
            yield nodo
        pendientes.extend(hijos(nodo))


def _bases(clase: Node) -> list[Node]:
    """Clases base (``ast.ClassDef.bases``): los argumentos posicionales."""
    superclases = campo(clase, "superclasses")
    if superclases is None:
        return []
    return [
        h
        for h in nombrados(superclases)
        if h.type not in ("keyword_argument", "dictionary_splat")
    ]


def _docstring(nodo: Node) -> str | None:
    return (texto_ts.docstring(cuerpo(nodo)) or "").strip() or None


# --------------------------------------------------------------------------- #
# Análisis
# --------------------------------------------------------------------------- #
class _Analisis:
    def __init__(self, proyecto: _Proyecto) -> None:
        self.p = proyecto
        self.modelos = self._buscar_modelos()
        self.inclusiones = self._buscar_inclusiones()
        self._llama_a: dict[tuple[str, int], list[str]] = {}

    # --- modelos Pydantic -------------------------------------------------
    def _buscar_modelos(self) -> set[tuple[str, str]]:
        """(ruta, clase) de cada modelo Pydantic del proyecto, por herencia."""
        modelos: set[tuple[str, str]] = set()
        cambio = True
        while cambio:
            cambio = False
            for modulo in self.p.modulos.values():
                for nombre_clase, clase in modulo.clases.items():
                    if (modulo.ruta, nombre_clase) in modelos:
                        continue
                    for base in _bases(clase):
                        directo = _ultimo_nombre(base) in ("BaseModel", "SQLModel")
                        if directo or self.p.resolver(modulo, base) in modelos:
                            modelos.add((modulo.ruta, nombre_clase))
                            cambio = True
                            break
        return modelos

    def es_modelo(self, modulo: _Modulo, anotacion: Node | None) -> str | None:
        """Nombre del modelo si la anotación es un modelo (o ``list[Modelo]``)."""
        if anotacion is None:
            return None
        partes = texto_ts.partes_subindice(anotacion)
        if partes is not None:
            valor, es_tupla, indices = partes
            if _ultimo_nombre(valor) in ("list", "List"):
                interno = (
                    self.es_modelo(modulo, indices[0])
                    if not es_tupla and indices
                    else None
                )
                return f"list[{interno}]" if interno else None
        destino = self.p.resolver(modulo, anotacion)
        return destino[1] if destino in self.modelos else None

    def describir_modelos(self, modulo: _Modulo) -> list[dict[str, Any]]:
        resultado = []
        for nombre_clase, clase in modulo.clases.items():
            if (modulo.ruta, nombre_clase) not in self.modelos:
                continue
            bases = [self.p.resolver(modulo, base) for base in _bases(clase)]
            resultado.append(
                {
                    "nombre": nombre_clase,
                    "linea": linea(clase),
                    "docstring": _docstring(clase),
                    "hereda_de": [b[1] for b in bases if b in self.modelos],
                    "campos": self._campos(modulo, clase),
                }
            )
        return resultado

    def _campos(
        self, modulo: _Modulo, clase: Node, visitados: frozenset = frozenset()
    ) -> list[dict[str, Any]]:
        """Campos del modelo, con los heredados de otros modelos del proyecto primero."""
        clave = (modulo.ruta, nombre(clase))
        if clave in visitados:
            return []
        heredados: dict[str, dict[str, Any]] = {}
        for base in _bases(clase):
            destino = self.p.resolver(modulo, base)
            if destino in self.modelos:
                otro = self.p.modulos[destino[0]]
                for campo_heredado in self._campos(
                    otro, otro.clases[destino[1]], visitados | {clave}
                ):
                    heredados[campo_heredado["nombre"]] = campo_heredado
        propios = {c["nombre"]: c for c in self._campos_propios(clase)}
        return list({**heredados, **propios}.values())

    @staticmethod
    def _campos_propios(clase: Node) -> list[dict[str, Any]]:
        """Campos declarados en la propia clase (``nombre: tipo = valor``)."""
        campos = []
        for sentencia in sentencias(cuerpo(clase)):
            if sentencia.type != "expression_statement":
                continue
            asignacion = nombrados(sentencia)[:1]
            if not asignacion or asignacion[0].type != "assignment":
                continue
            asignacion_nodo = asignacion[0]
            anotacion = campo(asignacion_nodo, "type")
            objetivo = sin_envoltura(campo(asignacion_nodo, "left"))
            if anotacion is None or objetivo is None or objetivo.type != "identifier":
                continue
            tipo, extra = _metadatos(anotacion)
            valor = campo(asignacion_nodo, "right")
            campo_modelo: dict[str, Any] = {
                "nombre": texto(objetivo),
                "tipo": _texto(tipo),
                "requerido": valor is None,
                "por_defecto": None,
                "restricciones": {},
            }
            llamadas = [sin_envoltura(e) for e in extra if _es_llamada(e)]
            valor_llamada = sin_envoltura(valor)
            if _es_llamada(valor_llamada) and (
                _ultimo_nombre(campo(valor_llamada, "function")) == "Field"
            ):
                llamadas.append(valor_llamada)
                posicionales = _argumentos(valor_llamada)
                defecto = (
                    posicionales[0] if posicionales else _kw(valor_llamada, "default")
                )
                tiene_fabrica = _kw(valor_llamada, "default_factory") is not None
                elipsis = texto_ts.es_constante_puntos(defecto)
                campo_modelo["requerido"] = (
                    defecto is None or elipsis
                ) and not tiene_fabrica
                campo_modelo["por_defecto"] = (
                    None if campo_modelo["requerido"] else _texto(defecto)
                )
            elif valor is not None:
                campo_modelo["por_defecto"] = _texto(valor)
            for llamada in llamadas:
                if _ultimo_nombre(campo(llamada, "function")) == "Field":
                    campo_modelo["restricciones"].update(_restricciones(llamada))
            campos.append(campo_modelo)
        return campos

    # --- prefijos de routers ----------------------------------------------
    def _buscar_inclusiones(
        self,
    ) -> dict[tuple[str, str], list[tuple[tuple[str, str], str | None]]]:
        """router → [(app o router que lo incluye, prefijo literal o None)]."""
        inclusiones: dict[
            tuple[str, str], list[tuple[tuple[str, str], str | None]]
        ] = {}
        for modulo in self.p.modulos.values():
            for nodo in recorrer(modulo.arbol.root_node):
                if nodo.type != "call":
                    continue
                funcion = sin_envoltura(campo(nodo, "function"))
                posicionales = _argumentos(nodo)
                if not (
                    funcion is not None
                    and funcion.type == "attribute"
                    and texto(campo(funcion, "attribute")) == "include_router"
                    and posicionales
                ):
                    continue
                padre = self.p.objeto(modulo, campo(funcion, "object"))
                hijo = self.p.objeto(modulo, posicionales[0])
                if padre and hijo:
                    prefijo = _kw_texto(nodo, "prefix", "")
                    inclusiones.setdefault(hijo, []).append((padre, prefijo))
        return inclusiones

    def prefijo(
        self, objeto: tuple[str, str], visitados: frozenset = frozenset()
    ) -> tuple[str, bool]:
        """Prefijo completo de una app o router y si se pudo resolver."""
        tipo, propio = self.p.modulos[objeto[0]].objetos[objeto[1]]
        if tipo == "app":
            return "", True
        if propio is None or objeto in visitados:
            return propio or "", False
        incluido = self.inclusiones.get(objeto)
        if not incluido:
            return propio, False  # router que ninguna app del proyecto incluye
        padre, prefijo_inclusion = incluido[0]
        base, ok = self.prefijo(padre, visitados | {objeto})
        if prefijo_inclusion is None:
            return base + propio, False
        return base + prefijo_inclusion + propio, ok

    # --- llama_a -----------------------------------------------------------
    def llama_a(
        self, modulo: _Modulo, funcion: Node, manejadores: set[tuple[str, str]]
    ) -> list[str]:
        """Funciones públicas del proyecto que llama ``funcion`` (``ruta.py::nombre``).

        Se pide dos veces por manejador (endpoint y mapa ``llama_a``): se guarda el
        resultado, porque recorrer el cuerpo nodo por nodo es lo caro con tree-sitter.
        """
        clave = (modulo.ruta, funcion.id)
        if clave not in self._llama_a:
            self._llama_a[clave] = self._calcular_llama_a(modulo, funcion, manejadores)
        return list(self._llama_a[clave])

    def _calcular_llama_a(
        self, modulo: _Modulo, funcion: Node, manejadores: set[tuple[str, str]]
    ) -> list[str]:
        encontradas = set()
        for llamada in _llamadas(funcion):
            destino = self.p.resolver(modulo, campo(llamada, "function"))
            if (
                destino
                and destino[1] in self.p.modulos[destino[0]].funciones
                and not destino[1].startswith("_")
                and destino != (modulo.ruta, nombre(funcion))
                and destino not in manejadores
            ):
                encontradas.add(f"{destino[0]}::{destino[1]}")
        return sorted(encontradas)

    # --- endpoints ---------------------------------------------------------
    def rutas_de(self, modulo: _Modulo, funcion: Node) -> list[dict[str, Any]]:
        """Los (método, ruta, decorador) con que se registra ``funcion``."""
        rutas = []
        for expresion_decorador in decoradores(funcion):
            decorador = sin_envoltura(expresion_decorador)
            if decorador is None or decorador.type != "call":
                continue
            llamado = sin_envoltura(campo(decorador, "function"))
            if llamado is None or llamado.type != "attribute":
                continue
            accion = texto(campo(llamado, "attribute"))
            objeto = self.p.objeto(modulo, campo(llamado, "object"))
            if objeto is None:
                continue
            if accion == "api_route":
                metodos = _literal(_kw(decorador, "methods")) or ["GET"]
            elif accion.upper() in METODOS:
                metodos = [accion.upper()]
            else:
                continue
            posicionales = _argumentos(decorador)
            camino = posicionales[0] if posicionales else _kw(decorador, "path")
            texto_camino = _literal(camino)
            base, resuelta = self.prefijo(objeto)
            for metodo in metodos:
                if str(metodo).upper() not in METODOS:
                    continue
                rutas.append(
                    {
                        "metodo": str(metodo).upper(),
                        "ruta": base + texto_camino
                        if isinstance(texto_camino, str)
                        else None,
                        "resuelta": resuelta and isinstance(texto_camino, str),
                        "app": objeto[1]
                        if objeto[0] == modulo.ruta
                        else f"{objeto[0]}::{objeto[1]}",
                        "decorador": decorador,
                    }
                )
        return rutas

    def describir_endpoint(
        self,
        modulo: _Modulo,
        funcion: Node,
        ruta: dict[str, Any],
        manejadores: set[tuple[str, str]],
    ) -> dict[str, Any]:
        decorador: Node = ruta["decorador"]
        camino = ruta["ruta"] or ""
        en_ruta = set(_PARAM_RUTA.findall(camino))
        parametros_ruta: dict[str, list[dict[str, Any]]] = {
            "ruta": [],
            "consulta": [],
            "cabeceras": [],
        }
        cuerpo_peticion: list[dict[str, Any]] = []
        dependencias: list[dict[str, Any]] = []

        todos = [
            p
            for p in parametros(campo(funcion, "parameters"))
            if p.clase in (POSICIONAL_SOLO, POSICIONAL, SOLO_NOMBRE)
        ]
        for argumento in todos:
            defecto = argumento.defecto
            tipo, extra = _metadatos(argumento.tipo)
            marcadores = [sin_envoltura(e) for e in [*extra, defecto] if _es_llamada(e)]
            marca = next(
                (
                    m
                    for m in marcadores
                    if _ultimo_nombre(campo(m, "function"))
                    in (
                        "Depends",
                        "Security",
                        "Query",
                        "Path",
                        "Body",
                        "Header",
                        "Cookie",
                        "Form",
                        "File",
                    )
                ),
                None,
            )
            clase = _ultimo_nombre(campo(marca, "function")) if marca else None
            if _ultimo_nombre(tipo) in TIPOS_ESPECIALES if tipo is not None else False:
                continue
            if clase in ("Depends", "Security"):
                posicionales = _argumentos(marca)
                objetivo = posicionales[0] if posicionales else _kw(marca, "dependency")
                objetivo = objetivo or tipo
                dependencias.append(
                    {
                        "parametro": argumento.nombre,
                        "funcion": _texto(objetivo),
                        "en_proyecto": self._ref(modulo, objetivo),
                    }
                )
                continue
            descripcion = {
                "nombre": argumento.nombre,
                "tipo": _texto(tipo),
                "requerido": True,
                "por_defecto": None,
                "restricciones": _restricciones(marca) if marca else {},
            }
            valor_defecto = defecto if marca is None else None
            if marca is not None:
                posicionales = _argumentos(marca)
                valor_defecto = (
                    posicionales[0] if posicionales else _kw(marca, "default")
                )
                if valor_defecto is None and marca != sin_envoltura(defecto):
                    valor_defecto = defecto  # Annotated[int, Query()] = 10
            if valor_defecto is not None and not texto_ts.es_constante_puntos(
                valor_defecto
            ):
                descripcion["requerido"] = False
                descripcion["por_defecto"] = _texto(valor_defecto)

            modelo = self.es_modelo(modulo, tipo)
            if clase in ("Body", "Form", "File") or (
                modelo and clase is None and argumento.nombre not in en_ruta
            ):
                cuerpo_peticion.append({**descripcion, "modelo": modelo})
            elif clase == "Path" or argumento.nombre in en_ruta:
                parametros_ruta["ruta"].append({**descripcion, "requerido": True})
            elif clase in ("Header", "Cookie"):
                parametros_ruta["cabeceras"].append(descripcion)
            else:
                parametros_ruta["consulta"].append(descripcion)

        for extra in _literal_lista(_kw(decorador, "dependencies")):
            llamada = sin_envoltura(extra)
            if _es_llamada(llamada) and _ultimo_nombre(campo(llamada, "function")) in (
                "Depends",
                "Security",
            ):
                posicionales = _argumentos(llamada)
                objetivo = posicionales[0] if posicionales else None
                dependencias.append(
                    {
                        "parametro": None,
                        "funcion": _texto(objetivo),
                        "en_proyecto": self._ref(modulo, objetivo),
                    }
                )

        estado = _codigo_estado(_kw(decorador, "status_code"))
        excepciones = []
        for llamada in _llamadas(funcion):
            if _ultimo_nombre(campo(llamada, "function")) != "HTTPException":
                continue
            posicionales = _argumentos(llamada)
            codigo = _codigo_estado(
                posicionales[0] if posicionales else _kw(llamada, "status_code")
            )
            detalle = _literal(
                posicionales[1] if len(posicionales) > 1 else _kw(llamada, "detail")
            )
            excepciones.append(
                {
                    "status_code": codigo,
                    "detalle": detalle if isinstance(detalle, str) else None,
                    "linea": linea(llamada),
                }
            )

        excepciones.sort(key=lambda e: e["linea"])
        metodo = ruta["metodo"]
        return {
            "objetivo": f"{metodo} {camino}" if ruta["ruta"] is not None else None,
            "metodo": metodo,
            "ruta": ruta["ruta"],
            "resuelta": ruta["resuelta"],
            "app": ruta["app"],
            "manejador": nombre(funcion),
            "linea": linea(funcion),
            "linea_fin": linea_fin(funcion),
            "es_async": es_async(funcion),
            "firma": texto_ts.firma(funcion),
            "docstring": _docstring(funcion),
            "ramas": contar_ramas(funcion),
            "parametros_ruta": parametros_ruta["ruta"],
            "parametros_consulta": parametros_ruta["consulta"],
            "cabeceras": parametros_ruta["cabeceras"],
            "cuerpo": cuerpo_peticion[0]
            if len(cuerpo_peticion) == 1
            else (cuerpo_peticion or None),
            "response_model": _texto(_kw(decorador, "response_model")),
            "status_code": estado if estado is not None else 200,
            "status_code_declarado": estado is not None,
            "dependencias": dependencias,
            "excepciones_http": excepciones,
            "llama_a": self.llama_a(modulo, funcion, manejadores),
        }

    def _ref(self, modulo: _Modulo, expr: Node | None) -> str | None:
        if expr is None:
            return None
        destino = self.p.resolver(modulo, expr)
        return f"{destino[0]}::{destino[1]}" if destino else None


def _literal_lista(nodo: Node | None) -> list[Node]:
    nodo = sin_envoltura(nodo)
    if nodo is not None and nodo.type in ("list", "tuple"):
        return nombrados(nodo)
    return []


# --------------------------------------------------------------------------- #
# Interfaz pública
# --------------------------------------------------------------------------- #
def analizar_rutas(arboles: dict[str, Tree]) -> dict[str, dict[str, Any]]:
    """Endpoints, modelos y ``llama_a`` de cada módulo.

    Args:
        arboles: árbol tree-sitter de cada módulo del proyecto, por ruta relativa POSIX.

    Returns:
        Por ruta de módulo: ``endpoints`` (lista), ``modelos`` (lista),
        ``manejadores`` (nombres de las funciones que atienden rutas, que dejan
        de contarse como funciones sueltas) y ``llama_a`` (por nombre de función).
    """
    proyecto = _Proyecto(arboles)
    analisis = _Analisis(proyecto)

    rutas_por_funcion: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for modulo in proyecto.modulos.values():
        for nombre_funcion, funcion in modulo.funciones.items():
            rutas = analisis.rutas_de(modulo, funcion)
            if rutas:
                rutas_por_funcion[(modulo.ruta, nombre_funcion)] = rutas
    manejadores = set(rutas_por_funcion)

    resultado: dict[str, dict[str, Any]] = {}
    for modulo in proyecto.modulos.values():
        endpoints = [
            analisis.describir_endpoint(modulo, funcion, ruta, manejadores)
            for nombre_funcion, funcion in modulo.funciones.items()
            for ruta in rutas_por_funcion.get((modulo.ruta, nombre_funcion), [])
        ]
        endpoints.sort(key=lambda e: (e["linea"], e["metodo"]))
        resultado[modulo.ruta] = {
            "endpoints": endpoints,
            "modelos": analisis.describir_modelos(modulo),
            "manejadores": sorted(n for (r, n) in manejadores if r == modulo.ruta),
            "llama_a": {
                nombre_funcion: analisis.llama_a(modulo, funcion, manejadores)
                for nombre_funcion, funcion in modulo.funciones.items()
            },
        }
    return resultado

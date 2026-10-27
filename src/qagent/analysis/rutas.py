"""Rutas FastAPI, modelos Pydantic y mapa de llamadas (EN-14).

Segunda pasada del analizador estático (EN-02): recibe el AST de **todos** los
módulos del proyecto y extrae, sin ejecutar nada (solo ``ast``):

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

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

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
_NODOS_ANIDADOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_TIPOS_TRY = (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)
_Funcion = ast.FunctionDef | ast.AsyncFunctionDef


# --------------------------------------------------------------------------- #
# Tabla de símbolos del proyecto
# --------------------------------------------------------------------------- #
def sentencias_modulo(nodos: Iterable[ast.stmt]) -> Iterable[ast.stmt]:
    """Recorre las sentencias a nivel de módulo, entrando en bloques condicionales

    (``try``, ``if``, ``with``, ``match``, etc.), pero sin entrar en funciones ni clases.
    """
    for nodo in nodos:
        yield nodo
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(nodo, ast.If):
            yield from sentencias_modulo(nodo.body)
            yield from sentencias_modulo(nodo.orelse)
        elif isinstance(nodo, _TIPOS_TRY):
            yield from sentencias_modulo(nodo.body)
            for h in nodo.handlers:
                yield from sentencias_modulo(h.body)
            yield from sentencias_modulo(nodo.orelse)
            yield from sentencias_modulo(nodo.finalbody)
        elif isinstance(nodo, (ast.With, ast.AsyncWith)):
            yield from sentencias_modulo(nodo.body)
        elif hasattr(ast, "Match") and isinstance(nodo, ast.Match):
            for caso in nodo.cases:
                yield from sentencias_modulo(caso.body)
        elif isinstance(nodo, (ast.For, ast.AsyncFor, ast.While)):
            yield from sentencias_modulo(nodo.body)
            yield from sentencias_modulo(nodo.orelse)


def _desglosar_atributo(expr: ast.expr) -> list[str] | None:
    """``a.b.c`` → ``['a', 'b', 'c']``; None si la raíz no es un nombre simple."""
    partes: list[str] = []
    actual: ast.expr = expr
    while isinstance(actual, ast.Attribute):
        partes.append(actual.attr)
        actual = actual.value
    if isinstance(actual, ast.Name):
        partes.append(actual.id)
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
    arbol: ast.Module
    #: alias local → (ruta del módulo del proyecto, nombre original o None si es el módulo)
    imports: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    funciones: dict[str, _Funcion] = field(default_factory=dict)
    clases: dict[str, ast.ClassDef] = field(default_factory=dict)
    #: nombre → ("app" | "router", prefijo del APIRouter o None si no es literal)
    objetos: dict[str, tuple[str, str | None]] = field(default_factory=dict)


class _Proyecto:
    """Índice de los módulos: imports resueltos, funciones, clases y apps."""

    def __init__(self, arboles: dict[str, ast.Module]) -> None:
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
            for nombre, ruta in self._por_nombre.items()
            if nombre.endswith("." + punteado)
        ]
        return min(candidatos, key=len) if candidatos else None

    def _base_relativa(self, modulo: _Modulo, nodo: ast.ImportFrom) -> str:
        paquete = nombre_punteado(modulo.ruta).split(".")
        if not modulo.ruta.endswith("__init__.py"):
            paquete = paquete[:-1]
        paquete = (
            paquete[: len(paquete) - (nodo.level - 1)] if nodo.level > 1 else paquete
        )
        return ".".join([*paquete, *([nodo.module] if nodo.module else [])])

    def _indexar(self, modulo: _Modulo) -> None:
        for nodo in sentencias_modulo(modulo.arbol.body):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    destino = self.buscar_modulo(alias.name)
                    if destino:
                        modulo.imports[alias.asname or alias.name.split(".")[0]] = (
                            destino,
                            None,
                        )
            elif isinstance(nodo, ast.ImportFrom):
                base = (
                    self._base_relativa(modulo, nodo)
                    if nodo.level
                    else nodo.module or ""
                )
                for alias in nodo.names:
                    local = alias.asname or alias.name
                    submodulo = self.buscar_modulo(f"{base}.{alias.name}".strip("."))
                    destino = self.buscar_modulo(base) if base else None
                    if submodulo:
                        modulo.imports[local] = (submodulo, None)
                    elif destino:
                        modulo.imports[local] = (destino, alias.name)
            elif isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if nodo.name not in modulo.funciones:
                    modulo.funciones[nodo.name] = nodo
            elif isinstance(nodo, ast.ClassDef):
                if nodo.name not in modulo.clases:
                    modulo.clases[nodo.name] = nodo
            elif isinstance(nodo, (ast.Assign, ast.AnnAssign)):
                self._registrar_objeto(modulo, nodo)

    @staticmethod
    def _registrar_objeto(modulo: _Modulo, nodo: ast.Assign | ast.AnnAssign) -> None:
        valor = nodo.value
        if not isinstance(valor, ast.Call):
            return
        tipo = _ultimo_nombre(valor.func)
        if tipo not in ("FastAPI", "APIRouter"):
            return
        objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
        prefijo: str | None = ""
        if tipo == "APIRouter":
            prefijo = _kw_texto(valor, "prefix", "")
        for objetivo in objetivos:
            if isinstance(objetivo, ast.Name):
                existente = modulo.objetos.get(objetivo.id)
                if existente is None or (not existente[1] and prefijo):
                    modulo.objetos[objetivo.id] = (
                        "app" if tipo == "FastAPI" else "router",
                        prefijo,
                    )

    # --- resolución de nombres --------------------------------------------
    def resolver(
        self, modulo: _Modulo, expr: ast.expr, profundidad: int = 0
    ) -> tuple[str, str] | None:
        """(ruta del módulo, nombre) del símbolo del proyecto al que apunta ``expr``."""
        if profundidad > 5:
            return None
        if isinstance(expr, ast.Name):
            nombre = expr.id
            if (
                nombre in modulo.funciones
                or nombre in modulo.clases
                or nombre in modulo.objetos
            ):
                return modulo.ruta, nombre
            if nombre in modulo.imports:
                destino, original = modulo.imports[nombre]
                if original is None:
                    return None  # es un módulo, no un símbolo
                otro = self.modulos[destino]
                return self.resolver(otro, ast.Name(id=original), profundidad + 1)
            return None
        if isinstance(expr, ast.Attribute):
            partes = _desglosar_atributo(expr)
            if partes and len(partes) >= 2:
                primero = partes[0]
                if primero in modulo.imports:
                    destino, original = modulo.imports[primero]
                    if original is None:
                        if len(partes) == 2:
                            otro = self.modulos.get(destino)
                            if otro:
                                return self.resolver(
                                    otro, ast.Name(id=partes[1]), profundidad + 1
                                )
                        else:
                            dest_punteado = nombre_punteado(destino)
                            sub = self.buscar_modulo(
                                f"{dest_punteado}.{'.'.join(partes[1:-1])}"
                            )
                            if sub and sub in self.modulos:
                                return self.resolver(
                                    self.modulos[sub],
                                    ast.Name(id=partes[-1]),
                                    profundidad + 1,
                                )
                sub_directo = self.buscar_modulo(".".join(partes[:-1]))
                if sub_directo and sub_directo in self.modulos:
                    return self.resolver(
                        self.modulos[sub_directo],
                        ast.Name(id=partes[-1]),
                        profundidad + 1,
                    )
        return None

    def objeto(self, modulo: _Modulo, expr: ast.expr) -> tuple[str, str] | None:
        """Como :meth:`resolver`, pero solo si el símbolo es una app o un router."""
        destino = self.resolver(modulo, expr)
        if destino and destino[1] in self.modulos[destino[0]].objetos:
            return destino
        return None


# --------------------------------------------------------------------------- #
# Ayudas sobre nodos
# --------------------------------------------------------------------------- #
def _ultimo_nombre(expr: ast.expr) -> str | None:
    """``fastapi.FastAPI`` → ``FastAPI``; ``Depends`` → ``Depends``."""
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


def _kw(llamada: ast.Call, nombre: str) -> ast.expr | None:
    return next((k.value for k in llamada.keywords if k.arg == nombre), None)


def _kw_texto(llamada: ast.Call, nombre: str, defecto: str | None) -> str | None:
    """Texto literal de un argumento por nombre; ``defecto`` si no está; None si no es literal."""
    valor = _kw(llamada, nombre)
    if valor is None:
        return defecto
    if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
        return valor.value
    return None


def _literal(nodo: ast.expr | None) -> Any:
    """Valor de un literal simple (número, texto, booleano); None si no lo es."""
    if nodo is None:
        return None
    try:
        return ast.literal_eval(nodo)
    except (ValueError, SyntaxError, TypeError, RecursionError):
        return None


def _codigo_estado(nodo: ast.expr | None) -> int | None:
    """``201`` o ``status.HTTP_201_CREATED`` → 201."""
    valor = _literal(nodo)
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    if nodo is not None:
        nombre = _ultimo_nombre(nodo) or ""
        coincide = re.match(r"HTTP_(\d{3})_", nombre)
        if coincide:
            return int(coincide.group(1))
    return None


def _restricciones(llamada: ast.Call) -> dict[str, Any]:
    return {
        clave: valor
        for clave in RESTRICCIONES
        if (valor := _literal(_kw(llamada, clave))) is not None
    }


def _metadatos(anotacion: ast.expr | None) -> tuple[ast.expr | None, list[ast.expr]]:
    """``Annotated[int, Query(gt=0)]`` → (``int``, [``Query(gt=0)``])."""
    if (
        isinstance(anotacion, ast.Subscript)
        and _ultimo_nombre(anotacion.value) == "Annotated"
        and isinstance(anotacion.slice, ast.Tuple)
        and anotacion.slice.elts
    ):
        tipo, *extra = anotacion.slice.elts
        return tipo, extra
    return anotacion, []


def _texto(nodo: ast.AST | None) -> str | None:
    return None if nodo is None else ast.unparse(nodo)


def _llamadas(funcion: _Funcion) -> Iterable[ast.Call]:
    """Las llamadas del cuerpo de una función, sin entrar en funciones o clases anidadas."""
    pendientes: list[ast.AST] = list(funcion.body)
    while pendientes:
        nodo = pendientes.pop()
        if isinstance(nodo, _NODOS_ANIDADOS):
            continue
        if isinstance(nodo, ast.Call):
            yield nodo
        pendientes.extend(ast.iter_child_nodes(nodo))


# --------------------------------------------------------------------------- #
# Análisis
# --------------------------------------------------------------------------- #
class _Analisis:
    def __init__(self, proyecto: _Proyecto) -> None:
        self.p = proyecto
        self.modelos = self._buscar_modelos()
        self.inclusiones = self._buscar_inclusiones()

    # --- modelos Pydantic -------------------------------------------------
    def _buscar_modelos(self) -> set[tuple[str, str]]:
        """(ruta, clase) de cada modelo Pydantic del proyecto, por herencia."""
        modelos: set[tuple[str, str]] = set()
        cambio = True
        while cambio:
            cambio = False
            for modulo in self.p.modulos.values():
                for nombre, clase in modulo.clases.items():
                    if (modulo.ruta, nombre) in modelos:
                        continue
                    for base in clase.bases:
                        directo = _ultimo_nombre(base) in ("BaseModel", "SQLModel")
                        if directo or self.p.resolver(modulo, base) in modelos:
                            modelos.add((modulo.ruta, nombre))
                            cambio = True
                            break
        return modelos

    def es_modelo(self, modulo: _Modulo, anotacion: ast.expr | None) -> str | None:
        """Nombre del modelo si la anotación es un modelo (o ``list[Modelo]``)."""
        if anotacion is None:
            return None
        if isinstance(anotacion, ast.Subscript) and _ultimo_nombre(anotacion.value) in (
            "list",
            "List",
        ):
            interno = self.es_modelo(modulo, anotacion.slice)
            return f"list[{interno}]" if interno else None
        destino = self.p.resolver(modulo, anotacion)
        return destino[1] if destino in self.modelos else None

    def describir_modelos(self, modulo: _Modulo) -> list[dict[str, Any]]:
        resultado = []
        for nombre, clase in modulo.clases.items():
            if (modulo.ruta, nombre) not in self.modelos:
                continue
            bases = [self.p.resolver(modulo, base) for base in clase.bases]
            resultado.append(
                {
                    "nombre": nombre,
                    "linea": clase.lineno,
                    "docstring": (ast.get_docstring(clase) or "").strip() or None,
                    "hereda_de": [b[1] for b in bases if b in self.modelos],
                    "campos": self._campos(modulo, clase),
                }
            )
        return resultado

    def _campos(
        self, modulo: _Modulo, clase: ast.ClassDef, visitados: frozenset = frozenset()
    ) -> list[dict[str, Any]]:
        """Campos del modelo, con los heredados de otros modelos del proyecto primero."""
        clave = (modulo.ruta, clase.name)
        if clave in visitados:
            return []
        heredados: dict[str, dict[str, Any]] = {}
        for base in clase.bases:
            destino = self.p.resolver(modulo, base)
            if destino in self.modelos:
                otro = self.p.modulos[destino[0]]
                for campo in self._campos(
                    otro, otro.clases[destino[1]], visitados | {clave}
                ):
                    heredados[campo["nombre"]] = campo
        propios = {c["nombre"]: c for c in self._campos_propios(clase)}
        return list({**heredados, **propios}.values())

    @staticmethod
    def _campos_propios(clase: ast.ClassDef) -> list[dict[str, Any]]:
        """Campos declarados en la propia clase (``nombre: tipo = valor``)."""
        campos = []
        for nodo in clase.body:
            if not (
                isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name)
            ):
                continue
            tipo, extra = _metadatos(nodo.annotation)
            campo: dict[str, Any] = {
                "nombre": nodo.target.id,
                "tipo": _texto(tipo),
                "requerido": nodo.value is None,
                "por_defecto": None,
                "restricciones": {},
            }
            llamadas = [e for e in extra if isinstance(e, ast.Call)]
            valor = nodo.value
            if isinstance(valor, ast.Call) and _ultimo_nombre(valor.func) == "Field":
                llamadas.append(valor)
                defecto = valor.args[0] if valor.args else _kw(valor, "default")
                tiene_fabrica = _kw(valor, "default_factory") is not None
                elipsis = isinstance(defecto, ast.Constant) and defecto.value is ...
                campo["requerido"] = (defecto is None or elipsis) and not tiene_fabrica
                campo["por_defecto"] = None if campo["requerido"] else _texto(defecto)
            elif valor is not None:
                campo["por_defecto"] = _texto(valor)
            for llamada in llamadas:
                if _ultimo_nombre(llamada.func) == "Field":
                    campo["restricciones"].update(_restricciones(llamada))
            campos.append(campo)
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
            for nodo in ast.walk(modulo.arbol):
                if not (
                    isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "include_router"
                    and nodo.args
                ):
                    continue
                padre = self.p.objeto(modulo, nodo.func.value)
                hijo = self.p.objeto(modulo, nodo.args[0])
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
        self, modulo: _Modulo, funcion: _Funcion, manejadores: set[tuple[str, str]]
    ) -> list[str]:
        """Funciones públicas del proyecto que llama ``funcion`` (``ruta.py::nombre``)."""
        encontradas = set()
        for llamada in _llamadas(funcion):
            destino = self.p.resolver(modulo, llamada.func)
            if (
                destino
                and destino[1] in self.p.modulos[destino[0]].funciones
                and not destino[1].startswith("_")
                and destino != (modulo.ruta, funcion.name)
                and destino not in manejadores
            ):
                encontradas.add(f"{destino[0]}::{destino[1]}")
        return sorted(encontradas)

    # --- endpoints ---------------------------------------------------------
    def rutas_de(self, modulo: _Modulo, funcion: _Funcion) -> list[dict[str, Any]]:
        """Los (método, ruta, decorador) con que se registra ``funcion``."""
        rutas = []
        for decorador in funcion.decorator_list:
            if not (
                isinstance(decorador, ast.Call)
                and isinstance(decorador.func, ast.Attribute)
            ):
                continue
            accion = decorador.func.attr
            objeto = self.p.objeto(modulo, decorador.func.value)
            if objeto is None:
                continue
            if accion == "api_route":
                metodos = _literal(_kw(decorador, "methods")) or ["GET"]
            elif accion.upper() in METODOS:
                metodos = [accion.upper()]
            else:
                continue
            camino = decorador.args[0] if decorador.args else _kw(decorador, "path")
            texto = _literal(camino)
            base, resuelta = self.prefijo(objeto)
            for metodo in metodos:
                if str(metodo).upper() not in METODOS:
                    continue
                rutas.append(
                    {
                        "metodo": str(metodo).upper(),
                        "ruta": base + texto if isinstance(texto, str) else None,
                        "resuelta": resuelta and isinstance(texto, str),
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
        funcion: _Funcion,
        ruta: dict[str, Any],
        manejadores: set[tuple[str, str]],
    ) -> dict[str, Any]:
        decorador: ast.Call = ruta["decorador"]
        camino = ruta["ruta"] or ""
        en_ruta = set(_PARAM_RUTA.findall(camino))
        parametros: dict[str, list[dict[str, Any]]] = {
            "ruta": [],
            "consulta": [],
            "cabeceras": [],
        }
        cuerpo: list[dict[str, Any]] = []
        dependencias: list[dict[str, Any]] = []

        args = funcion.args
        posicionales = [*args.posonlyargs, *args.args]
        defectos = [None] * (len(posicionales) - len(args.defaults)) + list(
            args.defaults
        )
        todos = [*zip(posicionales, defectos), *zip(args.kwonlyargs, args.kw_defaults)]
        for argumento, defecto in todos:
            tipo, extra = _metadatos(argumento.annotation)
            marcadores = [e for e in [*extra, defecto] if isinstance(e, ast.Call)]
            marca = next(
                (
                    m
                    for m in marcadores
                    if _ultimo_nombre(m.func)
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
            clase = _ultimo_nombre(marca.func) if marca else None
            if _ultimo_nombre(tipo) in TIPOS_ESPECIALES if tipo is not None else False:
                continue
            if clase in ("Depends", "Security"):
                objetivo = marca.args[0] if marca.args else _kw(marca, "dependency")
                objetivo = objetivo or tipo
                dependencias.append(
                    {
                        "parametro": argumento.arg,
                        "funcion": _texto(objetivo),
                        "en_proyecto": self._ref(modulo, objetivo),
                    }
                )
                continue
            descripcion = {
                "nombre": argumento.arg,
                "tipo": _texto(tipo),
                "requerido": True,
                "por_defecto": None,
                "restricciones": _restricciones(marca) if marca else {},
            }
            valor_defecto = defecto if marca is None else None
            if marca is not None:
                valor_defecto = marca.args[0] if marca.args else _kw(marca, "default")
                if valor_defecto is None and marca is not defecto:
                    valor_defecto = defecto  # Annotated[int, Query()] = 10
            if valor_defecto is not None and not (
                isinstance(valor_defecto, ast.Constant) and valor_defecto.value is ...
            ):
                descripcion["requerido"] = False
                descripcion["por_defecto"] = _texto(valor_defecto)

            modelo = self.es_modelo(modulo, tipo)
            if clase in ("Body", "Form", "File") or (
                modelo and clase is None and argumento.arg not in en_ruta
            ):
                cuerpo.append({**descripcion, "modelo": modelo})
            elif clase == "Path" or argumento.arg in en_ruta:
                parametros["ruta"].append({**descripcion, "requerido": True})
            elif clase in ("Header", "Cookie"):
                parametros["cabeceras"].append(descripcion)
            else:
                parametros["consulta"].append(descripcion)

        for extra in _literal_lista(_kw(decorador, "dependencies")):
            if isinstance(extra, ast.Call) and _ultimo_nombre(extra.func) in (
                "Depends",
                "Security",
            ):
                objetivo = extra.args[0] if extra.args else None
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
            if _ultimo_nombre(llamada.func) != "HTTPException":
                continue
            codigo = _codigo_estado(
                llamada.args[0] if llamada.args else _kw(llamada, "status_code")
            )
            detalle = _literal(
                llamada.args[1] if len(llamada.args) > 1 else _kw(llamada, "detail")
            )
            excepciones.append(
                {
                    "status_code": codigo,
                    "detalle": detalle if isinstance(detalle, str) else None,
                    "linea": llamada.lineno,
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
            "manejador": funcion.name,
            "linea": funcion.lineno,
            "linea_fin": funcion.end_lineno,
            "es_async": isinstance(funcion, ast.AsyncFunctionDef),
            "firma": f"({ast.unparse(funcion.args)})"
            + (f" -> {ast.unparse(funcion.returns)}" if funcion.returns else ""),
            "docstring": (ast.get_docstring(funcion) or "").strip() or None,
            "ramas": contar_ramas(funcion),
            "parametros_ruta": parametros["ruta"],
            "parametros_consulta": parametros["consulta"],
            "cabeceras": parametros["cabeceras"],
            "cuerpo": cuerpo[0] if len(cuerpo) == 1 else (cuerpo or None),
            "response_model": _texto(_kw(decorador, "response_model")),
            "status_code": estado if estado is not None else 200,
            "status_code_declarado": estado is not None,
            "dependencias": dependencias,
            "excepciones_http": excepciones,
            "llama_a": self.llama_a(modulo, funcion, manejadores),
        }

    def _ref(self, modulo: _Modulo, expr: ast.expr | None) -> str | None:
        if expr is None:
            return None
        destino = self.p.resolver(modulo, expr)
        return f"{destino[0]}::{destino[1]}" if destino else None


def _literal_lista(nodo: ast.expr | None) -> list[ast.expr]:
    return list(nodo.elts) if isinstance(nodo, (ast.List, ast.Tuple)) else []


# --------------------------------------------------------------------------- #
# Interfaz pública
# --------------------------------------------------------------------------- #
def analizar_rutas(arboles: dict[str, ast.Module]) -> dict[str, dict[str, Any]]:
    """Endpoints, modelos y ``llama_a`` de cada módulo.

    Args:
        arboles: AST de cada módulo del proyecto, por ruta relativa POSIX.

    Returns:
        Por ruta de módulo: ``endpoints`` (lista), ``modelos`` (lista),
        ``manejadores`` (nombres de las funciones que atienden rutas, que dejan
        de contarse como funciones sueltas) y ``llama_a`` (por nombre de función).
    """
    proyecto = _Proyecto(arboles)
    analisis = _Analisis(proyecto)

    rutas_por_funcion: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for modulo in proyecto.modulos.values():
        for nombre, funcion in modulo.funciones.items():
            rutas = analisis.rutas_de(modulo, funcion)
            if rutas:
                rutas_por_funcion[(modulo.ruta, nombre)] = rutas
    manejadores = set(rutas_por_funcion)

    resultado: dict[str, dict[str, Any]] = {}
    for modulo in proyecto.modulos.values():
        endpoints = [
            analisis.describir_endpoint(modulo, funcion, ruta, manejadores)
            for nombre, funcion in modulo.funciones.items()
            for ruta in rutas_por_funcion.get((modulo.ruta, nombre), [])
        ]
        endpoints.sort(key=lambda e: (e["linea"], e["metodo"]))
        resultado[modulo.ruta] = {
            "endpoints": endpoints,
            "modelos": analisis.describir_modelos(modulo),
            "manejadores": sorted(n for (r, n) in manejadores if r == modulo.ruta),
            "llama_a": {
                nombre: analisis.llama_a(modulo, funcion, manejadores)
                for nombre, funcion in modulo.funciones.items()
            },
        }
    return resultado

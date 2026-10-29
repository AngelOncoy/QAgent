"""Reglas de planificación de Python (pytest y FastAPI) para el Planner (#168).

Es el código que antes vivía en ``agents/planner.py``, movido sin cambios de
comportamiento: el Planner es compartido y pide estas reglas al adaptador.

- Prompts: cómo se piden al modelo los casos de las funciones y de los endpoints
  FastAPI, completos o de humo (#75).
- Filtros sin IA de cada caso: tuplas que JSON convierte en listas (#145), llamadas
  que no encajan con la firma (#138), casos límite sin especificación (#76) y
  oráculos que la procedencia declarada no respalda (#113).
- Endpoints (HU-27): método, ruta, estados y campos que salen de la declaración.

Todo es estático (tree-sitter, TA-16): nunca se importa ni se ejecuta el código.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tree_sitter import Node

from qagent.analysis import arbol_ts, texto_ts
from qagent.llm.fake import MARCA_MODULO, MARCA_OBJETIVOS

#: Orígenes válidos de un valor esperado para una función (`planner_contract.v2`).
#: No existe "ejecucion": el valor esperado nunca sale de ejecutar el código.
ORIGENES = ("firma", "tipo", "docstring")


_EJEMPLO_RESPUESTA = [
    {
        "objetivo": "calcular_descuento",
        "casos": [
            {
                "id": "descuento_normal",
                "descripcion": "Aplica el porcentaje al precio",
                "entrada": {"precio": 100.0, "porcentaje": 20.0},
                "valor_esperado": 80.0,
                "origen": "docstring",
                "categoria": "normal",
            },
            {
                "id": "porcentaje_maximo",
                "entrada": {"precio": 100.0, "porcentaje": 100.0},
                "valor_esperado": 0.0,
                "origen": "docstring",
                "categoria": "limite",
            },
            {
                "id": "porcentaje_invalido",
                "entrada": {"precio": 100.0, "porcentaje": 150.0},
                "excepcion": "ValueError",
                "origen": "docstring",
                "categoria": "error",
            },
        ],
    }
]


#: #138: una llamada con argumentos que no encajan con la firma lanza TypeError antes
#: de entrar al cuerpo; esa prueba pasa sin ejecutar una línea de la función.
MOTIVO_CASO_TRIVIAL = (
    "llama a la función con argumentos que no encajan con su firma; ese TypeError lo "
    "lanza Python antes de entrar al cuerpo y no verifica su comportamiento"
)


MOTIVO_OMITIDA_TRIVIAL = (
    "solo se pudo proponer una llamada con argumentos que no encajan con su firma; "
    "ese TypeError lo lanza Python, no la función, así que no verifica su comportamiento"
)


class _PromptsPython:
    """Prompts del Planner para Python (antes métodos de ``PlannerAgent``)."""

    @staticmethod
    def prompt_funciones_completo(modulo: dict[str, Any]) -> str:
        """Prompt compacto: solo firma y docstring de cada función (sin el código)."""
        objetivos = [
            {
                "nombre": funcion["nombre"],
                "firma": funcion.get("firma"),
                "docstring": funcion.get("docstring"),
            }
            for funcion in modulo.get("funciones", [])
        ]
        ejemplo = json.dumps(_EJEMPLO_RESPUESTA, ensure_ascii=False)
        return f"""
Diseña casos de prueba unitaria pytest para las funciones de un módulo Python.

REGLAS OBLIGATORIAS:
- No ejecutes ni importes el código del usuario: no lo tienes y no hace falta.
- El valor esperado sale SOLO de la firma, los tipos o el docstring. Si el docstring
  no permite deducir un valor con certeza, no inventes ese caso.
- Una función sin docstring sigue siendo planificable, pero NO declares origen
  "docstring". Con origen "tipo", un tipo general como int, str o bool no determina
  por sí solo un valor concreto; `-> None` sí respalda `null`.
- No propongas llamadas con argumentos que no encajan con la firma (faltan
  obligatorios o sobran claves): ese TypeError lo lanza Python antes de entrar a la
  función y no prueba su comportamiento.
- Si ninguna fuente permite un oráculo concreto, omite la función. No sustituyas una
  igualdad por `is not None`, una mera invocación ni otra aserción débil.
- Incluye casos normales, de límite y de error cuando el docstring los describa.
- "categoria" de cada caso: "normal" (entrada válida típica), "limite" (valor en el
  borde de lo permitido: 0, vacío, máximo o un umbral que describa el docstring) o
  "error" (entrada inválida que lanza una excepción). Propón un caso "limite" SOLO
  si el docstring o los tipos describen ese límite; si no, no lo inventes.
- Cada caso tiene: "id" (minúsculas, números y _), "entrada" (objeto con los
  argumentos por nombre), "origen" (uno de: {", ".join(ORIGENES)}), "categoria" y
  "valor_esperado" o "excepcion" (nombre de la excepción, ej. "ValueError").
  "descripcion" es opcional.
- Si un resultado documentado es una tupla Python, serialízalo como array JSON y
  agrega "tipo_valor_esperado": "tuple"; no uses esa metadata para listas.
- Devuelve SOLO una lista JSON con un objeto por función:
  {{"objetivo": nombre, "casos": [...]}}. Sin explicaciones ni bloques Markdown.

EJEMPLO DE RESPUESTA:
{ejemplo}

{MARCA_MODULO} {modulo["ruta"]}
{MARCA_OBJETIVOS} {json.dumps(objetivos, ensure_ascii=False)}
""".strip()

    @staticmethod
    def prompt_funciones_humo(modulo: dict[str, Any]) -> str:
        """Humo (#75): un caso normal por función, con instrucciones mínimas."""
        objetivos = [
            {
                "nombre": funcion["nombre"],
                "firma": funcion.get("firma"),
                "docstring": funcion.get("docstring"),
            }
            for funcion in modulo.get("funciones", [])
        ]
        ejemplo = json.dumps(
            [{**_EJEMPLO_RESPUESTA[0], "casos": _EJEMPLO_RESPUESTA[0]["casos"][:1]}],
            ensure_ascii=False,
        )
        return f"""
Prueba de humo pytest: UN caso normal por función (entrada válida y su resultado).
- No ejecutes el código. El valor esperado sale SOLO de firma, tipos o docstring; si
  no se deduce con certeza, omite la función.
- Sin docstring, no uses origen "docstring": `-> None` puede justificar `null`.
- No propongas llamadas con argumentos que no encajan con la firma: ese TypeError
  lo lanza Python, no la función.
- No inventes valores ni conviertas el humo en una prueba de mera ejecución.
- Caso: "id", "entrada" (argumentos por nombre), "valor_esperado", "origen" (uno de:
  {", ".join(ORIGENES)}) y "categoria": "normal". Sin "excepcion" ni casos límite.
- Si el resultado documentado es una tupla Python, usa un array JSON y agrega
  "tipo_valor_esperado": "tuple". Una anotación tuple sin valores concretos no basta.
- Devuelve SOLO una lista JSON con un objeto por función:
  [{{"objetivo": nombre, "casos": [caso]}}]. Si ninguna tiene un caso deducible,
  devuelve la lista vacía [].
Ejemplo: {ejemplo}

{MARCA_MODULO} {modulo["ruta"]}
{MARCA_OBJETIVOS} {json.dumps(objetivos, ensure_ascii=False)}
""".strip()

    @staticmethod
    def prompt_endpoints_completo(
        modulo: dict[str, Any],
        endpoints: dict[str, dict[str, Any]],
        fuente: str | None,
    ) -> str:
        """Prompt compacto: lo declarado por cada ruta, sus modelos y su código."""
        lineas = fuente.splitlines() if fuente else []
        objetivos = []
        for endpoint in endpoints.values():
            descripcion = {
                "objetivo": endpoint["objetivo"],
                "docstring": endpoint.get("docstring"),
                "status_code": endpoint.get("status_code"),
                "response_model": endpoint.get("response_model"),
                "cuerpo": endpoint.get("cuerpo"),
                "parametros_ruta": endpoint.get("parametros_ruta"),
                "parametros_consulta": endpoint.get("parametros_consulta"),
                "cabeceras": endpoint.get("cabeceras"),
                "dependencias": [
                    d.get("funcion") for d in endpoint.get("dependencias", [])
                ],
                "excepciones_http": [
                    {"status_code": e.get("status_code"), "detalle": e.get("detalle")}
                    for e in endpoint.get("excepciones_http", [])
                ],
            }
            inicio, fin = endpoint.get("linea"), endpoint.get("linea_fin")
            if lineas and inicio and fin:
                descripcion["codigo"] = "\n".join(lineas[inicio - 1 : fin])
            objetivos.append(descripcion)
        modelos = [
            {
                "nombre": m["nombre"],
                "campos": [
                    {k: c[k] for k in ("nombre", "tipo", "requerido", "restricciones")}
                    for c in m.get("campos", [])
                ],
            }
            for m in modulo.get("modelos", [])
        ]
        ejemplo = json.dumps(_EJEMPLO_ENDPOINTS, ensure_ascii=False)
        return f"""
Diseña casos de prueba para los endpoints de una API FastAPI. Cada caso es una
petición HTTP y la respuesta que la API DEBE dar según lo que declara.

REGLAS OBLIGATORIAS:
- No ejecutes ni importes el código: el valor esperado sale SOLO de lo declarado
  (status_code, response_model, modelos Pydantic y sus restricciones, las
  HTTPException del código) o del docstring. Si no se puede deducir con certeza,
  no inventes ese caso.
- Por endpoint incluye como mínimo: un caso con el status_code declarado; un 422
  si recibe cuerpo o parámetros con tipo o restricciones; un caso por cada
  HTTPException; y los errores que describa el docstring (por ejemplo, un 404).
- "categoria" de cada caso: "normal" (petición válida típica), "limite" (valor
  válido en el borde de lo permitido: Field(ge=..., le=...), min_length, un umbral
  del docstring) o "error" (petición inválida que devuelve 4xx/5xx). Propón un caso
  "limite" SOLO si las restricciones o el docstring describen ese límite.
- Cada caso tiene: "id" (minúsculas, números y _), "entrada" {{"metodo", "ruta"
  con los parámetros ya puestos, y opcionales "query", "json", "headers"}},
  "valor_esperado" {{"status_code" y, si se conoce, "json" (respuesta completa)
  o "json_contiene" (solo algunos campos)}}, "origen" (uno de:
  {", ".join(ORIGENES_ENDPOINT)}) y "categoria". "descripcion" es opcional: úsala para decir
  qué datos deben existir antes de la petición (por ejemplo, "con el artículo 1
  guardado").
- Devuelve SOLO una lista JSON con un objeto por endpoint:
  {{"objetivo": "MÉTODO /ruta", "casos": [...]}}. Sin explicaciones ni Markdown.

EJEMPLO DE RESPUESTA:
{ejemplo}

MODELOS: {json.dumps(modelos, ensure_ascii=False)}
{MARCA_MODULO} {modulo["ruta"]}
{MARCA_OBJETIVOS} {json.dumps(objetivos, ensure_ascii=False)}
""".strip()

    @staticmethod
    def prompt_endpoints_humo(
        modulo: dict[str, Any], endpoints: dict[str, dict[str, Any]]
    ) -> str:
        """Humo (#75): una petición válida por endpoint, sin código ni errores HTTP."""
        objetivos = [
            {
                k: endpoint.get(k)
                for k in (
                    "objetivo",
                    "docstring",
                    "status_code",
                    "response_model",
                    "cuerpo",
                    "parametros_ruta",
                    "parametros_consulta",
                    "cabeceras",
                )
            }
            for endpoint in endpoints.values()
        ]
        modelos = [
            {
                "nombre": m["nombre"],
                "campos": [
                    {k: c[k] for k in ("nombre", "tipo", "requerido", "restricciones")}
                    for c in m.get("campos", [])
                ],
            }
            for m in modulo.get("modelos", [])
        ]
        ejemplo = json.dumps(
            [{**_EJEMPLO_ENDPOINTS[0], "casos": _EJEMPLO_ENDPOINTS[0]["casos"][:1]}],
            ensure_ascii=False,
        )
        return f"""
Prueba de humo de una API FastAPI: UNA petición válida por endpoint y la respuesta
exitosa que declara (su status_code, 200 si no lo declara).
- No ejecutes el código. Lo esperado sale SOLO de lo declarado o del docstring; si no
  se deduce con certeza, omite el endpoint.
- Caso: "id", "entrada" {{"metodo", "ruta", opcionales "query", "json", "headers"}},
  "valor_esperado" {{"status_code" y, si se conoce, "json_contiene"}}, "origen" (uno
  de: {", ".join(ORIGENES_ENDPOINT)}) y "categoria": "normal". Sin casos de error.
- Devuelve SOLO una lista JSON con un objeto por endpoint:
  [{{"objetivo": "MÉTODO /ruta", "casos": [caso]}}]. Si ninguno tiene una respuesta
  deducible, devuelve la lista vacía [].
Ejemplo: {ejemplo}

MODELOS: {json.dumps(modelos, ensure_ascii=False)}
{MARCA_MODULO} {modulo["ruta"]}
{MARCA_OBJETIVOS} {json.dumps(objetivos, ensure_ascii=False)}
""".strip()


def motivo_limite_funcion(funcion: dict[str, Any], caso: dict[str, Any]) -> str | None:
    """Por qué un caso `limite` de una función no tiene oráculo; None si lo tiene (#76).

    El límite tiene que salir del docstring o de un tipo con restricciones
    (`Annotated[...]`); la firma sola no describe ningún borde.
    """
    if caso.get("categoria") != "limite":
        return None
    origen = caso.get("origen")
    if origen == "docstring" and funcion.get("docstring"):
        return None
    if origen == "tipo" and "Annotated[" in (funcion.get("firma") or ""):
        return None
    return "caso límite sin una especificación que describa ese límite"


def motivo_oraculo_funcion(funcion: dict[str, Any], caso: dict[str, Any]) -> str | None:
    """Valida que la procedencia declarada pueda justificar el oráculo del caso.

    El JSON Schema comprueba la forma y el vocabulario de ``origen``. Esta validación
    cruzada comprueba además que la fuente exista y que aporte una propiedad concreta.
    Es deliberadamente conservadora: una anotación general describe el dominio del
    resultado, pero no permite adivinar un valor; una firma describe cómo invocar la
    función, pero no su comportamiento funcional.
    """
    origen = caso.get("origen")
    if origen == "docstring":
        if caso.get("tipo_valor_esperado") == "tuple":
            if _docstring_respalda_tupla(funcion.get("docstring"), caso):
                return None
            return "el docstring no documenta esa tupla esperada de forma explícita"
        if funcion.get("docstring"):
            return None
        return "declara origen 'docstring', pero la función no tiene docstring"
    if origen == "tipo":
        if _tipo_respalda_oraculo(funcion, caso):
            return None
        return (
            "el tipo declarado no determina ese valor esperado ni esa excepción "
            "con suficiente precisión"
        )
    if origen == "firma":
        if _firma_respalda_oraculo(funcion, caso):
            return None
        return (
            "la firma solo describe la invocación y no determina ese resultado "
            "funcional"
        )
    return None


def _tipo_respalda_oraculo(funcion: dict[str, Any], caso: dict[str, Any]) -> bool:
    """Si existe una declaración de tipos que respalde el caso propuesto.

    El Planner interpreta la relación funcional declarada por las anotaciones; esta
    capa no intenta ejecutar ni reinterpretar el cuerpo. Para ``None`` y un
    ``Literal`` único sí se exige además que el valor coincida exactamente.
    """
    if "valor_esperado" not in caso or "excepcion" in caso:
        return False
    retorno = funcion.get("retorno") or _retorno_de_firma(funcion.get("firma"))
    if not isinstance(retorno, str):
        return False
    retorno = retorno.strip()
    esperado = caso["valor_esperado"]
    if retorno in {"None", "NoneType", "type(None)"}:
        return esperado is None
    literal = _literal_unico(retorno)
    if literal is not _SIN_LITERAL:
        return esperado == literal
    # Una tupla anotada demuestra el contenedor, pero no sus elementos concretos.
    return not _anotacion_es_tupla(retorno)


def _preservar_tipo_valor_esperado(
    funcion: dict[str, Any], caso: dict[str, Any]
) -> dict[str, Any]:
    """Añade metadata de tupla cuando firma o docstring la justifican.

    El valor concreto sigue procediendo del caso documentado. Esta función solo
    recupera el tipo que JSON pierde al convertir una tupla en array.
    """
    if (
        "valor_esperado" not in caso
        or not isinstance(caso["valor_esperado"], list)
        or "tipo_valor_esperado" in caso
    ):
        return caso
    retorno = funcion.get("retorno") or _retorno_de_firma(funcion.get("firma"))
    if _anotacion_es_tupla(retorno) or _docstring_respalda_tupla(
        funcion.get("docstring"), caso
    ):
        return {**caso, "tipo_valor_esperado": "tuple"}
    return caso


def _anotacion_es_tupla(anotacion: Any) -> bool:
    """Reconoce ``tuple[...]``, ``Tuple[...]`` y ``typing.Tuple[...]`` sin evaluar."""
    if not isinstance(anotacion, str):
        return False
    nodo = texto_ts.expresion_de_texto(anotacion.strip())
    if nodo is None:
        return False
    partes = texto_ts.partes_subindice(nodo)
    base = partes[0] if partes is not None else nodo
    return texto_ts.expresion(base) in {"tuple", "Tuple", "typing.Tuple"}


def _docstring_respalda_tupla(docstring: Any, caso: dict[str, Any]) -> bool:
    """Comprueba una tupla literal tras ``->`` en el docstring, sin evaluar código."""
    if not isinstance(docstring, str) or not isinstance(
        caso.get("valor_esperado"), list
    ):
        return False
    esperado = tuple(caso["valor_esperado"])
    for linea in docstring.splitlines():
        if "->" not in linea:
            continue
        texto = linea.split("->", 1)[1].strip()
        try:
            literal = texto_ts.literal_de_texto(texto)
        except (ValueError, TypeError):
            continue
        if isinstance(literal, tuple) and literal == esperado:
            return True
    return False


_SIN_LITERAL = object()


def _literal_unico(anotacion: str) -> Any:
    """Valor de ``Literal[x]`` cuando declara exactamente una posibilidad."""
    nodo = texto_ts.expresion_de_texto(anotacion)
    partes = texto_ts.partes_subindice(nodo) if nodo is not None else None
    if partes is None:
        return _SIN_LITERAL
    valor, es_tupla, indices = partes
    nombre = texto_ts.expresion(valor)
    if nombre not in {"Literal", "typing.Literal"} or es_tupla or not indices:
        return _SIN_LITERAL
    try:
        return texto_ts.literal(indices[0])
    except (ValueError, TypeError):
        return _SIN_LITERAL


def _retorno_de_firma(firma: Any) -> str | None:
    """Extrae la anotación de retorno de la firma sin evaluar código."""
    funcion = _nodo_firma(firma)
    if funcion is None:
        return None
    return texto_ts.expresion(funcion.child_by_field_name("return_type"))


def es_caso_trivial(funcion: dict[str, Any], caso: dict[str, Any]) -> bool:
    """Si el caso solo comprueba que Python rechaza la llamada (#138).

    Espera ``TypeError`` y sus argumentos no encajan con la firma (faltan obligatorios,
    se pasa un posicional-only por nombre o sobra una clave). Ese error ocurre antes de
    entrar al cuerpo: la prueba pasaría sin ejecutar una línea de la función, sea cual
    sea el ``origen`` declarado. Se decide con el AST de la firma, sin IA.

    Un ``TypeError`` con argumentos que sí encajan (por ejemplo, «lanza TypeError si x
    no es int» con ``x="a"``) no es trivial: lo lanza la función.
    """
    if caso.get("excepcion") not in {"TypeError", "builtins.TypeError"}:
        return False
    return _llamada_no_liga(funcion, caso.get("entrada"))


def _firma_respalda_oraculo(funcion: dict[str, Any], caso: dict[str, Any]) -> bool:
    """Si la firma demuestra un ``TypeError`` antes de entrar al cuerpo.

    Desde #138 ese caso se descarta antes (`es_caso_trivial`), así que en la práctica
    la firma ya no respalda ningún oráculo; se conserva para validar casos sueltos.
    """
    if caso.get("excepcion") not in {"TypeError", "builtins.TypeError"}:
        return False
    return _llamada_no_liga(funcion, caso.get("entrada"))


def _llamada_no_liga(funcion: dict[str, Any], entrada: Any) -> bool:
    """Si los argumentos por nombre de un caso no pueden ligarse a la firma.

    Los casos del contrato invocan funciones con argumentos por nombre: no ligan si
    faltan obligatorios, se pasa un posicional-only por nombre o sobra una clave.
    """
    if not isinstance(entrada, dict):
        return False
    nodo = _nodo_firma(funcion.get("firma"))
    if nodo is None:
        return False
    lista = arbol_ts.parametros(nodo.child_by_field_name("parameters"))
    requeridos = {
        p.nombre
        for p in lista
        if p.clase
        in (arbol_ts.POSICIONAL_SOLO, arbol_ts.POSICIONAL, arbol_ts.SOLO_NOMBRE)
        and p.defecto is None
    }
    claves = set(entrada)
    posonly = {p.nombre for p in lista if p.clase == arbol_ts.POSICIONAL_SOLO}
    permitidas = {
        p.nombre
        for p in lista
        if p.clase in (arbol_ts.POSICIONAL, arbol_ts.SOLO_NOMBRE)
    }
    faltan = requeridos - claves
    posonly_por_nombre = claves & posonly
    con_kwargs = any(p.clase == arbol_ts.KWARGS for p in lista)
    sobran = set() if con_kwargs else claves - permitidas
    return bool(faltan or posonly_por_nombre or sobran)


def _nodo_firma(firma: Any) -> Node | None:
    """La ``function_definition`` de una firma textual, sin importar ni ejecutar nada."""
    if not isinstance(firma, str) or not firma.startswith("("):
        return None
    codigo = f"def _objetivo{firma}:\n    pass\n"
    arbol = arbol_ts.parsear(codigo)
    if arbol_ts.error_de_sintaxis(arbol, codigo) is not None:
        return None
    sentencias = arbol_ts.sentencias(arbol.root_node)
    if len(sentencias) != 1 or sentencias[0].type != "function_definition":
        return None
    return sentencias[0]


def motivo_limite_endpoint(
    endpoint: dict[str, Any], caso: dict[str, Any], modelos: dict[str, dict[str, Any]]
) -> str | None:
    """Igual que `motivo_limite_funcion` para un endpoint (#76).

    El límite sale del docstring o de restricciones declaradas: `Field`/`Query`/`Path`
    con `ge`, `le`, `min_length`… en los parámetros o en los modelos Pydantic.
    """
    if caso.get("categoria") != "limite":
        return None
    origen = caso.get("origen")
    if origen == "docstring" and endpoint.get("docstring"):
        return None
    if origen in ("modelo_pydantic", "tipo") and tiene_restricciones(endpoint, modelos):
        return None
    return "caso límite sin una especificación que describa ese límite"


def tiene_restricciones(
    endpoint: dict[str, Any], modelos: dict[str, dict[str, Any]]
) -> bool:
    """Si los parámetros o los modelos del endpoint declaran restricciones (#76)."""
    parametros = [
        *endpoint.get("parametros_ruta", []),
        *endpoint.get("parametros_consulta", []),
        *endpoint.get("cabeceras", []),
    ]
    if any(p.get("restricciones") for p in parametros):
        return True
    return any(
        campo.get("restricciones")
        for modelo in modelos.values()
        for campo in modelo.get("campos", [])
    )


def _aplicacion_principal(endpoints: Any) -> str:
    """Elige el símbolo FastAPI raíz conocido por el análisis estático.

    EN-14 conserva el objeto decorado (``app`` o ``router``). Cuando un módulo
    combina ambos, se prefiere el símbolo convencional ``app`` que incluye al
    router y, por tanto, expone las rutas completas a ``TestClient``.
    """
    aplicaciones = [
        str(endpoint.get("app", "")).split("::")[-1]
        for endpoint in endpoints
        if endpoint.get("app")
    ]
    if "app" in aplicaciones:
        return "app"
    return aplicaciones[0] if aplicaciones else "app"


def _dependencias_con_reemplazo(
    modulo: dict[str, Any], endpoint: dict[str, Any]
) -> list[dict[str, str]]:
    """Convierte cada Depends analizado en un doble instanciable.

    El tipo de retorno de la función de dependencia ya forma parte de la salida
    estática de EN-14. Para ``obtener_repositorio() -> Repositorio``, por ejemplo,
    el Generator recibe ambos símbolos sin inspeccionar ni ejecutar el proyecto.
    """
    funciones = {funcion["nombre"]: funcion for funcion in modulo.get("funciones", [])}
    resultado = []
    for dependencia in endpoint.get("dependencias", []):
        nombre = dependencia.get("funcion")
        retorno = (funciones.get(nombre) or {}).get("retorno")
        if not isinstance(nombre, str) or not isinstance(retorno, str):
            continue
        reemplazo = retorno.split("[")[0].split("|")[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reemplazo):
            resultado.append({"funcion": nombre, "reemplazo": reemplazo})
    return resultado


#: Orígenes de un valor esperado para un endpoint (`planner_contract.v2`).
ORIGENES_ENDPOINT = (
    "status_code",
    "response_model",
    "modelo_pydantic",
    "docstring",
    "firma",
    "tipo",
)


_EJEMPLO_ENDPOINTS = [
    {
        "objetivo": "POST /items",
        "casos": [
            {
                "id": "crear_valido",
                "entrada": {
                    "metodo": "POST",
                    "ruta": "/items",
                    "json": {"nombre": "lapiz", "precio": 2.5},
                },
                "valor_esperado": {
                    "status_code": 201,
                    "json_contiene": {"nombre": "lapiz", "precio": 2.5},
                },
                "origen": "status_code",
                "categoria": "normal",
            },
            {
                "id": "precio_cero",
                "entrada": {
                    "metodo": "POST",
                    "ruta": "/items",
                    "json": {"nombre": "lapiz", "precio": 0},
                },
                "valor_esperado": {"status_code": 422},
                "origen": "modelo_pydantic",
                "categoria": "error",
            },
        ],
    }
]


_PARAM_RUTA = re.compile(r"{[^}]+}")


_CODIGO_EN_TEXTO = re.compile(r"\b([1-5]\d\d)\b")


def ruta_coincide(plantilla: str, ruta: str) -> bool:
    """``/items/{item_id}`` acepta ``/items/7`` (sin la consulta ``?...``)."""
    partes = _PARAM_RUTA.split(plantilla)
    patron = "[^/]+".join(re.escape(p) for p in partes)
    return re.fullmatch(patron, ruta.split("?", 1)[0]) is not None


def tiene_entradas(endpoint: dict[str, Any]) -> bool:
    """Si recibe cuerpo o parámetros con tipo o restricciones (puede responder 422)."""
    parametros = [
        *endpoint.get("parametros_ruta", []),
        *endpoint.get("parametros_consulta", []),
        *endpoint.get("cabeceras", []),
    ]
    return bool(endpoint.get("cuerpo")) or any(
        p.get("restricciones") or (p.get("tipo") not in (None, "str"))
        for p in parametros
    )


def estados_permitidos(endpoint: dict[str, Any]) -> set[int]:
    """Códigos que un caso puede esperar: declarados, 422 o documentados."""
    permitidos = {endpoint.get("status_code") or 200}
    if tiene_entradas(endpoint):
        permitidos.add(422)
    permitidos.update(
        e["status_code"]
        for e in endpoint.get("excepciones_http", [])
        if isinstance(e.get("status_code"), int)
    )
    permitidos.update(
        int(c) for c in _CODIGO_EN_TEXTO.findall(endpoint.get("docstring") or "")
    )
    return permitidos


def _campos_respuesta(
    endpoint: dict[str, Any], modelos: dict[str, dict[str, Any]]
) -> tuple[set[str] | None, bool]:
    """(campos del response_model, si es una lista); None si no hay modelo conocido."""
    modelo = (endpoint.get("response_model") or "").strip()
    es_lista = modelo.startswith(("list[", "List["))
    nombre = modelo[5:-1] if es_lista else modelo
    if nombre not in modelos:
        return None, es_lista
    return {c["nombre"] for c in modelos[nombre].get("campos", [])}, es_lista


def motivo_rechazo(
    endpoint: dict[str, Any], caso: dict[str, Any], modelos: dict[str, dict[str, Any]]
) -> str | None:
    """Por qué un caso no sale de la declaración del endpoint; None si es válido."""
    entrada = caso["entrada"]
    if entrada["metodo"] != endpoint["metodo"]:
        return f"el método {entrada['metodo']} no es el del endpoint ({endpoint['metodo']})"
    if not ruta_coincide(endpoint["ruta"], entrada["ruta"]):
        return f"la ruta {entrada['ruta']} no corresponde a {endpoint['ruta']}"
    esperado = caso["valor_esperado"]
    estado = esperado["status_code"]
    permitidos = estados_permitidos(endpoint)
    if estado not in permitidos:
        return (
            f"el estado {estado} no está declarado "
            f"(posibles: {', '.join(str(e) for e in sorted(permitidos))})"
        )
    cuerpo = esperado.get("json", esperado.get("json_contiene"))
    exito = estado == (endpoint.get("status_code") or 200)
    campos, es_lista = _campos_respuesta(endpoint, modelos)
    if cuerpo is None or not exito or campos is None:
        return None
    elementos = cuerpo if es_lista and isinstance(cuerpo, list) else [cuerpo]
    if es_lista and "json" in esperado and not isinstance(cuerpo, list):
        return "el response_model es una lista y el json esperado no lo es"
    for elemento in elementos:
        if isinstance(elemento, dict):
            extra = sorted(set(elemento) - campos)
            if extra:
                return (
                    f"los campos {', '.join(extra)} no están en el response_model "
                    f"({endpoint.get('response_model')})"
                )
    return None


def faltantes(endpoint: dict[str, Any], casos: list[dict[str, Any]]) -> list[str]:
    """Avisos por los casos mínimos que faltan (no descartan el contrato)."""
    estados = {c["valor_esperado"]["status_code"] for c in casos}
    objetivo = endpoint["objetivo"]
    avisos = []
    declarado = endpoint.get("status_code") or 200
    if declarado not in estados:
        avisos.append(
            f"{objetivo}: falta un caso con el estado declarado ({declarado})"
        )
    if tiene_entradas(endpoint) and 422 not in estados:
        avisos.append(f"{objetivo}: falta un caso con datos inválidos (422)")
    for excepcion in endpoint.get("excepciones_http", []):
        codigo = excepcion.get("status_code")
        if isinstance(codigo, int) and codigo not in estados:
            avisos.append(f"{objetivo}: falta un caso para la HTTPException {codigo}")
    return avisos


prompt_funciones_completo = _PromptsPython.prompt_funciones_completo
prompt_funciones_humo = _PromptsPython.prompt_funciones_humo
prompt_endpoints_completo = _PromptsPython.prompt_endpoints_completo
prompt_endpoints_humo = _PromptsPython.prompt_endpoints_humo


class ReglasPlanificacionPython:
    """Reglas del Planner para Python (ver ``ReglasPlanificacion`` en ``base``)."""

    motivo_caso_trivial = MOTIVO_CASO_TRIVIAL
    motivo_omitida_trivial = MOTIVO_OMITIDA_TRIVIAL

    @staticmethod
    def prompt_funciones(modulo: dict[str, Any], humo: bool) -> str:
        """Prompt de las funciones del módulo (completo o de humo)."""
        return (
            prompt_funciones_humo(modulo) if humo else prompt_funciones_completo(modulo)
        )

    @staticmethod
    def prompt_endpoints(
        modulo: dict[str, Any],
        endpoints: dict[str, dict[str, Any]],
        fuente: str | None,
        humo: bool,
    ) -> str:
        """Prompt de los endpoints FastAPI del módulo (completo o de humo)."""
        if humo:
            return prompt_endpoints_humo(modulo, endpoints)
        return prompt_endpoints_completo(modulo, endpoints, fuente)

    preparar_caso = staticmethod(_preservar_tipo_valor_esperado)
    es_caso_trivial = staticmethod(es_caso_trivial)
    motivo_limite_funcion = staticmethod(motivo_limite_funcion)
    motivo_oraculo_funcion = staticmethod(motivo_oraculo_funcion)
    aplicacion_principal = staticmethod(_aplicacion_principal)
    dependencias_con_reemplazo = staticmethod(_dependencias_con_reemplazo)
    motivo_rechazo_endpoint = staticmethod(motivo_rechazo)
    motivo_limite_endpoint = staticmethod(motivo_limite_endpoint)
    faltantes_endpoint = staticmethod(faltantes)


#: Instancia única: las reglas no guardan estado.
REGLAS_PLANIFICACION_PYTHON = ReglasPlanificacionPython()

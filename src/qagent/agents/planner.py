"""Agente Planner: diseña casos de prueba a partir del análisis AST (HU-11, HU-27).

El LLM solo propone los **casos** (entrada, valor esperado u excepción y su origen).
Todo lo que ya se sabe por el análisis estático lo pone el código: versión del
contrato, módulo, huella SHA-256, tipo, nombre, firma, `critical` y `llama_a`. Así el
modelo no puede inventar esos campos, el prompt es más corto (menos tokens) y el
contrato siempre coincide con el código analizado.

Con el perfil Humo (#75) pide y acepta **un solo caso normal por objetivo**: en una
función, una entrada válida con `valor_esperado` (sin `excepcion`); en un endpoint, una
petición con la respuesta exitosa declarada. El prompt es más corto y, si el modelo
devuelve más casos, se conserva el primero normal y queda un aviso.

Cada caso lleva su `categoria` (#76): `normal`, `limite` o `error`. Sin IA se comprueba
que sea coherente con lo que espera (una excepción o un 4xx/5xx es `error`) y, si no,
se corrige con un aviso. Un caso `limite` solo se acepta si la especificación describe
ese límite (docstring, tipos con restricciones o modelo Pydantic); si no, se descarta.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from qagent import contracts
from qagent.contracts import ContratoInvalido, categoria_de, es_caso_de_error
from qagent.llm import ClienteLLM, TokenTracker
from qagent.llm.fake import MARCA_MODULO, MARCA_OBJETIVOS

#: Orígenes válidos de un valor esperado para una función (`planner_contract.v2`).
#: No existe "ejecucion": el valor esperado nunca sale de ejecutar el código.
ORIGENES = ("firma", "tipo", "docstring")
#: Perfil de comprobación rápida (#75); igual que `qagent.storage.registro.PERFIL_HUMO`.
PERFIL_HUMO = "humo"

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

# Contrato mínimo para validar un caso suelto contra el schema del Planner.
_CONTRATO_DE_PRUEBA = {
    "version": "2",
    "modulo": "x.py",
    "huella": "0" * 64,
    "tipo": "funcion",
    "objetivo": "x",
    "firma": "()",
    "critical": False,
}


class ErrorRespuestaPlanner(ValueError):
    """El Planner devolvió una respuesta que no puede utilizarse."""


class PlannerAgent:
    """Genera contratos de prueba sin ejecutar el código del usuario."""

    def __init__(
        self,
        cliente: ClienteLLM,
        tracker: TokenTracker,
        *,
        es_simulado: bool = False,
        perfil: str | None = None,
    ) -> None:
        """Inicializa el Planner con su cliente y registro de tokens.

        Args:
            perfil: perfil de la corrida; con `humo` planifica un caso normal por
                objetivo (#75).
        """
        self.cliente = cliente
        self.tracker = tracker
        self.es_simulado = es_simulado
        self.perfil = perfil
        #: Qué se descartó en la última llamada (objetivos o casos) y por qué.
        self.descartados: list[str] = []
        #: Casos mínimos que faltan en el último plan de endpoints (no lo descartan) y,
        #: en Humo, los casos de más que se dejaron fuera.
        self.avisos: list[str] = []

    @property
    def es_humo(self) -> bool:
        """Si la corrida es Humo: un caso normal por objetivo (#75)."""
        return self.perfil == PERFIL_HUMO

    def planificar(self, modulo: dict[str, Any]) -> list[dict[str, Any]]:
        """Devuelve un `planner_contract.v2` por cada función del módulo con casos.

        Las funciones que el modelo no cubre, los objetivos que no existen en el
        módulo y los casos inválidos se descartan (quedan en `self.descartados`) en
        lugar de tumbar la corrida del módulo.

        Raises:
            ErrorRespuestaPlanner: si la respuesta no es una lista JSON, o si trae
                objetivos pero ninguno produce un contrato válido.
        """
        self.descartados = []
        self.avisos = []
        funciones = {f["nombre"]: f for f in modulo.get("funciones", [])}
        if not funciones:
            return []

        prompt = (
            self._crear_prompt_humo(modulo)
            if self.es_humo
            else self._crear_prompt(modulo)
        )
        respuesta = self.cliente.generar(prompt, rol="planner")
        self.tracker.registrar(
            agente="planner",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
        )

        try:
            propuesta = json.loads(_quitar_cerca_json(respuesta.contenido))
        except json.JSONDecodeError as error:
            raise ErrorRespuestaPlanner(
                "El Planner no devolvió JSON válido."
            ) from error
        if not isinstance(propuesta, list):
            raise ErrorRespuestaPlanner(
                "El Planner debe devolver una lista de objetivos."
            )

        plan: list[dict[str, Any]] = []
        for elemento in propuesta:
            vistos = {contrato["objetivo"] for contrato in plan}
            contrato = self._armar_contrato(modulo, funciones, elemento, vistos)
            if contrato is not None:
                plan.append(contrato)

        if propuesta and not plan:
            detalle = "; ".join(self.descartados[:3])
            raise ErrorRespuestaPlanner(
                f"El Planner no produjo ningún contrato válido ({detalle})."
            )
        return plan

    # --- Construcción del contrato ----------------------------------------------

    def _armar_contrato(
        self,
        modulo: dict[str, Any],
        funciones: dict[str, dict[str, Any]],
        elemento: Any,
        vistos: set[str],
    ) -> dict[str, Any] | None:
        if not isinstance(elemento, dict):
            self.descartados.append("un elemento del plan no es un objeto JSON")
            return None
        nombre = elemento.get("objetivo")
        if nombre not in funciones:
            self.descartados.append(f"objetivo desconocido: {nombre!r}")
            return None
        if nombre in vistos:
            self.descartados.append(f"objetivo repetido: {nombre}")
            return None

        funcion = funciones[nombre]
        casos = self._casos_validos(nombre, elemento.get("casos"), funcion)
        if self.es_humo:
            casos = self._solo_un_caso_normal(nombre, casos, es_normal_funcion)
        if not casos:
            self.descartados.append(
                f"{nombre}: sin un caso normal deducible de la especificación"
                if self.es_humo
                else f"{nombre}: sin casos válidos"
            )
            return None

        contrato = {
            "version": "2",
            "modulo": modulo["ruta"],
            "huella": modulo["huella"],
            "tipo": "funcion",
            "objetivo": nombre,
            "firma": funcion.get("firma") or "()",
            # HU-06: la marca Profundizar de la vista previa (filtrar_modulos);
            # nunca la decide el modelo.
            "critical": bool(funcion.get("critical", False)),
            "llama_a": list(dict.fromkeys(funcion.get("llama_a") or [])),
            "casos": casos,
        }
        try:
            contracts.validar(contracts.PLANNER, contrato)
        except ContratoInvalido as error:
            self.descartados.append(f"{nombre}: {error}")
            return None
        return contrato

    def _casos_validos(
        self, nombre: str, casos: Any, funcion: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Se queda con los casos que cumplen el schema; descarta el resto.

        Cada caso sale con una `categoria` coherente (#76) y los casos límite sin una
        especificación que los describa se descartan.
        """
        if not isinstance(casos, list):
            return []
        validos: list[dict[str, Any]] = []
        for caso in casos:
            if not isinstance(caso, dict):
                self.descartados.append(f"{nombre}: un caso no es un objeto JSON")
                continue
            if any(caso.get("id") == previo["id"] for previo in validos):
                self.descartados.append(f"{nombre}: caso repetido {caso.get('id')!r}")
                continue
            try:
                contracts.validar(
                    contracts.PLANNER, {**_CONTRATO_DE_PRUEBA, "casos": [caso]}
                )
            except ContratoInvalido as error:
                self.descartados.append(f"{nombre}: caso {caso.get('id')!r}: {error}")
                continue
            caso = self._con_categoria(nombre, caso)
            motivo = motivo_limite_funcion(funcion or {}, caso)
            if motivo:
                self.descartados.append(f"{nombre}: caso {caso['id']!r}: {motivo}")
                continue
            validos.append(caso)
        return validos

    def _con_categoria(self, objetivo: str, caso: dict[str, Any]) -> dict[str, Any]:
        """El caso con una categoría coherente con lo que espera (#76).

        Si no la trae, queda sin ella y se infiere al leerla (`contracts.categoria_de`),
        igual que en las specs anteriores. Si la trae y no encaja (un `error` sin
        excepción ni 4xx/5xx, o un `normal`/`limite` que espera un error), se corrige
        con un aviso: el caso sigue siendo válido, solo estaba mal clasificado.
        """
        declarada = caso.get("categoria")
        if declarada is None:
            return caso
        inferida = categoria_de({k: v for k, v in caso.items() if k != "categoria"})
        if (declarada == "error") == es_caso_de_error(caso):
            return caso
        self.avisos.append(
            f"{objetivo}: caso {caso['id']!r} marcado como {declarada!r} pero espera "
            f"{'un error' if inferida == 'error' else 'un resultado válido'}; "
            f"se clasifica como {inferida!r}"
        )
        return {**caso, "categoria": inferida}

    def _solo_un_caso_normal(
        self,
        objetivo: str,
        casos: list[dict[str, Any]],
        es_normal: Callable[[dict[str, Any]], bool],
    ) -> list[dict[str, Any]]:
        """Humo (#75): el primer caso normal válido; avisa si sobraron casos."""
        normales = [caso for caso in casos if es_normal(caso)]
        if not normales:
            return []
        if len(casos) > 1:
            fuera = [str(c.get("id")) for c in casos if c is not normales[0]]
            self.avisos.append(
                f"{objetivo}: Humo usa un solo caso normal; se conserva "
                f"{normales[0]['id']!r} y se dejan fuera {len(fuera)} "
                f"({', '.join(fuera)})"
            )
        return normales[:1]

    # --- Prompt -------------------------------------------------------------------

    @staticmethod
    def _crear_prompt(modulo: dict[str, Any]) -> str:
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
- Incluye casos normales, de límite y de error cuando el docstring los describa.
- "categoria" de cada caso: "normal" (entrada válida típica), "limite" (valor en el
  borde de lo permitido: 0, vacío, máximo o un umbral que describa el docstring) o
  "error" (entrada inválida que lanza una excepción). Propón un caso "limite" SOLO
  si el docstring o los tipos describen ese límite; si no, no lo inventes.
- Cada caso tiene: "id" (minúsculas, números y _), "entrada" (objeto con los
  argumentos por nombre), "origen" (uno de: {", ".join(ORIGENES)}), "categoria" y
  "valor_esperado" o "excepcion" (nombre de la excepción, ej. "ValueError").
  "descripcion" es opcional.
- Devuelve SOLO una lista JSON con un objeto por función:
  {{"objetivo": nombre, "casos": [...]}}. Sin explicaciones ni bloques Markdown.

EJEMPLO DE RESPUESTA:
{ejemplo}

{MARCA_MODULO} {modulo["ruta"]}
{MARCA_OBJETIVOS} {json.dumps(objetivos, ensure_ascii=False)}
""".strip()

    @staticmethod
    def _crear_prompt_humo(modulo: dict[str, Any]) -> str:
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
- Caso: "id", "entrada" (argumentos por nombre), "valor_esperado", "origen" (uno de:
  {", ".join(ORIGENES)}) y "categoria": "normal". Sin "excepcion" ni casos límite.
- Devuelve SOLO una lista JSON: {{"objetivo": nombre, "casos": [caso]}}.
Ejemplo: {ejemplo}

{MARCA_MODULO} {modulo["ruta"]}
{MARCA_OBJETIVOS} {json.dumps(objetivos, ensure_ascii=False)}
""".strip()

    # --- Endpoints FastAPI (HU-27) --------------------------------------------------

    def planificar_endpoints(
        self, modulo: dict[str, Any], fuente: str | None = None
    ) -> list[dict[str, Any]]:
        """Devuelve un `planner_contract.v2` de tipo "endpoint" por endpoint del módulo.

        Usa la salida del analizador (EN-14): método, ruta, estado declarado, modelos,
        parámetros, dependencias y `HTTPException`. El modelo de IA propone los casos
        en UNA llamada por módulo (como con las funciones, para no repetir las
        instrucciones en cada pedido); después una validación sin IA descarta los
        casos cuyo método, ruta, estado o campos no salen de la declaración.

        Args:
            modulo: un módulo de `analizar_proyecto()` (con `endpoints` y `modelos`).
            fuente: texto del módulo, para enviar al modelo solo el código de cada
                ruta (no el archivo entero). Si es None, se envía solo lo declarado.

        Raises:
            ErrorRespuestaPlanner: igual que `planificar`.
        """
        self.descartados = []
        self.avisos = []
        endpoints: dict[str, dict[str, Any]] = {}
        for endpoint in modulo.get("endpoints", []):
            objetivo = endpoint.get("objetivo")
            if not objetivo or not endpoint.get("resuelta", True):
                self.avisos.append(
                    f"{objetivo or endpoint.get('manejador')}: ruta sin resolver, "
                    "no se planifica (su prefijo final no se conoce sin ejecutar la app)"
                )
                continue
            endpoints[objetivo] = endpoint
        if not endpoints:
            return []

        aplicacion = _aplicacion_principal(endpoints.values())
        prompt = (
            self._crear_prompt_endpoints_humo(modulo, endpoints)
            if self.es_humo
            else self._crear_prompt_endpoints(modulo, endpoints, fuente)
        )
        respuesta = self.cliente.generar(prompt, rol="planner")
        self.tracker.registrar(
            agente="planner",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
            funcion=f"{modulo['ruta']} (endpoints)",
        )
        propuesta = _leer_lista(respuesta.contenido)

        modelos = {m["nombre"]: m for m in modulo.get("modelos", [])}
        plan: list[dict[str, Any]] = []
        for elemento in propuesta:
            if not isinstance(elemento, dict):
                self.descartados.append("un elemento del plan no es un objeto JSON")
                continue
            objetivo = elemento.get("objetivo")
            if objetivo not in endpoints:
                self.descartados.append(f"endpoint desconocido: {objetivo!r}")
                continue
            if any(c["objetivo"] == objetivo for c in plan):
                self.descartados.append(f"endpoint repetido: {objetivo}")
                continue
            contrato = self._contrato_endpoint(
                modulo,
                endpoints[objetivo],
                elemento.get("casos"),
                modelos,
                aplicacion,
            )
            if contrato is not None:
                plan.append(contrato)
                if not self.es_humo:  # Humo no busca los casos de error
                    self.avisos.extend(
                        faltantes(endpoints[objetivo], contrato["casos"])
                    )

        if propuesta and not plan:
            detalle = "; ".join(self.descartados[:3])
            raise ErrorRespuestaPlanner(
                f"El Planner no produjo ningún contrato de endpoint válido ({detalle})."
            )
        return plan

    def _contrato_endpoint(
        self,
        modulo: dict[str, Any],
        endpoint: dict[str, Any],
        casos: Any,
        modelos: dict[str, dict[str, Any]],
        aplicacion: str,
    ) -> dict[str, Any] | None:
        objetivo = endpoint["objetivo"]
        base = {
            "version": "2",
            "modulo": modulo["ruta"],
            "huella": modulo["huella"],
            "tipo": "endpoint",
            "objetivo": objetivo,
            "manejador": endpoint["manejador"],
            "aplicacion": aplicacion,
            "dependencias": _dependencias_con_reemplazo(modulo, endpoint),
            "firma": endpoint.get("firma") or "()",
            "critical": bool(endpoint.get("critical", False)),
            "llama_a": list(dict.fromkeys(endpoint.get("llama_a") or [])),
        }
        validos: list[dict[str, Any]] = []
        for caso in casos if isinstance(casos, list) else []:
            if not isinstance(caso, dict):
                self.descartados.append(f"{objetivo}: un caso no es un objeto JSON")
                continue
            if any(caso.get("id") == previo["id"] for previo in validos):
                self.descartados.append(f"{objetivo}: caso repetido {caso.get('id')!r}")
                continue
            try:
                contracts.validar(contracts.PLANNER, {**base, "casos": [caso]})
            except ContratoInvalido as error:
                self.descartados.append(f"{objetivo}: caso {caso.get('id')!r}: {error}")
                continue
            motivo = motivo_rechazo(endpoint, caso, modelos)
            if motivo:
                self.descartados.append(f"{objetivo}: caso {caso['id']!r}: {motivo}")
                continue
            caso = self._con_categoria(objetivo, caso)
            motivo = motivo_limite_endpoint(endpoint, caso, modelos)
            if motivo:
                self.descartados.append(f"{objetivo}: caso {caso['id']!r}: {motivo}")
                continue
            validos.append(caso)
        if self.es_humo:
            exito = endpoint.get("status_code") or 200
            validos = self._solo_un_caso_normal(
                objetivo,
                validos,
                lambda caso: (
                    caso["valor_esperado"]["status_code"] == exito
                    and categoria_de(caso) == "normal"
                ),
            )
        if not validos:
            self.descartados.append(
                f"{objetivo}: sin un caso con la respuesta exitosa declarada"
                if self.es_humo
                else f"{objetivo}: sin casos válidos"
            )
            return None
        contrato = {**base, "casos": validos}
        contracts.validar(contracts.PLANNER, contrato)
        return contrato

    @staticmethod
    def _crear_prompt_endpoints(
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
    def _crear_prompt_endpoints_humo(
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
- Devuelve SOLO una lista JSON: {{"objetivo": "MÉTODO /ruta", "casos": [caso]}}.
Ejemplo: {ejemplo}

MODELOS: {json.dumps(modelos, ensure_ascii=False)}
{MARCA_MODULO} {modulo["ruta"]}
{MARCA_OBJETIVOS} {json.dumps(objetivos, ensure_ascii=False)}
""".strip()


def es_normal_funcion(caso: dict[str, Any]) -> bool:
    """Caso normal de una función: espera un valor, no una excepción (#75, #76)."""
    return (
        "valor_esperado" in caso
        and "excepcion" not in caso
        and categoria_de(caso) == "normal"
    )


def es_normal_endpoint(caso: dict[str, Any]) -> bool:
    """Caso normal guardado de un endpoint: espera una respuesta 2xx (#75, #76)."""
    estado = (caso.get("valor_esperado") or {}).get("status_code")
    return (
        isinstance(estado, int)
        and 200 <= estado < 300
        and categoria_de(caso) == "normal"
    )


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


def contrato_humo(contrato: dict[str, Any]) -> dict[str, Any] | None:
    """El contrato con solo su primer caso normal, para usar una spec en Humo (#75).

    None si no tiene ninguno: entonces la spec no sirve para Humo y se replanifica.
    """
    es_normal = (
        es_normal_endpoint if contrato.get("tipo") == "endpoint" else es_normal_funcion
    )
    normal = next((c for c in contrato.get("casos") or [] if es_normal(c)), None)
    return None if normal is None else {**contrato, "casos": [normal]}


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


def _quitar_cerca_json(contenido: str) -> str:
    """Elimina una cerca Markdown ```json si el modelo la agregó."""
    texto = contenido.strip()
    if not texto.startswith("```"):
        return texto

    lineas = texto.splitlines()
    if lineas and lineas[0].strip().startswith("```"):
        lineas.pop(0)
    if lineas and lineas[-1].strip() == "```":
        lineas.pop()
    return "\n".join(lineas).strip()


# --- Validación de casos de endpoint sin IA (HU-27) ------------------------------

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


def _leer_lista(contenido: str) -> list[Any]:
    try:
        propuesta = json.loads(_quitar_cerca_json(contenido))
    except json.JSONDecodeError as error:
        raise ErrorRespuestaPlanner("El Planner no devolvió JSON válido.") from error
    if not isinstance(propuesta, list):
        raise ErrorRespuestaPlanner("El Planner debe devolver una lista de objetivos.")
    return propuesta

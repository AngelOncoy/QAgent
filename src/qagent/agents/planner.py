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

Una función cuyo valor esperado no se puede deducir de su firma, tipos o docstring (por
ejemplo, devuelve un token con la hora actual o un objeto de una biblioteca) queda
**omitida** con un aviso (`omitidas`): el modelo no propone casos o solo propone casos
que no se pueden respaldar. No es un error: la corrida sigue con las demás funciones y,
si se omiten todas las del módulo, el módulo termina sin objetivos.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from qagent import contracts
from qagent.contracts import ContratoInvalido, categoria_de, es_caso_de_error
from qagent.lenguajes import LanguageAdapter, adaptador_de_contrato, adaptador_para
from qagent.llm import ClienteLLM, TokenTracker

#: Perfil de comprobación rápida (#75); igual que `qagent.storage.registro.PERFIL_HUMO`.
PERFIL_HUMO = "humo"


# Contrato mínimo para validar un caso suelto contra el schema del Planner.
#: Por qué se omite una función sin valor esperado deducible (fuera de Humo y en Humo).
MOTIVO_OMITIDA = (
    "no se pudo deducir un resultado esperado verificable a partir de la firma, "
    "los tipos ni el docstring; se requiere información adicional sobre su comportamiento"
)
MOTIVO_OMITIDA_HUMO = (
    "no hay un caso normal deducible con resultado verificable de la firma, los tipos "
    "ni el docstring"
)

# Campos fijos para validar un caso suelto contra el schema (el encabezado del
# lenguaje lo agrega `PlannerAgent._encabezado`).
_CONTRATO_DE_PRUEBA = {
    "modulo": "x",
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
        adaptador: LanguageAdapter | None = None,
    ) -> None:
        """Inicializa el Planner con su cliente y registro de tokens.

        Args:
            perfil: perfil de la corrida; con `humo` planifica un caso normal por
                objetivo (#75).
            adaptador: adaptador del lenguaje del proyecto (#168): pone `lenguaje` y
                los frameworks del contrato. Sin él, el de los contratos anteriores
                a EN-17.
        """
        self.adaptador = adaptador or adaptador_para(
            contracts.LENGUAJE_CONTRATOS_ANTERIORES
        )
        #: Prompts y filtros de casos del lenguaje (#168).
        self.reglas = self.adaptador.reglas_planificacion()
        self.cliente = cliente
        self.tracker = tracker
        self.es_simulado = es_simulado
        self.perfil = perfil
        #: Qué se descartó en la última llamada (objetivos o casos) y por qué.
        self.descartados: list[str] = []
        #: Casos mínimos que faltan en el último plan de endpoints (no lo descartan) y,
        #: en Humo, los casos de más que se dejaron fuera.
        self.avisos: list[str] = []
        #: Funciones del último plan sin valor esperado deducible: nombre → motivo.
        self.omitidas: dict[str, str] = {}
        # Casos con formato inválido en la última llamada (errores del modelo, no
        # falta de especificación).
        self._casos_invalidos = 0
        # #138: casos triviales descartados por objetivo en la última llamada.
        self._triviales: dict[str, int] = {}

    def _encabezado(self, tipo: str) -> dict[str, Any]:
        """Campos de `planner_contract.v3` que salen del adaptador, no del modelo."""
        encabezado = {
            "version": "3",
            "lenguaje": self.adaptador.lenguaje,
            "framework_pruebas": self.adaptador.framework_predeterminado,
        }
        if tipo == "endpoint":
            encabezado["framework_app"] = self.adaptador.frameworks_app[0]
        return encabezado

    @property
    def es_humo(self) -> bool:
        """Si la corrida es Humo: un caso normal por objetivo (#75)."""
        return self.perfil == PERFIL_HUMO

    def planificar(self, modulo: dict[str, Any]) -> list[dict[str, Any]]:
        """Devuelve un `planner_contract.v3` por cada función del módulo con casos.

        Los objetivos que no existen en el módulo y los casos inválidos se descartan
        (quedan en `self.descartados`); las funciones sin valor esperado deducible
        quedan en `self.omitidas`. Ninguno de los dos tumba la corrida del módulo.

        Raises:
            ErrorRespuestaPlanner: si la respuesta no es una lista JSON (un objeto
                suelto con "objetivo" cuenta como lista de uno, #135), o si ninguna
                función produce un contrato válido por errores del modelo (y no porque
                su valor esperado no se pueda deducir).
        """
        self.descartados = []
        self.avisos = []
        self.omitidas = {}
        self._casos_invalidos = 0
        self._triviales = {}
        funciones = {f["nombre"]: f for f in modulo.get("funciones", [])}
        if not funciones:
            return []

        prompt = self.reglas.prompt_funciones(modulo, self.es_humo)
        respuesta = self.cliente.generar(prompt, rol="planner")
        self.tracker.registrar(
            agente="planner",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
            es_estimado=getattr(respuesta, "es_estimado", False),
        )

        propuesta = _leer_lista(respuesta.contenido)

        plan: list[dict[str, Any]] = []
        for elemento in propuesta:
            vistos = {contrato["objetivo"] for contrato in plan}
            contrato = self._armar_contrato(modulo, funciones, elemento, vistos)
            if contrato is not None:
                plan.append(contrato)

        # El modelo omite las funciones que no puede respaldar (lo pide el prompt).
        cubiertas = {contrato["objetivo"] for contrato in plan} | set(self.omitidas)
        intentadas = {
            e.get("objetivo") for e in propuesta if isinstance(e, dict)
        } & set(funciones)
        for nombre, funcion in funciones.items():
            if nombre not in cubiertas and nombre not in intentadas:
                self._omitir(nombre, funcion)

        if not plan and self.descartados and not self.omitidas:
            detalle = "; ".join(self.descartados[:3])
            raise ErrorRespuestaPlanner(
                f"El Planner no produjo ningún contrato válido ({detalle})."
            )
        return plan

    def _omitir(self, nombre: str, funcion: dict[str, Any] | None = None) -> None:
        """Deja la función como omitida: su valor esperado no se puede deducir."""
        motivo = MOTIVO_OMITIDA_HUMO if self.es_humo else MOTIVO_OMITIDA
        if self._triviales.get(nombre):
            motivo = self.reglas.motivo_omitida_trivial  # #138
        if funcion is not None and not funcion.get("docstring"):
            motivo = f"la función no tiene docstring y {motivo}"
        self.omitidas[nombre] = motivo

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
        invalidos_antes = self._casos_invalidos
        casos = self._casos_validos(nombre, elemento.get("casos"), funcion)
        if self.es_humo:
            casos = self._solo_un_caso_normal(nombre, casos, es_normal_funcion)
        if not casos:
            if self._casos_invalidos == invalidos_antes:
                # Sin casos o solo con casos que la especificación no respalda: el
                # valor esperado no se puede deducir. No es un error del modelo.
                self._omitir(nombre, funcion)
            else:
                self.descartados.append(f"{nombre}: sin casos válidos")
            return None

        contrato = {
            **self._encabezado("funcion"),
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
            contracts.validar(contracts.PLANNER_V3, contrato)
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
                self._casos_invalidos += 1
                self.descartados.append(f"{nombre}: un caso no es un objeto JSON")
                continue
            if any(caso.get("id") == previo["id"] for previo in validos):
                self._casos_invalidos += 1
                self.descartados.append(f"{nombre}: caso repetido {caso.get('id')!r}")
                continue
            caso = self.reglas.preparar_caso(funcion or {}, caso)
            try:
                contracts.validar(
                    contracts.PLANNER_V3,
                    {
                        **self._encabezado("funcion"),
                        **_CONTRATO_DE_PRUEBA,
                        "casos": [caso],
                    },
                )
            except ContratoInvalido as error:
                self._casos_invalidos += 1
                self.descartados.append(f"{nombre}: caso {caso.get('id')!r}: {error}")
                continue
            if self.reglas.es_caso_trivial(funcion or {}, caso):
                # #138: no prueba la función. Es falta de especificación, no un error
                # del modelo: si era su único caso, el objetivo queda omitido.
                self._triviales[nombre] = self._triviales.get(nombre, 0) + 1
                self.descartados.append(
                    f"{nombre}: caso {caso.get('id')!r}: "
                    f"{self.reglas.motivo_caso_trivial}"
                )
                continue
            caso = self._con_categoria(nombre, caso)
            motivo = self.reglas.motivo_limite_funcion(funcion or {}, caso)
            if motivo:
                self.descartados.append(f"{nombre}: caso {caso['id']!r}: {motivo}")
                continue
            motivo = self.reglas.motivo_oraculo_funcion(funcion or {}, caso)
            if motivo:
                # La estructura JSON es válida, pero su oráculo no está respaldado
                # por la procedencia declarada. Es falta de especificación, no una
                # respuesta malformada del proveedor; el objetivo puede omitirse.
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

    # --- Endpoints FastAPI (HU-27) --------------------------------------------------

    def planificar_endpoints(
        self, modulo: dict[str, Any], fuente: str | None = None
    ) -> list[dict[str, Any]]:
        """Devuelve un `planner_contract.v3` de tipo "endpoint" por endpoint del módulo.

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

        aplicacion = self.reglas.aplicacion_principal(endpoints.values())
        prompt = self.reglas.prompt_endpoints(modulo, endpoints, fuente, self.es_humo)
        respuesta = self.cliente.generar(prompt, rol="planner")
        self.tracker.registrar(
            agente="planner",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
            es_estimado=getattr(respuesta, "es_estimado", False),
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
                        self.reglas.faltantes_endpoint(
                            endpoints[objetivo], contrato["casos"]
                        )
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
            **self._encabezado("endpoint"),
            "modulo": modulo["ruta"],
            "huella": modulo["huella"],
            "tipo": "endpoint",
            "objetivo": objetivo,
            "manejador": endpoint["manejador"],
            "aplicacion": aplicacion,
            "dependencias": self.reglas.dependencias_con_reemplazo(modulo, endpoint),
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
                contracts.validar(contracts.PLANNER_V3, {**base, "casos": [caso]})
            except ContratoInvalido as error:
                self.descartados.append(f"{objetivo}: caso {caso.get('id')!r}: {error}")
                continue
            motivo = self.reglas.motivo_rechazo_endpoint(endpoint, caso, modelos)
            if motivo:
                self.descartados.append(f"{objetivo}: caso {caso['id']!r}: {motivo}")
                continue
            caso = self._con_categoria(objetivo, caso)
            motivo = self.reglas.motivo_limite_endpoint(endpoint, caso, modelos)
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
        try:
            contracts.validar(contracts.PLANNER_V3, contrato)
        except ContratoInvalido as error:
            self.descartados.append(f"{objetivo}: {error}")
            return None
        return contrato


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


def contrato_humo(contrato: dict[str, Any]) -> dict[str, Any] | None:
    """El contrato con solo su primer caso normal, para usar una spec en Humo (#75).

    None si no tiene ninguno: entonces la spec no sirve para Humo y se replanifica.
    """
    es_normal = (
        es_normal_endpoint if contrato.get("tipo") == "endpoint" else es_normal_funcion
    )
    normal = next((c for c in contrato.get("casos") or [] if es_normal(c)), None)
    return None if normal is None else {**contrato, "casos": [normal]}


def contrato_sin_triviales(contrato: dict[str, Any]) -> dict[str, Any] | None:
    """El contrato sin sus casos triviales, para reutilizar una spec guardada (#138).

    Las specs guardadas antes de #138 pueden traer la llamada con argumentos que no
    encajan con la firma. None si no le queda ningún caso: la spec no sirve y el
    objetivo se vuelve a planificar (y, si no hay más, queda omitido).
    """
    if contrato.get("tipo") == "endpoint":
        return contrato
    reglas = adaptador_de_contrato(contrato).reglas_planificacion()
    casos = [
        c
        for c in contrato.get("casos") or []
        if not reglas.es_caso_trivial(contrato, c)
    ]
    if not casos:
        return None
    return (
        contrato
        if len(casos) == len(contrato["casos"])
        else {**contrato, "casos": casos}
    )


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


def _leer_lista(contenido: str) -> list[Any]:
    """Lee la lista de objetivos que devuelve el Planner (funciones y endpoints).

    #135: con un solo objetivo el modelo a veces devuelve el objeto suelto en vez de una
    lista de uno. Un objeto con la clave "objetivo" se toma como esa lista; cada elemento
    se valida después igual que siempre. Cualquier otra forma sigue siendo un error.

    Raises:
        ErrorRespuestaPlanner: si no es JSON, o no es una lista ni un objeto con
            "objetivo". El mensaje dice qué se recibió, sin copiar la respuesta.
    """
    try:
        propuesta = json.loads(_quitar_cerca_json(contenido))
    except json.JSONDecodeError as error:
        raise ErrorRespuestaPlanner("El Planner no devolvió JSON válido.") from error
    if isinstance(propuesta, dict) and "objetivo" in propuesta:
        return [propuesta]
    if not isinstance(propuesta, list):
        raise ErrorRespuestaPlanner(
            "El Planner debe devolver una lista de objetivos; se recibió "
            f"{_describir_json(propuesta)}."
        )
    return propuesta


def _describir_json(valor: Any) -> str:
    """Qué tipo de valor JSON es, en palabras, para los mensajes de error (#135)."""
    if isinstance(valor, dict):
        return 'un objeto sin "objetivo"'
    if isinstance(valor, str):
        return "un texto"
    if isinstance(valor, bool):
        return "un valor booleano"
    if isinstance(valor, int | float):
        return "un número"
    if valor is None:
        return "null"
    return "un valor no válido"

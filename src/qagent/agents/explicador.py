"""Agente Explicador, paso 1: explicaciones con plantillas, sin IA (HU-32, ADR-008).

Después del veredicto, arma una explicación en lenguaje simple por cada objetivo que
no terminó en `accept`: qué se esperaba, qué pasó y qué revisar. Solo lee lo que la
corrida ya guardó (`results.json` y `detalle.json`); no ejecuta código, no llama a
otros agentes ni a un LLM (0 tokens) y nunca cambia decisiones, intentos, cobertura ni
`laundering_detectado`.

La salida cumple el contrato `explicaciones` (EN-21) con `origen: "plantilla"` y
`modelo: null`. Una explicación que no pasa `validar_explicacion` se descarta y su
motivo se devuelve para registrarlo en el log; las demás se conservan.

Paso 2 (#166): con un `RedactorIA`, cada explicación la redacta un LLM a partir de
toda la traza de intentos del objetivo, y la plantilla queda de respaldo. Si la
respuesta no cumple el contrato, contradice la decisión, propone relajar una aserción,
o si el LLM falla, tarda demasiado o no queda presupuesto, se usa la plantilla y el
motivo se devuelve para el log. La IA nunca cambia el veredicto: solo lo explica.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qagent import contracts
from qagent.llm.cliente import estimar_tokens
from qagent.llm.modelos import ClienteLLM, RespuestaLLM
from qagent.llm.precios import PrecioAgente
from qagent.llm.tracker import TokenTracker
from qagent.storage.exportar_informe import sanitizar_secretos

VERSION = "1"
ORIGEN = "plantilla"
ORIGEN_IA = "ia"
#: Nombre del agente en el `TokenTracker` y en log.json.
AGENTE = "explicador"

#: Tipos de hallazgo, uno por plantilla. Laundering no es un valor de `decision`: sale
#: de `laundering_detectado` y tiene prioridad sobre la decisión.
LAUNDERING = "assertion_laundering"
BUG = "bug_detectado"
ESTANCADA = "estancada"
SIN_VEREDICTO = "sin_veredicto"
CORRIDA_NUEVA = "requiere_corrida_nueva"
TIPOS = (LAUNDERING, BUG, ESTANCADA, SIN_VEREDICTO, CORRIDA_NUEVA)

#: Largo máximo de un valor citado (entrada, esperado u obtenido).
LARGO_MAXIMO_VALOR = 120

#: Caracteres finales del `feedback` de cada intento que recibe el LLM (#166): el
#: resumen de pytest está al final.
LARGO_MAXIMO_FEEDBACK = 600
#: Casos del contrato que recibe el LLM, como máximo.
MAXIMO_CASOS_IA = 8
#: Tokens que se reservan para la respuesta al revisar el presupuesto antes de llamar.
TOKENS_RESERVA_RESPUESTA = 800
#: Campos que el LLM debe devolver; el resto de la explicación lo completa QAgent.
CAMPOS_IA = ("decision", "resumen", "que_se_esperaba", "que_paso", "que_hacer")

# Rutas absolutas de Windows (C:\..., \\servidor\...) y de Linux o macOS (/home/...).
_RUTA_ABSOLUTA = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'<>|]*|(?<![\w.:])/(?:[\w.-]+/)+[\w.-]*"
)


@dataclass
class ResultadoExplicador:
    """Explicaciones válidas de la corrida y por qué se descartó cada una de las otras.

    `respaldos` dice, por objetivo, por qué se usó la plantilla en lugar del LLM (#166).
    """

    datos: dict[str, Any]
    descartadas: list[str] = field(default_factory=list)
    respaldos: list[str] = field(default_factory=list)


def tipo_de_hallazgo(objetivo: dict[str, Any]) -> str | None:
    """Tipo de hallazgo de un objetivo de `results.json`; None si fue aceptado."""
    decision = objetivo.get("decision")
    if decision == "accept":
        return None
    if objetivo.get("laundering_detectado"):
        return LAUNDERING
    if decision is None:
        return SIN_VEREDICTO
    if decision == "stalled":
        return ESTANCADA
    if decision == "requiere_corrida_nueva":
        return CORRIDA_NUEVA
    return BUG


def explicar_corrida(
    results: dict[str, Any],
    detalle: dict[str, Any] | None = None,
    redactor: RedactorIA | None = None,
    docstrings: dict[tuple[str, str], str | None] | None = None,
) -> ResultadoExplicador:
    """Explicaciones de todos los objetivos no aceptados de una corrida.

    Args:
        results: contenido de `results.json`.
        detalle: contenido de `detalle.json` (contrato e intentos de cada función);
            sin él las explicaciones se arman solo con `results.json`.
        redactor: con él, cada explicación la pide al LLM y la plantilla queda de
            respaldo (#166); sin él, todas salen de las plantillas.
        docstrings: docstring de cada objetivo por `(modulo, objetivo)`, del análisis
            estático; el contrato del Planner no lo guarda.

    Returns:
        El contenido de `explicaciones.json`, los motivos de las descartadas y por
        qué se usó la plantilla en lugar del LLM.
    """
    funciones = {
        (f.get("modulo"), f.get("funcion")): f
        for f in (detalle or {}).get("funciones") or []
    }
    explicaciones: list[dict[str, Any]] = []
    descartadas: list[str] = []
    respaldos: list[str] = []
    for objetivo in results.get("objetivos") or []:
        if tipo_de_hallazgo(objetivo) is None:
            continue
        clave = (objetivo.get("modulo"), objetivo.get("funcion"))
        funcion = funciones.get(clave)
        explicacion = None
        if redactor is not None:
            try:
                explicacion = redactor.redactar(
                    objetivo,
                    funcion,
                    results.get("run_id"),
                    (docstrings or {}).get(clave),  # type: ignore[arg-type]
                )
            except SinExplicacionIA as motivo:
                respaldos.append(f"{objetivo.get('funcion')}: {motivo}")
        if explicacion is None:
            explicacion = explicar_objetivo(objetivo, funcion, results.get("run_id"))
        try:
            contracts.validar_explicacion(explicacion, resultado_confiable=objetivo)
        except contracts.ContratoInvalido as error:
            descartadas.append(f"{objetivo.get('funcion')}: {'; '.join(error.errores)}")
            continue
        explicaciones.append(explicacion)

    datos: dict[str, Any] = {
        "version": VERSION,
        "tipo": "explicaciones",
        "explicaciones": explicaciones,
    }
    if results.get("run_id"):
        datos["run_id"] = results["run_id"]
    return ResultadoExplicador(datos, descartadas, respaldos)


def explicar_objetivo(
    objetivo: dict[str, Any],
    funcion: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Explicación `explanation.v1` de un objetivo no aceptado, armada con plantillas.

    Args:
        objetivo: el objetivo de `results.json`.
        funcion: la función de `detalle.json` con el mismo módulo y nombre, si existe.
        run_id: identificador de la corrida.
    """
    tipo = tipo_de_hallazgo(objetivo)
    if tipo is None:
        raise ValueError("un objetivo aceptado no lleva explicación")
    hechos = _Hechos.de(objetivo, funcion)
    plantilla = _PLANTILLAS[tipo]
    explicacion: dict[str, Any] = {
        "version": VERSION,
        "objetivo": str(objetivo["funcion"]),
        "decision": objetivo.get("decision"),
        **{campo: _limpiar(texto) for campo, texto in plantilla(hechos).items()},
        "origen": ORIGEN,
        "modelo": None,
    }
    if objetivo.get("modulo"):
        explicacion["modulo"] = _limpiar(str(objetivo["modulo"]))
    if run_id:
        explicacion["run_id"] = run_id
    return explicacion


@dataclass(frozen=True)
class _Hechos:
    """Lo que las plantillas citan de un objetivo, ya en palabras simples."""

    nombre: str
    es_endpoint: bool
    intentos: int
    motivo_estancado: str | None
    motivo_sin_veredicto: str | None
    promesas: list[str]
    entrada: str | None
    esperado: str | None
    obtenido: str | None

    @classmethod
    def de(cls, objetivo: dict[str, Any], funcion: dict[str, Any] | None) -> _Hechos:
        contrato = (funcion or {}).get("contrato") or {}
        casos = contrato.get("casos") or []
        fallido = _caso_que_falla(funcion)
        caso = _caso_del_contrato(casos, fallido)
        esperado = (fallido or {}).get("esperado")
        if esperado is None and caso is not None:
            esperado = _esperado_del_contrato(caso)
        return cls(
            nombre=str(objetivo.get("funcion") or "la función"),
            es_endpoint=objetivo.get("tipo") == "endpoint",
            intentos=int((objetivo.get("metricas") or {}).get("iteraciones") or 0),
            motivo_estancado=objetivo.get("motivo_estancado"),
            motivo_sin_veredicto=objetivo.get("motivo_sin_veredicto"),
            promesas=[
                str(c["descripcion"]).rstrip(".") for c in casos if c.get("descripcion")
            ][:3],
            entrada=_entrada(caso.get("entrada")) if caso else None,
            esperado=_valor(esperado),
            obtenido=_valor((fallido or {}).get("obtenido")),
        )

    @property
    def sujeto(self) -> str:
        return (
            f"la ruta {self.nombre}"
            if self.es_endpoint
            else f"la función {self.nombre}"
        )

    @property
    def promesa(self) -> str:
        """Qué prometía el objetivo según su documentación (los casos del Planner)."""
        if not self.promesas:
            return (
                f"Que {self.sujeto} hiciera lo que dicen su documentación y sus tipos."
            )
        return (
            f"Lo que la documentación de {self.sujeto} promete: "
            + "; ".join(_minuscula(p) for p in self.promesas)
            + "."
        )

    @property
    def veces(self) -> str:
        """Cantidad de intentos entre paréntesis, o nada si no se registró."""
        if self.intentos <= 0:
            return ""
        return f" ({self.intentos} intento{'s' if self.intentos != 1 else ''})"


def _bug(h: _Hechos) -> dict[str, str]:
    if h.esperado is not None and h.obtenido is not None:
        con = f"Con {h.entrada}, " if h.entrada else ""
        que_paso = (
            f"{con}{h.sujeto} dio {h.obtenido}, pero debía dar {h.esperado}. "
            f"La prueba se ejecutó en un entorno aislado{h.veces}."
        )
    else:
        que_paso = (
            f"En al menos uno de los casos, {h.sujeto} no se comportó como prometía. "
            f"La prueba se ejecutó en un entorno aislado{h.veces}."
        )
    return {
        "resumen": f"Se encontró un posible error en {h.sujeto}.",
        "que_se_esperaba": h.promesa,
        "que_paso": que_paso,
        "que_hacer": (
            f"Revisa el código de {h.sujeto}: la documentación describe el "
            "comportamiento correcto, así que el arreglo va en la función. Cuando la "
            "corrijas, vuelve a ejecutar las pruebas."
        ),
    }


_ESTANCADA_QUE_PASO = {
    "limite_intentos": (
        "QAgent intentó escribir una prueba que funcionara{veces} y no lo logró, "
        "así que dejó de intentarlo."
    ),
    "error_repetido": (
        "La prueba falló dos veces seguidas por el mismo motivo{veces}, así que "
        "QAgent dejó de intentarlo para no gastar más."
    ),
    "limite_tokens": (
        "Se alcanzó el tope de gasto de IA de la corrida antes de terminar con "
        "{sujeto}{veces}."
    ),
}


def _estancada(h: _Hechos) -> dict[str, str]:
    plantilla = _ESTANCADA_QUE_PASO.get(
        h.motivo_estancado or "", _ESTANCADA_QUE_PASO["limite_intentos"]
    )
    if h.motivo_estancado == "limite_tokens":
        que_hacer = (
            f"Vuelve a ejecutar {h.sujeto} sola o sube el tope de gasto en "
            "Configuración. No hace falta tocar tu código."
        )
    else:
        que_hacer = (
            f"Revisa que la documentación de {h.sujeto} diga con claridad qué recibe "
            "y qué devuelve, con un ejemplo si se puede, y vuelve a ejecutar. Esto no "
            "significa que tu código tenga un error."
        )
    return {
        "resumen": f"No se pudo terminar la prueba de {h.sujeto}.",
        "que_se_esperaba": h.promesa,
        "que_paso": plantilla.format(veces=h.veces, sujeto=h.sujeto),
        "que_hacer": que_hacer,
    }


_SIN_VEREDICTO_QUE_PASO = {
    "tiempo_agotado": (
        "Un paso de la revisión o el proveedor de IA tardó demasiado en responder, "
        "así que no hubo resultado."
    ),
    "error_contrato_planner": (
        "El plan de casos que se armó para {sujeto} salió incompleto, así que no se "
        "pudo escribir su prueba."
    ),
    "error_planner": (
        "Hubo un problema al planificar los casos de {sujeto}, así que no se llegó a "
        "probar."
    ),
}


def _sin_veredicto(h: _Hechos) -> dict[str, str]:
    que_paso = _SIN_VEREDICTO_QUE_PASO.get(
        h.motivo_sin_veredicto or "",
        "La corrida se detuvo antes de llegar a un resultado para {sujeto}.",
    ).format(sujeto=h.sujeto)
    return {
        "resumen": f"No hay resultado para {h.sujeto}.",
        "que_se_esperaba": h.promesa,
        "que_paso": que_paso,
        "que_hacer": (
            "Vuelve a ejecutar la corrida. Si se repite, revisa tu conexión y la "
            "cuenta del proveedor de IA en Configuración. Esto no dice nada sobre si "
            "tu código está bien o mal."
        ),
    }


def _laundering(h: _Hechos) -> dict[str, str]:
    return {
        "resumen": f"Se descartó una prueba de {h.sujeto} porque se había debilitado.",
        "que_se_esperaba": h.promesa,
        "que_paso": (
            "Una versión de la prueba dejaba de comprobar lo que la documentación "
            "promete, y así habría pasado sin demostrar nada. QAgent la detectó y la "
            f"descartó{h.veces}: no cuenta como aprobada."
        ),
        "que_hacer": (
            f"Revisa el código de {h.sujeto} y su documentación: lo que la "
            "documentación promete sigue siendo lo que debe cumplirse. Cuando estén de "
            "acuerdo, vuelve a ejecutar las pruebas."
        ),
    }


def _corrida_nueva(h: _Hechos) -> dict[str, str]:
    return {
        "resumen": f"La prueba guardada de {h.sujeto} ya no sirve.",
        "que_se_esperaba": h.promesa,
        "que_paso": (
            f"El código de {h.sujeto} cambió desde que se guardó su prueba, o la "
            "prueba guardada ya no es válida, así que no se volvió a usar."
        ),
        "que_hacer": (
            "Ejecuta una corrida nueva (Estándar) para que QAgent prepare la prueba "
            "de nuevo a partir del código actual."
        ),
    }


_PLANTILLAS = {
    BUG: _bug,
    ESTANCADA: _estancada,
    SIN_VEREDICTO: _sin_veredicto,
    LAUNDERING: _laundering,
    CORRIDA_NUEVA: _corrida_nueva,
}


def _caso_que_falla(funcion: dict[str, Any] | None) -> dict[str, Any] | None:
    """Primer caso fallido del último intento que llegó a ejecutarse."""
    con = [i for i in (funcion or {}).get("intentos") or [] if i.get("ejecucion")]
    if not con:
        return None
    for caso in con[-1]["ejecucion"].get("casos") or []:
        if caso.get("resultado") in ("fallo", "error"):
            return caso
    return None


def _caso_del_contrato(
    casos: list[dict[str, Any]], fallido: dict[str, Any] | None
) -> dict[str, Any] | None:
    """El caso del contrato que corresponde al fallido (por su id en el nombre)."""
    if fallido is None:
        return None
    nombre = str(fallido.get("nombre") or "")
    for caso in casos:
        if caso.get("id") and str(caso["id"]) in nombre:
            return caso
    return None


def _esperado_del_contrato(caso: dict[str, Any]) -> Any:
    if caso.get("excepcion"):
        return f"un aviso de error ({caso['excepcion']})"
    return caso.get("valor_esperado")


def _entrada(entrada: Any) -> str | None:
    """Los argumentos del caso como `precio = 100.0, porcentaje = 20.0`."""
    if not entrada:
        return None
    if isinstance(entrada, dict):
        return _valor(", ".join(f"{k} = {_valor(v)}" for k, v in entrada.items()))
    return _valor(entrada)


def _valor(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
    texto = " ".join(texto.split())
    if len(texto) > LARGO_MAXIMO_VALOR:
        texto = texto[: LARGO_MAXIMO_VALOR - 1] + "…"
    return texto


def _minuscula(texto: str) -> str:
    return texto[:1].lower() + texto[1:] if texto else texto


def _limpiar(texto: str) -> str:
    """Sin claves (RN-07) ni rutas absolutas: de una ruta solo queda el archivo."""
    texto = sanitizar_secretos(texto)
    return _RUTA_ABSOLUTA.sub(lambda m: re.split(r"[\\/]", m.group(0))[-1], texto)


# --- Paso 2: explicaciones redactadas por un LLM (#166, ADR-008) ----------------------

#: Marca de la línea con la entrada del objetivo en el prompt; la IA simulada la lee.
MARCA_ENTRADA = "EXPLICACION_JSON:"

_INSTRUCCIONES = """Eres el Agente Explicador de QAgent. Explica a una persona con poca
experiencia en programación por qué una prueba automática no terminó bien. Habla de
«la función» o «la ruta», no de pytest ni de aserciones.

Reglas:
- No cambies ni pongas en duda la decisión: repite el valor de "decision" tal cual.
- No propongas relajar, quitar ni debilitar una comprobación, ni cambiar el valor
  esperado: lo que promete la documentación es lo correcto.
- Usa toda la traza de intentos, no solo el último error.
- Si la decisión es "stalled" o no hay decisión, aclara que eso no prueba que el
  código tenga un error.
- Frases cortas y concretas. Sin rutas de archivos ni datos que no estén abajo.

Responde solo con un objeto JSON, sin texto antes ni después, con estas claves:
"decision", "resumen", "que_se_esperaba", "que_paso", "que_hacer".
"""


class SinExplicacionIA(Exception):
    """El LLM no dio una explicación usable; el motivo va al log y se usa la plantilla."""


class RedactorIA:
    """Pide al LLM la explicación de cada objetivo, sin pasar los topes de la corrida.

    Solo lee lo que la corrida guardó; no ejecuta código ni llama a otros agentes.
    Registra cada llamada como agente `explicador` en el mismo `TokenTracker`.
    """

    def __init__(
        self,
        cliente: ClienteLLM,
        tracker: TokenTracker,
        precio: PrecioAgente,
        *,
        tiempo_maximo_s: float,
        max_tokens: int | None = None,
        tope_usd: float | None = None,
        es_simulado: bool = False,
        cancelado: Callable[[], bool] | None = None,
    ) -> None:
        """Prepara el redactor.

        Args:
            cliente: cliente LLM de `[agentes.explicador]`.
            tracker: el `TokenTracker` de la corrida.
            precio: modelo y precios del Explicador, para el costo de cada llamada.
            tiempo_maximo_s: segundos máximos por explicación.
            max_tokens: `max_tokens_por_corrida`; None si no hay tope de tokens.
            tope_usd: `tope_por_corrida_usd`; None si no hay tope de gasto.
            es_simulado: True con la IA simulada.
            cancelado: devuelve True si el usuario canceló la corrida.
        """
        self.cliente = cliente
        self.tracker = tracker
        self.precio = precio
        self.tiempo_maximo_s = tiempo_maximo_s
        self.max_tokens = max_tokens
        self.tope_usd = tope_usd
        self.es_simulado = es_simulado
        self.cancelado = cancelado

    def redactar(
        self,
        objetivo: dict[str, Any],
        funcion: dict[str, Any] | None = None,
        run_id: str | None = None,
        docstring: str | None = None,
    ) -> dict[str, Any]:
        """Explicación `explanation.v1` con `origen: "ia"`, ya validada.

        Raises:
            SinExplicacionIA: con el motivo por el que se usa la plantilla.
        """
        if self.cancelado is not None and self.cancelado():
            raise SinExplicacionIA("la corrida se canceló")
        entrada = entrada_ia(objetivo, funcion, docstring)
        prompt = (
            f"{_INSTRUCCIONES}\n{MARCA_ENTRADA} "
            f"{json.dumps(entrada, ensure_ascii=False)}"
        )
        self._revisar_presupuesto(prompt)
        respuesta = self._generar(prompt)
        modelo = respuesta.modelo or self.precio.modelo
        self.tracker.fijar_contexto_hilo(str(objetivo.get("funcion")), None)
        self.tracker.registrar(
            agente=AGENTE,
            modelo=modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=self.precio.costo(
                respuesta.tokens_entrada, respuesta.tokens_salida
            ),
            es_simulado=self.es_simulado,
            es_estimado=respuesta.es_estimado,
        )
        explicacion = _explicacion_ia(respuesta.contenido, objetivo, run_id, modelo)
        try:
            contracts.validar_explicacion(explicacion, resultado_confiable=objetivo)
        except contracts.ContratoInvalido as error:
            raise SinExplicacionIA(
                "la respuesta no cumple el contrato: " + "; ".join(error.errores)
            ) from error
        return explicacion

    def _revisar_presupuesto(self, prompt: str) -> None:
        """Corta antes de llamar si la llamada podría pasar algún tope de la corrida."""
        entrada = estimar_tokens(prompt)
        if self.max_tokens:
            previstos = self.tracker.total_tokens + entrada + TOKENS_RESERVA_RESPUESTA
            if previstos > self.max_tokens:
                raise SinExplicacionIA(
                    f"se alcanzó el presupuesto de tokens ({self.max_tokens})"
                )
        if self.tope_usd:
            costo = self.precio.costo(entrada, TOKENS_RESERVA_RESPUESTA)
            if self.tracker.total_costo_usd + costo > self.tope_usd:
                raise SinExplicacionIA(
                    f"se alcanzó el tope de gasto (US$ {self.tope_usd:.2f})"
                )

    def _generar(self, prompt: str) -> RespuestaLLM:
        """Llama al LLM en otro hilo y lo espera a lo sumo `tiempo_maximo_s`."""
        salida: dict[str, Any] = {}

        def llamar() -> None:
            try:
                salida["respuesta"] = self.cliente.generar(prompt, rol=AGENTE)
            except Exception as error:  # noqa: BLE001 — se informa abajo
                salida["error"] = error

        hilo = threading.Thread(target=llamar, name="explicador-ia", daemon=True)
        hilo.start()
        hilo.join(self.tiempo_maximo_s)
        if hilo.is_alive():
            raise SinExplicacionIA(
                f"el LLM no respondió en {self.tiempo_maximo_s:g} s (tiempo agotado)"
            )
        if "error" in salida:
            error = salida["error"]
            raise SinExplicacionIA(
                f"el LLM falló: {type(error).__name__}: {_limpiar(str(error))}"
            )
        return salida["respuesta"]


def entrada_ia(
    objetivo: dict[str, Any],
    funcion: dict[str, Any] | None = None,
    docstring: str | None = None,
) -> dict[str, Any]:
    """Lo que recibe el LLM de un objetivo (ADR-008, 5.2), sin secretos ni rutas.

    Incluye cada intento con su `tipo_fallo` y el final de su `feedback`, no solo el
    último; nunca el código del proyecto.
    """
    contrato = (funcion or {}).get("contrato") or {}
    metricas = objetivo.get("metricas") or {}
    fallido = _caso_que_falla(funcion)
    entrada = {
        "objetivo": objetivo.get("funcion"),
        "tipo": objetivo.get("tipo") or "funcion",
        "modulo": objetivo.get("modulo"),
        "decision": objetivo.get("decision"),
        "motivo_estancado": objetivo.get("motivo_estancado"),
        "motivo_sin_veredicto": objetivo.get("motivo_sin_veredicto"),
        "intentos": metricas.get("iteraciones"),
        "laundering_detectado": bool(objetivo.get("laundering_detectado")),
        "docstring": docstring,
        "casos": [
            {clave: caso[clave] for clave in _CLAVES_CASO if clave in caso}
            for caso in (contrato.get("casos") or [])[:MAXIMO_CASOS_IA]
        ],
        "traza": [
            {
                "intento": intento.get("intento"),
                "decision": intento.get("decision"),
                "estado_sandbox": intento.get("estado_sandbox"),
                "tipo_fallo": intento.get("tipo_fallo"),
                "laundering_detectado": intento.get("laundering_detectado"),
                "feedback": _recortar(intento.get("feedback")),
            }
            for intento in (funcion or {}).get("intentos") or []
        ],
        "primer_caso_fallido": (
            {
                "caso": fallido.get("nombre"),
                "esperado": _valor(fallido.get("esperado")),
                "obtenido": _valor(fallido.get("obtenido")),
            }
            if fallido
            else None
        ),
        "cobertura": {
            "lineas": metricas.get("cobertura_lineas"),
            "ramas": metricas.get("cobertura_ramas"),
        },
    }
    return _limpiar_estructura(entrada)


_CLAVES_CASO = ("id", "descripcion", "entrada", "valor_esperado", "excepcion", "origen")


def _explicacion_ia(
    contenido: str, objetivo: dict[str, Any], run_id: str | None, modelo: str
) -> dict[str, Any]:
    """Explicación completa a partir de la respuesta del LLM (sin validar aún)."""
    texto = contenido.strip()
    if texto.startswith("```"):  # algunos modelos envuelven el JSON en un bloque
        texto = texto.strip("`").removeprefix("json").strip()
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as error:
        raise SinExplicacionIA(f"la respuesta no es JSON ({error.msg})") from error
    if not isinstance(datos, dict):
        raise SinExplicacionIA("la respuesta no es un objeto JSON")
    faltan = [c for c in CAMPOS_IA if c not in datos]
    if faltan:
        raise SinExplicacionIA(f"a la respuesta le falta {', '.join(faltan)}")
    explicacion: dict[str, Any] = {
        "version": VERSION,
        "objetivo": str(objetivo["funcion"]),
        "decision": datos["decision"],
        **{
            campo: _limpiar(datos[campo]) if isinstance(datos[campo], str) else None
            for campo in CAMPOS_IA[1:]
        },
        "origen": ORIGEN_IA,
        "modelo": modelo,
    }
    if objetivo.get("modulo"):
        explicacion["modulo"] = _limpiar(str(objetivo["modulo"]))
    if run_id:
        explicacion["run_id"] = run_id
    return explicacion


def _recortar(feedback: Any) -> str | None:
    """El final del feedback de un intento, como mucho `LARGO_MAXIMO_FEEDBACK`."""
    if not feedback:
        return None
    texto = str(feedback).strip()
    if len(texto) > LARGO_MAXIMO_FEEDBACK:
        texto = "…" + texto[-(LARGO_MAXIMO_FEEDBACK - 1) :]
    return texto


def _limpiar_estructura(dato: Any) -> Any:
    """`_limpiar` en cada texto de un diccionario o lista."""
    if isinstance(dato, str):
        return _limpiar(dato)
    if isinstance(dato, dict):
        return {clave: _limpiar_estructura(valor) for clave, valor in dato.items()}
    if isinstance(dato, list):
        return [_limpiar_estructura(valor) for valor in dato]
    return dato

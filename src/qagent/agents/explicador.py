"""Agente Explicador, paso 1: explicaciones con plantillas, sin IA (HU-32, ADR-008).

Después del veredicto, arma una explicación en lenguaje simple por cada objetivo que
no terminó en `accept`: qué se esperaba, qué pasó y qué revisar. Solo lee lo que la
corrida ya guardó (`results.json` y `detalle.json`); no ejecuta código, no llama a
otros agentes ni a un LLM (0 tokens) y nunca cambia decisiones, intentos, cobertura ni
`laundering_detectado`.

La salida cumple el contrato `explicaciones` (EN-21) con `origen: "plantilla"` y
`modelo: null`. Una explicación que no pasa `validar_explicacion` se descarta y su
motivo se devuelve para registrarlo en el log; las demás se conservan.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from qagent import contracts
from qagent.storage.exportar_informe import sanitizar_secretos

VERSION = "1"
ORIGEN = "plantilla"

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

# Rutas absolutas de Windows (C:\..., \\servidor\...) y de Linux o macOS (/home/...).
_RUTA_ABSOLUTA = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'<>|]*|(?<![\w.:])/(?:[\w.-]+/)+[\w.-]*"
)


@dataclass
class ResultadoExplicador:
    """Explicaciones válidas de la corrida y por qué se descartó cada una de las otras."""

    datos: dict[str, Any]
    descartadas: list[str] = field(default_factory=list)


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
    results: dict[str, Any], detalle: dict[str, Any] | None = None
) -> ResultadoExplicador:
    """Explicaciones de todos los objetivos no aceptados de una corrida.

    Args:
        results: contenido de `results.json`.
        detalle: contenido de `detalle.json` (contrato e intentos de cada función);
            sin él las explicaciones se arman solo con `results.json`.

    Returns:
        El contenido de `explicaciones.json` y los motivos de las descartadas.
    """
    funciones = {
        (f.get("modulo"), f.get("funcion")): f
        for f in (detalle or {}).get("funciones") or []
    }
    explicaciones: list[dict[str, Any]] = []
    descartadas: list[str] = []
    for objetivo in results.get("objetivos") or []:
        if tipo_de_hallazgo(objetivo) is None:
            continue
        funcion = funciones.get((objetivo.get("modulo"), objetivo.get("funcion")))
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
    return ResultadoExplicador(datos, descartadas)


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

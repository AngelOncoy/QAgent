"""Manifiesto y clasificación de la matriz de compatibilidad Java (#309).

Este módulo es puro: carga y valida `matriz.toml` y clasifica lo observado en una
ejecución. No clona, no usa Docker ni red; eso vive en `ejecutar.py`.

Una fila termina siempre en uno de los resultados de `RESULTADOS`. Solo
`aprobado` y `no_admitido_confirmado` cuentan como éxito: una omisión, una prueba
`skipped` o una fila sin ejecutar nunca se cuentan como aprobación.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

RAIZ_REPO = Path(__file__).resolve().parents[2]
RUTA_MATRIZ = Path(__file__).with_name("matriz.toml")

TIPOS_FILA = ("externo", "fixture")
NIVELES = ("pr", "ampliada")
SOPORTES = ("declarado", "no_admitido")
#: Configuraciones que la matriz debe cubrir (criterio 3 de #309).
CONFIGURACIONES = (
    "maven_simple",
    "padre_publico",
    "reactor",
    "perfiles",
    "tipos_aserciones",
    "inferencia",
    "spring",
    "defecto_sembrado",
    "proyecto_grande",
)
CONFIGURACIONES_OBLIGATORIAS = CONFIGURACIONES[:-1]
#: Estado observado de un objetivo; el esperado usa los mismos valores.
ESTADOS_OBJETIVO = (
    "aprobado",
    "bug_detectado",
    "hallazgo_inferido",
    "omitido",
    "construccion_bloqueada",
    "estancado",
    "rechazado_laundering",
    "sin_veredicto",
    "requiere_corrida_nueva",
    "ausente",
)
ESPERADOS_VALIDOS = (
    "aprobado",
    "bug_detectado",
    "hallazgo_inferido",
    "omitido",
    "construccion_bloqueada",
)
#: Resultado de una fila de la matriz.
APROBADO = "aprobado"
NO_ADMITIDO_CONFIRMADO = "no_admitido_confirmado"
FALLO_FUNCIONAL = "fallo_funcional"
FALLO_TECNICO = "fallo_tecnico"
NO_EJECUTADO = "no_ejecutado"
RESULTADOS = (
    APROBADO,
    NO_ADMITIDO_CONFIRMADO,
    FALLO_FUNCIONAL,
    FALLO_TECNICO,
    NO_EJECUTADO,
)
EXITOS = (APROBADO, NO_ADMITIDO_CONFIRMADO)
#: TOML no tiene null: este texto representa `null` en `valor_esperado`.
NULO = "__null__"
_SHA = re.compile(r"[0-9a-f]{40}")
_ID = re.compile(r"[a-z0-9][a-z0-9-]*")
_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+")
#: Texto que debe aparecer en el archivo de licencia para cada SPDX admitido.
MARCAS_LICENCIA = {
    "Apache-2.0": "Apache License",
    "MIT": "MIT License",
    "BSD-3-Clause": "Redistribution and use in source and binary forms",
}


class MatrizInvalida(ValueError):
    """El manifiesto no cumple las reglas de la matriz."""


@dataclass(frozen=True)
class Objetivo:
    """Objetivo seleccionado en una fila y lo que se espera de él."""

    modulo: str
    objetivo: str
    tipo: str
    esperado: str
    motivo: str | None = None
    imports: tuple[str, ...] = ()
    casos: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Fila:
    """Una combinación proyecto/commit/configuración de la matriz."""

    id: str
    tipo: str
    nivel: str
    soporte: str
    configuraciones: tuple[str, ...]
    descripcion: str
    url: str | None = None
    licencia: str | None = None
    archivo_licencia: str | None = None
    commit: str | None = None
    subdirectorio: str = ""
    perfil: str = "std"
    inferir: bool = False
    base: str | None = None
    defecto_sembrado: bool = False
    motivo_no_admitido: str | None = None
    parches: tuple[dict[str, str], ...] = ()
    objetivos: tuple[Objetivo, ...] = ()
    ruta: str | None = None
    prueba: str | None = None
    datos: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


def _nulos(valor: Any) -> Any:
    """Convierte el marcador `__null__` en None, también dentro de listas y tablas."""
    if valor == NULO:
        return None
    if isinstance(valor, list):
        return [_nulos(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _nulos(v) for k, v in valor.items()}
    return valor


def _objetivo(datos: dict[str, Any]) -> Objetivo:
    casos = []
    for caso in datos.get("caso", []):
        caso = _nulos(dict(caso))
        caso.setdefault("evidencia", None)
        if caso["evidencia"] is None:
            caso.pop("evidencia")
        casos.append(caso)
    return Objetivo(
        modulo=datos["modulo"],
        objetivo=datos["objetivo"],
        tipo=datos.get("tipo", "funcion"),
        esperado=datos["esperado"],
        motivo=datos.get("motivo"),
        imports=tuple(datos.get("imports", ())),
        casos=tuple(casos),
    )


def _heredar(datos: dict[str, Any], filas: dict[str, dict[str, Any]]) -> dict:
    """Una variante con `base` hereda origen y casos del proyecto que repite."""
    base = datos.get("base")
    if not base:
        return datos
    if base not in filas:
        raise MatrizInvalida(f"{datos['id']}: la base {base!r} no existe")
    origen = filas[base]
    if origen.get("base"):
        raise MatrizInvalida(f"{datos['id']}: la base no puede ser otra variante")
    heredado = {
        k: origen[k]
        for k in (
            "url",
            "licencia",
            "archivo_licencia",
            "commit",
            "subdirectorio",
            "perfil",
            "inferir",
        )
        if k in origen
    }
    casos = {(o["modulo"], o["objetivo"]): o for o in origen.get("objetivo", [])}
    objetivos = []
    for objetivo in datos.get("objetivo", []):
        clave = (objetivo["modulo"], objetivo["objetivo"])
        if clave not in casos:
            raise MatrizInvalida(
                f"{datos['id']}: {objetivo['objetivo']} no está en la base {base}"
            )
        completo = {**casos[clave], **objetivo}
        objetivos.append(completo)
    return {**heredado, **datos, "objetivo": objetivos}


def cargar(ruta: Path = RUTA_MATRIZ) -> list[Fila]:
    """Lee y valida el manifiesto; lanza MatrizInvalida con todos los problemas."""
    datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    if datos.get("version") != 1:
        raise MatrizInvalida("versión de la matriz desconocida")
    crudas = datos.get("fila", [])
    por_id: dict[str, dict[str, Any]] = {}
    for cruda in crudas:
        if cruda.get("id") in por_id:
            raise MatrizInvalida(f"id repetido: {cruda.get('id')}")
        por_id[cruda.get("id")] = cruda
    filas = []
    for cruda in crudas:
        completa = _heredar(cruda, por_id)
        filas.append(
            Fila(
                id=completa["id"],
                tipo=completa["tipo"],
                nivel=completa["nivel"],
                soporte=completa["soporte"],
                configuraciones=tuple(completa.get("configuraciones", ())),
                descripcion=completa.get("descripcion", ""),
                url=completa.get("url"),
                licencia=completa.get("licencia"),
                archivo_licencia=completa.get("archivo_licencia"),
                commit=completa.get("commit"),
                subdirectorio=completa.get("subdirectorio", ""),
                perfil=completa.get("perfil", "std"),
                inferir=bool(completa.get("inferir", False)),
                base=completa.get("base"),
                defecto_sembrado=bool(completa.get("defecto_sembrado", False)),
                motivo_no_admitido=completa.get("motivo_no_admitido"),
                parches=tuple(completa.get("parche", ())),
                objetivos=tuple(_objetivo(o) for o in completa.get("objetivo", [])),
                ruta=completa.get("ruta"),
                prueba=completa.get("prueba"),
                datos=completa,
            )
        )
    problemas = [p for fila in filas for p in problemas_de_fila(fila)]
    problemas += problemas_de_cobertura(filas)
    if problemas:
        raise MatrizInvalida("\n".join(problemas))
    return filas


def problemas_de_fila(fila: Fila) -> list[str]:
    """Reglas de una fila: trazabilidad, commit fijo y esperados cerrados."""
    p = []
    nombre = fila.id or "<sin id>"
    if not _ID.fullmatch(fila.id or ""):
        p.append(f"{nombre}: id inválido")
    if fila.tipo not in TIPOS_FILA:
        p.append(f"{nombre}: tipo {fila.tipo!r} no admitido")
    if fila.nivel not in NIVELES:
        p.append(f"{nombre}: nivel {fila.nivel!r} no admitido")
    if fila.soporte not in SOPORTES:
        p.append(f"{nombre}: soporte {fila.soporte!r} no admitido")
    if not fila.descripcion:
        p.append(f"{nombre}: falta la descripción")
    desconocidas = set(fila.configuraciones) - set(CONFIGURACIONES)
    if desconocidas or not fila.configuraciones:
        p.append(f"{nombre}: configuraciones inválidas {sorted(desconocidas)}")
    if fila.tipo == "externo" and fila.defecto_sembrado != (
        "defecto_sembrado" in fila.configuraciones
    ):
        p.append(f"{nombre}: defecto_sembrado y su configuración no coinciden")
    if fila.soporte == "no_admitido" and not fila.motivo_no_admitido:
        p.append(f"{nombre}: un escenario no admitido debe explicar su motivo")
    if fila.tipo == "externo":
        if not _URL.fullmatch(fila.url or ""):
            p.append(f"{nombre}: la URL debe ser un repositorio público de GitHub")
        if fila.licencia not in MARCAS_LICENCIA:
            p.append(f"{nombre}: licencia {fila.licencia!r} sin marca conocida")
        if not fila.archivo_licencia:
            p.append(f"{nombre}: falta el archivo de licencia")
        if not _SHA.fullmatch(fila.commit or ""):
            p.append(f"{nombre}: el commit debe ser un SHA completo de 40 caracteres")
        if not fila.objetivos:
            p.append(f"{nombre}: un externo necesita objetivos esperados")
        if fila.perfil not in ("humo", "std", "deep"):
            p.append(f"{nombre}: perfil {fila.perfil!r} no admitido")
        if fila.defecto_sembrado and not fila.parches:
            p.append(f"{nombre}: un defecto sembrado necesita su parche")
        if fila.parches and not fila.defecto_sembrado:
            p.append(f"{nombre}: un parche solo se admite como defecto sembrado")
        for parche in fila.parches:
            if not all(parche.get(k) for k in ("archivo", "buscar", "reemplazar")):
                p.append(f"{nombre}: parche incompleto")
            elif parche["buscar"] == parche["reemplazar"]:
                p.append(f"{nombre}: el parche no cambia nada")
    else:
        if not fila.prueba or not (RAIZ_REPO / fila.prueba).is_file():
            p.append(f"{nombre}: la prueba del fixture no existe: {fila.prueba}")
        if not fila.ruta or not (RAIZ_REPO / fila.ruta).exists():
            p.append(f"{nombre}: la ruta del fixture no existe: {fila.ruta}")
        if fila.objetivos or fila.parches:
            p.append(f"{nombre}: un fixture se comprueba con su prueba, sin objetivos")
    esperados = {o.esperado for o in fila.objetivos}
    for objetivo in fila.objetivos:
        if objetivo.esperado not in ESPERADOS_VALIDOS:
            p.append(f"{nombre}: esperado {objetivo.esperado!r} no admitido")
        if objetivo.tipo not in ("funcion", "endpoint"):
            p.append(f"{nombre}: tipo de objetivo {objetivo.tipo!r} no admitido")
        if objetivo.esperado == "omitido" and not objetivo.motivo:
            p.append(f"{nombre}: {objetivo.objetivo} omitido necesita su motivo")
        veredicto = objetivo.esperado in (
            "aprobado",
            "bug_detectado",
            "hallazgo_inferido",
        )
        if veredicto and not objetivo.casos:
            p.append(f"{nombre}: {objetivo.objetivo} necesita casos grabados")
        for caso in objetivo.casos:
            p += _problemas_caso(nombre, objetivo, caso)
    if (
        fila.soporte == "declarado"
        and esperados
        & {
            "omitido",
            "construccion_bloqueada",
        }
        and esperados <= {"omitido", "construccion_bloqueada"}
    ):
        p.append(
            f"{nombre}: una fila declarada no puede esperar solo omisiones; "
            "es un escenario no admitido"
        )
    if fila.soporte == "no_admitido" and esperados & {"aprobado", "bug_detectado"}:
        p.append(f"{nombre}: un escenario no admitido no puede esperar veredictos")
    if fila.defecto_sembrado and not esperados & {"bug_detectado", "hallazgo_inferido"}:
        p.append(f"{nombre}: el defecto sembrado debe esperar su detección")
    return p


def _problemas_caso(nombre: str, objetivo: Objetivo, caso: dict[str, Any]) -> list:
    p = []
    for clave in ("id", "entrada", "origen", "categoria", "junit"):
        if clave not in caso:
            p.append(f"{nombre}: {objetivo.objetivo} caso sin {clave}")
    if ("valor_esperado" in caso) == ("excepcion" in caso):
        p.append(f"{nombre}: {objetivo.objetivo} necesita valor_esperado o excepcion")
    origen = caso.get("origen")
    if origen not in ("docstring", "tipo", "inferido", "status_code"):
        p.append(f"{nombre}: {objetivo.objetivo} origen {origen!r} no admitido")
    if origen == "inferido" and not caso.get("evidencia"):
        p.append(f"{nombre}: un caso inferido debe citar su evidencia (ADR-018)")
    return p


def problemas_de_cobertura(filas: list[Fila]) -> list[str]:
    """La matriz cubre cada configuración y el PR detecta un defecto sembrado."""
    p = []
    cubiertas = {c for f in filas for c in f.configuraciones}
    for configuracion in CONFIGURACIONES_OBLIGATORIAS:
        if configuracion not in cubiertas:
            p.append(f"ninguna fila cubre {configuracion}")
    externas = {c for f in filas if f.tipo == "externo" for c in f.configuraciones}
    for configuracion in ("maven_simple", "padre_publico", "reactor", "spring"):
        if configuracion not in externas:
            p.append(f"ningún proyecto externo cubre {configuracion}")
    pr = [f for f in filas if f.nivel == "pr"]
    if not any("defecto_sembrado" in f.configuraciones for f in pr):
        p.append("el nivel pr necesita al menos un defecto sembrado")
    if not any(f.tipo == "externo" for f in pr):
        p.append("el nivel pr necesita al menos un proyecto externo")
    return p


def seleccionar(filas: list[Fila], nivel: str, ids: list[str] | None = None) -> list:
    """Filas del nivel pedido (`ampliada` incluye `pr`), o las de `ids` si se dan."""
    if ids:
        desconocidos = set(ids) - {f.id for f in filas}
        if desconocidos:
            raise MatrizInvalida(f"filas desconocidas: {sorted(desconocidos)}")
        return [f for f in filas if f.id in ids]
    if nivel not in NIVELES:
        raise MatrizInvalida(f"nivel desconocido: {nivel}")
    return [f for f in filas if nivel == "ampliada" or f.nivel == "pr"]


def comparar(
    fila: Fila, observados: dict[str, dict[str, Any]]
) -> tuple[str, list[str]]:
    """Compara lo observado con lo esperado y devuelve el resultado de la fila.

    `observados` va de objetivo a {estado, motivo}. La comparación es estricta: un
    objetivo omitido, ausente o sin veredicto cuando se esperaba otro estado es un
    fallo funcional, nunca una aprobación.
    """
    diferencias = []
    for objetivo in fila.objetivos:
        visto = observados.get(objetivo.objetivo, {"estado": "ausente"})
        estado = visto.get("estado")
        if estado != objetivo.esperado:
            diferencias.append(
                f"{objetivo.objetivo}: se esperaba {objetivo.esperado} y se observó "
                f"{estado}" + (f" ({visto['motivo']})" if visto.get("motivo") else "")
            )
        elif objetivo.motivo and objetivo.motivo not in (visto.get("motivo") or ""):
            diferencias.append(
                f"{objetivo.objetivo}: el motivo observado no contiene "
                f"{objetivo.motivo!r}: {visto.get('motivo')!r}"
            )
    if diferencias:
        return FALLO_FUNCIONAL, diferencias
    return (NO_ADMITIDO_CONFIRMADO if fila.soporte == "no_admitido" else APROBADO), []


def resultado_de_pytest(totales: dict[str, int]) -> tuple[str, list[str]]:
    """Resultado de una fila fixture según el JUnit de su prueba `docker`.

    Un `skipped` no acredita ejecución real: la fila queda `no_ejecutado`.
    """
    if totales.get("errores"):
        return FALLO_TECNICO, [f"{totales['errores']} error(es) al ejecutar la prueba"]
    if totales.get("fallos"):
        return FALLO_FUNCIONAL, [f"{totales['fallos']} prueba(s) fallaron"]
    if totales.get("omitidas"):
        return NO_EJECUTADO, [
            f"{totales['omitidas']} prueba(s) omitidas: no acreditan ejecución"
        ]
    if not totales.get("total"):
        return NO_EJECUTADO, ["la prueba no recolectó casos"]
    return APROBADO, []


def codigo_salida(resultados: list[dict[str, Any]]) -> int:
    """0 solo si todas las filas ejecutadas terminaron en un éxito declarado."""
    if not resultados:
        return 1
    return 0 if all(r["resultado"] in EXITOS for r in resultados) else 1

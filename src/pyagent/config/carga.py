"""Carga de la configuración fija del sistema (EN-06).

Lee dos fuentes:

- `config.toml` (se versiona): modelo y precio por agente, tope de gasto, reintentos y
  umbrales de calidad.
- `.env` (nunca se versiona): claves de API de cada proveedor.

La carga **no lanza excepciones por datos faltantes**: reúne todos los problemas en
`ResultadoCarga.avisos` para que la interfaz los muestre juntos y deshabilite
"Iniciar corrida". Los valores de las claves viven solo en `Claves`, que nunca se
imprime ni se serializa (RN-07).
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyagent.llm.cliente import es_modo_simulado
from pyagent.llm.precios import AGENTES, PrecioAgente

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

RAIZ = Path(__file__).resolve().parents[3]
RUTA_CONFIG = RAIZ / "config.toml"
RUTA_ENV = RAIZ / ".env"

# Variable que activa la IA simulada (EN-11): se puede definir en el sistema o en el .env.
VARIABLE_SIMULADA = "PYAGENT_FAKE_LLM"

#: Variable de `.env` que guarda la clave de cada proveedor de `config.toml`.
CLAVE_POR_PROVEEDOR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "xiaomi": "XIAOMI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

#: Umbrales de calidad que debe definir `[umbrales]` (metas de la carta, ADR-001).
UMBRALES = ("pass_rate_min", "cobertura_lineas_min", "iteraciones_promedio_max")

MIN_LARGO_SECRETO = 8  # menos que esto no se redacta: daría falsos positivos
_NOMBRE_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Presupuesto:
    """Topes de gasto en US$."""

    tope_por_corrida_usd: float
    tope_semestre_usd: float


@dataclass(frozen=True)
class Umbrales:
    """Metas de calidad de una corrida."""

    pass_rate_min: float
    cobertura_lineas_min: float
    iteraciones_promedio_max: float


@dataclass(frozen=True)
class Configuracion:
    """Contenido validado de `config.toml`."""

    presupuesto: Presupuesto
    max_intentos: int
    umbrales: Umbrales
    agentes: dict[str, PrecioAgente]

    def proveedores(self) -> dict[str, list[str]]:
        """Agentes que usa cada proveedor: `{"openai": ["reviewer"], ...}`."""
        usados: dict[str, list[str]] = {}
        for agente, precio in self.agentes.items():
            usados.setdefault(precio.proveedor, []).append(agente)
        return usados


class Claves:
    """Claves de API cargadas desde `.env`. Su contenido nunca se muestra.

    `repr()` y `str()` solo indican cuántas hay; así una clave no termina en un log,
    un traceback ni un informe por accidente. Usa `obtener()` solo en el punto donde
    se arma la petición al proveedor.
    """

    def __init__(self, valores: Mapping[str, str] | None = None) -> None:
        self._valores = {k: v for k, v in (valores or {}).items() if v}

    def obtener(self, nombre: str) -> str | None:
        """Valor de una variable, o None si no está definida."""
        return self._valores.get(nombre)

    def tiene(self, nombre: str) -> bool:
        """True si la variable existe y no está vacía."""
        return nombre in self._valores

    def nombres(self) -> list[str]:
        """Nombres (nunca valores) de las claves cargadas."""
        return sorted(self._valores)

    def redactar(self, texto: str) -> str:
        """Reemplaza cualquier clave presente en `texto` por `***`."""
        for valor in sorted(self._valores.values(), key=len, reverse=True):
            if len(valor) >= MIN_LARGO_SECRETO:
                texto = texto.replace(valor, "***")
        return texto

    def __repr__(self) -> str:
        return f"Claves(<{len(self._valores)} cargadas, ocultas>)"

    __str__ = __repr__

    def __reduce__(self) -> Any:  # evita volcar las claves con pickle/copy accidental
        raise TypeError("Claves no se puede serializar")


class FiltroSecretos(logging.Filter):
    """Filtro de `logging` que oculta las claves en cada mensaje (RN-07)."""

    def __init__(self, claves: Claves) -> None:
        super().__init__()
        self._claves = claves

    def filter(self, record: logging.LogRecord) -> bool:
        """Reescribe el mensaje ya formateado, sin claves."""
        record.msg = self._claves.redactar(record.getMessage())
        record.args = None
        return True


def instalar_filtro_logs(claves: Claves) -> FiltroSecretos:
    """Agrega `FiltroSecretos` a los handlers del logger raíz y lo devuelve."""
    filtro = FiltroSecretos(claves)
    raiz = logging.getLogger()
    for handler in raiz.handlers:
        handler.addFilter(filtro)
    return filtro


@dataclass
class ResultadoCarga:
    """Resultado de leer `config.toml` y `.env`.

    Atributos:
        config: configuración validada, o None si `config.toml` no se pudo usar.
        claves: claves de `.env` (puede estar vacía).
        avisos_config: problemas de `config.toml`, en español.
        avisos_claves: problemas de `.env` (archivo o claves que faltan), en español.
            Ningún aviso contiene valores secretos.
        simulado: True si se usa la IA simulada de EN-11 (0 tokens, sin claves).
    """

    config: Configuracion | None
    claves: Claves = field(default_factory=Claves)
    avisos_config: list[str] = field(default_factory=list)
    avisos_claves: list[str] = field(default_factory=list)
    simulado: bool = False

    @property
    def avisos(self) -> list[str]:
        """Todos los motivos por los que no se pueden iniciar corridas."""
        return [*self.avisos_config, *self.avisos_claves]

    @property
    def ok(self) -> bool:
        """True si hay configuración válida y ningún aviso."""
        return self.config is not None and not self.avisos


def leer_env(ruta: str | Path = RUTA_ENV) -> dict[str, str]:
    """Lee un archivo `.env` (`NOMBRE=valor`, `#` comentarios, comillas opcionales).

    Raises:
        FileNotFoundError: si el archivo no existe.
    """
    texto = Path(ruta).read_text(encoding="utf-8-sig")  # utf-8-sig: BOM de Windows
    valores: dict[str, str] = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        if linea.startswith("export "):
            linea = linea[len("export ") :].lstrip()
        nombre, separador, valor = linea.partition("=")
        nombre = nombre.strip()
        if not separador or not _NOMBRE_ENV.match(nombre):
            continue
        valores[nombre] = _limpiar_valor(valor)
    return valores


def _limpiar_valor(valor: str) -> str:
    valor = valor.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return re.split(r"\s+#", valor, maxsplit=1)[0].strip()


def simulado_desde_env(ruta_env: str | Path = RUTA_ENV) -> bool:
    """True si el `.env` activa la IA simulada con `PYAGENT_FAKE_LLM=1` (EN-11).

    Si el archivo no existe o no se puede leer, la IA simulada no está activa.
    """
    try:
        return leer_env(ruta_env).get(VARIABLE_SIMULADA, "").strip() == "1"
    except (OSError, UnicodeDecodeError):
        return False


def modo_simulado(ruta_env: str | Path = RUTA_ENV) -> bool:
    """¿Está activa la IA simulada? Lo definido en el sistema manda sobre el `.env`.

    `PYAGENT_FAKE_LLM` puede ponerse en el entorno del sistema o en el `.env`, que es
    donde el equipo ya guarda su configuración local. Si el sistema la define (aunque
    sea en `0`), se respeta esa decisión; si no, se mira el `.env`.
    """
    if VARIABLE_SIMULADA in os.environ:
        return es_modo_simulado()
    return simulado_desde_env(ruta_env)


def aplicar_simulacion_desde_env(ruta_env: str | Path = RUTA_ENV) -> bool:
    """Si el `.env` activa la IA simulada, lo deja activo para todo el programa.

    El cliente de IA (`pyagent.llm`) solo mira el entorno del sistema, así que al
    iniciar la aplicación se copia esa única bandera a `os.environ`. Nunca se copian
    claves. Lo definido en el sistema no se pisa.

    Returns:
        True si esta llamada activó la IA simulada.
    """
    if VARIABLE_SIMULADA in os.environ or not simulado_desde_env(ruta_env):
        return False
    os.environ[VARIABLE_SIMULADA] = "1"
    return True


def cargar_configuracion(
    ruta_config: str | Path = RUTA_CONFIG,
    ruta_env: str | Path = RUTA_ENV,
    simulado: bool | None = None,
) -> ResultadoCarga:
    """Lee `config.toml` y `.env`, y reúne todo lo que falta o es inválido.

    Args:
        ruta_config: ruta de `config.toml`.
        ruta_env: ruta de `.env`.
        simulado: True si la IA es simulada (EN-11) y no hacen falta claves; si es
            None se toma de `PYAGENT_FAKE_LLM`, en el sistema o en el `.env`.
    """
    simulado = modo_simulado(ruta_env) if simulado is None else simulado
    avisos_config: list[str] = []
    avisos_claves: list[str] = []
    config = _leer_config(Path(ruta_config), avisos_config)

    claves = Claves()
    if not simulado:
        claves = _leer_claves(Path(ruta_env), config, avisos_claves)
    return ResultadoCarga(config, claves, avisos_config, avisos_claves, simulado)


def _leer_claves(
    ruta_env: Path, config: Configuracion | None, avisos: list[str]
) -> Claves:
    if not ruta_env.exists():
        if not crear_env(ruta_env, config):
            avisos.append(
                f"No existe el archivo .env ({ruta_env}) y no se pudo crear. "
                "Créalo con las claves que te dé el equipo (una por línea, NOMBRE=valor)."
            )
            return Claves()
        avisos.append(
            f"Se creó el archivo .env en {ruta_env}. Ábrelo, completa las claves que "
            "te dé el equipo y pulsa Reintentar."
        )
    try:
        valores = leer_env(ruta_env)
    except (OSError, UnicodeDecodeError):
        avisos.append("No se pudo leer el archivo .env. Revisa que sea texto UTF-8.")
        return Claves()

    claves = Claves(valores)
    if config is not None:
        for proveedor, agentes in config.proveedores().items():
            variable = CLAVE_POR_PROVEEDOR.get(proveedor)
            if variable and not claves.tiene(variable):
                avisos.append(
                    f"Falta la clave {variable} en .env (la usa: {', '.join(agentes)}). "
                    "Pídela al equipo, agrégala y pulsa Reintentar."
                )
    return claves


def variables_requeridas(config: Configuracion | None) -> list[str]:
    """Variables de `.env` que pide `config.toml`; sin config válida, todas las conocidas."""
    if config is None:
        return list(dict.fromkeys(CLAVE_POR_PROVEEDOR.values()))
    return [
        CLAVE_POR_PROVEEDOR[p] for p in config.proveedores() if p in CLAVE_POR_PROVEEDOR
    ]


def crear_env(ruta: Path, config: Configuracion | None) -> bool:
    """Crea un `.env` con las variables requeridas **vacías** (nunca escribe valores).

    No sobrescribe un archivo existente. Devuelve True si lo creó.
    """
    lineas = [
        "# Claves de API de QAgent. Completa cada valor con la clave que te dé el equipo.",
        "# Este archivo NO se sube al repositorio (.gitignore) y no debe compartirse.",
        "# Para ver la simulación sin claves ni Docker, agrega la línea: PYAGENT_FAKE_LLM=1",
        "",
        *(f"{variable}=" for variable in variables_requeridas(config)),
        "",
    ]
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "x", encoding="utf-8") as archivo:  # "x": falla si ya existe
            archivo.write("\n".join(lineas))
    except OSError:
        return False
    return True


def _leer_config(ruta: Path, avisos: list[str]) -> Configuracion | None:
    try:
        with open(ruta, "rb") as archivo:
            datos = tomllib.load(archivo)
    except FileNotFoundError:
        avisos.append(f"No existe config.toml ({ruta}).")
        return None
    except tomllib.TOMLDecodeError as error:
        avisos.append(f"config.toml tiene un error de sintaxis: {error}")
        return None

    antes = len(avisos)
    presupuesto = _leer_presupuesto(datos.get("presupuesto", {}), avisos)
    max_intentos = _leer_reintentos(datos.get("reintentos", {}), avisos)
    umbrales = _leer_umbrales(datos.get("umbrales", {}), avisos)
    agentes = _leer_agentes(datos.get("agentes", {}), avisos)
    if len(avisos) > antes:
        return None
    return Configuracion(presupuesto, max_intentos, umbrales, agentes)  # type: ignore[arg-type]


def _numero(
    tabla: Mapping[str, Any], clave: str, seccion: str, avisos: list[str]
) -> float | None:
    """Número > 0 de `tabla[clave]`; agrega un aviso y devuelve None si falta o no sirve."""
    if clave not in tabla:
        avisos.append(f"Falta {clave} en [{seccion}] de config.toml.")
        return None
    valor = tabla[clave]
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor <= 0:
        avisos.append(f"{clave} en [{seccion}] debe ser un número mayor que 0.")
        return None
    return float(valor)


def _leer_presupuesto(
    tabla: Mapping[str, Any], avisos: list[str]
) -> Presupuesto | None:
    corrida = _numero(tabla, "tope_por_corrida_usd", "presupuesto", avisos)
    semestre = _numero(tabla, "tope_semestre_usd", "presupuesto", avisos)
    if corrida is None or semestre is None:
        return None
    return Presupuesto(corrida, semestre)


def _leer_reintentos(tabla: Mapping[str, Any], avisos: list[str]) -> int | None:
    intentos = _numero(tabla, "max_intentos", "reintentos", avisos)
    if intentos is None:
        return None
    if intentos != int(intentos):
        avisos.append("max_intentos en [reintentos] debe ser un número entero.")
        return None
    return int(intentos)


def _leer_umbrales(tabla: Mapping[str, Any], avisos: list[str]) -> Umbrales | None:
    valores = [_numero(tabla, nombre, "umbrales", avisos) for nombre in UMBRALES]
    if any(v is None for v in valores):
        return None
    return Umbrales(*valores)  # type: ignore[arg-type]


def _leer_agentes(
    seccion: Mapping[str, Any], avisos: list[str]
) -> dict[str, PrecioAgente]:
    agentes: dict[str, PrecioAgente] = {}
    for agente in AGENTES:
        tabla = seccion.get(agente)
        if tabla is None:
            avisos.append(f"Falta la sección [agentes.{agente}] en config.toml.")
            continue
        precio = _leer_agente(agente, tabla, avisos)
        if precio is not None:
            agentes[agente] = precio
    return agentes


def _leer_agente(
    agente: str, tabla: Mapping[str, Any], avisos: list[str]
) -> PrecioAgente | None:
    seccion = f"agentes.{agente}"
    antes = len(avisos)
    textos: dict[str, str] = {}
    for clave in ("proveedor", "modelo"):
        valor = tabla.get(clave)
        if not isinstance(valor, str) or not valor.strip():
            avisos.append(f"Falta {clave} en [{seccion}] de config.toml.")
        else:
            textos[clave] = valor.strip()
    entrada = _numero(tabla, "precio_entrada_usd_m", seccion, avisos)
    salida = _numero(tabla, "precio_salida_usd_m", seccion, avisos)

    proveedor = textos.get("proveedor")
    if proveedor and proveedor not in CLAVE_POR_PROVEEDOR:
        conocidos = ", ".join(sorted(CLAVE_POR_PROVEEDOR))
        avisos.append(
            f"Proveedor desconocido '{proveedor}' en [{seccion}] (válidos: {conocidos})."
        )
    if len(avisos) > antes:
        return None
    return PrecioAgente(
        agente=agente,
        proveedor=textos["proveedor"],
        modelo=textos["modelo"],
        entrada_usd_m=entrada,  # type: ignore[arg-type]
        salida_usd_m=salida,  # type: ignore[arg-type]
    )

"""Carga de la configuración fija del sistema (EN-06).

Lee dos fuentes:

- `config.toml` (se versiona): modelo y precio por agente, tope de gasto, reintentos,
  umbrales de calidad y límites del sandbox Docker (`[sandbox]`, opcional).
- `.env` (nunca se versiona): claves de API de cada proveedor.

`config.toml` viaja dentro del paquete; `.env` y `config.local.toml` son del usuario y
viven en `~/.qagent/` (TA-06), nunca en la carpeta del programa.

Los proveedores válidos salen del catálogo `llm/proveedores.toml` (HU-30). Cada agente
tiene su propia clave en `.env`, en `<VARIABLE_DEL_PROVEEDOR>_<AGENTE>` (ej.
`GEMINI_API_KEY_PLANNER`): el proveedor se puede repetir entre agentes, la clave no. Si
esa variable no existe se usa la del proveedor (`GEMINI_API_KEY`), como antes de HU-30. Un agente sin sección `[agentes.<agente>]` queda «Sin
configurar»: no invalida el resto, pero impide iniciar corridas con la IA real.

La carga **no lanza excepciones por datos faltantes**: reúne todos los problemas en
`ResultadoCarga.avisos` para que la interfaz los muestre juntos y deshabilite
"Iniciar corrida". Los valores de las claves viven solo en `Claves`, que nunca se
imprime ni se serializa (RN-07).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qagent.llm.cliente import VARIABLE_SIMULADA, es_modo_simulado, valor_simulado
from qagent.llm.precios import AGENTES, PrecioAgente, texto_opcional
from qagent.llm.precios import RUTA_CONFIG as RUTA_CONFIG_EQUIPO
from qagent.llm.proveedores import variable_por_proveedor
from qagent.sandbox.modelos import LIMITES_POR_DEFECTO, LimitesSandbox
from qagent.usuario import carpeta_usuario

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

#: Raíz del código fuente. Solo sirve al desarrollar desde el repositorio: de aquí se
#: migran `.env` y `config.local.toml` de antes de TA-06 y aquí busca claves la auditoría.
RAIZ = Path(__file__).resolve().parents[3]
# `config.toml` viaja dentro del paquete (qagent/config/); una sola definición en precios.
RUTA_CONFIG = RUTA_CONFIG_EQUIPO
#: Configuración personal (no se versiona): reemplaza secciones de `config.toml` en esta
#: computadora, p. ej. los modelos que el usuario eligió en la pantalla Configuración.
#: La usan la aplicación y `python -m qagent.llm.validar`; las pruebas la dejan fuera.
RUTA_CONFIG_LOCAL = carpeta_usuario() / "config.local.toml"
RUTA_ENV = carpeta_usuario() / ".env"
#: Archivos del usuario que antes de TA-06 vivían en la raíz del repositorio.
ARCHIVOS_DEL_USUARIO = (".env", "config.local.toml")


def migrar_desde_repositorio(
    raiz: str | Path = RAIZ, destino: str | Path | None = None
) -> list[str]:
    """Mueve `.env` y `config.local.toml` de la raíz del repositorio a `~/.qagent/`.

    Antes de TA-06 vivían junto al código. Solo mueve un archivo si existe en el
    repositorio y no en el destino: nunca sobrescribe. Con el programa instalado (sin
    `pyproject.toml` en `raiz`) no hace nada. Nunca lanza excepciones.

    Returns:
        Los nombres de los archivos que se movieron.
    """
    raiz = Path(raiz)
    destino = Path(destino) if destino is not None else carpeta_usuario()
    if not (raiz / "pyproject.toml").is_file():
        return []
    movidos: list[str] = []
    for nombre in ARCHIVOS_DEL_USUARIO:
        origen, final = raiz / nombre, destino / nombre
        if not origen.is_file() or final.exists():
            continue
        try:
            destino.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origen), str(final))
        except OSError:
            continue
        movidos.append(nombre)
    return movidos


#: Variable de `.env` que guarda la clave de cada proveedor (catálogo de HU-30).
CLAVE_POR_PROVEEDOR = variable_por_proveedor()

#: Lee una variable de `.env` (`Claves.obtener` o `dict.get`).
LectorClaves = Callable[[str], "str | None"]

#: Nombre visible de cada agente.
NOMBRE_AGENTE = {"planner": "Planner", "generator": "Generator", "reviewer": "Reviewer"}

#: Proveedor y modelo que ocupan el lugar de un agente sin configurar con la IA simulada.
PROVEEDOR_SIMULADO = "simulado"
MODELO_SIMULADO = "ia-simulada"

#: Umbrales de calidad que debe definir `[umbrales]` (metas de la carta, ADR-001).
UMBRALES = ("pass_rate_min", "cobertura_lineas_min", "iteraciones_promedio_max")

#: Tiempo máximo de mutmut por función crítica si `[mutacion]` no lo define (EN-09).
TIEMPO_MUTACION_POR_DEFECTO_S = 120

#: Memoria en formato Docker: un entero y una unidad (b, k, m o g), p. ej. "512m" o "3g".
#: Secciones que solo define el equipo en `config.toml`: `config.local.toml` no las
#: cambia. Los límites del sandbox no son un ajuste del usuario final (EN-03).
SECCIONES_SOLO_EQUIPO = frozenset({"sandbox"})

_MEMORIA_DOCKER = re.compile(r"^[1-9][0-9]*[bkmg]$", re.IGNORECASE)

MIN_LARGO_SECRETO = 8  # menos que esto no se redacta: daría falsos positivos
_NOMBRE_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Presupuesto:
    """Topes de gasto en US$ y presupuesto de tokens."""

    tope_por_corrida_usd: float
    tope_semestre_usd: float
    max_tokens_por_corrida: int | None = None


@dataclass(frozen=True)
class Umbrales:
    """Metas de calidad de una corrida."""

    pass_rate_min: float
    cobertura_lineas_min: float
    iteraciones_promedio_max: float


@dataclass(frozen=True)
class Mutacion:
    """Mutation testing de las funciones críticas (EN-09)."""

    tiempo_maximo_por_funcion_s: int = TIEMPO_MUTACION_POR_DEFECTO_S


@dataclass(frozen=True)
class Configuracion:
    """Contenido validado de `config.toml`."""

    presupuesto: Presupuesto
    max_intentos: int
    umbrales: Umbrales
    agentes: dict[str, PrecioAgente]
    mutacion: Mutacion = Mutacion()
    sandbox: LimitesSandbox = LIMITES_POR_DEFECTO

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
        sin_configurar: agentes sin sección `[agentes.*]` (HU-30). Con la IA real
            bloquean las corridas; con la simulada se reemplazan por la IA simulada.
    """

    config: Configuracion | None
    claves: Claves = field(default_factory=Claves)
    avisos_config: list[str] = field(default_factory=list)
    avisos_claves: list[str] = field(default_factory=list)
    simulado: bool = False
    sin_configurar: list[str] = field(default_factory=list)

    @property
    def avisos(self) -> list[str]:
        """Todos los motivos por los que no se pueden iniciar corridas."""
        return [*self.avisos_config, *self.avisos_claves]

    @property
    def ok(self) -> bool:
        """True si hay configuración válida y ningún aviso."""
        return self.config is not None and not self.avisos


def leer_env(ruta: str | Path | None = None) -> dict[str, str]:
    """Lee un archivo `.env` (`NOMBRE=valor`, `#` comentarios, comillas opcionales).

    Raises:
        FileNotFoundError: si el archivo no existe.
    """
    ruta_res = RUTA_ENV if ruta is None else Path(ruta)
    texto = ruta_res.read_text(encoding="utf-8-sig")  # utf-8-sig: BOM de Windows
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


def simulado_desde_env(ruta_env: str | Path | None = None) -> bool:
    """True si el `.env` activa la IA simulada con `QAGENT_FAKE_LLM=1` (EN-11).

    Si el archivo no existe o no se puede leer, la IA simulada no está activa.
    """
    ruta_res = RUTA_ENV if ruta_env is None else Path(ruta_env)
    try:
        return (valor_simulado(leer_env(ruta_res)) or "").strip() == "1"
    except (OSError, UnicodeDecodeError):
        return False


def modo_simulado(ruta_env: str | Path | None = None) -> bool:
    """¿Está activa la IA simulada? Lo definido en el sistema manda sobre el `.env`.

    `QAGENT_FAKE_LLM` puede ponerse en el entorno del sistema o en el `.env`, que es
    donde el equipo ya guarda su configuración local. Si el sistema la define (aunque
    sea en `0`), se respeta esa decisión; si no, se mira el `.env`.
    """
    if valor_simulado(os.environ) is not None:
        return es_modo_simulado()
    return simulado_desde_env(ruta_env)


def aplicar_simulacion_desde_env(ruta_env: str | Path | None = None) -> bool:
    """Si el `.env` activa la IA simulada, lo deja activo para todo el programa.

    El cliente de IA (`qagent.llm`) solo mira el entorno del sistema, así que al
    iniciar la aplicación se copia esa única bandera a `os.environ`. Nunca se copian
    claves. Lo definido en el sistema no se pisa.

    Returns:
        True si esta llamada activó la IA simulada.
    """
    if valor_simulado(os.environ) is not None or not simulado_desde_env(ruta_env):
        return False
    os.environ[VARIABLE_SIMULADA] = "1"
    return True


def cargar_configuracion(
    ruta_config: str | Path | None = None,
    ruta_env: str | Path | None = None,
    simulado: bool | None = None,
    ruta_local: str | Path | None = None,
) -> ResultadoCarga:
    """Lee `config.toml` y `.env`, y reúne todo lo que falta o es inválido.

    Args:
        ruta_config: ruta de `config.toml`.
        ruta_env: ruta de `.env`.
        simulado: True si la IA es simulada (EN-11) y no hacen falta claves; si es
            None se toma de `QAGENT_FAKE_LLM`, en el sistema o en el `.env`.
        ruta_local: `config.local.toml` opcional; si existe, sus agentes reemplazan
            a los de `config.toml` y sus demás valores se superponen clave a clave.
    """
    ruta_config_res = RUTA_CONFIG if ruta_config is None else Path(ruta_config)
    ruta_env_res = RUTA_ENV if ruta_env is None else Path(ruta_env)
    simulado = modo_simulado(ruta_env_res) if simulado is None else simulado
    avisos_config: list[str] = []
    avisos_claves: list[str] = []
    sin_configurar: list[str] = []
    config = _leer_config(
        ruta_config_res,
        avisos_config,
        Path(ruta_local) if ruta_local else None,
        sin_configurar,
    )
    if config is not None:
        for agente in sin_configurar:
            if simulado:
                config.agentes[agente] = PrecioAgente(
                    agente, PROVEEDOR_SIMULADO, MODELO_SIMULADO, 0.0, 0.0
                )
            else:
                avisos_config.append(mensaje_sin_configurar(agente))

    claves = Claves()
    if not simulado:
        claves = _leer_claves(ruta_env_res, config, avisos_claves)
    return ResultadoCarga(
        config, claves, avisos_config, avisos_claves, simulado, sin_configurar
    )


def mensaje_sin_configurar(agente: str) -> str:
    """Aviso de un agente sin proveedor ni modelo (HU-30, criterio 10)."""
    return (
        f"Falta configurar el {NOMBRE_AGENTE.get(agente, agente)} "
        f"([agentes.{agente}] en config.toml): ve a Configuración → «Modelo de cada "
        "agente» y pulsa «Agregar API»."
    )


def variable_de_agente(agente: str, proveedor: str) -> str | None:
    """Variable propia del agente: `<VARIABLE_DEL_PROVEEDOR>_<AGENTE>` (HU-30).

    >>> variable_de_agente("generator", "gemini")
    'GEMINI_API_KEY_GENERATOR'
    """
    base = CLAVE_POR_PROVEEDOR.get(proveedor)
    return f"{base}_{agente.upper()}" if base else None


def variable_en_uso(agente: str, proveedor: str, obtener: LectorClaves) -> str | None:
    """Variable de `.env` de donde sale la clave del agente, o None si no hay ninguna.

    Primero la propia del agente; si no existe, la compartida del proveedor
    (configuraciones anteriores a HU-30 o editadas a mano).
    """
    for variable in (
        variable_de_agente(agente, proveedor),
        CLAVE_POR_PROVEEDOR.get(proveedor),
    ):
        if variable and obtener(variable):
            return variable
    return None


def _leer_claves(
    ruta_env: Path, config: Configuracion | None, avisos: list[str]
) -> Claves:
    try:
        existe = ruta_env.exists()
    except OSError:
        existe = False

    if not existe:
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
        for agente, precio in config.agentes.items():
            propia = variable_de_agente(agente, precio.proveedor)
            if (
                propia
                and variable_en_uso(agente, precio.proveedor, claves.obtener) is None
            ):
                avisos.append(
                    f"Falta la clave {propia} en .env (la usa: {agente}). Agrégala en "
                    "Configuración → «Agregar API» y pulsa Reintentar."
                )
    return claves


def variables_requeridas(config: Configuracion | None) -> list[str]:
    """Variables de `.env` que pide `config.toml` (una por agente); sin config válida,
    la de cada proveedor conocido."""
    if config is None:
        return list(dict.fromkeys(CLAVE_POR_PROVEEDOR.values()))
    variables = (variable_de_agente(a, p.proveedor) for a, p in config.agentes.items())
    return [v for v in variables if v]


def crear_env(ruta: Path, config: Configuracion | None) -> bool:
    """Crea un `.env` con las variables requeridas **vacías** (nunca escribe valores).

    No sobrescribe un archivo existente. Devuelve True si lo creó.
    """
    lineas = [
        "# Claves de API de QAgent. Completa cada valor con la clave que te dé el equipo.",
        "# Este archivo NO se sube al repositorio (.gitignore) y no debe compartirse.",
        "# Para ver la simulación sin claves ni Docker, agrega la línea: QAGENT_FAKE_LLM=1",
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


def _leer_config(
    ruta: Path,
    avisos: list[str],
    ruta_local: Path | None = None,
    sin_configurar: list[str] | None = None,
) -> Configuracion | None:
    try:
        with open(ruta, "rb") as archivo:
            datos = tomllib.load(archivo)
    except FileNotFoundError:
        avisos.append(f"No existe config.toml ({ruta}).")
        return None
    except tomllib.TOMLDecodeError as error:
        avisos.append(f"config.toml tiene un error de sintaxis: {error}")
        return None
    if ruta_local is not None and ruta_local.is_file():
        try:
            with open(ruta_local, "rb") as archivo:
                datos = superponer_config(datos, tomllib.load(archivo))
        except tomllib.TOMLDecodeError as error:
            avisos.append(f"{ruta_local.name} tiene un error de sintaxis: {error}")
            return None

    antes = len(avisos)
    presupuesto = _leer_presupuesto(datos.get("presupuesto", {}), avisos)
    max_intentos = _leer_reintentos(datos.get("reintentos", {}), avisos)
    umbrales = _leer_umbrales(datos.get("umbrales", {}), avisos)
    mutacion = _leer_mutacion(datos.get("mutacion", {}), avisos)
    sandbox = _leer_sandbox(datos.get("sandbox", {}), avisos)
    agentes = _leer_agentes(
        datos.get("agentes", {}),
        avisos,
        sin_configurar if sin_configurar is not None else [],
    )
    if len(avisos) > antes:
        return None
    return Configuracion(
        presupuesto, max_intentos, umbrales, agentes, mutacion, sandbox
    )  # type: ignore[arg-type]


def superponer_config(
    base: Mapping[str, Any], local: Mapping[str, Any]
) -> dict[str, Any]:
    """`config.toml` con `config.local.toml` encima.

    Cada agente de `[agentes.*]` se reemplaza entero (así no se mezclan el proveedor
    local con el precio o el `esfuerzo` del equipo); las demás secciones se
    superponen clave a clave, salvo `SECCIONES_SOLO_EQUIPO`, que se ignoran.
    """
    datos = {
        seccion: dict(valor) if isinstance(valor, Mapping) else valor
        for seccion, valor in base.items()
    }
    for seccion, valor in local.items():
        if seccion in SECCIONES_SOLO_EQUIPO:
            continue
        if seccion == "agentes" and isinstance(valor, Mapping):
            agentes = dict(datos.get("agentes") or {})
            agentes.update({agente: dict(tabla) for agente, tabla in valor.items()})
            datos["agentes"] = agentes
        elif isinstance(valor, Mapping) and isinstance(datos.get(seccion), dict):
            datos[seccion].update(valor)
        else:
            datos[seccion] = valor
    return datos


def _numero(
    tabla: Mapping[str, Any],
    clave: str,
    seccion: str,
    avisos: list[str],
    *,
    permitir_cero: bool = False,
) -> float | None:
    """Número > 0 de `tabla[clave]` (≥ 0 con `permitir_cero`); None y un aviso si no sirve.

    Los precios aceptan 0 para los modelos de capa gratuita (Gemini, Groq, OpenRouter
    `:free`); topes, reintentos y umbrales siguen exigiendo un valor mayor que 0.
    """
    if clave not in tabla:
        avisos.append(f"Falta {clave} en [{seccion}] de config.toml.")
        return None
    valor = tabla[clave]
    minimo_ok = (
        isinstance(valor, (int, float))
        and not isinstance(valor, bool)
        and (valor >= 0 if permitir_cero else valor > 0)
    )
    if not minimo_ok:
        condicion = "mayor o igual que 0" if permitir_cero else "mayor que 0"
        avisos.append(f"{clave} en [{seccion}] debe ser un número {condicion}.")
        return None
    return float(valor)


def _leer_presupuesto(
    tabla: Mapping[str, Any], avisos: list[str]
) -> Presupuesto | None:
    corrida = _numero(tabla, "tope_por_corrida_usd", "presupuesto", avisos)
    semestre = _numero(tabla, "tope_semestre_usd", "presupuesto", avisos)
    if corrida is None or semestre is None:
        return None
    max_tokens = None
    if "max_tokens_por_corrida" in tabla:
        val = tabla["max_tokens_por_corrida"]
        if val is not None:
            if (
                isinstance(val, bool)
                or not isinstance(val, (int, float))
                or val < 0
                or int(val) != val
            ):
                avisos.append(
                    "max_tokens_por_corrida en [presupuesto] debe ser un número entero mayor o igual que 0."
                )
                return None
            max_tokens = int(val) if int(val) > 0 else None
    return Presupuesto(corrida, semestre, max_tokens)


def _leer_reintentos(tabla: Mapping[str, Any], avisos: list[str]) -> int | None:
    intentos = _numero(tabla, "max_intentos", "reintentos", avisos)
    if intentos is None:
        return None
    if intentos != int(intentos):
        avisos.append("max_intentos en [reintentos] debe ser un número entero.")
        return None
    return int(intentos)


def _leer_mutacion(tabla: Mapping[str, Any], avisos: list[str]) -> Mutacion | None:
    """`[mutacion]` es opcional: sin `tiempo_maximo_por_funcion_s` usa el valor por defecto."""
    if not isinstance(tabla, Mapping):
        avisos.append("[mutacion] de config.toml debe ser una sección.")
        return None
    if "tiempo_maximo_por_funcion_s" not in tabla:
        return Mutacion()
    tiempo = _numero(tabla, "tiempo_maximo_por_funcion_s", "mutacion", avisos)
    if tiempo is None:
        return None
    if tiempo != int(tiempo):
        avisos.append(
            "tiempo_maximo_por_funcion_s en [mutacion] debe ser un número entero."
        )
        return None
    return Mutacion(int(tiempo))


def _leer_sandbox(tabla: Mapping[str, Any], avisos: list[str]) -> LimitesSandbox | None:
    """`[sandbox]` es opcional: cada valor que falte toma el de `LIMITES_POR_DEFECTO`.

    `cpus` es un número > 0, `memoria` un texto en formato Docker ("512m", "3g") y
    `timeout_s` un entero > 0. Un valor inválido deja un aviso, nunca una excepción.
    """
    if not isinstance(tabla, Mapping):
        avisos.append("[sandbox] de config.toml debe ser una sección.")
        return None
    antes = len(avisos)
    cpus = LIMITES_POR_DEFECTO.cpus
    if "cpus" in tabla:
        cpus = _numero(tabla, "cpus", "sandbox", avisos)  # type: ignore[assignment]
    memoria = LIMITES_POR_DEFECTO.memoria
    if "memoria" in tabla:
        valor = tabla["memoria"]
        if isinstance(valor, str) and _MEMORIA_DOCKER.match(valor.strip()):
            memoria = valor.strip().lower()
        else:
            avisos.append(
                "memoria en [sandbox] debe tener el formato de Docker: un entero y "
                'una unidad (b, k, m o g), p. ej. "512m" o "3g".'
            )
    timeout = LIMITES_POR_DEFECTO.timeout_s
    if "timeout_s" in tabla:
        leido = _numero(tabla, "timeout_s", "sandbox", avisos)
        if leido is not None and leido != int(leido):
            avisos.append("timeout_s en [sandbox] debe ser un número entero.")
        elif leido is not None:
            timeout = int(leido)
    if len(avisos) > antes:
        return None
    return LimitesSandbox(cpus=cpus, memoria=memoria, timeout_s=timeout)


def _leer_umbrales(tabla: Mapping[str, Any], avisos: list[str]) -> Umbrales | None:
    valores = [_numero(tabla, nombre, "umbrales", avisos) for nombre in UMBRALES]
    if any(v is None for v in valores):
        return None
    return Umbrales(*valores)  # type: ignore[arg-type]


def _leer_agentes(
    seccion: Mapping[str, Any], avisos: list[str], sin_configurar: list[str]
) -> dict[str, PrecioAgente]:
    agentes: dict[str, PrecioAgente] = {}
    for agente in AGENTES:
        tabla = seccion.get(agente)
        # `configurado = false` en config.local.toml tapa la sección del equipo (TA-06).
        if tabla is None or (
            isinstance(tabla, Mapping) and tabla.get("configurado") is False
        ):
            sin_configurar.append(agente)
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
    entrada = _numero(
        tabla, "precio_entrada_usd_m", seccion, avisos, permitir_cero=True
    )
    salida = _numero(tabla, "precio_salida_usd_m", seccion, avisos, permitir_cero=True)

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
        endpoint=texto_opcional(tabla.get("endpoint")),
        esfuerzo=texto_opcional(tabla.get("esfuerzo")),
    )

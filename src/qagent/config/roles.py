"""Proveedor, modelo y API key de cada agente, elegidos desde la interfaz (HU-30).

Se apoya en la configuración fija de EN-06 (`carga.py`):

- `config.toml` guarda **solo** qué proveedor y qué modelo usa cada agente (con su
  precio del catálogo). Al guardar se reescribe únicamente la sección
  `[agentes.<agente>]`; el resto del archivo, comentarios incluidos, no se toca.
- `.env` guarda las claves, **una por agente**, en `<VARIABLE_DEL_PROVEEDOR>_<AGENTE>`
  (ej. `GEMINI_API_KEY_PLANNER`, `GEMINI_API_KEY_GENERATOR`).

Regla: el mismo proveedor puede estar en dos o tres agentes, pero cada agente necesita
su propia API key; una clave que ya usa otro agente se rechaza antes de llamar al
proveedor.

Antes de guardar se prueba la conexión con el proveedor (`llm.proveedores`); si falla,
no se escribe nada. Ninguna función de este módulo devuelve ni registra una clave
completa: la interfaz solo recibe la versión enmascarada.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import escribir_texto_atomico
from qagent.config.carga import (
    NOMBRE_AGENTE,
    RUTA_CONFIG,
    RUTA_ENV,
    crear_env,
    leer_env,
    superponer_config,
    variable_de_agente,
    variable_en_uso,
)
from qagent.llm.cliente import TransporteLLM
from qagent.llm.precios import AGENTES
from qagent.llm.proveedores import TIPOS, Proveedor, catalogo, cliente_de

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

#: Caracteres visibles al inicio y al final de una clave enmascarada.
VISIBLES_MASCARA = 4
#: Una clave más corta que esto se oculta entera: mostrar 8 caracteres sería casi toda.
MIN_LARGO_MASCARA = 12
MASCARA_CORTA = "••••"

_CABECERA = re.compile(r"^\s*\[")


class ErrorRol(ValueError):
    """Agente, proveedor o modelo que no están en el catálogo."""


def enmascarar(clave: str | None) -> str:
    """Primeros 4 caracteres + «…» + últimos 4; «••••» si la clave es corta.

    >>> enmascarar("sk-abcdefghijklmnop")
    'sk-a…mnop'
    """
    if not clave:
        return ""
    if len(clave) < MIN_LARGO_MASCARA:
        return MASCARA_CORTA
    return f"{clave[:VISIBLES_MASCARA]}…{clave[-VISIBLES_MASCARA:]}"


# --- Lectura -------------------------------------------------------------------------


def listar_proveedores() -> list[dict[str, Any]]:
    """Proveedores que ofrece la interfaz, con sus modelos.

    Returns:
        Lista de `{"id", "nombre", "tipo", "tipo_nombre", "genera_texto",
        "variables": {agente: variable de .env}, "modelos": [{"id", "nombre",
        "precio_confirmado", "entrada_usd_m", "salida_usd_m"}]}`. No dice si hay claves
        guardadas: una clave no se comparte entre agentes.
    """
    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "tipo": p.tipo,
            "tipo_nombre": TIPOS[p.tipo],
            "genera_texto": p.genera_texto,
            "variables": {a: variable_de_agente(a, p.id) for a in AGENTES},
            "modelos": [
                {
                    "id": m.id,
                    "nombre": m.nombre,
                    "precio_confirmado": m.precio_confirmado,
                    "entrada_usd_m": m.entrada_usd_m,
                    "salida_usd_m": m.salida_usd_m,
                }
                for m in p.modelos
            ],
        }
        for p in catalogo().values()
        if p.visible
    ]


def leer_roles(
    ruta_config: str | Path = RUTA_CONFIG,
    ruta_env: str | Path = RUTA_ENV,
    ruta_local: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Estado de cada agente para la pantalla Configuración.

    Args:
        ruta_config: `config.toml`, donde se guardan proveedor y modelo.
        ruta_env: `.env`, de donde sale la clave (solo enmascarada).
        ruta_local: `config.local.toml` opcional; si define un agente, ese agente usa lo
            de ese archivo y `desde_local` es True.

    Returns:
        Un dict por agente (en orden Planner, Generator, Reviewer) con `agente`,
        `nombre`, `configurado`, `proveedor`, `proveedor_nombre`, `modelo`,
        `modelo_nombre`, `tipo`, `tipo_nombre`, `genera_texto`, `en_catalogo`,
        `precio_confirmado`, `variable` (la que se usa, o la propia si falta),
        `tiene_clave`, `clave_enmascarada`, `clave_repetida_con` (otros agentes con la
        misma clave) y `desde_local`. Nunca incluye la clave completa.
    """
    tablas, locales = _tablas_agentes(Path(ruta_config), ruta_local)
    env = _leer_env_seguro(Path(ruta_env))
    actuales = _claves_actuales(tablas, env)
    return [
        _estado_rol(agente, tablas.get(agente), actuales, agente in locales)
        for agente in AGENTES
    ]


def _estado_rol(
    agente: str,
    tabla: dict[str, Any] | None,
    actuales: dict[str, tuple[str | None, str | None]],
    desde_local: bool,
) -> dict[str, Any]:
    estado: dict[str, Any] = {
        "agente": agente,
        "nombre": NOMBRE_AGENTE[agente],
        "configurado": False,
        "desde_local": desde_local,
    }
    if tabla is None:
        return estado
    pid = str(tabla["proveedor"])
    modelo_id = str(tabla.get("modelo", ""))
    proveedor = catalogo().get(pid)
    modelo = proveedor.modelo(modelo_id) if proveedor else None
    variable, clave = actuales[agente]
    tipo = proveedor.tipo if proveedor else "texto"
    return {
        **estado,
        "configurado": True,
        "proveedor": pid,
        "proveedor_nombre": proveedor.nombre if proveedor else pid,
        "modelo": modelo_id,
        "modelo_nombre": modelo.nombre if modelo else modelo_id,
        "tipo": tipo,
        "tipo_nombre": TIPOS.get(tipo, tipo),
        "genera_texto": tipo == "texto",
        "en_catalogo": modelo is not None,
        "precio_confirmado": bool(modelo and modelo.precio_confirmado),
        "variable": variable or variable_de_agente(agente, pid) or "",
        "tiene_clave": bool(clave),
        "clave_enmascarada": enmascarar(clave),
        "clave_repetida_con": _repetida_con(agente, clave, actuales),
    }


def _tablas_agentes(
    ruta_config: Path, ruta_local: str | Path | None
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Sección `[agentes.*]` vigente de cada agente configurado y los que vienen del local."""
    base = _leer_toml(ruta_config)
    local = _leer_toml(Path(ruta_local)) if ruta_local else {}
    datos = superponer_config(base, local) if local else base
    agentes = datos.get("agentes") if isinstance(datos.get("agentes"), dict) else {}
    locales = local.get("agentes") if isinstance(local.get("agentes"), dict) else {}
    tablas = {
        a: t
        for a, t in agentes.items()
        if a in AGENTES and isinstance(t, dict) and t.get("proveedor")
    }
    return tablas, set(locales) & set(AGENTES)


def _claves_actuales(
    tablas: Mapping[str, Mapping[str, Any]], env: Mapping[str, str]
) -> dict[str, tuple[str | None, str | None]]:
    """`{agente: (variable en uso, clave)}`; `(None, None)` si no tiene clave."""
    actuales: dict[str, tuple[str | None, str | None]] = {}
    for agente in AGENTES:
        tabla = tablas.get(agente)
        variable = (
            variable_en_uso(agente, str(tabla["proveedor"]), env.get) if tabla else None
        )
        actuales[agente] = (variable, env.get(variable) if variable else None)
    return actuales


def _repetida_con(
    agente: str,
    clave: str | None,
    actuales: Mapping[str, tuple[str | None, str | None]],
) -> list[str]:
    """Nombres de los otros agentes que usan exactamente la misma clave."""
    if not clave:
        return []
    return [
        NOMBRE_AGENTE[otro]
        for otro, (_, valor) in actuales.items()
        if otro != agente and valor == clave
    ]


def _leer_toml(ruta: Path) -> dict[str, Any]:
    try:
        with open(ruta, "rb") as archivo:
            return tomllib.load(archivo)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _leer_env_seguro(ruta: Path) -> dict[str, str]:
    try:
        return leer_env(ruta)
    except (OSError, UnicodeDecodeError):
        return {}


# --- Guardar y eliminar --------------------------------------------------------------


def _fallo(mensaje: str, detalle: str = "") -> dict[str, Any]:
    return {"ok": False, "mensaje": mensaje, "detalle": detalle}


def configurar_rol(
    agente: str,
    proveedor: str,
    modelo: str,
    clave: str | None = None,
    *,
    ruta_config: str | Path = RUTA_CONFIG,
    ruta_env: str | Path = RUTA_ENV,
    ruta_local: str | Path | None = None,
    transporte: TransporteLLM | None = None,
) -> dict[str, Any]:
    """Prueba la conexión y, si responde bien, guarda el proveedor y modelo del agente.

    Args:
        agente: "planner", "generator" o "reviewer".
        proveedor: id del catálogo (ej. "gemini"); puede repetirse en otros agentes.
        modelo: id de un modelo de ese proveedor en el catálogo.
        clave: API key nueva; vacía o None mantiene la que el agente ya tiene, solo si
            sigue con el mismo proveedor.
        ruta_config: `config.toml`.
        ruta_env: `.env`.
        ruta_local: `config.local.toml` opcional (para conocer las claves de los demás).
        transporte: transporte HTTP (las pruebas lo reemplazan por uno simulado).

    Returns:
        `{"ok": True, "mensaje": "Conectado ✓"}` o `{"ok": False, "mensaje": motivo,
        "detalle": str}`. Si `ok` es False no se modificó ningún archivo. Una clave
        que ya usa otro agente se rechaza sin llamar al proveedor.
    """
    try:
        datos_proveedor = _validar_eleccion(agente, proveedor, modelo)
    except ErrorRol as error:
        return _fallo(str(error))

    clave_nueva = (clave or "").strip()
    if any(c.isspace() for c in clave_nueva) or '"' in clave_nueva:
        return _fallo(
            "La API key no puede tener espacios, saltos de línea ni comillas."
        )

    ruta_config, ruta_env = Path(ruta_config), Path(ruta_env)
    tablas, _ = _tablas_agentes(ruta_config, ruta_local)
    env = _leer_env_seguro(ruta_env)
    actuales = _claves_actuales(tablas, env)
    anterior = tablas.get(agente)
    mismo_proveedor = anterior is not None and anterior["proveedor"] == proveedor

    clave_a_usar = clave_nueva or (actuales[agente][1] if mismo_proveedor else None)
    if not clave_a_usar:
        return _fallo(
            f"Escribe la API key de {datos_proveedor.nombre} para el "
            f"{NOMBRE_AGENTE[agente]}."
        )
    repetida = _repetida_con(agente, clave_a_usar, actuales)
    if repetida:
        return _fallo(
            f"Esa API key ya la usa el {' y el '.join(repetida)}. Cada agente necesita "
            "su propia API key."
        )

    resultado = cliente_de(datos_proveedor, transporte).validar(clave_a_usar, modelo)
    if not resultado.ok:
        return _fallo(resultado.mensaje, resultado.detalle)

    propia = variable_de_agente(agente, proveedor)
    assert propia is not None  # el proveedor ya se validó en el catálogo
    previa = (
        variable_de_agente(agente, str(anterior["proveedor"])) if anterior else None
    )
    try:
        _guardar(
            agente,
            datos_proveedor,
            modelo,
            ruta_config,
            ruta_env,
            fijar={propia: clave_a_usar} if env.get(propia) != clave_a_usar else {},
            quitar=[previa] if previa and previa != propia else [],
        )
    except (OSError, ValueError) as error:
        return _fallo(
            "La conexión funcionó, pero no se pudo guardar la configuración.",
            str(error).replace(clave_a_usar, "***"),
        )
    return {"ok": True, "mensaje": resultado.mensaje}


def eliminar_rol(
    agente: str,
    *,
    ruta_config: str | Path = RUTA_CONFIG,
    ruta_env: str | Path = RUTA_ENV,
) -> dict[str, Any]:
    """Deja al agente «Sin configurar»: quita su sección de `config.toml` y su clave.

    Se borra solo la variable propia del agente (`<VARIABLE>_<AGENTE>`); la variable
    compartida del proveedor, si existe, no se toca.

    Returns:
        `{"ok": bool, "mensaje": str}`.
    """
    if agente not in AGENTES:
        return {"ok": False, "mensaje": f"Agente desconocido: {agente}."}
    ruta_config, ruta_env = Path(ruta_config), Path(ruta_env)
    try:
        texto = ruta_config.read_text(encoding="utf-8")
        tabla = _leer_toml(ruta_config).get("agentes", {}).get(agente)
        nuevo = reemplazar_seccion_agente(texto, agente, None)
        if nuevo != texto:
            _comprobar_toml(nuevo)
            escribir_texto_atomico(ruta_config, nuevo)
        propia = (
            variable_de_agente(agente, str(tabla.get("proveedor")))
            if isinstance(tabla, dict)
            else None
        )
        if propia and ruta_env.exists():
            env_texto = ruta_env.read_text(encoding="utf-8-sig")
            env_nuevo = quitar_variable_env(env_texto, propia)
            if env_nuevo != env_texto:
                escribir_texto_atomico(ruta_env, env_nuevo)
    except (OSError, ValueError) as error:
        return {
            "ok": False,
            "mensaje": f"No se pudo eliminar la configuración: {error}",
        }
    return {"ok": True, "mensaje": f"{NOMBRE_AGENTE[agente]}: sin configurar."}


def _validar_eleccion(agente: str, proveedor: str, modelo: str) -> Proveedor:
    if agente not in AGENTES:
        raise ErrorRol(f"Agente desconocido: {agente}.")
    datos = catalogo().get(proveedor)
    if datos is None or not datos.visible:
        raise ErrorRol(f"Proveedor no disponible: {proveedor}.")
    if datos.modelo(modelo) is None:
        raise ErrorRol(f"El modelo {modelo} no está en la lista de {datos.nombre}.")
    return datos


def _guardar(
    agente: str,
    proveedor: Proveedor,
    modelo: str,
    ruta_config: Path,
    ruta_env: Path,
    *,
    fijar: Mapping[str, str],
    quitar: list[str],
) -> None:
    """Escribe `.env` (si cambia) y luego `config.toml`; si este falla, deshace `.env`.

    Raises:
        OSError, ValueError: si no se pudo escribir alguno de los dos archivos.
    """
    texto_config = ruta_config.read_text(encoding="utf-8")
    nuevo_config = reemplazar_seccion_agente(
        texto_config, agente, _tabla_agente(proveedor, modelo)
    )
    _comprobar_toml(nuevo_config)

    env_anterior: str | None = None
    if fijar or quitar:
        if not ruta_env.exists():
            crear_env(ruta_env, None)
        env_anterior = ruta_env.read_text(encoding="utf-8-sig")
        env_nuevo = env_anterior
        for nombre in quitar:
            env_nuevo = quitar_variable_env(env_nuevo, nombre)
        for nombre, valor in fijar.items():
            env_nuevo = reemplazar_variable_env(env_nuevo, nombre, valor)
        escribir_texto_atomico(ruta_env, env_nuevo)
    try:
        escribir_texto_atomico(ruta_config, nuevo_config)
    except OSError:
        if env_anterior is not None:
            escribir_texto_atomico(ruta_env, env_anterior)
        raise


def _tabla_agente(proveedor: Proveedor, modelo_id: str) -> list[str]:
    """Líneas de `[agentes.<agente>]`: proveedor, modelo y precios. Nunca la clave."""
    modelo = proveedor.modelo(modelo_id)
    assert modelo is not None  # ya validado
    nota = "" if modelo.precio_confirmado else "   # precio sin confirmar"
    return [
        "# Elegido desde la aplicación (HU-30). La clave está en .env.",
        f"proveedor = {_cadena_toml(proveedor.id)}",
        f"modelo = {_cadena_toml(modelo.id)}",
        f"precio_entrada_usd_m = {modelo.entrada_usd_m:g}{nota}",
        f"precio_salida_usd_m = {modelo.salida_usd_m:g}{nota}",
    ]


def _cadena_toml(valor: str) -> str:
    """Cadena básica de TOML (las secuencias de escape de JSON son válidas en TOML)."""
    return json.dumps(valor)


def _comprobar_toml(texto: str) -> None:
    """Falla antes de escribir si el resultado no fuera TOML válido."""
    try:
        tomllib.loads(texto)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"config.toml quedaría inválido: {error}") from error


def reemplazar_seccion_agente(texto: str, agente: str, lineas: list[str] | None) -> str:
    """Reemplaza (o quita, con `lineas=None`) la sección `[agentes.<agente>]`.

    La sección va desde su encabezado hasta el siguiente encabezado `[...]`. Si no
    existe, se agrega antes de la sección del siguiente agente o al final del archivo.
    El resto del texto no cambia.
    """
    filas = texto.splitlines()
    inicio = _indice_encabezado(filas, agente)
    bloque = [f"[agentes.{agente}]", *lineas, ""] if lineas is not None else []
    if inicio is None:
        if lineas is None:
            return texto
        posicion = _posicion_nueva_seccion(filas, agente)
        if posicion > 0 and filas[posicion - 1].strip():
            bloque = ["", *bloque]
        filas[posicion:posicion] = bloque
    else:
        fin = inicio + 1
        while fin < len(filas) and not _CABECERA.match(filas[fin]):
            fin += 1
        filas[inicio:fin] = bloque
    while filas and not filas[-1].strip():
        filas.pop()
    return "\n".join(filas) + "\n"


def _indice_encabezado(filas: list[str], agente: str) -> int | None:
    patron = re.compile(rf"^\s*\[\s*agentes\s*\.\s*{re.escape(agente)}\s*\]\s*(#.*)?$")
    return next((i for i, fila in enumerate(filas) if patron.match(fila)), None)


def _posicion_nueva_seccion(filas: list[str], agente: str) -> int:
    for siguiente in AGENTES[AGENTES.index(agente) + 1 :]:
        indice = _indice_encabezado(filas, siguiente)
        if indice is not None:
            return indice
    return len(filas)


def _patron_variable(nombre: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*(export\s+)?{re.escape(nombre)}\s*=")


def reemplazar_variable_env(texto: str, nombre: str, valor: str) -> str:
    """Fija `NOMBRE=valor` en el texto de un `.env`, sin tocar las demás líneas.

    Si la variable aparece varias veces, queda una sola (la primera, actualizada); si no
    aparece, se agrega al final.
    """
    patron = _patron_variable(nombre)
    filas: list[str] = []
    puesta = False
    for fila in texto.splitlines():
        if patron.match(fila):
            if not puesta:
                filas.append(f"{nombre}={valor}")
                puesta = True
            continue
        filas.append(fila)
    if not puesta:
        while filas and not filas[-1].strip():
            filas.pop()
        filas.append(f"{nombre}={valor}")
    return "\n".join(filas) + "\n"


def quitar_variable_env(texto: str, nombre: str) -> str:
    """Quita todas las líneas `NOMBRE=...` de un `.env`; las demás no cambian."""
    patron = _patron_variable(nombre)
    if not any(patron.match(fila) for fila in texto.splitlines()):
        return texto
    filas = [fila for fila in texto.splitlines() if not patron.match(fila)]
    return "\n".join(filas) + "\n"

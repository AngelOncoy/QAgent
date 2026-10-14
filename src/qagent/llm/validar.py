"""Prueba las claves y los modelos de `config.toml` con una llamada mínima por agente.

Uso (desde la carpeta del repositorio):

    python -m qagent.llm.validar            # una llamada corta a cada agente
    python -m qagent.llm.validar --gratis   # además lista los modelos :free de OpenRouter

Lee `config.toml`, `config.local.toml` (si existe) y `.env` igual que la aplicación, ignora `QAGENT_FAKE_LLM` (siempre
usa la IA real) y nunca muestra las claves: solo dice qué agente respondió, con qué
modelo, en cuánto tiempo y cuántos tokens usó. Cada llamada cuesta unos pocos tokens
(US$ 0 con los modelos de capa gratuita).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from qagent.config import carga as config_carga
from qagent.config.carga import cargar_configuracion
from qagent.llm.fabrica import ConfiguracionLLMIncompleta, crear_cliente

#: Instrucción mínima: pocos tokens de entrada y de salida.
PROMPT_PRUEBA = "Responde solo con la palabra OK."
URL_MODELOS_OPENROUTER = "https://openrouter.ai/api/v1/models"


def validar(con_gratis: bool = False) -> int:
    """Llama una vez a cada agente; devuelve 0 si todos respondieron, 1 si no."""
    carga = cargar_configuracion(
        simulado=False, ruta_local=config_carga.RUTA_CONFIG_LOCAL
    )
    if carga.config is None:
        for aviso in carga.avisos_config:
            print(f"[config.toml] {aviso}")
        return 1
    for aviso in carga.avisos:
        print(f"[aviso] {aviso}")

    fallos = 0
    for agente, precio in carga.config.agentes.items():
        etiqueta = f"{agente:9} {precio.proveedor}/{precio.modelo}"
        try:
            cliente = crear_cliente(
                precio, carga.claves, simulado=False, timeout_s=60.0
            )
            inicio = time.monotonic()
            respuesta = cliente.generar(PROMPT_PRUEBA, rol=agente)
            segundos = time.monotonic() - inicio
        except ConfiguracionLLMIncompleta as error:
            fallos += 1
            print(f"FALLA  {etiqueta}\n       {error}")
            continue
        except Exception as error:  # noqa: BLE001 - se informa cualquier fallo de red o API
            fallos += 1
            print(f"FALLA  {etiqueta}\n       {error}")
            continue
        texto = " ".join(respuesta.contenido.split())[:40]
        print(
            f"OK     {etiqueta}  {segundos:.1f} s  "
            f"{respuesta.tokens_entrada}+{respuesta.tokens_salida} tokens  "
            f"US$ {respuesta.costo_usd:.6f}  respuesta: {texto!r}"
        )

    if con_gratis:
        listar_gratis_openrouter()
    print(
        "\nTodos los agentes respondieron."
        if not fallos
        else (
            f"\n{fallos} agente(s) no respondieron. Según el detalle: «No se pudo "
            "conectar» = red o firewall; HTTP 401/403 = clave en .env; HTTP 404 o "
            "«model» = nombre del modelo en config.local.toml; HTTP 429 = cuota gratuita."
        )
    )
    return 1 if fallos else 0


def modelos_gratis_openrouter(datos: dict[str, Any]) -> list[tuple[str, int | None]]:
    """IDs `:free` (y su ventana de contexto) de la respuesta de `/api/v1/models`."""
    modelos = datos.get("data") if isinstance(datos, dict) else None
    if not isinstance(modelos, list):
        return []
    return sorted(
        (m["id"], m.get("context_length"))
        for m in modelos
        if isinstance(m, dict) and str(m.get("id", "")).endswith(":free")
    )


def listar_gratis_openrouter() -> None:
    """Imprime los modelos gratuitos de OpenRouter (la lista es pública, sin clave)."""
    print("\nModelos :free de OpenRouter hoy:")
    try:
        with urlopen(Request(URL_MODELOS_OPENROUTER), timeout=30) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except (URLError, OSError, json.JSONDecodeError) as error:
        print(f"  No se pudo leer la lista: {error}")
        return
    gratis = modelos_gratis_openrouter(datos)
    if not gratis:
        print("  (ninguno)")
    for modelo, contexto in gratis:
        print(f"  {modelo}" + (f"  (contexto {contexto:,} tokens)" if contexto else ""))


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de `python -m qagent.llm.validar`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--gratis",
        action="store_true",
        help="lista también los modelos :free de OpenRouter",
    )
    args = parser.parse_args(argv)
    config_carga.migrar_desde_repositorio()  # .env y config.local.toml → ~/.qagent/
    return validar(con_gratis=args.gratis)


if __name__ == "__main__":
    sys.exit(main())

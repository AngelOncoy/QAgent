"""Mutation testing acotado con mutmut dentro del sandbox (EN-09).

Solo muta las funciones que se le piden (las marcadas como críticas, HU-06), nunca el
repositorio completo (RN-04). Todo ocurre en el contenedor sin red de `ejecutar_en_sandbox`,
sobre la copia del proyecto:

1. Copia las pruebas aprobadas dentro de la copia del proyecto. mutmut identifica las
   pruebas con rutas relativas; si quedan fuera del proyecto no las encuentra al probar
   cada mutante y cuenta ese error como «killed», lo que daría un Mutation Score falso.
2. Escribe la sección `[mutmut]` de `setup.cfg` (solo en la copia) para mutar únicamente
   el archivo del módulo.
3. Ejecuta `mutmut run` solo con los mutantes de las funciones pedidas.
4. Lee el resultado de cada mutante y el cambio de los que sobrevivieron.

Los manejadores de endpoints FastAPI (#74) llevan decorador y mutmut no los muta; antes de
correr, su cuerpo se aísla en una función sin decorador (`manejadores.py`), solo en la
copia del sandbox, y se mutan únicamente esas funciones.

Si el proyecto ya trae `[tool.mutmut]` en su `pyproject.toml`, mutmut la prefiere sobre la
de QAgent: en ese caso no se ejecuta y el resultado lo explica.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker

from qagent.sandbox.ejecucion import DIR_SALIDA, ejecutar_en_sandbox
from qagent.sandbox.manejadores import (
    aislar_manejadores,
    motivo_no_aislable,
    nombre_aislado,
)
from qagent.sandbox.modelos import (
    LIMITES_POR_DEFECTO,
    LimitesSandbox,
    ResultadoSandbox,
)

ARCHIVO_RESULTADO = "mutacion.json"
#: Carpeta (dentro de la copia del proyecto) donde se copian las pruebas aprobadas.
CARPETA_PRUEBAS = "_qagent_mutacion"
#: Módulo con los manejadores aislados (#74); viaja con las pruebas y reemplaza al
#: módulo en la copia del proyecto. No termina en .py para que pytest no lo recoja.
ARCHIVO_AISLADO = "_qagent_modulo_aislado.txt"
LIMITE_RESULTADO_BYTES = 2_000_000

#: Estados de una función tras la mutación.
OK = "ok"
TIEMPO_AGOTADO = "tiempo_agotado"
CONFIG_PROPIA = "config_propia"
ERROR = "error"

# Códigos de salida por mutante, como los define mutmut 3 (`mutmut.stats`).
_DETECTADO = {1, 3, 24, -24, 36, 37, 152, 255}  # killed, timeout o atrapado por tipos
_SOBREVIVIO = {0, 5, 33}  # survived o sin pruebas que lo cubran

# Script que corre dentro del contenedor. Recibe el archivo y las funciones por variables
# de entorno y deja el resultado en /out/mutacion.json.
SCRIPT_MUTACION = f'''
import configparser, json, os, shutil, subprocess, sys
from pathlib import Path

archivo = os.environ["QAGENT_MUT_ARCHIVO"]
funciones = json.loads(os.environ["QAGENT_MUT_FUNCIONES"])
salida = Path("{DIR_SALIDA}") / "{ARCHIVO_RESULTADO}"

def terminar(datos):
    salida.write_text(json.dumps(datos), encoding="utf-8")
    sys.exit(0)

pyproject = Path("pyproject.toml")
if pyproject.is_file():
    import tomllib
    try:
        propia = "mutmut" in tomllib.loads(pyproject.read_text("utf-8")).get("tool", {{}})
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        propia = False
    if propia:
        terminar({{"estado": "{CONFIG_PROPIA}"}})

shutil.copytree("/work/tests", "{CARPETA_PRUEBAS}")
# Manejadores aislados (#74): reemplazan al módulo solo en esta copia del proyecto.
aislado = Path("{CARPETA_PRUEBAS}") / "{ARCHIVO_AISLADO}"
if aislado.is_file():
    Path(archivo).write_text(aislado.read_text("utf-8"), encoding="utf-8")
    aislado.unlink()
fuentes = sorted(
    p.name for p in Path(".").iterdir()
    if p.name not in {{"mutants", "{CARPETA_PRUEBAS}"}}
    and (p.is_dir() or p.suffix == ".py")
)
config = configparser.RawConfigParser()
config.read("setup.cfg")
config["mutmut"] = {{
    "source_paths": "\\n".join(fuentes),
    "only_mutate": archivo,
    "pytest_add_cli_args_test_selection": "{CARPETA_PRUEBAS}",
    "pytest_add_cli_args": "-p no:cacheprovider",
    "also_copy": "{CARPETA_PRUEBAS}",
}}
with open("setup.cfg", "w", encoding="utf-8") as f:
    config.write(f)

patrones = ["*.x_" + nombre + "__mutmut_*" for nombre in funciones]
corrida = subprocess.run(
    ["mutmut", "run", "--max-children", "1", *patrones],
    capture_output=True, text=True,
)
texto = (corrida.stdout + corrida.stderr).replace("\\r", "\\n")
salida_mutmut = "\\n".join(
    linea for linea in texto.splitlines() if linea.strip() and not linea[0] in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
)[-4000:]

meta = Path("mutants") / (archivo + ".meta")
if not meta.is_file():
    terminar({{"estado": "{ERROR}", "salida": salida_mutmut}})
codigos = json.loads(meta.read_text("utf-8")).get("exit_code_by_key", {{}})
elegidos = {{
    nombre: codigo for nombre, codigo in codigos.items()
    if nombre.rsplit("__mutmut_", 1)[0].rsplit(".", 1)[-1][2:] in funciones
}}
cambios = {{}}
for nombre, codigo in elegidos.items():
    if codigo in {sorted(_SOBREVIVIO)}:
        mostrado = subprocess.run(["mutmut", "show", nombre], capture_output=True, text=True)
        cambios[nombre] = mostrado.stdout[-3000:]
terminar({{"estado": "{OK}", "codigos": elegidos, "cambios": cambios, "salida": salida_mutmut}})
'''


@dataclass
class Sobreviviente:
    """Un mutante que las pruebas no detectaron.

    Atributos:
        mutante: nombre de mutmut (ej. `calc.x_descuento__mutmut_3`).
        linea: línea del archivo original donde está el cambio, o None si no se sabe
            (se calcula con la línea del `def` que da el análisis AST).
        cambio: texto antes → después, ej. `precio > 100 → precio > 101`.
    """

    mutante: str
    linea: int | None
    cambio: str


@dataclass
class MutacionFuncion:
    """Resultado de la mutación de una función.

    Atributos:
        funcion: nombre de la función.
        estado: "ok", "tiempo_agotado", "config_propia" o "error".
        puntuacion: Mutation Score (0-100) o None si no se pudo calcular.
        detectados: mutantes que las pruebas detectaron (incluye timeouts).
        sobrevivientes: mutantes que las pruebas no detectaron.
        mensaje: explicación para el usuario cuando el estado no es "ok".
    """

    funcion: str
    estado: str
    puntuacion: float | None = None
    detectados: int = 0
    sobrevivientes: list[Sobreviviente] = field(default_factory=list)
    mensaje: str | None = None

    @property
    def evaluados(self) -> int:
        """Mutantes con veredicto: detectados más sobrevivientes."""
        return self.detectados + len(self.sobrevivientes)


@dataclass
class ResultadoMutacion:
    """Resultado de una ejecución de mutmut sobre las funciones de un módulo.

    Atributos:
        modulo: ruta del módulo relativa al proyecto.
        funciones: resultado por nombre de función.
        duracion_s: duración de la ejecución en el sandbox.
        salida: últimas líneas de mutmut, para diagnóstico.
    """

    modulo: str
    funciones: dict[str, MutacionFuncion]
    duracion_s: float = 0.0
    salida: str = ""


def puntuacion(detectados: int, sobrevivientes: int) -> float | None:
    """Mutation Score: detectados ÷ (detectados + sobrevivientes) × 100, con un decimal.

    None si no hubo ningún mutante con veredicto.
    """
    evaluados = detectados + sobrevivientes
    if evaluados == 0:
        return None
    return round(detectados / evaluados * 100, 1)


def funcion_del_mutante(nombre: str) -> str:
    """Función a la que pertenece un mutante: `pkg.calc.x_descuento__mutmut_3` → `descuento`."""
    prefijo = nombre.rsplit("__mutmut_", 1)[0].rsplit(".", 1)[-1]
    return prefijo.removeprefix("x_")


def linea_y_cambio(diff: str) -> tuple[int | None, str]:
    """Línea del cambio y texto `antes → después` del diff de `mutmut show`.

    `mutmut show` compara solo el texto de la función, así que la línea es relativa a
    ella (1 = la línea del `def`).
    """
    numero: int | None = None
    antes = despues = None
    for linea in diff.splitlines():
        encabezado = re.match(r"^@@ -(\d+)", linea)
        if encabezado:
            numero = int(encabezado.group(1))
            continue
        if numero is None or linea.startswith(("---", "+++")):
            continue
        if linea.startswith("-") and antes is None:
            antes = linea[1:].strip()
        elif linea.startswith("+") and despues is None:
            despues = linea[1:].strip()
        elif antes is None:
            numero += 1
    if antes is None and despues is None:
        return None, ""
    return numero, f"{antes or ''} → {despues or ''}".strip()


def interpretar(
    datos: dict[str, Any] | None,
    funciones: list[str],
    inicios: dict[str, int] | None = None,
) -> dict[str, MutacionFuncion]:
    """Traduce el `mutacion.json` del contenedor al resultado de cada función.

    `inicios` es la línea del `def` de cada función en el archivo (del análisis AST);
    con ella la línea de cada sobreviviente pasa a ser la del archivo. Sin ella, queda
    en None.
    """
    estado = (datos or {}).get("estado")
    if estado == CONFIG_PROPIA:
        return _todas(
            funciones,
            CONFIG_PROPIA,
            "El proyecto tiene su propia configuración de mutmut en pyproject.toml; "
            "QAgent no la sobrescribe.",
        )
    if estado != OK:
        return _todas(funciones, ERROR, "mutmut no pudo ejecutarse en el sandbox.")

    codigos: dict[str, int | None] = datos.get("codigos") or {}
    cambios: dict[str, str] = datos.get("cambios") or {}
    resultado = {nombre: MutacionFuncion(nombre, OK) for nombre in funciones}
    for mutante, codigo in sorted(codigos.items()):
        funcion = resultado.get(funcion_del_mutante(mutante))
        if funcion is None:
            continue
        if codigo in _DETECTADO:
            funcion.detectados += 1
        elif codigo in _SOBREVIVIO:
            relativa, cambio = linea_y_cambio(cambios.get(mutante, ""))
            inicio = (inicios or {}).get(funcion.funcion)
            linea = (
                None if relativa is None or inicio is None else inicio + relativa - 1
            )
            funcion.sobrevivientes.append(Sobreviviente(mutante, linea, cambio))
    for funcion in resultado.values():
        funcion.puntuacion = puntuacion(funcion.detectados, len(funcion.sobrevivientes))
        if funcion.puntuacion is None:
            funcion.mensaje = "mutmut no generó mutantes evaluables para esta función."
    return resultado


def comando_mutacion(
    modulo: str, funciones: list[str]
) -> tuple[list[str], dict[str, str]]:
    """Comando y variables de entorno con que el sandbox corre mutmut (EN-17).

    Args:
        modulo: ruta del módulo relativa al proyecto (ej. `pkg/calc.py`).
        funciones: nombres de las funciones críticas a mutar.
    """
    entorno = {
        # Sin PYTHONPATH: mutmut debe importar el módulo mutado de `mutants/`, no el original.
        "PYTHONPATH": "",
        "QAGENT_MUT_ARCHIVO": Path(modulo).as_posix(),
        "QAGENT_MUT_FUNCIONES": json.dumps(list(funciones)),
    }
    return ["python", "-c", SCRIPT_MUTACION], entorno


def ejecutar_mutacion(
    imagen: str,
    ruta_proyecto: str | Path,
    ruta_tests: str | Path,
    modulo: str,
    funciones: list[str],
    limites: LimitesSandbox = LIMITES_POR_DEFECTO,
    cliente: docker.DockerClient | None = None,
    inicios: dict[str, int] | None = None,
    manejadores: list[str] | None = None,
) -> ResultadoMutacion:
    """Ejecuta mutmut en el sandbox solo sobre `funciones` del archivo `modulo`.

    Args:
        imagen: etiqueta de la imagen devuelta por `preparar_imagen`.
        ruta_proyecto: carpeta raíz del proyecto original (no se modifica).
        ruta_tests: carpeta con las pruebas aprobadas que se usan contra cada mutante.
        modulo: ruta del módulo relativa al proyecto (ej. `pkg/calc.py`).
        funciones: nombres de las funciones críticas a mutar.
        limites: CPU, memoria y tiempo máximo de toda la ejecución.
        cliente: cliente Docker; si es None se crea uno.
        inicios: línea del `def` de cada función o manejador, para ubicar los
            sobrevivientes.
        manejadores: manejadores de endpoints críticos (#74). Se muta solo su cuerpo,
            aislado en la copia del sandbox; el resultado queda con su nombre.

    Returns:
        Resultado por función y por manejador. Si se agota el tiempo, todas quedan en "tiempo_agotado"
        sin puntuación; nunca lanza por un fallo de mutmut.
    """
    manejadores = list(dict.fromkeys(manejadores or []))
    if manejadores:
        return _con_manejadores_aislados(
            imagen,
            ruta_proyecto,
            ruta_tests,
            modulo,
            funciones,
            limites,
            cliente,
            inicios or {},
            manejadores,
        )
    leido: dict[str, Any] = {}

    def leer(_copia: Path, salida: Path) -> None:
        archivo = salida / ARCHIVO_RESULTADO
        try:
            if archivo.is_file() and archivo.stat().st_size <= LIMITE_RESULTADO_BYTES:
                leido.update(json.loads(archivo.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass

    comando, entorno = comando_mutacion(modulo, funciones)
    ejecucion: ResultadoSandbox = ejecutar_en_sandbox(
        imagen,
        comando,
        ruta_proyecto,
        ruta_tests,
        limites,
        entorno=entorno,
        al_terminar=leer,
        cliente=cliente,
    )
    if ejecucion.timed_out:
        por_funcion = _todas(
            funciones,
            TIEMPO_AGOTADO,
            f"Se agotó el tiempo máximo de la mutación ({limites.timeout_s} s).",
        )
    else:
        por_funcion = interpretar(leido or None, funciones, inicios)
    salida = str(leido.get("salida") or (ejecucion.stdout + ejecucion.stderr))[-4000:]
    return ResultadoMutacion(
        modulo=Path(modulo).as_posix(),
        funciones=por_funcion,
        duracion_s=ejecucion.duracion_s,
        salida=salida,
    )


def _con_manejadores_aislados(
    imagen: str,
    ruta_proyecto: str | Path,
    ruta_tests: str | Path,
    modulo: str,
    funciones: list[str],
    limites: LimitesSandbox,
    cliente: docker.DockerClient | None,
    inicios: dict[str, int],
    manejadores: list[str],
) -> ResultadoMutacion:
    """Aísla los manejadores, corre mutmut y devuelve el resultado con sus nombres."""
    try:
        fuente = (Path(ruta_proyecto) / modulo).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        fuente, motivos = "", dict.fromkeys(manejadores, f"No se pudo leer: {error}")
    else:
        motivos = {m: motivo_no_aislable(fuente, m) for m in manejadores}
    aislables = [m for m in manejadores if not motivos[m]]
    no_aislables = {
        m: MutacionFuncion(m, ERROR, mensaje=motivo)
        for m, motivo in motivos.items()
        if motivo
    }
    if not funciones and not aislables:
        return ResultadoMutacion(Path(modulo).as_posix(), no_aislables)

    with tempfile.TemporaryDirectory(prefix="qagent-aislado-") as carpeta:
        pruebas = Path(carpeta) / "pruebas"
        shutil.copytree(ruta_tests, pruebas)
        if aislables:
            (pruebas / ARCHIVO_AISLADO).write_text(
                aislar_manejadores(fuente, aislables), encoding="utf-8"
            )
        resultado = ejecutar_mutacion(
            imagen,
            ruta_proyecto,
            pruebas,
            modulo,
            [*funciones, *(nombre_aislado(m) for m in aislables)],
            limites,
            cliente,
            {
                **inicios,
                **{nombre_aislado(m): inicios[m] for m in aislables if m in inicios},
            },
        )
    por_nombre = {
        nombre: resultado.funciones[nombre]
        for nombre in funciones
        if nombre in resultado.funciones
    }
    for manejador in aislables:
        aislado = resultado.funciones.get(nombre_aislado(manejador))
        if aislado is not None:
            aislado.funcion = manejador
            por_nombre[manejador] = aislado
    resultado.funciones = {**por_nombre, **no_aislables}
    return resultado


def _todas(
    funciones: list[str], estado: str, mensaje: str
) -> dict[str, MutacionFuncion]:
    return {
        nombre: MutacionFuncion(nombre, estado, mensaje=mensaje) for nombre in funciones
    }

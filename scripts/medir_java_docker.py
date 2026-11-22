"""Corrida completa grabada; JUnit y Maven solo en Docker sin red."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.cwd()))
from qagent.config import carga, cargar_configuracion
from qagent.lenguajes import java, java_generacion, java_revision, treesitter
from qagent.llm import FakeLLMClient, RespuestaLLM
from qagent.llm.fake import MARCA_CONTRATO
from qagent.orchestrator import corrida
from qagent.sandbox import ejecucion
from qagent.sandbox.modelos import IMAGEN_JAVA
from tests.sandbox.test_issue305_construccion_docker import pom_de_fixture

argumentos = argparse.ArgumentParser(description=__doc__)
argumentos.add_argument("etiqueta", choices=["antes", "despues", "medicion"])
argumentos.add_argument("--salida", type=Path, required=True)
opciones = argumentos.parse_args()
base = opciones.salida.resolve()
base.mkdir(parents=True, exist_ok=True)
fase = opciones.etiqueta
raiz = base / ("Proyecto-" + fase)
raiz.mkdir(exist_ok=False)
fuentes = raiz / "src/main/java/ejemplo"
fuentes.mkdir(parents=True)
for i in range(8):
    codigo = "\n".join(
        f"/** Devuelve el doble. @return dos veces x */ public static int f{j}(int x) {{ return x * 2; }}"
        for j in range(4)
    )
    (fuentes / f"Banco{i}.java").write_text(
        f"package ejemplo; public class Banco{i} {{\n{codigo}\n}}\n", encoding="utf-8"
    )
pom_de_fixture(raiz)
originales = {
    p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in raiz.rglob("*")
    if p.is_file()
}
contadores = {
    "parseos": 0,
    "declaraciones": 0,
    "copias": 0,
    "contenedores": 0,
    "compilaciones_javac_observadas": 0,
    "fases_compile_observadas": 0,
}
obtener_parser = treesitter.obtener_parser
declaraciones = java._declaraciones
copiar = ejecucion.copiar_proyecto
from docker.models.containers import ContainerCollection

import qagent.lenguajes.java_construccion as construccion

ejecutar_real = ContainerCollection.run
ids = []


class Parser:
    def __init__(self, lenguaje):
        self.parser = obtener_parser(lenguaje)

    def parse(self, *a, **k):
        contadores["parseos"] += 1
        return self.parser.parse(*a, **k)


def declarar(*a, **k):
    contadores["declaraciones"] += 1
    return declaraciones(*a, **k)


def copiar_contado(*a, **k):
    contadores["copias"] += 1
    return copiar(*a, **k)


def ejecutar(self, *a, **k):
    assert k["network_mode"] == "none" and k["read_only"] and k["cap_drop"] == ["ALL"]
    contadores["contenedores"] += 1
    c = ejecutar_real(self, *a, **k)
    ids.append(c.id)
    logs = c.logs

    def leer_logs(*args, **kwargs):
        datos = logs(*args, **kwargs)
        if kwargs.get("stdout") and not kwargs.get("stderr"):
            import re

            texto = datos.decode("utf-8", errors="replace")
            contadores["fases_compile_observadas"] += len(
                re.findall(r"--- compiler:[^\n]*:compile ", texto)
            )
            contadores["compilaciones_javac_observadas"] += len(
                re.findall(r"Compiling \d+ source files?", texto)
            )
        return datos

    c.logs = leer_logs
    return c


caso = [
    {
        "id": "normal",
        "entrada": {"x": 2},
        "valor_esperado": 4,
        "origen": "docstring",
        "categoria": "normal",
    }
]


class Cliente(FakeLLMClient):
    def __init__(self):
        super().__init__(
            grabaciones={
                f"Banco{i}.java::Banco{i}.f{j}": caso
                for i in range(8)
                for j in range(4)
            }
        )

    def generar(self, prompt, rol="planner"):
        if rol != "generator":
            return super().generar(prompt, rol)
        contrato = json.loads(prompt.rsplit(MARCA_CONTRATO, 1)[1])
        clase, metodo = contrato["objetivo"].split(".")
        codigo = f"package ejemplo; import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.assertEquals; class {clase}Test {{ @Test void test_normal() {{ assertEquals(4,{clase}.{metodo}(2)); }} }}"
        return RespuestaLLM(
            contenido=codigo,
            modelo="fake-308",
            tokens_entrada=0,
            tokens_salida=0,
            costo_usd=0,
        )


with pytest.MonkeyPatch.context() as m:
    m.setattr(carga, "RUTA_ENV", base / "perfil-sin-claves/.env")
    m.setattr(carga, "RUTA_CONFIG_LOCAL", base / "perfil-sin-claves/config.local.toml")
    m.setattr(java, "_declaraciones", declarar)
    for modulo in (java, java_generacion, java_revision):
        m.setattr(modulo, "obtener_parser", Parser, raising=False)
    try:
        from qagent.lenguajes import java_sesion

        m.setattr(java_sesion, "obtener_parser", Parser)
    except ImportError:
        pass
    m.setattr(ejecucion, "copiar_proyecto", copiar_contado)
    m.setattr(construccion, "copiar_proyecto", copiar_contado)
    m.setattr(ContainerCollection, "run", ejecutar)
    m.setattr(corrida, "crear_cliente", lambda *a, **k: Cliente())
    config = cargar_configuracion(simulado=True).config
    seleccion = [
        {
            "ruta": "src/main/java/ejemplo/Banco0.java",
            "funciones": ["Banco0.f0", "Banco0.f1", "Banco0.f2"],
        }
    ]
    inicio = time.perf_counter()
    r = corrida.ejecutar_corrida(
        raiz,
        "humo",
        config,
        None,
        simulado=True,
        preparar_imagen=lambda _: IMAGEN_JAVA,
        seleccion=seleccion,
    )
    duracion = time.perf_counter() - inicio
assert r.estado == "fin" and r.aceptadas == 3 and r.tokens_reales == 0, r.a_dict()
assert originales == {
    p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in raiz.rglob("*")
    if p.is_file() and ".qagent" not in p.parts
}
import docker

c = docker.from_env()
assert all(not c.containers.list(all=True, filters={"id": i}) for i in ids)
results = json.loads((Path(r.carpeta) / "results.json").read_text(encoding="utf-8"))
salida = {
    "revision": __import__("subprocess")
    .check_output(["git", "rev-parse", "HEAD"], text=True)
    .strip(),
    "archivos_fuente": 8,
    "objetivos_disponibles": 32,
    "objetivos_seleccionados": 3,
    **contadores,
    "duracion_s": duracion,
    "resumen": r.a_dict(),
    "veredictos": [
        {k: o.get(k) for k in ("modulo", "funcion", "decision", "metricas")}
        for o in results["objetivos"]
    ],
    "imagen_id": c.images.get(IMAGEN_JAVA).id,
    "originales_sha256": originales,
    "cpu_docker_medida": None,
    "pico_memoria_docker_medido": None,
    "rss_host_medido": None,
    "limites_docker": {
        "cpus": config.limites_sandbox("java").cpus,
        "memoria": config.limites_sandbox("java").memoria,
        "timeout_s": config.limites_sandbox("java").timeout_s,
    },
}
(base / f"docker-{fase}.json").write_text(
    json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(
    json.dumps(
        {
            k: v
            for k, v in salida.items()
            if k not in {"veredictos", "originales_sha256", "resumen"}
        },
        ensure_ascii=True,
    ),
    flush=True,
)

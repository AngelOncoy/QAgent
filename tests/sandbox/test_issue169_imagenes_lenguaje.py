"""#169: imágenes del sandbox para Node y Java, con Docker simulado (no necesita Docker).

Cubre la selección de imagen según el adaptador, la construcción de la imagen base y de
la derivada por proyecto (`npm ci`, `mvn dependency:go-offline`, Gradle), su
reutilización, los avisos de avance y que la ejecución use los límites del lenguaje.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import ImageNotFound

from qagent.lenguajes import adaptador_para
from qagent.sandbox import (
    IMAGEN_BASE,
    IMAGEN_JAVA,
    IMAGEN_NODE,
    ImagenNoEncontrada,
    LimitesSandbox,
    asegurar_imagen,
    construir_imagen_base,
    ejecutar_en_sandbox,
    preparar_imagen,
)
from qagent.sandbox import imagen as modulo_imagen
from qagent.sandbox.imagen import (
    RECETAS,
    aviso_dependencias,
    describir_linea,
    etiqueta_para_dependencias,
    etiqueta_para_requirements,
)
from qagent.sandbox.limpieza import PREFIJOS_DERIVADAS, _es_imagen_req

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

RAIZ = Path(__file__).resolve().parents[2]
CARPETA_SANDBOX = RAIZ / "src" / "qagent" / "sandbox"

LOCK_VACIO = b'{"name": "demo", "lockfileVersion": 3, "packages": {}}\n'


class DockerSimulado:
    """Cliente Docker simulado: recuerda qué imágenes existen y qué se construyó."""

    def __init__(self, *existentes: str) -> None:
        self.existentes = set(existentes)
        self.construcciones: list[dict] = []
        self.cliente = MagicMock()
        self.cliente.images.get.side_effect = self._get
        self.cliente.images.build.side_effect = self._build

    def _get(self, etiqueta: str) -> MagicMock:
        if etiqueta not in self.existentes:
            raise ImageNotFound(etiqueta)
        return MagicMock()

    def _build(self, path: str, tag: str, **kwargs) -> tuple:
        raiz = Path(path)
        self.construcciones.append(
            {
                "tag": tag,
                "archivos": sorted(
                    p.relative_to(raiz).as_posix()
                    for p in raiz.rglob("*")
                    if p.is_file()
                ),
                "dockerfile": (raiz / "Dockerfile").read_text(encoding="utf-8"),
            }
        )
        self.existentes.add(tag)
        return MagicMock(), iter([])


@pytest.fixture
def proyecto_node(tmp_path: Path) -> Path:
    raiz = tmp_path / "web"
    (raiz / "src").mkdir(parents=True)
    (raiz / "src" / "suma.js").write_text("export const suma = (a, b) => a + b;\n")
    (raiz / ".env").write_text("CLAVE=secreta\n", encoding="utf-8")
    (raiz / "package.json").write_bytes(b'{"name": "demo", "version": "1.0.0"}\n')
    (raiz / "package-lock.json").write_bytes(LOCK_VACIO)
    return raiz


@pytest.fixture
def proyecto_maven(tmp_path: Path) -> Path:
    raiz = tmp_path / "api"
    (raiz / "src" / "main" / "java").mkdir(parents=True)
    (raiz / "src" / "main" / "java" / "Suma.java").write_text("class Suma {}\n")
    (raiz / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    return raiz


# --- Selección de imagen según el adaptador --------------------------------------------


@pytest.mark.parametrize(
    "lenguaje, imagen",
    [
        ("python", IMAGEN_BASE),
        ("javascript", IMAGEN_NODE),
        ("typescript", IMAGEN_NODE),
        ("java", IMAGEN_JAVA),
    ],
)
def test_cada_adaptador_pide_la_imagen_de_su_lenguaje(lenguaje, imagen):
    entorno = adaptador_para(lenguaje).entorno_sandbox()

    assert entorno.imagen == imagen
    assert imagen in RECETAS
    # Todas las imágenes comparten las carpetas del sandbox.
    assert (entorno.dir_tests, entorno.dir_salida) == ("/work/tests", "/out")


def test_imagen_desconocida_da_error_claro(tmp_path):
    with pytest.raises(ValueError, match="no es una imagen base"):
        preparar_imagen(tmp_path, cliente=MagicMock(), imagen="otra:imagen")
    with pytest.raises(ValueError, match="no es una imagen base"):
        construir_imagen_base(MagicMock(), imagen="otra:imagen")


# --- Imagen base -----------------------------------------------------------------------


def test_construye_la_imagen_de_node_solo_con_su_dockerfile():
    docker = DockerSimulado()

    assert construir_imagen_base(docker.cliente, imagen=IMAGEN_NODE) == IMAGEN_NODE

    [construccion] = docker.construcciones
    assert construccion["tag"] == IMAGEN_NODE
    assert construccion["archivos"] == ["Dockerfile"]
    assert construccion["dockerfile"] == (
        CARPETA_SANDBOX / "Dockerfile.node"
    ).read_text(encoding="utf-8")


def test_construye_la_imagen_de_java_con_su_proyecto_de_calentamiento():
    docker = DockerSimulado()

    assert construir_imagen_base(docker.cliente, imagen=IMAGEN_JAVA) == IMAGEN_JAVA

    [construccion] = docker.construcciones
    assert construccion["tag"] == IMAGEN_JAVA
    assert "Dockerfile" in construccion["archivos"]
    assert "java/calentamiento/pom.xml" in construccion["archivos"]
    assert "java/resolver.gradle" in construccion["archivos"]
    assert "FROM eclipse-temurin:" in construccion["dockerfile"]


def test_la_imagen_de_python_no_cambia():
    docker = DockerSimulado()

    construir_imagen_base(docker.cliente)

    [construccion] = docker.construcciones
    assert construccion["tag"] == IMAGEN_BASE
    assert construccion["archivos"] == ["Dockerfile"]


def test_asegurar_imagen_construye_la_base_solo_si_falta(proyecto_node):
    docker = DockerSimulado()

    etiqueta = asegurar_imagen(proyecto_node, IMAGEN_NODE, docker.cliente)

    assert [c["tag"] for c in docker.construcciones] == [IMAGEN_NODE, etiqueta]
    # Segunda corrida: ya existen las dos imágenes, no se construye nada.
    assert asegurar_imagen(proyecto_node, IMAGEN_NODE, docker.cliente) == etiqueta
    assert len(docker.construcciones) == 2


def test_un_proyecto_de_python_no_construye_las_imagenes_de_otros_lenguajes(tmp_path):
    (tmp_path / "requirements.txt").write_bytes(b"six\n")
    docker = DockerSimulado(IMAGEN_BASE)

    asegurar_imagen(tmp_path, IMAGEN_BASE, docker.cliente)

    etiquetas = [c["tag"] for c in docker.construcciones]
    assert etiquetas == [etiqueta_para_requirements(b"six\n")]


# --- Imagen derivada de Node -----------------------------------------------------------


def test_node_con_lockfile_usa_npm_ci_y_solo_copia_las_dependencias(proyecto_node):
    docker = DockerSimulado(IMAGEN_NODE)

    etiqueta = preparar_imagen(proyecto_node, docker.cliente, imagen=IMAGEN_NODE)

    [construccion] = docker.construcciones
    assert etiqueta.startswith("qagent-sandbox:node-")
    assert construccion["tag"] == etiqueta
    assert construccion["archivos"] == [
        "Dockerfile",
        "package-lock.json",
        "package.json",
    ]
    dockerfile = construccion["dockerfile"]
    assert dockerfile.startswith(f"FROM {IMAGEN_NODE}\n")
    assert "npm ci" in dockerfile
    # Las dependencias quedan fuera de /work/proyecto, que se monta al ejecutar.
    assert "/work/node_modules" in dockerfile
    assert dockerfile.rstrip().endswith("USER sandbox")


def test_node_sin_lockfile_usa_npm_install(proyecto_node):
    (proyecto_node / "package-lock.json").unlink()
    docker = DockerSimulado(IMAGEN_NODE)

    preparar_imagen(proyecto_node, docker.cliente, imagen=IMAGEN_NODE)

    [construccion] = docker.construcciones
    assert construccion["archivos"] == ["Dockerfile", "package.json"]
    assert "npm install --no-package-lock" in construccion["dockerfile"]
    assert "npm ci" not in construccion["dockerfile"]


def test_node_sin_package_json_usa_la_imagen_base(tmp_path):
    docker = DockerSimulado(IMAGEN_NODE)

    assert preparar_imagen(tmp_path, docker.cliente, imagen=IMAGEN_NODE) == IMAGEN_NODE
    assert docker.construcciones == []


def test_node_reutiliza_la_derivada_si_no_cambian_las_dependencias(proyecto_node):
    docker = DockerSimulado(IMAGEN_NODE)
    primera = preparar_imagen(proyecto_node, docker.cliente, imagen=IMAGEN_NODE)

    (proyecto_node / "src" / "suma.js").write_text("// el código cambia\n")
    assert preparar_imagen(proyecto_node, docker.cliente, imagen=IMAGEN_NODE) == primera
    assert len(docker.construcciones) == 1

    (proyecto_node / "package-lock.json").write_bytes(LOCK_VACIO + b"\n")
    segunda = preparar_imagen(proyecto_node, docker.cliente, imagen=IMAGEN_NODE)
    assert segunda != primera
    assert len(docker.construcciones) == 2


def test_node_sin_imagen_base_pide_construirla(proyecto_node):
    docker = DockerSimulado()

    with pytest.raises(ImagenNoEncontrada, match=re.escape(IMAGEN_NODE)):
        preparar_imagen(proyecto_node, docker.cliente, imagen=IMAGEN_NODE)


# --- Imagen derivada de Java -----------------------------------------------------------


def test_maven_usa_dependency_go_offline(proyecto_maven):
    docker = DockerSimulado(IMAGEN_JAVA)

    etiqueta = preparar_imagen(proyecto_maven, docker.cliente, imagen=IMAGEN_JAVA)

    [construccion] = docker.construcciones
    assert etiqueta.startswith("qagent-sandbox:java-")
    assert construccion["archivos"] == ["Dockerfile", "pom.xml"]
    assert construccion["dockerfile"].startswith(f"FROM {IMAGEN_JAVA}\n")
    assert "mvn dependency:go-offline" in construccion["dockerfile"]


def test_maven_reutiliza_la_derivada_si_no_cambia_el_pom(proyecto_maven):
    docker = DockerSimulado(IMAGEN_JAVA)
    primera = preparar_imagen(proyecto_maven, docker.cliente, imagen=IMAGEN_JAVA)

    assert (
        preparar_imagen(proyecto_maven, docker.cliente, imagen=IMAGEN_JAVA) == primera
    )
    (proyecto_maven / "pom.xml").write_text("<project><x/></project>\n")
    assert (
        preparar_imagen(proyecto_maven, docker.cliente, imagen=IMAGEN_JAVA) != primera
    )
    assert len(docker.construcciones) == 2


def test_gradle_resuelve_las_dependencias_en_una_cache_de_solo_lectura(tmp_path):
    (tmp_path / "gradle").mkdir()
    (tmp_path / "build.gradle.kts").write_text("plugins { java }\n")
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "demo"\n')
    (tmp_path / "gradle" / "libs.versions.toml").write_text("[versions]\n")
    (tmp_path / "Suma.java").write_text("class Suma {}\n")
    docker = DockerSimulado(IMAGEN_JAVA)

    etiqueta = preparar_imagen(tmp_path, docker.cliente, imagen=IMAGEN_JAVA)

    [construccion] = docker.construcciones
    assert etiqueta.startswith("qagent-sandbox:java-")
    assert construccion["archivos"] == [
        "Dockerfile",
        "build.gradle.kts",
        "gradle/libs.versions.toml",
        "settings.gradle.kts",
    ]
    dockerfile = construccion["dockerfile"]
    assert "COPY gradle/libs.versions.toml " in dockerfile
    assert "resolver.gradle" in dockerfile
    assert "/opt/qagent/gradle-ro" in dockerfile


def test_con_pom_y_gradle_se_prefiere_maven(proyecto_maven):
    (proyecto_maven / "build.gradle").write_text("apply plugin: 'java'\n")
    docker = DockerSimulado(IMAGEN_JAVA)

    preparar_imagen(proyecto_maven, docker.cliente, imagen=IMAGEN_JAVA)

    assert docker.construcciones[0]["archivos"] == ["Dockerfile", "pom.xml"]


# --- Etiquetas y limpieza --------------------------------------------------------------


def test_la_etiqueta_de_python_sigue_siendo_la_de_siempre():
    """Las imágenes `req-` ya construidas se siguen reutilizando."""
    contenido = b"fastapi==0.115.0\n"
    assert etiqueta_para_dependencias(
        "req-", {"requirements.txt": contenido}
    ) == etiqueta_para_requirements(contenido)


def test_la_etiqueta_depende_del_nombre_y_del_contenido():
    a = etiqueta_para_dependencias("java-", {"pom.xml": b"x"})
    assert a == etiqueta_para_dependencias("java-", {"pom.xml": b"x"})
    assert a != etiqueta_para_dependencias("java-", {"build.gradle": b"x"})
    assert a != etiqueta_para_dependencias("java-", {"pom.xml": b"y"})


def test_la_limpieza_conoce_las_derivadas_de_todas_las_recetas():
    assert {r.prefijo for r in RECETAS.values()} <= set(PREFIJOS_DERIVADAS)
    assert _es_imagen_req("qagent-sandbox:node-0123456789ab")
    assert _es_imagen_req("qagent-sandbox:java-0123456789ab")
    for base in RECETAS:
        assert not _es_imagen_req(base)


# --- Avance en el Monitor --------------------------------------------------------------


def test_avisa_el_avance_de_la_construccion_de_node(proyecto_node):
    docker = DockerSimulado(IMAGEN_NODE)
    docker.cliente.api.build.return_value = iter(
        [
            {"stream": "Step 3/5 : RUN cd /tmp/qagent-deps && npm ci\n"},
            {"stream": "added 57 packages in 3s\n"},
            {"stream": "Successfully tagged qagent-sandbox:node-x\n"},
        ]
    )
    avisos: list[str] = []

    preparar_imagen(proyecto_node, docker.cliente, avisos.append, IMAGEN_NODE)

    assert avisos == [
        modulo_imagen.AVISO_CONSTRUYENDO,
        aviso_dependencias("package.json"),
        "Instalados 57 paquetes",
        modulo_imagen.AVISO_GUARDANDO,
        modulo_imagen.AVISO_LISTO,
    ]


def test_un_error_de_construccion_nombra_el_archivo_de_dependencias(proyecto_maven):
    docker = DockerSimulado(IMAGEN_JAVA)
    docker.cliente.api.build.return_value = iter(
        [{"stream": "[ERROR] Could not resolve dependencies\n"}, {"error": "falló"}]
    )

    with pytest.raises(modulo_imagen.ErrorConstruccionImagen, match="pom.xml") as error:
        preparar_imagen(proyecto_maven, docker.cliente, lambda _: None, IMAGEN_JAVA)

    assert "Could not resolve dependencies" in error.value.log


@pytest.mark.parametrize(
    "linea, esperado",
    [
        ("added 1 package in 1s", "Instalados 1 paquete"),
        ("[INFO] BUILD SUCCESS", modulo_imagen.AVISO_DEPENDENCIAS_LISTAS),
        ("BUILD SUCCESSFUL in 12s", modulo_imagen.AVISO_DEPENDENCIAS_LISTAS),
        ("[INFO] Scanning for projects...", None),
    ],
)
def test_describe_las_lineas_de_npm_maven_y_gradle(linea, esperado):
    assert describir_linea(linea) == esperado


# --- Ejecución con los límites del lenguaje --------------------------------------------


def test_la_ejecucion_usa_la_imagen_y_los_limites_del_lenguaje(tmp_path):
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    contenedor = MagicMock()
    contenedor.wait.return_value = {"StatusCode": 0}
    contenedor.logs.return_value = b""
    contenedor.attrs = {"State": {"OOMKilled": False}}
    cliente = MagicMock()
    cliente.info.return_value = {"NCPU": 2}
    cliente.containers.run.return_value = contenedor
    limites = LimitesSandbox(cpus=4.0, memoria="4g", timeout_s=300)

    resultado = ejecutar_en_sandbox(
        IMAGEN_JAVA, ["mvn", "-o", "test"], proyecto, tests, limites, cliente=cliente
    )

    argumentos = cliente.containers.run.call_args
    assert argumentos.args[0] == IMAGEN_JAVA
    assert argumentos.kwargs["network_mode"] == "none"
    assert argumentos.kwargs["read_only"] is True
    assert argumentos.kwargs["mem_limit"] == "4g"
    # Los CPU se recortan a los de Docker igual que en Python.
    assert argumentos.kwargs["nano_cpus"] == 2_000_000_000
    assert resultado.limites == LimitesSandbox(cpus=2.0, memoria="4g", timeout_s=300)
    contenedor.remove.assert_called_once()


# --- Empaquetado y versiones fijas -----------------------------------------------------


def test_los_dockerfile_y_recursos_viajan_en_el_paquete():
    datos = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    patrones = datos["tool"]["setuptools"]["package-data"]["qagent.sandbox"]
    for receta in RECETAS.values():
        assert receta.dockerfile.is_file()
        assert any(receta.dockerfile.match(p) for p in patrones), receta.dockerfile
    assert "java/**/*" in patrones


@pytest.mark.parametrize("nombre", ["Dockerfile.node", "Dockerfile.java"])
def test_las_herramientas_tienen_versiones_fijas(nombre):
    texto = (CARPETA_SANDBOX / nombre).read_text(encoding="utf-8")
    [desde] = re.findall(r"^FROM\s+(\S+)", texto, flags=re.MULTILINE)
    assert re.search(r":\d+\.\d+\.\d+", desde), desde
    assert "latest" not in texto
    # Cada paquete de npm lleva su versión exacta.
    for paquete in re.findall(r"^\s+(@?[a-z][\w./-]*@\S+)", texto, flags=re.MULTILINE):
        assert re.search(r"@\d+\.\d+\.\d+$", paquete), paquete

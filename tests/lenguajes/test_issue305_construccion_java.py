"""Comprobación Java previa a IA con Docker simulado, sin compilar en el host."""

from unittest.mock import MagicMock

import pytest

from qagent.lenguajes.java_construccion import (
    comando_construccion,
    comprobar_construccion,
)
from qagent.sandbox.modelos import LimitesSandbox, ResultadoSandbox

MODULO = "src/main/java/ejemplo/Banco.java"
IMAGEN = "sha256:" + "a" * 64
POM = """<project><modelVersion>4.0.0</modelVersion><groupId>ejemplo</groupId>
<artifactId>banco</artifactId><version>1</version><properties>
<maven.compiler.release>21</maven.compiler.release></properties></project>"""
FUENTE = (
    "package ejemplo; public class Banco { public static int f(int x) {return x;} }"
)


@pytest.fixture
def proyecto(tmp_path):
    (tmp_path / "pom.xml").write_text(POM, encoding="utf-8")
    fuente = tmp_path / MODULO
    fuente.parent.mkdir(parents=True)
    fuente.write_text(FUENTE, encoding="utf-8")
    return tmp_path


@pytest.fixture
def cliente():
    docker = MagicMock()
    docker.images.get.return_value.id = IMAGEN
    docker.info.return_value = {
        "OSType": "linux",
        "Architecture": "x86_64",
        "NCPU": 4,
        "ServerVersion": "29.7.2",
    }
    return docker


def comprobar(proyecto, cliente, ejecutor, **opciones):
    return comprobar_construccion(
        proyecto,
        "qagent-sandbox:java",
        [MODULO],
        LimitesSandbox(),
        cliente=cliente,
        ejecutor=ejecutor,
        **opciones,
    )


def test_compila_offline_en_imagen_inmutable_y_sin_tests(proyecto, cliente):
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }

    def ejecutar(imagen, comando, copia, pruebas, limites, **opciones):
        assert imagen == IMAGEN
        assert (
            copia != proyecto and (copia / MODULO).read_text(encoding="utf-8") == FUENTE
        )
        assert not list(pruebas.iterdir())
        assert comando[-2:] == ["clean", "compile"]
        assert "--offline" in comando and "-Dmaven.test.skip=true" in comando
        assert "-DskipTests=true" in comando and "-DskipITs=true" in comando
        assert opciones["entorno"]["MAVEN_SKIP_RC"] == "true"
        return ResultadoSandbox(0, "BUILD SUCCESS", "")

    resultado = comprobar(proyecto, cliente, ejecutar)
    assert resultado.aprobado and not resultado.reutilizado
    assert resultado.imagen_id == IMAGEN and len(resultado.huella) == 64
    assert all((proyecto / p).read_bytes() == b for p, b in originales.items())


def test_aprobacion_se_reutiliza_sin_ejecutar_maven(proyecto, cliente):
    ejecutar = MagicMock(return_value=ResultadoSandbox(0, "BUILD SUCCESS", ""))
    primero = comprobar(proyecto, cliente, ejecutar)
    segundo = comprobar(proyecto, cliente, ejecutar)
    assert primero.huella == segundo.huella and segundo.reutilizado and segundo.aprobado
    assert ejecutar.call_count == 1


@pytest.mark.parametrize(
    "archivo,contenido",
    [
        (MODULO, FUENTE.replace("return x", "return x+1")),
        ("pom.xml", POM.replace("<version>1", "<version>2")),
        ("src/main/resources/config.properties", "modo=nuevo"),
        (".mvn/maven.config", "-Drevision=2"),
        ("generar.py", "# input de un plugin Maven"),
        ("src/main/java/target/Otra.java", "package target; class Otra {}"),
    ],
)
def test_cambios_de_inputs_invalidan_reutilizacion(
    proyecto, cliente, archivo, contenido
):
    ejecutar = MagicMock(return_value=ResultadoSandbox(0, "BUILD SUCCESS", ""))
    primero = comprobar(proyecto, cliente, ejecutar)
    destino = proyecto / archivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    segundo = comprobar(proyecto, cliente, ejecutar)
    assert segundo.aprobado and not segundo.reutilizado
    assert primero.huella != segundo.huella and ejecutar.call_count == 2


def test_cambio_de_imagen_invalida_aunque_la_etiqueta_no_cambie(proyecto, cliente):
    ejecutar = MagicMock(return_value=ResultadoSandbox(0, "BUILD SUCCESS", ""))
    primero = comprobar(proyecto, cliente, ejecutar)
    cliente.images.get.return_value.id = "sha256:" + "b" * 64
    segundo = comprobar(proyecto, cliente, ejecutar)
    assert primero.huella != segundo.huella and not segundo.reutilizado
    assert ejecutar.call_count == 2


def test_datos_qagent_secretos_y_target_no_son_inputs(proyecto, cliente):
    ejecutar = MagicMock(return_value=ResultadoSandbox(0, "BUILD SUCCESS", ""))
    primero = comprobar(proyecto, cliente, ejecutar)
    for nombre in (".env", "target/Clase.class", ".qagent/runs/ruido.json"):
        archivo = proyecto / nombre
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text("dato-no-pertinente", encoding="utf-8")
    segundo = comprobar(proyecto, cliente, ejecutar)
    assert segundo.reutilizado and segundo.huella == primero.huella
    assert ejecutar.call_count == 1


def test_cache_corrupto_no_autoriza_ia(proyecto, cliente):
    ejecutar = MagicMock(return_value=ResultadoSandbox(0, "BUILD SUCCESS", ""))
    primero = comprobar(proyecto, cliente, ejecutar)
    archivo = proyecto / ".qagent/cache/construccion_java" / (primero.huella + ".json")
    archivo.write_text('{"estado":"aprobado"}', encoding="utf-8")
    assert not comprobar(proyecto, cliente, ejecutar).reutilizado
    assert ejecutar.call_count == 2


@pytest.mark.parametrize(
    "log,categoria",
    [
        (
            "[ERROR] Cannot access central in offline mode; artifact has not been downloaded",
            "dependencias",
        ),
        ("[ERROR] PluginResolutionException", "dependencias"),
        (
            "[ERROR] error: release version 26 not supported",
            "incompatibilidad_herramienta",
        ),
        ("[ERROR] UnsupportedClassVersionError", "incompatibilidad_herramienta"),
        (
            "[ERROR] java.lang.NoSuchFieldError: javac.api",
            "incompatibilidad_herramienta",
        ),
        ("[ERROR] Non-parseable POM", "configuracion"),
        ("[ERROR] COMPILATION FAILURE: cannot find symbol", "compilacion"),
        ("[ERROR] fallo sin causa demostrable", "tecnico"),
    ],
)
def test_clasifica_y_no_reutiliza_fallos(proyecto, cliente, log, categoria):
    ejecutar = MagicMock(return_value=ResultadoSandbox(1, log, ""))
    primero = comprobar(proyecto, cliente, ejecutar)
    segundo = comprobar(proyecto, cliente, ejecutar)
    assert not primero.aprobado and primero.categoria == categoria
    assert not segundo.reutilizado and ejecutar.call_count == 2
    assert not list((proyecto / ".qagent/cache/construccion_java").glob("*.json"))


@pytest.mark.parametrize(
    "salida,categoria",
    [
        (ResultadoSandbox(137, "", "", timed_out=True), "timeout"),
        (ResultadoSandbox(137, "", "", cancelado=True), "cancelado"),
        (ResultadoSandbox(137, "", "", oom_killed=True), "recursos"),
    ],
)
def test_interrupciones_no_se_guardan_como_aprobadas(
    proyecto, cliente, salida, categoria
):
    resultado = comprobar(proyecto, cliente, lambda *a, **k: salida)
    assert not resultado.aprobado and resultado.categoria == categoria
    assert not list((proyecto / ".qagent/cache/construccion_java").glob("*.json"))


def test_cancelado_antes_no_consulta_docker(proyecto, cliente):
    ejecutar = MagicMock()
    resultado = comprobar(proyecto, cliente, ejecutar, cancelado=lambda: True)
    assert resultado.estado == "cancelado"
    ejecutar.assert_not_called()
    cliente.images.get.assert_not_called()


def test_log_no_conserva_credenciales(proyecto, cliente):
    secreto = 'api_key="secreto de prueba" https://usuario:clave@repo.test/maven?token=123\n{"secret": "valor privado"}'
    resultado = comprobar(
        proyecto, cliente, lambda *a, **k: ResultadoSandbox(1, secreto, "")
    )
    assert all(
        s not in resultado.log
        for s in ("secreto de prueba", "usuario:clave", "token=123", "valor privado")
    )
    assert "repo.test/maven" in resultado.log and "[oculto]" in resultado.log


def test_reactor_compila_seleccion_y_dependencias_sin_elegir_tests(tmp_path):
    (tmp_path / "pom.xml").write_text(
        POM.replace(
            "</project>",
            "<packaging>pom</packaging><modules><module>lib</module><module>app</module></modules></project>",
        ),
        encoding="utf-8",
    )
    for nombre in ("lib", "app"):
        carpeta = tmp_path / nombre
        carpeta.mkdir()
        (carpeta / "pom.xml").write_text(
            POM.replace("<artifactId>banco", "<artifactId>" + nombre), encoding="utf-8"
        )
    comando = comando_construccion(tmp_path, ["app/" + MODULO])
    assert comando[comando.index("-pl") + 1] == "app" and "-am" in comando
    assert comando[-2:] == ["clean", "compile"]
    with pytest.raises(ValueError):
        comando_construccion(tmp_path, ["fuera/" + MODULO])


@pytest.mark.parametrize(
    "campo,valor", [("memoria", "1g"), ("cpus", 1.0), ("timeout_s", 30)]
)
def test_cambiar_limites_invalida_aprobacion(proyecto, cliente, campo, valor):
    ejecutar = MagicMock(return_value=ResultadoSandbox(0, "BUILD SUCCESS", ""))
    primero = comprobar(proyecto, cliente, ejecutar)
    limites = LimitesSandbox(**{campo: valor})
    segundo = comprobar_construccion(
        proyecto,
        "misma-etiqueta",
        [MODULO],
        limites,
        cliente=cliente,
        ejecutor=ejecutar,
    )
    assert primero.huella != segundo.huella and not segundo.reutilizado
    assert ejecutar.call_count == 2


def test_cambio_de_entorno_docker_invalida_aprobacion(proyecto, cliente):
    ejecutar = MagicMock(return_value=ResultadoSandbox(0, "BUILD SUCCESS", ""))
    primero = comprobar(proyecto, cliente, ejecutar)
    cliente.info.return_value["Architecture"] = "aarch64"
    segundo = comprobar(proyecto, cliente, ejecutar)
    assert primero.huella != segundo.huella and ejecutar.call_count == 2


def test_cancelacion_antes_de_guardar_no_deja_cache_aprobado(proyecto, cliente):
    estado = {"cancelado": False}

    def ejecutar(*a, **k):
        estado["cancelado"] = True
        return ResultadoSandbox(0, "BUILD SUCCESS", "")

    resultado = comprobar(
        proyecto, cliente, ejecutar, cancelado=lambda: estado["cancelado"]
    )
    assert resultado.estado == "cancelado" and not resultado.aprobado
    assert not list((proyecto / ".qagent/cache/construccion_java").glob("*.json"))


def test_warning_sobre_source_no_oculta_error_de_compilacion(proyecto, cliente):
    log = "[WARNING] source option 21\n[ERROR] COMPILATION FAILURE: cannot access Banco; cannot find symbol"
    resultado = comprobar(
        proyecto, cliente, lambda *a, **k: ResultadoSandbox(1, log, "")
    )
    assert resultado.categoria == "compilacion"

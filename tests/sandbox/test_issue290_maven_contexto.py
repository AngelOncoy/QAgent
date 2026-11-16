"""Preparación Maven de distintos proyectos: inspección estática, sin Docker."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import BuildError

from qagent.sandbox import IMAGEN_JAVA
from qagent.sandbox.imagen import etiqueta_para_dependencias, preparar_imagen
from qagent.sandbox.maven import explicar_fallo, inspeccionar
from qagent.sandbox.modelos import ErrorConstruccionImagen


def pom(raiz: Path, nombre: str = "pom.xml", contenido: str = "") -> Path:
    """Escribe un descriptor ficticio; nunca se ejecutan fuentes del proyecto."""
    ruta = raiz / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">'
        + contenido
        + "</project>",
        encoding="utf-8",
    )
    return ruta


def test_maven_recoge_modulos_padre_y_perfiles_sin_fuentes_ni_claves(tmp_path):
    """Conserva el árbol de POM incluso cuando un módulo depende del padre local."""
    pom(
        tmp_path,
        contenido="<properties><maven.compiler.release>21</maven.compiler.release></properties><modules><module>core</module><module>api</module></modules><profiles><profile><id>extra</id><modules><module>extra</module></modules></profile></profiles>",
    )
    padre = "<parent><groupId>demo</groupId><artifactId>raiz</artifactId><version>1</version></parent>"
    for modulo in ("core", "api", "extra"):
        pom(tmp_path, f"{modulo}/pom.xml", padre)
    (tmp_path / ".env").write_text("FALSO=solo_fixture")
    (tmp_path / "settings.xml").write_text("<settings/>")
    (tmp_path / "Fuente.java").write_text("class Fuente {}")
    resultado = inspeccionar(tmp_path)
    assert set(resultado.archivos) == {
        "pom.xml",
        "core/pom.xml",
        "api/pom.xml",
        "extra/pom.xml",
    }
    assert resultado.descriptores[0].perfiles == ("extra",)
    assert all(d.java == "21" for d in resultado.descriptores)
    print("Maven: raíz, padre local y 3 módulos; sin fuentes, settings ni .env")


def test_padre_remoto_no_se_confunde_con_archivo_local_obligatorio(tmp_path):
    """Un padre remoto con relativePath vacío se conserva para resolver en Docker."""
    ruta = pom(
        tmp_path,
        contenido="<parent><groupId>org.example</groupId><artifactId>padre</artifactId><version>1</version><relativePath/></parent>",
    )
    resultado = inspeccionar(tmp_path)
    assert resultado.archivos == {"pom.xml": ruta.read_bytes()}
    assert resultado.descriptores[0].padre == "org.example:padre:1"


def test_padre_local_se_incluye_aunque_no_sea_un_modulo(tmp_path):
    """Recopila el padre por relativePath y hereda sus propiedades estáticas."""
    pom(
        tmp_path,
        contenido="<parent><relativePath>padre/pom.xml</relativePath></parent>",
    )
    pom(
        tmp_path,
        "padre/pom.xml",
        "<properties><java.version>17</java.version></properties>",
    )
    proyecto = inspeccionar(tmp_path)
    assert set(proyecto.archivos) == {"pom.xml", "padre/pom.xml"}
    assert {d.java for d in proyecto.descriptores} == {"17"}


@pytest.mark.parametrize("modulo", ["../fuera", "/fuera", "${desconocida}"])
def test_modulos_externos_o_no_resueltos_no_entran_al_contexto(tmp_path, modulo):
    """Rechaza rutas no contenidas y propiedades sin respaldo antes de Docker."""
    pom(tmp_path, contenido=f"<modules><module>{modulo}</module></modules>")
    with pytest.raises(ErrorConstruccionImagen):
        inspeccionar(tmp_path)


def test_modulo_ausente_da_error_de_preparacion(tmp_path):
    pom(tmp_path, contenido="<modules><module>ausente</module></modules>")
    with pytest.raises(ErrorConstruccionImagen, match="descriptor Maven"):
        inspeccionar(tmp_path)


def test_ciclo_de_padres_no_provoca_recursion_infinita(tmp_path):
    pom(
        tmp_path,
        contenido="<parent><relativePath>padre/pom.xml</relativePath></parent>",
    )
    pom(
        tmp_path,
        "padre/pom.xml",
        "<parent><relativePath>../pom.xml</relativePath></parent>",
    )
    with pytest.raises(ErrorConstruccionImagen, match="ciclo"):
        inspeccionar(tmp_path)


@pytest.mark.parametrize(
    "contenido",
    [
        "<!DOCTYPE project [<!ENTITY x 'valor'>]><project>&x;</project>",
        "<no-es-project/>",
        "<project>",
    ],
)
def test_xml_no_valido_no_se_entrega_a_docker(tmp_path, contenido):
    (tmp_path / "pom.xml").write_text(contenido)
    with pytest.raises(ErrorConstruccionImagen):
        inspeccionar(tmp_path)


def test_huella_cambia_si_cambia_un_pom_hijo(tmp_path):
    pom(tmp_path, contenido="<modules><module>api</module></modules>")
    ruta = pom(tmp_path, "api/pom.xml", "<version>1</version>")
    archivos = inspeccionar(tmp_path).archivos
    primera = etiqueta_para_dependencias("java-", archivos)
    assert primera == etiqueta_para_dependencias(
        "java-", inspeccionar(tmp_path).archivos
    )
    ruta.write_text(ruta.read_text().replace("<version>1", "<version>2"))
    assert primera != etiqueta_para_dependencias(
        "java-", inspeccionar(tmp_path).archivos
    )


@pytest.mark.parametrize(
    "log, esperado",
    [
        ("[ERROR] Non-resolvable parent POM for demo", "POM padre"),
        ("[ERROR] Could not find artifact org.demo:falta:jar:1", "dependencia"),
        ("[ERROR] Failed to transfer: status code: 401", "autorización"),
        ("[ERROR] Unknown host repo.example", "conectar"),
        ("[ERROR] release version 26 not supported", "versión Java"),
        ("The command returned a non-zero code: 1", "consulte el detalle técnico"),
    ],
)
def test_diagnostico_distingue_causas_sin_inventarlas(log, esperado):
    """No atribuye un código de salida genérico a una dependencia específica."""
    assert esperado in explicar_fallo({}, log)


def test_diagnostico_no_muestra_usuario_password_ni_token():
    log = "[ERROR] Could not find artifact from https://usuario:clave@repo.example/maven?token=valor token=secreto"
    mensaje = explicar_fallo({}, log)
    assert "repo.example/maven" in mensaje
    assert all(
        secreto not in mensaje for secreto in ("usuario", "clave", "valor", "secreto")
    )


@pytest.mark.parametrize(
    "secreto",
    [
        "<password>ficticio</password>",
        "<url>https://usuario:ficticio@repo.example</url>",
        "<url>https://repo.example/maven?token=ficticio</url>",
    ],
)
def test_pom_con_credenciales_incrustadas_no_se_copia(tmp_path, secreto):
    """Rechaza el descriptor sin incluir su secreto en el mensaje público."""
    pom(tmp_path, contenido=secreto)
    with pytest.raises(
        ErrorConstruccionImagen, match="credenciales incrustadas"
    ) as error:
        inspeccionar(tmp_path)
    assert "ficticio" not in str(error.value)


def test_error_docker_expone_la_causa_maven_y_conserva_log(tmp_path, monkeypatch):
    """El fallo genérico de RUN se reemplaza por el diagnóstico para la aplicación."""
    pom(tmp_path)
    cliente = MagicMock()
    from docker.errors import ImageNotFound

    cliente.images.get.side_effect = [MagicMock(), ImageNotFound("derivada")]
    log = "[ERROR] Non-resolvable parent POM for org.demo:api:1"
    cliente.images.build.side_effect = BuildError(
        "The command returned a non-zero code: 1", [{"stream": log}]
    )
    monkeypatch.setattr(
        "qagent.sandbox.imagen.espacio.verificar_espacio_libre", lambda: None
    )
    with pytest.raises(ErrorConstruccionImagen, match="POM padre") as error:
        preparar_imagen(tmp_path, cliente, imagen=IMAGEN_JAVA)
    assert log in error.value.log

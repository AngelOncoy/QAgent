"""Comando y preparación estática de una prueba Java para el sandbox (#182).

No ejecuta procesos en el anfitrión. preparar_java recibe exclusivamente la
copia desechable; Maven se invoca después dentro del sandbox común sin red.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from qagent.lenguajes.treesitter import obtener_parser
from qagent.sandbox.informe_pytest import LIMITE_XML, JUnitInvalido
from qagent.sandbox.maven import inspeccionar, separar_fuente
from qagent.sandbox.modelos import ErrorConstruccionImagen, ErrorPreparacionSandbox

POM = ".qagent-junit.xml"
TESTS = ".qagent-junit-tests"
TARGET = ".qagent-junit-target"
REACTOR = ".qagent-maven"
MARCA = "QAGENT_JAVA_ETAPA="
_NS = "http://maven.apache.org/POM/4.0.0"
_BASE = "/work/proyecto/"
_RECETA = Path(__file__).resolve().parents[1] / "sandbox/java/calentamiento/pom.xml"


def comando_java(modulo: str) -> list[str]:
    """Devuelve etapas Maven offline separadas, con JaCoCo aun si JUnit falla.

    Requiere preparar_java en la copia antes de ejecutarse. Las rutas del comando
    son constantes; modulo se valida y no se interpola en un script de shell.
    La etapa final y el código de salida permiten distinguir errores técnicos.
    """
    separar_fuente(modulo)
    ruta = PurePosixPath(modulo.replace("\\", "/"))
    receta = _xml(_RECETA.read_text(encoding="utf-8"))
    version = receta.findtext("{*}properties/{*}jacoco.version")
    if not version or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", version):
        raise ValueError("La receta Java no declara una versión JaCoCo válida.")
    script = f"""set -u
cd /work/proyecto || exit $?
case "$1" in
  src/main/java/*) seleccion=. ;;
  *) seleccion="${{1%/src/main/java/*}}" ;;
esac
pom=/work/proyecto/{POM}
reactor=false
if [ -f /work/proyecto/{REACTOR}/pom.xml ]; then
  pom=/work/proyecto/{REACTOR}/pom.xml
  reactor=true
fi
ejecutar_maven() {{
  mvn --offline --batch-mode --no-transfer-progress -Dmaven.repo.local=/opt/qagent/m2 -f "$pom" "$@"
}}
ejecutar_compilacion() {{
  if [ "$reactor" = true ]; then
    ejecutar_maven -pl "$2" -am "$1"
  else
    ejecutar_maven "$1"
  fi
}}
echo '{MARCA}proyecto'
if [ ! -f "/work/proyecto/$1" ]; then
  echo 'La fuente Java seleccionada no existe en la copia' >&2
  exit 1
fi
if [ "$reactor" = true ]; then
  ejecutar_compilacion compile "$seleccion" || exit $?
else
  ejecutar_maven compile || exit $?
fi
echo '{MARCA}prueba'
if [ "$reactor" = true ]; then
  ejecutar_compilacion test-compile "$seleccion" || exit $?
else
  ejecutar_maven test-compile || exit $?
fi
echo '{MARCA}ejecucion'
if [ "$reactor" = true ]; then
  ejecutar_maven -pl "$seleccion" -am test-compile org.jacoco:jacoco-maven-plugin:{version}:prepare-agent surefire:test
else
  ejecutar_maven org.jacoco:jacoco-maven-plugin:{version}:prepare-agent surefire:test
fi
estado_test=$?
echo '{MARCA}cobertura'
if [ "$reactor" = true ]; then
  ejecutar_maven -pl "$seleccion" org.jacoco:jacoco-maven-plugin:{version}:report
else
  ejecutar_maven org.jacoco:jacoco-maven-plugin:{version}:report
fi
estado_cobertura=$?
if [ "$estado_cobertura" -ne 0 ]; then exit "$estado_cobertura"; fi
if [ ! -f /out/jacoco-report/jacoco.xml ]; then
  echo 'JaCoCo no produjo el informe XML esperado' >&2
  exit 1
fi
cp /out/jacoco-report/jacoco.xml /out/jacoco.xml || exit $?
echo '{MARCA}ejecucion'
exit "$estado_test"
"""
    return ["sh", "-c", script, "qagent-java", ruta.as_posix()]


def preparar_java(copia: Path, pruebas: Path, modulo: str | None = None) -> None:
    """Dispone una prueba en su módulo y un reactor aislado sin tocar los POM originales.

    Sin módulo mantiene la entrada histórica de un solo proyecto. Los proyectos
    con agregación requieren la selección explícita para no adivinar el módulo.
    El modelo Maven se resuelve después dentro de Docker, nunca en el anfitrión.
    """
    try:
        proyecto = inspeccionar(copia)
        carpeta = separar_fuente(modulo)[0] if modulo else ""
        if carpeta and carpeta + "/pom.xml" not in proyecto.archivos:
            raise ValueError(
                "La fuente seleccionada no pertenece a un módulo Maven declarado."
            )
        if (copia / REACTOR).exists() or (copia / REACTOR).is_symlink():
            raise ValueError("El proyecto contiene una ruta reservada de QAgent Maven.")
        hay_modulos = any(d.modulos for d in proyecto.descriptores)
        versiones = {d.ruta: d.java for d in proyecto.descriptores}
        if not hay_modulos and not carpeta:
            _preparar_un_modulo(copia, pruebas, version_java=versiones.get("pom.xml"))
            return
        if modulo is None:
            raise ValueError(
                "La ejecución multimódulo requiere una fuente seleccionada explícitamente."
            )
        # Los POM se espejan; fuentes y recursos apuntan a la copia original.
        # Solo el objetivo recibe pruebas. Los demás módulos compilan con una
        # carpeta de tests vacía, nunca con los src/test del repositorio.
        for nombre in proyecto.archivos:
            relativa = Path(nombre).parent
            seleccionada = relativa.as_posix() == (carpeta or ".")
            base = _BASE + (
                relativa.as_posix() + "/" if relativa.as_posix() != "." else ""
            )
            _preparar_un_modulo(
                copia / relativa,
                pruebas,
                base=base,
                objetivo=seleccionada,
                version_java=versiones.get(nombre),
            )
            temporal = copia / relativa / POM
            arbol = _xml(temporal.read_text(encoding="utf-8"))
            ns = f"{{{_NS}}}" if arbol.tag.startswith("{") else ""
            build = _hijo(arbol, ns + "build")
            _hijo(build, ns + "sourceDirectory").text = base + "src/main/java"
            recursos = build.find(ns + "resources")
            if recursos is None:
                recursos = ET.SubElement(build, ns + "resources")
                recurso = ET.SubElement(recursos, ns + "resource")
                ET.SubElement(recurso, ns + "directory").text = (
                    base + "src/main/resources"
                )
            else:
                for recurso in recursos:
                    directorio = recurso.find(ns + "directory")
                    if (
                        directorio is not None
                        and directorio.text
                        and not directorio.text.startswith("/")
                    ):
                        directorio.text = base + directorio.text
            destino = copia / REACTOR / nombre
            destino.parent.mkdir(parents=True, exist_ok=True)
            if ns:
                for nodo in arbol.iter():
                    nodo.tag = nodo.tag.removeprefix(ns)
                arbol.set("xmlns", _NS)
            destino.write_bytes(
                _serializar_pom(arbol, temporal.read_text(encoding="utf-8"))
            )
        opciones = copia / ".mvn/maven.config"
        if opciones.is_file():
            destino = copia / REACTOR / ".mvn/maven.config"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(opciones.read_bytes())
    except (ErrorConstruccionImagen, OSError, ValueError, ET.ParseError) as error:
        raise ErrorPreparacionSandbox(
            f"{MARCA}proyecto\nNo se pudo preparar Java: {error}"
        ) from error


def _preparar_un_modulo(
    copia: Path,
    pruebas: Path,
    *,
    base: str = _BASE,
    objetivo: bool = True,
    version_java: str | None = None,
) -> None:
    """Crea POM, fuente de prueba y salidas reservadas en la copia, sin compilar.

    Conserva el POM y src/test originales y la herencia declarada. Añade las
    herramientas de la receta del equipo y mantiene las dependencias del proyecto.
    Solo el objetivo incluye una fuente recibida; no copia pruebas preexistentes.
    Errores de preparación se marcan como proyecto o prueba para su clasificación.
    """
    etapa = "proyecto"
    try:
        for nombre in (POM, TESTS, TARGET):
            ruta = copia / nombre
            if ruta.exists() or ruta.is_symlink():
                raise ValueError(
                    "El proyecto contiene una ruta reservada de QAgent Java."
                )
        original = _xml(_leer(copia / "pom.xml", copia))
        if original.tag not in {"project", f"{{{_NS}}}project"}:
            raise ValueError("Se requiere un pom.xml Maven válido.")
        padre = original.find("{*}parent")
        if padre is not None and not all(
            padre.findtext("{*}" + c) for c in ("groupId", "artifactId", "version")
        ):
            raise ValueError(
                "El POM padre debe declarar groupId, artifactId y version."
            )
        receta = _xml(_RECETA.read_text(encoding="utf-8"))
        preparado = copy.deepcopy(original)
        ns = f"{{{_NS}}}" if preparado.tag.startswith("{") else ""
        build = _hijo(preparado, ns + "build")
        for nombre, valor in (
            ("directory", base + TARGET),
            ("outputDirectory", base + TARGET + "/classes"),
            ("testOutputDirectory", base + TARGET + "/test-classes"),
            ("testSourceDirectory", base + TESTS),
        ):
            _hijo(build, ns + nombre).text = valor
        plugins = _hijo(build, ns + "plugins")
        propiedades = {
            p.tag.rsplit("}", 1)[-1]: p.text for p in receta.find("{*}properties")
        }
        propiedades_proyecto = _hijo(preparado, ns + "properties")
        if (
            padre is None
            and propiedades_proyecto.find(ns + "maven.compiler.release") is None
            and propiedades_proyecto.find(ns + "maven.compiler.source") is None
        ):
            _hijo(propiedades_proyecto, ns + "maven.compiler.release").text = (
                version_java
                or propiedades_proyecto.findtext(ns + "java.version")
                or propiedades["maven.compiler.release"]
            )
        for nombre in (
            "maven-resources-plugin",
            "maven-compiler-plugin",
            "maven-surefire-plugin",
            "jacoco-maven-plugin",
        ):
            ejemplo = next(
                p
                for p in receta.findall("{*}build/{*}plugins/{*}plugin")
                if p.findtext("{*}artifactId") == nombre
            )
            existentes = [p for p in plugins if p.findtext("{*}artifactId") == nombre]
            if len(existentes) > 1:
                raise ValueError("El POM contiene plugins de pruebas duplicados.")
            plugin = (
                existentes[0] if existentes else ET.SubElement(plugins, ns + "plugin")
            )
            for campo in ("groupId", "artifactId", "version"):
                valor = ejemplo.findtext("{*}" + campo)
                if valor and valor.startswith("${"):
                    valor = propiedades[valor[2:-1]]
                _hijo(plugin, ns + campo).text = valor
            if nombre == "maven-surefire-plugin":
                config = _hijo(plugin, ns + "configuration")
                opciones_jvm = config.findtext(ns + "argLine") or ""
                for campo in (
                    "includes",
                    "excludes",
                    "skip",
                    "skipTests",
                    "test",
                    "reportsDirectory",
                    "testFailureIgnore",
                    "failIfNoTests",
                    "forkCount",
                    "argLine",
                ):
                    for previo in list(config.findall(ns + campo)):
                        config.remove(previo)
                for campo, valor in (
                    ("reportsDirectory", "/out/junit-raw"),
                    ("testFailureIgnore", "false"),
                    ("failIfNoTests", "true" if objetivo else "false"),
                    ("skip", "false"),
                    ("skipTests", "false"),
                    ("forkCount", "1"),
                    ("argLine", ("@{qagentJacocoArgLine} " + opciones_jvm).strip()),
                ):
                    _hijo(config, ns + campo).text = valor
            elif nombre == "jacoco-maven-plugin":
                # Se usan goals explícitos: no reutilizar agentes/executions del usuario.
                for campo in ("configuration", "executions"):
                    for previo in list(plugin.findall(ns + campo)):
                        plugin.remove(previo)
                config = _hijo(plugin, ns + "configuration")
                for campo, valor in (
                    ("destFile", "/out/jacoco.exec"),
                    ("dataFile", "/out/jacoco.exec"),
                    ("outputDirectory", "/out/jacoco-report"),
                    ("append", "false"),
                    ("propertyName", "qagentJacocoArgLine"),
                ):
                    _hijo(config, ns + campo).text = valor
        _dependencia_junit(preparado, ns, propiedades["junit.version"])
        etapa = "prueba"
        candidatas = (
            [p for p in pruebas.rglob("*") if p.is_file() and p.suffix == ".java"]
            if objetivo
            else []
        )
        if objetivo and len(candidatas) != 1:
            raise ValueError(
                "Se requiere exactamente una fuente .java de prueba generada."
            )
        selector = None
        if objetivo:
            codigo = _leer(candidatas[0], pruebas)
            relativa, selector = _identidad_prueba(codigo)
            destino = copia / TESTS / relativa
            destino.parent.mkdir(parents=True)
            destino.write_text(codigo, encoding="utf-8", newline="")
        surefire = next(
            p for p in plugins if p.findtext("{*}artifactId") == "maven-surefire-plugin"
        )
        if selector:
            _hijo(_hijo(surefire, ns + "configuration"), ns + "test").text = selector
        if ns:
            for nodo in preparado.iter():
                nodo.tag = nodo.tag.removeprefix(ns)
            preparado.set("xmlns", _NS)
        with (copia / POM).open("xb") as archivo:
            archivo.write(_serializar_pom(preparado, _leer(copia / "pom.xml", copia)))
    except (OSError, UnicodeError, ValueError, ET.ParseError) as error:
        raise ErrorPreparacionSandbox(
            f"{MARCA}{etapa}\nNo se pudo preparar Java: {error}"
        ) from error


def _serializar_pom(pom: ET.Element, original: str) -> bytes:
    """Conserva avisos del prólogo del descriptor del que deriva el POM auxiliar.

    ElementTree descarta comentarios anteriores a la raíz. No se inventa una
    licencia ni se omiten controles Maven: se conservan los avisos originales.
    """
    prologo = re.match(
        r"\s*(?:<\?xml[^?]*\?>\s*)?((?:<!--.*?-->\s*)*)", original, re.DOTALL
    )
    comentarios = prologo.group(1) if prologo else ""
    return (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        + comentarios.encode("utf-8")
        + ET.tostring(pom, encoding="utf-8")
    )


def _dependencia_junit(pom: ET.Element, ns: str, version: str) -> None:
    """Añade JUnit 5 solo si falta, respetando la versión existente del proyecto."""
    dependencias = _hijo(pom, ns + "dependencies")
    junit = [d for d in dependencias if d.findtext("{*}groupId") == "org.junit.jupiter"]
    if any(d.findtext("{*}artifactId") == "junit-jupiter" for d in junit):
        return
    dependencia = ET.SubElement(dependencias, ns + "dependency")
    for campo, valor in (
        ("groupId", "org.junit.jupiter"),
        ("artifactId", "junit-jupiter"),
        ("scope", "test"),
    ):
        _hijo(dependencia, ns + campo).text = valor
    if junit:
        existente = junit[0].findtext("{*}version")
        if existente:
            _hijo(dependencia, ns + "version").text = existente
    else:
        _hijo(dependencia, ns + "version").text = version


def _identidad_prueba(codigo: str) -> tuple[Path, str]:
    """Obtiene paquete y clase del AST; no confunde una sintaxis inválida con el proyecto.

    Si la prueba no permite reconocer una identidad, se guarda con un nombre
    auxiliar: test-compile reportará el error en la etapa prueba. No repara su código.
    """
    raiz = obtener_parser("java").parse(codigo.encode("utf-8")).root_node
    paquete = next(
        (
            n.named_children[-1].text.decode("utf-8")
            for n in raiz.named_children
            if n.type == "package_declaration"
        ),
        "",
    )
    tipos = [
        n
        for n in raiz.named_children
        if n.type in {"class_declaration", "record_declaration", "enum_declaration"}
    ]
    nombre = tipos[0].child_by_field_name("name") if len(tipos) == 1 else None
    clase = nombre.text.decode("utf-8") if nombre is not None else "QAgentGeneratedTest"
    segmentos = [*paquete.split("."), clase] if paquete else [clase]
    if not all(s.replace("$", "_").isidentifier() for s in segmentos):
        segmentos = ["QAgentGeneratedTest"]
    return Path(*segmentos[:-1], segmentos[-1] + ".java"), ".".join(segmentos)


def recoger_junit(dir_salida: Path) -> str | None:
    """Agrega los informes Surefire de esta ejecución, con límites y sin enlaces externos."""
    from qagent.lenguajes.java_junit import interpretar_junit_java

    raiz = ET.Element("testsuites")
    total = 0
    try:
        carpeta = dir_salida / "junit-raw"
        if carpeta.is_symlink() or not carpeta.resolve().is_relative_to(
            dir_salida.resolve()
        ):
            return None
        informes = sorted(carpeta.glob("TEST-*.xml"))
        if not informes or len(informes) > 50:
            return None
        for archivo in informes:
            texto = _leer(archivo, dir_salida)
            total += len(texto.encode("utf-8"))
            if total > LIMITE_XML:
                return None
            interpretar_junit_java(texto)
            suite = ET.fromstring(texto)
            if suite.tag == "testsuite":
                raiz.append(suite)
            else:
                raiz.extend(list(suite))
        agregado = ET.tostring(raiz, encoding="unicode")
        interpretar_junit_java(agregado)
        return agregado
    except (OSError, UnicodeError, ValueError, ET.ParseError, JUnitInvalido):
        return None


def _leer(archivo: Path, raiz: Path) -> str:
    """Lee UTF-8 acotado dentro de una raíz, sin seguir fuentes externas."""
    if archivo.is_symlink() or not archivo.resolve().is_relative_to(raiz.resolve()):
        raise ValueError("No se admite una ruta externa al sandbox.")
    with archivo.open("rb") as entrada:
        datos = entrada.read(LIMITE_XML + 1)
    if len(datos) > LIMITE_XML:
        raise ValueError("El archivo supera el tamaño permitido.")
    return datos.decode("utf-8-sig")


def _xml(texto: str) -> ET.Element:
    """Lee POM sin resolver DTD ni entidades externas."""
    if "<!DOCTYPE" in texto or "<!ENTITY" in texto:
        raise ValueError("No se admiten DTD ni entidades en el POM.")
    return ET.fromstring(texto)


def _hijo(padre: ET.Element, nombre: str) -> ET.Element:
    """Obtiene o crea un hijo sin sobrescribir elementos ajenos al ajuste requerido."""
    encontrado = padre.find(nombre)
    return encontrado if encontrado is not None else ET.SubElement(padre, nombre)

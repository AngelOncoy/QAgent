"""Inspección estática y diagnóstico Maven del sandbox (#290).

No ejecuta Maven ni fuentes. Reúne únicamente descriptores del proyecto y evita
seguir enlaces o rutas externas al construir la imagen de dependencias.
"""

from __future__ import annotations

import copy
import posixpath
import re
import shlex
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from qagent.sandbox.modelos import ErrorConstruccionImagen

_MAX_POM = 1024 * 1024
_MAX_ARCHIVOS = 1000
_MAX_TOTAL = 16 * 1024 * 1024
_PROPIEDAD = re.compile(r"\$\{([^}]+)\}")


def separar_fuente(modulo: str) -> tuple[str, str]:
    """Separa módulo Maven y fuente estándar sin aceptar recorridos ni opciones CLI."""
    normal = modulo.replace("\\", "/")
    ruta = PurePosixPath(normal)
    partes = normal.split("/")
    if ruta.is_absolute() or any(p in {"", ".", ".."} for p in partes) or ":" in normal:
        raise ValueError("Se requiere una fuente Maven relativa dentro del proyecto.")
    indices = [
        i
        for i in range(len(partes) - 3)
        if partes[i : i + 3] == ["src", "main", "java"]
    ]
    if len(indices) != 1 or ruta.suffix != ".java":
        raise ValueError(
            "Se requiere src/main/java/paquete/Clase.java dentro de un módulo Maven."
        )
    indice = indices[0]
    if any(
        not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", p) for p in partes[:indice]
    ):
        raise ValueError("El nombre del módulo Maven contiene caracteres no admitidos.")
    if not all(
        p.replace("$", "_").isidentifier()
        for p in (*partes[indice + 3 : -1], ruta.stem)
    ):
        raise ValueError(
            "La ruta de la fuente Java no contiene identificadores válidos."
        )
    return "/".join(partes[:indice]), "/".join(partes[indice:])


@dataclass(frozen=True)
class DescriptorMaven:
    """POM relativo, padre declarado, módulos y requisitos Java sin ejecutar código."""

    ruta: str
    padre: str | None
    modulos: tuple[str, ...]
    perfiles: tuple[str, ...]
    java: str | None


@dataclass(frozen=True)
class ProyectoMaven:
    """Descriptores recopilados y su contenido original para la huella de imagen."""

    archivos: dict[str, bytes]
    descriptores: tuple[DescriptorMaven, ...]


def _fallo(texto: str) -> ErrorConstruccionImagen:
    return ErrorConstruccionImagen(f"No se pudo preparar pom.xml: {texto}")


def _ruta_interna(raiz: Path, candidata: Path) -> Path:
    """Rechaza enlaces y rutas fuera del proyecto antes de abrir un descriptor."""
    ruta = candidata.resolve()
    if not ruta.is_relative_to(raiz):
        raise _fallo("un padre o módulo apunta fuera de la carpeta del proyecto.")
    original = candidata.absolute()
    for parte in (original, *original.parents):
        if parte.is_symlink():
            raise _fallo("un descriptor Maven utiliza un enlace simbólico.")
        if parte == raiz:
            break
    return ruta


def _leer_pom(ruta: Path) -> tuple[bytes, ET.Element]:
    try:
        if ruta.stat().st_size > _MAX_POM:
            raise _fallo("un descriptor supera el límite de 1 MiB.")
        contenido = ruta.read_bytes()
        # El parser de stdlib permite entidades internas: no aceptarlas aquí.
        texto = contenido.decode("utf-8-sig")
        if "<!DOCTYPE" in texto.upper() or "<!ENTITY" in texto.upper():
            raise _fallo("no se admiten declaraciones DTD ni entidades en el POM.")
        if (
            re.search(r"https?://[^\s/<]+:[^\s/]+@", texto)
            or re.search(
                r"[?&](?:amp;)?(?:token|password|api[_-]?key|access[_-]?token|signature)=[^\s<&]+",
                texto,
                re.IGNORECASE,
            )
            or re.search(
                r"<(?:\w+:)?(?:password|passphrase|privateKey|token|secret)\b",
                texto,
                re.IGNORECASE,
            )
        ):
            raise _fallo(
                "el descriptor contiene credenciales incrustadas; no se copiará al contexto Docker."
            )
        arbol = ET.fromstring(contenido)
        if arbol.tag not in {"project", "{http://maven.apache.org/POM/4.0.0}project"}:
            raise _fallo("la raíz del descriptor no es project.")
        return contenido, arbol
    except (OSError, UnicodeError, ET.ParseError) as error:
        raise _fallo(
            f"no se pudo leer un descriptor Maven ({type(error).__name__})."
        ) from error


def _texto(nodo: ET.Element, nombre: str) -> str | None:
    valor = nodo.findtext(nombre)
    return valor.strip() if valor and valor.strip() else None


def _resolver(valor: str, propiedades: dict[str, str]) -> str:
    for _ in range(12):
        nuevo = _PROPIEDAD.sub(lambda m: propiedades.get(m[1], m[0]), valor)
        if nuevo == valor:
            return valor
        valor = nuevo
    return valor


def inspeccionar(raiz: Path) -> ProyectoMaven:
    """Recopila POM raíz, padres locales y módulos; no descarga ni ejecuta nada.

    Conserva bytes y rutas para invalidar la caché ante cualquier cambio. Incluye
    módulos declarados en perfiles, pero no activa esos perfiles por su cuenta.
    Los padres remotos se dejan a Maven; no se inventan sus propiedades.
    """
    raiz = raiz.resolve()
    archivos: dict[str, bytes] = {}
    descriptores: dict[str, DescriptorMaven] = {}
    visitando: set[Path] = set()
    propiedades_por_ruta: dict[Path, dict[str, str]] = {}
    opciones = _opciones_maven(raiz)
    propiedades_cli = dict(o[2:].split("=", 1) for o in opciones if o.startswith("-D"))
    perfiles_cli = {
        p.lstrip("+?")
        for o in opciones
        if o.startswith("-P")
        for p in o[2:].split(",")
        if not p.startswith(("!", "-"))
    }

    def visitar(candidata: Path) -> dict[str, str]:
        ruta = _ruta_interna(raiz, candidata)
        if ruta in visitando:
            raise _fallo("se detectó un ciclo entre padres Maven.")
        if len(visitando) >= 100:
            raise _fallo("la cadena de padres Maven supera el límite de inspección.")
        if ruta in propiedades_por_ruta:
            return propiedades_por_ruta[ruta]
        if len(archivos) >= _MAX_ARCHIVOS:
            raise _fallo("el proyecto supera el límite de descriptores Maven.")
        contenido, pom = _leer_pom(ruta)
        relativa = ruta.relative_to(raiz).as_posix()
        archivos[relativa] = contenido
        if sum(map(len, archivos.values())) > _MAX_TOTAL:
            raise _fallo("los descriptores Maven superan el límite total de 16 MiB.")
        visitando.add(ruta)
        ns = "{http://maven.apache.org/POM/4.0.0}" if pom.tag.startswith("{") else ""
        props: dict[str, str] = {}
        padre = pom.find(ns + "parent")
        identidad_padre = None
        if padre is not None:
            identidad_padre = ":".join(
                _texto(padre, ns + campo) or "?"
                for campo in ("groupId", "artifactId", "version")
            )
            referencia = padre.find(ns + "relativePath")
            local = (
                "../pom.xml" if referencia is None else (referencia.text or "").strip()
            )
            if local:
                candidato = ruta.parent / local
                if candidato.is_dir():
                    candidato /= "pom.xml"
                # Maven permite un padre remoto sin archivo en relativePath.
                if candidato.exists():
                    props.update(visitar(candidato))
                elif referencia is not None:
                    _ruta_interna(raiz, candidato)
                    # relativePath es una preferencia local, no prohíbe resolver
                    # el padre por sus coordenadas desde un repositorio remoto.
        nodo_props = pom.find(ns + "properties")
        if nodo_props is not None:
            props.update(
                {h.tag.rsplit("}", 1)[-1]: (h.text or "").strip() for h in nodo_props}
            )
        perfiles = tuple(pom.findall(ns + "profiles/" + ns + "profile"))
        for perfil in perfiles:
            identificador = _texto(perfil, ns + "id") or ""
            por_defecto = (
                _texto(perfil, ns + "activation/" + ns + "activeByDefault") == "true"
            )
            if identificador in perfiles_cli or (por_defecto and not perfiles_cli):
                nodo_props = perfil.find(ns + "properties")
                if nodo_props is not None:
                    props.update(
                        {
                            h.tag.rsplit("}", 1)[-1]: (h.text or "").strip()
                            for h in nodo_props
                        }
                    )
        props.update(propiedades_cli)
        java = next(
            (
                props[c]
                for c in (
                    "maven.compiler.release",
                    "maven.compiler.source",
                    "java.version",
                )
                if props.get(c)
            ),
            None,
        )
        modulos = [*_modulos(pom, ns)]
        for perfil in perfiles:
            modulos.extend(_modulos(perfil, ns))
        resueltos = tuple(dict.fromkeys(_resolver(m, props) for m in modulos))
        if any("${" in m for m in resueltos):
            raise _fallo(f"un módulo de {relativa} usa propiedades no resueltas.")
        descriptores[relativa] = DescriptorMaven(
            relativa,
            identidad_padre,
            resueltos,
            tuple(_texto(p, ns + "id") or "" for p in perfiles),
            _resolver(java, props) if java else None,
        )
        visitando.remove(ruta)
        propiedades_por_ruta[ruta] = props
        for modulo in resueltos:
            visitar(ruta.parent / modulo / "pom.xml")
        return props

    visitar(raiz / "pom.xml")
    return ProyectoMaven(archivos, tuple(descriptores.values()))


def _modulos(pom: ET.Element, ns: str) -> list[str]:
    return [
        m.text.strip()
        for m in pom.findall(ns + "modules/" + ns + "module")
        if m.text and m.text.strip()
    ]


def recolectar_archivos(raiz: Path) -> dict[str, bytes]:
    """Entrega solo los POM necesarios; nunca copia fuentes, settings ni .env."""
    diagnostico = comprobar_preparacion(raiz)
    if not diagnostico["compatible"]:
        raise ErrorConstruccionImagen(str(diagnostico["mensaje"]))
    archivos = inspeccionar(raiz).archivos
    opciones = raiz / ".mvn/maven.config"
    if opciones.is_file():
        archivos[".mvn/maven.config"] = opciones.read_bytes()
    return archivos


def _opciones_maven(raiz: Path) -> tuple[str, ...]:
    """Permite perfiles y propiedades de versión; rechaza opciones ajenas explícitamente."""
    archivo = raiz / ".mvn/maven.config"
    if not archivo.exists():
        return ()
    _ruta_interna(raiz.resolve(), archivo)
    if archivo.stat().st_size > 16_384:
        raise _fallo(".mvn/maven.config supera el límite de inspección.")
    opciones = shlex.split(archivo.read_text(encoding="utf-8-sig"), comments=True)
    for opcion in opciones:
        if re.fullmatch(r"-P[!+?A-Za-z0-9_.!,\-]+", opcion):
            continue
        if re.fullmatch(r"-D(?:revision|changelist|sha1)=[A-Za-z0-9_.\-]*", opcion):
            continue
        raise _fallo(
            ".mvn/maven.config solo admite perfiles -P y propiedades revision/changelist/sha1; no se ignorarán otras opciones."
        )
    return tuple(opciones)


def comprobar_preparacion(raiz: Path) -> dict[str, object]:
    """Diagnóstico estático antes de IA: compatible no significa ya compilado.

    Las versiones heredadas de un padre remoto se resuelven en Docker. No se
    afirma compatibilidad con todas las bibliotecas ni se descarga nada aquí.
    """
    try:
        if not (raiz / "pom.xml").is_file():
            raise _fallo(
                "se requiere un pom.xml raíz; Gradle no está admitido por el ejecutor Java."
            )
        proyecto = inspeccionar(raiz)
        _opciones_maven(raiz)
        for nombre in (".mvn/extensions.xml", ".mvn/jvm.config"):
            archivo = raiz / nombre
            if archivo.exists() and archivo.stat().st_size:
                raise _fallo(
                    f"{nombre} requiere opciones de construcción que todavía no están admitidas; no se ignorará su configuración."
                )
        contexto = dict(proyecto.archivos)
        opciones = raiz / ".mvn/maven.config"
        if opciones.is_file():
            contexto[".mvn/maven.config"] = opciones.read_bytes()
        contexto_dependencias(contexto)
        for descriptor in proyecto.descriptores:
            if descriptor.java and re.fullmatch(r"(?:1\.)?[0-9]+", descriptor.java):
                version = int(descriptor.java.removeprefix("1."))
                if version > 25 or version < 8:
                    raise _fallo(
                        f"{descriptor.ruta} requiere Java {descriptor.java}, fuera del rango de compilación admitido por este sandbox JDK 25."
                    )
            arbol = ET.fromstring(proyecto.archivos[descriptor.ruta])
            padre = arbol.find("{*}parent")
            if padre is not None and not all(
                _texto(padre, "{*}" + c) for c in ("groupId", "artifactId", "version")
            ):
                raise _fallo(
                    f"el padre de {descriptor.ruta} debe declarar groupId, artifactId y version."
                )
            if arbol.find(".//{*}systemPath") is not None:
                raise _fallo(
                    "las dependencias systemPath requieren archivos externos y aún no están admitidas."
                )
            fuente = arbol.findtext("{*}build/{*}sourceDirectory")
            if fuente and fuente not in {
                "src/main/java",
                "${project.basedir}/src/main/java",
                "${basedir}/src/main/java",
            }:
                raise _fallo(
                    f"{descriptor.ruta} declara un sourceDirectory no estándar que este ejecutor aún no admite."
                )
        return {
            "compatible": True,
            "mensaje": f"Estructura Maven admitida: {len(proyecto.descriptores)} POM; JDK 25. Las dependencias se comprobarán al preparar Docker. Antes de usar IA se comprobará la construcción sin ejecutar tests existentes.",
            "descriptores": [
                {
                    "ruta": d.ruta,
                    "padre": d.padre,
                    "modulos": list(d.modulos),
                    "perfiles": list(d.perfiles),
                    "java": d.java,
                }
                for d in proyecto.descriptores
            ],
        }
    except (ErrorConstruccionImagen, OSError, ValueError) as error:
        return {"compatible": False, "mensaje": str(error), "descriptores": []}


def contexto_dependencias(archivos: dict[str, bytes]) -> dict[str, bytes]:
    """Omite dependencias entre módulos solo en la copia para descargar terceros.

    Un artefacto del reactor todavía no existe en un repositorio remoto. Sus
    dependencias externas sí se recorren desde su propio POM. El ejecutor conserva
    las dependencias internas originales y las compila dentro del reactor offline.
    La huella se calcula con los bytes originales, antes de esta transformación.
    """
    arboles = {
        n: ET.fromstring(c) for n, c in archivos.items() if n.endswith("pom.xml")
    }
    modelos = _modelos_contexto(arboles, archivos)
    identidades = {
        tuple(
            props.get("project." + c, "") for c in ("groupId", "artifactId", "version")
        )
        for props, _ in modelos.values()
    }
    resultado = dict(archivos)
    for nombre, original in arboles.items():
        pom = copy.deepcopy(original)
        props, gestionadas = modelos[nombre]
        cambiado = False
        for dependencias in pom.findall(".//{*}dependencies"):
            for d in list(dependencias):
                grupo = _resolver(_texto(d, "{*}groupId") or "", props)
                artefacto = _resolver(_texto(d, "{*}artifactId") or "", props)
                version = _resolver(
                    _texto(d, "{*}version") or gestionadas.get((grupo, artefacto), ""),
                    props,
                )
                if (grupo, artefacto, version) not in identidades:
                    continue
                if _texto(d, "{*}type") == "pom" and _texto(d, "{*}scope") == "import":
                    raise _fallo(
                        "un BOM interno requiere instalación previa; esta configuración aún no está admitida."
                    )
                if (
                    _texto(d, "{*}classifier")
                    or (_texto(d, "{*}type") or "jar") != "jar"
                ):
                    raise _fallo(
                        "una dependencia interna con classifier o tipo distinto de jar requiere artefactos adicionales aún no admitidos."
                    )
                dependencias.remove(d)
                cambiado = True
        if cambiado:
            ns = "{http://maven.apache.org/POM/4.0.0}"
            if pom.tag.startswith(ns):
                for nodo in pom.iter():
                    nodo.tag = nodo.tag.removeprefix(ns)
                pom.set("xmlns", ns[1:-1])
            resultado[nombre] = ET.tostring(pom, encoding="utf-8", xml_declaration=True)
    return resultado


def _modelos_contexto(
    arboles: dict[str, ET.Element], archivos: dict[str, bytes]
) -> dict[str, tuple[dict[str, str], dict[tuple[str, str], str]]]:
    """Resuelve coordenadas locales acotadas; Maven resuelve el modelo completo en Docker.

    Solo permite omitir un artefacto si coinciden grupo, nombre y versión. No
    confunde otra versión publicada con el módulo que se compilará localmente.
    """
    opciones = shlex.split(
        archivos.get(".mvn/maven.config", b"").decode("utf-8-sig"), comments=True
    )
    cli = dict(o[2:].split("=", 1) for o in opciones if o.startswith("-D"))
    perfiles = {
        p.lstrip("+?")
        for o in opciones
        if o.startswith("-P")
        for p in o[2:].split(",")
        if not p.startswith(("!", "-"))
    }
    modelos: dict[str, tuple[dict[str, str], dict[tuple[str, str], str]]] = {}
    visitando: set[str] = set()

    def resolver(nombre: str) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
        if nombre in modelos:
            return modelos[nombre]
        if nombre in visitando or len(visitando) >= 100:
            raise _fallo("ciclo o profundidad excesiva entre padres Maven.")
        visitando.add(nombre)
        pom = arboles[nombre]
        padre = pom.find("{*}parent")
        props: dict[str, str] = {}
        gestionadas: dict[tuple[str, str], str] = {}
        if padre is not None:
            referencia = padre.find("{*}relativePath")
            relativa = (
                "../pom.xml" if referencia is None else (referencia.text or "").strip()
            )
            ruta = posixpath.normpath(
                posixpath.join(posixpath.dirname(nombre), relativa)
            )
            if ruta not in arboles and ruta + "/pom.xml" in arboles:
                ruta += "/pom.xml"
            if ruta in arboles and relativa:
                heredadas, versiones = resolver(ruta)
                props.update(heredadas)
                gestionadas.update(versiones)
            for campo in ("groupId", "artifactId", "version"):
                props["project.parent." + campo] = _texto(padre, "{*}" + campo) or ""
        nodo = pom.find("{*}properties")
        if nodo is not None:
            props.update({n.tag.rsplit("}", 1)[-1]: n.text or "" for n in nodo})
        activos = []
        for perfil in pom.findall("{*}profiles/{*}profile"):
            if _texto(perfil, "{*}id") in perfiles or (
                not perfiles
                and _texto(perfil, "{*}activation/{*}activeByDefault") == "true"
            ):
                activos.append(perfil)
                nodo = perfil.find("{*}properties")
                if nodo is not None:
                    props.update({n.tag.rsplit("}", 1)[-1]: n.text or "" for n in nodo})
        props.update(cli)
        for campo in ("groupId", "artifactId", "version"):
            valor = _texto(pom, "{*}" + campo) or props.get(
                "project.parent." + campo, ""
            )
            props["project." + campo] = _resolver(valor, props)
            props["pom." + campo] = props["project." + campo]
        declaraciones = [
            d
            for fuente in (pom, *activos)
            for d in fuente.findall(
                "{*}dependencyManagement/{*}dependencies/{*}dependency"
            )
        ]
        for dependencia in declaraciones:
            grupo = _resolver(_texto(dependencia, "{*}groupId") or "", props)
            artefacto = _resolver(_texto(dependencia, "{*}artifactId") or "", props)
            gestionadas[grupo, artefacto] = _resolver(
                _texto(dependencia, "{*}version") or "", props
            )
        modelos[nombre] = (props, gestionadas)
        visitando.remove(nombre)
        return modelos[nombre]

    for nombre in arboles:
        resolver(nombre)
    return modelos


def _sanear(texto: str) -> str:
    """Oculta credenciales en URLs y parámetros antes de mostrar el diagnóstico."""

    def url_segura(m: re.Match[str]) -> str:
        try:
            url = urlsplit(m[0])
            host = url.netloc.rsplit("@", 1)[-1]
            return urlunsplit((url.scheme, host, url.path, "", ""))
        except ValueError:
            return "[URL omitida]"

    texto = re.sub(r"https?://[^\s<>]+", url_segura, texto)
    return re.sub(
        r"(?i)((?:password|token|secret|authorization|api[_-]?key)\s*[=:]\s*)\S+",
        r"\1[oculto]",
        texto,
    )


def explicar_fallo(archivos: dict[str, bytes], log: str) -> str:
    """Clasifica el error original Maven; un código de salida solo no inventa causa."""
    limpio = _sanear(re.sub(r"\x1b\[[0-9;]*m", "", log))
    errores = [linea.strip() for linea in limpio.splitlines() if "[ERROR]" in linea]
    detalle = next(
        (
            e
            for e in errores
            if "To see the full stack trace" not in e and "Re-run Maven" not in e
        ),
        "",
    )
    texto = limpio.lower()
    if any(
        s in texto
        for s in (
            "status code: 401",
            "status code: 403",
            "unauthorized",
            "authentication failed",
        )
    ):
        causa = "El repositorio Maven requiere autorización o denegó el acceso."
    elif any(
        s in texto
        for s in (
            "unknown host",
            "unknownhost",
            "could not resolve host",
            "connection timed out",
            "pkix path building failed",
        )
    ):
        causa = "No se pudo conectar de forma segura al repositorio Maven."
    elif "non-resolvable parent pom" in texto or "non-resolvable import pom" in texto:
        causa = "Maven no pudo resolver el POM padre o un BOM del proyecto."
    elif "child module" in texto and "does not exist" in texto:
        causa = "Falta un módulo declarado en el POM del proyecto."
    elif any(
        s in texto
        for s in (
            "could not find artifact",
            "could not resolve dependencies",
            "pluginresolutionexception",
        )
    ):
        causa = "Maven no pudo resolver una dependencia o un plugin del proyecto."
    elif "release version" in texto and "not supported" in texto:
        causa = "La versión Java requerida no es compatible con el JDK del sandbox."
    else:
        causa = "Maven no pudo preparar las dependencias de pom.xml; consulte el detalle técnico."
    return (
        "Preparación de pom.xml: "
        + causa
        + (" Causa Maven: " + detalle[:900] if detalle else "")
    )

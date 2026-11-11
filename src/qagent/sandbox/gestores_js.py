"""Dependencias de proyectos JavaScript/TypeScript: npm, pnpm, yarn y workspaces (#272).

La imagen derivada de Node instala las dependencias del proyecto con su propio gestor de
paquetes, sin ejecutar nunca los scripts del proyecto (`postinstall`, `prepare`...):
eso sería código del usuario corriendo con red al construir la imagen.

Este módulo es puro (no usa Docker):

- `detectar_gestor` decide npm, pnpm o yarn (classic o berry) por el lockfile y el campo
  `packageManager` del `package.json`.
- `recolectar_archivos` junta lo que hace falta copiar al contexto de build: lockfile,
  configuración del gestor sin credenciales, el `package.json` de cada workspace y los
  parches que declara el proyecto. Nunca copia código fuente.
- `dockerfile_js` arma el Dockerfile derivado. Todo valor que sale del proyecto y entra
  en el Dockerfile (la versión del gestor) se valida antes con una expresión regular.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

#: Versión fija de corepack (Node 25+ ya no lo trae): instala pnpm y yarn.
VERSION_COREPACK = "0.36.0"

#: Versión de cada gestor si el proyecto no declara `packageManager`.
VERSIONES_POR_DEFECTO = {
    "pnpm": "10.33.4",
    "yarn-classic": "1.22.22",
    "yarn-berry": "4.18.1",
}

#: Script que sube las dependencias de los workspaces a /work/node_modules.
SCRIPT_REUBICAR = Path(__file__).parent / "node" / "reubicar_workspaces.cjs"
#: Nombre del script dentro del contexto de build (no choca con archivos del proyecto).
NOMBRE_SCRIPT = ".qagent-reubicar-workspaces.cjs"

#: Marca del log cuando el lockfile no coincide y se instala sin bloquear versiones.
MARCA_SIN_LOCKFILE = "QAGENT: lockfile desactualizado"

#: Límites para no recorrer ni copiar sin fin en repositorios enormes.
MAXIMO_WORKSPACES = 300
MAXIMO_PARCHES = 200
_MAXIMO_BYTES_PARCHE = 2 * 1024 * 1024

_CARPETAS_IGNORADAS = {"node_modules", ".git", ".qagent", "dist", "build", "coverage"}

#: `pnpm@10.33.4`, `yarn@4.1.0+sha512.abc...` (corepack acepta el hash de integridad).
_PACKAGE_MANAGER = re.compile(
    r"^(npm|pnpm|yarn)@(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)"
    r"(\+sha(?:1|224|256|384|512)\.[0-9a-f]+)?$"
)

#: Líneas de configuración con credenciales: no entran a la imagen.
_CLAVE_SECRETA = re.compile(
    r"(_auth|_authtoken|_password|password|username|token|certfile|keyfile|"
    r"npmauthtoken|npmauthident|npmalwaysauth)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GestorJS:
    """Gestor de paquetes de un proyecto JS.

    Atributos:
        nombre: `npm`, `pnpm`, `yarn-classic` o `yarn-berry`.
        version: versión que se instala con corepack (`None` para npm: el de la imagen).
        lockfile: lockfile presente en el proyecto, o `None`.
    """

    nombre: str
    version: str | None
    lockfile: str | None

    @property
    def descripcion(self) -> str:
        """Texto para personas: «pnpm 10.33.4 y pnpm-lock.yaml», «npm sin lockfile»."""
        nombre = {"yarn-classic": "yarn", "yarn-berry": "yarn"}.get(
            self.nombre, self.nombre
        )
        version = f" {self.version.split('+')[0]}" if self.version else ""
        origen = f"y {self.lockfile}" if self.lockfile else "sin lockfile"
        return f"{nombre}{version} {origen}"


_LOCKFILES = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
    ("npm-shrinkwrap.json", "npm"),
)


def leer_package_json(contenido: bytes | None) -> dict:
    """`package.json` como diccionario; `{}` si falta o no es JSON válido."""
    if not contenido:
        return {}
    try:
        datos = json.loads(contenido.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _package_manager(paquete: Mapping) -> tuple[str, str] | None:
    """(`pnpm`, `10.33.4+sha512...`) del campo `packageManager`, si es válido."""
    valor = paquete.get("packageManager")
    if not isinstance(valor, str):
        return None
    coincidencia = _PACKAGE_MANAGER.match(valor.strip())
    if coincidencia is None:
        return None
    return coincidencia.group(1), coincidencia.group(2) + (coincidencia.group(3) or "")


def gestor_de_archivos(archivos: Mapping[str, bytes]) -> GestorJS:
    """Gestor a partir de los archivos del proyecto (ruta POSIX → contenido).

    Manda el lockfile; si hay varios, el que coincide con `packageManager`. Sin lockfile
    se usa `packageManager` y, si tampoco está, npm. Yarn es berry (2+) si lo declara
    `packageManager`, si hay `.yarnrc.yml` o si el lockfile tiene `__metadata:`.
    """
    declarado = _package_manager(leer_package_json(archivos.get("package.json")))
    presentes = [(lock, nombre) for lock, nombre in _LOCKFILES if lock in archivos]

    elegido: tuple[str | None, str] | None = None
    if declarado is not None:
        elegido = next(
            ((lock, nombre) for lock, nombre in presentes if nombre == declarado[0]),
            None,
        )
        if elegido is None and not presentes:
            elegido = (None, declarado[0])
    if elegido is None:
        elegido = presentes[0] if presentes else (None, "npm")
    lockfile, nombre = elegido

    version = declarado[1] if declarado and declarado[0] == nombre else None
    if nombre == "npm":
        return GestorJS("npm", None, lockfile)
    if nombre == "yarn":
        berry = (
            not version.startswith("1.")
            if version
            else (
                ".yarnrc.yml" in archivos
                or b"__metadata:" in archivos.get("yarn.lock", b"")[:4096]
            )
        )
        nombre = "yarn-berry" if berry else "yarn-classic"
    return GestorJS(nombre, version or VERSIONES_POR_DEFECTO[nombre], lockfile)


def detectar_gestor(raiz: Path) -> GestorJS:
    """Gestor de paquetes del proyecto en `raiz` (ver `gestor_de_archivos`)."""
    archivos = {
        nombre: contenido
        for nombre in ("package.json", ".yarnrc.yml", *(lock for lock, _ in _LOCKFILES))
        if (contenido := _leer(raiz / nombre)) is not None
    }
    return gestor_de_archivos(archivos)


# --- Workspaces --------------------------------------------------------------------------


def _lista_yaml(texto: str, clave: str) -> list[str]:
    """Valores de una lista de primer nivel en YAML simple (`clave:` y `- valor`).

    Basta para `pnpm-workspace.yaml`; no se agrega una dependencia de YAML por esto.
    """
    valores: list[str] = []
    dentro = False
    for linea in texto.splitlines():
        sin_comentario = re.sub(r"\s+#.*$", "", linea).rstrip()
        if not sin_comentario.strip() or sin_comentario.lstrip().startswith("#"):
            continue
        if not linea[:1].isspace() and not sin_comentario.startswith("-"):
            dentro = sin_comentario.split(":", 1)[0].strip() == clave
            continue
        if dentro and sin_comentario.strip().startswith("- "):
            valores.append(sin_comentario.strip()[2:].strip().strip("'\""))
    return valores


def _mapa_yaml(texto: str, clave: str) -> list[str]:
    """Valores de un mapa de primer nivel en YAML simple (`clave:` y `  a: valor`)."""
    valores: list[str] = []
    dentro = False
    for linea in texto.splitlines():
        sin_comentario = re.sub(r"\s+#.*$", "", linea).rstrip()
        if not sin_comentario.strip() or sin_comentario.lstrip().startswith("#"):
            continue
        if not linea[:1].isspace():
            dentro = sin_comentario.split(":", 1)[0].strip() == clave
            continue
        if dentro and ":" in sin_comentario:
            valor = sin_comentario.rsplit(":", 1)[1].strip().strip("'\"")
            if valor:
                valores.append(valor)
    return valores


def patrones_workspaces(raiz: Path, gestor: GestorJS) -> list[str]:
    """Patrones de workspaces: `pnpm-workspace.yaml` (pnpm) o `workspaces` del package.json."""
    if gestor.nombre == "pnpm":
        texto = _leer_texto(raiz / "pnpm-workspace.yaml")
        return _lista_yaml(texto, "packages") if texto else []
    paquete = leer_package_json(_leer(raiz / "package.json"))
    workspaces = paquete.get("workspaces")
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages")
    if not isinstance(workspaces, list):
        return []
    return [w for w in workspaces if isinstance(w, str)]


def _patron_seguro(patron: str) -> str | None:
    """Patrón relativo sin `..` ni rutas absolutas; `None` si no lo es."""
    limpio = patron.strip().replace("\\", "/").removeprefix("./").rstrip("/")
    if not limpio or limpio.startswith("/") or re.match(r"^[A-Za-z]:", limpio):
        return None
    if ".." in PurePosixPath(limpio).parts:
        return None
    return limpio


def _ignorada(relativa: Path) -> bool:
    return any(parte in _CARPETAS_IGNORADAS for parte in relativa.parts)


def carpetas_workspaces(raiz: Path, patrones: list[str]) -> list[str]:
    """Carpetas (rutas POSIX relativas) de los workspaces que tienen `package.json`.

    Admite los comodines de pnpm, npm y yarn (`packages/*`, `apps/**`) y exclusiones con
    `!`. Nunca sale de `raiz` ni entra en `node_modules`.
    """
    incluidas: set[str] = set()
    excluidas: set[str] = set()
    for patron in patrones:
        negado = patron.startswith("!")
        limpio = _patron_seguro(patron[1:] if negado else patron)
        if limpio is None:
            continue
        for carpeta in raiz.glob(limpio):
            if not carpeta.is_dir():
                continue
            relativa = carpeta.relative_to(raiz)
            if relativa == Path(".") or _ignorada(relativa):
                continue
            (excluidas if negado else incluidas).add(relativa.as_posix())
    carpetas = sorted(
        c for c in incluidas - excluidas if (raiz / c / "package.json").is_file()
    )
    return carpetas[:MAXIMO_WORKSPACES]


def _parches(raiz: Path, gestor: GestorJS, paquete: Mapping) -> list[str]:
    """Archivos de parches que el gestor necesita para instalar (`patchedDependencies`)."""
    rutas: list[str] = []
    if gestor.nombre == "pnpm":
        pnpm = paquete.get("pnpm")
        if isinstance(pnpm, dict) and isinstance(pnpm.get("patchedDependencies"), dict):
            rutas += [
                v for v in pnpm["patchedDependencies"].values() if isinstance(v, str)
            ]
        texto = _leer_texto(raiz / "pnpm-workspace.yaml")
        if texto:
            rutas += _mapa_yaml(texto, "patchedDependencies")
    if gestor.nombre == "yarn-berry":
        carpeta = raiz / ".yarn" / "patches"
        if carpeta.is_dir():
            rutas += [
                p.relative_to(raiz).as_posix() for p in sorted(carpeta.rglob("*.patch"))
            ]
    seguras = []
    for ruta in rutas:
        limpia = _patron_seguro(ruta)
        if limpia and (raiz / limpia).is_file() and limpia not in seguras:
            seguras.append(limpia)
    return seguras[:MAXIMO_PARCHES]


# --- Archivos del contexto de build -----------------------------------------------------


def sin_credenciales(contenido: bytes) -> bytes:
    """Quita de `.npmrc`, `.yarnrc` o `.yarnrc.yml` las líneas con credenciales.

    En `.yarnrc.yml` también quita `yarnPath` y el bloque `plugins` (código del proyecto
    que yarn ejecutaría al instalar).
    """
    texto = contenido.decode("utf-8", errors="replace")
    lineas: list[str] = []
    en_plugins = False
    for linea in texto.splitlines():
        sangria = linea[:1].isspace()
        clave = linea.split(":", 1)[0].split("=", 1)[0].strip()
        if not sangria and linea.strip():
            en_plugins = clave == "plugins"
            if en_plugins or clave == "yarnPath":
                continue
        if en_plugins:
            continue
        # `.npmrc`: `//registro/:_authToken=...` (la clave lleva `:`); `.yarnrc`:
        # `"//registro/:_authToken" "..."`; `.yarnrc.yml`: `npmAuthToken: ...`.
        if _CLAVE_SECRETA.search(linea.split("=", 1)[0]):
            continue
        lineas.append(linea)
    return ("\n".join(lineas) + "\n").encode("utf-8")


_CONFIGURACION = {
    "npm": (".npmrc",),
    "pnpm": (".npmrc", "pnpm-workspace.yaml"),
    "yarn-classic": (".npmrc", ".yarnrc"),
    "yarn-berry": (".yarnrc.yml",),
}


def recolectar_archivos(raiz: Path) -> dict[str, bytes]:
    """Archivos que se copian al contexto de build de un proyecto JS (rutas POSIX).

    `package.json` de la raíz y de cada workspace, el lockfile del gestor, su
    configuración sin credenciales, los parches declarados y, si hay workspaces, el
    script que reubica sus dependencias.
    """
    gestor = detectar_gestor(raiz)
    archivos: dict[str, bytes] = {"package.json": (raiz / "package.json").read_bytes()}
    if gestor.lockfile:
        archivos[gestor.lockfile] = (raiz / gestor.lockfile).read_bytes()
    for nombre in _CONFIGURACION[gestor.nombre]:
        ruta = raiz / nombre
        if ruta.is_file():
            contenido = ruta.read_bytes()
            archivos[nombre] = (
                contenido
                if nombre == "pnpm-workspace.yaml"
                else sin_credenciales(contenido)
            )
    workspaces = carpetas_workspaces(raiz, patrones_workspaces(raiz, gestor))
    for carpeta in workspaces:
        archivos[f"{carpeta}/package.json"] = (
            raiz / carpeta / "package.json"
        ).read_bytes()
    paquete = leer_package_json(archivos["package.json"])
    for parche in _parches(raiz, gestor, paquete):
        ruta = raiz / parche
        if ruta.stat().st_size <= _MAXIMO_BYTES_PARCHE:
            archivos[parche] = ruta.read_bytes()
    if workspaces:
        archivos[NOMBRE_SCRIPT] = SCRIPT_REUBICAR.read_bytes()
    return archivos


# --- Dockerfile derivado ----------------------------------------------------------------


def _comandos_instalacion(gestor: GestorJS) -> tuple[str, str | None]:
    """(instalación con lockfile, instalación sin bloquearlo o `None`)."""
    if gestor.nombre == "npm":
        sin_bloqueo = (
            "npm install --no-package-lock --ignore-scripts --no-audit --no-fund"
        )
        if gestor.lockfile:
            return "npm ci --ignore-scripts --no-audit --no-fund", sin_bloqueo
        return sin_bloqueo, None
    corepack = f"corepack {gestor.nombre.split('-')[0]}@{gestor.version}"
    if gestor.nombre == "pnpm":
        comun = (
            f"{corepack} install --ignore-scripts --ignore-pnpmfile "
            "--config.node-linker=hoisted --store-dir=/tmp/qagent-store"
        )
        if gestor.lockfile:
            return f"{comun} --frozen-lockfile", f"{comun} --no-frozen-lockfile"
        return f"{comun} --no-frozen-lockfile", None
    if gestor.nombre == "yarn-classic":
        comun = (
            f"{corepack} install --ignore-scripts --non-interactive "
            "--cache-folder /tmp/qagent-yarn-cache"
        )
        if gestor.lockfile:
            return f"{comun} --frozen-lockfile", comun
        return f"{comun} --pure-lockfile", None
    comun = f"{corepack} install --mode=skip-build"
    if gestor.lockfile:
        return f"{comun} --immutable", f"{comun} --no-immutable"
    return f"{comun} --no-immutable", None


def dockerfile_js(
    base: str, archivos: Mapping[str, bytes], carpeta: str, usuario: str
) -> str:
    """Dockerfile derivado que instala las dependencias JS en `/work/node_modules`.

    Args:
        base: imagen base (`qagent-sandbox:node` o la del navegador).
        archivos: archivos del contexto (ruta POSIX → contenido), de `recolectar_archivos`.
        carpeta: carpeta temporal donde se instala dentro de la imagen.
        usuario: usuario con el que queda la imagen (`sandbox` o `pwuser`).
    """
    gestor = gestor_de_archivos(archivos)
    con_lockfile, sin_bloqueo = _comandos_instalacion(gestor)
    instalar = con_lockfile
    if sin_bloqueo:
        instalar = (
            f"( {con_lockfile} \\\n"
            f"       || ( echo '{MARCA_SIN_LOCKFILE}; se instala sin bloquear versiones' \\\n"
            f"            && {sin_bloqueo} ) )"
        )
    preparar = ""
    limpiar = ""
    if gestor.nombre != "npm":
        # Las variables solo valen durante la instalación: no quedan en la imagen.
        variables = [
            "COREPACK_ENABLE_DOWNLOAD_PROMPT=0",
            "COREPACK_ENABLE_STRICT=0",
            "COREPACK_HOME=/tmp/qagent-corepack",
            "CI=true",
        ]
        if gestor.nombre == "yarn-berry":
            variables += [
                "YARN_NODE_LINKER=node-modules",
                "YARN_ENABLE_SCRIPTS=0",
                "YARN_IGNORE_PATH=1",
                "YARN_ENABLE_GLOBAL_CACHE=0",
                "YARN_CACHE_FOLDER=/tmp/qagent-yarn-cache",
                "YARN_ENABLE_TELEMETRY=0",
            ]
        preparar = (
            f"    && export {' '.join(variables)} \\\n"
            # Sin «added 1 package» en el log: el Monitor solo cuenta los del proyecto.
            f"    && npm install -g corepack@{VERSION_COREPACK} --no-audit --no-fund"
            " --loglevel=error \\\n"
        )
        limpiar = (
            " /tmp/qagent-store /tmp/qagent-yarn-cache /tmp/qagent-corepack"
            " && npm uninstall -g corepack --no-audit --no-fund"
        )
    reubicar = ""
    if NOMBRE_SCRIPT in archivos:
        reubicar = f"    && node {NOMBRE_SCRIPT} {carpeta} /work/node_modules /work/proyecto \\\n"
    # Forma JSON de COPY: las rutas de workspaces pueden tener espacios o comillas.
    copias = "".join(
        f"COPY {json.dumps([nombre, f'{carpeta}/{nombre}'], ensure_ascii=False)}\n"
        for nombre in archivos
    )
    return (
        f"FROM {base}\n"
        "USER root\n"
        f"{copias}"
        "RUN true \\\n"
        f"{preparar}"
        f"    && cd {carpeta} && {instalar} \\\n"
        "    && mkdir -p node_modules \\\n"
        f"{reubicar}"
        "    && mv node_modules /work/node_modules \\\n"
        f"    && cd / && rm -rf {carpeta}{limpiar} \\\n"
        "    && npm cache clean --force\n"
        f"USER {usuario}\n"
    )


# --- Mensaje de error para personas -----------------------------------------------------

#: (marcas del log, causa, qué hacer). Se revisan en orden; gana la primera que aparece.
_CAUSAS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("ENOTFOUND", "EAI_AGAIN", "ETIMEDOUT", "ECONNRESET", "getaddrinfo"),
        "no hubo conexión con el registro de paquetes",
        (
            "Revisa la conexión a internet (la instalación de dependencias necesita red) "
            "y vuelve a intentarlo"
        ),
    ),
    (
        ("E401", "E403", "ERR_PNPM_FETCH_401", "ERR_PNPM_FETCH_403", "YN0041"),
        "el registro de paquetes pidió credenciales",
        (
            "El proyecto usa un registro privado. QAgent no copia credenciales a la "
            "imagen, así que esas dependencias no se pueden instalar"
        ),
    ),
    (
        (
            "ERR_PNPM_UNSUPPORTED_ENGINE",
            "EBADENGINE",
            "is incompatible with this module",
        ),
        "el proyecto pide otra versión de Node",
        "Revisa el campo `engines` del package.json: el entorno aislado usa Node 26",
    ),
    (
        ("ERR_PNPM_LOCKFILE_BREAKING_CHANGE", "ERR_PNPM_LOCKFILE_CONFIG_MISMATCH"),
        "el lockfile es de otra versión del gestor",
        (
            "Declara la versión del gestor en `packageManager` del package.json "
            "(por ejemplo, `pnpm@9.15.0`)"
        ),
    ),
    (
        (
            "ERR_PNPM_WORKSPACE_PKG_NOT_FOUND",
            "ERR_PNPM_NO_MATCHING_VERSION_INSIDE_WORKSPACE",
        ),
        "un paquete del monorepo no se encontró entre los workspaces",
        "Revisa `pnpm-workspace.yaml` o el campo `workspaces` del package.json",
    ),
    (
        (
            "ETARGET",
            "No matching version found",
            "ERR_PNPM_NO_MATCHING_VERSION",
            "E404",
        ),
        "una dependencia pide una versión que no existe en el registro",
        "Revisa las versiones del package.json y del lockfile",
    ),
    (
        ("ERESOLVE", "ERR_PNPM_PEER_DEP_ISSUES"),
        "hay dependencias con versiones incompatibles entre sí",
        (
            "Revisa las dependencias «peer» del proyecto (`npm install` también debería "
            "fallar en tu equipo)"
        ),
    ),
    (
        ("ENOSPC", "no space left on device"),
        "Docker se quedó sin espacio en disco",
        "Libera espacio en Docker Desktop (imágenes sin uso) y vuelve a intentarlo",
    ),
    (
        # No buscar «corepack» a secas: el log repite la orden RUN, que lo nombra.
        ("Usage Error:", "Internal Error:"),
        "no se pudo preparar el gestor de paquetes con corepack",
        "Revisa el campo `packageManager` del package.json",
    ),
)

_LINEA_ERROR = re.compile(
    r"(npm (?:ERR!|error)|ERR_PNPM_|\bYN\d{4}\b|^error\b|Error:)", re.IGNORECASE
)


def explicar_fallo(archivos: Mapping[str, bytes], log: str) -> str:
    """Mensaje para personas cuando falla la instalación de dependencias JS.

    Dice qué gestor se usó, la causa probable según el log y qué hacer, y cita las
    últimas líneas de error del gestor (no el comando de Docker).
    """
    gestor = gestor_de_archivos(archivos)
    mensaje = (
        "No se pudieron instalar las dependencias del proyecto con "
        f"{gestor.descripcion}"
    )
    causa = next(
        (
            (texto, accion)
            for marcas, texto, accion in _CAUSAS
            if any(marca in log for marca in marcas)
        ),
        None,
    )
    if causa is not None:
        mensaje += f": {causa[0]}. {causa[1]}."
    else:
        mensaje += ". Revisa el detalle del error del gestor de paquetes."
    errores = [
        linea.strip()
        for linea in log.splitlines()
        if _LINEA_ERROR.search(linea) and MARCA_SIN_LOCKFILE not in linea
    ]
    if errores:
        mensaje += " Detalle: " + " | ".join(errores[-3:])[:600]
    return mensaje


def _leer(ruta: Path) -> bytes | None:
    try:
        return ruta.read_bytes()
    except OSError:
        return None


def _leer_texto(ruta: Path) -> str | None:
    contenido = _leer(ruta)
    return None if contenido is None else contenido.decode("utf-8", errors="replace")

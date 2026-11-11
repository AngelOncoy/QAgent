"""#272: dependencias de proyectos JS con npm, pnpm, yarn y workspaces, sin Docker.

Cubre la detección del gestor, la lectura de workspaces, qué archivos se copian al
contexto de build (sin credenciales ni código), el Dockerfile derivado (nunca ejecuta
scripts del proyecto) y el script que reubica las dependencias de los workspaces.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import ImageNotFound

from qagent.sandbox import (
    IMAGEN_NAVEGADOR,
    IMAGEN_NODE,
    ErrorConstruccionImagen,
    preparar_imagen,
)
from qagent.sandbox.gestores_js import (
    MARCA_SIN_LOCKFILE,
    NOMBRE_SCRIPT,
    SCRIPT_REUBICAR,
    VERSION_COREPACK,
    VERSIONES_POR_DEFECTO,
    carpetas_workspaces,
    detectar_gestor,
    dockerfile_js,
    recolectar_archivos,
    sin_credenciales,
)
from qagent.sandbox.imagen import aviso_dependencias, etiqueta_para_dependencias

CARPETA = "/tmp/qagent-deps"


def _escribir(raiz: Path, archivos: dict[str, str | dict]) -> Path:
    for nombre, contenido in archivos.items():
        ruta = raiz / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        texto = json.dumps(contenido) if isinstance(contenido, dict) else contenido
        ruta.write_text(texto, encoding="utf-8")
    return raiz


@pytest.fixture
def monorepo_pnpm(tmp_path: Path) -> Path:
    """Monorepo como marktext: pnpm, workspaces anidados y `postinstall` propio."""
    return _escribir(
        tmp_path / "marktext",
        {
            "package.json": {
                "name": "marktext-monorepo",
                "private": True,
                "packageManager": "pnpm@10.33.4",
                "scripts": {"postinstall": "tsx scripts/postinstall.ts"},
            },
            "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
            "pnpm-workspace.yaml": (
                "packages:\n"
                "  - 'packages/*'\n"
                "  # comentario\n"
                "  - 'packages/muya/e2e'\n"
                "  - '!packages/ignorado'\n"
                "\n"
                "overrides:\n"
                "  postcss: '8.5.29'\n"
                "patchedDependencies:\n"
                "  foo@1.0.0: patches/foo@1.0.0.patch\n"
            ),
            ".npmrc": (
                "shamefully-hoist=true\n//registry.npmjs.org/:_authToken=npm_SECRETO\n"
            ),
            "patches/foo@1.0.0.patch": "diff --git a/x b/x\n",
            "scripts/postinstall.ts": "throw new Error('no debe ejecutarse')\n",
            "packages/desktop/package.json": {"name": "marktext"},
            "packages/desktop/src/main.ts": "export const x = 1;\n",
            "packages/muya/package.json": {"name": "@muyajs/core"},
            "packages/muya/e2e/package.json": {"name": "muya-e2e"},
            "packages/ignorado/package.json": {"name": "ignorado"},
            "packages/sin-paquete/README.md": "no es un workspace\n",
            "packages/desktop/node_modules/x/package.json": {"name": "x"},
            ".env": "CLAVE=secreta\n",
        },
    )


# --- Detección del gestor ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("archivos", "nombre", "version", "lockfile"),
    [
        ({"package.json": {}}, "npm", None, None),
        (
            {"package.json": {}, "package-lock.json": "{}"},
            "npm",
            None,
            "package-lock.json",
        ),
        (
            {"package.json": {}, "pnpm-lock.yaml": ""},
            "pnpm",
            VERSIONES_POR_DEFECTO["pnpm"],
            "pnpm-lock.yaml",
        ),
        (
            {"package.json": {"packageManager": "pnpm@9.15.0"}},
            "pnpm",
            "9.15.0",
            None,
        ),
        (
            {"package.json": {}, "yarn.lock": "# yarn lockfile v1\n"},
            "yarn-classic",
            VERSIONES_POR_DEFECTO["yarn-classic"],
            "yarn.lock",
        ),
        (
            {"package.json": {}, "yarn.lock": "__metadata:\n  version: 8\n"},
            "yarn-berry",
            VERSIONES_POR_DEFECTO["yarn-berry"],
            "yarn.lock",
        ),
        (
            {"package.json": {}, "yarn.lock": "", ".yarnrc.yml": "nodeLinker: pnp\n"},
            "yarn-berry",
            VERSIONES_POR_DEFECTO["yarn-berry"],
            "yarn.lock",
        ),
        (
            {"package.json": {"packageManager": "yarn@4.1.0"}, "yarn.lock": ""},
            "yarn-berry",
            "4.1.0",
            "yarn.lock",
        ),
        (
            {"package.json": {"packageManager": "yarn@1.22.19"}, "yarn.lock": ""},
            "yarn-classic",
            "1.22.19",
            "yarn.lock",
        ),
    ],
)
def test_detecta_el_gestor(tmp_path, archivos, nombre, version, lockfile):
    gestor = detectar_gestor(_escribir(tmp_path, archivos))

    assert (gestor.nombre, gestor.version, gestor.lockfile) == (
        nombre,
        version,
        lockfile,
    )


def test_con_varios_lockfiles_manda_el_de_package_manager(tmp_path):
    _escribir(
        tmp_path,
        {
            "package.json": {"packageManager": "pnpm@10.33.4"},
            "package-lock.json": "{}",
            "pnpm-lock.yaml": "",
        },
    )

    gestor = detectar_gestor(tmp_path)

    assert (gestor.nombre, gestor.lockfile) == ("pnpm", "pnpm-lock.yaml")


def test_con_varios_lockfiles_sin_package_manager_gana_pnpm(tmp_path):
    _escribir(
        tmp_path, {"package.json": {}, "package-lock.json": "{}", "pnpm-lock.yaml": ""}
    )

    assert detectar_gestor(tmp_path).nombre == "pnpm"


def test_conserva_el_hash_de_integridad_de_package_manager(tmp_path):
    _escribir(
        tmp_path,
        {"package.json": {"packageManager": "pnpm@10.33.4+sha512.abc123"}},
    )

    gestor = detectar_gestor(tmp_path)

    assert gestor.version == "10.33.4+sha512.abc123"
    assert gestor.descripcion == "pnpm 10.33.4 sin lockfile"


@pytest.mark.parametrize(
    "declarado",
    [
        "pnpm@10.0.0 && curl evil",
        "pnpm@latest",
        "pnpm@10.0.0;rm -rf /",
        "pnpm@$(id)",
        "bun@1.0.0",
    ],
)
def test_ignora_un_package_manager_que_no_es_una_version(tmp_path, declarado):
    _escribir(tmp_path, {"package.json": {"packageManager": declarado}})

    gestor = detectar_gestor(tmp_path)
    dockerfile = dockerfile_js(
        IMAGEN_NODE, recolectar_archivos(tmp_path), CARPETA, "sandbox"
    )

    assert gestor.nombre == "npm"
    assert declarado not in dockerfile


def test_package_json_invalido_cae_en_npm(tmp_path):
    (tmp_path / "package.json").write_text("{ no es json", encoding="utf-8")

    assert detectar_gestor(tmp_path).nombre == "npm"


# --- Workspaces y archivos copiados -----------------------------------------------------


def test_lee_los_workspaces_de_pnpm_con_exclusiones(monorepo_pnpm):
    archivos = recolectar_archivos(monorepo_pnpm)

    assert sorted(archivos) == sorted(
        [
            "package.json",
            "pnpm-lock.yaml",
            "pnpm-workspace.yaml",
            ".npmrc",
            "packages/desktop/package.json",
            "packages/muya/package.json",
            "packages/muya/e2e/package.json",
            "patches/foo@1.0.0.patch",
            NOMBRE_SCRIPT,
        ]
    )


def test_nunca_copia_codigo_ni_secretos_del_proyecto(monorepo_pnpm):
    archivos = recolectar_archivos(monorepo_pnpm)

    assert not any(n.endswith((".ts", ".env")) for n in archivos)
    assert not any("node_modules" in n for n in archivos)
    assert b"npm_SECRETO" not in archivos[".npmrc"]
    assert b"shamefully-hoist=true" in archivos[".npmrc"]


def test_lee_los_workspaces_de_npm_y_yarn(tmp_path):
    _escribir(
        tmp_path,
        {
            "package.json": {"workspaces": {"packages": ["apps/*", "libs/**"]}},
            "yarn.lock": "",
            "apps/web/package.json": {},
            "libs/a/package.json": {},
            "libs/a/b/package.json": {},
        },
    )

    archivos = recolectar_archivos(tmp_path)

    assert {
        "apps/web/package.json",
        "libs/a/package.json",
        "libs/a/b/package.json",
    } <= set(archivos)


@pytest.mark.parametrize("patron", ["../fuera/*", "/etc/*", "C:/Windows/*"])
def test_un_workspace_nunca_sale_del_proyecto(tmp_path, patron):
    proyecto = _escribir(
        tmp_path / "proyecto", {"package.json": {"workspaces": [patron]}}
    )
    _escribir(tmp_path, {"fuera/x/package.json": {}})

    assert carpetas_workspaces(proyecto, [patron]) == []
    assert NOMBRE_SCRIPT not in recolectar_archivos(proyecto)


def test_sin_workspaces_no_copia_el_script_de_reubicacion(tmp_path):
    _escribir(tmp_path, {"package.json": {}, "package-lock.json": "{}"})

    assert sorted(recolectar_archivos(tmp_path)) == [
        "package-lock.json",
        "package.json",
    ]


def test_yarnrc_sin_credenciales_ni_plugins_ni_yarn_path():
    contenido = (
        b"nodeLinker: pnp\n"
        b"npmAuthToken: SECRETO\n"
        b"yarnPath: .yarn/releases/yarn-4.1.0.cjs\n"
        b"plugins:\n"
        b"  - path: .yarn/plugins/x.cjs\n"
        b"npmScopes:\n"
        b"  empresa:\n"
        b"    npmAuthToken: OTRO\n"
        b"    npmRegistryServer: https://npm.empresa\n"
    )

    limpio = sin_credenciales(contenido).decode()

    assert "SECRETO" not in limpio and "OTRO" not in limpio
    assert "yarnPath" not in limpio and "plugins" not in limpio
    assert "nodeLinker: pnp" in limpio
    assert "npmRegistryServer: https://npm.empresa" in limpio


# --- Dockerfile derivado ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("archivos", "con_lockfile", "fallback"),
    [
        (
            {"package.json": {}, "package-lock.json": "{}"},
            "npm ci --ignore-scripts",
            "npm install --no-package-lock --ignore-scripts",
        ),
        ({"package.json": {}}, "npm install --no-package-lock --ignore-scripts", None),
        (
            {"package.json": {}, "pnpm-lock.yaml": ""},
            f"corepack pnpm@{VERSIONES_POR_DEFECTO['pnpm']} install --ignore-scripts",
            "--no-frozen-lockfile",
        ),
        (
            {"package.json": {}, "yarn.lock": ""},
            "--ignore-scripts --non-interactive",
            None,
        ),
        (
            {"package.json": {"packageManager": "yarn@4.1.0"}, "yarn.lock": ""},
            "corepack yarn@4.1.0 install --mode=skip-build --immutable",
            "--no-immutable",
        ),
    ],
)
def test_dockerfile_instala_sin_scripts_y_respeta_el_lockfile(
    tmp_path, archivos, con_lockfile, fallback
):
    _escribir(tmp_path, archivos)

    dockerfile = dockerfile_js(
        IMAGEN_NODE, recolectar_archivos(tmp_path), CARPETA, "sandbox"
    )

    assert dockerfile.startswith(f"FROM {IMAGEN_NODE}\n")
    assert con_lockfile in dockerfile
    if fallback:
        assert MARCA_SIN_LOCKFILE in dockerfile and fallback in dockerfile
    assert "mv node_modules /work/node_modules" in dockerfile
    assert dockerfile.rstrip().endswith("USER sandbox")
    assert "postinstall" not in dockerfile


def test_dockerfile_de_yarn_berry_no_ejecuta_scripts_ni_yarn_path(tmp_path):
    _escribir(tmp_path, {"package.json": {"packageManager": "yarn@4.1.0"}})

    dockerfile = dockerfile_js(
        IMAGEN_NODE, recolectar_archivos(tmp_path), CARPETA, "sandbox"
    )

    for variable in (
        "YARN_ENABLE_SCRIPTS=0",
        "YARN_IGNORE_PATH=1",
        "YARN_NODE_LINKER=node-modules",
    ):
        assert variable in dockerfile


def test_dockerfile_de_pnpm_usa_corepack_fijo_y_no_deja_variables(monorepo_pnpm):
    dockerfile = dockerfile_js(
        IMAGEN_NODE, recolectar_archivos(monorepo_pnpm), CARPETA, "sandbox"
    )

    assert f"npm install -g corepack@{VERSION_COREPACK}" in dockerfile
    assert "corepack pnpm@10.33.4 install" in dockerfile
    assert "--ignore-pnpmfile" in dockerfile
    assert "--config.node-linker=hoisted" in dockerfile
    assert "--frozen-lockfile" in dockerfile
    assert f"node {NOMBRE_SCRIPT} {CARPETA} /work/node_modules /work/proyecto" in (
        dockerfile
    )
    assert "\nENV " not in dockerfile  # corepack y CI solo valen al instalar
    assert "npm uninstall -g corepack" in dockerfile


def test_copy_en_forma_json_para_rutas_con_espacios(tmp_path):
    _escribir(
        tmp_path,
        {
            "package.json": {"workspaces": ["apps/*"]},
            "apps/mi app & co/package.json": {},
        },
    )

    dockerfile = dockerfile_js(
        IMAGEN_NODE, recolectar_archivos(tmp_path), CARPETA, "sandbox"
    )

    assert (
        'COPY ["apps/mi app & co/package.json", '
        '"/tmp/qagent-deps/apps/mi app & co/package.json"]'
    ) in dockerfile


# --- Imagen derivada (Docker simulado) --------------------------------------------------


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


def test_marktext_construye_la_derivada_con_pnpm_y_workspaces(monorepo_pnpm):
    docker = DockerSimulado(IMAGEN_NODE)

    etiqueta = preparar_imagen(monorepo_pnpm, docker.cliente, imagen=IMAGEN_NODE)

    [construccion] = docker.construcciones
    assert etiqueta.startswith("qagent-sandbox:node-")
    assert "packages/desktop/package.json" in construccion["archivos"]
    assert "scripts/postinstall.ts" not in construccion["archivos"]
    assert "corepack pnpm@10.33.4 install" in construccion["dockerfile"]


def test_la_derivada_del_navegador_queda_con_pwuser(monorepo_pnpm):
    docker = DockerSimulado(IMAGEN_NAVEGADOR)

    preparar_imagen(monorepo_pnpm, docker.cliente, imagen=IMAGEN_NAVEGADOR)

    [construccion] = docker.construcciones
    assert construccion["dockerfile"].rstrip().endswith("USER pwuser")


def test_cambiar_un_workspace_cambia_la_etiqueta(monorepo_pnpm):
    antes = etiqueta_para_dependencias(
        "node-", recolectar_archivos(monorepo_pnpm), IMAGEN_NODE
    )
    (monorepo_pnpm / "packages" / "muya" / "package.json").write_text(
        json.dumps({"name": "@muyajs/core", "dependencies": {"x": "1"}})
    )

    despues = etiqueta_para_dependencias(
        "node-", recolectar_archivos(monorepo_pnpm), IMAGEN_NODE
    )

    assert antes != despues


def test_no_reutiliza_las_derivadas_que_ejecutaban_scripts():
    archivos = {"package.json": b"{}"}
    import hashlib

    vieja = hashlib.sha256(b"package.json\0{}\0").hexdigest()[:12]

    assert etiqueta_para_dependencias("node-", archivos, IMAGEN_NODE) != (
        f"qagent-sandbox:node-{vieja}"
    )


# --- Script de reubicación (Node) -------------------------------------------------------


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite probar el script de reubicación.")
    return node


def test_reubica_las_dependencias_de_los_workspaces(tmp_path):
    node = _node()
    instalacion = _escribir(
        tmp_path / "deps",
        {
            "package.json": {},
            "packages/a/package.json": {},
            "node_modules/comun/index.js": "raiz",
            "packages/a/node_modules/comun/index.js": "workspace",
            "packages/a/node_modules/solo-a/index.js": "a",
            "packages/a/node_modules/@scope/lib/index.js": "lib",
        },
    )

    salida = subprocess.run(
        [node, str(SCRIPT_REUBICAR), str(instalacion), "/work/node_modules", "/work/p"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout

    raiz = instalacion / "node_modules"
    assert (raiz / "solo-a" / "index.js").read_text() == "a"
    assert (raiz / "@scope" / "lib" / "index.js").read_text() == "lib"
    assert (raiz / "comun" / "index.js").read_text() == "raiz"
    assert "1 paquete(s) de workspaces tienen otra versión" in salida


@pytest.mark.skipif(sys.platform == "win32", reason="enlaces simbólicos de Linux")
def test_reescribe_los_enlaces_a_paquetes_del_monorepo(tmp_path):
    node = _node()
    instalacion = _escribir(
        tmp_path / "deps",
        {
            "package.json": {},
            "packages/core/package.json": {},
            "node_modules/dep/bin.js": "",
        },
    )
    raiz = instalacion / "node_modules"
    (raiz / "@mono").mkdir()
    (raiz / "@mono" / "core").symlink_to("../../packages/core")
    (raiz / ".bin").mkdir()
    (raiz / ".bin" / "dep").symlink_to("../dep/bin.js")

    subprocess.run(
        [node, str(SCRIPT_REUBICAR), str(instalacion), "/work/node_modules", "/work/p"],
        check=True,
    )

    assert (raiz / "@mono" / "core").readlink() == Path("/work/p/packages/core")
    assert (raiz / ".bin" / "dep").readlink() == Path("/work/node_modules/dep/bin.js")


# --- Mensaje de error y avance ----------------------------------------------------------


def _fallo_pnpm(monorepo: Path, log: str) -> str:
    docker = DockerSimulado(IMAGEN_NODE)
    docker.cliente.api.build.return_value = iter(
        [
            {"stream": "Step 6/7 : RUN true && corepack pnpm@10.33.4 install\n"},
            {"stream": log},
            {"error": "The command '/bin/sh -c true' returned a non-zero code: 1"},
        ]
    )
    with pytest.raises(ErrorConstruccionImagen) as error:
        preparar_imagen(monorepo, docker.cliente, lambda _t: None, IMAGEN_NODE)
    return str(error.value)


def test_el_error_nombra_el_gestor_la_causa_y_no_la_orden_de_docker(monorepo_pnpm):
    mensaje = _fallo_pnpm(
        monorepo_pnpm,
        " ERR_PNPM_UNSUPPORTED_ENGINE  Unsupported environment (bad pnpm and/or Node.js version)\n",
    )

    assert mensaje.startswith(
        "No se pudieron instalar las dependencias del proyecto con "
        "pnpm 10.33.4 y pnpm-lock.yaml: el proyecto pide otra versión de Node."
    )
    assert "ERR_PNPM_UNSUPPORTED_ENGINE" in mensaje
    assert "/bin/sh" not in mensaje and "RUN" not in mensaje


@pytest.mark.parametrize(
    ("log", "causa"),
    [
        ("npm error code ETARGET\n", "una dependencia pide una versión que no existe"),
        ("npm error code E401\n", "el registro de paquetes pidió credenciales"),
        ("npm error network getaddrinfo ENOTFOUND registry\n", "no hubo conexión"),
        ("Usage Error: This project is configured to use yarn\n", "corepack"),
        ("ENOSPC: no space left on device\n", "sin espacio en disco"),
    ],
)
def test_reconoce_las_causas_habituales(monorepo_pnpm, log, causa):
    assert causa in _fallo_pnpm(monorepo_pnpm, log)


def test_sin_causa_conocida_cita_las_ultimas_lineas_de_error(monorepo_pnpm):
    mensaje = _fallo_pnpm(monorepo_pnpm, " ERR_PNPM_ALGO_RARO  Algo raro pasó\n")

    assert "Revisa el detalle del error del gestor de paquetes" in mensaje
    assert "ERR_PNPM_ALGO_RARO  Algo raro pasó" in mensaje


def test_el_monitor_nombra_el_gestor_y_los_paquetes_de_pnpm(monorepo_pnpm):
    docker = DockerSimulado(IMAGEN_NODE)
    docker.cliente.api.build.return_value = iter(
        [{"stream": "Packages: +1234\n"}, {"stream": "Successfully tagged x\n"}]
    )
    avisos: list[str] = []

    preparar_imagen(monorepo_pnpm, docker.cliente, avisos.append, IMAGEN_NODE)

    assert aviso_dependencias("pnpm 10.33.4 y pnpm-lock.yaml") in avisos
    assert "Instalando 1234 paquetes" in avisos

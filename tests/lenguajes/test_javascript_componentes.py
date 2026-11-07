"""Detección de React y análisis estático de componentes con tree-sitter (#171, CA1).

Sin Node.js, sin Docker y sin red: se escriben fuentes en carpetas temporales.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.javascript_componentes import (
    AVISO_NO_SOPORTADOS,
    MOTIVO_SIN_ORACULO,
    detectar_framework_ui,
    separar_componentes,
)
from qagent.lenguajes.javascript_estructura import exportadas
from qagent.lenguajes.treesitter import obtener_parser

BOTON_TSX = """
interface BotonProps {
  /** Texto visible del botón. */
  etiqueta: string;
  deshabilitado?: boolean;
  onPulsar: (id: number) => void;
}

/** Botón que muestra su etiqueta y avisa al pulsarlo. */
export function Boton({ etiqueta, deshabilitado = false, onPulsar }: BotonProps) {
  return (
    <button disabled={deshabilitado} onClick={() => onPulsar(1)}>
      {etiqueta}
    </button>
  );
}

type SaludoProps = { nombre: string };
export const Saludo: React.FC<SaludoProps> = ({ nombre }) => <h1>Hola {nombre}</h1>;

export function SinTipos(props) {
  return <div>{props.x}</div>;
}

export function formatear(precio: number): string {
  return `S/ ${precio}`;
}
"""


def _componentes(codigo: str, gramatica: str = "tsx") -> dict[str, dict[str, Any]]:
    raiz = obtener_parser(gramatica).parse(codigo.encode("utf-8")).root_node
    assert not raiz.has_error
    _, componentes = separar_componentes(raiz, exportadas(raiz))
    return {c["nombre"]: c for c in componentes}


def _escribir(raiz: Path, archivos: dict[str, str]) -> None:
    for relativa, codigo in archivos.items():
        ruta = raiz / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(codigo, encoding="utf-8")


def _package(dependencias: dict[str, str]) -> str:
    return json.dumps({"name": "demo", "dependencies": dependencias})


# --- Framework desde package.json -----------------------------------------------------


def test_detecta_react_en_dependencies_o_dev(tmp_path: Path) -> None:
    _escribir(tmp_path, {"package.json": _package({"react": "^19.0.0"})})
    assert detectar_framework_ui(tmp_path) == {
        "framework": "react",
        "nombre": "React",
        "soportado": True,
        "aviso": None,
    }
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"react": "19.0.0"}}), encoding="utf-8"
    )
    assert detectar_framework_ui(tmp_path)["framework"] == "react"


@pytest.mark.parametrize(
    ("paquete", "nombre"),
    [("vue", "Vue"), ("astro", "Astro"), ("@angular/core", "Angular")],
)
def test_framework_no_soportado(tmp_path: Path, paquete: str, nombre: str) -> None:
    _escribir(tmp_path, {"package.json": _package({paquete: "1.0.0"})})
    framework = detectar_framework_ui(tmp_path)
    assert framework["nombre"] == nombre
    assert framework["soportado"] is False
    assert framework["aviso"] == AVISO_NO_SOPORTADOS


@pytest.mark.parametrize(
    "contenido", [None, "{no es json", "[]", '{"dependencies": 3}']
)
def test_package_ausente_o_ilegible_no_detecta(
    tmp_path: Path, contenido: str | None
) -> None:
    if contenido is not None:
        (tmp_path / "package.json").write_text(contenido, encoding="utf-8")
    assert detectar_framework_ui(tmp_path) is None


# --- Componentes y props ------------------------------------------------------------


def test_identifica_componentes_que_devuelven_jsx() -> None:
    componentes = _componentes(BOTON_TSX)
    assert set(componentes) == {"Boton", "Saludo", "SinTipos"}


def test_props_desde_interface_con_opcionales_defectos_y_eventos() -> None:
    boton = _componentes(BOTON_TSX)["Boton"]
    assert boton["origen_props"] == "typescript"
    assert boton["props_tipadas"] is True
    assert boton["verificable"] is True
    assert boton["eventos"] == ["onPulsar"]
    props = {p["nombre"]: p for p in boton["props"]}
    assert props["etiqueta"] == {
        "nombre": "etiqueta",
        "tipo": "string",
        "opcional": False,
        "por_defecto": None,
        "descripcion": "Texto visible del botón.",
        "evento": False,
    }
    assert props["deshabilitado"]["opcional"] is True
    assert props["deshabilitado"]["por_defecto"] == "false"
    assert props["onPulsar"]["tipo"] == "(id: number) => void"
    assert props["onPulsar"]["evento"] is True
    assert boton["jsdoc"]["descripcion"].startswith("Botón que muestra")


def test_props_desde_react_fc_y_tipo_en_linea() -> None:
    saludo = _componentes(BOTON_TSX)["Saludo"]
    assert [p["nombre"] for p in saludo["props"]] == ["nombre"]
    assert saludo["props_tipadas"] is True
    linea = _componentes(
        "export default function Tarjeta(props: { titulo?: string }) {\n"
        "  return <section>{props.titulo}</section>;\n}\n"
    )["Tarjeta"]
    assert linea["props"][0]["opcional"] is True
    assert linea["exportacion"] == "default"


def test_props_desde_jsdoc_en_javascript() -> None:
    codigo = """
/**
 * Muestra un aviso.
 * @param {Object} props
 * @param {string} props.mensaje - Texto del aviso.
 * @param {boolean} [props.urgente]
 * @param {() => void} props.onCerrar
 */
export function Aviso({ mensaje, urgente, onCerrar }) {
  return <p role="alert" onClick={onCerrar}>{urgente ? "!" : ""}{mensaje}</p>;
}
"""
    aviso = _componentes(codigo, "javascript")["Aviso"]
    assert aviso["origen_props"] == "jsdoc"
    assert aviso["props_tipadas"] is True
    props = {p["nombre"]: p for p in aviso["props"]}
    assert props["mensaje"]["descripcion"] == "Texto del aviso."
    assert props["urgente"]["opcional"] is True
    assert aviso["eventos"] == ["onCerrar"]
    assert aviso["ramas"] == 1


def test_componente_sin_tipos_ni_jsdoc_no_es_verificable() -> None:
    sin_tipos = _componentes(BOTON_TSX)["SinTipos"]
    assert sin_tipos["props_tipadas"] is False
    assert sin_tipos["verificable"] is False
    assert "sin resultado esperado verificable" in MOTIVO_SIN_ORACULO


def test_no_son_componentes_minusculas_metodos_ni_sin_jsx() -> None:
    codigo = """
export function lista() { return <ul />; }
export function Calcular(a: number): number { return a * 2; }
export class Vista { Render() { return <div />; } }
export function Contenedor() { const f = () => <span />; return f; }
"""
    assert _componentes(codigo) == {}


# --- analizar() y objetivos() -------------------------------------------------------


def test_analizar_separa_componentes_y_objetivos_con_react(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "package.json": _package({"react": "^19.0.0"}),
            "tsconfig.json": "{}",
            "src/Boton.tsx": BOTON_TSX,
        },
    )
    adaptador = TypeScriptAdapter()
    estructura = adaptador.analizar(tmp_path)
    [modulo] = estructura["modulos"]
    assert [f["nombre"] for f in modulo["funciones"]] == ["formatear"]
    assert [c["nombre"] for c in modulo["componentes"]] == [
        "Boton",
        "Saludo",
        "SinTipos",
    ]
    assert all(c["modulo"] == "src/Boton.tsx" for c in modulo["componentes"])
    assert estructura["framework_ui"]["framework"] == "react"
    assert estructura["framework_ui"]["componentes"] == 3
    assert estructura["framework_ui"]["verificables"] == 2

    objetivos = adaptador.objetivos(estructura)
    assert {(o["tipo"], o["objetivo"]) for o in objetivos} == {
        ("funcion", "formatear"),
        ("componente", "Boton"),
        ("componente", "Saludo"),
        ("componente", "SinTipos"),
    }
    assert all(not o["critical"] for o in objetivos if o["tipo"] == "componente")


def test_framework_no_soportado_prueba_solo_logica(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "package.json": _package({"vue": "^3.5.0"}),
            "src/App.vue": "<template><div/></template>",
            "src/precio.js": "/** @returns {number} */\nexport const iva = (p) => p;\n",
            "src/Vista.jsx": "export function Vista() { return <div />; }\n",
        },
    )
    adaptador = JavaScriptAdapter()
    estructura = adaptador.analizar(tmp_path)
    assert estructura["framework_ui"]["aviso"] == AVISO_NO_SOPORTADOS
    assert estructura["framework_ui"]["componentes"] == 1
    assert estructura["framework_ui"]["verificables"] == 0
    assert {o["tipo"] for o in adaptador.objetivos(estructura)} == {"funcion"}


def test_jsx_sin_react_en_package_tambien_avisa(tmp_path: Path) -> None:
    _escribir(
        tmp_path, {"src/Vista.jsx": "export function Vista() { return <i />; }\n"}
    )
    estructura = JavaScriptAdapter().analizar(tmp_path)
    assert estructura["framework_ui"]["soportado"] is False
    assert estructura["framework_ui"]["aviso"] == AVISO_NO_SOPORTADOS


def test_proyecto_sin_componentes_conserva_la_forma(tmp_path: Path) -> None:
    _escribir(tmp_path, {"src/a.ts": "export const f = (x: number): number => x;\n"})
    estructura = TypeScriptAdapter().analizar(tmp_path)
    assert "framework_ui" not in estructura
    assert "componentes" not in estructura["modulos"][0]

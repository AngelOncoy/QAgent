"""Pruebas de los adaptadores de JavaScript y TypeScript con tree-sitter (ADR-009).

Verifica la carga de gramáticas en caché y la validación de sintaxis estática
sin Node.js, sin Docker y sin acceso a red.
"""

from __future__ import annotations

import pytest

from qagent.lenguajes import (
    JavaScriptAdapter,
    TypeScriptAdapter,
    cargar_gramatica,
)
from qagent.lenguajes.treesitter import (
    extraer_errores_sintaxis,
    obtener_parser,
    validar_sintaxis_js,
    validar_sintaxis_ts,
)

# --- Carga de gramáticas y caché --------------------------------------------


def test_cargar_gramatica_usa_cache() -> None:
    """La función compartida carga cada gramática una sola vez con functools.cache."""
    gramatica_js_1 = cargar_gramatica("javascript")
    gramatica_js_2 = cargar_gramatica("javascript")
    assert gramatica_js_1 is gramatica_js_2

    gramatica_ts_1 = cargar_gramatica("typescript")
    gramatica_ts_2 = cargar_gramatica("typescript")
    assert gramatica_ts_1 is gramatica_ts_2

    gramatica_tsx_1 = cargar_gramatica("tsx")
    gramatica_tsx_2 = cargar_gramatica("tsx")
    assert gramatica_tsx_1 is gramatica_tsx_2


def test_cargar_gramatica_lenguaje_no_soportado() -> None:
    """Gramáticas desconocidas lanzan ValueError."""
    with pytest.raises(ValueError, match="no soportada"):
        cargar_gramatica("ruby")


# --- Extensiones y filtros de archivos --------------------------------------


def test_extensiones_soportadas() -> None:
    """JS y TS declaran las extensiones estándar del ecosistema."""
    js = JavaScriptAdapter()
    assert set(js.extensiones) == {".js", ".mjs", ".cjs", ".jsx"}

    ts = TypeScriptAdapter()
    assert set(ts.extensiones) == {".ts", ".tsx", ".mts", ".cts"}


def test_typescript_ignora_archivos_de_declaracion_d_ts() -> None:
    """Los archivos .d.ts no son fuentes testeables y deben ignorarse."""
    ts = TypeScriptAdapter()
    assert ts.es_fuente("src/servicios/pago.ts") is True
    assert ts.es_fuente("src/componentes/Boton.tsx") is True
    assert ts.es_fuente("src/utils/config.mts") is True
    assert ts.es_fuente("src/utils/helpers.cts") is True
    assert ts.es_fuente("src/tipos/globales.d.ts") is False
    assert ts.es_fuente("src/tipos/DECLARACION.D.TS") is False


# --- Validación de sintaxis JavaScript --------------------------------------


def test_javascript_codigo_valido() -> None:
    """Código JS estándar con ES6+, async/await y clases no produce errores."""
    js = JavaScriptAdapter()
    codigo = """
    import { sumar } from './math.js';

    export class Calculadora {
        constructor(base = 0) {
            this.base = base;
        }

        async ejecutar(valor) {
            const resultado = sumar(this.base, valor);
            return { total: resultado };
        }
    }
    """
    assert js.validar_sintaxis(codigo) == []


def test_javascript_jsx_valido() -> None:
    """La gramática de JavaScript admite elementos JSX sin error."""
    js = JavaScriptAdapter()
    codigo = """
    export function Alerta({ mensaje }) {
        return (
            <div className="alerta">
                <span>{mensaje}</span>
            </div>
        );
    }
    """
    assert js.validar_sintaxis(codigo) == []


def test_javascript_codigo_invalido_detecta_linea() -> None:
    """Código con sintaxis incorrecta reporta la línea del error."""
    js = JavaScriptAdapter()
    codigo = (
        "const a = 10;\n"
        "const b = ; \n"  # línea 2: falta expresión
        "const c = 30;\n"
    )
    errores = js.validar_sintaxis(codigo)
    assert len(errores) > 0
    assert any("línea 2" in err for err in errores)


def test_javascript_llaves_sin_cerrar() -> None:
    """Bloque sin cerrar reporta error de sintaxis."""
    js = JavaScriptAdapter()
    codigo = "function test() {"
    errores = js.validar_sintaxis(codigo)
    assert len(errores) > 0
    assert any("línea 1" in err for err in errores)


# --- Validación de sintaxis TypeScript --------------------------------------


def test_typescript_codigo_valido() -> None:
    """Código TypeScript con interfaces, tipos y genéricos es válido."""
    ts = TypeScriptAdapter()
    codigo = """
    interface Usuario {
        id: string;
        activo: boolean;
    }

    type Respuesta<T> = {
        datos: T;
        exito: boolean;
    };

    export function procesar<T extends Usuario>(item: T): Respuesta<T> {
        return { datos: item, exito: item.activo };
    }
    """
    assert ts.validar_sintaxis(codigo) == []


def test_typescript_tsx_valido() -> None:
    """Componentes TSX con tipado y JSX son válidos."""
    ts = TypeScriptAdapter()
    codigo = """
    interface Props {
        titulo: string;
    }

    export const Tarjeta: React.FC<Props> = ({ titulo }) => {
        return (
            <section>
                <h1>{titulo}</h1>
            </section>
        );
    };
    """
    assert ts.validar_sintaxis(codigo) == []


def test_typescript_codigo_invalido_detecta_linea() -> None:
    """TypeScript con error de sintaxis reporta la línea."""
    ts = TypeScriptAdapter()
    codigo = (
        "interface Item {\n"
        "    id: number;\n"
        "}\n"
        "const x: Item = { id: \n"  # línea 4: incompleto
    )
    errores = ts.validar_sintaxis(codigo)
    assert len(errores) > 0
    assert any("línea 4" in err for err in errores)


def test_typescript_error_en_tipo() -> None:
    """Error de sintaxis en anotación de tipo."""
    ts = TypeScriptAdapter()
    codigo = "const variable: = 123;"
    errores = ts.validar_sintaxis(codigo)
    assert len(errores) > 0
    assert any("línea 1" in err for err in errores)


# --- Funciones auxiliares del módulo treesitter ------------------------------


def test_extraer_errores_sintaxis_arbol_valido() -> None:
    """Un árbol de sintaxis válido no produce errores."""
    parser = obtener_parser("javascript")
    arbol = parser.parse(b"const x = 1;")
    assert extraer_errores_sintaxis(arbol.root_node) == []


def test_validar_sintaxis_js_directo() -> None:
    """Llamada directa a validar_sintaxis_js."""
    assert validar_sintaxis_js("const a = 1;") == []
    errores = validar_sintaxis_js("const = ;")
    assert len(errores) > 0


def test_validar_sintaxis_ts_directo() -> None:
    """Llamada directa a validar_sintaxis_ts."""
    assert validar_sintaxis_ts("const a: number = 1;") == []
    errores = validar_sintaxis_ts("const a: = ;")
    assert len(errores) > 0

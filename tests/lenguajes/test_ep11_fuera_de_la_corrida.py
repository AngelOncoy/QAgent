"""EP-11: los archivos de JS o TS que una corrida no prueba se avisan, no se omiten
en silencio. La corrida usa un solo adaptador: el del lenguaje con más archivos."""

from __future__ import annotations

from pathlib import Path

from qagent.lenguajes import adaptador_del_proyecto, fuera_de_la_corrida
from qagent.proyectos.vista_previa import generar_vista_previa

BANCO_JS = Path(__file__).resolve().parents[2] / "bench" / "banco_mvp_js"


def _escribir(raiz: Path, archivos: dict[str, str]) -> Path:
    for ruta, texto in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return raiz


def test_el_banco_js_avisa_los_dos_archivos_typescript() -> None:
    adaptador = adaptador_del_proyecto(BANCO_JS)

    fuera = fuera_de_la_corrida(BANCO_JS, adaptador)

    assert adaptador.lenguaje == "javascript"
    assert len(fuera) == 1
    assert fuera[0]["lenguaje"] == "typescript"
    assert fuera[0]["archivos"] == 2
    assert fuera[0]["rutas"] == ["src/precios.ts", "src/texto.ts"]
    assert fuera[0]["mensaje"].startswith(
        "2 archivos de TypeScript no se prueban en esta corrida"
    )
    assert "se prueba como JavaScript" in fuera[0]["mensaje"]


def test_un_solo_archivo_javascript_en_un_proyecto_typescript(tmp_path) -> None:
    _escribir(
        tmp_path,
        {
            "tsconfig.json": "{}",
            "src/a.ts": "export const a = 1;\n",
            "src/b.ts": "export const b = 1;\n",
            "vite.config.js": "export default {};\n",
            "src/tipos.d.ts": "export type T = number;\n",
        },
    )
    adaptador = adaptador_del_proyecto(tmp_path)

    fuera = fuera_de_la_corrida(tmp_path, adaptador)

    assert adaptador.lenguaje == "typescript"
    assert [f["rutas"] for f in fuera] == [["vite.config.js"]]
    assert fuera[0]["mensaje"].startswith(
        "1 archivo de JavaScript no se prueba en esta corrida"
    )


def test_un_proyecto_de_un_solo_lenguaje_no_avisa_nada(tmp_path) -> None:
    _escribir(tmp_path, {"package.json": "{}", "src/a.js": "export const a = 1;\n"})

    assert fuera_de_la_corrida(tmp_path, adaptador_del_proyecto(tmp_path)) == []


def test_python_con_javascript_no_cambia_ni_avisa(tmp_path) -> None:
    """El flujo de Python no cambia: un ``static/`` con JS no es un hermano."""
    _escribir(
        tmp_path,
        {
            "app.py": "def f(x: int) -> int:\n    return x\n",
            "static/a.js": "export const a = 1;\n",
            "static/b.ts": "export const b = 1;\n",
        },
    )
    adaptador = adaptador_del_proyecto(tmp_path)

    assert adaptador.lenguaje == "python"
    assert fuera_de_la_corrida(tmp_path, adaptador) == []


def test_la_vista_previa_incluye_lo_que_queda_fuera(tmp_path) -> None:
    _escribir(
        tmp_path,
        {
            "package.json": "{}",
            "src/a.js": "export function a(x) { return x; }\n",
            "src/b.js": "export function b(x) { return x; }\n",
            "src/c.ts": "export function c(x: number): number { return x; }\n",
        },
    )

    vista = generar_vista_previa(tmp_path)

    assert vista["lenguaje"] == "javascript"
    assert [f["rutas"] for f in vista["fuera_de_la_corrida"]] == [["src/c.ts"]]
    assert {m["ruta"] for m in vista["modulos"]} == {"src/a.js", "src/b.js"}


def test_la_vista_previa_de_python_no_trae_avisos_de_otros_lenguajes(
    tmp_path,
) -> None:
    _escribir(tmp_path, {"calc.py": "def f(x: int) -> int:\n    return x\n"})

    assert generar_vista_previa(tmp_path)["fuera_de_la_corrida"] == []

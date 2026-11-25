"""Reglas de la matriz de compatibilidad Java, sin Docker ni red (#309)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from qagent.llm.fake import MARCA_CONTRATO, MARCA_MODULO, MARCA_OBJETIVOS
from tests.compatibilidad_java import ejecutar, matriz
from tests.compatibilidad_java.proveedor import ProveedorMatriz

FILAS = matriz.cargar()
POR_ID = {f.id: f for f in FILAS}


def _escribir(ruta: Path, texto: str) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def test_manifiesto_valido_y_cubre_cada_configuracion() -> None:
    """Cada configuración pedida por #309 tiene al menos una fila."""
    cubiertas = {c for f in FILAS for c in f.configuraciones}
    assert set(matriz.CONFIGURACIONES_OBLIGATORIAS) <= cubiertas
    assert matriz.problemas_de_cobertura(FILAS) == []


@pytest.mark.parametrize(
    "fila", [f for f in FILAS if f.tipo == "externo"], ids=lambda f: f.id
)
def test_externos_trazables_con_commit_inmutable(fila: matriz.Fila) -> None:
    """URL pública, licencia conocida y SHA de 40 caracteres, nunca una rama."""
    assert fila.url.startswith("https://github.com/")
    assert len(fila.commit) == 40 and int(fila.commit, 16) >= 0
    assert fila.licencia in matriz.MARCAS_LICENCIA
    assert fila.archivo_licencia
    assert fila.objetivos


def test_variante_hereda_commit_y_casos_de_su_base() -> None:
    """El defecto sembrado repite el mismo commit y los mismos esperados del Javadoc."""
    base, variante = POR_ID["thealgorithms-java"], POR_ID["thealgorithms-java-defecto"]
    assert variante.commit == base.commit and variante.url == base.url
    casos_base = {o.objetivo: o.casos for o in base.objetivos}
    for objetivo in variante.objetivos:
        assert objetivo.casos == casos_base[objetivo.objetivo]
    assert variante.parches


def test_nivel_pr_es_subconjunto_con_defecto_sembrado() -> None:
    """El PR corre externos y detecta al menos un defecto sembrado."""
    pr = matriz.seleccionar(FILAS, "pr")
    ampliada = matriz.seleccionar(FILAS, "ampliada")
    assert {f.id for f in pr} < {f.id for f in ampliada}
    assert any(f.tipo == "externo" for f in pr)
    assert any("defecto_sembrado" in f.configuraciones for f in pr)


def test_null_de_toml_se_convierte_en_none() -> None:
    """TOML no tiene null: `__null__` se entrega al Planner como None."""
    [caso] = next(o for o in POR_ID["gs-multi-module"].objetivos if o.casos).casos
    assert caso["valor_esperado"] is None


def _manifiesto(tmp_path: Path, fila: str) -> Path:
    return _escribir(tmp_path / "m.toml", "version = 1\n" + fila)


EXTERNO = """
[[fila]]
id = "x"
tipo = "externo"
nivel = "pr"
soporte = "declarado"
configuraciones = ["maven_simple", "padre_publico", "reactor", "perfiles", "tipos_aserciones", "inferencia", "spring", "defecto_sembrado"]
descripcion = "d"
url = "https://github.com/a/b"
licencia = "MIT"
archivo_licencia = "LICENSE"
commit = "COMMIT"
defecto_sembrado = true
[[fila.parche]]
archivo = "A.java"
buscar = "a"
reemplazar = "b"
[[fila.objetivo]]
modulo = "A.java"
objetivo = "A.f"
esperado = "ESPERADO"
[[fila.objetivo.caso]]
id = "c"
entrada = {}
valor_esperado = 1
origen = "docstring"
categoria = "normal"
junit = "assertEquals(1, A.f());"
"""


@pytest.mark.parametrize(
    "commit,esperado,error",
    [
        ("main", "bug_detectado", "SHA completo"),
        ("a" * 39, "bug_detectado", "SHA completo"),
        ("a" * 40, "aprobado", "debe esperar su detección"),
        ("a" * 40, "skipped", "no admitido"),
    ],
)
def test_rechaza_ramas_y_esperados_que_ocultan(
    tmp_path: Path, commit: str, esperado: str, error: str
) -> None:
    """Una rama móvil, un defecto sin detección o un `skipped` no son válidos."""
    ruta = _manifiesto(
        tmp_path, EXTERNO.replace("COMMIT", commit).replace("ESPERADO", esperado)
    )
    with pytest.raises(matriz.MatrizInvalida, match=error):
        matriz.cargar(ruta)


def test_manifiesto_minimo_valido(tmp_path: Path) -> None:
    ruta = _manifiesto(
        tmp_path,
        EXTERNO.replace("COMMIT", "a" * 40).replace("ESPERADO", "bug_detectado"),
    )
    [fila] = matriz.cargar(ruta)
    assert fila.defecto_sembrado and fila.objetivos[0].esperado == "bug_detectado"


def test_no_admitido_no_puede_esperar_veredictos(tmp_path: Path) -> None:
    texto = (
        EXTERNO.replace("COMMIT", "a" * 40)
        .replace("ESPERADO", "bug_detectado")
        .replace('soporte = "declarado"', 'soporte = "no_admitido"')
    )
    with pytest.raises(matriz.MatrizInvalida) as error:
        matriz.cargar(_manifiesto(tmp_path, texto))
    assert "explicar su motivo" in str(error.value)
    assert "no puede esperar veredictos" in str(error.value)


def test_caso_inferido_exige_evidencia(tmp_path: Path) -> None:
    texto = (
        EXTERNO.replace("COMMIT", "a" * 40)
        .replace("ESPERADO", "bug_detectado")
        .replace('origen = "docstring"', 'origen = "inferido"')
    )
    with pytest.raises(matriz.MatrizInvalida, match="evidencia"):
        matriz.cargar(_manifiesto(tmp_path, texto))


@pytest.mark.parametrize(
    "observado,resultado",
    [
        (
            {"estado": "omitido", "motivo": "sin resultado esperado verificable"},
            "fallo_funcional",
        ),
        ({"estado": "sin_veredicto"}, "fallo_funcional"),
        (None, "fallo_funcional"),
        ({"estado": "aprobado"}, "aprobado"),
    ],
)
def test_comparar_no_cuenta_omisiones_como_aprobaciones(
    observado: dict | None, resultado: str
) -> None:
    """Un objetivo omitido, sin veredicto o ausente nunca aprueba una fila declarada."""
    fila = POR_ID["gs-maven"]
    observados = {} if observado is None else {"Greeter.sayHello": observado}
    obtenido, diferencias = matriz.comparar(fila, observados)
    assert obtenido == resultado
    assert bool(diferencias) is (resultado != "aprobado")


def test_comparar_exige_el_motivo_de_la_omision() -> None:
    fila = POR_ID["gs-rest-service"]
    ok = {
        "GET /greeting": {
            "estado": "omitido",
            "motivo": "sin resultado esperado verificable: x",
        }
    }
    otro = {"GET /greeting": {"estado": "omitido", "motivo": "ruta sin resolver"}}
    assert matriz.comparar(fila, ok) == (matriz.NO_ADMITIDO_CONFIRMADO, [])
    assert matriz.comparar(fila, otro)[0] == matriz.FALLO_FUNCIONAL


@pytest.mark.parametrize(
    "totales,resultado",
    [
        ({"total": 1, "omitidas": 1}, matriz.NO_EJECUTADO),
        ({"total": 0}, matriz.NO_EJECUTADO),
        ({"total": 2, "fallos": 1}, matriz.FALLO_FUNCIONAL),
        ({"total": 2, "errores": 1}, matriz.FALLO_TECNICO),
        ({"total": 2}, matriz.APROBADO),
    ],
)
def test_skipped_de_un_fixture_no_acredita_ejecucion(
    totales: dict, resultado: str
) -> None:
    assert matriz.resultado_de_pytest(totales)[0] == resultado


def test_codigo_de_salida_solo_con_exitos() -> None:
    assert matriz.codigo_salida([]) == 1
    assert (
        matriz.codigo_salida(
            [{"resultado": "aprobado"}, {"resultado": "no_admitido_confirmado"}]
        )
        == 0
    )
    for malo in ("fallo_funcional", "fallo_tecnico", "no_ejecutado"):
        assert (
            matriz.codigo_salida([{"resultado": "aprobado"}, {"resultado": malo}]) == 1
        )


def test_totales_junit(tmp_path: Path) -> None:
    ruta = _escribir(
        tmp_path / "j.xml",
        '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="1"/></testsuites>',
    )
    assert ejecutar.totales_junit(ruta) == {
        "total": 3,
        "fallos": 1,
        "errores": 0,
        "omitidas": 1,
    }


def test_parche_debe_coincidir_una_vez(tmp_path: Path) -> None:
    """Un defecto sembrado que ya no coincide con el commit es un fallo técnico."""
    fila = POR_ID["gs-maven-defecto"]
    checkout = tmp_path / "checkout"
    archivo = "complete/" + fila.parches[0]["archivo"]
    _escribir(checkout / archivo, 'class Greeter { String s() { return "otro"; } }')
    with pytest.raises(ejecutar.ErrorTecnico, match="exactamente una vez"):
        ejecutar.preparar_copia(fila, checkout, tmp_path / "trabajo")
    _escribir(checkout / archivo, 'class G { String s() { return "Hello world!"; } }')
    proyecto = ejecutar.preparar_copia(fila, checkout, tmp_path / "trabajo")
    assert 'return "Hello World";' in (proyecto / fila.parches[0]["archivo"]).read_text(
        encoding="utf-8"
    )
    # El checkout descargado no cambia: el parche solo se aplica a la copia.
    assert "Hello world!" in (checkout / archivo).read_text(encoding="utf-8")


def test_evidencia_sanea_secretos(tmp_path: Path) -> None:
    origen = tmp_path / "corrida"
    _escribir(
        origen / "construccion.log",
        "token=abc123secreto\nhttps://user:pw@repo.example/x\n",
    )
    copiados = ejecutar.copiar_evidencia(origen, tmp_path / "evidencia")
    assert copiados == ["construccion.log"]
    texto = (tmp_path / "evidencia/construccion.log").read_text(encoding="utf-8")
    assert "abc123secreto" not in texto and "user:pw" not in texto


def test_seleccion_agrupa_funciones_y_endpoints_por_modulo() -> None:
    seleccion = ejecutar.seleccion_de(POR_ID["gs-multi-module"])
    assert [m["ruta"].split("/")[0] for m in seleccion] == ["library", "application"]
    assert seleccion[0]["funciones"] == ["ServiceProperties.getMessage"]
    assert seleccion[1]["endpoints"] == ["GET /"]


def _resultados(tmp_path: Path, results: dict, detalle: dict) -> SimpleNamespace:
    carpeta = tmp_path / "run"
    _escribir(carpeta / "results.json", json.dumps(results))
    _escribir(carpeta / "detalle.json", json.dumps(detalle))
    return SimpleNamespace(
        construccion={"estado": "aprobado"}, carpeta=str(carpeta), motivo=None
    )


def test_observar_distingue_hallazgo_inferido_de_bug(tmp_path: Path) -> None:
    """Un fallo con esperado inferido es un hallazgo a revisar (ADR-018)."""
    resumen = _resultados(
        tmp_path,
        {
            "objetivos": [{"funcion": "Greeter.sayHello", "decision": "bug_detectado"}],
            "omitidos": [],
        },
        {
            "funciones": [
                {
                    "funcion": "Greeter.sayHello",
                    "contrato": {"casos": [{"origen": "inferido"}]},
                }
            ]
        },
    )
    observados = ejecutar.observar(resumen, POR_ID["gs-maven-defecto"])
    assert observados["Greeter.sayHello"]["estado"] == "hallazgo_inferido"


def test_observar_construccion_bloqueada(tmp_path: Path) -> None:
    resumen = SimpleNamespace(
        construccion={"estado": "fallido", "categoria": "compilacion"},
        carpeta=None,
        motivo="x",
    )
    observados = ejecutar.observar(resumen, POR_ID["gs-maven"])
    assert observados["Greeter.sayHello"]["estado"] == "construccion_bloqueada"
    assert "compilacion" in observados["Greeter.sayHello"]["motivo"]


def _prompt_planner(nombre: str, inferencia: bool) -> str:
    inicio = "Infiere pruebas JUnit 5" if inferencia else "Planifica pruebas JUnit 5"
    return (
        f"{inicio}\n{MARCA_MODULO} src/main/java/hello/Greeter.java\n"
        f"{MARCA_OBJETIVOS} {json.dumps([{'nombre': nombre}])}"
    )


def test_proveedor_solo_entrega_inferidos_al_prompt_de_inferencia(
    tmp_path: Path,
) -> None:
    fila = POR_ID["gs-maven"]
    proveedor = ProveedorMatriz(fila, tmp_path)
    normal = json.loads(
        proveedor.generar(_prompt_planner("Greeter.sayHello", False)).contenido
    )
    inferido = json.loads(
        proveedor.generar(_prompt_planner("Greeter.sayHello", True)).contenido
    )
    assert normal == []
    [plan] = inferido
    assert plan["casos"][0]["origen"] == "inferido"
    assert "junit" not in plan["casos"][0]
    assert proveedor.generar(_prompt_planner("Otro.f", True)).contenido == "[]"


def test_proveedor_genera_el_junit_grabado_del_contrato(tmp_path: Path) -> None:
    fila = POR_ID["thealgorithms-java"]
    objetivo = next(o for o in fila.objetivos if o.objetivo == "FindMax.findMax")
    _escribir(
        tmp_path / objetivo.modulo, "package com.thealgorithms.maths;\nclass FindMax {}"
    )
    contrato = {"objetivo": "FindMax.findMax", "casos": [{"id": "arreglo_vacio"}]}
    respuesta = ProveedorMatriz(fila, tmp_path).generar(
        f"Genera\n{MARCA_CONTRATO} {json.dumps(contrato)}", rol="generator"
    )
    codigo = respuesta.contenido
    assert respuesta.tokens_entrada == respuesta.tokens_salida == 0
    assert codigo.startswith("package com.thealgorithms.maths;")
    assert "class FindMaxTest {" in codigo
    assert "@Test void test_arreglo_vacio()" in codigo
    assert "assertThrows(IllegalArgumentException.class" in codigo
    assert "maximo_normal" not in codigo  # solo los casos que llegaron en el contrato

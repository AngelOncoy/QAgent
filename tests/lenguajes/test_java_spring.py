"""Detección estática Spring real: no compila ni ejecuta controladores (#183)."""

from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter

_IMPORTS = """
package ejemplo;
import org.springframework.web.bind.annotation.*;
import org.springframework.stereotype.Controller;
import org.springframework.http.HttpStatus;
"""


def _analizar(tmp_path: Path, codigo: str) -> list[dict]:
    """Escribe una fuente y devuelve endpoints del adaptador público real."""
    (tmp_path / "Api.java").write_text(_IMPORTS + codigo, encoding="utf-8")
    estructura = JavaAdapter().analizar(tmp_path)
    assert estructura["errores"] == []
    endpoints = estructura["modulos"][0]["endpoints"]
    assert estructura["resumen"]["total_endpoints"] == len(endpoints)
    return endpoints


@pytest.mark.parametrize(
    "anotacion,verbo",
    [
        ("GetMapping", "GET"),
        ("PostMapping", "POST"),
        ("PutMapping", "PUT"),
        ("DeleteMapping", "DELETE"),
        ("PatchMapping", "PATCH"),
    ],
)
def test_compone_rutas_sin_leer_cuerpo(
    tmp_path: Path, anotacion: str, verbo: str
) -> None:
    """Prefijo y ruta literal producen el objetivo; el cuerpo no fija el estado."""
    endpoints = _analizar(
        tmp_path,
        f"""@RestController @RequestMapping("/api")
    class Api {{ @{anotacion}("/items") public String listar() {{ throw new Error(); }} }}""",
    )
    assert len(endpoints) == 1
    e = endpoints[0]
    assert (e["objetivo"], e["manejador"], e["paquete"]) == (
        verbo + " /api/items",
        "Api.listar",
        "ejemplo",
    )
    assert e["resuelta"] is True
    assert e["retorno"] == "String"
    assert e["status_code"] is None
    assert e["cuerpo_respuesta"] is True


def test_parametros_cuerpo_y_respuesta_declarada(tmp_path: Path) -> None:
    """Conserva parámetros, validaciones y estado explícito sin inventar payloads."""
    e = _analizar(
        tmp_path,
        """@RestController class Api {
      @PostMapping(path="/items/{id}", consumes="application/json")
      @ResponseStatus(HttpStatus.CREATED)
      public Item crear(@PathVariable("id") long numero,
        @RequestParam(required=false, defaultValue="1") int pagina,
        @jakarta.validation.Valid @RequestBody Item cuerpo) { return null; }
    }""",
    )[0]
    assert e["status_code"] == 201
    assert e["estado_explicito"] is True
    assert e["consumes"] == ["application/json"]
    p = e["parametros"]
    assert (p[0]["alias"], p[0]["tipo"], p[0]["vinculacion"]) == (
        "id",
        "long",
        "PathVariable",
    )
    assert (p[1]["requerido"], p[1]["por_defecto"]) == (False, ["1"])
    assert p[2]["vinculacion"] == "RequestBody"
    assert "@jakarta.validation.Valid" in p[2]["anotaciones"][0]
    assert e["retorno"] == "Item"


def test_arrays_rutas_y_request_mapping(tmp_path: Path) -> None:
    """Expande cada combinación literal y conserva ambos métodos declarados."""
    endpoints = _analizar(
        tmp_path,
        """@RestController @RequestMapping({"/a", "/b"}) class Api {
      @RequestMapping(path={"/x", "/y"}, method={RequestMethod.GET, RequestMethod.POST})
      public void listar() {}
    }""",
    )
    assert {e["objetivo"] for e in endpoints} == {
        v + " " + p + r
        for v in ("GET", "POST")
        for p in ("/a", "/b")
        for r in ("/x", "/y")
    }


@pytest.mark.parametrize("prefijo", ["BASE", '"${api.prefix}"', '"#{config.ruta}"'])
def test_ruta_dinamica_no_se_inventa(tmp_path: Path, prefijo: str) -> None:
    """Una constante o placeholder no resuelto nunca se presenta como ruta resuelta."""
    e = _analizar(
        tmp_path,
        """@RestController @RequestMapping(PREFIJO) class Api {
      @GetMapping("/items") public String listar() {return "x";}
    }""".replace("PREFIJO", prefijo),
    )[0]
    assert e["resuelta"] is False


def test_controller_vistas_no_inventa_cuerpo_rest(tmp_path: Path) -> None:
    """El String de @Controller puede ser una vista; @ResponseBody sí es explícito."""
    endpoints = _analizar(
        tmp_path,
        """@Controller class Api {
      @GetMapping("/vista") public String vista() {return "index";}
      @GetMapping("/rest") @ResponseBody public String rest() {return "hola";}
    }""",
    )
    assert [e["cuerpo_respuesta"] for e in endpoints] == [False, True]


def test_anotaciones_ajenas_no_son_spring(tmp_path: Path) -> None:
    """Una anotación con el mismo nombre de otro paquete no crea endpoints."""
    codigo = """import otro.RestController; import otro.GetMapping;
      @RestController class Api { @GetMapping("/x") public int x(){return 1;} }"""
    (tmp_path / "Api.java").write_text(codigo, encoding="utf-8")
    assert JavaAdapter().analizar(tmp_path)["resumen"]["total_endpoints"] == 0


def test_anotaciones_cualificadas(tmp_path: Path) -> None:
    """Los nombres completos de Spring funcionan incluso sin imports."""
    (tmp_path / "Api.java").write_text(
        """
      @org.springframework.web.bind.annotation.RestController class Api {
        @org.springframework.web.bind.annotation.GetMapping("/x") public int x(){return 1;}
      }""",
        encoding="utf-8",
    )
    assert (
        JavaAdapter().analizar(tmp_path)["modulos"][0]["endpoints"][0]["objetivo"]
        == "GET /x"
    )


def test_no_analiza_tests_ni_carpetas_generadas(tmp_path: Path) -> None:
    """Los controladores de pruebas/target no se ofrecen como fuentes del usuario."""
    for carpeta in ("src/test/java", "target/classes", "build/generated"):
        directorio = tmp_path / carpeta
        directorio.mkdir(parents=True)
        (directorio / "Api.java").write_text(
            _IMPORTS
            + """@RestController class Api {
          @GetMapping("/x") public int x(){return 1;}
        }""",
            encoding="utf-8",
        )
    assert JavaAdapter().analizar(tmp_path)["resumen"]["total_endpoints"] == 0

"""IDs reparados llegan a MockMvc real sin alterar esperado ni originales (#302)."""

import json
import shutil

import pytest
from docker.errors import NotFound
from docker.models.containers import ContainerCollection

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.orchestrator import corrida
from qagent.sandbox.imagen import (
    _buscar_dependencias,
    etiqueta_para_dependencias,
    receta_de,
)
from qagent.sandbox.modelos import IMAGEN_JAVA
from tests.orchestrator.test_issue302_spring_flujo import (
    SELECCION,
    ClienteIdsSpring,
    verificar_guardado,
)
from tests.sandbox.test_spring_corrida_docker import BANCO

pytestmark = pytest.mark.docker


def test_ids_spring_reparados_ejecutan_201_y_detectan_200_en_docker(
    cliente_docker, tmp_path, monkeypatch
):
    receta = receta_de(IMAGEN_JAVA)
    _, archivos = _buscar_dependencias(BANCO, receta)
    etiqueta = etiqueta_para_dependencias(receta.prefijo, archivos)
    imagen = cliente_docker.images.get(etiqueta).id
    raiz = tmp_path / "spring-302"
    shutil.copytree(BANCO, raiz)
    originales = {p: p.read_bytes() for p in raiz.rglob("*") if p.is_file()}
    AlmacenProyecto(raiz).inicializar()
    cliente = ClienteIdsSpring()
    monkeypatch.setattr(corrida, "crear_cliente", lambda *a, **k: cliente)
    contenedores = []
    ejecutar = ContainerCollection.run

    def observar(self, *args, **kwargs):
        assert kwargs["network_mode"] == "none"
        assert kwargs["read_only"] and kwargs["cap_drop"] == ["ALL"]
        assert kwargs["security_opt"] == ["no-new-privileges"]
        contenedor = ejecutar(self, *args, **kwargs)
        contenedores.append(contenedor.id)
        return contenedor

    monkeypatch.setattr(ContainerCollection, "run", observar)
    eventos = []
    resumen = corrida.ejecutar_corrida(
        raiz,
        "std",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda *a: imagen,
        seleccion=SELECCION,
        al_evento=eventos.append,
    )
    assert (
        resumen.estado == "fin" and resumen.aceptadas == resumen.bugs_detectados == 1
    ), resumen
    assert resumen.estancadas == resumen.sin_veredicto == 0
    _results, detalle = verificar_guardado(raiz, resumen)
    defecto = next(
        f for f in detalle["funciones"] if f["funcion"] == "POST /api/articulos-defecto"
    )
    caso = defecto["intentos"][0]["ejecucion"]["casos"][0]
    assert (caso["esperado"], caso["obtenido"]) == ("201", "200")
    assert len(contenedores) == 3  # Precompilación y dos clases JUnit aisladas.
    for identificador in contenedores:
        with pytest.raises(NotFound):
            cliente_docker.containers.get(identificador)
    assert all(p.read_bytes() == contenido for p, contenido in originales.items())
    assert [e for e in eventos if e["tipo"] == "veredicto"][-1]["progreso"] == {
        "hechos": 2,
        "total": 3,
    }
    assert any("ID repetido después de normalizar" in e["mensaje"] for e in eventos)
    assert cliente.llamadas.count("planner") == 1
    (tmp_path / "evidencia302.json").write_text(
        json.dumps(
            {
                "resumen": resumen.a_dict(),
                "eventos": eventos,
                "imagen": imagen,
                "contenedores": contenedores,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "issue": 302,
                "run_id": resumen.run_id,
                "aceptadas": 1,
                "defectos_detectados": 1,
                "omitidos": 1,
                "contenedores_offline": 3,
                "tokens": resumen.tokens,
            }
        )
    )

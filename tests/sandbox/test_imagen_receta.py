"""Huella de la receta de las imágenes base: reconocer una imagen vieja (#250).

Sin Docker: el cliente es un doble. Una imagen `qagent-sandbox:java` construida antes de
#185 no trae ArchUnit y hace fallar las pruebas Java por el entorno; el label
`qagent.receta` permite reconocerla.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from docker.errors import ImageNotFound

from qagent.sandbox import imagen
from qagent.sandbox.imagen import (
    LABEL_RECETA,
    RecetaImagen,
    construir_imagen_base,
    huella_receta,
    imagen_desactualizada,
    receta_de,
)
from qagent.sandbox.modelos import ETIQUETA_CONSTRUCCION, IMAGEN_BASE, IMAGEN_JAVA


def _receta(tmp_path: Path) -> RecetaImagen:
    (tmp_path / "Dockerfile").write_text("FROM ubuntu\n", encoding="utf-8")
    recurso = tmp_path / "java"
    (recurso / "calentamiento").mkdir(parents=True)
    (recurso / "calentamiento" / "pom.xml").write_text("<project/>", encoding="utf-8")
    return RecetaImagen(
        imagen=IMAGEN_JAVA,
        dockerfile=tmp_path / "Dockerfile",
        recursos=(recurso,),
        prefijo="java-",
        dependencias=(),
    )


def test_huella_cambia_con_el_dockerfile_los_recursos_y_los_argumentos(tmp_path):
    receta = _receta(tmp_path)
    original = huella_receta(receta)
    assert original == huella_receta(receta)

    pom = tmp_path / "java" / "calentamiento" / "pom.xml"
    pom.write_text("<project><archunit/></project>", encoding="utf-8")
    con_archunit = huella_receta(receta)
    assert con_archunit != original

    (tmp_path / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    assert huella_receta(receta) != con_archunit
    assert huella_receta(receta, {"PYTHON_VERSION": "3.12"}) != huella_receta(receta)


def _cliente_con(labels: dict | None = None, existe: bool = True) -> MagicMock:
    cliente = MagicMock()
    if existe:
        cliente.images.get.return_value = SimpleNamespace(labels=labels)
    else:
        cliente.images.get.side_effect = ImageNotFound("no está")
    return cliente


def test_imagen_sin_label_o_con_otra_huella_esta_desactualizada():
    assert imagen_desactualizada(_cliente_con(None), IMAGEN_JAVA) is True
    assert imagen_desactualizada(_cliente_con({}), IMAGEN_JAVA) is True
    assert (
        imagen_desactualizada(_cliente_con({LABEL_RECETA: "vieja"}), IMAGEN_JAVA)
        is True
    )


def test_imagen_con_la_huella_actual_esta_al_dia():
    huella = huella_receta(receta_de(IMAGEN_JAVA))
    cliente = _cliente_con({LABEL_RECETA: huella})
    assert imagen_desactualizada(cliente, IMAGEN_JAVA) is False


def test_imagen_que_no_existe_no_esta_desactualizada():
    assert imagen_desactualizada(_cliente_con(existe=False), IMAGEN_JAVA) is False


def test_la_huella_de_python_incluye_su_version():
    huella = huella_receta(receta_de(IMAGEN_BASE), {"PYTHON_VERSION": "3.11"})
    al_dia = _cliente_con({LABEL_RECETA: huella})
    assert imagen_desactualizada(al_dia, IMAGEN_BASE) is False
    assert imagen_desactualizada(al_dia, "qagent-sandbox:base-py3.12") is True


def test_construir_imagen_base_guarda_la_huella_en_un_label():
    cliente = MagicMock()
    construir_imagen_base(cliente, imagen=IMAGEN_JAVA)
    labels = cliente.images.build.call_args.kwargs["labels"]
    # #267: además de la huella, toda construcción lleva el label de QAgent.
    assert labels == {
        **ETIQUETA_CONSTRUCCION,
        LABEL_RECETA: huella_receta(receta_de(IMAGEN_JAVA)),
    }


def test_construir_con_avance_tambien_guarda_la_huella():
    cliente = MagicMock()
    cliente.api.build.return_value = iter([{"stream": "Step 1/2\n"}])
    construir_imagen_base(cliente, avanzar=lambda _texto: None, imagen=IMAGEN_BASE)
    kwargs = cliente.api.build.call_args.kwargs
    assert kwargs["labels"][LABEL_RECETA] == huella_receta(
        receta_de(IMAGEN_BASE), {"PYTHON_VERSION": "3.11"}
    )
    assert kwargs["buildargs"] == {"PYTHON_VERSION": "3.11"}


def test_sin_labels_ni_buildargs_solo_se_pasa_la_etiqueta_de_construccion():
    # #267: el label de QAgent va siempre, para reconocer lo que deja una construcción cortada.
    assert imagen._opciones_build(None, None) == {"labels": ETIQUETA_CONSTRUCCION}

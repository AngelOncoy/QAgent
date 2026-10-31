"""La caché modular admite Java sin cambiar identificadores Python históricos (#182)."""

from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto, ErrorAlmacen, id_de_modulo
from tests.agents.test_generator_java import preparar


def test_identificadores_java_no_colisionan_con_python() -> None:
    """Conserva los IDs Python y distingue lenguaje, ruta y normalizaciones Java."""
    assert id_de_modulo("Banco.py") == "Banco"
    modulos = ("Banco.py", "Banco.java", "src/Banco.java", "src__Banco.java")
    assert len({id_de_modulo(m) for m in modulos}) == len(modulos)
    assert id_de_modulo("Banco.java") == id_de_modulo("Banco.java")


@pytest.mark.parametrize(
    "modulo", ["../Banco.java", "/Banco.java", "C:/Banco.java", "a\\Banco.java"]
)
def test_rechaza_rutas_java_inseguras(modulo: str) -> None:
    """Aceptar Java no permite escapar de la raíz ni introducir rutas Windows absolutas."""
    with pytest.raises(ErrorAlmacen):
        id_de_modulo(modulo)


def test_plan_java_se_guarda_y_se_reutiliza(tmp_path: Path) -> None:
    """El contrato Java real conserva huella y plan al pasar por la caché compartida."""
    contrato = preparar(tmp_path)
    almacen = AlmacenProyecto(tmp_path)
    modulo, huella = contrato["modulo"], contrato["huella"]
    plan = almacen.guardar_plan_modulo(
        modulo, huella, [contrato], "20261031-000000-0182", "generado"
    )
    assert almacen.leer_plan_modulo(modulo) == plan
    assert almacen.buscar_plan_vigente(modulo, huella) == plan
    assert almacen.buscar_plan_vigente(modulo, "0" * 64) is None

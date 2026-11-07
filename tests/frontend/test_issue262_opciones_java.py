"""#262: Preparar recibe capacidades del adaptador y bloquea E2E incompatible."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from qagent.proyectos import vista_previa

RAIZ = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("proyecto", ["java", "spring", "typescript"])
def test_e2e_respeta_capacidad_del_proyecto_sin_afectar_arquitectura(
    tmp_path, monkeypatch, proyecto
) -> None:
    """Java no anuncia Playwright; Node conserva la opción y se verifica al detectar rutas."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node permite comprobar el componente JavaScript.")
    monkeypatch.setattr(vista_previa, "recomendar_para_vista", lambda *a, **kw: {})
    if proyecto == "typescript":
        (tmp_path / "banco.ts").write_text(
            "/** Devuelve x. */ export function f(x:number):number { return x; }",
            encoding="utf-8",
        )
        ruta = tmp_path
    else:
        ruta = RAIZ / (
            "bench_java"
            if proyecto == "java"
            else "bench_java/src/test/resources/spring"
        )
    vista = vista_previa.generar_vista_previa(ruta)
    assert vista["ok"] is True
    assert vista["e2e_humo_disponible"] is (proyecto == "typescript")
    script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const entrada=JSON.parse(fs.readFileSync(0,'utf8'));
const nodos=new Map();
function $(id){
  if(!nodos.has(id)) nodos.set(id,{textContent:'',disabled:false,title:''});
  return nodos.get(id);
}
let llamadas=0;
const ctx=vm.createContext({$, registrarComponente(){},
  window:{pywebview:{api:{detectar_e2e(){llamadas++;},ejecutar_e2e(){llamadas++;}}}}});
for (const ruta of entrada.scripts){
  const fuente=fs.readFileSync(ruta,'utf8');
  for(const nombre of fuente.match(/ICO_[A-Z_]+/g)||[])ctx[nombre]='';
  vm.runInContext(fuente,ctx);
}
ctx.vista=entrada.vista;
vm.runInContext('mostrarLenguajeProyecto(vista); renderCompatibilidadPruebas()',ctx);
const disponible=entrada.vista.e2e_humo_disponible;
assert.equal($('prepE2EEjecutar').disabled,!disponible);
assert.equal($('prepE2EDetectar').disabled,!disponible);
assert.equal($('prepArqVerificar').disabled,false);
if(!disponible){
  assert.match($('prepE2ECompatibilidad').textContent,/no está disponible/);
  (async()=>{
    await vm.runInContext('ejecutarE2E()',ctx);
    await vm.runInContext('detectarRutasE2E()',ctx);
    assert.equal(llamadas,0);
  })().catch(e=>{console.error(e);process.exitCode=1;});
}
"""
    resultado = subprocess.run(
        [node, "-e", script],
        input=json.dumps(
            {
                "vista": vista,
                "scripts": [
                    str(RAIZ / "src/qagent/frontend/componentes" / p)
                    for p in (
                        "vista-previa/vista-previa.js",
                        "config-pruebas/config-pruebas.js",
                    )
                ],
            }
        ),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert resultado.returncode == 0, resultado.stderr

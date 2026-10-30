# Informe real de PIT para #180

`critico-real.xml` se obtuvo ejecutando `test_pit_real_solo_metodo_critico`
en `qagent-sandbox:java`, con PIT 1.30.1 y pitest-junit5-plugin 1.2.3.
La ejecución del 30 de octubre de 2026 terminó correctamente en 18.031 segundos.

El proyecto controlado y su prueba JUnit están definidos en
`tests/sandbox/test_pit_docker.py`. Solo se selecciona `Criticos.critico`;
`noCritico` debe quedar fuera del informe. La prueba comprueba también que el
POM y el código originales permanezcan intactos.

Resultado: tres mutantes KILLED, uno SURVIVED y uno NO_COVERAGE. Con la fórmula
común de QAgent, `3 / (3 + 2) * 100`, la puntuación es 60 %. La prueba JUnit
es deliberadamente incompleta: este porcentaje demuestra que PIT descubre
debilidades en las pruebas, no que la protección sea suficiente.

`test_informe_real_grabado` reproduce la interpretación sin Docker. Para renovar
la evidencia real en PowerShell, con la imagen construida:

```powershell
$env:QAGENT_GRABAR_PIT = '1'
python -m pytest tests/sandbox/test_pit_docker.py -q -s
Remove-Item Env:QAGENT_GRABAR_PIT
```

El XML solo se guarda después de que todas las verificaciones de la prueba
real pasan. Las duraciones pueden variar según el equipo.

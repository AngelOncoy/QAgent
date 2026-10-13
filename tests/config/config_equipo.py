"""config.toml fijo para las pruebas de HU-30.

Es una copia del `config.toml` del equipo. Las pruebas no leen el del repositorio porque
la aplicación lo modifica al guardar la API de un agente: así no dependen de lo que el
usuario haya elegido en su computadora.
"""

CONFIG_EQUIPO = """\
[presupuesto]
tope_por_corrida_usd = 1.00
tope_semestre_usd = 25.00

[reintentos]
max_intentos = 3

[umbrales]
pass_rate_min = 70
cobertura_lineas_min = 60
iteraciones_promedio_max = 2.0

# Comentario antes del primer agente: no se debe tocar.
[agentes.planner]
proveedor = "xiaomi"
modelo = "mimo-v2.6-pro"
precio_entrada_usd_m = 0.435
precio_salida_usd_m = 0.87

[agentes.generator]
proveedor = "xiaomi"
modelo = "mimo-v2.6-pro"
precio_entrada_usd_m = 0.435
precio_salida_usd_m = 0.87

[agentes.reviewer]
proveedor = "openai"
modelo = "gpt-6-luna"
esfuerzo = "max"
precio_entrada_usd_m = 0.10
precio_salida_usd_m = 0.50
"""

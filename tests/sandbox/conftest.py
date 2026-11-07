"""Pruebas del sandbox.

`cliente_docker` e `imagen_base` están en `tests/conftest.py` para que también los usen
las pruebas `docker` de `tests/orchestrator/` y `tests/e2e/`. El marcador `docker` está
en `pyproject.toml`: esas pruebas solo corren con `--docker` (#250).
"""

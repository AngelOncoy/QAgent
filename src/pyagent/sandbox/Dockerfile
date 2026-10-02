# Imagen base del sandbox de QAgent: pyagent-sandbox:base (EN-03).
# Solo trae las herramientas de prueba. Las dependencias del proyecto del usuario
# se instalan en una imagen derivada (paso 1, con red) y las pruebas corren sin red (paso 2).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# httpx lo necesita fastapi.testclient.TestClient; fastapi viene del requirements.txt del proyecto.
RUN pip install \
        pytest==9.1.1 \
        pytest-cov==7.1.0 \
        coverage==7.16.2 \
        mutmut==3.8.0 \
        httpx==0.28.1

RUN useradd --create-home --uid 1000 sandbox \
    && mkdir -p /work/proyecto /work/tests /out \
    && chown -R sandbox:sandbox /work /out

USER sandbox
WORKDIR /work

"""IA grabada de la matriz (#309): solo sustituye al proveedor, nunca a los agentes.

El Planner recibe los casos del manifiesto (esperados del Javadoc del commit fijado
o inferidos con su evidencia) y el Generator recibe el JUnit grabado de cada caso.
Validaciones, guardrails, ejecución en Docker y veredictos son los productivos.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from qagent.llm import FakeLLMClient, RespuestaLLM
from qagent.llm.fake import MARCA_CONTRATO, MARCA_OBJETIVOS
from tests.compatibilidad_java.matriz import Fila, Objetivo

MODELO = "matriz-java-grabada"
_PAQUETE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _json_tras(prompt: str, marca: str) -> Any:
    """JSON de la línea que sigue a una marca del prompt, o None si no está."""
    if marca not in prompt:
        return None
    resto = prompt.rsplit(marca, 1)[1].strip()
    try:
        return json.loads(resto.splitlines()[0] if marca != MARCA_CONTRATO else resto)
    except (ValueError, IndexError):
        return None


def _normalizar(identificador: str) -> str:
    """El mismo ID que deja el adaptador Java (#253, #302)."""
    return re.sub(r"[^a-z0-9_]+", "_", identificador.lower())


class ProveedorMatriz:
    """Respuestas grabadas para los objetivos de una fila de la matriz."""

    def __init__(self, fila: Fila, proyecto: Path) -> None:
        """Indexa los objetivos de la fila; `proyecto` es la copia analizada."""
        self.fila = fila
        self.proyecto = proyecto
        self.por_objetivo: dict[str, Objetivo] = {o.objetivo: o for o in fila.objetivos}
        self.respaldo = FakeLLMClient(grabaciones={})
        self.llamadas: dict[str, int] = {}

    def generar(self, prompt: str, rol: str = "planner") -> RespuestaLLM:
        """Devuelve casos o JUnit grabados; otros roles usan la IA simulada común."""
        self.llamadas[rol] = self.llamadas.get(rol, 0) + 1
        if rol == "planner":
            contenido = self._planificar(prompt)
        elif rol == "generator":
            contenido = self._generar(prompt)
        else:
            return self.respaldo.generar(prompt, rol)
        return RespuestaLLM(contenido, 0, 0, 0.0, MODELO)

    def _planificar(self, prompt: str) -> str:
        """Casos del manifiesto; los inferidos solo responden al prompt de inferencia."""
        inferencia = prompt.startswith("Infiere")
        objetivos = _json_tras(prompt, MARCA_OBJETIVOS) or []
        plan = []
        for declarado in objetivos:
            if not isinstance(declarado, dict):
                continue
            nombre = declarado.get("nombre") or declarado.get("objetivo")
            objetivo = self.por_objetivo.get(nombre)
            if objetivo is None:
                continue
            casos = [
                {k: v for k, v in caso.items() if k != "junit"}
                for caso in objetivo.casos
                if (caso.get("origen") == "inferido") == inferencia
            ]
            if casos:
                plan.append({"objetivo": nombre, "casos": casos})
        return json.dumps(plan, ensure_ascii=False)

    def _generar(self, prompt: str) -> str:
        """Clase JUnit con el cuerpo grabado de cada caso que llegó en el contrato."""
        contrato = _json_tras(prompt, MARCA_CONTRATO)
        if not isinstance(contrato, dict):
            return ""
        objetivo = self.por_objetivo.get(contrato.get("objetivo"))
        if objetivo is None:
            return ""
        grabados = {_normalizar(c["id"]): c["junit"] for c in objetivo.casos}
        fuente = (self.proyecto / objetivo.modulo).read_text(encoding="utf-8-sig")
        paquete = _PAQUETE.search(fuente)
        clase = objetivo.objetivo.split(".")[0]
        lineas = [f"package {paquete[1]};"] if paquete else []
        lineas.append("import org.junit.jupiter.api.Test;")
        lineas += [f"import {nombre};" for nombre in objetivo.imports]
        lineas.append(f"class {clase}Test {{")
        for caso in contrato.get("casos", []):
            cuerpo = grabados.get(caso.get("id"))
            if cuerpo is None:
                continue
            lineas += [
                f"    @Test void test_{caso['id']}() {{",
                f"        {cuerpo}",
                "    }",
            ]
        lineas.append("}")
        return "\n".join(lineas) + "\n"

"""Integración de Graphify + Tree-sitter para el contexto de dependencias inter-archivo.

Combina Graphify en modo estructural (--no-cluster, 0 tokens) para conectar el grafo
de llamadas y dependencias entre archivos, con Tree-sitter local para extraer las
firmas tipadas y docstrings de las funciones y clases destino.

Incluye optimizaciones de alto rendimiento:
1. Modo estructural determinista (--no-cluster) sin llamadas a LLM ni clustering.
2. Caché incremental en disco (.qagent/graph_cache.json) y memoria para latencias < 15 ms.
3. Fallback transparente y resiliente a Tree-sitter si Graphify no está instalado.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from qagent.analysis import arbol_ts, texto_ts
from qagent.analysis.arbol_ts import (
    cuerpo,
    definicion,
    es_clase,
    es_funcion,
    nombre,
    sentencias,
)

# Caché en memoria durante la sesión
_CACHE_MEMORIA: dict[tuple[str, str, str, str], list[DependenciaExterna]] = {}
_HASH_CACHE_MEMORIA: dict[str, str] = {}


@dataclass(frozen=True)
class DependenciaExterna:
    """Símbolo de otro archivo detectado a través del grafo de dependencias."""

    modulo_origen: str
    archivo_origen: str
    nombre: str
    tipo: str  # "funcion", "clase", "llamada"
    relacion: str  # "calls", "uses", "references"
    firma: str = ""
    docstring: str = ""
    atributos_o_campos: list[str] = field(default_factory=list)


def calcular_hash_directorio(carpeta: Path) -> str:
    """Calcula un hash MD5 rápido de los archivos Python en la carpeta para invalidación de caché."""
    if not carpeta.is_dir():
        return ""
    hasher = hashlib.md5()
    try:
        archivos = sorted(carpeta.glob("*.py"))
        for arch in archivos:
            if arch.is_file():
                stat = arch.stat()
                hasher.update(arch.name.encode("utf-8"))
                hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
                hasher.update(str(stat.st_size).encode("utf-8"))
    except OSError:
        pass
    return hasher.hexdigest()


def encontrar_ejecutable_graphify(raiz_proyecto: Path) -> Path | None:
    """Busca el binario de Graphify en entornos virtuales locales o en el PATH del sistema."""
    raiz = Path(raiz_proyecto).resolve()
    candidatos = [
        raiz / ".venv-graphify" / "Scripts" / "graphify.exe",
        raiz / ".venv-graphify" / "bin" / "graphify",
        raiz / ".venv" / "Scripts" / "graphify.exe",
        raiz / ".venv" / "bin" / "graphify",
        raiz / "venv" / "Scripts" / "graphify.exe",
        raiz / "venv" / "bin" / "graphify",
    ]
    for cand in candidatos:
        if cand.is_file():
            return cand
    en_path = shutil.which("graphify")
    return Path(en_path) if en_path else None


def ruta_archivo_cache(raiz_proyecto: Path) -> Path:
    """Ruta al archivo de caché incremental de QAgent."""
    dot_qagent = Path(raiz_proyecto).resolve() / ".qagent"
    dot_qagent.mkdir(parents=True, exist_ok=True)
    return dot_qagent / "graph_cache.json"


def cargar_cache_disco(raiz_proyecto: Path, clave_hash: str) -> dict[str, Any] | None:
    """Carga la caché del grafo desde disco si el hash coincide."""
    cache_path = ruta_archivo_cache(raiz_proyecto)
    if not cache_path.is_file():
        return None
    try:
        datos = json.loads(cache_path.read_text(encoding="utf-8"))
        if datos.get("hash_directorio") == clave_hash:
            return datos.get("dependencias", {})
    except (OSError, json.JSONDecodeError):
        pass
    return None


def guardar_cache_disco(
    raiz_proyecto: Path, clave_hash: str, dependencias_dict: dict[str, Any]
) -> None:
    """Guarda en disco la caché incremental de dependencias."""
    cache_path = ruta_archivo_cache(raiz_proyecto)
    try:
        contenido = {
            "version": 1,
            "hash_directorio": clave_hash,
            "timestamp": time.time(),
            "dependencias": dependencias_dict,
        }
        cache_path.write_text(
            json.dumps(contenido, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, TypeError, ValueError):
        pass


def asegurar_grafo_json(
    raiz_proyecto: Path, carpeta_codigo: Path | None = None
) -> Path | None:
    """Genera o localiza graph.json mediante `graphify update --no-cluster` (0 tokens, ultra-rápido)."""
    raiz = Path(raiz_proyecto).resolve()
    target_dir = (carpeta_codigo or raiz).resolve()

    candidatos_json = [
        target_dir / "graphify-out" / "graph.json",
        raiz / "graphify-out" / "graph.json",
    ]
    for c in candidatos_json:
        if c.is_file() and c.stat().st_size > 100:
            return c

    exe = encontrar_ejecutable_graphify(raiz)
    if exe is None:
        return None

    try:
        # Modo estructural determinista: --no-cluster (0 tokens)
        cmd = [str(exe), "update", str(target_dir), "--no-cluster"]
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=20, check=False
        )
        if res.returncode == 0:
            for c in candidatos_json:
                if c.is_file():
                    return c
    except (subprocess.SubprocessError, OSError):
        pass

    return None


def _modulo_punteado(archivo_rel: str) -> str:
    """Convierte una ruta de archivo relativa a formato de módulo importable."""
    return (
        PurePosixPath(archivo_rel.replace("\\", "/"))
        .with_suffix("")
        .as_posix()
        .replace("/", ".")
    )


def extraer_metadatos_treesitter(
    ruta_archivo: Path, nombre_simbolo: str
) -> dict[str, Any]:
    """Extrae con Tree-sitter la firma tipada, docstring y campos de un símbolo de otro archivo."""
    try:
        fuente = ruta_archivo.read_text(encoding="utf-8")
        arbol = arbol_ts.parsear(fuente)
    except (OSError, UnicodeDecodeError):
        return {"firma": "", "docstring": "", "campos": []}

    for sentencia in sentencias(arbol.root_node):
        elem = definicion(sentencia)
        if es_funcion(elem) and nombre(elem) == nombre_simbolo:
            sig = texto_ts.firma(elem)
            doc = texto_ts.docstring(cuerpo(elem)) or ""
            return {
                "tipo": "funcion",
                "firma": sig,
                "docstring": doc.splitlines()[0] if doc else "",
                "campos": [],
            }
        elif es_clase(elem) and nombre(elem) == nombre_simbolo:
            doc = texto_ts.docstring(cuerpo(elem)) or ""
            campos: list[str] = []
            bloque = cuerpo(elem)
            if bloque:
                for sub in sentencias(bloque):
                    if sub.type == "expression_statement":
                        asig = arbol_ts.campo(sub, "assignment")
                        if asig:
                            izq = arbol_ts.campo(asig, "left")
                            tip = arbol_ts.campo(asig, "type")
                            if izq and tip:
                                campos.append(
                                    f"{arbol_ts.texto(izq)}: {arbol_ts.texto(tip)}"
                                )
            return {
                "tipo": "clase",
                "firma": f"class {nombre_simbolo}",
                "docstring": doc.splitlines()[0] if doc else "",
                "campos": campos,
            }

    return {"firma": "", "docstring": "", "campos": []}


def _fallback_treesitter(
    raiz_proyecto: Path,
    modulo: str,
    objetivo: str,
    tipo_objetivo: str = "funcion",
) -> list[DependenciaExterna]:
    """Fallback ultrarrápido usando el motor sintáctico de Tree-sitter si Graphify no está instalado."""
    try:
        from qagent.analysis.grafo_imports import construir_grafo_dependencias

        grafo = construir_grafo_dependencias(
            raiz_proyecto, modulo, objetivo, tipo_objetivo=tipo_objetivo
        )
        dependencias: list[DependenciaExterna] = []
        for s in grafo.simbolos_directos:
            dependencias.append(
                DependenciaExterna(
                    modulo_origen=s.modulo_origen,
                    archivo_origen=s.archivo_origen,
                    nombre=s.nombre,
                    tipo=s.tipo,
                    relacion="calls" if s.tipo == "funcion" else "uses",
                    firma=s.firma,
                    docstring=s.docstring,
                    atributos_o_campos=s.atributos_o_campos,
                )
            )
        return dependencias
    except (ImportError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


def analizar_dependencias_con_graphify(
    raiz_proyecto: Path,
    modulo: str,
    objetivo: str,
    tipo_objetivo: str = "funcion",
) -> list[DependenciaExterna]:
    """Analiza dependencias cruzadas usando Graphify + Tree-sitter con caché incremental de alta velocidad.

    1. Comprueba la caché en memoria y en disco (<15 ms).
    2. Si no hay caché, localiza o genera graph.json con `--no-cluster` (0 tokens).
    3. Si Graphify no está disponible, utiliza el fallback nativo de Tree-sitter.
    4. Cruza los enlaces relacionales con Tree-sitter para extraer firmas tipadas y docstrings.
    5. Actualiza la caché para subsiguientes consultas inmediatas.
    """
    raiz = Path(raiz_proyecto).resolve()
    archivo_objetivo = (raiz / modulo).resolve()
    carpeta_objetivo = archivo_objetivo.parent

    # 1. Comprobación de caché
    hash_dir = calcular_hash_directorio(carpeta_objetivo)
    clave_cache = (str(raiz), modulo, objetivo, tipo_objetivo)

    if (
        clave_cache in _CACHE_MEMORIA
        and _HASH_CACHE_MEMORIA.get(str(carpeta_objetivo)) == hash_dir
    ):
        return _CACHE_MEMORIA[clave_cache]

    cache_disco = cargar_cache_disco(raiz, hash_dir)
    clave_item = f"{modulo}::{objetivo}"
    if cache_disco and clave_item in cache_disco:
        deps_cargadas = [DependenciaExterna(**item) for item in cache_disco[clave_item]]
        _CACHE_MEMORIA[clave_cache] = deps_cargadas
        _HASH_CACHE_MEMORIA[str(carpeta_objetivo)] = hash_dir
        return deps_cargadas

    # 2. Localizar o generar el grafo con Graphify
    grafo_path = asegurar_grafo_json(raiz, carpeta_objetivo)
    if not grafo_path or not grafo_path.is_file():
        # Fallback resiliente con Tree-sitter nativo
        deps_fallback = _fallback_treesitter(raiz, modulo, objetivo, tipo_objetivo)
        if deps_fallback:
            _CACHE_MEMORIA[clave_cache] = deps_fallback
            _HASH_CACHE_MEMORIA[str(carpeta_objetivo)] = hash_dir
        return deps_fallback

    try:
        data = json.loads(grafo_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _fallback_treesitter(raiz, modulo, objetivo, tipo_objetivo)

    nodes_by_id = {n["id"]: n for n in data.get("nodes", [])}
    nombre_archivo_obj = archivo_objetivo.name

    # 3. Localizar el nodo de origen
    nodo_origen_id = None
    for n in data.get("nodes", []):
        if n.get("source_file") == nombre_archivo_obj:
            label = n.get("label", "")
            nid = n.get("id", "")
            if (
                label.startswith(f"{objetivo}(")
                or objetivo == label
                or nid.endswith(f"_{objetivo}")
            ):
                nodo_origen_id = nid
                break

    if not nodo_origen_id:
        for n in data.get("nodes", []):
            if (
                objetivo in n.get("id", "")
                and n.get("source_file") == nombre_archivo_obj
            ):
                nodo_origen_id = n["id"]
                break

    if not nodo_origen_id:
        return _fallback_treesitter(raiz, modulo, objetivo, tipo_objetivo)

    # 4. Seguir enlaces salientes (calls, uses, references)
    dependencias: list[DependenciaExterna] = []
    visitados: set[str] = set()

    for link in data.get("links", []):
        if link.get("source") == nodo_origen_id:
            tgt_id = link.get("target")
            rel = link.get("relation", "calls")
            if not tgt_id or tgt_id in visitados:
                continue
            visitados.add(tgt_id)

            tgt_node = nodes_by_id.get(tgt_id)
            if not tgt_node:
                continue

            archivo_destino = tgt_node.get("source_file")
            if not archivo_destino or archivo_destino == nombre_archivo_obj:
                continue

            label = tgt_node.get("label", "")
            simbolo_nombre = label.replace("()", "").strip()
            if not simbolo_nombre:
                simbolo_nombre = tgt_id.split("_")[-1]

            ruta_completa_destino = carpeta_objetivo / archivo_destino
            if not ruta_completa_destino.is_file():
                ruta_completa_destino = raiz / archivo_destino

            try:
                ruta_rel = ruta_completa_destino.relative_to(raiz).as_posix()
            except ValueError:
                ruta_rel = archivo_destino

            mod_punt = _modulo_punteado(ruta_rel)
            meta = extraer_metadatos_treesitter(ruta_completa_destino, simbolo_nombre)

            dependencias.append(
                DependenciaExterna(
                    modulo_origen=mod_punt,
                    archivo_origen=ruta_rel,
                    nombre=simbolo_nombre,
                    tipo=meta.get("tipo", "funcion"),
                    relacion=rel,
                    firma=meta.get("firma", ""),
                    docstring=meta.get("docstring", ""),
                    atributos_o_campos=meta.get("campos", []),
                )
            )

    # Si Graphify no encontró enlaces pero el módulo importa otros archivos, probar fallback
    if not dependencias:
        dependencias = _fallback_treesitter(raiz, modulo, objetivo, tipo_objetivo)

    # 5. Guardar en memoria y disco
    _CACHE_MEMORIA[clave_cache] = dependencias
    _HASH_CACHE_MEMORIA[str(carpeta_objetivo)] = hash_dir

    try:
        dict_actual = cache_disco or {}
        dict_actual[clave_item] = [asdict(d) for d in dependencias]
        guardar_cache_disco(raiz, hash_dir, dict_actual)
    except (OSError, TypeError, ValueError):
        pass

    return dependencias


def formatear_contexto_graphify(
    dependencias: list[DependenciaExterna], modulo_importador: str
) -> str:
    """Genera el bloque textual formateado para inyectar en el prompt del Generator."""
    if not dependencias:
        return ""

    lineas = [
        "DEPENDENCIAS INTERNAS DEL PROYECTO (detectadas con Graphify + Tree-sitter, 0 tokens):",
        "- Las siguientes funciones o clases de otros archivos son invocadas por este objetivo:",
    ]

    for dep in dependencias:
        doc_info = f" — {dep.docstring}" if dep.docstring else ""
        if dep.tipo == "funcion":
            lineas.append(
                f"- Función: `{dep.modulo_origen}.{dep.nombre}{dep.firma}`{doc_info}"
            )
            lineas.append(
                f"  Sugerencia mock: `unittest.mock.patch('{modulo_importador}.{dep.nombre}', return_value=...)`"
            )
        elif dep.tipo == "clase":
            lineas.append(f"- Clase: `{dep.modulo_origen}.{dep.nombre}`{doc_info}")
            if dep.atributos_o_campos:
                lineas.append(f"  Campos: {', '.join(dep.atributos_o_campos[:6])}")

    lineas.append(
        "REGLA OBLIGATORIA: Simula las funciones anteriores mediante unittest.mock.patch."
    )
    lineas.append(
        "Usa sus firmas y tipos para retornar valores de negocio realistas y coherentes."
    )
    return "\n".join(lineas)

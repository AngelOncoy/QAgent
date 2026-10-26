"""Informe PDF de una corrida con la identidad del rediseño de QAgent (HU-22).

Sigue la misma estructura que la pantalla Resultados (bandeja de problemas): primero la
respuesta («3 posibles bugs. Empieza por…»), las cifras y las prioridades; después el
resultado de cada función o endpoint con su evidencia; al final, un anexo técnico.
Habla en lenguaje de personas: sin costos, sin nombres de agentes internos.

Es PDF-1.4 sin dependencias externas: fuentes Type1 estándar con WinAnsiEncoding, flujos
sin comprimir (el texto se puede extraer y auditar con `extraer_texto_pdf`).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from qagent import __version__
from qagent.storage.vista_ejecucion import corrida_incompleta, respuesta_principal

# Página A4 en puntos
ANCHO, ALTO = 595.0, 842.0
MARGEN = 48.0
CONTENIDO = ANCHO - 2 * MARGEN
ARRIBA = ALTO - 72.0
ABAJO = 56.0

# Colores de la identidad para impresión (tema claro de css/tokens.css), en RGB 0..1
Color = tuple[float, float, float]
TEXTO: Color = (0.106, 0.118, 0.137)
TEXTO_2: Color = (0.290, 0.318, 0.357)
TEXTO_3: Color = (0.420, 0.447, 0.486)
BORDE: Color = (0.867, 0.882, 0.906)
SUPERFICIE: Color = (0.953, 0.961, 0.973)
ACCION: Color = (0.055, 0.227, 0.682)
ESTADOS: dict[str, tuple[Color, Color]] = {  # (texto, fondo)
    "exito": ((0.110, 0.478, 0.322), (0.902, 0.957, 0.925)),
    "bug": ((0.706, 0.137, 0.188), (0.984, 0.914, 0.918)),
    "error": ((0.420, 0.247, 0.690), (0.941, 0.914, 0.984)),
    "aviso": ((0.541, 0.353, 0.043), (0.988, 0.945, 0.863)),
    "neutro": ((0.290, 0.318, 0.357), (0.953, 0.961, 0.973)),
}

# Estado del backend → (bandeja, etiqueta, clase de color, orden). Igual que la bandeja.
BANDEJA = {
    "bug_detectado": ("bug", "Posible bug en tu código", "bug", 0),
    "estancado": ("sin", "No se pudo generar la prueba", "error", 1),
    "rechazado_laundering": ("sin", "No se pudo generar la prueba", "error", 1),
    "sin_veredicto": ("sin", "No se pudo generar la prueba", "error", 1),
    "requiere_corrida_nueva": ("repetir", "Requiere corrida nueva", "aviso", 3),
    "aprobado": ("paso", "Pasó", "exito", 4),
}
MOTIVO_SIN_PRUEBA = {
    "estancado": "No se logró una prueba que pase después de todos los intentos.",
    "rechazado_laundering": "Las pruebas generadas debilitaban el criterio esperado y se rechazaron.",
    "sin_veredicto": "La verificación no terminó con un veredicto.",
}
ETAPAS = (
    ("planner", "Analizando"),
    ("generator", "Escribiendo pruebas"),
    ("reviewer", "Verificando"),
)
METRICA = {  # clave → nombre para personas
    "pass_rate": "Pruebas que pasan",
    "cobertura": "Cobertura de líneas y ramas",
    "iteraciones": "Intentos promedio por función",
    "costo": "Tokens de la corrida",
    "mutation_score": "Fortaleza de las pruebas",
}
CONTROL = {
    "ok": "En orden",
    "falla": "No cumple",
    "no_aplica": "No aplica",
    "pendiente": "Pendiente",
    "sin_dato": "Sin dato",
}

# Símbolo de QAgent (assets/logo/qagent-icono.svg), en coordenadas del SVG (100 x 100)
_SIMBOLO = (
    (
        (70.4, 9.47),
        (25.81, 9.47),
        (8.18, 27.32),
        (8.18, 65.12),
        (25.81, 82.97),
        (62.1, 82.97),
        (69.22, 74.93),
    ),
    ((69.22, 74.93), (81.6, 60.97)),
    ((69.22, 74.93), (61.0, 67.0)),
    ((69.22, 74.93), (85.39, 90.53)),
    ((40.0, 46.0), (55.89, 62.0), (91.82, 24.5)),
)


def _rgb(c: Color) -> str:
    return f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f}"


def _normalizar_para_pdf(texto: str) -> str:
    """Convierte símbolos fuera de Windows-1252 a equivalentes legibles en Type1."""
    reemplazos = {
        "≥": ">=",
        "≤": "<=",
        "→": "->",
        "✅": "[OK]",
        "❌": "[NO]",
        "☑️": "[OK]",
        "⚠️": "[!]",
        "♻": "",
        "↻": "",
        "★": "*",
        "—": "-",
        "–": "-",
        "…": "...",
    }
    for orig, dest in reemplazos.items():
        texto = texto.replace(orig, dest)
    return texto


def _escapar_literal_pdf(texto: str) -> str:
    """Codifica una cadena en literal PDF con escapes octales para caracteres no ASCII."""
    normalizado = _normalizar_para_pdf(texto).replace("\t", "    ")
    datos = normalizado.encode("cp1252", errors="replace")
    partes: list[str] = []
    for byte in datos:
        if byte == 0x5C:  # \
            partes.append("\\\\")
        elif byte == 0x28:  # (
            partes.append("\\(")
        elif byte == 0x29:  # )
            partes.append("\\)")
        elif 32 <= byte <= 126:
            partes.append(chr(byte))
        elif byte >= 128:
            partes.append(f"\\{byte:03o}")
    return "".join(partes)


def _decodificar_literal_pdf(cuerpo: str) -> str:
    """Inversa de `_escapar_literal_pdf` para pruebas y auditoría."""
    salida = bytearray()
    i = 0
    n = len(cuerpo)
    while i < n:
        ch = cuerpo[i]
        if ch == "\\" and i + 1 < n:
            sig = cuerpo[i + 1]
            if sig in "\\()":
                salida.append(ord(sig))
                i += 2
                continue
            if i + 4 <= n and all(c in "01234567" for c in cuerpo[i + 1 : i + 4]):
                salida.append(int(cuerpo[i + 1 : i + 4], 8))
                i += 4
                continue
        salida.append(ord(ch) if ord(ch) < 256 else ord("?"))
        i += 1
    return bytes(salida).decode("cp1252", errors="replace")


def _envolver_linea(texto: str, max_caracteres: int = 92) -> list[str]:
    """Envuelve una línea larga respetando palabras."""
    if len(texto) <= max_caracteres:
        return [texto]
    palabras = texto.split(" ")
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        while len(palabra) > max_caracteres:
            if actual:
                lineas.append(actual)
                actual = ""
            lineas.append(palabra[:max_caracteres])
            palabra = palabra[max_caracteres:]
        if not actual:
            actual = palabra
        elif len(actual) + 1 + len(palabra) <= max_caracteres:
            actual = f"{actual} {palabra}"
        else:
            lineas.append(actual)
            actual = palabra
    if actual or not lineas:
        lineas.append(actual)
    return lineas


def _caracteres_por_linea(ancho: float, tamano: float, mono: bool = False) -> int:
    """Caracteres aproximados que caben en `ancho` (Helvetica ≈ 0,5 em; Courier 0,6 em)."""
    return max(10, int(ancho / (tamano * (0.6 if mono else 0.5))))


class _Lienzo:
    """Va escribiendo de arriba abajo y abre páginas nuevas cuando no hay sitio."""

    def __init__(self, titulo_pie: str) -> None:
        self.titulo_pie = titulo_pie
        self.paginas: list[list[str]] = []
        self.ops: list[str] = []
        self.y = ARRIBA
        self._nueva_pagina()

    # -- páginas --
    def _nueva_pagina(self) -> None:
        if self.ops:
            self.paginas.append(self.ops)
        self.ops = []
        self.y = ARRIBA

    def asegurar(self, alto: float) -> None:
        if self.y - alto < ABAJO:
            self._nueva_pagina()

    def cerrar(self) -> list[list[str]]:
        self.paginas.append(self.ops)
        total = len(self.paginas)
        for numero, ops in enumerate(self.paginas, start=1):
            ops[:0] = self._cabecera(numero == 1)
            ops.extend(self._pie(numero, total))
        return self.paginas

    def _cabecera(self, primera: bool) -> list[str]:
        if primera:
            return []
        ops = self._simbolo(MARGEN, ALTO - 40, 14.0)
        ops += self._texto_ops(MARGEN + 20, ALTO - 37, "QAgent", 10, "F2", TEXTO)
        ops += self._texto_ops(
            ANCHO - MARGEN - 220, ALTO - 37, self.titulo_pie, 8.5, "F1", TEXTO_3
        )
        ops.append(
            f"{_rgb(BORDE)} RG 0.6 w {MARGEN} {ALTO - 50} m {ANCHO - MARGEN} {ALTO - 50} l S"
        )
        return ops

    def _pie(self, numero: int, total: int) -> list[str]:
        ops = [f"{_rgb(BORDE)} RG 0.6 w {MARGEN} 40 m {ANCHO - MARGEN} 40 l S"]
        ops += self._texto_ops(
            MARGEN,
            28,
            f"Generado por QAgent {__version__} · el código se verificó en un entorno aislado, sin internet",
            7.5,
            "F1",
            TEXTO_3,
        )
        ops += self._texto_ops(
            ANCHO - MARGEN - 60, 28, f"Página {numero} de {total}", 7.5, "F1", TEXTO_3
        )
        return ops

    # -- primitivas --
    @staticmethod
    def _texto_ops(
        x: float, y: float, texto: str, tamano: float, fuente: str, color: Color
    ) -> list[str]:
        return [
            f"BT {_rgb(color)} rg /{fuente} {tamano} Tf {x:.1f} {y:.1f} Td ({_escapar_literal_pdf(texto)}) Tj ET"
        ]

    def texto(
        self,
        x: float,
        y: float,
        texto: str,
        tamano: float = 10,
        fuente: str = "F1",
        color: Color = TEXTO,
    ) -> None:
        self.ops += self._texto_ops(x, y, texto, tamano, fuente, color)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        relleno: Color | None = None,
        borde: Color | None = None,
    ) -> None:
        if relleno:
            self.ops.append(f"{_rgb(relleno)} rg {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")
        if borde:
            self.ops.append(
                f"{_rgb(borde)} RG 0.6 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S"
            )

    @staticmethod
    def _simbolo(x: float, y: float, tamano: float, color: Color = TEXTO) -> list[str]:
        """El símbolo de QAgent con su esquina superior izquierda en (x, y + tamano)."""
        s = tamano / 100.0
        trazos = []
        for trazo in _SIMBOLO:
            (x0, y0), *resto = trazo
            trazos.append(
                f"{x0:.2f} {y0:.2f} m "
                + " ".join(f"{a:.2f} {b:.2f} l" for a, b in resto)
                + " S"
            )
        return [
            f"q {_rgb(color)} RG 7.6 w 2 J 0 j {s:.4f} 0 0 {-s:.4f} {x:.1f} {y + tamano:.1f} cm "
            + " ".join(trazos)
            + " Q"
        ]

    def simbolo(self, x: float, y: float, tamano: float, color: Color = TEXTO) -> None:
        self.ops += self._simbolo(x, y, tamano, color)

    # -- bloques de texto que paginan solos --
    def parrafo(
        self,
        texto: str,
        tamano: float = 10,
        fuente: str = "F1",
        color: Color = TEXTO,
        x: float = MARGEN,
        ancho: float = CONTENIDO,
        interlineado: float = 1.45,
        mono: bool = False,
    ) -> None:
        por_linea = _caracteres_por_linea(ancho, tamano, mono)
        for bruta in str(texto).splitlines() or [""]:
            for linea in _envolver_linea(bruta, por_linea) or [""]:
                self.asegurar(tamano * interlineado)
                self.y -= tamano * interlineado
                self.texto(x, self.y, linea, tamano, fuente, color)

    def espacio(self, alto: float) -> None:
        self.y -= alto

    def titulo_seccion(self, texto: str) -> None:
        self.asegurar(44)
        self.espacio(18)
        self.texto(MARGEN, self.y - 14, texto, 14, "F2", TEXTO)
        self.y -= 22
        self.ops.append(
            f"{_rgb(BORDE)} RG 0.6 w {MARGEN} {self.y:.1f} m {ANCHO - MARGEN} {self.y:.1f} l S"
        )
        self.espacio(4)

    def chip(self, x: float, y: float, texto: str, clase: str) -> float:
        """Etiqueta de estado (texto + fondo suave). Devuelve su ancho."""
        fg, bg = ESTADOS.get(clase, ESTADOS["neutro"])
        ancho = len(texto) * 8.5 * 0.52 + 14
        self.rect(x, y - 4, ancho, 15, relleno=bg)
        self.texto(x + 7, y, texto, 8.5, "F2", fg)
        return ancho

    def caja_codigo(
        self, texto: str, etiqueta: str | None = None, tamano: float = 7.5
    ) -> None:
        """Bloque monoespaciado sobre fondo gris; se parte entre páginas si hace falta."""
        if etiqueta:
            self.asegurar(30)
            self.parrafo(etiqueta, 8.5, "F2", TEXTO_2)
            self.espacio(2)
        por_linea = _caracteres_por_linea(CONTENIDO - 16, tamano, mono=True)
        lineas = [
            ln
            for bruta in str(texto).splitlines()
            for ln in (_envolver_linea(bruta, por_linea) or [""])
        ]
        alto_linea = tamano * 1.4
        i = 0
        while i < len(lineas):
            self.asegurar(alto_linea * 2 + 10)
            cabe = max(1, int((self.y - ABAJO - 10) // alto_linea))
            tramo = lineas[i : i + cabe]
            alto = len(tramo) * alto_linea + 10
            self.rect(MARGEN, self.y - alto, CONTENIDO, alto, relleno=SUPERFICIE)
            y = self.y - 5
            for linea in tramo:
                y -= alto_linea
                self.texto(MARGEN + 8, y + 2, linea, tamano, "F3", TEXTO)
            self.y -= alto + 4
            i += len(tramo)


# ---------------------------------------------------------------------------------------


def _clase_bandeja(f: dict[str, Any]) -> tuple[str, str, str, int]:
    return BANDEJA.get(str(f.get("estado")), BANDEJA["sin_veredicto"])


def _nombre(f: dict[str, Any]) -> str:
    return str(f.get("identificador") or f.get("funcion") or "Función sin nombre")


def _ejecucion_final(f: dict[str, Any]) -> dict[str, Any] | None:
    con = [i for i in (f.get("intentos") or []) if i.get("ejecucion")]
    return con[-1]["ejecucion"] if con else None


def _caso_que_falla(ej: dict[str, Any] | None) -> dict[str, Any] | None:
    for c in (ej or {}).get("casos") or []:
        if c.get("resultado") in ("fallo", "error") and (
            c.get("esperado") is not None or c.get("obtenido") is not None
        ):
            return c
    return None


def _explicacion(f: dict[str, Any]) -> str | None:
    intentos = f.get("intentos") or []
    if intentos and intentos[-1].get("feedback"):
        return str(intentos[-1]["feedback"])
    estado = str(f.get("estado"))
    if estado in MOTIVO_SIN_PRUEBA:
        return MOTIVO_SIN_PRUEBA[estado]
    if estado == "requiere_corrida_nueva":
        return "El código cambió desde que se guardó esta prueba: hay que generarla de nuevo."
    if estado == "aprobado":
        return "La prueba pasó en el entorno aislado."
    return None


def _pct(valor: Any) -> str:
    return "—" if valor is None else f"{round(float(valor))} %"


def _portada(
    lz: _Lienzo,
    datos: dict[str, Any],
    funciones: list[dict[str, Any]],
    limpiar: Callable[[str], str],
) -> None:
    lz.simbolo(MARGEN, ARRIBA - 4, 26.0)
    lz.texto(MARGEN + 34, ARRIBA + 4, "QAgent", 18, "F1", TEXTO)
    lz.texto(ANCHO - MARGEN - 150, ARRIBA + 6, "Informe de pruebas", 10, "F2", ACCION)
    lz.texto(
        ANCHO - MARGEN - 150,
        ARRIBA - 7,
        f"Corrida {datos['run_id']}",
        8.5,
        "F1",
        TEXTO_3,
    )
    lz.y = ARRIBA - 34

    bugs = [f for f in funciones if _clase_bandeja(f)[0] == "bug"]
    sin = [f for f in funciones if _clase_bandeja(f)[0] in ("sin", "repetir")]
    total = len(funciones)
    respuesta = respuesta_principal(
        bugs=len(bugs),
        primer_bug=_nombre(bugs[0]) if bugs else None,
        sin_prueba=len(sin),
        total=total,
        omitidos=len(datos.get("omitidos") or []),
        incompleta=corrida_incompleta(datos),
    )
    lz.parrafo(limpiar(respuesta), 20, "F2", TEXTO, interlineado=1.3)

    meta = [
        Path(str(datos.get("proyecto") or "")).name,  # solo el nombre, no la ruta
        "Python",
        str(datos.get("fecha") or "")[:16].replace("T", " "),
    ]
    if datos.get("rama"):
        meta.append(f"rama {datos['rama']}")
    if datos.get("perfil"):
        meta.append(str(datos["perfil"]))
    if datos.get("es_simulado"):
        meta.append("IA simulada")
    duracion = datos.get("duracion_total_s")
    if isinstance(duracion, (int, float)) and not isinstance(duracion, bool):
        meta.append(
            f"{round(duracion * 1000)} ms"
            if duracion < 1
            else f"duración medida {duracion:.1f} s"
        )
    lz.espacio(4)
    lz.parrafo(limpiar(" · ".join(m for m in meta if m)), 9.5, "F1", TEXTO_2)
    if datos.get("motivo_fallo"):
        lz.parrafo(
            limpiar(f"La corrida se detuvo: {datos['motivo_fallo']}"),
            9.5,
            "F1",
            ESTADOS["aviso"][0],
        )

    # Cifras: pasaron, posibles bugs, cobertura y tokens (nunca costos)
    m = {x["clave"]: x for x in datos.get("metricas") or []}
    pasaron = sum(1 for f in funciones if _clase_bandeja(f)[0] == "paso")
    cob = m.get("cobertura", {})
    tokens = (m.get("costo") or {}).get("tokens_total")
    cifras = [
        ("Pasaron", f"{pasaron} / {total}", f"{total - pasaron} con algo por revisar"),
        ("Posibles bugs", str(len(bugs)), f"En {len(bugs)} de {total}"),
        (
            "Cobertura",
            _pct(cob.get("lineas")),
            "Ramas no exigidas en Humo"
            if datos.get("perfil") == "Humo"
            else f"{_pct(cob.get('ramas'))} de las ramas",
        ),
        (
            "Tokens de la corrida",
            "—" if tokens is None else f"{int(tokens):,}".replace(",", "."),
            "Sumando las tres etapas",
        ),
    ]
    lz.espacio(14)
    ancho = (CONTENIDO - 3 * 10) / 4
    alto = 60.0
    lz.asegurar(alto)
    y = lz.y - alto
    for i, (etq, valor, sub) in enumerate(cifras):
        x = MARGEN + i * (ancho + 10)
        lz.rect(x, y, ancho, alto, relleno=SUPERFICIE)
        lz.texto(x + 10, y + alto - 16, etq, 8, "F1", TEXTO_2)
        lz.texto(
            x + 10,
            y + 22,
            valor,
            17,
            "F2",
            ESTADOS["bug"][0] if etq == "Posibles bugs" and bugs else TEXTO,
        )
        lz.texto(x + 10, y + 9, limpiar(sub), 7, "F1", TEXTO_3)
    lz.y = y - 6


def _metas(lz: _Lienzo, datos: dict[str, Any]) -> None:
    lz.titulo_seccion("Metas de calidad")
    for mt in datos.get("metricas") or []:
        lz.asegurar(24)
        y = lz.y - 16
        nombre = METRICA.get(mt.get("clave"), mt.get("nombre", ""))
        if mt.get("clave") == "mutation_score" and mt.get("criticas") is not None:
            nombre = f"{nombre} ({mt['criticas']} críticas)"
        es_tokens = mt.get("clave") == "costo"
        resultado = (
            f"{int(mt.get('tokens_total') or 0):,} tokens".replace(",", ".")
            if es_tokens
            else str(mt.get("resultado", ""))
        )
        lz.texto(MARGEN, y, nombre, 9.5, "F1", TEXTO)
        lz.texto(MARGEN + 210, y, resultado, 9.5, "F2", TEXTO)
        if not es_tokens:
            lz.texto(MARGEN + 340, y, str(mt.get("meta", "")), 8.5, "F1", TEXTO_3)
            lz.chip(
                ANCHO - MARGEN - 76,
                y,
                "Cumple" if mt.get("cumple") else "No cumple",
                "exito" if mt.get("cumple") else "bug",
            )
        else:
            lz.texto(MARGEN + 340, y, "Informativo", 8.5, "F1", TEXTO_3)
        lz.ops.append(
            f"{_rgb(BORDE)} RG 0.4 w {MARGEN} {y - 7:.1f} m {ANCHO - MARGEN} {y - 7:.1f} l S"
        )
        lz.y = y - 8


def _prioridades(
    lz: _Lienzo, funciones: list[dict[str, Any]], limpiar: Callable[[str], str]
) -> None:
    bugs = [f for f in funciones if _clase_bandeja(f)[0] == "bug"][:3]
    if not bugs:
        return
    lz.titulo_seccion("Por dónde empezar")
    for n, f in enumerate(bugs, start=1):
        lz.asegurar(40)
        lz.espacio(4)
        lz.texto(MARGEN, lz.y - 11, f"Prioridad {n}", 8, "F2", ACCION)
        lz.y -= 14
        lz.parrafo(
            limpiar(f"Corrige {_nombre(f)} · {f.get('modulo', '')}"), 10, "F2", TEXTO
        )
        explicacion = _explicacion(f)
        if explicacion:
            lz.parrafo(limpiar(explicacion.split("\n")[0]), 9, "F1", TEXTO_2)


def _datos_corrida(
    lz: _Lienzo, datos: dict[str, Any], limpiar: Callable[[str], str]
) -> None:
    lz.titulo_seccion("Datos de la corrida")
    filas: list[tuple[str, str]] = []
    modelos = datos.get("modelos") or {}
    for clave, etapa in ETAPAS:
        info = modelos.get(clave) or {}
        if info.get("modelo"):
            filas.append((etapa, f"{info['modelo']} ({info.get('proveedor', '')})"))
    specs = (datos.get("specs") or {}).get("texto") or ""
    specs = specs.split(" · guardados en")[0]
    if specs:
        filas.append(("Trabajo del análisis", specs))
    if datos.get("texto_categorias"):
        filas.append(("Casos planificados", str(datos["texto_categorias"])))
    filas.append(
        (
            "Funciones y endpoints",
            f"{datos.get('total_funciones', 0)} revisados · {datos.get('criticas', 0)} críticos",
        )
    )
    for etq, valor in filas:
        lz.asegurar(16)
        y0 = lz.y
        lz.texto(MARGEN, y0 - 12, etq, 9, "F1", TEXTO_2)
        lz.parrafo(
            limpiar(valor), 9, "F1", TEXTO, x=MARGEN + 150, ancho=CONTENIDO - 150
        )
        lz.espacio(3)


def _resultado_funcion(
    lz: _Lienzo, f: dict[str, Any], opts: dict[str, bool], limpiar: Callable[[str], str]
) -> None:
    _, etiqueta, clase, _orden = _clase_bandeja(f)
    lz.asegurar(70)
    lz.espacio(12)
    lz.ops.append(
        f"{_rgb(BORDE)} RG 0.6 w {MARGEN} {lz.y:.1f} m {ANCHO - MARGEN} {lz.y:.1f} l S"
    )
    lz.espacio(4)
    lz.parrafo(limpiar(_nombre(f)), 12, "F4", TEXTO, ancho=CONTENIDO - 170, mono=True)
    lz.chip(
        ANCHO - MARGEN - (len(etiqueta) * 8.5 * 0.52 + 14), lz.y + 2, etiqueta, clase
    )
    detalle = [str(f.get("modulo") or "")]
    if f.get("firma") or f.get("manejador"):
        detalle.append(str(f.get("firma") or f.get("manejador")))
    if f.get("critical"):
        detalle.append("crítica")
    lz.parrafo(limpiar(" · ".join(d for d in detalle if d)), 8.5, "F1", TEXTO_3)

    explicacion = _explicacion(f)
    if explicacion:
        lz.espacio(3)
        lz.parrafo(limpiar(explicacion), 9.5, "F1", TEXTO)

    ej = _ejecucion_final(f)
    fallo = _caso_que_falla(ej)
    if fallo:
        lz.espacio(4)
        lz.caja_codigo(
            limpiar(
                f"Esperado: {fallo.get('esperado') if fallo.get('esperado') is not None else '—'}\nObtenido: {fallo.get('obtenido') if fallo.get('obtenido') is not None else '—'}"
            ),
            "Esperado frente a obtenido",
            8.5,
        )
        if fallo.get("archivo"):
            lz.parrafo(
                limpiar(
                    f"Dónde: {fallo['archivo']}:{fallo.get('linea')}"
                    + (f" → {fallo['codigo']}" if fallo.get("codigo") else "")
                ),
                8.5,
                "F3",
                TEXTO_2,
                mono=True,
            )
    sin_cubrir = (ej or {}).get("lineas_sin_cubrir")
    if isinstance(sin_cubrir, list):
        lz.parrafo(
            "Código sin probar · líneas " + ", ".join(str(int(n)) for n in sin_cubrir)
            if sin_cubrir
            else "Todas las líneas de la función se ejecutaron en las pruebas",
            8.5,
            "F1",
            ESTADOS["aviso" if sin_cubrir else "exito"][0],
        )

    datos = []
    if f.get("iteraciones"):
        datos.append(f"{f['iteraciones']} de 3 intentos")
    if f.get("cobertura_lineas") is not None:
        datos.append(
            f"cobertura {_pct(f['cobertura_lineas'])} de líneas"
            + (
                f" y {_pct(f['cobertura_ramas'])} de ramas"
                if f.get("cobertura_ramas") is not None
                else ""
            )
        )
    if f.get("mutation_score") is not None:
        datos.append(f"fortaleza {_pct(f['mutation_score'])}")
    if datos:
        lz.parrafo(" · ".join(datos), 8.5, "F1", TEXTO_3)

    intentos = f.get("intentos") or []
    if any(i.get("laundering_detectado") for i in intentos):
        lz.parrafo(
            "Criterio original conservado: se bloqueó un intento de debilitar esta prueba."
            + (" El posible bug sigue visible." if clase == "bug" else ""),
            8.5,
            "F2",
            ESTADOS["aviso"][0],
        )

    controles = f.get("controles") or []
    if controles:
        en_orden = sum(1 for c in controles if c.get("estado") == "ok")
        lz.espacio(3)
        lz.parrafo(
            f"Controles de integridad: {en_orden} de {len(controles)} en orden",
            8.5,
            "F2",
            TEXTO_2,
        )
        for c in controles:
            if c.get("estado") != "ok":
                lz.parrafo(
                    limpiar(
                        f"· {c.get('etiqueta', '')}: {c.get('nota') or CONTROL.get(c.get('estado'), '')}"
                    ),
                    8.5,
                    "F1",
                    TEXTO_2,
                    x=MARGEN + 8,
                    ancho=CONTENIDO - 8,
                )

    vivos = (f.get("mutacion") or {}).get("sobrevivientes") or []
    if vivos:
        lz.parrafo(
            f"Cambios introducidos a propósito que las pruebas no detectaron ({len(vivos)}):",
            8.5,
            "F2",
            TEXTO_2,
        )
        for s in vivos:
            lz.parrafo(
                limpiar(
                    f"· línea {s.get('linea', '—')}: {s.get('cambio') or s.get('mutante') or ''}"
                ),
                8,
                "F3",
                TEXTO_2,
                x=MARGEN + 8,
                ancho=CONTENIDO - 8,
                mono=True,
            )

    if opts.get("contratos"):
        casos = (f.get("contrato_http") or {}).get("casos") or []
        for c in casos:
            lz.parrafo(
                limpiar(
                    f"Caso del contrato · {c.get('descripcion') or c.get('id') or ''}"
                ),
                8.5,
                "F2",
                TEXTO_2,
            )
            lz.caja_codigo(
                limpiar(
                    f"Petición: {c.get('peticion')}\nRespuesta esperada: {c.get('respuesta_esperada')}"
                ),
                tamano=7.5,
            )
        ejecutados = (ej or {}).get("casos") or []
        if ejecutados:
            pasaron = sum(1 for c in ejecutados if c.get("resultado") == "paso")
            lz.parrafo(
                f"Casos ejecutados: {pasaron} de {len(ejecutados)} pasaron",
                8.5,
                "F2",
                TEXTO_2,
            )
            for c in ejecutados:
                resultado = {
                    "paso": "Pasó",
                    "fallo": "Falló",
                    "error": "Error",
                    "omitido": "Omitido",
                }.get(c.get("resultado"), "—")
                lz.parrafo(
                    limpiar(f"· [{resultado.upper()}] {c.get('nombre', '')}"),
                    8,
                    "F3",
                    TEXTO_2,
                    x=MARGEN + 8,
                    ancho=CONTENIDO - 8,
                    mono=True,
                )

    if opts.get("codigo") and f.get("codigo"):
        lz.espacio(3)
        lz.caja_codigo(limpiar(str(f["codigo"])), "Prueba generada")
    if opts.get("trazas"):
        traza = f.get("traza") or (fallo or {}).get("traza")
        if traza:
            lz.caja_codigo(limpiar(str(traza)), "Detalle técnico (salida de pytest)", 7)


def construir_pdf(
    datos: dict[str, Any], opts: dict[str, bool], limpiar: Callable[[str], str]
) -> bytes:
    """Construye el PDF del informe con la identidad del rediseño.

    Args:
        datos: salida de `datos_informe` (ya sin secretos).
        opts: `normalizar_opciones` (detalle, trazas, codigo, contratos).
        limpiar: quita secretos de cada texto antes de escribirlo (defensa extra).
    """
    funciones = sorted(
        datos.get("funciones") or [],
        key=lambda f: (_clase_bandeja(f)[3], not f.get("critical")),
    )
    lz = _Lienzo(f"Informe de la corrida {datos['run_id']}")
    _portada(lz, datos, funciones, limpiar)
    _metas(lz, datos)
    _prioridades(lz, funciones, limpiar)
    _datos_corrida(lz, datos, limpiar)

    if opts.get("detalle"):
        lz.titulo_seccion("Resultados por función y endpoint")
        lz.parrafo(
            "Primero lo que requiere atención; las críticas, antes.", 8.5, "F1", TEXTO_3
        )
        for f in funciones:
            _resultado_funcion(lz, f, opts, limpiar)

    from qagent.storage.exportar_informe import _filas_entorno

    entorno = _filas_entorno(datos)
    if entorno:
        lz.titulo_seccion("Datos de la ejecución (anexo técnico)")
        for etq, valor in entorno:
            if etq == "Comando" and not opts.get("trazas"):
                continue
            lz.asegurar(16)
            y0 = lz.y
            lz.texto(MARGEN, y0 - 12, etq, 9, "F1", TEXTO_2)
            lz.parrafo(
                limpiar(valor), 9, "F1", TEXTO, x=MARGEN + 150, ancho=CONTENIDO - 150
            )
            lz.espacio(2)

    return _ensamblar(lz.cerrar(), str(datos["run_id"]))


def _ensamblar(paginas: list[list[str]], run_id: str) -> bytes:
    """Une las páginas en un PDF-1.4 con fuentes estándar y metadatos."""
    objetos: list[bytes] = []

    def agregar(cuerpo: str | bytes) -> int:
        objetos.append(cuerpo.encode("latin-1") if isinstance(cuerpo, str) else cuerpo)
        return len(objetos)

    fuentes = {
        "F1": agregar(
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        ),
        "F2": agregar(
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
        ),
        "F3": agregar(
            "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
        ),
        "F4": agregar(
            "<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>"
        ),
    }
    recursos = (
        "<< /Font << "
        + " ".join(f"/{k} {v} 0 R" for k, v in fuentes.items())
        + " >> >>"
    )
    # El nodo /Pages va justo después de cada página (flujo + página): se calcula su número.
    id_paginas = len(objetos) + 2 * len(paginas) + 1
    ids_pagina = []
    for ops in paginas:
        flujo = "\n".join(ops).encode("latin-1", errors="replace")
        id_flujo = agregar(
            b"<< /Length "
            + str(len(flujo)).encode()
            + b" >>\nstream\n"
            + flujo
            + b"\nendstream"
        )
        ids_pagina.append(
            agregar(
                f"<< /Type /Page /Parent {id_paginas} 0 R /MediaBox [0 0 {ANCHO:.0f} {ALTO:.0f}] "
                f"/Resources {recursos} /Contents {id_flujo} 0 R >>"
            )
        )
    assert (
        agregar(
            "<< /Type /Pages /Kids ["
            + " ".join(f"{i} 0 R" for i in ids_pagina)
            + f"] /Count {len(ids_pagina)} >>"
        )
        == id_paginas
    )
    id_catalogo = agregar(f"<< /Type /Catalog /Pages {id_paginas} 0 R >>")
    id_info = agregar(
        f"<< /Title ({_escapar_literal_pdf('Informe de pruebas · corrida ' + run_id)}) /Producer (QAgent) >>"
    )

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{numero} 0 obj\n".encode() + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for pos in posiciones:
        salida += f"{pos:010d} 00000 n \n".encode()
    salida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root {id_catalogo} 0 R /Info {id_info} 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(salida)

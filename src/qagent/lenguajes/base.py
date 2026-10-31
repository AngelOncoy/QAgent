"""Interfaz común de los adaptadores por lenguaje (EN-17).

Un adaptador reúne **todo lo que depende del lenguaje** del código del usuario:
detectarlo, analizarlo estáticamente, armar el comando de pruebas, describir el
entorno del sandbox, interpretar el informe de la ejecución y validar el test
generado (sintaxis y Assertion Laundering). El orquestador, el Planner, el
Generator y el Reviewer son compartidos: hablan con el adaptador y con los
contratos versionados, nunca con un analizador o un runner concreto.

Reglas que todo adaptador cumple (AGENTS.md):

* ``analizar`` es **estático**: no importa, compila ni ejecuta el código del usuario.
  Si un lenguaje necesita su propio parser, la decisión se documenta en un ADR.
* ``comando_pruebas`` se ejecuta solo dentro del sandbox.
* La lógica no depende de la interfaz: este paquete no importa ``qagent.app``.

Ver ``src/qagent/lenguajes/README.md`` para implementar un lenguaje nuevo.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import NotImplementedType
from typing import Any, ClassVar, Protocol

Estructura = dict[str, Any]


@dataclass(frozen=True)
class Deteccion:
    """Indicios de que un proyecto está escrito en un lenguaje.

    Atributos:
        lenguaje: valor de ``lenguaje`` en los contratos (``python``, ``java``...).
        archivos: cantidad de archivos fuente con las extensiones del lenguaje.
        marcadores: archivos de proyecto encontrados (``pyproject.toml``, ``pom.xml``...).
        confianza: proporción (0 a 1) de los archivos fuente del proyecto que son de
            este lenguaje. La calcula el registro al comparar todos los lenguajes.
    """

    lenguaje: str
    archivos: int
    marcadores: tuple[str, ...] = ()
    confianza: float = 0.0


@dataclass(frozen=True)
class EntornoSandbox:
    """Lo que el sandbox necesita para ejecutar las pruebas de un lenguaje.

    Atributos:
        imagen: imagen Docker base (sin red, efímera).
        paquetes_base: herramientas que la imagen ya trae (runner, cobertura...).
        dir_tests: carpeta del contenedor donde se copian los tests.
        dir_salida: carpeta del contenedor donde queda el informe.
        informe: nombre del archivo de resultados dentro de ``dir_salida``.
    """

    imagen: str
    paquetes_base: tuple[str, ...]
    dir_tests: str
    dir_salida: str
    informe: str


@dataclass(frozen=True)
class ComandoSandbox:
    """Comando que el sandbox ejecuta, con sus variables de entorno.

    Atributos:
        comando: argumentos del comando (ej. ``["python", "-c", "..."]``).
        entorno: variables de entorno extra para el contenedor.
    """

    comando: list[str]
    entorno: dict[str, str] = field(default_factory=dict)


class ComparacionAserciones(Protocol):
    """Resultado mínimo de comparar las aserciones de dos versiones de un test.

    El de Python (``qagent.analysis.ResultadoComparacion``) ya lo cumple; cada
    lenguaje puede devolver su propio tipo con más detalle.
    """

    es_laundering: bool
    resumen: str


@dataclass(frozen=True)
class Clasificacion:
    """Qué dice la salida del runner, según las reglas del lenguaje (#168).

    Atributos:
        tipo: ``entorno`` (falla del entorno, reintentar no sirve), ``bug_respuesta``
            (la respuesta del endpoint no cumple lo declarado), ``error_test`` (el
            test está mal) o ``fallo_asercion`` (una aserción legítima falló).
        detalle: texto para el feedback.
        motivo_sin_veredicto: fallo técnico que impide juzgar el código; None
            conserva las decisiones y los reintentos habituales.
    """

    tipo: str
    detalle: str
    motivo_sin_veredicto: str | None = None


class ReglasRevision(Protocol):
    """Lo que el Reviewer necesita saber del lenguaje de un test (#168)."""

    def error_de_sintaxis(self, codigo: str) -> str | None:
        """Texto del error si el test no se puede parsear; None si es válido."""

    def validar_oraculo(self, contrato: dict[str, Any], codigo: str) -> str | None:
        """Por qué el test no comprueba los valores del contrato; None si los comprueba."""

    def clasificar_salida(
        self, salida: str, contrato: dict[str, Any], raiz: Path
    ) -> Clasificacion | None:
        """Clasifica la salida del runner; None si no se reconoce."""

    def rango_de_objetivo(
        self, raiz: Path, modulo: str, nombre: str
    ) -> tuple[int, int] | None:
        """Primera y última línea del cuerpo de ``nombre`` en ``modulo``."""


class ReglasPlanificacion(Protocol):
    """Lo que el Planner necesita saber del lenguaje para pedir y filtrar casos (#168).

    Los prompts dicen al modelo cómo se escriben los casos en este lenguaje y los
    filtros descartan, sin IA, los casos cuyo oráculo la especificación no respalda.
    """

    motivo_caso_trivial: str
    motivo_omitida_trivial: str

    def prompt_funciones(self, modulo: dict[str, Any], humo: bool) -> str: ...

    def prompt_endpoints(
        self,
        modulo: dict[str, Any],
        endpoints: dict[str, dict[str, Any]],
        fuente: str | None,
        humo: bool,
    ) -> str: ...

    def preparar_caso(
        self, funcion: dict[str, Any], caso: dict[str, Any]
    ) -> dict[str, Any]: ...

    def es_caso_trivial(
        self, funcion: dict[str, Any], caso: dict[str, Any]
    ) -> bool: ...

    def motivo_limite_funcion(
        self, funcion: dict[str, Any], caso: dict[str, Any]
    ) -> str | None: ...

    def motivo_oraculo_funcion(
        self, funcion: dict[str, Any], caso: dict[str, Any]
    ) -> str | None: ...

    def aplicacion_principal(self, endpoints: Any) -> str: ...

    def dependencias_con_reemplazo(
        self, modulo: dict[str, Any], endpoint: dict[str, Any]
    ) -> list[dict[str, str]]: ...

    def motivo_rechazo_endpoint(
        self,
        endpoint: dict[str, Any],
        caso: dict[str, Any],
        modelos: dict[str, dict[str, Any]],
    ) -> str | None: ...

    def motivo_limite_endpoint(
        self,
        endpoint: dict[str, Any],
        caso: dict[str, Any],
        modelos: dict[str, dict[str, Any]],
    ) -> str | None: ...

    def faltantes_endpoint(
        self, endpoint: dict[str, Any], casos: list[dict[str, Any]]
    ) -> list[str]: ...


class NoImplementado(NotImplementedError):
    """Operación que el adaptador de un lenguaje todavía no implementa."""

    def __init__(self, lenguaje: str, operacion: str) -> None:
        self.lenguaje = lenguaje
        self.operacion = operacion
        super().__init__(
            f"El adaptador de {lenguaje} todavía no implementa '{operacion}'."
        )


class LanguageAdapter(ABC):
    """Contrato que cumple cada lenguaje soportado por QAgent.

    Atributos de clase (los declara cada adaptador):
        lenguaje: valor de ``lenguaje`` en los contratos (``contracts.LENGUAJES``).
        extensiones: extensiones de los archivos fuente, con punto (``.py``).
        marcadores: nombres de archivos de proyecto que delatan el lenguaje.
        frameworks_pruebas: frameworks de pruebas admitidos; el primero es el
            predeterminado. Deben estar en ``contracts.FRAMEWORKS_PRUEBAS``.
        frameworks_app: frameworks web cuyos endpoints se prueban
            (``contracts.FRAMEWORKS_APP``).

    Operaciones:
        * Detección: :meth:`detectar`.
        * Análisis e información estructural: :meth:`analizar` y :meth:`objetivos`.
        * Puntos de extensión: :meth:`comando_pruebas`, :meth:`entorno_sandbox`,
          :meth:`interpretar_resultados`, :meth:`leer_cobertura`,
          :meth:`archivo_de_prueba`, :meth:`comando_mutacion`,
          :meth:`validar_sintaxis` y :meth:`comparar_aserciones`.
    """

    lenguaje: ClassVar[str]
    #: Nombre para personas («TypeScript»); vacío = el lenguaje con mayúscula inicial.
    nombre: ClassVar[str] = ""
    #: Si el adaptador implementa todo lo que necesita una corrida (#168). Los
    #: lenguajes en desarrollo solo detectan y la app avisa que aún no se soportan.
    completo: ClassVar[bool] = True
    #: Permite calcular huellas estáticas aun cuando la generación no está completa.
    huellas_disponibles: ClassVar[bool] = False
    #: Nombre del motor que usa el adaptador, para los mensajes compartidos.
    motor_mutacion: ClassVar[str] = "mutación"
    #: Comprobación opcional de librerías del sistema propia del entorno Python.
    comprobar_librerias_sistema: ClassVar[bool] = False
    extensiones: ClassVar[tuple[str, ...]]
    marcadores: ClassVar[tuple[str, ...]] = ()
    frameworks_pruebas: ClassVar[tuple[str, ...]]
    frameworks_app: ClassVar[tuple[str, ...]] = ()

    @property
    def nombre_visible(self) -> str:
        """Nombre del lenguaje para los mensajes de la interfaz."""
        return self.nombre or self.lenguaje.capitalize()

    # --- Detección --------------------------------------------------------------

    def detectar(self, archivos: Sequence[str]) -> Deteccion | None:
        """Busca indicios del lenguaje en una lista de rutas relativas (POSIX).

        Es pura (no lee el disco) para poder probarla sin carpetas. Cuenta los
        archivos con las extensiones del lenguaje y los marcadores presentes.

        Returns:
            La detección, o ``None`` si no hay ningún indicio.
        """
        fuentes = sum(1 for a in archivos if self.es_fuente(a))
        nombres = {PurePosixPath(a).name for a in archivos}
        marcadores = tuple(m for m in self.marcadores if m in nombres)
        if not fuentes and not marcadores:
            return None
        return Deteccion(self.lenguaje, fuentes, marcadores)

    def es_fuente(self, archivo: str) -> bool:
        """Si ``archivo`` es un archivo fuente de este lenguaje."""
        return archivo.lower().endswith(self.extensiones)

    # --- Análisis e información estructural ------------------------------------

    @abstractmethod
    def analizar(self, raiz: str | os.PathLike[str]) -> Estructura:
        """Analiza estáticamente el proyecto, sin ejecutar nada.

        Returns:
            Estructura con ``lenguaje``, ``modulos`` (cada uno con ``ruta``,
            ``huella``, ``funciones`` y ``endpoints``), ``errores`` y ``resumen``:
            la misma forma que ``qagent.analysis.analizar_proyecto``.

        Raises:
            NotADirectoryError: si ``raiz`` no es una carpeta.
        """

    def objetivos(self, estructura: Estructura) -> list[dict[str, str]]:
        """Lista las funciones y endpoints que se pueden probar.

        Cada objetivo trae ``modulo``, ``tipo`` (``funcion`` o ``endpoint``) y
        ``objetivo``, con los mismos valores que usará el contrato del Planner. Los
        endpoints sin ruta resoluble se omiten.
        """
        encontrados: list[dict[str, str]] = []
        for modulo in estructura.get("modulos", []):
            ruta = modulo["ruta"]
            for funcion in modulo.get("funciones", []):
                encontrados.append(
                    {"modulo": ruta, "tipo": "funcion", "objetivo": funcion["nombre"]}
                )
            for endpoint in modulo.get("endpoints", []):
                if endpoint.get("objetivo"):
                    encontrados.append(
                        {
                            "modulo": ruta,
                            "tipo": "endpoint",
                            "objetivo": endpoint["objetivo"],
                        }
                    )
        return encontrados

    def motivo_endpoint_no_planificable(self, endpoint: dict[str, Any]) -> str | None:
        """Filtro estático opcional anterior al LLM; None conserva la planificación.

        El adaptador puede explicar que falta una declaración verificable. El
        Planner registra la omisión sin pedir a la IA que invente un resultado.
        """
        return None

    def aplicacion_de_endpoint(self, endpoint: dict[str, Any], principal: str) -> str:
        """Símbolo de aplicación por endpoint; por defecto usa el del módulo."""
        return principal

    def objetivo_de_cobertura(self, contrato: dict[str, Any]) -> str:
        """Identidad del cuerpo probado: manejador de endpoint o función del contrato."""
        return contrato.get("manejador") or contrato["objetivo"]

    # --- Puntos de extensión ----------------------------------------------------

    @property
    def framework_predeterminado(self) -> str:
        """Framework de pruebas que se usa si el contrato no indica otro."""
        return self.frameworks_pruebas[0]

    def elegir_framework(self, framework: str | None = None) -> str:
        """Devuelve ``framework`` si este lenguaje lo admite, o el predeterminado.

        Raises:
            ValueError: si el framework no corresponde al lenguaje.
        """
        if framework is None:
            return self.framework_predeterminado
        if framework not in self.frameworks_pruebas:
            opciones = ", ".join(self.frameworks_pruebas)
            raise ValueError(
                f"{self.lenguaje} no admite el framework '{framework}' ({opciones})."
            )
        return framework

    @abstractmethod
    def comando_pruebas(self, modulo: str, framework: str | None = None) -> list[str]:
        """Comando que el sandbox ejecuta para correr los tests con cobertura.

        Args:
            modulo: módulo o archivo cuyo código se mide.
            framework: framework de pruebas del contrato; ``None`` = predeterminado.
        """

    def modulo_cobertura(self, modulo: str) -> str:
        """Lo que ``comando_pruebas`` recibe para medir ``modulo`` (ruta del contrato).

        Por defecto la misma ruta; Python la convierte a nombre importable.
        """
        return modulo

    def variables_pruebas(self) -> dict[str, str]:
        """Variables de entorno extra del contenedor al correr las pruebas."""
        return {}

    def preparador_sandbox(self) -> Callable[[Path, Path], None] | None:
        """Preparación estática opcional sobre la copia y tests, antes del contenedor.

        None conserva la ejecución actual. Nunca se ejecuta código del usuario
        aquí; solo se disponen archivos y configuración del runner del lenguaje.
        """
        return None

    def lector_informe_sandbox(self) -> Callable[[Path], str | None] | None:
        """Lector opcional de informes del runner desde /out antes de la limpieza.

        None utiliza el archivo indicado por entorno_sandbox().informe.
        """
        return None

    def cobertura_de_objetivo(
        self, cobertura: dict[str, Any] | None, modulo: str, objetivo: str
    ) -> dict[str, float | None] | None | NotImplementedType:
        """Contadores exactos del objetivo; NotImplemented usa el cálculo por líneas.

        None significa que no hay medición del objetivo, sin sustituirla por
        cobertura de otros métodos del archivo.
        """
        return NotImplemented

    def clasificar_ejecucion(self, resultado: Any) -> Clasificacion | None:
        """Clasifica informes y etapas del runner; None conserva las reglas actuales."""
        return None

    @abstractmethod
    def entorno_sandbox(self) -> EntornoSandbox:
        """Imagen, herramientas y carpetas del sandbox para este lenguaje."""

    @abstractmethod
    def interpretar_resultados(self, informe: str) -> dict[str, Any]:
        """Convierte el informe del runner en totales y casos.

        Returns:
            ``total``, ``pasaron``, ``fallaron``, ``errores``, ``omitidos``,
            ``duracion_s``, ``inicio`` y ``casos``: la forma que usa
            ``review_result`` (ver ``qagent.sandbox.informe_pytest``).
        """

    @abstractmethod
    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Errores de sintaxis del test generado; lista vacía si es válido.

        No ejecuta el código: solo lo parsea.
        """

    @abstractmethod
    def comparar_aserciones(
        self, original: str, reparado: str
    ) -> ComparacionAserciones:
        """Detecta Assertion Laundering entre un test y su versión reparada."""

    @abstractmethod
    def leer_cobertura(
        self, dir_salida: str | os.PathLike[str]
    ) -> dict[str, Any] | None:
        """Lee el informe de cobertura que el runner dejó en ``dir_salida``.

        Returns:
            La cobertura en el formato JSON de coverage.py (``files`` y ``totals``),
            que es el que interpreta el Reviewer; ``None`` si no hay informe o no se
            puede leer. Cada lenguaje convierte su formato (v8, JaCoCo...) a este.
        """

    @abstractmethod
    def archivo_de_prueba(self, objetivo: str) -> str:
        """Nombre o ruta relativa del test de ``objetivo`` dentro de su carpeta aislada.

        Es el valor de ``archivo`` en ``generated_test.v2``.
        """

    def archivo_para_contrato(
        self, contrato: dict[str, Any], ruta_proyecto: Path | None
    ) -> str | None:
        """Ruta calculada con contexto estático; None conserva el nombre predeterminado.

        Permite respetar paquetes sin añadir reglas de un lenguaje al Generator.
        Los adaptadores existentes conservan su comportamiento y sus contratos.
        """
        return None

    @abstractmethod
    def comando_mutacion(self, modulo: str, funciones: list[str]) -> ComandoSandbox:
        """Comando que muta solo ``funciones`` de ``modulo`` dentro del sandbox.

        La mutación corre únicamente sobre funciones ``critical: true``.
        """

    # --- Agentes y regresión (#168) ---------------------------------------------
    # No son abstractos para que un lenguaje en desarrollo pueda registrarse sin
    # ellos; mientras falten, el adaptador no es ``completo`` y no se usa.

    def reglas_planificacion(self) -> ReglasPlanificacion:
        """Prompts y filtros de casos del Planner para este lenguaje."""
        raise NoImplementado(self.lenguaje, "reglas_planificacion")

    def prompt_generator(
        self,
        contrato: dict[str, Any],
        intento: int,
        feedback: str | None,
        ruta_proyecto: Path | None,
    ) -> str:
        """Prompt con el que el Generator pide el test de ``contrato``."""
        raise NoImplementado(self.lenguaje, "prompt_generator")

    def reglas_revision(self) -> ReglasRevision:
        """Sintaxis, oráculo y clasificación de la salida para el Reviewer."""
        raise NoImplementado(self.lenguaje, "reglas_revision")

    def validar_oraculo(
        self, contrato: dict[str, Any], codigo: str, ruta_proyecto: Path
    ) -> str | None:
        """Valida el oráculo con contexto opcional del proyecto, sin ejecutar código.

        Por defecto conserva las reglas existentes. Un lenguaje puede contrastar
        también su paquete, clase y dependencias con el análisis de la fuente.
        """
        return self.reglas_revision().validar_oraculo(contrato, codigo)

    def ejecutar_mutacion(self, *args: Any, **opciones: Any) -> Any:
        """Muta las funciones críticas en el sandbox (firma de ``sandbox.ejecutar_mutacion``).

        Solo sobre funciones ``critical: true``. Devuelve un ``ResultadoMutacion``.
        """
        raise NoImplementado(self.lenguaje, "ejecutar_mutacion")

    def huellas_de_archivo(self, fuente: str, relativa: str) -> dict[str, str] | None:
        """Huella de cada función y endpoint de un archivo fuente (HU-24, HU-25).

        Returns:
            ``objetivo -> huella``, o None si el archivo no se puede analizar.
        """
        raise NoImplementado(self.lenguaje, "huellas_de_archivo")

    def funciones_de_modulo(self, raiz: Path, modulo: str) -> list[dict[str, Any]]:
        """``nombre`` y ``linea`` de cada función de primer nivel de ``modulo``."""
        raise NoImplementado(self.lenguaje, "funciones_de_modulo")


class AdaptadorEnDesarrollo(LanguageAdapter):
    """Base de un lenguaje que ya se detecta pero aún no se analiza ni ejecuta.

    Cada operación pendiente lanza :class:`NoImplementado`. El responsable del
    lenguaje reemplaza estos métodos uno por uno sin tocar los componentes
    compartidos. Mientras sea ``completo = False``, la corrida no lo usa y la app
    avisa que el lenguaje aún no se soporta (#168).
    """

    completo: ClassVar[bool] = False

    def analizar(self, raiz: str | os.PathLike[str]) -> Estructura:
        raise NoImplementado(self.lenguaje, "analizar")

    def comando_pruebas(self, modulo: str, framework: str | None = None) -> list[str]:
        raise NoImplementado(self.lenguaje, "comando_pruebas")

    def entorno_sandbox(self) -> EntornoSandbox:
        raise NoImplementado(self.lenguaje, "entorno_sandbox")

    def interpretar_resultados(self, informe: str) -> dict[str, Any]:
        raise NoImplementado(self.lenguaje, "interpretar_resultados")

    def validar_sintaxis(self, codigo: str) -> list[str]:
        raise NoImplementado(self.lenguaje, "validar_sintaxis")

    def comparar_aserciones(
        self, original: str, reparado: str
    ) -> ComparacionAserciones:
        raise NoImplementado(self.lenguaje, "comparar_aserciones")

    def leer_cobertura(
        self, dir_salida: str | os.PathLike[str]
    ) -> dict[str, Any] | None:
        raise NoImplementado(self.lenguaje, "leer_cobertura")

    def archivo_de_prueba(self, objetivo: str) -> str:
        raise NoImplementado(self.lenguaje, "archivo_de_prueba")

    def comando_mutacion(self, modulo: str, funciones: list[str]) -> ComandoSandbox:
        raise NoImplementado(self.lenguaje, "comando_mutacion")

"""Banco de pruebas propio para evaluar la detección de bugs por parte de los agentes.

Contiene funciones tipadas y documentadas con docstrings que especifican
su comportamiento esperado. Algunas funciones contienen bugs sembrados intencionales.
"""


def calcular_descuento(precio: float, porcentaje: float) -> float:
    """Calcula el precio final tras aplicar un porcentaje de descuento.

    Args:
        precio: Monto original del producto, debe ser mayor o igual a 0.
        porcentaje: Porcentaje de descuento, valor entre 0 y 100 inclusive.

    Returns:
        float: Precio final con el descuento aplicado.

    Raises:
        ValueError: Si el precio es negativo o el porcentaje no está entre 0 y 100.
    """
    if precio < 0:
        raise ValueError("El precio no puede ser negativo.")
    if not (0 <= porcentaje <= 100):
        raise ValueError("El porcentaje debe estar entre 0 y 100.")

    # BUG SEMBRADO 1: Retorna solo el monto de descuento en lugar del precio final (precio - descuento)
    monto_descuento = precio * (porcentaje / 100.0)
    return monto_descuento


def clasificar_edad(edad: int) -> str:
    """Clasifica a una persona según su rango etario.

    Categorías:
        - "menor": edad menor estricta a 18 años (0 a 17 años).
        - "adulto": edad entre 18 y 64 años inclusive.
        - "adulto mayor": edad mayor o igual a 65 años.

    Args:
        edad: Años cumplidos, debe ser mayor o igual a 0.

    Returns:
        str: Categoría correspondiente ('menor', 'adulto', 'adulto mayor').

    Raises:
        ValueError: Si la edad es menor a 0.
    """
    if edad < 0:
        raise ValueError("La edad no puede ser negativa.")

    # BUG SEMBRADO 2: Error de frontera (off-by-one). Usa <= 18 en vez de < 18,
    # clasificando a los de 18 años como 'menor' cuando deberían ser 'adulto'.
    if edad <= 18:
        return "menor"
    elif edad <= 64:
        return "adulto"
    else:
        return "adulto mayor"


def buscar_elemento_mayor(numeros: list[int | float]) -> int | float:
    """Encuentra el valor numérico máximo en una lista.

    Args:
        numeros: Lista de números (enteros o flotantes), no debe estar vacía.

    Returns:
        int | float: El número de mayor valor en la lista.

    Raises:
        ValueError: Si la lista está vacía.
    """
    if not numeros:
        raise ValueError("La lista no puede estar vacía.")

    # BUG SEMBRADO 3: Inicializa el valor máximo en 0 en lugar del primer elemento.
    # Si la lista contiene solo números negativos (ej. [-10, -5, -20]),
    # retornará incorrectamente 0 en lugar de -5.
    maximo = 0
    for num in numeros:
        if num > maximo:
            maximo = num
    return maximo


def es_palindromo(texto: str) -> bool:
    """Verifica si una palabra o frase es un palíndromo.

    Ignora diferencias entre mayúsculas, minúsculas y espacios en blanco.

    Args:
        texto: Cadena a evaluar.

    Returns:
        bool: True si se lee igual en ambos sentidos, False en caso contrario.
    """
    limpio = "".join(c.lower() for c in texto if c.isalnum())
    return limpio == limpio[::-1]


def invertir_palabras(frase: str) -> str:
    """Invierte el orden de las palabras en una oración conservando espacios simples.

    Args:
        frase: Oración de entrada.

    Returns:
        str: Frase con el orden de las palabras invertido.
    """
    palabras = frase.split()
    return " ".join(reversed(palabras))


def formatear_moneda(cantidad: float, simbolo: str = "$") -> str:
    """Formatea una cantidad numérica a formato de moneda con dos decimales.

    Args:
        cantidad: Valor numérico a formatear.
        simbolo: Prefijo del símbolo de moneda (por defecto '$').

    Returns:
        str: Texto formateado, por ejemplo '$12.50'.
    """
    return f"{simbolo}{cantidad:.2f}"
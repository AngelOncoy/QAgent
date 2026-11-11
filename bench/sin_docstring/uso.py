from precios import aplicar_descuento, es_mayor_de_edad


def total_a_pagar(precio):
    # Quien llama usa el resultado como el precio que se cobra.
    return aplicar_descuento(precio, 20)


def puede_comprar_alcohol(edad):
    # Quien llama asume que a los 18 ya es mayor de edad.
    return es_mayor_de_edad(edad)

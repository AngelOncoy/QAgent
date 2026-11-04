"""Tienda con una API y reglas de negocio en el mismo proyecto."""

from fastapi import FastAPI

app = FastAPI()


def aplicar_cupon(total: float, cupon: str) -> float:
    """Descuenta 10 % con el cupón 'PROMO10' y 25 % con 'PROMO25'; otro cupón no cambia el total."""
    if cupon == "PROMO10":
        return total * 0.9
    if cupon == "PROMO25":
        return total * 0.75
    return total


def envio_gratis(total: float, es_socio: bool) -> bool:
    """El envío es gratis para socios o para totales de 100 o más."""
    return es_socio or total >= 100


@app.get("/precio/{producto_id}")
def precio_de(producto_id: int) -> dict:
    """Devuelve el precio del producto."""
    return {"id": producto_id, "precio": 9.99}


@app.post("/cupon", status_code=200)
def validar_cupon(cupon: str) -> dict:
    """Indica si el cupón existe."""
    return {"valido": cupon in {"PROMO10", "PROMO25"}}

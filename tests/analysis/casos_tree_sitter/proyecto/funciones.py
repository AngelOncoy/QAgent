"""Casos límite de firmas, docstrings y ramas (TA-16).

Este archivo no se formatea con ruff: el formato raro es justamente lo que se prueba.
"""
from __future__ import annotations

import os, sys as sistema
from typing import (Any, Callable,
    Optional, Union)
import typing as t
from collections import *

try:
    import ujson as json  # opcional
except ImportError:
    import json
else:
    pass
finally:
    VALOR_FINAL = 1

if sistema.version_info >= (3, 11):
    from tomllib import loads
else:
    loads = None

CONSTANTE = 10
x, y = 1, 2
z: int = 3
w: str
a = b = "doble"
contador = 0
contador += 1
lista_global = [1, 2]
lista_global[0] = 5
os.environ["X"] = "1"


def simple(a, b):
    return a + b


def con_tipos(a: int, b: "str" = 'hola', *args: int, c: float = 1.5, d, **kw: Any) -> Optional[int]:
    """Docstring de una línea."""
    return None


def multilinea(
    a: int,  # comentario dentro de la firma
    b: dict[str,   int] = {'x': 1, "y": 2},
    /,
    c: list[int] = [1,2,3],
    *,
    d: tuple = (1,),
    e: t.Optional[  str ] = None,
) -> tuple[int, ...]:
    '''
    Docstring con sangría.

        Línea más sangrada.
    Fin.
    '''
    return (a,)


def numeros(a=0x10, b=1_000, c=1e3, d=1.5e-3, e=0o17, f=0b101, g=3j, h=-1, i=+2, j=~3, k=1e400, l=0.0, m=10.0) -> None:
    pass


def cadenas(a="it's", b='dice "hola"', c="tab\there", d=b"bytes", e=r"raw\n", f="unié", g="a" "b", h=u"u", i="""triple""", j='\'', k="\\", l="nueva\nlinea", m="ñandú") -> None:
    "Docstring con comillas dobles simples."


def fstrings(a=f"x{1}", b=f"{CONSTANTE!r:>10}", c=f"{CONSTANTE=}", d=f"{{literal}}", e=f"{'anidada'}", f="a" f"b{CONSTANTE}") -> None:
    pass


def expresiones(a=lambda x, y=1: x + y, b=[i * 2 for i in range(3) if i], c={k: v for k, v in {}.items()}, d={1, 2}, e=(i for i in []), f=not True, g=1 if CONSTANTE else 2, h=(1 + 2) * 3, i=2 ** -1, j=(2 ** 3) ** 2, k=2 ** (3 ** 2), l=a or b and c, m=(a or b) and c, n=1 < 2 <= 3, o=x is not None, p=x not in [], q=[*lista_global], r={**{}}, s=lista_global[1:2], u=lista_global[::2], v=sistema.argv[0], w=(yield_ := 1), z=-(-1), aa=(1).real, bb=f(*[1], **{}), cc=f(a=1, *[2]), dd=~-1, ee=(lambda: 0)(), ff=x if y else (z if w else 0), gg=(), hh=(1, 2), ii={}, jj=[], kk=..., ll=None, mm=True, nn=a[1, 2], oo=a[(1, 2)], pp=a[()], qq=a[1:2, 3], rr=a @ b, ss=a // b % c, tt=a << 1 | b >> 2 ^ c & d, uu=-a ** 2, vv=(-a) ** 2, ww=not (a and b), xx=(not a) == b, yy=f(x for x in []), zz=f((x for x in []), 1)) -> Callable[[int, str], Union[int, None]]:
    pass


def anotaciones(a: int | None, b: list["Modelo"], c: Callable[..., Any], d: t.Dict[str, t.List[int]], e: 'Optional[int]' = None) -> int | str:
    return 1


async def asincrona(n: int) -> list[int]:
    """Async con ramas."""
    resultado = []
    async for i in generador():
        if i:
            resultado.append(i)
    async with recurso() as r:
        pass
    await asincrona(n - 1)
    return [i async for i in generador() if i > 1]


def ramas(x, y=None):
    if x:
        return 1
    elif y:
        return 2
    elif x and y:
        return 3
    else:
        for i in range(3):
            while i:
                i -= 1
            else:
                pass
        try:
            pass
        except (ValueError, KeyError) as e:
            pass
        except Exception:
            pass
        else:
            pass
        finally:
            pass
    valor = 1 if x else 2 if y else 3
    lista = [i for i in range(3) if i if i > 1 for j in range(2) if j]
    conjunto = {i for i in range(3) if i}
    dic = {i: i for i in range(3) if i}
    gen = list(i for i in range(3) if i)
    f = lambda q: 1 if q else 2
    match x:
        case 1 | 2:
            pass
        case [a, b, *resto] if a:
            pass
        case {"k": v}:
            pass
        case Punto(x=0):
            pass
        case _:
            pass

    def interna():
        if x:
            pass

    class Interna:
        def metodo(self):
            if x:
                pass

    return valor


def grupo_excepciones():
    try:
        pass
    except* ValueError:
        pass
    except* TypeError:
        pass


@decorador
@otro.decorador(1, clave="v")
def decorada(a: int) -> int:
    """Decorada."""
    return a


def _privada():
    return 1


def redefinida():
    """Primera."""


def redefinida(x):
    """Segunda."""


if CONSTANTE:
    def en_if(a: int = 1):
        """Dentro de un if de módulo."""
        return a
else:
    def en_else():
        pass

try:
    def en_try():
        pass
except Exception:
    def en_except():
        pass

with open(__file__) as archivo:
    def en_with():
        pass

for _i in range(1):
    def en_for():
        pass

while False:
    def en_while():
        pass

match CONSTANTE:
    case 10:
        def en_match():
            pass


def sin_docstring_bytes():
    b"no es docstring"
    return 1


def docstring_fstring():
    f"no es docstring {CONSTANTE}"


def docstring_concatenado():
    "uno " 'dos'


def docstring_vacio():
    """   """


def docstring_escapes():
    """Con \t tab, \\ barra y \x41 hex.
    Segunda línea con \N{GREEK SMALL LETTER ALPHA}.
    """


def docstring_raw():
    r"""Raw \d+ sin escapes."""


def llamadas_globales(a):
    print(CONSTANTE, os.path.join("a", "b"), json.dumps({}), loads, x)
    global contador
    contador = contador + 1
    nueva = z
    del nueva
    for CONSTANTE2 in lista_global:
        pass
    obj.attr = w
    lista_global.append(b)
    return simple(a, y) + con_tipos(1) + t.cast(int, a)


def sin_retorno(a: int, b: str):
    pass


def todo_tipado(a: int, *args: str, b: int = 1, **kw: float) -> None:
    pass


def vacios(*, a):
    pass


def solo_varargs(*args, **kwargs):
    pass


def posicional_solo(a, b=2, /, c=3):
    pass


def generador_func():
    yield 1
    yield from range(2)
    x = yield
    return (yield)


class Clase:
    """Las clases no son funciones públicas."""

    def metodo(self):
        return 1


def con_comentario_final(a):
    if a:
        return 1
    return 2
    # comentario final dentro del bloque

# comentario fuera


def ultima(
    a,
    b,
):
    return a

"""Los mundos: cada negocio con su propio calendario.

Pedido de Ivan (12/11/2026): "que sean dos mundos. Una persona cuando vaya a
entrar, que pueda elegir el calendario de Redexpres o el de Tienda Inglesa. Eso
lo harían las personas que tengan acceso a los dos; una persona que tenga
acceso a un solo mundo va directamente al único que tiene".

Un mundo es una clave fija que llevan las barras del calendario
(`calendario_barras.mundo`) y la lista de mundos que puede abrir cada persona
(`users.mundos`). Un superadmin abre todos.

El catálogo vive acá y, con los nombres y colores, en
`frontend/lib/mundos.ts`: si se agrega uno, va en los dos.
"""
from __future__ import annotations

from fastapi import HTTPException, status

MUNDO_POR_DEFECTO = "tienda_inglesa"

# clave -> nombre. El orden es el del selector.
MUNDOS: dict[str, str] = {
    "tienda_inglesa": "Tienda Inglesa",
    # Tienda Express es parte de Tienda Inglesa, pero lleva su calendario.
    "tienda_express": "Tienda Express",
    "redexpres": "Redexpres",
    "tienda_viajes": "Tienda Viajes",
    "tienda_farma": "Tienda Farma",
}


def es_mundo(clave: str) -> bool:
    return clave in MUNDOS


def mundos_de(usuario) -> list[str]:
    """Los mundos que puede abrir una persona, en el orden del catálogo."""
    if getattr(usuario, "is_superuser", False):
        return list(MUNDOS)
    propios = set(getattr(usuario, "mundos", None) or [])
    return [m for m in MUNDOS if m in propios]


def puede_abrir(usuario, mundo: str) -> bool:
    return mundo in mundos_de(usuario)


def exigir_mundo(usuario, mundo: str) -> str:
    """El mundo, si existe y la persona lo puede abrir. Si no, 422 o 403."""
    if not es_mundo(mundo):
        raise HTTPException(status_code=422, detail="Ese mundo no existe")
    if not puede_abrir(usuario, mundo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tenés acceso al calendario de {MUNDOS[mundo]}",
        )
    return mundo

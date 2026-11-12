"""Los mundos: cada negocio, con toda la plataforma para él solo.

Pedido de Ivan (12/11/2026): "Los mundos tienen que ser de toda la plataforma.
La persona que entra a ese mundo va a ver todo hecho para ese mundo". Quien
tiene acceso a varios elige al entrar; quien tiene uno solo "va directamente al
único mundo al que tiene acceso".

Un mundo es una clave fija. La llevan:

- cada persona, en la lista de los que puede abrir (`users.mundos`);
- lo que se guarda separado por negocio: las barras del calendario
  (`calendario_barras.mundo`) y los destinos de cenefas
  (`cenefa_destinos.mundo`).

Qué herramientas tiene cada mundo (la planilla de pedidos es de Redexpres, los
medios son de Tienda Inglesa...) es cosa del menú: está en
`frontend/lib/mundos.ts`. Acá se cuida lo que sí se guarda por mundo, para que
nadie lea ni escriba lo de un negocio que no es el suyo. Los permisos siguen
valiendo igual que siempre: el mundo dice DE QUÉ negocio, el permiso dice QUÉ
se puede hacer.

El catálogo vive acá y, con los nombres y colores, en `frontend/lib/mundos.ts`:
si se agrega uno, va en los dos.
"""
from __future__ import annotations

from fastapi import HTTPException, status

MUNDO_POR_DEFECTO = "tienda_inglesa"

# clave -> nombre. El orden es el del selector.
MUNDOS: dict[str, str] = {
    "tienda_inglesa": "Tienda Inglesa",
    # Para la empresa Tienda Express es parte de Tienda Inglesa; acá va aparte
    # porque tiene su propia web y va a tener acciones solo suyas.
    "tienda_express": "Tienda Express",
    "redexpres": "Redexpres",
    "tienda_viajes": "Tienda Viajes",
    "tienda_farma": "Tienda Farma",
}


def es_mundo(clave: str) -> bool:
    return clave in MUNDOS


def mundos_de(usuario) -> list[str]:
    """Los mundos a los que entra una persona, en el orden del catálogo.

    Nadie queda sin mundo: sin ninguno no podría entrar a la plataforma. A
    quien todavía no se le asignó ninguno (una cuenta creada por un script
    viejo, por ejemplo) le toca el de siempre, Tienda Inglesa. Para sacarle el
    acceso a alguien se lo desactiva, no se le vacía esta lista."""
    if getattr(usuario, "is_superuser", False):
        return list(MUNDOS)
    propios = set(getattr(usuario, "mundos", None) or [])
    return [m for m in MUNDOS if m in propios] or [MUNDO_POR_DEFECTO]


def puede_abrir(usuario, mundo: str) -> bool:
    return mundo in mundos_de(usuario)


def exigir_mundo(usuario, mundo: str) -> str:
    """El mundo, si existe y la persona puede entrar. Si no, 422 o 403."""
    if not es_mundo(mundo):
        raise HTTPException(status_code=422, detail="Ese mundo no existe")
    if not puede_abrir(usuario, mundo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tenés acceso a {MUNDOS[mundo]}",
        )
    return mundo


def mundos_iniciales(permisos, es_sucursal_de_redexpres: bool = False) -> list[str]:
    """Con qué mundos arranca una cuenta, según lo que puede hacer.

    Es la regla con la que la 0060 repartió a quienes ya estaban, y la que se
    usa al crear una cuenta nueva. Pura, para probarla sin base.

    - Un login de sucursal de Redexpres entra solo a Redexpres.
    - Quien tiene algún permiso de Redexpres entra a Redexpres: la planilla de
      pedidos vive ahí, y sin el mundo dejaría de verla.
    - Todos los demás entran a Tienda Inglesa, que es donde estaba todo. Solo
      queda afuera quien no tiene NADA más que permisos de Redexpres.
    """
    if es_sucursal_de_redexpres:
        return ["redexpres"]
    permisos = set(permisos or [])
    de_redexpres = {p for p in permisos if p.startswith("redexpres.")}
    mundos = []
    if not permisos or permisos - de_redexpres:
        mundos.append("tienda_inglesa")
    if de_redexpres:
        mundos.append("redexpres")
    return mundos

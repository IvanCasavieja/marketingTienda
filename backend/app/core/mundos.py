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

# Permisos de algo que está en todos los mundos (el chat de Don Tino): no dicen
# de qué negocio es la persona. Los 60 logins de sucursal de Redexpres tienen
# solo este (visto en una copia de producción el 15/11/2026): sin esto la
# 0060 los dejaba también en Tienda Inglesa.
PERMISOS_DE_TODOS_LOS_MUNDOS = frozenset({"ai.don_tino"})


def es_del_equipo_de_tienda_inglesa(permisos) -> bool:
    """Si tiene algún permiso de Tienda Inglesa: ni de Redexpres ni de algo
    que está en todos los mundos."""
    return any(
        not p.startswith("redexpres.") and p not in PERMISOS_DE_TODOS_LOS_MUNDOS
        for p in (permisos or [])
    )

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


def es_de_afuera(usuario) -> bool:
    """Si es una cuenta externa (la agencia). Lo mismo que externos.es_externo,
    acá para no importar ese módulo."""
    return bool(getattr(usuario, "es_externo", False))


def mundos_de(usuario) -> list[str]:
    """Los mundos a los que entra una persona del equipo, en el orden del
    catálogo.

    Nadie del equipo queda sin mundo: sin ninguno no podría entrar a la
    plataforma. A quien todavía no se le asignó ninguno (una cuenta creada por
    un script viejo, por ejemplo) le toca el de siempre, Tienda Inglesa. Para
    sacarle el acceso a alguien se lo desactiva, no se le vacía esta lista.

    Una cuenta externa (la agencia) no tiene mundos propios (25/11/2026, Ivan:
    "al ser agencia, ¿por qué tiene accesos a estos mundos? Sería al pedo,
    porque tienen acceso a su tablero"): sus tarjetas las ve de cualquier
    mundo, y el calendario, si se lo habilitan, solo de los mundos donde su
    agencia tiene trabajo (agencias.mundos_con_trabajo). Lo que tenga guardado
    en `users.mundos` de antes no se usa."""
    if es_de_afuera(usuario):
        return []
    if getattr(usuario, "is_superuser", False):
        return list(MUNDOS)
    propios = set(getattr(usuario, "mundos", None) or [])
    return [m for m in MUNDOS if m in propios] or [MUNDO_POR_DEFECTO]


def puede_abrir(usuario, mundo: str) -> bool:
    """Si a la persona le puede llegar trabajo de ese mundo: es lo que se mira
    para asignarle una tarea, avisarle de una tarjeta o ponerla a aprobar.

    Una cuenta externa, de cualquiera: a la agencia le piden piezas en todos
    los mundos, y de cada uno ve solo lo suyo (lo recorta cada ruta). Antes,
    si a una agencia le pedían algo en un mundo que no tenía tildado, no lo
    veía ni le llegaba el aviso, y nadie se enteraba."""
    if es_de_afuera(usuario):
        return es_mundo(mundo)
    return mundo in mundos_de(usuario)


def exigir_mundo(usuario, mundo: str, *, propio: bool = False) -> str:
    """El mundo, si existe y la persona puede entrar. Si no, 422 o 403.

    Una cuenta externa entra a un mundo solo por algo que ya se sabe que es
    suyo (`propio`: una tarjeta de su agencia, ya comprobado por quien llama).
    Para ver el calendario de un mundo, agencias.exigir_mundo_del_calendario,
    que mira dónde tiene trabajo; si alguna ruta se olvidara de eso, acá
    contesta 403: mejor de menos que de más."""
    if not es_mundo(mundo):
        raise HTTPException(status_code=422, detail="Ese mundo no existe")
    if es_de_afuera(usuario):
        if propio:
            return mundo
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tenés acceso a {MUNDOS[mundo]}",
        )
    if not puede_abrir(usuario, mundo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tenés acceso a {MUNDOS[mundo]}",
        )
    return mundo


def mundos_que_no_puede_dar(quien, antes, pedidos) -> list[str]:
    """Los mundos de `pedidos` que `quien` estaría dando y no puede: los que
    la persona no tenía (`antes`) y a los que `quien` mismo no entra. Igual
    que con los permisos, nadie da lo que no tiene. Sacar siempre se puede."""
    if getattr(quien, "is_superuser", False):
        return []
    propios = set(mundos_de(quien))
    ya_tenia = set(antes or [])
    return [m for m in MUNDOS if m in set(pedidos or []) and m not in ya_tenia and m not in propios]


def mundos_iniciales(permisos, es_sucursal_de_redexpres: bool = False) -> list[str]:
    """Con qué mundos arranca una cuenta, según lo que puede hacer.

    Es la regla con la que la 0060 repartió a quienes ya estaban, y la que se
    usa al crear una cuenta nueva. Pura, para probarla sin base.

    - Quien tiene un local de Redexpres asignado, o algún permiso de
      Redexpres, entra a Redexpres: "Mi pedido" y la planilla viven ahí, y sin
      el mundo dejaría de verlos.
    - Quien tiene algún permiso que no es de Redexpres entra a Tienda Inglesa,
      que es donde estaba todo.
    - Un login de sucursal (un local asignado y, de permisos, nada más que
      Redexpres o lo que está en todos los mundos, como Don Tino) entra solo
      a Redexpres. Alguien del equipo de Tienda Inglesa que además tiene un
      local (se asignó uno para probar) entra a los dos.
    - Quien no tiene nada entra a Tienda Inglesa.
    """
    permisos = set(permisos or [])
    de_redexpres = {p for p in permisos if p.startswith("redexpres.")}
    mundos = []
    if es_sucursal_de_redexpres:
        # Del equipo de Tienda Inglesa solo si tiene algo más que lo que está
        # en todos los mundos (Don Tino): los logins de sucursal tienen eso.
        if permisos - de_redexpres - PERMISOS_DE_TODOS_LOS_MUNDOS:
            mundos.append("tienda_inglesa")
        mundos.append("redexpres")
        return mundos
    if permisos - de_redexpres or not permisos:
        mundos.append("tienda_inglesa")
    if de_redexpres:
        mundos.append("redexpres")
    return mundos

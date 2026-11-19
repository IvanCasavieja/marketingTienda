"""Los tres tableros: Publicis, Another Monday y Diseñadores.

Pedido de Ivan (17/11/2026): cada pieza de una tarea se manda a uno de tres
tableros, que se elige en el modal de la pieza: "asignar a Publicis, asignar
a Another Monday o asignar a diseñadores, esos son los 3". Cada tablero es un
equipo que entra con sus propios usuarios y ve solo lo suyo; la pieza la toma
y la responde cualquiera de ese equipo ("lo hace quien quiera, lo toma quien
quiera, responde quien quiera").

Por adentro, un tablero es una agencia de las de la 0069: las cuentas
externas cuya empresa se llama igual que el tablero, y la pieza va "para la
agencia" con ese nombre (`calendario_tareas.para = 'agencia'`). Así valen las
reglas que ya existen: quién la ve, quién entrega, a quién le llega el aviso.

A diferencia de cualquier otra agencia, se puede mandar una pieza a uno de
estos tres aunque todavía no tenga cuentas: la tarjeta espera en su tablero
(el equipo de Tienda la ve) y aparece sola para sus cuentas cuando se crean
en el panel. Desde el 19/11/2026 la empresa de esas cuentas se elige de una
lista (app/services/agencias.py) y se compara sin tildes ni mayúsculas: antes
se escribía a mano y una cuenta con «Disenadores» no veía las de «Diseñadores».
"""
from __future__ import annotations

from app.core.externos import misma_empresa

TABLEROS: tuple[str, ...] = ("Publicis", "Another Monday", "Diseñadores")


def tablero_de(nombre: str | None) -> str | None:
    """El tablero con ese nombre (sin mirar tildes, la ñ, mayúsculas ni
    espacios de más: «disenadores» es Diseñadores), o None si no es uno de
    los tres. Puro."""
    for tablero in TABLEROS:
        if misma_empresa(tablero, nombre):
            return tablero
    return None

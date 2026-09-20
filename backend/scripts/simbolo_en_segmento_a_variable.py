"""Pasa el símbolo de moneda ESCRITO A MANO ADENTRO de un cuadro compuesto a
<<unidadMoneda>>.

Es la segunda mitad de `simbolo_a_variable.py` (17/09/2026). Ese script se
ocupó de los cuadros cuyo texto entero era el símbolo --41 cuadros, 10
plantillas-- y salteó a propósito los compuestos:

    "Un cuadro compuesto ya tiene su propia estructura; el símbolo ahí es un
     segmento y se trata aparte (no es un 'cuadro fijo' para el motor)."

Ese "aparte" es esto. Medido el 20/09/2026 sobre las 23 plantillas de
producción: quedan **68 segmentos** con el símbolo tipeado, en **15
plantillas**. Un producto en dólares imprime "$" en todos ellos -- incluido el
precio de oferta de Rompe Precios A4 y los seis "PRECIO REGULAR: $" de Mega
Rompe Precios 6xA4.

-----------------------------------------------------------------------------
Las dos formas reales, y por qué el espacio importa
-----------------------------------------------------------------------------

Un segmento no tiene lugar para "texto más variable": es una cosa o la otra
(``type`` "static" o "variable", ver TextSegment en types/cenefas.ts). Así que
un segmento que hoy dice " $ " no se puede reemplazar por la variable sin
perder los dos espacios que el diseñador puso alrededor, y esos espacios se
imprimen: sin ellos "3x $ 160" pasa a "3x$160". Por eso el símbolo se parte en
hasta tres pedazos, y los espacios quedan en estáticos propios:

    A) el segmento es SOLO el símbolo (44 casos)

         "$"      ->  [<<unidadMoneda>>]
         "$ "     ->  [<<unidadMoneda>>, " "]
         " $ "    ->  [" ", <<unidadMoneda>>, " "]

    B) el símbolo cierra una etiqueta (24 casos)

         "PRECIO REGULAR: $"   ->  ["PRECIO REGULAR: ", <<unidadMoneda>>]
         "PRECIO REGULAR: $ "  ->  ["PRECIO REGULAR: ", <<unidadMoneda>>, " "]

Cualquier otra forma (el símbolo en el medio de una frase) NO se toca: se
lista al final para que la mire una persona. Adivinar dónde corta una frase no
es tarea de un script.

-----------------------------------------------------------------------------
Lo que hay que renumerar, o se rompe un precio
-----------------------------------------------------------------------------

Una regla apunta a un segmento por su NÚMERO de posición
(``target_segment_index``, ver el comentario del campo en types/cenefas.ts), así
que partir un segmento en dos corre de lugar a todos los que vienen detrás.

Caso real, y la razón por la que este script renumera en vez de confiar: en
Rompe Precios Congelados 3xA4 tres cuadros son
["PRECIO REGULAR: $", <<precioRegular>>, " unidad"] y tienen una regla de
persona *Mostrar " unidad" si codigo contiene "-"* apuntando al segmento **2**.
Sin renumerar, después de partir el primero esa regla pasaría a apuntar a
<<precioRegular>>: el precio regular se mostraría solo en los productos cuyo
código tiene guión y **desaparecería del resto**.

Las reglas fijas del sistema (``bloqueada: True``) se recalculan aparte, con
`asegurar_reglas_fijas`, que ya sabe descartar las que quedaron apuntando a un
índice viejo. Las de las personas se renumeran acá, una por una.

Por defecto SIMULA. Con --aplicar escribe.

    python backend/scripts/simbolo_en_segmento_a_variable.py
    python backend/scripts/simbolo_en_segmento_a_variable.py --aplicar

Es idempotente: un segmento ya convertido es una variable y no vuelve a
entrar.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import AsyncSessionLocal
import app.models  # noqa: F401
from app.models.cenefa_template_v2 import CenefaTemplateV2
from app.services.cenefas.reglas_fijas import VAR_SIMBOLO, asegurar_reglas_fijas

# Lo que cuenta como símbolo de moneda. La misma lista corta que usan
# `simbolo_a_variable.py` y `reglas_fijas._SIMBOLOS_FIJOS`.
SIMBOLOS = ("U$S", "US$", "USD", "$")


def _partir(valor: str) -> list[dict] | None:
    """Los pedazos en los que se convierte un estático, o None si no se toca.

    Devuelve una lista de dicts ``{"tipo": "static"|"variable", "valor": ...}``
    en el orden en que van. El estilo lo pone el llamador: todos heredan el del
    segmento original, que es el que el diseñador le puso al símbolo.
    """
    if not valor:
        return None
    # El símbolo tiene que estar al FINAL del texto (salvo espacios). Así
    # entran las dos formas reales -- "$", " $ ", "PRECIO REGULAR: $" -- y
    # queda afuera el símbolo en el medio de una frase.
    cuerpo = valor.rstrip()
    espacios_finales = valor[len(cuerpo):]
    simbolo = next((s for s in SIMBOLOS if cuerpo.upper().endswith(s)), None)
    if simbolo is None:
        return None
    etiqueta = cuerpo[:len(cuerpo) - len(simbolo)]
    partes: list[dict] = []
    if etiqueta:
        partes.append({"tipo": "static", "valor": etiqueta})
    partes.append({"tipo": "variable", "valor": VAR_SIMBOLO})
    if espacios_finales:
        partes.append({"tipo": "static", "valor": espacios_finales})
    return partes


def convertir_componente(comp: dict) -> tuple[dict, dict[int, int], list[str]]:
    """Convierte los símbolos tipeados de un cuadro.

    Devuelve (cuadro nuevo, mapa de índices viejo->nuevo, descripción de los
    cambios). Si no hay nada que convertir, el cuadro vuelve igual y el mapa
    vacío.
    """
    segs = comp.get("segments") or []
    if not segs:
        return comp, {}, []

    nuevos: list[dict] = []
    mapa: dict[int, int] = {}
    cambios: list[str] = []
    for i, seg in enumerate(segs):
        mapa[i] = len(nuevos)
        partes = _partir(str(seg.get("value") or "")) if seg.get("type") == "static" else None
        if partes is None:
            nuevos.append(seg)
            continue
        estilo = seg.get("style")
        for parte in partes:
            pedazo: dict = {"type": parte["tipo"], "value": parte["valor"]}
            if estilo is not None:
                pedazo["style"] = dict(estilo)
            # El tamaño puesto a mano se respeta pedazo por pedazo: los tres
            # nacen del mismo segmento, así que les toca la misma marca.
            if seg.get("_manual_font_override"):
                pedazo["_manual_font_override"] = True
            nuevos.append(pedazo)
        # El índice del símbolo es el que importa para las reglas del sistema:
        # el mapa apunta al PEDAZO DEL SÍMBOLO, no al primer pedazo.
        mapa[i] = len(nuevos) - len(partes) + next(
            j for j, parte in enumerate(partes) if parte["tipo"] == "variable"
        )
        cambios.append(
            f"{str(seg.get('value'))!r} -> "
            + " + ".join(
                f"<<{p['valor']}>>" if p["tipo"] == "variable" else repr(p["valor"])
                for p in partes
            )
        )
    if not cambios:
        return comp, {}, []
    return {**comp, "segments": nuevos}, mapa, cambios


def convertir_definicion(defin: dict) -> tuple[dict, list[tuple[str, list[str]]], tuple[int, int]]:
    """Convierte una definición entera y renumera las reglas que apuntan a un
    segmento.

    Devuelve (definición nueva, [(id del cuadro, cambios)], (reglas de personas
    renumeradas, reglas del sistema renumeradas)). Las del sistema se renumeran
    igual, aunque `asegurar_reglas_fijas` las vuelva a calcular después: así el
    resultado no depende del orden de los dos pasos.
    """
    componentes: list[dict] = []
    mapas: dict[str, dict[int, int]] = {}
    detalle: list[tuple[str, list[str]]] = []
    for comp in defin.get("components") or []:
        nuevo, mapa, cambios = convertir_componente(comp)
        componentes.append(nuevo)
        if cambios:
            mapas[comp.get("id")] = mapa
            detalle.append((comp.get("id"), cambios))
    if not detalle:
        return defin, [], (0, 0)

    renumeradas = [0, 0]  # [de personas, del sistema]
    reglas: list[dict] = []
    for regla in defin.get("rules") or []:
        idx = regla.get("target_segment_index")
        mapa = mapas.get(regla.get("target_component_id"))
        if idx is not None and mapa is not None and mapa.get(idx, idx) != idx:
            reglas.append({**regla, "target_segment_index": mapa[idx]})
            renumeradas[1 if regla.get("bloqueada") else 0] += 1
        else:
            reglas.append(regla)

    nueva = {**defin, "components": componentes, "rules": reglas}
    # Las fijas se recalculan solas sobre la estructura nueva: descartan las
    # que quedaron apuntando a un índice viejo y vuelven a apuntar al símbolo,
    # que ahora es una variable (`_indice_del_simbolo` reconoce las dos formas).
    return asegurar_reglas_fijas(nueva), detalle, (renumeradas[0], renumeradas[1])


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    print("APLICANDO (escribe en la base)\n" if aplicar else "SIMULACION -- no escribe nada\n")

    tocadas = total = reglas_personas = reglas_sistema = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CenefaTemplateV2).order_by(CenefaTemplateV2.name))
        for tmpl in result.scalars().all():
            defin = tmpl.definition or {}
            nueva, detalle, renumeradas = convertir_definicion(defin)
            if not detalle:
                continue
            tocadas += 1
            reglas_personas += renumeradas[0]
            reglas_sistema += renumeradas[1]
            cuantos = sum(len(c) for _, c in detalle)
            total += cuantos
            detalle_reglas = ", ".join(
                f"{n} reglas {quien} renumeradas"
                for n, quien in ((renumeradas[0], "de personas"), (renumeradas[1], "del sistema")) if n
            )
            print(f"  {tmpl.name[:46]:48} {cuantos:>2} segmentos"
                  + (f", {detalle_reglas}" if detalle_reglas else ""))
            for comp_id, cambios in detalle:
                for cambio in cambios:
                    print(f"       cuadro {str(comp_id)[:8]}  {cambio}")
            if aplicar:
                tmpl.definition = nueva
                flag_modified(tmpl, "definition")
        if aplicar:
            await db.commit()

    print(f"\n{'Convertidos' if aplicar else 'Se convertirian'}: {total} segmentos "
          f"en {tocadas} plantillas; reglas renumeradas: {reglas_personas} de personas, "
          f"{reglas_sistema} del sistema")
    if not aplicar:
        print("Para aplicarlo: agregar --aplicar")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

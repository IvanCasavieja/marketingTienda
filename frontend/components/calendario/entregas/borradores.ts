'use client'

// Lo que se estaba cargando para entregar, guardado en este navegador (H-039
// de la auditoría del 25/11/2026). Las reglas (qué se guarda, cuándo sirve)
// están en lib/calendario/borrador.ts; acá, el guardado: IndexedDB, que
// guarda las imágenes tal cual, sin pasarlas a texto. Todo es «si se puede»:
// sin IndexedDB (un Safari viejo en navegación privada, el almacenamiento
// bloqueado) no se guarda nada y entregar anda igual que antes.

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  VIDA_DEL_BORRADOR_MS, armarBorrador, borradorVigente, type BorradorDeEntrega, type ImagenGuardada,
} from '@/lib/calendario/borrador'

const BASE = 'core-tienda-borradores'
const TABLA = 'entregas'

function abrirBase(): Promise<IDBDatabase | null> {
  return new Promise(resolver => {
    try {
      const pedido = indexedDB.open(BASE, 1)
      pedido.onupgradeneeded = () => { pedido.result.createObjectStore(TABLA) }
      pedido.onsuccess = () => resolver(pedido.result)
      pedido.onerror = () => resolver(null)
      pedido.onblocked = () => resolver(null)
    } catch {
      resolver(null)
    }
  })
}

// De a una, en el orden en que se piden: un guardado que salió justo antes de
// mandar no puede caer después del borrado.
let cola: Promise<unknown> = Promise.resolve()

/** Una operación sobre la tabla, en su propia transacción: lo que devolvió, o
 *  null si no se pudo. */
function enLaTabla<T>(
  modo: IDBTransactionMode, operacion: (tabla: IDBObjectStore) => IDBRequest<T> | void,
): Promise<T | null> {
  const hecho = cola.then(async () => {
    const base = await abrirBase()
    if (!base) return null
    return new Promise<T | null>(resolver => {
      const terminar = (valor: T | null) => { base.close(); resolver(valor) }
      try {
        const tx = base.transaction(TABLA, modo)
        const pedido = operacion(tx.objectStore(TABLA))
        tx.oncomplete = () => terminar(pedido ? pedido.result ?? null : null)
        tx.onerror = () => terminar(null)
        tx.onabort = () => terminar(null)
      } catch {
        terminar(null)
      }
    })
  })
  cola = hecho.catch(() => null)
  return hecho
}

let barrido = false
/** Lo de hace más de un día se borra, de cualquier tarjeta: una vez por página,
 *  así lo que nadie volvió a abrir no se queda ocupando lugar en la compu. */
function barrerLoViejo(ahora: number) {
  if (barrido) return
  barrido = true
  void enLaTabla('readwrite', tabla => {
    const pedido = tabla.openCursor()
    pedido.onsuccess = () => {
      const cursor = pedido.result
      if (!cursor) return
      const guardado = (cursor.value as Partial<BorradorDeEntrega> | undefined)?.guardado
      if (typeof guardado !== 'number' || ahora - guardado >= VIDA_DEL_BORRADOR_MS) cursor.delete()
      cursor.continue()
    }
  })
}

export async function leerBorrador(clave: string): Promise<BorradorDeEntrega | null> {
  barrerLoViejo(Date.now())
  return (await enLaTabla<BorradorDeEntrega | undefined>('readonly', tabla => tabla.get(clave))) ?? null
}

export function guardarBorrador(clave: string, borrador: BorradorDeEntrega) {
  return enLaTabla('readwrite', tabla => tabla.put(borrador, clave))
}

export function borrarBorrador(clave: string) {
  return enLaTabla('readwrite', tabla => tabla.delete(clave))
}

/** Al cerrar sesión: lo que alguien dejó a medio cargar no queda en la compu. */
export function borrarTodosLosBorradores() {
  try {
    indexedDB.deleteDatabase(BASE)
  } catch {
    // Sin almacenamiento no hay nada guardado que borrar.
  }
}

/**
 * El borrador del formulario de entrega. Al abrirlo busca lo que quedó y, si
 * sirve para esta entrega, se lo pasa a `alRecuperar`. Mientras se carga, lo
 * guarda solo: medio segundo después del último cambio, nunca a mitad de
 * preparar una imagen, de leer el ZIP o de subir. Devuelve `olvidar`, para
 * cuando se manda o se descarta lo cargado.
 */
export function useBorradorDeEntrega({ clave, entrega, cargado, quieto, alRecuperar }: {
  /** De quién y de qué tarjeta (claveDeBorrador); null, sin borrador. */
  clave: string | null
  entrega: { fase: string | null; ronda: number; versiones: string[] }
  cargado: {
    versionId: string; comentario: string; link: string; porQue: string; zip: string | null
    imagenes: (ImagenGuardada & { deZip?: number })[]
  }
  quieto: boolean
  alRecuperar: (borrador: BorradorDeEntrega) => void
}): () => void {
  // Hasta saber si había algo guardado no se guarda nada: si no, lo vacío del
  // primer momento pisaría lo que se quiere recuperar.
  const [buscado, setBuscado] = useState(false)
  const ultimo = useRef({ entrega, alRecuperar })
  useEffect(() => { ultimo.current = { entrega, alRecuperar } })

  useEffect(() => {
    if (!clave) return
    let vivo = true
    void leerBorrador(clave).then(borrador => {
      if (!vivo) return
      if (borrador && borradorVigente(borrador, ultimo.current.entrega, Date.now())) ultimo.current.alRecuperar(borrador)
      else if (borrador) void borrarBorrador(clave)
      setBuscado(true)
    })
    return () => { vivo = false }
  }, [clave])

  const { versionId, comentario, link, porQue, zip, imagenes } = cargado
  useEffect(() => {
    if (!clave || !buscado || !quieto) return
    const reloj = window.setTimeout(() => {
      const borrador = armarBorrador({ versionId, comentario, link, porQue, zip, imagenes }, ultimo.current.entrega, Date.now())
      void (borrador ? guardarBorrador(clave, borrador) : borrarBorrador(clave))
    }, 500)
    return () => window.clearTimeout(reloj)
  }, [clave, buscado, quieto, versionId, comentario, link, porQue, zip, imagenes])

  return useCallback(() => { if (clave) void borrarBorrador(clave) }, [clave])
}

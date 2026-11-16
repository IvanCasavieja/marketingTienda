'use client'

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'

/**
 * Dictado con la Web Speech API del navegador.
 *
 * Por qué esta y no un servicio de voz: es gratis y ya viene en Chrome (también
 * en Android) y en Safari (también en el iPhone). No se paga por minuto ni hay
 * que mandar el audio a un servidor nuestro. Donde no existe (Firefox, por
 * ejemplo) el pedido se escribe a mano y sigue el mismo camino: la IA ordena
 * texto, no audio.
 *
 * Ojo: en Chrome el reconocimiento lo hace Google en sus servidores; por eso
 * pide conexión y puede fallar con "network".
 *
 * Los tipos van acá porque la librería de TypeScript no trae los de esta API
 * (no es un estándar terminado).
 */

type ResultadoDeVoz = { isFinal: boolean; 0: { transcript: string } }
type EventoDeVoz = { resultIndex: number; results: ArrayLike<ResultadoDeVoz> }
type ErrorDeVoz = { error: string }

interface Reconocedor {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  onresult: ((e: EventoDeVoz) => void) | null
  onerror: ((e: ErrorDeVoz) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}

type ConstructorDeReconocedor = new () => Reconocedor

function constructorDelNavegador(): ConstructorDeReconocedor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: ConstructorDeReconocedor
    webkitSpeechRecognition?: ConstructorDeReconocedor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

/** Uruguay primero; si el navegador no lo tiene, el de Argentina, que suena igual. */
const IDIOMAS = ['es-UY', 'es-AR']

const MENSAJES: Record<string, string> = {
  'not-allowed': 'No hay permiso para usar el micrófono. Habilitalo en el navegador (el candadito de la barra de direcciones) y probá de nuevo.',
  'service-not-allowed': 'El navegador no deja dictar acá. Escribí el pedido abajo.',
  'no-speech': 'No se escuchó nada. Probá de nuevo, más cerca del micrófono.',
  'audio-capture': 'No se encontró un micrófono.',
  network: 'El dictado necesita conexión a internet. Probá de nuevo o escribilo abajo.',
}

const nada = () => () => {}

export type Dictado = {
  /** null mientras no se sabe (en el servidor); false si el navegador no tiene dictado. */
  disponible: boolean | null
  escuchando: boolean
  /** Lo que va entendiendo y todavía puede cambiar (en gris en la pantalla). */
  provisorio: string
  error: string | null
  empezar: () => void
  parar: () => void
}

/**
 * `alConfirmar` recibe cada tramo que el navegador da por definitivo: quien
 * usa el hook lo suma a su texto (que la persona puede seguir editando).
 */
export function useDictado(alConfirmar: (tramo: string) => void): Dictado {
  // Si hay dictado se sabe recién en el navegador. Con un "store" que no
  // cambia nunca, el servidor y el primer render dicen null y después el
  // navegador dice la verdad, sin un efecto que haga setState.
  const disponible = useSyncExternalStore(
    nada,
    () => constructorDelNavegador() !== null,
    () => null,
  )
  const [escuchando, setEscuchando] = useState(false)
  const [provisorio, setProvisorio] = useState('')
  const [error, setError] = useState<string | null>(null)
  const reconocedor = useRef<Reconocedor | null>(null)
  // El idioma que anduvo la última vez: no se vuelve a probar uno que no.
  const idioma = useRef(0)
  // El último callback, sin rearmar el reconocedor en cada render.
  const confirmar = useRef(alConfirmar)
  useEffect(() => { confirmar.current = alConfirmar })

  useEffect(() => {
    const actual = reconocedor
    return () => actual.current?.abort()
  }, [])

  const empezar = useCallback(() => {
    const Ctor = constructorDelNavegador()
    if (!Ctor || reconocedor.current) return

    const iniciar = (nroIdioma: number) => {
      const rec = new Ctor()
      rec.lang = IDIOMAS[nroIdioma]
      // Continuo: se puede hacer una pausa para pensar sin que se corte.
      rec.continuous = true
      rec.interimResults = true
      rec.maxAlternatives = 1
      rec.onresult = e => {
        idioma.current = nroIdioma
        let enCurso = ''
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i]
          if (r.isFinal) confirmar.current(r[0].transcript.trim())
          else enCurso += r[0].transcript
        }
        setProvisorio(enCurso.trim())
      }
      rec.onerror = e => {
        if (e.error === 'language-not-supported' && nroIdioma + 1 < IDIOMAS.length) {
          // Cuando termine este intento, se prueba con el idioma siguiente.
          rec.onend = () => { reconocedor.current = null; iniciar(nroIdioma + 1) }
          return
        }
        if (e.error === 'aborted') return
        setError(MENSAJES[e.error] ?? 'El dictado se cortó. Probá de nuevo o escribí el pedido abajo.')
      }
      rec.onend = () => {
        reconocedor.current = null
        setEscuchando(false)
        setProvisorio('')
      }
      reconocedor.current = rec
      try {
        rec.start()
        setEscuchando(true)
      } catch {
        // start() tira si ya había uno andando (dos toques muy seguidos).
        reconocedor.current = null
        setEscuchando(false)
      }
    }

    setError(null)
    setProvisorio('')
    iniciar(idioma.current)
  }, [])

  const parar = useCallback(() => {
    // stop() y no abort(): lo último que se dijo todavía llega como definitivo.
    reconocedor.current?.stop()
  }, [])

  return { disponible, escuchando, provisorio, error, empezar, parar }
}

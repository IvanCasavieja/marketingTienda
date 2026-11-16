'use client'

import { useState } from 'react'
import Link from 'next/link'
import ReactMarkdown, { type Components } from 'react-markdown'
import { Check, Copy } from 'lucide-react'
import { toast } from 'sonner'
import { htmlParaCopiar, prepararMarkdown, rutaInterna, textoParaCopiar } from '@/lib/chat/respuesta'

/**
 * Lo que contesta Don Tino, con negritas, listas y links que se pueden tocar.
 *
 * Antes la respuesta se mostraba como texto (solo se entendían las negritas):
 * los links que el prompt le pide al modelo salían como "[Dashboard](https://...)"
 * y los saltos de renglón se perdían. Ahora una acción nombrada en la
 * respuesta se toca y abre su ficha (/calendario?accion=...).
 *
 * Nada de HTML del modelo (skipHtml) y solo los elementos de abajo: lo demás
 * queda como texto. Los links que no son de la app no se pueden tocar (ver
 * lib/chat/respuesta.ts).
 */

const PERMITIDOS = ['p', 'strong', 'em', 'ul', 'ol', 'li', 'a', 'br', 'code']

function origen(): string | null {
  return typeof window === 'undefined' ? null : window.location.origin
}

const COMPONENTES: Components = {
  a: ({ href, children }) => {
    const ruta = rutaInterna(href, origen())
    if (ruta) {
      return (
        <Link href={ruta} className="font-semibold text-brand-700 underline decoration-brand-300 underline-offset-2 transition hover:decoration-brand-600 dark:text-brand-300 dark:decoration-brand-500/50">
          {children}
        </Link>
      )
    }
    // De afuera: se ve la dirección, pero no se toca.
    return <span>{children}{href ? <span className="text-slate-500"> ({href})</span> : null}</span>
  },
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-0.5 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-0.5 pl-5 last:mb-0">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900 dark:text-slate-100">{children}</strong>,
  code: ({ children }) => <code className="rounded bg-slate-100 px-1 text-[13px] dark:bg-slate-800">{children}</code>,
}

export function RespuestaDelBot({ texto }: { texto: string }) {
  return (
    <ReactMarkdown skipHtml allowedElements={PERMITIDOS} unwrapDisallowed components={COMPONENTES}>
      {prepararMarkdown(texto)}
    </ReactMarkdown>
  )
}

/**
 * Copia la respuesta lista para pegar en un mail (el estado para gerencia):
 * con negritas y viñetas donde se pega HTML, y en texto limpio donde no.
 */
export function BotonCopiar({ texto }: { texto: string }) {
  const [copiado, setCopiado] = useState(false)

  async function copiar() {
    const plano = textoParaCopiar(texto, origen())
    try {
      if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
        await navigator.clipboard.write([new ClipboardItem({
          'text/plain': new Blob([plano], { type: 'text/plain' }),
          'text/html': new Blob([htmlParaCopiar(texto, origen())], { type: 'text/html' }),
        })])
      } else {
        await navigator.clipboard.writeText(plano)
      }
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    } catch {
      toast.error('No se pudo copiar. Seleccioná el texto y copialo a mano.')
    }
  }

  return (
    <button
      type="button"
      onClick={copiar}
      className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
      aria-label="Copiar la respuesta"
    >
      {copiado ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
      {copiado ? 'Copiado' : 'Copiar'}
    </button>
  )
}

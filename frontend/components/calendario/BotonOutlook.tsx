'use client'

/**
 * "Ver en Outlook o en el teléfono": el link privado para suscribir el
 * calendario de Core Tienda en Outlook, Google Calendar o el iPhone (idea
 * aprobada por Ivan el 15/11/2026). Muestra las acciones de los mundos de la
 * persona y sus tareas, y se actualiza solo.
 */
import { useEffect, useRef, useState } from 'react'
import { CalendarPlus, Check, Copy, RefreshCw, Smartphone, X } from 'lucide-react'
import { toast } from 'sonner'
import { calendarioApi, urlDeLaApi } from '@/lib/api'
import { useDialogo } from './useDialogo'

export function BotonOutlook({ compacto = false }: { compacto?: boolean }) {
  const [abierto, setAbierto] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setAbierto(true)}
        title="Ver tu calendario en Outlook o en el teléfono"
        className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-slate-300 px-3 text-xs font-semibold text-slate-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 active:scale-95 dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-500/40 dark:hover:bg-brand-500/10 dark:hover:text-brand-200"
      >
        <CalendarPlus className="h-3.5 w-3.5" />
        {compacto ? 'Outlook' : 'Ver en Outlook'}
      </button>
      {abierto && <DialogoOutlook onCerrar={() => setAbierto(false)} />}
    </>
  )
}

function DialogoOutlook({ onCerrar }: { onCerrar: () => void }) {
  const caja = useRef<HTMLDivElement>(null)
  useDialogo(true, caja)
  const [link, setLink] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const [copiado, setCopiado] = useState(false)
  const [confirmarOtro, setConfirmarOtro] = useState(false)

  useEffect(() => {
    let vivo = true
    calendarioApi.linkDelCalendario()
      .then(({ data }) => { if (vivo) setLink(urlDeLaApi(data.ruta)) })
      .catch(() => { if (vivo) setError(true) })
    return () => { vivo = false }
  }, [])

  async function copiar() {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    } catch {
      toast.error('No se pudo copiar: seleccioná el link y copialo a mano.')
    }
  }

  async function otroLink() {
    try {
      const { data } = await calendarioApi.nuevoLinkDelCalendario()
      setLink(urlDeLaApi(data.ruta))
      setConfirmarOtro(false)
      toast.success('Listo: el link anterior ya no anda. Suscribí el nuevo donde lo tenías.')
    } catch {
      toast.error('No se pudo generar otro link. Probá de nuevo en un momento.')
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-4" onKeyDown={e => { if (e.key === 'Escape') onCerrar() }}>
      <div className="velo animate-fade-in" onClick={onCerrar} aria-hidden />
      <div
        ref={caja}
        role="dialog"
        aria-modal="true"
        aria-labelledby="outlook-titulo"
        className="relative flex max-h-[92dvh] w-full max-w-md animate-sheet-up flex-col overflow-y-auto rounded-t-3xl bg-white p-5 shadow-panel dark:bg-slate-900 dark:ring-1 dark:ring-slate-800 sm:animate-scale-in sm:rounded-2xl sm:p-6"
      >
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
            <CalendarPlus className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="outlook-titulo" className="text-lg font-bold leading-tight text-slate-900 dark:text-slate-100">Tu calendario en Outlook o en el teléfono</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
              Las acciones de tus mundos y tus tareas, en el calendario que ya usás. Se actualiza solo cada unas horas.
            </p>
          </div>
          <button type="button" onClick={onCerrar} className="boton-icono -mr-1 -mt-1" aria-label="Cerrar">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-4 flex gap-2">
          <input
            readOnly
            value={link ?? (error ? 'No se pudo traer el link' : 'Un momento…')}
            onFocus={e => e.currentTarget.select()}
            aria-label="Link de tu calendario"
            className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          />
          <button
            type="button"
            onClick={copiar}
            disabled={!link}
            className="flex shrink-0 items-center gap-1.5 rounded-xl bg-brand-600 px-3 text-sm font-semibold text-white transition hover:bg-brand-700 active:scale-95 disabled:opacity-50"
          >
            {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copiado ? 'Copiado' : 'Copiar'}
          </button>
        </div>

        {link && (
          <a
            href={link.replace(/^https?:\/\//, 'webcal://')}
            className="mt-2 flex items-center justify-center gap-2 rounded-xl border border-slate-300 px-3 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <Smartphone className="h-4 w-4" />
            Abrir en el calendario del iPhone o la Mac
          </a>
        )}

        <ol className="mt-4 space-y-2 text-sm text-slate-700 dark:text-slate-300">
          <li><strong>Outlook:</strong> Agregar calendario → Suscribirse desde la web → pegá el link.</li>
          <li><strong>Google Calendar:</strong> Otros calendarios → + → Desde URL → pegá el link.</li>
          <li><strong>iPhone:</strong> tocá el botón de arriba y después «Suscribirse».</li>
        </ol>

        <div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-400">
          El link es tuyo: quien lo tenga ve lo mismo que vos en el calendario. Si se compartió sin querer, generá otro y el anterior deja de andar.
          <div className="mt-2">
            {confirmarOtro ? (
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-800 dark:text-slate-200">¿Seguro? Vas a tener que suscribir el nuevo.</span>
                <button type="button" onClick={otroLink} className="rounded-lg bg-red-600 px-2.5 py-1 font-semibold text-white hover:bg-red-700">Sí, generar otro</button>
                <button type="button" onClick={() => setConfirmarOtro(false)} className="rounded-lg px-2.5 py-1 font-semibold hover:bg-slate-200 dark:hover:bg-slate-700">No</button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmarOtro(true)} disabled={!link} className="flex items-center gap-1.5 font-semibold text-slate-700 hover:text-slate-900 disabled:opacity-50 dark:text-slate-300 dark:hover:text-white">
                <RefreshCw className="h-3.5 w-3.5" />
                Generar otro link
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

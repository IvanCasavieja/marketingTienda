'use client'

import { useEffect, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { toast } from 'sonner'
import { adjuntosApi, calendarioApi } from '@/lib/api'
import { nuevoId } from '@/lib/calendario/derivar'
import type { Persona } from '@/lib/calendario/tipos'
import { useTableros } from '@/store/tiposDeTarea'
import { FormularioDeTarea, type PedidoDeTarea } from '../FormularioDeTarea'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

/**
 * "Nueva tarjeta" en Tableros: algo que se pide por fuera del calendario
 * (Ivan, 24/11/2026: "deberíamos poder crear acciones o tarjetas también de
 * cosas que estén por fuera del calendario, quizás mismo en los tableros
 * podríamos tener la opción de crear una tarjeta").
 *
 * El formulario es el mismo de "Crear tarea" en una acción (FormularioDeTarea),
 * sin acción: el nombre lo escribe la persona y siempre hay que elegir quién
 * la hace. La tarjeta nace en el tablero de quien la hace y en Mis tareas del
 * responsable; en el calendario no aparece (app/services/sin_accion.py).
 *
 * La ven quienes crean tareas (`calendario.tareas` o `calendario.pedidos`); la
 * agencia no. El servidor exige lo mismo. Si se está mirando el tablero de una
 * agencia, esa agencia viene ya elegida.
 */
export function NuevaTarjeta({ mundo, tablero, usuarioId, onCreada }: {
  mundo: string
  /** El tablero que se está mirando (Publicis…), si es el de una agencia. */
  tablero: string | null
  usuarioId: number | null
  onCreada: () => void
}) {
  const [abierta, setAbierta] = useState(false)
  const [personas, setPersonas] = useState<Persona[]>([])
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando')
  const [enviando, setEnviando] = useState(false)
  const { tableros } = useTableros(mundo)
  const quienInicial = tablero && tableros?.some(t => t.nombre === tablero) ? `agencia:${tablero}` : ''

  useEffect(() => {
    if (!abierta) return
    let vivo = true
    calendarioApi.personas(mundo)
      .then(({ data }) => { if (vivo) { setPersonas(data); setEstado('ok') } })
      .catch(() => { if (vivo) setEstado('error') })
    return () => { vivo = false }
  }, [abierta, mundo])

  function abrir() {
    setEstado('cargando')
    setAbierta(true)
  }

  function cerrar() {
    if (!enviando) setAbierta(false)
  }

  async function enviar(pedidos: PedidoDeTarea[], archivos: File[]) {
    setEnviando(true)
    let creadas = 0
    let sinArchivos = false
    try {
      for (const p of pedidos) {
        const id = nuevoId('ta')
        await calendarioApi.crearTarjeta({ ...p, id, mundo })
        creadas++
        if (archivos.length > 0) {
          try {
            await adjuntosApi.subir(id, archivos)
          } catch {
            sinArchivos = true
          }
        }
      }
      toast.success(creadas > 1
        ? `Se crearon ${creadas} tarjetas: ya están en el tablero de quien las hace.`
        : 'Tarjeta creada: ya está en el tablero de quien la hace.')
      if (sinArchivos) toast.error('No se pudieron subir los archivos: agregalos desde la tarjeta, en «Lo que se pidió».')
      setAbierta(false)
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo crear la tarjeta. Probá de nuevo.')
      // Si alguna ya se creó, que no quede la ventana como si no.
      if (creadas > 0) setAbierta(false)
    } finally {
      setEnviando(false)
      if (creadas > 0) onCreada()
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={abrir}
        className="flex min-h-[44px] items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98]"
      >
        <Plus className="h-4 w-4" /> Nueva tarjeta
      </button>
      {abierta && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 sm:items-center sm:p-4"
          onMouseDown={e => { if (e.target === e.currentTarget) cerrar() }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="nueva-tarjeta-titulo"
            onKeyDown={e => { if (e.key === 'Escape') cerrar() }}
            className="max-h-[92dvh] w-full animate-scale-in overflow-y-auto rounded-t-2xl bg-white p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-xl dark:bg-slate-900 sm:max-w-xl sm:rounded-2xl sm:p-5"
          >
            <div className="mb-4 flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <h2 id="nueva-tarjeta-titulo" className="text-lg font-bold text-slate-900 dark:text-slate-100">Nueva tarjeta</h2>
                <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
                  Para algo que no es de una acción del calendario: va al tablero de quien la hace, sin acción.
                </p>
              </div>
              <button type="button" onClick={cerrar} className="boton-icono -mr-2 -mt-1" aria-label="Cerrar sin crear">
                <X className="h-5 w-5" />
              </button>
            </div>
            <FormularioDeTarea
              mundo={mundo}
              accion={null}
              personas={personas}
              personasEstado={estado}
              usuarioId={usuarioId}
              encabezado="Nueva tarjeta"
              idDetalle="detalle-nueva-tarjeta"
              quienInicial={quienInicial}
              enviando={enviando}
              enMarco={false}
              onEnviar={enviar}
              onCancelar={cerrar}
            />
          </div>
        </div>
      )}
    </>
  )
}

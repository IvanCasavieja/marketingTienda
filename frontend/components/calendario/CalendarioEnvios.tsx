'use client'

import { AlertTriangle, Mail, MessageCircle, Send, Smartphone } from 'lucide-react'
import { CabeceraDias, EtiquetaBanda, FilaRejilla, useAnchoTotal } from './Rejilla'
import { MarcoScroll } from './MarcoScroll'
import { Seccion } from './Seccion'
import { diaDeHoy } from '@/lib/calendario/fechas'
import { enviosDelMes, filasDeEnvios, useCalendario } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

const ICONO: Record<string, React.ReactNode> = {
  email: <Mail className="h-3.5 w-3.5" />,
  whatsapp: <MessageCircle className="h-3.5 w-3.5" />,
  push: <Smartphone className="h-3.5 w-3.5" />,
}

/**
 * El cronograma de envíos: cuándo sale el mailing, el WhatsApp y el push.
 *
 * No se carga acá. Sale de las piezas que ya tiene cada acción en su ficha, así
 * que lo único que hay que hacer para que aparezca un envío es agregarle la
 * pieza a la acción y ponerle la fecha. Tocar un envío lleva a esa ficha, que
 * es donde se edita.
 */
export function CalendarioEnvios() {
  const mes = useCalendario(s => s.meses[s.mesActivo])
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const ancho = useAnchoTotal(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const { editable } = usePermisosCalendario()

  const canales = enviosDelMes(mes)
  const total = canales.reduce((n, c) => n + c.envios.length, 0)
  const sinFecha = canales.flatMap(c => c.envios.filter(e => e.heredaLaFecha))

  /** Un envío lleva a la ficha de su acción, que es donde se le pone la fecha. */
  function irAAccion(accionId: string) {
    for (const banda of mes.comercial) {
      for (let i = 0; i < banda.filas.length; i++) {
        if (banda.filas[i].some(b => b.id === accionId)) {
          abrirAccion({ bandaId: banda.id, filaIdx: i, barraId: accionId })
          return
        }
      }
    }
  }

  return (
    <Seccion
      icono={<Send className="h-4 w-4" />}
      titulo="Cronograma de envíos"
      bajada="Cuándo sale cada mailing, cada WhatsApp y cada push. Sale de las piezas de cada acción: se cargan una sola vez, en su ficha."
      contador={total === 1 ? '1 envío' : `${total} envíos`}
    >
      {sinFecha.length > 0 && (
        <div className="border-b border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 px-4 py-2.5">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-900 dark:text-amber-200">
            <AlertTriangle className="h-3.5 w-3.5" />
            {sinFecha.length === 1
              ? 'Un envío todavía no tiene fecha propia'
              : `${sinFecha.length} envíos todavía no tienen fecha propia`}
          </p>
          <ul className="mt-1 space-y-0.5">
            {sinFecha.map(e => (
              <li key={e.id} className="text-[11px] text-amber-800 dark:text-amber-300">
                <button onClick={() => irAAccion(e.accionId)} className="font-medium underline underline-offset-2">
                  {e.accion}
                </button>
                {' · '}{e.formato}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-400">
            Mientras tanto se muestran el día que arranca su acción. La fecha se pone en la ficha.
          </p>
        </div>
      )}

      <MarcoScroll ancho={ancho}>
        <CabeceraDias mes={mes} hoy={hoy} titulo="Canal" />

        {canales.map(canal => {
          const filas = filasDeEnvios(canal.envios)
          return (
            <div key={canal.area} className="flex">
              <EtiquetaBanda
                filas={filas.length}
                extra={
                  <span className="text-[9px] font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
                    {canal.envios.length === 0
                      ? 'sin envíos'
                      : canal.envios.length === 1 ? '1 envío' : `${canal.envios.length} envíos`}
                  </span>
                }
              >
                <span className="flex items-center gap-1.5">{ICONO[canal.area]} {canal.titulo}</span>
              </EtiquetaBanda>
              <div className="flex-1">
                {filas.map((fila, i) => (
                  <FilaRejilla
                    key={i}
                    mes={mes}
                    fila={fila}
                    hoy={hoy}
                    editable={editable}
                    esDerivada={() => true}
                    tituloDe={b => {
                      const e = canal.envios.find(x => x.id === b.id)
                      if (!e) return b.nombre
                      return `${e.accion} · ${e.formato} · día ${e.dia}${e.hora ? ` a las ${e.hora}` : ''}` +
                        `${e.heredaLaFecha ? ' · sin fecha propia, toma la de su acción' : ''}`
                    }}
                    onBarra={b => {
                      const e = canal.envios.find(x => x.id === b.id)
                      if (e) irAAccion(e.accionId)
                    }}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </MarcoScroll>

      {total === 0 && (
        <div className="px-4 py-8 text-center text-sm text-slate-400 dark:text-slate-500">
          Todavía no hay envíos cargados este mes.
          <br />
          <span className="text-xs">
            Se agregan en la ficha de cada acción, en Email, WhatsApp o Push.
          </span>
        </div>
      )}

      <footer className="flex flex-wrap items-center gap-4 border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2.5 text-[11px] text-slate-500 dark:text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border-l-[3px] border-l-slate-900/40 bg-slate-200 dark:bg-slate-700" />
          cada envío se edita en la ficha de su acción
        </span>
        <span>El color es el de la acción, para reconocerla de un vistazo.</span>
      </footer>
    </Seccion>
  )
}

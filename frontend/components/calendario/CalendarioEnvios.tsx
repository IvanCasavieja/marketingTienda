'use client'

import { AlertTriangle, Mail, MessageCircle, Send, Smartphone } from 'lucide-react'
import { CabeceraDias, EtiquetaBanda, FilaRejilla, Renglones, useAnchoTotal } from './Rejilla'
import { MarcoScroll } from './MarcoScroll'
import { Seccion } from './Seccion'
import { diaDeHoy, isoDe } from '@/lib/calendario/fechas'
import { enviosDelMes, filasDeEnvios, useCalendario, useMesActivo } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

const ICONO: Record<string, React.ReactNode> = {
  email: <Mail className="h-3.5 w-3.5" />,
  whatsapp: <MessageCircle className="h-3.5 w-3.5" />,
  push: <Smartphone className="h-3.5 w-3.5" />,
}

/**
 * El cronograma de envíos: cuándo sale el mailing, el WhatsApp y el push.
 *
 * La mayoría sale solo de las piezas que ya tiene cada acción en su ficha:
 * alcanza con agregarle la pieza y ponerle la fecha. Tocar uno de esos lleva a
 * la ficha de su acción, que es donde se edita.
 *
 * Desde el 28/09/2026 también hay envíos SUELTOS, sin una acción detrás: "de
 * repente no hay una promoción y tenemos que salir con un email marketing, con
 * una push, con un WhatsApp". Se crean acá, con el + de cada canal o tocando un
 * día libre, y tienen su propia ficha.
 */
export function CalendarioEnvios() {
  const mes = useMesActivo()
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const ancho = useAnchoTotal(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const { editable } = usePermisosCalendario()

  const canales = enviosDelMes(mes)
  const total = canales.reduce((n, c) => n + c.envios.length, 0)
  const sinFecha = canales.flatMap(c => c.envios.filter(e => e.heredaLaFecha))

  /** Cada barra dibujada, con su envío: se busca una vez y no por cada barra. */
  const porBarra = new Map(canales.flatMap(c => c.envios).map(e => [e.id, e]))
  // Un envío de una acción abre la ficha de la acción; uno suelto, la suya.
  // En los dos casos `accionId` es el id de lo que hay que abrir.
  const abrirFicha = abrirAccion
  const nuevoEnvio = (canal: string, dia: number) =>
    abrirEditor({ seccion: 'envio', banda: canal, carril: 0, barra: null, fechaInicial: isoDe(mes.clave, dia) })

  return (
    <Seccion
      icono={<Send className="h-4 w-4" />}
      titulo="Cronograma de envíos"
      bajada="Cuándo sale cada mailing, cada WhatsApp y cada push. Los de una acción salen solos de su ficha; los que no tienen acción se cargan acá, con el +."
      contador={total === 1 ? '1 envío' : `${total} envíos`}
    >
      {sinFecha.length > 0 && (
        // Compacto: los envíos van uno al lado del otro y no uno por renglón
        // (con cuatro, el aviso ocupaba más que el cronograma).
        <div className="border-b border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 px-4 py-2">
          <p className="flex flex-wrap items-center gap-x-1.5 text-xs font-semibold text-amber-900 dark:text-amber-200">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            {sinFecha.length === 1
              ? 'Un envío todavía no tiene fecha propia'
              : `${sinFecha.length} envíos todavía no tienen fecha propia`}
            <span className="text-[11px] font-normal text-amber-800 dark:text-amber-300">
              · se muestran el día que arranca su acción; la fecha se pone en la ficha.
            </span>
          </p>
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
            {sinFecha.map(e => (
              <li key={e.id} className="text-[11px] text-amber-800 dark:text-amber-300">
                <button onClick={() => abrirFicha(e.accionId)} className="font-medium underline underline-offset-2">
                  {e.accion}
                </button>
                {' · '}{e.formato}
              </li>
            ))}
          </ul>
        </div>
      )}

      <MarcoScroll ancho={ancho}>
        <CabeceraDias mes={mes} hoy={hoy} titulo="Canal" />

        {canales.map(canal => {
          const filas = filasDeEnvios(canal.envios, mes.clave)
          const clave = `envio:${canal.area}`
          return (
            <div key={canal.area} className="flex">
              <EtiquetaBanda
                clave={clave}
                filas={filas.length}
                extra={
                  <span className="text-[10px] font-semibold uppercase leading-none tracking-wide text-slate-500 dark:text-slate-400">
                    {canal.envios.length === 0
                      ? 'sin envíos'
                      : canal.envios.length === 1 ? '1 envío' : `${canal.envios.length} envíos`}
                  </span>
                }
                onAgregar={editable ? () => nuevoEnvio(canal.area, hoy ?? 1) : undefined}
                tituloAgregar={`Nuevo envío suelto por ${canal.titulo}`}
              >
                <span className="flex items-center gap-1.5">{ICONO[canal.area]} {canal.titulo}</span>
              </EtiquetaBanda>
              <Renglones clave={clave}>
                {filas.map((fila, i) => (
                  <FilaRejilla
                    key={i}
                    interna={i < filas.length - 1}
                    mes={mes}
                    fila={fila}
                    hoy={hoy}
                    // Cualquiera abre la ficha de un envío; crear, solo quien edita.
                    editable
                    esDerivada={b => !porBarra.get(b.id)?.suelto}
                    tituloDe={b => {
                      const e = porBarra.get(b.id)
                      if (!e) return b.nombre
                      return `${e.accion} · ${e.formato} · día ${e.dia}${e.hora ? ` a las ${e.hora}` : ''}` +
                        `${e.suelto ? ' · envío suelto' : ''}` +
                        `${e.heredaLaFecha ? ' · sin fecha propia, toma la de su acción' : ''}`
                    }}
                    onBarra={b => {
                      const e = porBarra.get(b.id)
                      if (e) abrirFicha(e.accionId)
                    }}
                    onDiaVacio={editable ? d => nuevoEnvio(canal.area, d) : undefined}
                  />
                ))}
              </Renglones>
            </div>
          )
        })}
      </MarcoScroll>

      {/* Sin envíos, una sola línea: el cartel grande con su ícono ocupaba
          más que el cronograma entero (pedido del 16/11/2026). Y la leyenda
          de colores recién hace falta cuando hay algo que leer. */}
      <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-300 bg-white px-4 py-2 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
        {total === 0 ? (
          <span>
            <b className="font-semibold">Todavía no hay envíos este mes.</b>{' '}
            Salen de la ficha de cada acción (Email, WhatsApp o Push) o se cargan sueltos con el + de cada canal.
          </span>
        ) : (
          <>
            <span className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-sm border-l-[3px] border-l-slate-900/40 bg-slate-200 dark:bg-slate-700" />
              de una acción: se edita en la ficha de la acción
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-sm bg-slate-200 dark:bg-slate-700" />
              suelto: tiene su propia ficha
            </span>
          </>
        )}
      </footer>
    </Seccion>
  )
}

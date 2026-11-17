'use client'

import { useEffect, useRef, useState } from 'react'
import { usePathname } from 'next/navigation'
import {
  ArrowRight, Building2, Check, MessageSquare, ChevronDown, Clock, Download, ExternalLink, FileText, Hourglass, Link2, Loader2, Lock,
  PartyPopper, Pencil, RotateCcw, Send, ShieldCheck, UserRound, X,
} from 'lucide-react'
import { toast } from 'sonner'
import { calendarioApi, entregasApi } from '@/lib/api'
import {
  ETIQUETA_DECISION, camposDe, fechaYHora, marcasPendientes, pasoEnLaVista, proximoPaso, tipoDePieza, versionAnterior,
  type DetalleEntregas, type FaseDetalle, type Marca, type Version,
} from '@/lib/calendario/entregas'
import { fechaCorta, hoyIso } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import type { Persona } from '@/lib/calendario/tipos'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { veCalendario } from '@/lib/alcance'
import { esExterno } from '@/lib/externos'
import { useVistaEntregas } from '@/store/entregas'
import { useCatalogoDeTipos } from '@/store/tiposDeTarea'
import { defColumna, quienLaHaceTexto } from '@/lib/calendario/tablero'
import { useDialogo } from '../useDialogo'
import { FormularioEntrega } from './FormularioEntrega'
import {
  FormularioEntregas, configParaEnviar, faltaEnConfig, type ConfigEntregas,
} from './FormularioEntregas'
import { ImagenConMarcas, Miniatura, type Pin } from './ImagenConMarcas'
import { LineaDeFases } from './LineaDeFases'
import { Revisor } from './Revisor'
import { urlDeImagen } from './useImagen'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

/**
 * Las entregas de una tarea, encima de todo: la línea de fases, el próximo
 * paso con su botón, la versión actual y la historia. Desde acá se entrega
 * y se revisa. Vive una sola vez, en el layout: la abren la ficha de la
 * acción, el tablero, "Mis tareas" y los avisos (ver store/entregas.ts).
 */
export default function VistaEntregas() {
  const tareaId = useVistaEntregas(s => s.tareaId)
  if (!tareaId) return null
  return <Contenido key={tareaId} tareaId={tareaId} />
}

function Contenido({ tareaId }: { tareaId: string }) {
  const modo = useVistaEntregas(s => s.modo)
  const setModo = useVistaEntregas(s => s.setModo)
  const cerrar = useVistaEntregas(s => s.cerrar)
  const huboCambios = useVistaEntregas(s => s.huboCambios)
  // Abierta desde el tablero para una sola cosa (entregar o revisar al
  // soltar la tarjeta): al terminar o cancelar, se vuelve al tablero.
  const soloEsto = useVistaEntregas(s => s.soloEsto)
  const { user } = useCurrentUser()
  const pathname = usePathname()
  const [detalle, setDetalle] = useState<DetalleEntregas | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [recarga, setRecarga] = useState(0)
  const cajaRef = useRef<HTMLDivElement>(null)
  const cerrarRef = useRef<HTMLButtonElement>(null)
  useDialogo(true, cajaRef, cerrarRef)

  useEffect(() => {
    let vivo = true
    entregasApi.detalle(tareaId)
      .then(({ data }) => { if (vivo) { setDetalle(data); setError(null) } })
      .catch(e => { if (vivo) setError(detalleDeError(e) ?? 'No se pudieron traer las entregas. Probá de nuevo.') })
    return () => { vivo = false }
  }, [tareaId, recarga])

  const version = detalle ? versionEnCurso(detalle) : null
  // Si de verdad hay un formulario abierto (entregar, revisar, configurar).
  // Si no se pudo abrir (falló la carga, la tarjeta ya cambió y no le toca,
  // la versión ya se decidió), se ve el resumen y se tiene que poder cerrar:
  // antes no había X ni Esc y el único botón era "Probar de nuevo".
  const formulario = !!detalle && (
    (modo === 'entregar' && detalle.puedo.entregar)
    || (modo === 'revisar' && detalle.puedo.decidir && !!version)
    || (modo === 'configurar' && detalle.puedo.configurar)
  )
  const sePuedeCerrar = !formulario

  // Escape cierra (solo mirando: entregando o revisando, se sale con Cancelar,
  // que avisa si hay algo sin mandar). Va en la captura para que no cierre
  // también la ficha que puede estar abajo.
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      if (sePuedeCerrar) cerrar()
    }
    window.addEventListener('keydown', tecla, true)
    return () => window.removeEventListener('keydown', tecla, true)
  }, [sePuedeCerrar, cerrar])

  /** Después de entregar, decidir o configurar: se trae todo de nuevo y se
   *  avisa al resto de la pantalla (el calendario, el tablero, Mis tareas). */
  function listo() {
    if (soloEsto) cerrar()
    else setModo('ver')
    setRecarga(n => n + 1)
    huboCambios()
    // Si el calendario está en pantalla (se abrió desde la ficha), se pone al
    // día ya. Desde el tablero o Mis tareas no: el calendario se trae solo al
    // volver, y bajar /datos entero (lo más pesado) con cada entrega no sirve.
    if (pathname?.startsWith('/calendario') && useCalendario.getState().rev != null) {
      void useCalendario.getState().sincronizar()
    }
  }

  // Revisando, la imagen necesita todo el lugar; en lo demás, la caja mide
  // lo que tiene adentro (sin un hueco blanco abajo) hasta el 92 % del alto.
  // Viendo la tarjeta, en pantalla grande, al costado van los comentarios
  // (17/11/2026, "como tiene Trello en un costado"): la caja es más ancha.
  const ancho = modo === 'revisar' ? 'sm:max-w-6xl sm:h-[92dvh]'
    : modo === 'ver' ? 'sm:max-w-3xl lg:max-w-5xl sm:h-auto sm:max-h-[92dvh]'
      : 'sm:max-w-3xl sm:h-auto sm:max-h-[92dvh]'

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center sm:p-4">
      <div className="velo animate-fade-in" onClick={() => { if (sePuedeCerrar) cerrar() }} aria-hidden />
      <div
        ref={cajaRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="entregas-titulo"
        tabIndex={-1}
        className={`relative flex h-[100dvh] w-full animate-sheet-up flex-col overflow-hidden bg-white shadow-panel outline-none dark:bg-slate-900 dark:ring-1 dark:ring-slate-700 sm:animate-scale-in sm:rounded-2xl ${ancho}`}
      >
        <Encabezado detalle={detalle} sePuedeCerrar={sePuedeCerrar} onCerrar={cerrar} cerrarRef={cerrarRef} />

        {error && !detalle && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
            <p className="text-sm text-slate-600 dark:text-slate-300">{error}</p>
            <button type="button" onClick={() => setRecarga(n => n + 1)} className="min-h-[44px] rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white">
              Probar de nuevo
            </button>
          </div>
        )}
        {!detalle && !error && (
          <div className="flex-1 space-y-4 p-5" role="status" aria-label="Cargando las entregas…">
            <div className="skeleton h-16 rounded-2xl" />
            <div className="skeleton h-20 rounded-2xl" />
            <div className="skeleton h-64 rounded-2xl" />
          </div>
        )}

        {detalle && modo === 'entregar' && detalle.puedo.entregar && (
          <FormularioEntrega detalle={detalle} onListo={listo} onCancelar={() => (soloEsto ? cerrar() : setModo('ver'))} />
        )}
        {detalle && modo === 'revisar' && detalle.puedo.decidir && version && (
          <Revisor
            detalle={detalle}
            version={version}
            anterior={versionAnterior(detalle.fases, version)}
            onListo={listo}
            onCancelar={() => (soloEsto ? cerrar() : setModo('ver'))}
          />
        )}
        {detalle && modo === 'configurar' && detalle.puedo.configurar && (
          <EditarConfiguracion detalle={detalle} onListo={listo} onCancelar={() => setModo('ver')} />
        )}
        {detalle && (modo === 'ver'
          || (modo === 'entregar' && !detalle.puedo.entregar)
          || (modo === 'revisar' && (!detalle.puedo.decidir || !version))
          || (modo === 'configurar' && !detalle.puedo.configurar)) && (
          <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
            <Resumen
              detalle={detalle}
              usuarioId={user?.id ?? null}
              // Cambiar la configuración necesita la lista de personas, que es
              // del calendario: con "No lo ve" el servidor no la da y el
              // formulario quedaba sin nombres. A esa persona no se le ofrece.
              puedeConfigurar={detalle.puedo.configurar && veCalendario(user)}
              onRecargar={() => setRecarga(n => n + 1)}
            />
            {/* En pantalla grande, los comentarios al costado; en una chica,
                van al final del resumen (ver Resumen). */}
            <Comentarios
              detalle={detalle}
              onRecargar={() => setRecarga(n => n + 1)}
              className="hidden min-h-0 border-l border-slate-200 dark:border-slate-800 lg:flex lg:w-80 lg:shrink-0 lg:flex-col"
            />
          </div>
        )}
      </div>
    </div>
  )
}

/** La versión de la fase en curso que está esperando, si hay. */
function versionEnCurso(d: DetalleEntregas): Version | null {
  const fase = d.fases.find(f => f.id === d.resumen.faseActual)
  const ultima = fase?.versiones[fase.versiones.length - 1]
  return ultima && ultima.estado === 'revision' ? ultima : null
}

function Encabezado({ detalle, sePuedeCerrar, onCerrar, cerrarRef }: {
  detalle: DetalleEntregas | null
  sePuedeCerrar: boolean
  onCerrar: () => void
  cerrarRef: React.Ref<HTMLButtonElement>
}) {
  const hoy = hoyIso()
  const t = detalle?.tarea
  const vencida = t?.vence && t.vence < hoy && detalle?.resumen.momento !== 'aprobada'
  // Lo que es: el tipo de tarea del catálogo ("Mailing", "Pantallas",
  // "Tótem") cuando la tarjeta tiene uno. El tipo de pieza de las entregas
  // los junta a todos en "Otro".
  const { tipos } = useCatalogoDeTipos()
  const queEs = (t?.tipo && tipos?.find(x => x.clave === t.tipo)?.nombre) || (detalle ? tipoDePieza(detalle.tipoPieza).nombre : '')
  return (
    <header className="flex shrink-0 items-start gap-3 border-b border-slate-300 px-4 pb-3 pt-4 dark:border-slate-700 sm:px-6">
      <div className="min-w-0 flex-1">
        {detalle ? (
          <>
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-semibold text-slate-600 dark:text-slate-400">
              <span className="rounded-full bg-brand-50 px-2 py-0.5 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
                {queEs}
              </span>
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="h-2.5 w-2.5 shrink-0 rounded-sm ring-1 ring-inset ring-black/10" style={{ backgroundColor: detalle.accion.color ?? '#cbd5e1' }} />
                <span className="truncate">{detalle.accion.nombre}</span>
              </span>
            </p>
            <h2 id="entregas-titulo" className="mt-1 text-xl font-bold leading-tight text-slate-900 dark:text-slate-100">{t?.titulo}</h2>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600 dark:text-slate-400">
              {detalle.columna && (
                <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                  <span className={`h-2 w-2 rounded-full ${defColumna(detalle.columna).punto}`} aria-hidden />
                  {defColumna(detalle.columna).titulo}
                </span>
              )}
              {t?.quienLaHace && t.quienLaHace.tipo !== 'tienda' ? (
                <span className="flex items-center gap-1"><Building2 className="h-4 w-4" /> La hace {quienLaHaceTexto(t.quienLaHace)}</span>
              ) : (
                <span className="flex items-center gap-1"><UserRound className="h-4 w-4" /> Entrega {t?.asignadoA != null ? detalle.personas[String(t.asignadoA)] ?? 'alguien' : 'nadie todavía'}</span>
              )}
              {t?.vence && (
                <span className={`flex items-center gap-1 ${vencida ? 'font-semibold text-rose-600 dark:text-rose-300' : ''}`}>
                  <Clock className="h-4 w-4" /> {vencida ? 'Venció el' : 'Vence el'} {fechaCorta(t.vence)}
                </span>
              )}
            </p>
          </>
        ) : (
          <h2 id="entregas-titulo" className="text-xl font-bold text-slate-900 dark:text-slate-100">Entregas</h2>
        )}
      </div>
      {sePuedeCerrar && (
        <button ref={cerrarRef} type="button" onClick={onCerrar} className="boton-icono -mr-2 -mt-1" aria-label="Cerrar las entregas" title="Cerrar (Esc)">
          <X className="h-5 w-5" />
        </button>
      )}
    </header>
  )
}

// ---------------------------------------------------------------------------
// Mirando
// ---------------------------------------------------------------------------

function Resumen({ detalle, usuarioId, puedeConfigurar, onRecargar }: {
  detalle: DetalleEntregas
  usuarioId: number | null
  puedeConfigurar: boolean
  onRecargar: () => void
}) {
  const setModo = useVistaEntregas(s => s.setModo)
  const huboCambios = useVistaEntregas(s => s.huboCambios)
  const { resumen, tarea, puedo } = detalle
  const nombreDe = (id: number | null) => (id != null ? detalle.personas[String(id)] : null) ?? 'alguien'
  const enCurso = versionEnCurso(detalle)
  const paso = pasoEnLaVista(
    proximoPaso(resumen, tarea.asignadoA, usuarioId, nombreDe, puedo.decidir && !puedo.comoRespaldo, {
      entregoYo: puedo.entregar, hace: tarea.quienLaHace,
    }),
    puedo.decidir, usuarioId != null && enCurso?.subidaPor === usuarioId,
  )
  // La versión que se muestra grande: la última de la fase en curso o, si ya
  // se aprobó todo, la aprobada de la última fase (la pieza que salió).
  const ultimaDeFase = (() => {
    const fase = detalle.fases.find(f => f.id === resumen.faseActual)
      ?? (resumen.momento === 'aprobada' ? detalle.fases[detalle.fases.length - 1] : undefined)
    return fase?.versiones[fase.versiones.length - 1] ?? null
  })()
  // La fase en curso, si la abrió una devolución: su texto va arriba de todo.
  const faseDevuelta = detalle.fases.find(f => f.id === resumen.faseActual && f.motivo) ?? null
  const pendientes = marcasPendientes(detalle.fases)
  const aCorregir = resumen.momento === 'cambios' ? pendientes.filter(m => m.tipo === 'cambio') : []
  const ajustes = pendientes.filter(m => m.tipo === 'ajuste')

  async function tildar(m: Marca, corregida: boolean) {
    try {
      await entregasApi.tildarMarca(m.id, corregida)
      onRecargar()
      huboCambios()
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo guardar.')
    }
  }

  const tonoPaso = paso.aQuien === 'vos'
    ? 'border-brand-300 bg-brand-50 dark:border-brand-500/40 dark:bg-brand-500/10'
    : resumen.momento === 'aprobada'
      ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10'
      : 'border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50'
  const IconoPaso = resumen.momento === 'aprobada' ? PartyPopper : paso.aQuien === 'vos' ? ArrowRight : Hourglass

  return (
    <div className="min-w-0 flex-1 space-y-6 overflow-y-auto overscroll-contain px-4 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-6">
      <LineaDeFases resumen={resumen} />

      {/* El próximo paso: lo primero que se lee, con su botón */}
      <section className={`rounded-2xl border p-4 ${tonoPaso}`} aria-label="Próximo paso">
        <div className="flex items-start gap-3">
          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
            paso.aQuien === 'vos' ? 'bg-brand-600 text-white' : resumen.momento === 'aprobada' ? 'bg-emerald-500 text-white' : 'bg-white text-slate-500 dark:bg-slate-900 dark:text-slate-400'
          }`}>
            <IconoPaso className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-base font-bold leading-snug text-slate-900 dark:text-slate-100">{paso.texto}</p>
            {resumen.momento === 'revision' && enCurso && (
              <CadenaDeAprobacion detalle={detalle} version={enCurso} />
            )}
            {resumen.momento === 'cambios' && paso.aQuien !== 'vos' && (
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">Volvió con cambios: lo corrige quien entrega.</p>
            )}
          </div>
        </div>
        {resumen.momento === 'aprobada' && puedo.devolver && (
          <DevolverAprobada tareaId={tarea.id} siguiente={`Entrega ${detalle.fases.length + 1}`} onListo={onRecargar} />
        )}
        {(paso.accion || (puedo.decidir && resumen.momento === 'revision')) && (
          <div className="mt-3 flex flex-wrap gap-2 sm:pl-[3.25rem]">
            {paso.accion === 'entregar' && puedo.entregar && (
              <button type="button" onClick={() => setModo('entregar')} className="flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] sm:min-h-[44px] sm:flex-none">
                <Send className="h-4 w-4" /> {resumen.momento === 'cambios' ? `Entregar ronda ${resumen.ronda + 1}` : 'Entregar'}
              </button>
            )}
            {puedo.decidir && resumen.momento === 'revision' && (
              <button type="button" onClick={() => setModo('revisar')} className={`flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-xl px-5 text-sm font-bold shadow-sm transition active:scale-[.98] sm:min-h-[44px] sm:flex-none ${
                puedo.comoRespaldo ? 'border border-violet-300 bg-white text-violet-800 hover:bg-violet-50 dark:border-violet-500/40 dark:bg-slate-900 dark:text-violet-200' : 'bg-brand-600 text-white hover:bg-brand-700'
              }`}>
                {puedo.comoRespaldo ? <ShieldCheck className="h-4 w-4" /> : <Check className="h-4 w-4" strokeWidth={3} />}
                {puedo.comoRespaldo ? 'Revisar como respaldo' : 'Revisar ahora'}
              </button>
            )}
          </div>
        )}
      </section>

      {faseDevuelta?.motivo && resumen.momento !== 'aprobada' && (
        <section aria-labelledby="motivo-devolucion" className="rounded-2xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-500/30 dark:bg-rose-500/10">
          <h3 id="motivo-devolucion" className="flex items-center gap-2 text-sm font-bold text-rose-800 dark:text-rose-200">
            <RotateCcw className="h-4 w-4" /> Volvió después de aprobada: {faseDevuelta.nombre}
          </h3>
          <p className="mt-1.5 whitespace-pre-line text-sm text-rose-950 dark:text-rose-50">{faseDevuelta.motivo}</p>
          {faseDevuelta.abiertaPor != null && (
            <p className="mt-1.5 text-xs text-rose-800/80 dark:text-rose-200/80">Lo pidió {nombreDe(faseDevuelta.abiertaPor)}</p>
          )}
        </section>
      )}

      {aCorregir.length > 0 && (
        <section aria-labelledby="hay-que-corregir">
          <h3 id="hay-que-corregir" className="mb-2 text-sm font-bold text-rose-700 dark:text-rose-300">
            Lo que hay que corregir ({aCorregir.length})
          </h3>
          <ol className="space-y-1.5">
            {aCorregir.map(m => (
              <li key={m.id} className="flex items-start gap-2 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:bg-rose-500/10 dark:text-rose-100">
                <span className="mt-0.5 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-rose-600 px-1 text-[11px] font-bold text-white">{m.numero}</span>
                <span className="min-w-0">{m.texto}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {ajustes.length > 0 && (
        <section aria-labelledby="ajustes">
          <h3 id="ajustes" className="mb-1 text-sm font-bold text-amber-800 dark:text-amber-200">Ajustes para el archivo final ({ajustes.length})</h3>
          <p className="mb-2 text-xs text-slate-600 dark:text-slate-400">Se aprobó con cambios: no hace falta otra ronda, pero hay que aplicarlos.</p>
          <ul className="space-y-1.5">
            {ajustes.map(m => (
              <li key={m.id}>
                <label className={`flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-50 ${puedo.tildarMarcas ? 'cursor-pointer' : ''}`}>
                  <input
                    type="checkbox"
                    checked={false}
                    disabled={!puedo.tildarMarcas}
                    onChange={() => void tildar(m, true)}
                    className="mt-0.5 h-5 w-5 shrink-0 rounded accent-emerald-600"
                    aria-label={`Marcar como aplicado: ${m.texto}`}
                  />
                  <span className="min-w-0"><strong>{m.numero}.</strong> {m.texto} <span className="text-xs opacity-70">· {m.fase}</span></span>
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}

      {ultimaDeFase && (
        <section aria-labelledby="ultima-version">
          <h3 id="ultima-version" className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">
            {resumen.momento === 'aprobada' ? 'La versión aprobada' : 'La última versión'}
          </h3>
          <TarjetaVersion detalle={detalle} version={ultimaDeFase} abierta />
        </section>
      )}

      {/* Antes de la primera entrega, lo que se pidió es lo que hay que leer: abierto. */}
      <Brief detalle={detalle} abiertoAlInicio={resumen.ronda === 0 && resumen.momento === 'produccion' && !detalle.fases.some(f => f.versiones.length > 0)} />
      <Historia detalle={detalle} sin={ultimaDeFase?.id ?? null} />

      {/* En pantalla chica, los comentarios van acá; en grande, al costado. */}
      <Comentarios detalle={detalle} onRecargar={onRecargar} className="flex flex-col lg:hidden" />

      {puedeConfigurar && (
        <button
          type="button"
          onClick={() => setModo('configurar')}
          className="flex min-h-[44px] items-center gap-2 rounded-xl px-3 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          <Pencil className="h-4 w-4" /> Cambiar el pedido, las fases o quiénes aprueban
        </button>
      )}
    </div>
  )
}

/**
 * Los comentarios de la tarjeta, como en Trello (17/11/2026: "deberíamos tener
 * una opción de poner comentario como tiene Trello en un costado, para así
 * poder explicar cambios y cosas así"). Los ve y los escribe cualquiera que ve
 * la tarjeta: el equipo y el tablero al que va; a los demás les llega a la
 * campanita.
 */
function Comentarios({ detalle, onRecargar, className = '' }: {
  detalle: DetalleEntregas
  onRecargar: () => void
  className?: string
}) {
  const comentarios = detalle.comentarios ?? []
  const [texto, setTexto] = useState('')
  const [mandando, setMandando] = useState(false)
  const id = `comentar-${detalle.tarea.id}-${className.includes('lg:hidden') ? 'abajo' : 'costado'}`

  async function comentar() {
    const t = texto.trim()
    if (!t || mandando) return
    setMandando(true)
    try {
      await entregasApi.comentar(detalle.tarea.id, { id: `co-${crypto.randomUUID()}`, texto: t })
      setTexto('')
      onRecargar()
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo guardar el comentario. Probá de nuevo.')
    } finally {
      setMandando(false)
    }
  }

  return (
    <section aria-labelledby={`${id}-titulo`} className={className}>
      <h3 id={`${id}-titulo`} className="flex items-center gap-2 px-4 pt-4 text-sm font-bold text-slate-900 dark:text-slate-100 lg:px-4">
        <MessageSquare className="h-4 w-4 text-brand-600 dark:text-brand-300" /> Comentarios
        {comentarios.length > 0 && <span className="rounded-full bg-slate-100 px-1.5 text-xs tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300">{comentarios.length}</span>}
      </h3>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {comentarios.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">Todavía no hay comentarios. Usalos para explicar cambios o hacer preguntas.</p>
        ) : (
          <ol className="space-y-2">
            {comentarios.map(c => (
              <li key={c.id} className={`rounded-xl px-3 py-2 ${c.mio ? 'ml-6 bg-brand-50 dark:bg-brand-500/10' : 'mr-6 bg-slate-100 dark:bg-slate-800'}`}>
                <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                  {c.mio ? 'Vos' : (c.autorNombre ?? 'Alguien del equipo')}
                  {c.fecha && <span className="font-normal text-slate-500 dark:text-slate-400"> · {fechaYHora(c.fecha)}</span>}
                </p>
                <p className="mt-0.5 whitespace-pre-line break-words text-sm text-slate-900 dark:text-slate-100">{c.texto}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
      <div className="space-y-2 border-t border-slate-200 px-4 py-3 dark:border-slate-800">
        <label htmlFor={id} className="sr-only">Escribí un comentario</label>
        <textarea
          id={id}
          value={texto}
          onChange={e => setTexto(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void comentar() } }}
          rows={2}
          maxLength={2000}
          placeholder="Escribí un comentario…"
          className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <button
          type="button"
          onClick={() => void comentar()}
          disabled={!texto.trim() || mandando}
          className="flex min-h-[40px] w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mandando && <Loader2 className="h-4 w-4 animate-spin" />} Comentar
        </button>
      </div>
    </section>
  )
}

/**
 * Devolver una pieza que ya estaba aprobada, con lo que hay que cambiar.
 *
 * Pedido de Ivan (17/11/2026): con la entrega aprobada "no aparece algo para
 * evaluar, un cuadro de texto o algo donde poder escribir algo para que
 * podamos volver para atrás el arte". Esto abre la Entrega siguiente (2, 3...
 * sin tope) y le avisa a quien entrega, con el texto.
 */
function DevolverAprobada({ tareaId, siguiente, onListo }: { tareaId: string; siguiente: string; onListo: () => void }) {
  const huboCambios = useVistaEntregas(s => s.huboCambios)
  const [abierto, setAbierto] = useState(false)
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function devolver() {
    const comentario = texto.trim()
    if (!comentario || enviando) return
    setEnviando(true)
    try {
      const { data } = await entregasApi.devolver(tareaId, comentario)
      toast.success(`Devuelta: le toca entregar ${data.fase.nombre}.`)
      setTexto('')
      setAbierto(false)
      onListo()
      huboCambios()
      if (useCalendario.getState().rev != null) void useCalendario.getState().sincronizar()
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo devolver. Probá de nuevo.')
    } finally {
      setEnviando(false)
    }
  }

  if (!abierto) {
    return (
      <div className="mt-3 sm:pl-[3.25rem]">
        <button
          type="button"
          onClick={() => setAbierto(true)}
          className="flex min-h-[44px] items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-rose-300 hover:text-rose-700 active:scale-[.98] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-rose-500/50 dark:hover:text-rose-200"
        >
          <RotateCcw className="h-4 w-4" /> Devolver para corregir
        </button>
      </div>
    )
  }
  return (
    <div className="mt-3 space-y-2 sm:pl-[3.25rem]">
      <label htmlFor={`devolver-${tareaId}`} className="block text-sm font-semibold text-slate-800 dark:text-slate-100">
        ¿Qué hay que cambiar?
      </label>
      <textarea
        id={`devolver-${tareaId}`}
        value={texto}
        onChange={e => setTexto(e.target.value)}
        rows={3}
        maxLength={5000}
        autoFocus
        placeholder="Por ejemplo: cambió el precio, ahora es 2x1."
        className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      <p className="text-xs text-slate-600 dark:text-slate-400">
        Se abre la {siguiente} y le llega el aviso a quien la hace, con este texto.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void devolver()}
          disabled={!texto.trim() || enviando}
          className="flex min-h-[44px] items-center gap-2 rounded-xl bg-rose-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-rose-700 active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {enviando ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />} Devolver
        </button>
        <button
          type="button"
          onClick={() => { setAbierto(false); setTexto('') }}
          className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Cancelar
        </button>
      </div>
    </div>
  )
}

/** "Marta ✓ → Carlos (le toca) → …": quién ya aprobó esta versión y a quién le toca. */
function CadenaDeAprobacion({ detalle, version }: { detalle: DetalleEntregas; version: Version }) {
  const nombreDe = (id: number | null) => (id != null ? detalle.personas[String(id)] : null) ?? 'alguien'
  const turno = detalle.resumen.aprobadorDeTurno
  return (
    <ol className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
      {detalle.aprobadores.map((id, i) => {
        const d = version.decisiones.find(x => x.aprobador === id)
        const toca = id === turno
        return (
          <li key={id} className="flex items-center gap-1.5">
            {i > 0 && <ArrowRight className="h-3 w-3 text-slate-500" aria-hidden />}
            <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold ${
              d ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200'
                : toca ? 'bg-amber-100 text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/15 dark:text-amber-100 dark:ring-amber-500/40'
                  : 'bg-white text-slate-500 dark:bg-slate-900 dark:text-slate-400'
            }`}>
              {d && <Check className="h-3 w-3" strokeWidth={3} />}
              {nombreDe(id)}{d ? (d.decision === 'aprobada-con-cambios' ? ' (con cambios)' : '') : toca ? ' · le toca' : ''}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

const ESTADO_VERSION = {
  revision: { texto: 'En revisión', tono: 'bg-amber-100 text-amber-900 dark:bg-amber-500/15 dark:text-amber-200' },
  aprobada: { texto: 'Aprobada', tono: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200' },
  cambios: { texto: 'Volvió con cambios', tono: 'bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-200' },
} as const

function TarjetaVersion({ detalle, version, abierta: abiertaAlInicio = false }: {
  detalle: DetalleEntregas
  version: Version
  abierta?: boolean
}) {
  const [abierta, setAbierta] = useState(abiertaAlInicio)
  const [activa, setActiva] = useState(version.imagenes[0]?.id ?? null)
  const nombreDe = (id: number | null) => (id != null ? detalle.personas[String(id)] : null) ?? 'Alguien'
  const pines: Pin[] = version.marcas.filter(m => m.imagenId === activa).map(m => ({
    clave: m.id, numero: m.numero, x: m.x, y: m.y, texto: m.texto,
    tono: m.corregida ? 'corregida' : m.tipo === 'ajuste' ? 'ajuste' : 'cambio',
  }))
  const estado = ESTADO_VERSION[version.estado]
  const todasPurgadas = version.imagenes.length > 0 && version.imagenes.every(i => i.purgada)
  const vivas = version.imagenes.filter(i => !i.purgada)
  const [bajando, setBajando] = useState(false)
  const { user } = useCurrentUser()
  // A quien la hizo (o a la agencia) no se le dice que se la pida a sí misma.
  const laHizoQuienMira = esExterno(user) || (user?.id != null && user.id === version.subidaPor)

  /** Bajar las imágenes de esta ronda (16/11/2026: "para no andar pidiéndolos
   *  por mail"). Son las mismas imágenes comprimidas que se ven (no se guarda
   *  nada nuevo: la base es de 500 MB): sirven para revisar, no para
   *  publicar. El archivo final es el original, que va por el link; por eso
   *  el botón dice qué es lo que baja. */
  async function descargar() {
    setBajando(true)
    try {
      const fase = detalle.fases.find(f => f.id === version.faseId)?.nombre ?? 'Entrega'
      const base = `${detalle.tarea.titulo} - ${fase} - ronda ${version.ronda} - vista previa`.replace(/[\\/:*?"<>|]+/g, '-')
      for (const [i, im] of vivas.entries()) {
        const url = await urlDeImagen(im.id, 'grande')
        const a = document.createElement('a')
        a.href = url
        a.download = vivas.length > 1 ? `${base} - ${i + 1}.jpg` : `${base}.jpg`
        document.body.appendChild(a)
        a.click()
        a.remove()
      }
      // Con varias, el navegador puede preguntar (o bloquear sin decir nada)
      // si se permiten varias descargas: no se da por hecho que bajaron todas.
      toast.success(vivas.length === 1
        ? 'Empezó a bajar la vista previa.'
        : `Empezaron a bajar ${vivas.length} imágenes: si el navegador pregunta, permití descargar varios archivos.`)
    } catch {
      toast.error('No se pudieron bajar las imágenes. Probá de nuevo.')
    } finally {
      setBajando(false)
    }
  }

  return (
    <article className="rounded-2xl border border-slate-300 bg-white p-3 dark:border-slate-700 dark:bg-slate-900 sm:p-4">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">Ronda {version.ronda}</h4>
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${estado.tono}`}>{estado.texto}</span>
        <span className="text-xs text-slate-500 dark:text-slate-400">{nombreDe(version.subidaPor)} · {fechaYHora(version.fecha)}</span>
        {/* 44 px para el dedo en el teléfono; en la compu, más chicos. */}
        <span className="ml-auto flex flex-wrap items-center justify-end gap-1">
          {version.link && vivas.length > 0 && (
            <a
              href={version.link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex min-h-[44px] items-center gap-1.5 rounded-lg px-2 text-xs font-bold text-brand-700 transition hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10 sm:min-h-[36px]"
              title={`El archivo final, en el link: ${version.link}`}
            >
              <ExternalLink className="h-3.5 w-3.5" /> Bajar el original
            </a>
          )}
          {vivas.length > 0 && (
            <button
              type="button"
              onClick={() => void descargar()}
              disabled={bajando}
              className="flex min-h-[44px] items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 disabled:opacity-60 dark:text-slate-200 dark:hover:bg-slate-800 sm:min-h-[36px]"
              title="Las imágenes de esta ronda, achicadas para revisar (1600 px, JPEG): no son el archivo final"
            >
              {bajando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />} Vista previa (1600 px)
            </button>
          )}
          {!abierta && version.imagenes.length > 0 && (
            <button type="button" onClick={() => setAbierta(true)} className="min-h-[44px] rounded-lg px-2 text-xs font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10 sm:min-h-[36px]">
              Ver grande
            </button>
          )}
        </span>
      </header>

      {/* Solo imágenes: lo que baja es la vista previa. Se dice, para que nadie
          publique una imagen achicada creyendo que es el archivo final. */}
      {!version.link && vivas.length > 0 && (
        <p className="mt-1.5 text-xs text-slate-600 dark:text-slate-400">
          {laHizoQuienMira
            ? 'Sin link al original: lo que se baja es la vista previa.'
            : 'Sin link al original: pedíselo a quien la hace.'}
        </p>
      )}

      {version.imagenes.length === 0 && version.link && (
        <a href={version.link} target="_blank" rel="noopener noreferrer" title={version.link}
          className="mt-2 flex items-center gap-2 rounded-xl border border-slate-300 bg-slate-50 px-3 py-2.5 text-sm font-semibold text-brand-700 transition hover:border-brand-400 dark:border-slate-700 dark:bg-slate-800/50 dark:text-brand-200">
          <Link2 className="h-4 w-4 shrink-0" /> <span className="min-w-0 truncate">Materiales en el link: {version.link}</span>
        </a>
      )}

      {todasPurgadas ? (
        <p className="mt-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
          Las imágenes de esta ronda ya se borraron (se guardan hasta un tiempo después de terminada la acción). Quedan las marcas y las decisiones.
        </p>
      ) : abierta && activa ? (
        <div className="mt-3 space-y-2">
          <ImagenConMarcas imagenId={activa} pines={pines} claseImagen="max-h-[50vh]" etiqueta={`Ronda ${version.ronda}`} />
          {version.imagenes.length > 1 && (
            <div className="flex gap-2 overflow-x-auto">
              {version.imagenes.map((im, i) => (
                <button key={im.id} type="button" onClick={() => setActiva(im.id)} aria-pressed={im.id === activa}
                  className={`shrink-0 rounded-xl p-0.5 ${im.id === activa ? 'ring-2 ring-brand-600' : 'opacity-70 hover:opacity-100'}`}>
                  <Miniatura imagenId={im.id} etiqueta={`Imagen ${i + 1}`} className="h-14 w-14" />
                </button>
              ))}
            </div>
          )}
        </div>
      ) : version.imagenes.length > 0 ? (
        <button type="button" onClick={() => setAbierta(true)} className="mt-2 flex gap-2" aria-label={`Ver la ronda ${version.ronda} grande`}>
          {version.imagenes.map((im, i) => <Miniatura key={im.id} imagenId={im.id} etiqueta={`Imagen ${i + 1}`} className="h-14 w-14" />)}
        </button>
      ) : null}

      {(version.comentario || (version.link && todasPurgadas)) && (
        <div className="mt-2 text-sm text-slate-700 dark:text-slate-300">
          {version.comentario && <p className="whitespace-pre-line">«{version.comentario}»</p>}
          {/* Con imágenes, el original está arriba ("Bajar el original"); sin
              imágenes, en el recuadro del link. Acá, si ya se borraron. */}
          {version.link && todasPurgadas && (
            <a href={version.link} target="_blank" rel="noopener noreferrer" className="mt-0.5 inline-flex items-center gap-1 font-semibold text-brand-700 underline underline-offset-2 dark:text-brand-200">
              <ExternalLink className="h-3.5 w-3.5" /> Abrir el original
            </a>
          )}
        </div>
      )}

      {version.decisiones.length > 0 && (
        <ul className="mt-2 space-y-1">
          {version.decisiones.map((d, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-x-1.5 text-sm">
              <span className={`font-semibold ${d.decision === 'cambios' ? 'text-rose-700 dark:text-rose-300' : d.decision === 'aprobada-con-cambios' ? 'text-amber-700 dark:text-amber-300' : 'text-emerald-700 dark:text-emerald-300'}`}>
                {d.decision === 'cambios' ? <RotateCcw className="mr-1 inline h-3.5 w-3.5" /> : <Check className="mr-1 inline h-3.5 w-3.5" strokeWidth={3} />}
                {nombreDe(d.aprobador)} {ETIQUETA_DECISION[d.decision].toLowerCase()}
              </span>
              {d.decididoPor !== d.aprobador && d.decididoPor != null && (
                <span className="text-xs text-violet-700 dark:text-violet-300">(decidió {nombreDe(d.decididoPor)} como respaldo)</span>
              )}
              <span className="text-xs text-slate-500 dark:text-slate-400">{fechaYHora(d.fecha)}</span>
              {d.comentario && <span className="w-full text-slate-600 dark:text-slate-400">«{d.comentario}»</span>}
              {d.notaInterna && (
                <span className="mt-0.5 flex w-full items-start gap-1.5 rounded-lg bg-amber-50 px-2 py-1 text-[13px] text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
                  <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                  <span><span className="font-semibold">Nota interna (la agencia no la ve):</span> {d.notaInterna}</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {version.marcas.length > 0 && (
        <ol className="mt-2 space-y-1">
          {version.marcas.map(m => (
            <li key={m.id} className="flex items-start gap-2 text-sm">
              <span className={`mt-0.5 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1 text-[11px] font-bold ${
                m.corregida ? 'bg-emerald-600 text-white' : m.tipo === 'ajuste' ? 'bg-amber-500 text-slate-950' : 'bg-rose-600 text-white'
              }`}>{m.corregida ? <Check className="h-3 w-3" strokeWidth={3} /> : m.numero}</span>
              <span className={`min-w-0 ${m.corregida ? 'text-slate-500 line-through decoration-slate-400 dark:text-slate-400' : 'text-slate-700 dark:text-slate-300'}`}>
                {m.texto}
                {m.tipo === 'ajuste' && <span className="ml-1 text-xs text-amber-700 no-underline dark:text-amber-300">(ajuste)</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </article>
  )
}

function Brief({ detalle, abiertoAlInicio = false }: { detalle: DetalleEntregas; abiertoAlInicio?: boolean }) {
  const [abierto, setAbierto] = useState(abiertoAlInicio)
  // Lo tildado con sus medidas ya está arriba (`pedido`): el detalle del
  // pedido que lo repite no se muestra dos veces.
  const pedido = detalle.tarea.pedido ?? null
  const campos = camposDe(detalle.tipoPieza).filter(c => detalle.brief[c.clave] != null && detalle.brief[c.clave] !== '')
    .filter(c => !(pedido && c.clave === 'detalle' && String(detalle.brief.detalle).trim() === pedido.trim()))
  return (
    <section>
      <button
        type="button"
        onClick={() => setAbierto(v => !v)}
        aria-expanded={abierto}
        className="-ml-2 flex min-h-[40px] items-center gap-1.5 rounded-xl px-2 text-sm font-bold text-slate-900 transition hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-800"
      >
        <FileText className="h-4 w-4 text-brand-600 dark:text-brand-300" />
        Lo que se pidió
        <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${abierto ? 'rotate-180' : ''}`} />
      </button>
      {abierto && pedido && (
        <p className="mt-2 whitespace-pre-line rounded-2xl border border-brand-200 bg-brand-50/60 p-3.5 text-sm font-medium leading-relaxed text-slate-800 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-slate-100">
          {pedido}
        </p>
      )}
      {abierto && (
        campos.length === 0 ? (
          pedido ? null : <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">El pedido no tiene detalles cargados.</p>
        ) : (
          <dl className="mt-2 grid gap-x-4 gap-y-2 rounded-2xl bg-slate-50 p-3.5 text-sm dark:bg-slate-800/50 sm:grid-cols-2">
            {campos.map(c => {
              const v = String(detalle.brief[c.clave])
              return (
                <div key={c.clave} className={c.entero ? 'sm:col-span-2' : ''}>
                  <dt className="text-xs font-semibold text-slate-500 dark:text-slate-400">{c.etiqueta}</dt>
                  <dd className="whitespace-pre-line break-words text-slate-800 dark:text-slate-200">
                    {c.tipo === 'fecha' ? fechaCorta(v) : c.tipo === 'url' && /^https?:\/\//i.test(v)
                      ? <a href={v} target="_blank" rel="noopener noreferrer" className="text-brand-700 underline dark:text-brand-200">{v}</a>
                      : v}
                  </dd>
                </div>
              )
            })}
          </dl>
        )
      )}
    </section>
  )
}

function Historia({ detalle, sin }: { detalle: DetalleEntregas; sin: string | null }) {
  const fases: FaseDetalle[] = detalle.fases
    .map(f => ({ ...f, versiones: f.versiones.filter(v => v.id !== sin).reverse() }))
    .filter(f => f.versiones.length > 0)
  if (fases.length === 0) return null
  return (
    <section aria-labelledby="historia">
      <h3 id="historia" className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">Rondas anteriores</h3>
      <div className="space-y-4">
        {fases.map(f => (
          <div key={f.id}>
            <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">{f.nombre}</p>
            <div className="space-y-2">
              {f.versiones.map(v => <TarjetaVersion key={v.id} detalle={detalle} version={v} />)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Cambiar el pedido, las fases o los aprobadores
// ---------------------------------------------------------------------------

function EditarConfiguracion({ detalle, onListo, onCancelar }: {
  detalle: DetalleEntregas
  onListo: () => void
  onCancelar: () => void
}) {
  const { user } = useCurrentUser()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [guardando, setGuardando] = useState(false)
  const [config, setConfig] = useState<ConfigEntregas>(() => ({
    tipoPieza: detalle.tipoPieza,
    brief: Object.fromEntries(Object.entries(detalle.brief).map(([k, v]) => [k, String(v)])),
    fases: detalle.fases.map(f => ({ id: f.id, nombre: f.nombre, bloqueada: f.versiones.length > 0 || f.estado === 'aprobada' })),
    aprobadores: detalle.aprobadores,
  }))

  useEffect(() => {
    let vivo = true
    calendarioApi.personas(detalle.accion.mundo)
      .then(({ data }) => { if (vivo) setPersonas(data) })
      .catch(() => { if (vivo) toast.error('No se pudo traer la lista de personas.') })
    return () => { vivo = false }
  }, [detalle.accion.mundo])

  // De una agencia de afuera, `asignadoA` es quien del equipo CARGA lo que
  // manda, no quien la hace: puede aprobar (es lo común: la carga y la
  // aprueba la misma persona). La regla "quien entrega no aprueba" no va.
  const responsableId = detalle.tarea.quienLaHace?.tipo === 'fuera' ? null : detalle.tarea.asignadoA
  const falta = faltaEnConfig(config, responsableId)

  async function guardar() {
    if (falta || guardando) return
    setGuardando(true)
    try {
      await entregasApi.configurar(detalle.tarea.id, configParaEnviar(config))
      toast.success('Listo: se guardaron los cambios.')
      onListo()
    } catch (e) {
      toast.error(detalleDeError(e) ?? 'No se pudo guardar.')
      setGuardando(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6">
        <FormularioEntregas
          valor={config}
          onCambiar={setConfig}
          personas={personas}
          responsableId={responsableId}
          usuarioId={user?.id ?? null}
        />
      </div>
      <div className="flex shrink-0 items-center gap-2 border-t border-slate-300 px-4 py-3 pb-[max(.75rem,env(safe-area-inset-bottom))] dark:border-slate-700 sm:px-6">
        {falta && <p className="flex-1 text-xs text-amber-700 dark:text-amber-300">{falta}</p>}
        <button type="button" onClick={onCancelar} className="ml-auto min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
          Cancelar
        </button>
        <button
          type="button"
          onClick={() => void guardar()}
          disabled={!!falta || guardando}
          className="flex min-h-[44px] items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
        >
          {guardando && <Loader2 className="h-4 w-4 animate-spin" />} Guardar
        </button>
      </div>
    </div>
  )
}

'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Building2, CalendarClock, Check, ChevronDown, Layers, Mic, Plus, Sparkles, Store, UserRound, X } from 'lucide-react'
import { toast } from 'sonner'
import { DictarBrief, type BriefListo } from '@/components/ia/DictarBrief'
import { useCalendario } from '@/lib/calendario/store'
import { camposVisibles, descripcionDelPedido, nombreDeTarjeta, type TipoDeTarea } from '@/lib/calendario/tipos-de-tarea'
import { TIPOS_DE_PIEZA, type TipoPieza } from '@/lib/calendario/entregas'
import { TIPO_PARA_DICTADO } from '@/lib/calendario/entregas-dictado'
import { fechaCorta, hoyIso } from '@/lib/calendario/fechas'
import { venceAnclado } from '@/lib/calendario/plantillas'
import { delEquipo, type BarraGuardada, type Persona } from '@/lib/calendario/tipos'
import { useCatalogoDeTipos } from '@/store/tiposDeTarea'
import { useDialogo } from './useDialogo'
import {
  FormularioEntregas, configInicial, configParaEnviar, faltaEnConfig, type ConfigEntregas,
} from './entregas/FormularioEntregas'

/**
 * Pedir una pieza desde la ficha de una acción (16/11/2026): elegís qué es
 * (Banners, Email marketing, Mailing, Cenefas…), tildás lo que hace falta
 * —cada opción con su medida a la vista—, quién la hace y para cuándo. Le nace
 * sola su tarjeta en el tablero, en «Ingresado», con el nombre "<Acción> -
 * <Tipo>", y a quien la hace le llega "Iván te pidió: …".
 *
 * ¿Quién la hace? Una agencia que usa la plataforma (le aparece en su
 * tablero), alguien del equipo de diseño de Tienda, u otra agencia que no
 * usa la plataforma (alguien del equipo carga lo que manda).
 *
 * La fecha es N días antes del inicio de la acción (se mueve si la acción se
 * mueve) o una fija. La descripción es opcional (se puede dictar). El
 * formulario largo de entregas (fases, aprobadores, el pedido por campos) es
 * "Más opciones", solo para quien gestiona tareas.
 *
 * El catálogo (los tipos, las opciones y sus medidas) lo manda el servidor:
 * se edita en un solo lugar (backend/app/services/tipos_de_tarea.py).
 */
type Quien = 'agencia' | 'tienda' | 'fuera'

const DIAS_RAPIDOS = [1, 2, 3]
/** Lo mismo que acepta el servidor para "N días antes" (calendario.py, _DIAS_DE_ANCLA). */
const DIAS_MAXIMOS = 365

export function PedirPieza({ accion, parentId = null, tareaMadre, personas, usuarioId, gestiona, onListo }: {
  accion: BarraGuardada
  /** La tarea de la que es material (17/11/2026: "crear tarea y debajo de
   *  eso poder asignar los materiales de esa tarea creada"). */
  parentId?: string | null
  tareaMadre?: string
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
  onListo: () => void
}) {
  const crear = useCalendario(s => s.crearTarea)
  const configurarEntregas = useCalendario(s => s.configurarEntregas)
  const { tipos, error, reintentar } = useCatalogoDeTipos()

  // Las agencias que usan la plataforma: las empresas de las cuentas externas
  // que entran a este mundo. Con una sola, ya elegida.
  const agencias = useMemo(() => {
    const vistas = new Map<string, string>()
    for (const p of personas) if (p.externo && p.empresa) vistas.set(p.empresa.toLocaleLowerCase('es'), p.empresa)
    return [...vistas.values()].sort((a, b) => a.localeCompare(b, 'es'))
  }, [personas])
  const equipo = delEquipo(personas)

  const [tipoClave, setTipoClave] = useState<string | null>(null)
  const [opciones, setOpciones] = useState<string[]>([])
  // Las opciones del tipo se eligen en un modal en el centro (17/11/2026).
  const [eligiendoOpciones, setEligiendoOpciones] = useState(false)
  const [detalles, setDetalles] = useState<Record<string, string>>({})
  // Hasta que se elija, la agencia si hay alguna (es lo más común), si no Tienda.
  // Las personas pueden llegar después de abrir el formulario: por eso se deriva.
  const [quienElegido, setQuien] = useState<Quien | null>(null)
  const quien: Quien = quienElegido ?? (agencias.length ? 'agencia' : 'tienda')
  const [agenciaElegida, setAgencia] = useState<string>('')
  const agencia = agenciaElegida || agencias[0] || ''
  const [disenador, setDisenador] = useState<string>('')
  const [afuera, setAfuera] = useState('')
  const [cargaAfuera, setCargaAfuera] = useState<string>(usuarioId != null ? String(usuarioId) : '')
  const [cuando, setCuando] = useState<'antes' | 'fecha'>('antes')
  const [dias, setDias] = useState(3)
  // Lo que se está escribiendo en "N días antes" (puede quedar vacío un
  // momento mientras se escribe; `dias` es siempre un número válido).
  const [diasTexto, setDiasTexto] = useState<string | null>(null)
  const [fecha, setFecha] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [dictando, setDictando] = useState(false)
  const [masOpciones, setMasOpciones] = useState(false)
  const [config, setConfig] = useState<ConfigEntregas>(() => ({ ...configInicial('otro'), fases: [{ nombre: 'Entrega' }], aprobadores: usuarioId != null ? [usuarioId] : [] }))

  const tipo: TipoDeTarea | null = tipos?.find(t => t.clave === tipoClave) ?? null
  const titulo = nombreDeTarjeta(accion.nombre, tipo)
  const vence = cuando === 'antes' ? venceAnclado('inicio', -dias, accion.desde, accion.hasta) : fecha
  const pedido = descripcionDelPedido(tipo, opciones, detalles)
  const responsable = quien === 'tienda' ? (disenador ? Number(disenador) : null) : quien === 'fuera' ? (cargaAfuera ? Number(cargaAfuera) : null) : null
  // De una agencia de afuera, `responsable` es quien del equipo CARGA lo que
  // manda, no quien la hace: puede aprobar (lo común es que la cargue y la
  // apruebe la misma persona). Para la regla "quien entrega no aprueba", nadie.
  const quienEntrega = quien === 'fuera' ? null : responsable
  // La fecha ya pasó: la tarjeta nacería vencida. Se avisa, sin trabar.
  const yaPaso = /^\d{4}-\d{2}-\d{2}$/.test(vence) && vence < hoyIso()
  // El dictado ordena según lo elegido en "¿Qué es?" (Banners → banner web,
  // EMM → el mail, Cenefas → cenefa; Mailing, el folleto, y lo demás → otro).
  // Antes arrancaba siempre en cenefa.
  const piezaDictado = TIPO_PARA_DICTADO[TIPOS_DE_PIEZA.some(p => p.tipo === tipo?.pieza) ? (tipo!.pieza as TipoPieza) : 'otro']

  const falta = !tipo ? 'Elegí qué es.'
    : quien === 'agencia' && !agencia ? 'Elegí qué agencia la hace.'
      : quien === 'fuera' && !afuera.trim() ? 'Escribí el nombre de la agencia de afuera.'
        : quien === 'fuera' && responsable == null ? 'Elegí quién del equipo carga lo que manda.'
          : cuando === 'fecha' && !/^\d{4}-\d{2}-\d{2}$/.test(fecha) ? 'Elegí la fecha.'
            : masOpciones ? faltaEnConfig(config, quienEntrega) : null

  function escribirDias(texto: string) {
    setCuando('antes')
    setDiasTexto(texto)
    const n = Number(texto)
    if (texto.trim() !== '' && Number.isFinite(n)) setDias(Math.max(0, Math.min(DIAS_MAXIMOS, Math.round(n))))
  }

  function alternar(o: string) {
    setOpciones(prev => (prev.includes(o) ? prev.filter(x => x !== o) : [...prev, o]))
  }
  function agregarOtra(texto: string) {
    const o = texto.trim()
    if (!o) return
    if (!opciones.some(x => x.toLocaleLowerCase('es') === o.toLocaleLowerCase('es'))) setOpciones(prev => [...prev, o])
  }
  function elegirTipo(clave: string) {
    const elegido = tipos?.find(x => x.clave === clave)
    // Ivan (17/11/2026): "si aprieto banners que se abra un modal en el
    // centro que me dé todas las opciones de banners a marcar, y así con
    // todo". Los tipos sin opciones (Push, Tótem, Otro) no abren nada.
    const conOpciones = !!elegido && (elegido.opciones.length > 0 || elegido.otras || elegido.campos.length > 0)
    if (clave === tipoClave) {
      if (conOpciones) setEligiendoOpciones(true)
      return
    }
    setEligiendoOpciones(conOpciones)
    setTipoClave(clave)
    setOpciones([])
    setDetalles({})
    // El tipo de pieza de las entregas sale del tipo de tarea, como en el
    // servidor: con "Más opciones" abierto quedaba siempre en "Otro".
    const pieza = tipos?.find(x => x.clave === clave)?.pieza
    setConfig(c => ({ ...c, tipoPieza: TIPOS_DE_PIEZA.some(p => p.tipo === pieza) ? (pieza as TipoPieza) : 'otro' }))
  }
  function usarDictado(brief: BriefListo) {
    setDescripcion(brief.comoTexto.slice(0, 5000))
    setDictando(false)
  }

  function pedir(e: React.FormEvent) {
    e.preventDefault()
    if (falta || !tipo) return
    const detallesLimpios: Record<string, string | number> = {}
    for (const c of camposVisibles(tipo, opciones)) {
      const v = (detalles[c.clave] ?? '').trim()
      if (v) detallesLimpios[c.clave] = c.opciones ? v : Number(v)
    }
    const id = crear(accion.id, {
      titulo,
      parentId,
      descripcion: descripcion.trim() || null,
      asignadoA: responsable,
      para: quien,
      agencia: quien === 'agencia' ? agencia : quien === 'fuera' ? afuera.trim() : null,
      tipo: tipo.clave,
      opciones,
      detalles: detallesLimpios,
      ...(cuando === 'antes' ? { ancla: 'inicio' as const, anclaDias: -dias } : { vence: fecha }),
    })
    if (id && masOpciones && gestiona) {
      // Va en la cola de la acción, detrás del alta: reemplaza las entregas
      // por defecto con las que nace (una fase, la aprueba quien la pidió).
      // El pedido viaja igual que sin "Más opciones": lo tildado con sus
      // medidas y la descripción escrita. Antes este guardado lo pisaba y a
      // la agencia no le llegaba lo que se había escrito.
      const datos = configParaEnviar(config)
      const detalle = [pedido, descripcion.trim(), typeof datos.brief.detalle === 'string' ? datos.brief.detalle : '']
        .filter(Boolean).join('\n').slice(0, 5000)
      if (detalle) datos.brief.detalle = detalle
      else delete datos.brief.detalle
      void configurarEntregas(accion.id, id, datos).then(ok => {
        if (ok) toast.success('Se guardaron las fases y quiénes aprueban.')
      })
    }
    onListo()
  }

  return (
    <form
      onSubmit={pedir}
      onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onListo() } }}
      className="mt-3 animate-scale-in space-y-4 rounded-2xl border border-brand-200 bg-brand-50/50 p-3.5 dark:border-brand-500/30 dark:bg-brand-500/[.06] sm:p-4"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-bold text-brand-800 dark:text-brand-200">
          <Layers className="h-4 w-4" /> {tareaMadre ? `Nueva pieza para «${tareaMadre}»` : 'Pedir una pieza'}
        </p>
        <button type="button" onClick={onListo} aria-label="Cerrar sin pedir" className="-mr-1.5 -mt-1.5 flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 hover:bg-white/70 dark:text-slate-400 dark:hover:bg-slate-800">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* ¿Qué es? */}
      <fieldset>
        <legend className="etiqueta-campo">¿Qué es?</legend>
        {!tipos ? (
          error ? (
            <button type="button" onClick={reintentar} className="text-sm font-semibold text-brand-700 underline dark:text-brand-200">
              No se pudieron traer los tipos. Probar de nuevo
            </button>
          ) : <div className="skeleton h-10 rounded-xl" />
        ) : (
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Qué es">
            {tipos.map(t => (
              <button
                key={t.clave}
                type="button"
                role="radio"
                aria-checked={tipoClave === t.clave}
                onClick={() => elegirTipo(t.clave)}
                className={`min-h-[40px] rounded-xl border px-3 text-sm font-semibold transition active:scale-95 ${
                  tipoClave === t.clave
                    ? 'border-brand-600 bg-brand-600 text-white shadow-sm'
                    : 'border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:text-brand-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-brand-500/60'
                }`}
              >
                {t.nombre}
              </button>
            ))}
          </div>
        )}
      </fieldset>

      {tipo && (
        <div className="animate-fade-in space-y-3 rounded-xl border border-slate-300 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
          <p className="text-sm text-slate-700 dark:text-slate-200">
            Se va a llamar <strong className="font-bold text-slate-900 dark:text-slate-50">{titulo}</strong>
          </p>
          {tipo.bajada && <p className="rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-100">{tipo.bajada}</p>}
          {tipo.medida && <p className="text-xs font-medium text-slate-600 dark:text-slate-300">Medida: {tipo.medida}</p>}
          {(tipo.opciones.length > 0 || tipo.otras || tipo.campos.length > 0) && (
            <div className="space-y-2">
              {/* Solo los nombres: con las medidas va abajo, en "Lo que va a ver quien la hace". */}
              {opciones.length > 0 ? (
                <ul className="flex flex-wrap gap-1.5" aria-label={`${tipo.nombre} elegidos`}>
                  {opciones.map(o => (
                    <li key={o} className="rounded-lg bg-brand-50 px-2 py-1 text-xs font-semibold text-brand-800 ring-1 ring-brand-200 dark:bg-brand-500/10 dark:text-brand-100 dark:ring-brand-500/30">{o}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-600 dark:text-slate-400">Todavía no elegiste qué {tipo.nombre.toLocaleLowerCase('es')} hacen falta.</p>
              )}
              <button
                type="button"
                onClick={() => setEligiendoOpciones(true)}
                className="flex min-h-[44px] items-center gap-2 rounded-xl border border-brand-300 bg-white px-3 text-sm font-semibold text-brand-700 transition hover:bg-brand-50 active:scale-[.98] dark:border-brand-500/50 dark:bg-slate-900 dark:text-brand-200 dark:hover:bg-brand-500/10 sm:min-h-[40px]"
              >
                <Check className="h-4 w-4" /> {opciones.length > 0 ? 'Cambiar lo elegido' : `Elegir ${tipo.nombre.toLocaleLowerCase('es')}`}
              </button>
            </div>
          )}
        </div>
      )}
      {tipo && eligiendoOpciones && (
        <ModalDeOpciones
          tipo={tipo}
          opciones={opciones}
          detalles={detalles}
          onAlternar={alternar}
          onAgregarOtra={agregarOtra}
          onDetalle={(clave, valor) => setDetalles(d => ({ ...d, [clave]: valor }))}
          onCerrar={() => setEligiendoOpciones(false)}
        />
      )}

      {/* ¿Quién la hace? */}
      <fieldset>
        <legend className="etiqueta-campo">¿Quién la hace?</legend>
        <div className="grid gap-1.5 sm:grid-cols-3" role="radiogroup" aria-label="Quién la hace">
          {([
            ['agencia', 'Una agencia', 'Que usa Core Tienda', Building2],
            ['tienda', 'Diseño de Tienda', 'Alguien del equipo', UserRound],
            ['fuera', 'Otra agencia', 'Fuera de la plataforma', Store],
          ] as const).map(([valor, nombre, bajada, Icono]) => (
            // La elegida, con relleno y tilde (no solo un borde de otro tono:
            // en oscuro casi no se distinguía). La deshabilitada no baja la
            // opacidad: el motivo ("No hay cuentas de agencia") se tiene que leer.
            <button key={valor} type="button" role="radio" aria-checked={quien === valor} onClick={() => setQuien(valor)}
              disabled={valor === 'agencia' && agencias.length === 0}
              className={`flex min-h-[52px] items-center gap-2.5 rounded-xl border px-3 text-left transition disabled:cursor-not-allowed disabled:border-dashed disabled:bg-slate-50 dark:disabled:bg-slate-800/40 ${
                quien === valor ? 'border-brand-600 bg-brand-50 ring-2 ring-brand-500/40 dark:border-brand-400 dark:bg-brand-500/20' : 'border-slate-300 bg-white/70 hover:border-brand-400 dark:border-slate-700 dark:bg-slate-900/60'
              }`}>
              <Icono className={`h-5 w-5 shrink-0 ${quien === valor ? 'text-brand-600 dark:text-brand-300' : 'text-slate-500 dark:text-slate-400'}`} />
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-slate-900 dark:text-slate-100">{nombre}</span>
                <span className="block text-xs text-slate-600 dark:text-slate-400">{valor === 'agencia' && agencias.length === 0 ? 'No hay cuentas de agencia' : bajada}</span>
              </span>
              {quien === valor && <Check className="ml-auto h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" strokeWidth={3} aria-hidden />}
            </button>
          ))}
        </div>
        <div className="mt-2">
          {quien === 'agencia' && agencias.length > 1 && (
            <select value={agencia} onChange={e => setAgencia(e.target.value)} aria-label="Qué agencia" className="campo">
              {agencias.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          )}
          {quien === 'agencia' && agencias.length === 1 && (
            <p className="text-sm text-slate-700 dark:text-slate-200">La hace <strong>{agencias[0]}</strong>: le aparece en su tablero.</p>
          )}
          {quien === 'tienda' && (
            <select value={disenador} onChange={e => setDisenador(e.target.value)} aria-label="Quién de Tienda la hace" className="campo">
              <option value="">Sin asignar por ahora</option>
              {equipo.map(p => <option key={p.id} value={p.id}>{p.nombre}{p.id === usuarioId ? ' (vos)' : ''}</option>)}
            </select>
          )}
          {quien === 'fuera' && (
            <div className="grid gap-2 sm:grid-cols-2">
              <input value={afuera} onChange={e => setAfuera(e.target.value)} maxLength={120} placeholder="Nombre de la agencia" aria-label="Nombre de la agencia de afuera" className="campo" />
              <select value={cargaAfuera} onChange={e => setCargaAfuera(e.target.value)} aria-label="Quién del equipo carga lo que manda" className="campo">
                <option value="">¿Quién carga lo que manda?</option>
                {equipo.map(p => <option key={p.id} value={p.id}>Lo carga {p.nombre}{p.id === usuarioId ? ' (vos)' : ''}</option>)}
              </select>
            </div>
          )}
        </div>
      </fieldset>

      {/* ¿Para cuándo? */}
      <fieldset>
        <legend className="etiqueta-campo">¿Para cuándo?</legend>
        <div className="flex flex-wrap items-center gap-1.5">
          {DIAS_RAPIDOS.map(n => (
            <button key={n} type="button" aria-pressed={cuando === 'antes' && dias === n} onClick={() => { setCuando('antes'); setDias(n); setDiasTexto(null) }}
              className={`min-h-[40px] rounded-xl border px-3 text-sm font-semibold transition ${
                cuando === 'antes' && dias === n ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-brand-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200'
              }`}>
              {n} {n === 1 ? 'día' : 'días'} antes
            </button>
          ))}
          {/* Cualquier otro N (un catálogo de 44 páginas pide 15 días): sigue
              atado al inicio de la acción, así se mueve si la acción se mueve.
              Con "Otra fecha" queda fija. */}
          <label className={`flex min-h-[40px] items-center gap-1.5 rounded-xl border px-2 text-sm font-semibold ${
            cuando === 'antes' && !DIAS_RAPIDOS.includes(dias) ? 'border-brand-600 ring-2 ring-brand-500/30' : 'border-slate-300 dark:border-slate-600'
          } bg-white text-slate-700 dark:bg-slate-900 dark:text-slate-200`}>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={DIAS_MAXIMOS}
              value={diasTexto ?? (cuando === 'antes' && !DIAS_RAPIDOS.includes(dias) ? String(dias) : '')}
              onChange={e => escribirDias(e.target.value)}
              onBlur={() => setDiasTexto(null)}
              placeholder="N"
              aria-label="Cuántos días antes del inicio"
              className="h-8 w-14 rounded-lg border border-slate-300 bg-white px-1.5 text-center tabular-nums text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            />
            días antes
          </label>
          <button type="button" aria-pressed={cuando === 'fecha'} onClick={() => setCuando('fecha')}
            className={`min-h-[40px] rounded-xl border px-3 text-sm font-semibold transition ${
              cuando === 'fecha' ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-brand-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200'
            }`}>
            Otra fecha
          </button>
          {cuando === 'fecha' && (
            <input type="date" min="2000-01-01" max="2100-12-31" value={fecha} onChange={e => setFecha(e.target.value)} aria-label="Fecha" className="campo !w-auto" />
          )}
        </div>
        {cuando === 'antes' && (
          <p className="mt-1.5 flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300">
            <CalendarClock className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <span>
              Para el {fechaCorta(vence)} · {dias === 0 ? 'el día que arranca' : `${dias} ${dias === 1 ? 'día' : 'días'} antes de que arranque`} {accion.nombre}. Si la acción se mueve, se mueve con ella.
            </span>
          </p>
        )}
        {yaPaso && (
          <p className="mt-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-900 ring-1 ring-amber-300 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-500/40" role="status">
            Esa fecha ya pasó ({fechaCorta(vence)}): la tarjeta nacería vencida. Elegí menos días o una fecha nueva.
          </p>
        )}
      </fieldset>

      {/* Descripción (opcional, se puede dictar) */}
      <div>
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <label htmlFor={`pieza-desc-${accion.id}`} className="etiqueta-campo mb-0">Descripción (opcional)</label>
          {!dictando && (
            <button type="button" onClick={() => setDictando(true)} className="flex h-10 items-center gap-1.5 rounded-lg px-2.5 text-sm font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10">
              <Mic className="h-4 w-4" /> Dictar
            </button>
          )}
        </div>
        {dictando ? (
          // Con el tipo de lo que se pide (y solo ese): si se cambia "¿Qué
          // es?" mientras se dicta, arranca de nuevo con el tipo nuevo.
          <DictarBrief
            key={tipoClave ?? 'sin-tipo'}
            tipoInicial={piezaDictado}
            tipos={[piezaDictado]}
            etiquetaUsar="Usar en la descripción"
            onListo={usarDictado}
            onCancelar={() => setDictando(false)}
          />
        ) : (
          <textarea id={`pieza-desc-${accion.id}`} value={descripcion} onChange={e => setDescripcion(e.target.value)} rows={descripcion ? 4 : 2}
            maxLength={5000} placeholder="Lo que no entra en lo tildado: tono, referencias, qué no puede faltar…" className="campo !h-auto py-2.5" />
        )}
      </div>

      {pedido && (
        <div className="rounded-xl bg-white/80 px-3 py-2.5 text-xs leading-relaxed text-slate-700 ring-1 ring-slate-300 dark:bg-slate-900/70 dark:text-slate-200 dark:ring-slate-700">
          <p className="mb-0.5 font-semibold text-slate-900 dark:text-slate-100">Lo que va a ver quien la hace</p>
          <p className="whitespace-pre-line">{pedido}</p>
        </div>
      )}

      {gestiona && (
        <div>
          <button type="button" onClick={() => setMasOpciones(v => !v)} aria-expanded={masOpciones}
            className="-ml-2 flex min-h-[40px] items-center gap-1 rounded-xl px-2 text-sm font-semibold text-slate-700 hover:bg-white/70 dark:text-slate-200 dark:hover:bg-slate-800">
            <ChevronDown className={`h-4 w-4 transition-transform ${masOpciones ? 'rotate-180' : ''}`} />
            Más opciones: fases y quiénes aprueban
          </button>
          {masOpciones && (
            <div className="mt-2 rounded-xl border border-slate-300 bg-white p-3.5 dark:border-slate-700 dark:bg-slate-900">
              <FormularioEntregas valor={config} onCambiar={setConfig} personas={personas} responsableId={quienEntrega} usuarioId={usuarioId} ocultarTipo={!!tipo} />
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2">
        {falta && <p className="mr-auto text-xs font-medium text-amber-800 dark:text-amber-200">{falta}</p>}
        <button type="button" onClick={onListo} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 hover:bg-white/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
          Cancelar
        </button>
        <button type="submit" disabled={!!falta}
          className="flex min-h-[44px] items-center gap-1.5 rounded-xl bg-brand-600 px-4 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]">
          <Sparkles className="h-4 w-4" /> Pedir
        </button>
      </div>
    </form>
  )
}


/**
 * Las opciones de un tipo de pieza en un modal en el centro de la pantalla.
 *
 * Ivan (17/11/2026): "si aprieto banners que se abra un modal en el centro
 * que me dé todas las opciones de banners a marcar, y así con todo". Va con
 * portal al <body> (o al calendario en pantalla completa, donde el navegador
 * muestra solo ese elemento): adentro de la ficha, que se anima con
 * transform, un `fixed` quedaba atado a la ficha y no a la pantalla.
 */
function ModalDeOpciones({ tipo, opciones, detalles, onAlternar, onAgregarOtra, onDetalle, onCerrar }: {
  tipo: TipoDeTarea
  opciones: string[]
  detalles: Record<string, string>
  onAlternar: (opcion: string) => void
  onAgregarOtra: (texto: string) => void
  onDetalle: (clave: string, valor: string) => void
  onCerrar: () => void
}) {
  const cajaRef = useRef<HTMLDivElement>(null)
  const [otra, setOtra] = useState('')
  useDialogo(true, cajaRef)

  // Escape cierra el modal y nada más: va en la captura y corta ahí, así la
  // ficha y el pedido de abajo se quedan abiertos (como en DialogoPlantillas).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      e.preventDefault()
      onCerrar()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onCerrar])

  function agregar() {
    onAgregarOtra(otra)
    setOtra('')
  }

  const extras = opciones.filter(o => !tipo.opciones.some(x => x.nombre === o))
  const destino = typeof document === 'undefined' ? null : (document.fullscreenElement ?? document.body)
  if (!destino) return null

  return createPortal(
    // z-[70]: por encima de la ficha (z-50) y de las plantillas (z-[60]).
    <div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center sm:p-4">
      <div className="velo animate-fade-in" onClick={onCerrar} aria-hidden />
      <div
        ref={cajaRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="opciones-del-tipo"
        tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-2xl animate-sheet-up flex-col overflow-hidden rounded-t-3xl bg-white shadow-panel outline-none dark:bg-slate-900 dark:ring-1 dark:ring-slate-800 sm:animate-scale-in sm:rounded-2xl"
      >
        <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div className="min-w-0 flex-1">
            <h2 id="opciones-del-tipo" className="text-lg font-bold text-slate-900 dark:text-slate-100">{tipo.nombre}</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {tipo.opciones.length > 0 ? 'Tildá todo lo que hace falta.' : 'Completá lo que haga falta.'}
            </p>
            {tipo.bajada && <p className="mt-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-100">{tipo.bajada}</p>}
          </div>
          <button type="button" onClick={onCerrar} aria-label="Cerrar" className="-mr-1.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-4">
          {(tipo.opciones.length > 0 || extras.length > 0) && (
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {tipo.opciones.map(o => {
                const si = opciones.includes(o.nombre)
                return (
                  <li key={o.nombre}>
                    <label className={`flex min-h-[48px] cursor-pointer items-start gap-2.5 rounded-xl border px-3 py-2.5 transition ${
                      si ? 'border-brand-400 bg-brand-50 dark:border-brand-500/50 dark:bg-brand-500/10' : 'border-slate-300 hover:border-slate-400 dark:border-slate-700'
                    }`}>
                      {/* El tilde real es invisible: con el teclado, el foco se
                          pinta en la casilla dibujada. */}
                      <input type="checkbox" checked={si} onChange={() => onAlternar(o.nombre)} className="peer sr-only" />
                      <span aria-hidden className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500 peer-focus-visible:ring-offset-2 dark:peer-focus-visible:ring-offset-slate-900 ${
                        si ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-500 dark:border-slate-500'
                      }`}>{si && <Check className="h-3.5 w-3.5" strokeWidth={3} />}</span>
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold text-slate-900 dark:text-slate-100">{o.nombre}</span>
                        {o.medida && <span className="block text-xs text-slate-600 dark:text-slate-400">{o.medida}</span>}
                      </span>
                    </label>
                  </li>
                )
              })}
              {extras.map(o => (
                <li key={o}>
                  <span className="flex min-h-[48px] items-center gap-2 rounded-xl border border-brand-400 bg-brand-50 px-3 text-sm font-semibold text-slate-900 dark:border-brand-500/50 dark:bg-brand-500/10 dark:text-slate-100">
                    <span className="min-w-0 flex-1 truncate">{o}</span>
                    <button type="button" onClick={() => onAlternar(o)} aria-label={`Sacar ${o}`} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-white dark:text-slate-400 dark:hover:bg-slate-800">
                      <X className="h-4 w-4" />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          {tipo.otras && (
            <div className="flex gap-2">
              <input value={otra} onChange={e => setOtra(e.target.value)} maxLength={80}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); agregar() } }}
                placeholder="Otra (escribila)" aria-label={`Otra opción de ${tipo.nombre}`} className="campo flex-1" />
              <button type="button" onClick={agregar} disabled={!otra.trim()}
                className="flex min-h-[44px] items-center gap-1 rounded-xl border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-700 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 sm:min-h-[40px]">
                <Plus className="h-4 w-4" /> Agregar
              </button>
            </div>
          )}

          {camposVisibles(tipo, opciones).map(c => (
            <label key={c.clave} className="block">
              <span className="etiqueta-campo">{c.nombre} (opcional)</span>
              {c.opciones ? (
                <select value={detalles[c.clave] ?? ''} onChange={e => onDetalle(c.clave, e.target.value)} className="campo">
                  <option value="">—</option>
                  {c.opciones.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input type="number" inputMode="numeric" min={c.minimo} max={c.maximo} value={detalles[c.clave] ?? ''}
                  onChange={e => onDetalle(c.clave, e.target.value)} className="campo !w-32" />
              )}
            </label>
          ))}
        </div>

        <div className="flex items-center gap-3 border-t border-slate-200 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-800">
          <p className="mr-auto text-sm text-slate-600 dark:text-slate-400">
            {opciones.length === 0 ? 'Nada elegido todavía' : opciones.length === 1 ? '1 elegida' : `${opciones.length} elegidas`}
          </p>
          <button
            type="button"
            onClick={onCerrar}
            className="min-h-[44px] rounded-xl bg-brand-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98]"
          >
            Listo
          </button>
        </div>
      </div>
    </div>,
    destino,
  )
}

'use client'

import { useState } from 'react'
import { ArrowDown, ArrowUp, Mic, Plus, X } from 'lucide-react'
import { DictarBrief } from '@/components/ia/DictarBrief'
import {
  TIPOS_DE_PIEZA, camposDe, tipoDePieza, type CampoBrief, type TipoPieza,
} from '@/lib/calendario/entregas'
import { TIPO_PARA_DICTADO, briefDesdeDictado } from '@/lib/calendario/entregas-dictado'
import type { DatosEntregas } from '@/lib/calendario/store'
import type { Persona } from '@/lib/calendario/tipos'

/**
 * Lo que se carga cuando una tarea lleva entregas: el tipo de pieza, el
 * pedido a la agencia según ese tipo (el brief), las fases y quiénes
 * aprueban, en orden.
 *
 * Se usa al crear la tarea (BloqueTareas) y para cambiarlo después (la vista
 * de entregas). Las fases que ya tienen versiones no se pueden sacar ni
 * mover: el servidor tampoco lo deja (ver plan_de_fases).
 */

export type ConfigEntregas = {
  tipoPieza: TipoPieza
  /** Todo como texto: es lo que hay en los campos. Se convierte al mandar. */
  brief: Record<string, string>
  fases: { id?: string | null; nombre: string; bloqueada?: boolean }[]
  aprobadores: number[]
}

export function configInicial(tipo: TipoPieza = 'cenefa'): ConfigEntregas {
  return { tipoPieza: tipo, brief: {}, fases: tipoDePieza(tipo).fases.map(nombre => ({ nombre })), aprobadores: [] }
}

/** Lo que falta para poder guardar, dicho para la persona; null si está todo. */
export function faltaEnConfig(c: ConfigEntregas, responsableId: number | null): string | null {
  if (c.fases.length === 0) return 'Agregá al menos una fase.'
  if (c.fases.some(f => !f.nombre.trim())) return 'Cada fase necesita un nombre.'
  if (c.aprobadores.length === 0) return 'Elegí al menos una persona que apruebe.'
  if (responsableId != null && c.aprobadores.includes(responsableId)) return 'Quien entrega no puede aprobar su propia pieza.'
  const desde = c.brief.vigenciaDesde || c.brief.desde
  const hasta = c.brief.vigenciaHasta || c.brief.hasta
  if (desde && hasta && hasta < desde) return 'La fecha de fin del pedido es anterior a la de inicio.'
  const link = c.brief.link?.trim()
  if (link && !/^https?:\/\//i.test(link)) return 'El link de destino tiene que empezar con http:// o https://'
  return null
}

/** Lo que viaja al servidor: solo los campos del tipo elegido, sin los vacíos. */
export function configParaEnviar(c: ConfigEntregas): DatosEntregas {
  const brief: Record<string, string | number> = {}
  for (const campo of camposDe(c.tipoPieza)) {
    const v = (c.brief[campo.clave] ?? '').trim()
    if (!v) continue
    brief[campo.clave] = campo.tipo === 'numero' && /^\d+$/.test(v) ? Number(v) : v
  }
  return {
    tipoPieza: c.tipoPieza,
    brief,
    aprobadores: c.aprobadores,
    fases: c.fases.map(f => ({ id: f.id ?? null, nombre: f.nombre.trim() })),
  }
}

function mover<T>(lista: T[], i: number, paso: number): T[] {
  const j = i + paso
  if (j < 0 || j >= lista.length) return lista
  const copia = [...lista]
  ;[copia[i], copia[j]] = [copia[j], copia[i]]
  return copia
}

const BOTON_CHICO =
  'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 active:scale-95 disabled:pointer-events-none disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'

export function FormularioEntregas({ valor, onCambiar, personas, responsableId, usuarioId }: {
  valor: ConfigEntregas
  onCambiar: (c: ConfigEntregas) => void
  personas: Persona[]
  responsableId: number | null
  usuarioId: number | null
}) {
  const set = (cambios: Partial<ConfigEntregas>) => onCambiar({ ...valor, ...cambios })
  // Dictar el pedido desde el celular: la IA lo ordena y lo que encaja cae en
  // los campos de abajo; lo demás, en el detalle (lib/calendario/entregas-dictado).
  const [dictando, setDictando] = useState(false)
  const nombreDe = (id: number) => personas.find(p => p.id === id)?.nombre ?? 'Alguien que ya no ve este calendario'
  const disponibles = personas.filter(p => !valor.aprobadores.includes(p.id) && p.id !== responsableId)
  const hayBloqueadas = valor.fases.some(f => f.bloqueada)

  function elegirTipo(tipo: TipoPieza) {
    if (tipo === valor.tipoPieza) return
    // Si las fases son las de siempre del tipo anterior (nadie las tocó), se
    // cambian por las del tipo nuevo; si alguien las armó a mano, quedan.
    const deAntes = tipoDePieza(valor.tipoPieza).fases.join('|')
    const sinTocar = !hayBloqueadas && valor.fases.map(f => f.nombre).join('|') === deAntes
    set({ tipoPieza: tipo, ...(sinTocar ? { fases: tipoDePieza(tipo).fases.map(nombre => ({ nombre })) } : {}) })
  }

  return (
    <div className="space-y-5">
      <fieldset>
        <legend className="etiqueta-campo">Tipo de pieza</legend>
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Tipo de pieza">
          {TIPOS_DE_PIEZA.map(t => {
            const activo = valor.tipoPieza === t.tipo
            return (
              <button
                key={t.tipo}
                type="button"
                role="radio"
                aria-checked={activo}
                onClick={() => elegirTipo(t.tipo)}
                className={`min-h-[40px] rounded-xl border px-3.5 text-sm font-semibold transition active:scale-95 ${
                  activo
                    ? 'border-brand-600 bg-brand-600 text-white shadow-sm'
                    : 'border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:text-brand-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-brand-500/60 dark:hover:text-brand-200'
                }`}
              >
                {t.nombre}
              </button>
            )
          })}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">El pedido a la agencia</legend>
        {dictando ? (
          <div className="mb-3">
            <DictarBrief
              key={valor.tipoPieza}
              tipoInicial={TIPO_PARA_DICTADO[valor.tipoPieza]}
              tipos={[TIPO_PARA_DICTADO[valor.tipoPieza]]}
              etiquetaUsar="Usar en el pedido"
              onListo={b => { set({ brief: briefDesdeDictado(valor.tipoPieza, valor.brief, b) }); setDictando(false) }}
              onCancelar={() => setDictando(false)}
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setDictando(true)}
            className="mb-3 flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-3 text-sm font-semibold text-brand-700 transition hover:border-brand-300 hover:bg-brand-100 active:scale-[.99] dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-200 sm:min-h-[40px] sm:w-auto"
          >
            <Mic className="h-4 w-4" /> Dictar el pedido
          </button>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          {camposDe(valor.tipoPieza).map(campo => (
            <CampoDelBrief
              key={`${valor.tipoPieza}-${campo.clave}`}
              campo={campo}
              valor={valor.brief[campo.clave] ?? ''}
              onCambiar={v => set({ brief: { ...valor.brief, [campo.clave]: v } })}
            />
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-1 text-sm font-bold text-slate-900 dark:text-slate-100">Fases</legend>
        <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
          Se trabajan en orden: la siguiente arranca cuando se aprueba la anterior.
        </p>
        <ol className="space-y-1.5">
          {valor.fases.map((f, i) => (
            <li key={f.id ?? `nueva-${i}`} className="flex items-center gap-1.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{i + 1}</span>
              <input
                value={f.nombre}
                onChange={e => set({ fases: valor.fases.map((x, j) => (j === i ? { ...x, nombre: e.target.value } : x)) })}
                aria-label={`Nombre de la fase ${i + 1}`}
                maxLength={80}
                className="campo min-w-0 flex-1"
              />
              <button type="button" className={BOTON_CHICO} aria-label={`Subir la fase ${i + 1}`} title="Subir"
                disabled={i === 0 || f.bloqueada || valor.fases[i - 1]?.bloqueada}
                onClick={() => set({ fases: mover(valor.fases, i, -1) })}>
                <ArrowUp className="h-4 w-4" />
              </button>
              <button type="button" className={BOTON_CHICO} aria-label={`Bajar la fase ${i + 1}`} title="Bajar"
                disabled={i === valor.fases.length - 1 || f.bloqueada}
                onClick={() => set({ fases: mover(valor.fases, i, 1) })}>
                <ArrowDown className="h-4 w-4" />
              </button>
              <button type="button" className={`${BOTON_CHICO} hover:!bg-rose-50 hover:!text-rose-600 dark:hover:!bg-rose-500/10`}
                aria-label={`Sacar la fase ${f.nombre || i + 1}`}
                title={f.bloqueada ? 'Ya tiene versiones entregadas: no se puede sacar' : 'Sacar la fase'}
                disabled={f.bloqueada || valor.fases.length === 1}
                onClick={() => set({ fases: valor.fases.filter((_, j) => j !== i) })}>
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ol>
        {valor.fases.length < 8 && (
          <button
            type="button"
            onClick={() => set({ fases: [...valor.fases, { nombre: '' }] })}
            className="mt-2 flex min-h-[40px] items-center gap-1.5 rounded-xl px-2 text-sm font-semibold text-brand-700 transition hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10"
          >
            <Plus className="h-4 w-4" /> Agregar fase
          </button>
        )}
      </fieldset>

      <fieldset>
        <legend className="mb-1 text-sm font-bold text-slate-900 dark:text-slate-100">Quiénes aprueban, en orden</legend>
        <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
          Cada versión la revisa primero el 1, después el 2… Si cualquiera pide cambios, vuelve a quien entrega.
        </p>
        {valor.aprobadores.length > 0 && (
          <ol className="mb-2 space-y-1.5">
            {valor.aprobadores.map((id, i) => (
              <li key={id} className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white py-1 pl-2.5 pr-1 dark:border-slate-700 dark:bg-slate-900">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700 dark:bg-brand-500/20 dark:text-brand-200">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
                  {nombreDe(id)}{id === usuarioId ? ' (vos)' : ''}
                </span>
                <button type="button" className={BOTON_CHICO} aria-label={`Subir a ${nombreDe(id)}`} title="Antes"
                  disabled={i === 0} onClick={() => set({ aprobadores: mover(valor.aprobadores, i, -1) })}>
                  <ArrowUp className="h-4 w-4" />
                </button>
                <button type="button" className={BOTON_CHICO} aria-label={`Bajar a ${nombreDe(id)}`} title="Después"
                  disabled={i === valor.aprobadores.length - 1} onClick={() => set({ aprobadores: mover(valor.aprobadores, i, 1) })}>
                  <ArrowDown className="h-4 w-4" />
                </button>
                <button type="button" className={`${BOTON_CHICO} hover:!bg-rose-50 hover:!text-rose-600 dark:hover:!bg-rose-500/10`}
                  aria-label={`Sacar a ${nombreDe(id)} de la cadena`} title="Sacar"
                  onClick={() => set({ aprobadores: valor.aprobadores.filter(x => x !== id) })}>
                  <X className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ol>
        )}
        {valor.aprobadores.length < 6 && (
          <select
            value=""
            onChange={e => { if (e.target.value) set({ aprobadores: [...valor.aprobadores, Number(e.target.value)] }) }}
            aria-label="Agregar a alguien que aprueba"
            className="campo"
          >
            <option value="">{valor.aprobadores.length === 0 ? 'Elegí quién aprueba primero…' : 'Agregar a alguien más…'}</option>
            {disponibles.map(p => <option key={p.id} value={p.id}>{p.nombre}{p.id === usuarioId ? ' (vos)' : ''}</option>)}
          </select>
        )}
      </fieldset>
    </div>
  )
}

function CampoDelBrief({ campo, valor, onCambiar }: { campo: CampoBrief; valor: string; onCambiar: (v: string) => void }) {
  const id = `brief-${campo.clave}`
  const comun = { id, value: valor, placeholder: campo.placeholder }
  return (
    <label htmlFor={id} className={`block ${campo.entero ? 'sm:col-span-2' : ''}`}>
      <span className="etiqueta-campo">{campo.etiqueta}</span>
      {campo.tipo === 'largo' ? (
        <textarea
          {...comun}
          // El texto libre lo va a poder llenar el dictado por voz: lo
          // encuentra por este nombre.
          name={id}
          data-dictado={campo.clave === 'detalle' ? 'brief' : undefined}
          rows={campo.clave === 'detalle' ? 4 : 2}
          maxLength={5000}
          onChange={e => onCambiar(e.target.value)}
          className="campo !h-auto min-h-[4.5rem] py-2"
        />
      ) : campo.tipo === 'opciones' ? (
        <select {...comun} name={id} onChange={e => onCambiar(e.target.value)} className="campo">
          <option value="">Elegí…</option>
          {campo.opciones?.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input
          {...comun}
          name={id}
          type={campo.tipo === 'fecha' ? 'date' : campo.tipo === 'numero' ? 'number' : campo.tipo === 'url' ? 'url' : 'text'}
          inputMode={campo.tipo === 'numero' ? 'numeric' : undefined}
          min={campo.tipo === 'fecha' ? '2000-01-01' : campo.tipo === 'numero' ? 0 : undefined}
          max={campo.tipo === 'fecha' ? '2100-12-31' : undefined}
          maxLength={campo.tipo === 'url' ? 1000 : campo.tipo === 'texto' ? 300 : undefined}
          onChange={e => onCambiar(e.target.value)}
          className="campo"
        />
      )}
    </label>
  )
}

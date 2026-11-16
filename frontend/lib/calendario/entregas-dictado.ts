/**
 * El brief dictado (components/ia/DictarBrief) dentro del formulario de las
 * entregas por fases.
 *
 * Los dos los armaron por separado y no piden lo mismo: el dictado devuelve
 * texto libre por campo ("vigencia: del 28/11 al 3/12") y el formulario de
 * entregas tiene sus propios campos, algunos con tipo (fechas, número, link,
 * opciones). Acá se pasa lo que encaja sin adivinar (medidas, cantidad,
 * asunto…) y TODO lo demás va al "detalle", para que no se pierda nada de lo
 * que se dijo. Lo que la persona ya había escrito no se pisa.
 */
import { camposDe, type CampoBrief, type TipoPieza } from './entregas'

/** Los tipos del dictado (lib/api.ts, TipoPiezaBrief). Copiados acá para que
 *  este archivo se pueda probar sin la app entera (npm run test:calendario). */
type TipoPiezaBrief = 'cenefa' | 'mailing' | 'banner_web' | 'redes' | 'otro'

/** El tipo del dictado para cada tipo de las entregas (en el dictado el banner se llama distinto). */
export const TIPO_PARA_DICTADO: Record<TipoPieza, TipoPiezaBrief> = {
  cenefa: 'cenefa', mailing: 'mailing', banner: 'banner_web', redes: 'redes', otro: 'otro',
}

/** Campo del dictado → campo del formulario de entregas, solo donde significan lo mismo. */
const EQUIVALENTES: Record<TipoPieza, Record<string, string>> = {
  cenefa: { medidas: 'medidas', cantidad: 'cantidad', precio_mecanica: 'precio', legales: 'legales' },
  mailing: { asunto: 'asunto', segmento: 'segmento', llamado_accion: 'llamado' },
  banner: { medidas: 'medidas', link: 'link' },
  redes: { formato: 'formato', copy: 'copy' },
  otro: {},
}

export type CampoDictado = { clave: string; etiqueta: string; valor: string | null }

function comoQuedaEn(campo: CampoBrief, valor: string): string | null {
  const v = valor.trim()
  switch (campo.tipo) {
    case 'numero': return /^\d+$/.test(v) ? v : null
    case 'url': return /^https?:\/\/\S+$/i.test(v) ? v : null
    case 'fecha': return null // "del 28/11 al 3/12" no es una fecha: va al detalle
    case 'opciones': return campo.opciones?.find(o => o.toLowerCase() === v.toLowerCase()) ?? null
    default: return v
  }
}

export function briefDesdeDictado(
  tipo: TipoPieza,
  actual: Record<string, string>,
  dictado: { campos: CampoDictado[]; notas: string | null },
): Record<string, string> {
  const campos = camposDe(tipo)
  const nuevo = { ...actual }
  const alDetalle: string[] = []
  for (const c of dictado.campos) {
    const valor = c.valor?.trim()
    if (!valor) continue
    const destino = campos.find(x => x.clave === EQUIVALENTES[tipo][c.clave])
    const encaja = destino ? comoQuedaEn(destino, valor) : null
    if (destino && encaja !== null && !nuevo[destino.clave]?.trim()) {
      nuevo[destino.clave] = encaja
    } else if (!(destino && nuevo[destino.clave]?.trim() === valor)) {
      alDetalle.push(`${c.etiqueta}: ${valor}`)
    }
  }
  if (dictado.notas?.trim()) alDetalle.push(dictado.notas.trim())
  if (alDetalle.length) {
    nuevo.detalle = [actual.detalle?.trim(), ...alDetalle].filter(Boolean).join('\n')
  }
  return nuevo
}

"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { toast } from "sonner";
import {
  Camera, CheckCircle2, Clock, ImagePlus, MessageSquareText, RefreshCw, Store, Trash2, TriangleAlert, X,
} from "lucide-react";
import { colocacionApi, type FotoColocacion, type MiPedidoColocacion } from "@/lib/api";
import { extractErrorDetail } from "@/lib/errors";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import { hoyIso, rangoLargo } from "@/lib/calendario/fechas";
import { ETIQUETA_LOCAL, TONO, cuandoVence, pendientesDelLocal } from "@/lib/colocacion/estados";
import { prepararFoto } from "@/lib/colocacion/imagen";
import { usePendientesDeFotos } from "@/lib/colocacion/store";
import { FotoProtegida } from "@/components/colocacion/FotoProtegida";
import { useDialogo } from "@/components/calendario/useDialogo";

/**
 * "Fotos para subir": la pantalla del local.
 *
 * Marketing le pide al local una foto de cómo quedó la cartelería de una
 * acción; acá el local ve qué le pidieron (la acción, las fechas, qué
 * fotografiar y hasta cuándo), saca la foto con el teléfono y la sube. Si se
 * la devuelven, ve por qué y sube otra.
 *
 * Pensada para el teléfono de un local: letra grande, un botón grande para la
 * cámara y nada más que lo suyo (el local no ve el calendario ni lo de otros
 * locales; eso lo cuida el servidor). La foto se achica en el teléfono antes
 * de subir (lib/colocacion/imagen.ts): con la señal de un local, una foto de
 * 5 MB no sube nunca.
 */
export default function FotosParaSubirPage() {
  const { user, loading } = useCurrentUser();
  const [datos, setDatos] = useState<{ locales: string[]; pedidos: MiPedidoColocacion[] } | null>(null);
  const [fallo, setFallo] = useState(false);
  const [vuelta, setVuelta] = useState(0);
  const esLocal = (user?.assigned_locales?.length ?? 0) > 0;

  useEffect(() => {
    if (!esLocal) return;
    let vivo = true;
    const traer = () => colocacionApi.misFotos()
      .then(({ data }) => {
        if (!vivo) return;
        setDatos(data);
        setFallo(false);
        usePendientesDeFotos.getState().poner(pendientesDelLocal(data.pedidos));
      })
      .catch(() => { if (vivo) setFallo(true); });
    void traer();
    // Al volver a la pantalla (después de sacar la foto con otra app, o al
    // día siguiente) se trae lo último: pudo llegar un pedido nuevo.
    const alVolver = () => { if (document.visibilityState === "visible") void traer(); };
    document.addEventListener("visibilitychange", alVolver);
    return () => { vivo = false; document.removeEventListener("visibilitychange", alVolver); };
  }, [esLocal, vuelta]);

  function actualizar(nuevo: MiPedidoColocacion) {
    setDatos((d) => {
      if (!d) return d;
      const pedidos = d.pedidos.map((p) => (p.id === nuevo.id ? nuevo : p));
      usePendientesDeFotos.getState().poner(pendientesDelLocal(pedidos));
      return { ...d, pedidos };
    });
  }

  if (loading) return null;

  if (!esLocal) {
    return (
      <div className="mx-auto max-w-xl animate-fade-in space-y-4">
        <Encabezado />
        <div className="card flex flex-col items-center gap-3 p-8 text-center">
          <Store className="h-8 w-8 text-slate-300 dark:text-slate-600" />
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Esta pantalla es la de los locales: acá suben la foto de cómo quedó la cartelería.
          </p>
          {hasPermission(user, "calendario.edit") && (
            <Link href="/colocacion" className="btn-secondary">Ver las fotos que mandaron los locales</Link>
          )}
        </div>
      </div>
    );
  }

  const paraHacer = datos?.pedidos.filter((p) => p.visible === "pendiente" || p.visible === "devuelta" || p.visible === "atrasada") ?? [];
  const hechas = datos?.pedidos.filter((p) => p.visible === "enviada" || p.visible === "aprobada") ?? [];
  const variosLocales = (datos?.locales.length ?? 0) > 1;

  return (
    <div className="mx-auto max-w-xl animate-fade-in space-y-5">
      <Encabezado locales={datos?.locales ?? user?.assigned_locales ?? []} />

      {fallo && !datos && (
        <div className="card flex flex-col items-center gap-3 p-6 text-center">
          <TriangleAlert className="h-7 w-7 text-amber-500" />
          <p className="text-base text-slate-700 dark:text-slate-200">No pudimos traer tus fotos. Revisá la señal.</p>
          <button type="button" onClick={() => setVuelta((v) => v + 1)} className="btn-primary min-h-[48px] px-6 text-base">
            <RefreshCw className="h-5 w-5" /> Probar de nuevo
          </button>
        </div>
      )}

      {!datos && !fallo && (
        <div className="space-y-3" aria-label="Cargando…">
          {[0, 1].map((i) => <div key={i} className="skeleton h-64 rounded-2xl" />)}
        </div>
      )}

      {datos && datos.pedidos.length === 0 && (
        <div className="card flex flex-col items-center gap-3 px-6 py-10 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300">
            <CheckCircle2 className="h-7 w-7" />
          </span>
          <p className="text-lg font-bold text-slate-900 dark:text-white">No tenés fotos para subir</p>
          <p className="text-base text-slate-600 dark:text-slate-300">
            Cuando marketing te pida una, te llega un aviso a la campanita y aparece acá.
          </p>
        </div>
      )}

      {paraHacer.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Para subir · {paraHacer.length}
          </h2>
          {paraHacer.map((p) => <TarjetaPedido key={p.id} pedido={p} conLocal={variosLocales} onCambio={actualizar} />)}
        </section>
      )}

      {hechas.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Ya enviadas</h2>
          {hechas.map((p) => <TarjetaPedido key={p.id} pedido={p} conLocal={variosLocales} onCambio={actualizar} />)}
        </section>
      )}
    </div>
  );
}

function Encabezado({ locales = [] }: { locales?: string[] }) {
  return (
    <div>
      <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 dark:text-slate-100">
        <Camera className="h-6 w-6 text-brand-600 dark:text-brand-300" /> Fotos para subir
      </h1>
      <p className="mt-1 text-base text-slate-600 dark:text-slate-300">
        Sacale una foto a cómo quedó la cartelería en el local y subila acá. Marketing la revisa.
      </p>
      {locales.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {locales.map((l) => (
            <span key={l} className="flex items-center gap-1.5 rounded-lg bg-brand-50 px-2.5 py-1 text-sm font-semibold text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
              <Store className="h-4 w-4" /> {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

type Subida = { fase: "achicando" } | { fase: "subiendo"; progreso: number };

function TarjetaPedido({
  pedido, conLocal, onCambio,
}: {
  pedido: MiPedidoColocacion;
  conLocal: boolean;
  onCambio: (p: MiPedidoColocacion) => void;
}) {
  const camara = useRef<HTMLInputElement>(null);
  const galeria = useRef<HTMLInputElement>(null);
  const [subida, setSubida] = useState<Subida | null>(null);
  const [sacando, setSacando] = useState<number | null>(null);
  const [viendo, setViendo] = useState<FotoColocacion | null>(null);
  const vence = cuandoVence(pedido.limite, hoyIso());
  const activas = pedido.fotos.filter((f) => !f.devuelta);
  const puedeSacar = pedido.estado !== "aprobada";

  async function alElegir(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    // Se vacía para que elegir la misma foto otra vez vuelva a avisar.
    e.target.value = "";
    if (!archivo) return;
    setSubida({ fase: "achicando" });
    try {
      const lista = await prepararFoto(archivo);
      setSubida({ fase: "subiendo", progreso: 0 });
      const { data } = await colocacionApi.subir(pedido.id, lista.foto, lista.miniatura, (f) => setSubida({ fase: "subiendo", progreso: f }));
      onCambio(data);
      toast.success("¡Listo! Tu foto se envió a marketing.");
    } catch (err) {
      const deLaRed = (err as { isAxiosError?: boolean })?.isAxiosError;
      toast.error(deLaRed
        ? extractErrorDetail(err, "No se pudo subir la foto. Revisá la señal y probá de nuevo.")
        : (err as Error)?.message || "No se pudo preparar la foto.");
    } finally {
      setSubida(null);
    }
  }

  async function sacar(id: number) {
    try {
      const { data } = await colocacionApi.sacarFoto(id);
      onCambio(data);
      toast.success("Se sacó la foto.");
    } catch (err) {
      toast.error(extractErrorDetail(err, "No se pudo sacar la foto. Probá de nuevo."));
    } finally {
      setSacando(null);
    }
  }

  return (
    <article className="card overflow-hidden">
      <div className="space-y-3 p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-3 py-1 text-sm font-bold ${TONO[pedido.visible]}`}>{ETIQUETA_LOCAL[pedido.visible]}</span>
          {conLocal && (
            <span className="flex items-center gap-1 text-sm font-medium text-slate-500 dark:text-slate-400">
              <Store className="h-4 w-4" /> {pedido.local}
            </span>
          )}
        </div>

        <div>
          <h3 className="text-xl font-bold leading-tight text-slate-900 dark:text-white">{pedido.accion.nombre}</h3>
          <p className="mt-0.5 text-base text-slate-600 dark:text-slate-300">
            Va {rangoLargo(pedido.accion.desde, pedido.accion.hasta)}
          </p>
        </div>

        {pedido.estado !== "aprobada" && (
          <p className={`flex items-center gap-2 rounded-xl px-3 py-2.5 text-base ${
            vence.vencida && pedido.estado !== "enviada"
              ? "bg-rose-50 text-rose-800 dark:bg-rose-500/10 dark:text-rose-200"
              : vence.urgente ? "bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-100"
                : "bg-slate-50 text-slate-700 dark:bg-slate-800/60 dark:text-slate-200"
          }`}>
            <Clock className="h-5 w-5 shrink-0" />
            <span>{vence.vencida ? "La fecha límite " : "Fecha límite: "}<strong>{vence.texto}</strong></span>
          </p>
        )}

        {pedido.indicacion && (
          <div className="rounded-xl border-l-4 border-brand-500 bg-brand-50 px-3.5 py-2.5 dark:bg-brand-500/10">
            <p className="text-xs font-bold uppercase tracking-wide text-brand-700 dark:text-brand-300">Qué fotografiar</p>
            <p className="mt-0.5 text-base font-medium text-slate-900 dark:text-white">{pedido.indicacion}</p>
          </div>
        )}

        {pedido.comentario && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 px-3.5 py-3 dark:border-amber-500/40 dark:bg-amber-500/10">
            <p className="flex items-center gap-1.5 text-sm font-bold text-amber-900 dark:text-amber-200">
              <MessageSquareText className="h-4 w-4" /> Marketing te la devolvió:
            </p>
            <p className="mt-1 text-base text-amber-950 dark:text-amber-50">«{pedido.comentario}»</p>
            <p className="mt-1 text-sm text-amber-800 dark:text-amber-200">Sacá una foto nueva y subila.</p>
          </div>
        )}

        {pedido.fotos.length > 0 && (
          <ul className="grid grid-cols-3 gap-2">
            {pedido.fotos.map((f) => (
              <li key={f.id} className="relative">
                <button type="button" onClick={() => setViendo(f)} className="block w-full overflow-hidden rounded-xl" aria-label="Ver la foto grande">
                  <FotoProtegida id={f.id} tamano="mini" alt="Tu foto" className={`aspect-square w-full ${f.devuelta ? "opacity-60" : ""}`} />
                </button>
                {f.devuelta && (
                  <span className="pointer-events-none absolute bottom-1.5 left-1.5 rounded-full bg-amber-400 px-2 py-0.5 text-[11px] font-bold text-amber-950">Devuelta</span>
                )}
                {puedeSacar && (
                  <button
                    type="button"
                    onClick={() => setSacando(f.id)}
                    aria-label="Sacar esta foto"
                    className="absolute right-1 top-1 flex h-9 w-9 items-center justify-center rounded-full bg-black/60 text-white transition hover:bg-black/80 active:scale-95"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {sacando !== null && (
          <div role="alertdialog" aria-labelledby={`sacar-${pedido.id}`} className="space-y-3 rounded-xl border border-rose-200 bg-rose-50 p-3.5 dark:border-rose-500/30 dark:bg-rose-500/10">
            <p id={`sacar-${pedido.id}`} className="text-base text-rose-900 dark:text-rose-100">¿Sacar esta foto? Marketing deja de verla.</p>
            <div className="grid grid-cols-2 gap-2">
              <button type="button" autoFocus onClick={() => setSacando(null)} className="min-h-[48px] rounded-xl bg-white text-base font-semibold text-slate-700 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700">
                No
              </button>
              <button type="button" onClick={() => sacar(sacando)} className="flex min-h-[48px] items-center justify-center gap-1.5 rounded-xl bg-rose-600 text-base font-semibold text-white">
                <Trash2 className="h-5 w-5" /> Sí, sacarla
              </button>
            </div>
          </div>
        )}

        {subida && (
          <div className="space-y-2 rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/60" role="status" aria-live="polite">
            <p className="flex items-center gap-2 text-base font-semibold text-slate-800 dark:text-slate-100">
              <RefreshCw className="h-5 w-5 animate-spin text-brand-600" />
              {subida.fase === "achicando" ? "Preparando la foto…" : `Subiendo… ${Math.round(subida.progreso * 100)}%`}
            </p>
            <div className="h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
              <div
                className="h-full rounded-full bg-brand-600 transition-[width] duration-300"
                style={{ width: subida.fase === "achicando" ? "8%" : `${Math.max(8, Math.round(subida.progreso * 100))}%` }}
              />
            </div>
          </div>
        )}

        {pedido.puedeSubir && !subida && (
          <div className="space-y-2 pt-1">
            <button
              type="button"
              onClick={() => camara.current?.click()}
              className="flex min-h-[56px] w-full items-center justify-center gap-2.5 rounded-2xl bg-brand-600 px-4 text-lg font-bold text-white shadow-md shadow-brand-600/25 transition hover:bg-brand-700 active:scale-[.98]"
            >
              <Camera className="h-6 w-6" /> {activas.length > 0 ? "Sacar otra foto" : "Sacar foto"}
            </button>
            <button
              type="button"
              onClick={() => galeria.current?.click()}
              className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-white px-4 text-base font-semibold text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-50 active:scale-[.98] dark:bg-slate-800 dark:text-slate-100 dark:ring-slate-600 dark:hover:bg-slate-700"
            >
              <ImagePlus className="h-5 w-5" /> Elegir de la galería
            </button>
            <p className="text-center text-sm text-slate-500 dark:text-slate-400">
              Podés subir hasta 3 fotos. {pedido.quedan === 1 ? "Te queda 1." : `Te quedan ${pedido.quedan}.`}
            </p>
            {/* La cámara de atrás, directo; y la galería, por si la sacaron antes. */}
            <input ref={camara} type="file" accept="image/*" capture="environment" onChange={alElegir} className="hidden" />
            <input ref={galeria} type="file" accept="image/*" onChange={alElegir} className="hidden" />
          </div>
        )}

        {pedido.estado === "enviada" && !pedido.puedeSubir && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Ya subiste las 3 fotos. Si querés cambiar una, sacala con la cruz.</p>
        )}
        {pedido.estado === "enviada" && (
          <p className="flex items-start gap-2 text-base text-sky-800 dark:text-sky-200">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" /> Ya la mandaste. Si marketing te la devuelve, te llega un aviso.
          </p>
        )}
        {pedido.estado === "aprobada" && (
          <p className="flex items-start gap-2 text-base font-semibold text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" /> Aprobada. ¡Gracias!
          </p>
        )}
      </div>

      {viendo && <VerFoto foto={viendo} onCerrar={() => setViendo(null)} />}
    </article>
  );
}

function VerFoto({ foto, onCerrar }: { foto: FotoColocacion; onCerrar: () => void }) {
  const caja = useRef<HTMLDivElement>(null);
  const cerrarRef = useRef<HTMLButtonElement>(null);
  useDialogo(true, caja, cerrarRef);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCerrar(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCerrar]);
  // En el <body>: un "fixed" adentro de algo con transform queda atrapado en su caja.
  return createPortal(
    <div ref={caja} role="dialog" aria-modal="true" aria-label="Tu foto" className="fixed inset-0 z-[70] flex animate-fade-in items-center justify-center bg-black/90 p-3">
      <button
        ref={cerrarRef}
        type="button"
        onClick={onCerrar}
        aria-label="Cerrar"
        className="absolute right-3 top-3 z-10 flex h-12 w-12 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
      >
        <X className="h-6 w-6" />
      </button>
      <FotoProtegida id={foto.id} tamano="grande" alt="Tu foto" ajuste="contain" className="h-[85dvh] w-full !bg-transparent" />
    </div>,
    document.body,
  );
}

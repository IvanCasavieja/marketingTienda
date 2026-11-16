"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Archive, BarChart3, ChevronDown, Layers, Loader2, RotateCcw, Search, ShieldAlert, X } from "lucide-react";
import { toast } from "sonner";
import { entregasApi } from "@/lib/api";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import { numero, proximoPaso, type Columna, type Metricas, type Tarjeta } from "@/lib/calendario/entregas";
import {
  COLUMNAS_DEL_TABLERO, MS_PARA_ARRASTRAR_CON_EL_DEDO, PX_PARA_ARRASTRAR, defColumna, deQuien, opcionesDeQuien,
  ordenar, queHaceMover, sePuedeSoltar,
} from "@/lib/calendario/tablero";
import { hoyIso } from "@/lib/calendario/fechas";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";
import { SEGUNDOS_ENTRE_REVISIONES } from "@/lib/calendario/store";
import { mundoEfectivo, useMundoElegido } from "@/lib/mundos";
import { esExterno } from "@/lib/externos";
import { useVistaEntregas } from "@/store/entregas";
import { TarjetaEntrega } from "@/components/calendario/entregas/TarjetaEntrega";

/**
 * El tablero de tarjetas, estilo Trello (16/11/2026). Pedido de Ivan: "La
 * agencia tiene que tener otro tipo de entrada… lo único que le interesa es
 * tener las tareas de cada promoción para irlas completando y mandando. Una
 * vista estilo Trello: Ingresado, En proceso, Esperando feedback,
 * Finalizado, Archivado. Podemos ir arrastrando las tarjetas".
 *
 * Es uno solo para la agencia y para el equipo: cada uno ve lo suyo (eso lo
 * recorta el servidor) y puede mover lo que le toca (también lo decide el
 * servidor: cada tarjeta trae a qué columnas la puede llevar quien mira).
 *
 * - Arrastrar con el mouse, o en el teléfono manteniendo apretado y
 *   arrastrando. Además, cada tarjeta tiene "Mover a…".
 * - Soltar en "Esperando feedback" abre "Entregar": la tarjeta pasa recién
 *   cuando se mandan los materiales (si se cancela, queda donde estaba).
 * - Soltar de "Esperando feedback" en "En proceso" pide qué hay que cambiar.
 * - Rápido siempre: el servidor manda solo lo que se ve (Archivado, de a 20
 *   con "Ver más"; lo de hace más de 30 días, solo con el buscador), y las
 *   miniaturas se piden cuando la tarjeta aparece en pantalla.
 *
 * `/entregas?tarea=ta-xxx` abre esa tarjeta encima: es a donde lleva un aviso
 * de la campanita.
 */

type Datos = {
  mundo: string;
  hoy: string;
  tarjetas: Tarjeta[];
  archivadas: { total: number; mostradas: number };
};

type Arrastre = {
  tarjeta: Tarjeta;
  /** Dónde se agarró la tarjeta, relativo a su esquina. */
  dx: number;
  dy: number;
  ancho: number;
  conElDedo: boolean;
};

function AbrirTareaDeLaUrl() {
  const params = useSearchParams();
  const router = useRouter();
  const tarea = params.get("tarea");
  useEffect(() => {
    if (!tarea) return;
    useVistaEntregas.getState().abrir(tarea);
    router.replace("/entregas");
  }, [tarea, router]);
  return null;
}

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof d === "string" ? d : null;
}

export default function TableroPage() {
  const { allowed, checked, user } = usePermissionGuard({ permission: PERMISOS_CALENDARIO.ver });
  const elegido = useMundoElegido(s => s.elegido);
  const mundo = mundoEfectivo(user, elegido);
  const cambios = useVistaEntregas(s => s.cambios);
  const abrirDetalle = useVistaEntregas(s => s.abrir);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState(false);
  const [pestana, setPestana] = useState<Columna | null>(null);
  const [filtro, setFiltro] = useState<string | null>(null);
  const [cargandoMas, setCargandoMas] = useState(false);
  const [pidiendoCambios, setPidiendoCambios] = useState<Tarjeta | null>(null);
  const [verMetricas, setVerMetricas] = useState(false);
  const rev = useRef<number | null>(null);
  const datosRef = useRef<Datos | null>(null);
  useEffect(() => { datosRef.current = datos; }, [datos]);
  const claveMundo = mundo?.clave;
  const externo = esExterno(user);
  const yo = user?.id ?? null;

  const cargar = useCallback(async (desdeCero: boolean) => {
    if (!claveMundo) return;
    try {
      // Si cambió el día, una tarjeta pudo haber pasado sola a Archivado sin
      // que cambie nada más: se trae todo.
      const nuevoDia = datosRef.current && datosRef.current.hoy !== hoyIso();
      const { data } = await entregasApi.tablero(claveMundo, desdeCero || nuevoDia ? null : rev.current);
      if (data.sinCambios) return;
      rev.current = data.rev;
      setDatos({
        mundo: claveMundo, hoy: data.hoy ?? hoyIso(), tarjetas: data.tarjetas ?? [],
        archivadas: data.archivadas ?? { total: 0, mostradas: 0 },
      });
      setError(false);
    } catch {
      setError(true);
    }
  }, [claveMundo]);

  // Como el calendario: se pregunta cada 15 s si cambió algo (si no, la
  // respuesta es una línea) y al volver a la pestaña. Después de entregar o
  // decidir algo en el detalle, se trae todo.
  useEffect(() => {
    if (!allowed || !claveMundo) return;
    void cargar(true);
    const revisar = () => { if (document.visibilityState === "visible") void cargar(false); };
    const intervalo = window.setInterval(revisar, SEGUNDOS_ENTRE_REVISIONES * 1000);
    document.addEventListener("visibilitychange", revisar);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", revisar);
    };
  }, [allowed, claveMundo, cargar, cambios]);

  // ---------------------------------------------------------------------
  // Mover
  // ---------------------------------------------------------------------

  /** Lo que pasa al llevar una tarjeta a otra columna (arrastrando o con
   *  "Mover a…"). La regla la tiene el servidor; acá se abre lo que haga
   *  falta (entregar, decir qué cambiar) y se mueve en la pantalla al toque. */
  const moverA = useCallback(async (t: Tarjeta, a: Columna, comentario?: string) => {
    if (!sePuedeSoltar(t, a)) return;
    if (a === "esperando") {
      // A Esperando feedback se llega entregando: se abre "Entregar".
      abrirDetalle(t.tareaId, "entregar", null, true);
      return;
    }
    if (t.columna === "esperando" && a === "en-proceso" && comentario === undefined) {
      setPidiendoCambios(t);
      return;
    }
    const antes = datosRef.current;
    setDatos(d => d && { ...d, tarjetas: d.tarjetas.map(x => (x.tareaId === t.tareaId ? { ...x, columna: a, volvioConCambios: a === "en-proceso" && t.columna === "esperando" } : x)) });
    try {
      const { data } = await entregasApi.mover(t.tareaId, { desde: t.columna, a, comentario: comentario ?? null });
      if (data.columna !== a) {
        toast.success(data.columna === "esperando"
          ? "Aprobaste: ahora la revisa la siguiente persona de la cadena."
          : `Quedó en ${defColumna(data.columna).titulo}.`);
      } else if (a === "finalizado") {
        toast.success("Aprobada: quedó en Finalizado. Le avisamos a quien la hizo.");
      } else if (a === "en-proceso" && t.columna === "esperando") {
        toast.success("Volvió a En proceso con tus cambios. Le avisamos a quien la hace.");
      }
      useVistaEntregas.getState().huboCambios();
    } catch (e) {
      setDatos(antes);
      toast.error(detalleDeError(e) ?? "No se pudo mover la tarjeta. Probá de nuevo.");
      void cargar(true);
    }
  }, [abrirDetalle, cargar]);

  // ---------------------------------------------------------------------
  // Arrastrar (eventos del puntero, sin librería: mouse, lápiz y dedo)
  // ---------------------------------------------------------------------

  const [arrastre, setArrastre] = useState<Arrastre | null>(null);
  const [sobre, setSobre] = useState<Columna | null>(null);
  const fantasmaRef = useRef<HTMLDivElement>(null);
  const sobreRef = useRef<Columna | null>(null);
  const arrastreRef = useRef<Arrastre | null>(null);
  const recienArrastrada = useRef(false);

  const columnaEn = (x: number, y: number): Columna | null => {
    const el = document.elementFromPoint(x, y) as HTMLElement | null;
    return (el?.closest("[data-columna]")?.getAttribute("data-columna") as Columna | null) ?? null;
  };

  const ponerFantasma = (x: number, y: number) => {
    const a = arrastreRef.current;
    const f = fantasmaRef.current;
    if (!a || !f) return;
    // Con el dedo, la copia va más chica y arriba del dedo: si no, tapa
    // justo la columna donde se va a soltar.
    f.style.transform = a.conElDedo
      ? `translate3d(${x - a.ancho * 0.35}px, ${y - f.offsetHeight * 0.7 - 28}px, 0) scale(.7)`
      : `translate3d(${x - a.dx}px, ${y - a.dy}px, 0)`;
    const c = columnaEn(x, y);
    if (c !== sobreRef.current) {
      sobreRef.current = c;
      setSobre(c);
    }
  };

  const terminar = useCallback((soltar: boolean) => {
    const a = arrastreRef.current;
    const destino = sobreRef.current;
    arrastreRef.current = null;
    sobreRef.current = null;
    setArrastre(null);
    setSobre(null);
    document.body.classList.remove("arrastrando-tarjeta");
    if (!a) return;
    recienArrastrada.current = true;
    window.setTimeout(() => { recienArrastrada.current = false; }, 50);
    if (soltar && destino && sePuedeSoltar(a.tarjeta, destino)) void moverA(a.tarjeta, destino);
    else if (soltar && destino && destino !== a.tarjeta.columna) {
      toast.message(`No podés llevarla a ${defColumna(destino).titulo}.`, {
        description: a.tarjeta.puedo?.mover.length
          ? `Desde acá: ${a.tarjeta.puedo.mover.map(c => defColumna(c).titulo).join(", ")}.`
          : "Esta tarjeta no la movés vos.",
      });
    }
  }, [moverA]);

  const empezar = (t: Tarjeta, e: { clientX: number; clientY: number }, caja: DOMRect, conElDedo: boolean) => {
    const a: Arrastre = { tarjeta: t, dx: e.clientX - caja.left, dy: e.clientY - caja.top, ancho: caja.width, conElDedo };
    arrastreRef.current = a;
    setArrastre(a);
    document.body.classList.add("arrastrando-tarjeta");
    if (conElDedo && "vibrate" in navigator) navigator.vibrate?.(15);
    requestAnimationFrame(() => ponerFantasma(e.clientX, e.clientY));
  };

  /** Apretar una tarjeta: con el mouse, se arrastra apenas se mueve; con el
   *  dedo, después de mantenerla apretada un momento (si no, mover el dedo
   *  es hacer scroll, como siempre). */
  const alApretar = (t: Tarjeta) => (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || !(t.puedo?.mover.length)) return;
    const objetivo = e.target as HTMLElement;
    if (objetivo.closest("[role=menu]")) return;
    const tarjetaEl = e.currentTarget;
    const inicio = { x: e.clientX, y: e.clientY };
    const conElDedo = e.pointerType === "touch";
    let reloj: number | null = null;
    let ultimo = { clientX: e.clientX, clientY: e.clientY };

    const limpiar = () => {
      if (reloj) window.clearTimeout(reloj);
      window.removeEventListener("pointermove", alMover);
      window.removeEventListener("pointerup", alSoltar);
      window.removeEventListener("pointercancel", alCancelar);
      document.removeEventListener("touchmove", alMoverDedo);
      document.removeEventListener("touchend", alSoltarDedo);
      document.removeEventListener("touchcancel", alCancelarDedo);
    };
    const alMover = (ev: PointerEvent) => {
      ultimo = { clientX: ev.clientX, clientY: ev.clientY };
      if (arrastreRef.current) { ponerFantasma(ev.clientX, ev.clientY); return; }
      const movido = Math.hypot(ev.clientX - inicio.x, ev.clientY - inicio.y);
      if (conElDedo) {
        // Se movió antes de tiempo: es scroll, no arrastre.
        if (movido > 10) limpiar();
        return;
      }
      if (movido > PX_PARA_ARRASTRAR) empezar(t, ev, tarjetaEl.getBoundingClientRect(), false);
    };
    const alSoltar = () => { limpiar(); if (arrastreRef.current) terminar(true); };
    const alCancelar = () => {
      // Con el dedo, el navegador cancela el puntero cuando empieza a
      // arrastrar: desde ahí se sigue con los eventos de toque.
      if (conElDedo && arrastreRef.current) return;
      limpiar();
      if (arrastreRef.current) terminar(false);
    };
    // Con el dedo, una vez que arrancó el arrastre la página no tiene que
    // hacer scroll: el toque es de la tarjeta.
    const alMoverDedo = (ev: TouchEvent) => {
      if (!arrastreRef.current) return;
      ev.preventDefault();
      const toque = ev.touches[0];
      if (toque) { ultimo = { clientX: toque.clientX, clientY: toque.clientY }; ponerFantasma(toque.clientX, toque.clientY); }
    };
    const alSoltarDedo = () => { limpiar(); if (arrastreRef.current) terminar(true); };
    const alCancelarDedo = () => { limpiar(); if (arrastreRef.current) terminar(false); };

    window.addEventListener("pointermove", alMover);
    window.addEventListener("pointerup", alSoltar);
    window.addEventListener("pointercancel", alCancelar);
    if (conElDedo) {
      document.addEventListener("touchmove", alMoverDedo, { passive: false });
      document.addEventListener("touchend", alSoltarDedo);
      document.addEventListener("touchcancel", alCancelarDedo);
      reloj = window.setTimeout(() => {
        reloj = null;
        empezar(t, ultimo, tarjetaEl.getBoundingClientRect(), true);
      }, MS_PARA_ARRASTRAR_CON_EL_DEDO);
    }
  };

  // Escape suelta sin mover.
  useEffect(() => {
    if (!arrastre) return;
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") terminar(false); };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [arrastre, terminar]);

  // Un clic que en realidad fue el final de un arrastre no abre la tarjeta.
  useEffect(() => {
    const clic = (e: MouseEvent) => {
      if (recienArrastrada.current) { e.stopPropagation(); e.preventDefault(); }
    };
    window.addEventListener("click", clic, true);
    return () => window.removeEventListener("click", clic, true);
  }, []);

  // ---------------------------------------------------------------------

  async function verMas() {
    if (!claveMundo || !datos) return;
    setCargandoMas(true);
    try {
      const yaArchivadas = datos.tarjetas.filter(t => t.columna === "archivado").length;
      const { data } = await entregasApi.archivadas(claveMundo, yaArchivadas);
      setDatos(d => d && {
        ...d,
        tarjetas: [...d.tarjetas, ...data.tarjetas.filter(n => !d.tarjetas.some(t => t.tareaId === n.tareaId))],
        archivadas: { total: data.total, mostradas: data.hasta },
      });
    } catch {
      toast.error("No se pudieron traer más archivadas.");
    } finally {
      setCargandoMas(false);
    }
  }

  if (checked && !allowed) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <ShieldAlert size={40} className="text-rose-400" />
        <p className="font-medium text-slate-600 dark:text-slate-400">No tenés acceso al tablero.</p>
      </div>
    );
  }

  const hoy = datos?.hoy ?? hoyIso();
  const delMundo = datos && datos.mundo === claveMundo ? datos : null;
  const todas = delMundo?.tarjetas ?? [];
  const opciones = externo ? [] : opcionesDeQuien(todas);
  const tarjetas = todas.filter(t => deQuien(t, filtro));
  const meToca = (t: Tarjeta) => proximoPaso(t.entrega, t.asignadoA, yo, () => "", !!t.puedo?.decidir, {
    entregoYo: t.puedo?.entregar, hace: t.hace,
  }).aQuien === "vos";
  const columnas = COLUMNAS_DEL_TABLERO.map(c => ({
    ...c,
    lista: ordenar(tarjetas.filter(t => t.columna === c.clave), c.clave, meToca),
  }));
  // En el teléfono se ve una columna: la que tiene algo mío, o la primera con algo.
  const conMiTurno = columnas.find(c => c.clave !== "archivado" && c.lista.some(meToca))?.clave;
  const conAlgo = columnas.find(c => c.lista.length > 0)?.clave;
  const activa: Columna = pestana ?? conMiTurno ?? conAlgo ?? "ingresado";
  const totalArchivadas = filtro ? columnas[4].lista.length : (delMundo?.archivadas.total ?? 0);

  return (
    <div className="animate-fade-in">
      <Suspense fallback={null}><AbrirTareaDeLaUrl /></Suspense>

      <header className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm shadow-brand-600/30">
          <Layers className="h-6 w-6" />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{externo ? "Mi tablero" : "Tablero"}</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {externo
              ? `Lo que te pidieron${mundo ? ` en ${mundo.nombre}` : ""}. Arrastrá cada tarjeta a medida que avanzás: para mandarla a revisar, soltala en «Esperando feedback» y subí los materiales.`
              : `Las piezas de cada acción${mundo ? ` de ${mundo.nombre}` : ""}, con la agencia o con el equipo. Arrastrá para mover; las finalizadas pasan solas a Archivado a los 10 días.`}
          </p>
        </div>
        <Buscador mundo={claveMundo ?? null} usuarioId={yo} hoy={hoy} />
      </header>

      {!delMundo && !error && (
        <div className="grid gap-3 md:grid-cols-5" role="status" aria-label="Cargando el tablero…">
          {[0, 1, 2, 3, 4].map(i => <div key={i} className="skeleton h-72 rounded-2xl" />)}
        </div>
      )}
      {error && !delMundo && (
        <p className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          No se pudo traer el tablero. Se vuelve a intentar solo en unos segundos.
        </p>
      )}

      {delMundo && (
        <>
          {opciones.length > 1 && (
            <div className="mb-3 flex flex-wrap items-center gap-1.5" role="group" aria-label="¿Quién la hace?">
              <span className="mr-1 text-xs font-semibold text-slate-600 dark:text-slate-300">¿Quién la hace?</span>
              <Chip activo={filtro === null} onClick={() => setFiltro(null)}>Todas · {todas.length}</Chip>
              {opciones.map(o => (
                <Chip key={o.clave} activo={filtro === o.clave} onClick={() => setFiltro(f => (f === o.clave ? null : o.clave))}>
                  {o.nombre} · {o.cuantas}
                </Chip>
              ))}
            </div>
          )}

          {/* En el teléfono no entran cinco columnas: se elige cuál ver. */}
          <div className="segmentado mb-3 md:hidden" role="tablist" aria-label="Columna del tablero">
            {columnas.map(c => (
              <button
                key={c.clave}
                type="button"
                role="tab"
                aria-selected={activa === c.clave}
                onClick={() => setPestana(c.clave)}
                className="segmento !min-h-[48px] !flex-1 !px-0.5 flex-col !gap-0 text-[11px] leading-tight"
              >
                <span className="flex items-center gap-1 font-bold tabular-nums">
                  <span className={`h-1.5 w-1.5 rounded-full ${c.punto}`} aria-hidden />
                  {c.clave === "archivado" ? totalArchivadas : c.lista.length}
                </span>
                <span className="w-full truncate">{c.clave === "esperando" ? "Feedback" : c.titulo}</span>
              </button>
            ))}
          </div>

          <div className="flex gap-3 md:overflow-x-auto md:pb-2">
            {columnas.map(c => {
              const destinoValido = arrastre ? sePuedeSoltar(arrastre.tarjeta, c.clave) : false;
              const encima = sobre === c.clave;
              return (
                <section
                  key={c.clave}
                  data-columna={c.clave}
                  aria-labelledby={`col-${c.clave}`}
                  className={`flex min-w-0 flex-1 flex-col rounded-2xl border p-2 transition-[box-shadow,background-color] md:min-w-[12.5rem] ${c.fondo} ${
                    activa === c.clave ? "" : "hidden md:flex"
                  } ${arrastre && destinoValido ? `border-dashed ${encima ? `ring-2 ${c.destino} border-transparent` : "border-slate-400 dark:border-slate-500"}` : "border-slate-300 dark:border-slate-800"} ${
                    arrastre && !destinoValido && c.clave !== arrastre.tarjeta.columna ? "opacity-60" : ""
                  }`}
                >
                  <div className="mb-2 px-1.5 pt-1">
                    <h2 id={`col-${c.clave}`} className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${c.punto}`} aria-hidden />
                      <span className="min-w-0 text-sm font-bold leading-tight text-slate-900 dark:text-slate-100">{c.titulo}</span>
                      <span className="ml-auto rounded-full bg-white px-2 py-0.5 text-xs font-bold tabular-nums text-slate-700 ring-1 ring-slate-300 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700">
                        {c.clave === "archivado" ? totalArchivadas : c.lista.length}
                      </span>
                    </h2>
                    <p className="mt-0.5 pl-[1.125rem] text-xs text-slate-500 dark:text-slate-400">{c.bajada}</p>
                  </div>
                  {c.lista.length === 0 ? (
                    <p className="rounded-xl border border-dashed border-slate-300 px-3 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      {arrastre && destinoValido ? `Soltá acá: ${queHaceMover(arrastre.tarjeta.columna, c.clave)}` : "Nada por acá."}
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {c.lista.map((t, i) => (
                        <TarjetaEntrega
                          key={t.tareaId}
                          tarjeta={t}
                          usuarioId={yo}
                          hoy={hoy}
                          orden={i}
                          onMoverA={a => void moverA(t, a)}
                          onPointerDown={alApretar(t)}
                          mostrarQuien={!externo}
                          arrastrandose={arrastre?.tarjeta.tareaId === t.tareaId}
                        />
                      ))}
                    </ul>
                  )}
                  {c.clave === "archivado" && !filtro && (delMundo.archivadas.total > delMundo.archivadas.mostradas) && (
                    <button
                      type="button"
                      onClick={() => void verMas()}
                      disabled={cargandoMas}
                      className="mt-2 flex min-h-[44px] items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white text-sm font-semibold text-slate-700 transition hover:border-brand-400 hover:text-brand-700 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    >
                      {cargandoMas ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}
                      Ver más ({delMundo.archivadas.total - delMundo.archivadas.mostradas})
                    </button>
                  )}
                  {c.clave === "archivado" && (
                    <p className="mt-2 px-1.5 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                      A los 30 días en Archivado dejan de cargarse: las encontrás con el buscador.
                    </p>
                  )}
                </section>
              );
            })}
          </div>

          {tarjetas.length === 0 && (
            <div className="mt-4 flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center dark:border-slate-700 dark:bg-slate-900">
              <p className="text-base font-semibold text-slate-800 dark:text-slate-100">
                {externo ? "Todavía no tenés tarjetas" : "Todavía no hay tarjetas"}
              </p>
              <p className="mt-1 max-w-md text-sm text-slate-600 dark:text-slate-400">
                {externo
                  ? "Cuando el equipo te pida una pieza desde el calendario, aparece acá en «Ingresado» y te llega un aviso a la campanita."
                  : "Se piden desde la ficha de una acción del calendario: «Pedir una pieza», elegís qué es y quién la hace."}
              </p>
            </div>
          )}

          <section className="mt-6">
            <button
              type="button"
              onClick={() => setVerMetricas(v => !v)}
              aria-expanded={verMetricas}
              className="flex min-h-[44px] items-center gap-2 rounded-xl px-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <BarChart3 className="h-4 w-4 text-brand-600 dark:text-brand-300" />
              {externo ? "Tu retrabajo" : "Retrabajo"}
              <ChevronDown className={`h-4 w-4 transition-transform ${verMetricas ? "rotate-180" : ""}`} />
            </button>
            {verMetricas && claveMundo && <Retrabajo mundo={claveMundo} propio={externo} />}
          </section>
        </>
      )}

      {/* La copia que sigue al puntero mientras se arrastra. */}
      {arrastre && (
        <div
          ref={fantasmaRef}
          aria-hidden
          className="pointer-events-none fixed left-0 top-0 z-[80] origin-top-left"
          style={{ width: arrastre.ancho }}
        >
          <ul>
            <TarjetaEntrega tarjeta={arrastre.tarjeta} usuarioId={yo} hoy={hoy} fantasma />
          </ul>
        </div>
      )}

      {/* En el teléfono se ve una columna sola: mientras se arrastra, abajo
          aparecen todas, para soltar en cualquiera. */}
      {arrastre?.conElDedo && (
        <div className="fixed inset-x-0 bottom-0 z-[85] border-t border-slate-300 bg-white/95 px-2 pb-[max(.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95 md:hidden">
          <p className="mb-1.5 text-center text-xs font-semibold text-slate-600 dark:text-slate-300">Soltala en:</p>
          <div className="grid grid-cols-5 gap-1.5">
            {COLUMNAS_DEL_TABLERO.map(c => {
              const vale = sePuedeSoltar(arrastre.tarjeta, c.clave);
              return (
                <div
                  key={c.clave}
                  data-columna={c.clave}
                  className={`flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl border-2 px-1 text-center text-[11px] font-bold leading-tight ${
                    !vale ? "border-transparent bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
                      : sobre === c.clave ? `border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-500/20 dark:text-brand-100`
                        : "border-dashed border-slate-400 bg-white text-slate-800 dark:border-slate-500 dark:bg-slate-900 dark:text-slate-100"
                  }`}
                >
                  <span className={`h-2 w-2 rounded-full ${c.punto}`} aria-hidden />
                  {c.clave === "esperando" ? "Feedback" : c.titulo}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {pidiendoCambios && (
        <PedirCambios
          tarjeta={pidiendoCambios}
          onCancelar={() => setPidiendoCambios(null)}
          onMandar={texto => { const t = pidiendoCambios; setPidiendoCambios(null); void moverA(t, "en-proceso", texto); }}
          onRevisionCompleta={() => { const t = pidiendoCambios; setPidiendoCambios(null); abrirDetalle(t.tareaId, "revisar", null, true); }}
        />
      )}
    </div>
  );
}

function Chip({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={activo}
      className={`min-h-[36px] rounded-full border px-3 text-xs font-semibold transition ${
        activo
          ? "border-brand-600 bg-brand-600 text-white"
          : "border-slate-300 bg-white text-slate-700 hover:border-brand-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * Esperando feedback → En proceso es pedir cambios: un cuadro chico con "¿qué
 * hay que cambiar?" y un botón para ir a la revisión completa (con marcas
 * sobre la imagen).
 */
function PedirCambios({ tarjeta, onCancelar, onMandar, onRevisionCompleta }: {
  tarjeta: Tarjeta
  onCancelar: () => void
  onMandar: (texto: string) => void
  onRevisionCompleta: () => void
}) {
  const [texto, setTexto] = useState("");
  const cajaRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { cajaRef.current?.focus(); }, []);
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") onCancelar(); };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [onCancelar]);
  return (
    <div className="fixed inset-0 z-[72] flex items-end justify-center sm:items-center sm:p-4">
      <div className="velo animate-fade-in" onClick={onCancelar} aria-hidden />
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="pedir-cambios-titulo"
        onSubmit={e => { e.preventDefault(); if (texto.trim()) onMandar(texto.trim()); }}
        className="relative w-full max-w-lg animate-sheet-up rounded-t-3xl bg-white p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-panel dark:bg-slate-900 dark:ring-1 dark:ring-slate-800 sm:animate-scale-in sm:rounded-2xl"
      >
        <div className="mb-3 flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200">
            <RotateCcw className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h2 id="pedir-cambios-titulo" className="text-lg font-bold text-slate-900 dark:text-slate-100">¿Qué hay que cambiar?</h2>
            <p className="truncate text-sm text-slate-600 dark:text-slate-400">{tarjeta.titulo}</p>
          </div>
        </div>
        <textarea
          ref={cajaRef}
          value={texto}
          onChange={e => setTexto(e.target.value)}
          rows={4}
          maxLength={5000}
          placeholder="Ej: El precio más grande y sacar el fondo azul."
          className="campo !h-auto py-2.5"
          aria-label="Qué hay que cambiar"
        />
        <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">Vuelve a «En proceso» y le avisamos a quien la hace.</p>
        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:items-center">
          <button type="button" onClick={onRevisionCompleta} className="min-h-[44px] rounded-xl px-3 text-sm font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10 sm:mr-auto">
            Ir a la revisión completa (con marcas)
          </button>
          <button type="button" onClick={onCancelar} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
            Cancelar
          </button>
          <button type="submit" disabled={!texto.trim()} className="flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 text-sm font-bold text-white shadow-sm hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400">
            <RotateCcw className="h-4 w-4" /> Pedir cambios
          </button>
        </div>
      </form>
    </div>
  );
}

/**
 * El buscador: por el nombre de la tarjeta o de la acción ("ciberlunes
 * banners" encuentra "Ciberlunes - Banners"). Encuentra también lo archivado
 * que ya no se carga en el tablero, aparte.
 */
function Buscador({ mundo, usuarioId, hoy }: { mundo: string | null; usuarioId: number | null; hoy: string }) {
  const [q, setQ] = useState("");
  // El resultado queda atado a lo que se buscó: si la persona sigue
  // escribiendo, el de antes no se muestra como si fuera el de ahora.
  const [hallado, setHallado] = useState<{ q: string; enTablero: Tarjeta[]; archivadas: Tarjeta[] } | null>(null);
  const cambios = useVistaEntregas(s => s.cambios);
  const texto = q.trim();
  useEffect(() => {
    if (!mundo || texto.length < 2) return;
    let vivo = true;
    const reloj = window.setTimeout(() => {
      entregasApi.buscar(mundo, texto)
        .then(({ data }) => { if (vivo) setHallado({ q: texto, enTablero: data.enTablero, archivadas: data.archivadas }); })
        .catch(() => { if (vivo) setHallado({ q: texto, enTablero: [], archivadas: [] }); });
    }, 250);
    return () => { vivo = false; window.clearTimeout(reloj); };
  }, [texto, mundo, cambios]);
  const resultado = hallado && hallado.q === texto ? hallado : null;
  const buscando = texto.length >= 2 && !resultado;

  return (
    <div className="relative w-full sm:w-80">
      <label className="relative block">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-slate-400" aria-hidden />
        <input
          type="search"
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Buscar: Ciberlunes - Banners"
          aria-label="Buscar tarjetas por acción o nombre"
          className="campo !pl-9 !pr-9"
        />
        {q && (
          <button type="button" onClick={() => setQ("")} aria-label="Borrar la búsqueda"
            className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X className="h-4 w-4" />
          </button>
        )}
      </label>
      {q.trim().length >= 2 && (
        <div className="absolute right-0 top-full z-30 mt-2 max-h-[70vh] w-[min(100vw-2rem,26rem)] overflow-y-auto rounded-2xl border border-slate-300 bg-white p-3 shadow-panel dark:border-slate-700 dark:bg-slate-900">
          {buscando && !resultado ? (
            <p className="flex items-center gap-2 p-2 text-sm text-slate-600 dark:text-slate-300"><Loader2 className="h-4 w-4 animate-spin" /> Buscando…</p>
          ) : resultado && resultado.enTablero.length + resultado.archivadas.length === 0 ? (
            <p className="p-2 text-sm text-slate-600 dark:text-slate-300">No hay tarjetas con «{q.trim()}».</p>
          ) : resultado && (
            <div className="space-y-3">
              {resultado.enTablero.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">En el tablero · {resultado.enTablero.length}</p>
                  <ul className="space-y-2">
                    {resultado.enTablero.map(t => <TarjetaEntrega key={t.tareaId} tarjeta={t} usuarioId={usuarioId} hoy={hoy} />)}
                  </ul>
                </div>
              )}
              {resultado.archivadas.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Archivadas hace más de 30 días · {resultado.archivadas.length}</p>
                  <ul className="space-y-2">
                    {resultado.archivadas.map(t => <TarjetaEntrega key={t.tareaId} tarjeta={t} usuarioId={usuarioId} hoy={hoy} />)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Cuánto retrabajo hubo: las rondas que llevó aprobar cada fase y cuántas se
 * aprobaron a la primera. Se pide al abrirlo (no viaja con el tablero).
 */
function Retrabajo({ mundo, propio }: { mundo: string; propio: boolean }) {
  const [dias, setDias] = useState(90);
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [verDetalle, setVerDetalle] = useState(false);
  useEffect(() => {
    let vivo = true;
    entregasApi.metricas(mundo, dias).then(({ data }) => { if (vivo) setMetricas(data); }).catch(() => { if (vivo) setMetricas(null); });
    return () => { vivo = false; };
  }, [mundo, dias]);
  return (
    <section aria-label="Retrabajo" className="mt-2 rounded-2xl border border-slate-300 bg-white p-4 shadow-card dark:border-slate-700 dark:bg-slate-900 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="segmentado !p-0.5" role="group" aria-label="Período">
          {[30, 90, 365].map(d => (
            <button key={d} type="button" aria-pressed={dias === d} onClick={() => setDias(d)} className="segmento !min-h-[32px] !flex-none whitespace-nowrap !px-2.5 text-xs">
              {d === 365 ? "1 año" : `${d} días`}
            </button>
          ))}
        </div>
      </div>
      {!metricas ? (
        <div className="skeleton h-20 rounded-xl" />
      ) : metricas.fases === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Todavía no se aprobó ninguna fase en este período: cuando se aprueben, acá se ve cuántas rondas llevaron.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 sm:gap-3">
            <Dato etiqueta="Rondas hasta aprobar" valor={numero(metricas.rondasPromedio)} bajada="promedio por fase" />
            <Dato etiqueta="Aprobado a la primera" valor={metricas.aLaPrimera == null ? "—" : `${metricas.aLaPrimera}%`} bajada="de las fases" />
            <Dato etiqueta="Fases aprobadas" valor={String(metricas.fases)} bajada={dias === 365 ? "en el último año" : `en ${dias} días`} />
          </div>
          <button type="button" onClick={() => setVerDetalle(v => !v)} aria-expanded={verDetalle}
            className="-ml-2 mt-3 flex min-h-[40px] items-center gap-1 rounded-xl px-2 text-sm font-semibold text-brand-700 transition hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10">
            <ChevronDown className={`h-4 w-4 transition-transform ${verDetalle ? "rotate-180" : ""}`} />
            {verDetalle ? "Ocultar el detalle" : propio ? "Ver por tipo de pieza" : "Ver por tipo de pieza, responsable y mundo"}
          </button>
          {verDetalle && (
            <div className={`mt-2 grid gap-5 ${propio ? "" : "lg:grid-cols-3"}`}>
              <TablaDeRetrabajo titulo="Por tipo de pieza" filas={metricas.porTipo} />
              {!propio && <TablaDeRetrabajo titulo="Por responsable" filas={metricas.porResponsable} />}
              {!propio && <TablaDeRetrabajo titulo="Por mundo" filas={metricas.porMundo} />}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function Dato({ etiqueta, valor, bajada }: { etiqueta: string; valor: string; bajada: string }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-slate-800/50">
      <p className="text-xs font-semibold leading-tight text-slate-600 dark:text-slate-400">{etiqueta}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100 sm:text-3xl">{valor}</p>
      <p className="text-[11px] text-slate-500 dark:text-slate-400">{bajada}</p>
    </div>
  );
}

/** Una fila por grupo: cuántas fases, rondas promedio y una barra con el %
 *  aprobado a la primera (sobre el 100 %), con el número al lado. */
function TablaDeRetrabajo({ titulo, filas }: { titulo: string; filas: Metricas["porTipo"] }) {
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">{titulo}</h3>
      <table className="w-full text-sm">
        <thead className="sr-only">
          <tr><th>Quién o qué</th><th>Aprobado a la primera</th></tr>
        </thead>
        <tbody>
          {filas.map(f => (
            <tr key={String(f.clave)} className="border-b border-slate-200 last:border-0 dark:border-slate-700">
              <td className="max-w-0 py-2 pr-2">
                <span className="block truncate font-medium text-slate-800 dark:text-slate-200" title={f.nombre ?? String(f.clave)}>{f.nombre ?? String(f.clave)}</span>
                <span className="text-xs text-slate-500 dark:text-slate-400">{f.fases === 1 ? "1 fase" : `${f.fases} fases`} · {numero(f.rondasPromedio)} rondas</span>
              </td>
              <td className="w-[45%] py-2">
                <span className="flex items-center gap-2">
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                    <span className="block h-full rounded-full bg-brand-500" style={{ width: `${f.aLaPrimera ?? 0}%` }} />
                  </span>
                  <span className="w-10 text-right text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-300">{f.aLaPrimera ?? 0}%</span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

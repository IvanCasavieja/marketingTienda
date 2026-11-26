"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Archive, BarChart3, ChevronDown, Layers, Loader2, RotateCcw, Search, ShieldAlert, X } from "lucide-react";
import { toast } from "sonner";
import { entregasApi } from "@/lib/api";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import {
  numero, proximoPaso, type Columna, type Metricas, type Tarjeta, type TiemposDeAgencia, type TiemposDeEntrega,
} from "@/lib/calendario/entregas";
import {
  COLUMNAS_DEL_TABLERO, MS_PARA_ARRASTRAR_CON_EL_DEDO, OTRAS, PX_PARA_ARRASTRAR, conservarArchivadas, defColumna,
  ordenar, pestanasDeTableros, queHaceMover, seMovioElDedo, sePuedeSoltar, tableroDeTarjeta,
} from "@/lib/calendario/tablero";
import { diaEnUruguay, hoyIso } from "@/lib/calendario/fechas";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";
import { mundoEfectivo, useMundoElegido } from "@/lib/mundos";

/** El tablero de la agencia: el de todos los mundos (25/11/2026). */
const TODOS_LOS_MUNDOS = "todos";
import { esExterno } from "@/lib/externos";
import { direccionConTarjeta } from "@/lib/volver";
import { useTableros } from "@/store/tiposDeTarea";
import { useVistaEntregas } from "@/store/entregas";
import { TarjetaEntrega } from "@/components/calendario/entregas/TarjetaEntrega";
import { NuevaTarjeta } from "@/components/calendario/entregas/NuevaTarjeta";
import { hasPermission } from "@/lib/permissions";

/** Cada cuánto pregunta el tablero si cambió algo. Era 15 s, como el
 *  calendario; Ivan (24/11/2026): "entregué la entrega 2 y no se me
 *  actualizó en mi tarjeta de Tienda Inglesa instantáneamente, hubo una
 *  demora hasta que apareció". Sin cambios la respuesta es una línea. */
const SEGUNDOS_DEL_TABLERO = 6;

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
 * de la campanita o del mail. Y la tarjeta abierta queda en la dirección (ver
 * TarjetaEnLaDireccion).
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

/**
 * La tarjeta abierta, en la dirección: `/entregas?tarea=ta-xxx` (H-039 y H-040
 * de la auditoría del 25/11/2026). Abierta tocándola en el tablero, la
 * dirección quedaba «/entregas»: recargar en medio de una entrega, o volver a
 * entrar cuando vencía la sesión, caía en el tablero sin la tarjeta. Y la que
 * llegaba por un link no se sacaba al cerrarla (el router.replace de antes no
 * llegaba a aplicarse), así que recargar la volvía a abrir.
 *
 * - La dirección abre la tarjeta cuando llega con una: el link del mail, la
 *   campanita, recargar.
 * - Abrir o cerrar una tarjeta reescribe la dirección sin sumar pasos al
 *   «atrás» (history.replaceState, que Next toma para useSearchParams).
 * - Después de un «atrás» manda la tarjeta: el formulario de entrega deja un
 *   paso propio en la historia y, al cerrarse, lo saca; el paso al que se
 *   vuelve tiene la dirección de antes y no tiene que reabrir nada.
 */
function TarjetaEnLaDireccion() {
  const tarea = useSearchParams().get("tarea");
  const abierta = useVistaEntregas(s => s.tareaId);
  const llego = useRef(false);
  useEffect(() => {
    const alLlegar = !llego.current;
    llego.current = true;
    if (!tarea) return;
    const abrir = () => {
      // La de la dirección de ese momento: después de un «atrás», ya la corrigió
      // el escucha de abajo.
      const ahora = new URLSearchParams(window.location.search).get("tarea");
      if (tarea === ahora && tarea !== useVistaEntregas.getState().tareaId) useVistaEntregas.getState().abrir(tarea);
    };
    // Al llegar (el link, recargar), ya. Después, un instante más tarde: un
    // «atrás» se pinta enseguida, antes de que el escucha de abajo deje la
    // dirección como la tarjeta, y reabría la que se acababa de cerrar.
    if (alLlegar) {
      abrir();
      return;
    }
    const reloj = window.setTimeout(abrir, 0);
    return () => window.clearTimeout(reloj);
  }, [tarea]);
  useEffect(() => {
    // La del store, no `abierta`: la de arriba la pudo abrir recién.
    ponerLaTarjetaEnLaDireccion(useVistaEntregas.getState().tareaId);
  }, [abierta]);
  useEffect(() => {
    const alVolver = () => ponerLaTarjetaEnLaDireccion(useVistaEntregas.getState().tareaId);
    window.addEventListener("popstate", alVolver);
    return () => window.removeEventListener("popstate", alVolver);
  }, []);
  return null;
}

function ponerLaTarjetaEnLaDireccion(tareaId: string | null) {
  const { pathname, search } = window.location;
  const destino = direccionConTarjeta(pathname, search, tareaId);
  if (destino !== pathname + search) window.history.replaceState(null, "", destino);
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
  // Qué tablero mira el equipo (17/11/2026): Publicis, Another Monday o Diseñadores.
  const [tableroElegido, setTablero] = useState<string | null>(null);
  const [cargandoMas, setCargandoMas] = useState(false);
  const [pidiendoCambios, setPidiendoCambios] = useState<Tarjeta | null>(null);
  const [verMetricas, setVerMetricas] = useState(false);
  const rev = useRef<number | null>(null);
  const datosRef = useRef<Datos | null>(null);
  useEffect(() => { datosRef.current = datos; }, [datos]);
  // Como el calendario (lib/calendario/store.ts, sincronizar): cada pedido
  // del tablero lleva un número y solo se aplica la respuesta del último, y
  // nunca mientras haya un movimiento propio en camino. Si no, al pasar
  // varias tarjetas seguidas la respuesta de un pedido armado antes de
  // guardar el movimiento siguiente las hacía saltar a su columna vieja.
  const pedido = useRef(0);
  const enVuelo = useRef(0);
  const movioAlguna = useRef(false);
  const claveMundo = mundo?.clave;
  const externo = esExterno(user);
  // De qué es el tablero que se mira: el mundo elegido o, para la agencia,
  // todos (25/11/2026: no elige mundos; ve lo que le piden de cualquiera). Lo
  // que se le pide al servidor: el mundo, o nada (todos).
  const claveTablero = externo ? TODOS_LOS_MUNDOS : claveMundo;
  const mundoParaPedir = externo ? null : claveMundo ?? null;
  const yo = user?.id ?? null;
  const creaTarjetas = !externo
    && (hasPermission(user, PERMISOS_CALENDARIO.tareas) || hasPermission(user, PERMISOS_CALENDARIO.pedidos));
  const { tableros } = useTableros(claveMundo);

  const cargar = useCallback(async (desdeCero: boolean) => {
    if (!claveTablero) return;
    const n = ++pedido.current;
    try {
      // Si cambió el día, una tarjeta pudo haber pasado sola a Archivado sin
      // que cambie nada más: se trae todo. El día es el de Uruguay, como el
      // que manda el servidor (con el de la computadora, en otra zona horaria
      // daba distinto siempre y se bajaba todo en cada pregunta).
      const nuevoDia = datosRef.current && datosRef.current.hoy !== diaEnUruguay();
      const { data } = await entregasApi.tablero(mundoParaPedir, desdeCero || nuevoDia ? null : rev.current);
      // Salió otro pedido después, o se está moviendo una tarjeta: esto
      // puede ser de antes. Lo trae el pedido que sigue.
      if (n !== pedido.current || enVuelo.current > 0) return;
      if (data.sinCambios) return;
      rev.current = data.rev;
      const nuevas = data.tarjetas ?? [];
      setDatos(d => {
        // Lo que se trajo con "Ver más" de Archivado no se borra con cada
        // refresco (ver conservarArchivadas). Al cambiar de mundo, sí.
        const tarjetas = d && d.mundo === claveTablero ? conservarArchivadas(d.tarjetas, nuevas) : nuevas;
        const locales = tarjetas.filter(t => t.columna === "archivado").length;
        const total = data.archivadas?.total ?? 0;
        return {
          mundo: claveTablero, hoy: data.hoy ?? diaEnUruguay(), tarjetas,
          archivadas: { total, mostradas: Math.max(data.archivadas?.mostradas ?? 0, locales) },
        };
      });
      setError(false);
    } catch {
      if (n === pedido.current) setError(true);
    }
  }, [claveTablero, mundoParaPedir]);

  // Se pregunta cada SEGUNDOS_DEL_TABLERO si cambió algo (si no, la
  // respuesta es una línea), al volver a la pestaña y al volver a la ventana
  // (24/11/2026: antes era cada 15 s, como el calendario, y solo al volver a
  // la pestaña). Después de entregar o decidir algo en el detalle, se trae
  // todo.
  useEffect(() => {
    if (!allowed || !claveTablero) return;
    void cargar(true);
    // La pestaña y la ventana avisan juntas a veces: una sola pregunta.
    let ultima = 0;
    const revisar = () => {
      if (document.visibilityState !== "visible" || Date.now() - ultima < 1000) return;
      ultima = Date.now();
      void cargar(false);
    };
    const intervalo = window.setInterval(revisar, SEGUNDOS_DEL_TABLERO * 1000);
    document.addEventListener("visibilitychange", revisar);
    window.addEventListener("focus", revisar);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", revisar);
      window.removeEventListener("focus", revisar);
    };
  }, [allowed, claveTablero, cargar, cambios]);

  // ---------------------------------------------------------------------
  // Mover
  // ---------------------------------------------------------------------

  /** Lo que pasa al llevar una tarjeta a otra columna (arrastrando o con
   *  "Mover a…"). La regla la tiene el servidor; acá se abre lo que haga
   *  falta (entregar, decir qué cambiar) y se mueve en la pantalla al toque.
   *  Devuelve si la tarjeta se movió (para no cerrar "Pedir cambios" y
   *  perder lo escrito si el servidor dijo que no). */
  const moverA = useCallback(async (t: Tarjeta, a: Columna, comentario?: string): Promise<boolean> => {
    if (!sePuedeSoltar(t, a)) return false;
    // Quien la entrega llega a Esperando feedback entregando: se abre
    // "Entregar". El resto del equipo la mueve a mano, como en Trello
    // (18/11/2026); lo mismo con pedir cambios, que es de quien decide.
    if (a === "esperando" && t.puedo?.entregar) {
      abrirDetalle(t.tareaId, "entregar", null, true);
      return false;
    }
    if (t.columna === "esperando" && a === "en-proceso" && comentario === undefined && t.puedo?.decidir) {
      setPidiendoCambios(t);
      return false;
    }
    // Archivar lo que no se terminó es cancelar la pieza (16/11/2026): la
    // tarea queda cerrada y la agencia no la puede entregar. Se pregunta antes.
    const cancela = a === "archivado" && t.columna !== "finalizado";
    if (cancela && !window.confirm(`¿Cancelar «${t.titulo}»? Queda en Archivado y no se entrega ni se revisa. Si hace falta, se saca del archivo y vuelve a su columna.`)) {
      return false;
    }
    setDatos(d => d && { ...d, tarjetas: d.tarjetas.map(x => (x.tareaId === t.tareaId ? { ...x, columna: a, volvioConCambios: a === "en-proceso" && t.columna === "esperando" && !!t.puedo?.decidir } : x)) });
    // Lo que se pidió antes de este movimiento ya no vale (ver `pedido`).
    pedido.current++;
    enVuelo.current++;
    let salio = false;
    try {
      const { data } = await entregasApi.mover(t.tareaId, { desde: t.columna, a, comentario: comentario ?? null });
      salio = true;
      movioAlguna.current = true;
      if (data.accion === "a-mano") {
        toast.success(cancela
          ? "Pieza cancelada: quedó en Archivado. Para retomarla, sacala del archivo."
          : `Quedó en ${defColumna(data.columna).titulo}.`);
      } else if (data.columna !== a) {
        toast.success(data.columna === "esperando"
          ? "Aprobaste: ahora la revisa la siguiente persona de la cadena."
          : `Quedó en ${defColumna(data.columna).titulo}.`);
      } else if (cancela) {
        toast.success("Pieza cancelada: quedó en Archivado. Para retomarla, sacala del archivo.");
      } else if (a === "finalizado") {
        toast.success("Aprobada: quedó en Finalizado. Le avisamos a quien la hizo.");
      } else if (a === "en-proceso" && t.columna === "esperando") {
        toast.success("Volvió a En proceso con tus cambios. Le avisamos a quien la hace.");
      }
    } catch (e) {
      // Vuelve solo esta tarjeta: con una foto de antes se deshacían también
      // las otras que se movieron mientras tanto.
      setDatos(d => d && { ...d, tarjetas: d.tarjetas.map(x => (x.tareaId === t.tareaId ? t : x)) });
      toast.error(detalleDeError(e) ?? "No se pudo mover la tarjeta. Probá de nuevo.");
    } finally {
      enVuelo.current--;
      pedido.current++;
    }
    // Se trae el tablero cuando terminó el último movimiento en camino.
    if (enVuelo.current === 0) {
      if (movioAlguna.current) {
        movioAlguna.current = false;
        useVistaEntregas.getState().huboCambios();
      } else {
        void cargar(true);
      }
    }
    return salio;
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
  /** Saca los oyentes del puntero de la tarjeta apretada (ver alApretar).
   *  Escape lo usa: si no, con el botón todavía apretado, mover el mouse
   *  volvía a arrancar el arrastre y al soltar movía (o aprobaba) igual. */
  const soltarPresion = useRef<(() => void) | null>(null);

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

  /** `comoToque`: fue un toque largo con el dedo, sin moverlo. No se mueve
   *  nada y el clic que sigue abre la tarjeta, como un toque común. */
  const terminar = useCallback((soltar: boolean, comoToque = false) => {
    const a = arrastreRef.current;
    const destino = sobreRef.current;
    arrastreRef.current = null;
    sobreRef.current = null;
    setArrastre(null);
    setSobre(null);
    document.body.classList.remove("arrastrando-tarjeta");
    if (!a || comoToque) return;
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
    // Con el dedo: dónde estaba cuando arrancó el arrastre y si después se
    // movió de verdad. Un toque largo sin mover no suelta en ningún lado
    // (si no, la barra "Soltala en:" aparecía bajo el dedo y aprobaba).
    let desde: { x: number; y: number } | null = null;
    let seMovio = false;

    const limpiar = () => {
      if (reloj) window.clearTimeout(reloj);
      window.removeEventListener("pointermove", alMover);
      window.removeEventListener("pointerup", alSoltar);
      window.removeEventListener("pointercancel", alCancelar);
      document.removeEventListener("touchmove", alMoverDedo);
      document.removeEventListener("touchend", alSoltarDedo);
      document.removeEventListener("touchcancel", alCancelarDedo);
      if (soltarPresion.current === limpiar) soltarPresion.current = null;
    };
    const alMover = (ev: PointerEvent) => {
      ultimo = { clientX: ev.clientX, clientY: ev.clientY };
      if (arrastreRef.current) {
        if (conElDedo && seMovioElDedo(desde, ev.clientX, ev.clientY)) seMovio = true;
        ponerFantasma(ev.clientX, ev.clientY);
        return;
      }
      const movido = Math.hypot(ev.clientX - inicio.x, ev.clientY - inicio.y);
      if (conElDedo) {
        // Se movió antes de tiempo: es scroll, no arrastre.
        if (movido > 10) limpiar();
        return;
      }
      if (movido > PX_PARA_ARRASTRAR) empezar(t, ev, tarjetaEl.getBoundingClientRect(), false);
    };
    /** Soltar: con el dedo quieto es un toque (abre la tarjeta), no un movimiento. */
    const soltar = () => {
      limpiar();
      if (!arrastreRef.current) return;
      if (conElDedo && !seMovio) terminar(false, true);
      else terminar(true);
    };
    const alSoltar = soltar;
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
      if (toque) {
        ultimo = { clientX: toque.clientX, clientY: toque.clientY };
        if (seMovioElDedo(desde, toque.clientX, toque.clientY)) seMovio = true;
        ponerFantasma(toque.clientX, toque.clientY);
      }
    };
    const alSoltarDedo = soltar;
    const alCancelarDedo = () => { limpiar(); if (arrastreRef.current) terminar(false); };

    soltarPresion.current = limpiar;
    window.addEventListener("pointermove", alMover);
    window.addEventListener("pointerup", alSoltar);
    window.addEventListener("pointercancel", alCancelar);
    if (conElDedo) {
      document.addEventListener("touchmove", alMoverDedo, { passive: false });
      document.addEventListener("touchend", alSoltarDedo);
      document.addEventListener("touchcancel", alCancelarDedo);
      reloj = window.setTimeout(() => {
        reloj = null;
        desde = { x: ultimo.clientX, y: ultimo.clientY };
        empezar(t, ultimo, tarjetaEl.getBoundingClientRect(), true);
      }, MS_PARA_ARRASTRAR_CON_EL_DEDO);
    }
  };

  // Escape suelta sin mover, y suelta también la tarjeta apretada: mover
  // el mouse con el botón todavía abajo ya no vuelve a arrancar el arrastre.
  useEffect(() => {
    if (!arrastre) return;
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      soltarPresion.current?.();
      terminar(false);
    };
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
    if (!claveTablero || !datos) return;
    setCargandoMas(true);
    try {
      const yaArchivadas = datos.tarjetas.filter(t => t.columna === "archivado").length;
      const { data } = await entregasApi.archivadas(mundoParaPedir, yaArchivadas);
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
  const delMundo = datos && datos.mundo === claveTablero ? datos : null;
  const todas = delMundo?.tarjetas ?? [];
  // Tres tableros (17/11/2026: "asignar a Publicis, asignar a Another Monday
  // o asignar a diseñadores, esos son los 3"). El equipo los ve en pestañas;
  // cada uno de esos equipos entra con su usuario y ve solo el suyo (eso lo
  // recorta el servidor), así que a una cuenta externa no se le muestran.
  const nombresDeTableros = tableros?.map(t => t.nombre) ?? [];
  const pestanas = externo || !tableros ? [] : pestanasDeTableros(todas, nombresDeTableros);
  const filtro = externo || pestanas.length === 0 ? null
    : pestanas.some(p => p.clave === tableroElegido) ? tableroElegido
      : (pestanas.find(p => p.cuantas > 0)?.clave ?? pestanas[0].clave);
  const tarjetas = filtro == null ? todas
    : todas.filter(t => (tableroDeTarjeta(t, nombresDeTableros) ?? OTRAS) === filtro);
  // Sin `puedo.decidir`: ver la nota en TarjetaEntrega (el respaldo no es "te toca").
  const meToca = (t: Tarjeta) => proximoPaso(t.entrega, t.asignadoA, yo, () => "", false, {
    entregoYo: t.puedo?.entregar, hace: t.hace,
  }).aQuien === "vos";
  const columnas = COLUMNAS_DEL_TABLERO.map(c => ({
    ...c,
    lista: ordenar(tarjetas.filter(t => t.columna === c.clave), c.clave, meToca),
  }));
  // En el teléfono se ve una columna: la que tiene algo que me volvió con
  // cambios (H-038 de la auditoría del 25/11/2026: la agencia abría en
  // «Ingresado» y no veía lo devuelto), la que tiene algo mío, o la primera con algo.
  const conCambiosParaMi = columnas.find(c => c.clave !== "archivado" && c.lista.some(t => t.volvioConCambios && meToca(t)))?.clave;
  const conMiTurno = columnas.find(c => c.clave !== "archivado" && c.lista.some(meToca))?.clave;
  const conAlgo = columnas.find(c => c.lista.length > 0)?.clave;
  const activa: Columna = pestana ?? conCambiosParaMi ?? conMiTurno ?? conAlgo ?? "ingresado";
  const totalArchivadas = filtro ? columnas[4].lista.length : (delMundo?.archivadas.total ?? 0);

  return (
    <div className="animate-fade-in">
      <Suspense fallback={null}><TarjetaEnLaDireccion /></Suspense>

      <header className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm shadow-brand-600/30">
          <Layers className="h-6 w-6" />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            {externo ? (user?.empresa ? `Tablero de ${user.empresa}` : "Mi tablero") : "Tableros"}
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {externo
              ? `Lo que te pidieron${mundo ? ` en ${mundo.nombre}` : ""}. Arrastrá cada tarjeta a medida que avanzás: para mandarla a revisar, soltala en «Esperando feedback» y subí los materiales.`
              : `Las piezas de cada acción${mundo ? ` de ${mundo.nombre}` : ""}, en el tablero al que se mandaron. Arrastrá para mover; las finalizadas pasan solas a Archivado a los 10 días.`}
          </p>
        </div>
        {/* Una tarjeta por fuera del calendario (24/11/2026): la crean
            quienes crean tareas; la agencia no. */}
        {creaTarjetas && claveMundo && (
          <NuevaTarjeta mundo={claveMundo} tablero={filtro} usuarioId={yo} onCreada={() => { void cargar(true); }} />
        )}
        <Buscador mundo={claveTablero ?? null} usuarioId={yo} hoy={hoy} conMundo={externo} />
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
          {pestanas.length > 0 && (
            <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Tableros">
              {pestanas.map(p => {
                const activa = filtro === p.clave;
                return (
                  <button
                    key={p.clave}
                    type="button"
                    role="tab"
                    aria-selected={activa}
                    onClick={() => setTablero(p.clave)}
                    className={`flex min-h-[44px] items-center gap-2 rounded-xl border px-4 text-sm font-bold transition active:scale-[.98] ${
                      activa
                        ? "border-brand-600 bg-brand-600 text-white shadow-sm"
                        : "border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    }`}
                  >
                    {p.nombre}
                    <span className={`rounded-full px-1.5 text-xs tabular-nums ${activa ? "bg-white/20" : "bg-slate-100 dark:bg-slate-800"}`}>{p.cuantas}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* En el teléfono no entran cinco columnas: se elige cuál ver. */}
          <div className="segmentado mb-3 md:hidden" role="tablist" aria-label="Columna del tablero">
            {columnas.map(c => {
              // Y la pestaña lo dice, para verlo desde cualquier columna (H-038).
              const volvieron = c.clave === "archivado" ? 0 : c.lista.filter(t => t.volvioConCambios).length;
              return (
              <button
                key={c.clave}
                type="button"
                role="tab"
                aria-selected={activa === c.clave}
                onClick={() => setPestana(c.clave)}
                title={volvieron > 0 ? `${c.titulo}: ${volvieron === 1 ? "1 volvió" : `${volvieron} volvieron`} con cambios` : c.titulo}
                // En 12 px y sin cortar el nombre: si no entra (un teléfono
                // angosto, la letra agrandada), pasa a dos renglones.
                className="segmento !min-h-[48px] !flex-1 !px-0.5 flex-col !gap-0 text-xs leading-tight"
              >
                <span className="flex items-center gap-1 font-bold tabular-nums">
                  <span className={`h-1.5 w-1.5 rounded-full ${c.punto}`} aria-hidden />
                  {c.clave === "archivado" ? totalArchivadas : c.lista.length}
                  {volvieron > 0 && (
                    <span className="flex items-center gap-0.5 rounded-full bg-rose-100 px-1 text-[11px] text-rose-800 dark:bg-rose-500/20 dark:text-rose-200">
                      <RotateCcw className="h-2.5 w-2.5" aria-hidden />{volvieron}
                      <span className="sr-only">{volvieron === 1 ? " volvió" : " volvieron"} con cambios</span>
                    </span>
                  )}
                </span>
                <span className="w-full break-words">{c.clave === "esperando" ? "Feedback" : c.titulo}</span>
              </button>
              );
            })}
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
                  // El anillo de "soltá acá" va por dentro (ring-inset): el
                  // contenedor hace scroll de costado y cortaba el de afuera.
                  // Fondos grises: el texto secundario va en slate-600 (en
                  // slate-500 sobre slate-100 no llegaba a 4,5:1).
                  // Cada columna es una caja apoyada, como las secciones del
                  // calendario: sombra, borde gris y arriba una línea gruesa
                  // del color de su estado. Sin eso, en claro se fundían con
                  // el fondo (Ivan, 19/11/2026).
                  className={`flex min-w-0 flex-1 flex-col rounded-2xl border border-t-4 p-2 shadow-card transition-[box-shadow,background-color] md:min-w-[12.5rem] ${c.fondo} ${c.arriba} ${
                    activa === c.clave ? "" : "hidden md:flex"
                  } ${arrastre && destinoValido ? `border-dashed ${encima ? `ring-2 ring-inset ${c.destino} border-transparent` : "border-slate-400 dark:border-slate-500"}` : "border-slate-300 dark:border-slate-700"} ${
                    arrastre && !destinoValido && c.clave !== arrastre.tarjeta.columna ? "opacity-60" : ""
                  }`}
                >
                  <div className="mb-2 border-b border-slate-300 px-1.5 pb-2 pt-1 dark:border-slate-700">
                    <h2 id={`col-${c.clave}`} className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${c.punto}`} aria-hidden />
                      <span className="min-w-0 text-sm font-bold leading-tight text-slate-900 dark:text-slate-100">{c.titulo}</span>
                      <span className="ml-auto rounded-full bg-white px-2 py-0.5 text-xs font-bold tabular-nums text-slate-700 ring-1 ring-slate-300 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700">
                        {c.clave === "archivado" ? totalArchivadas : c.lista.length}
                      </span>
                    </h2>
                    <p className="mt-0.5 pl-[1.125rem] text-xs text-slate-600 dark:text-slate-400">{c.bajada}</p>
                  </div>
                  {c.lista.length === 0 ? (
                    <p className="rounded-xl border border-dashed border-slate-400 bg-white/60 px-3 py-6 text-center text-sm text-slate-600 dark:border-slate-600 dark:bg-slate-900/40 dark:text-slate-400">
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
                          conMundo={externo}
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
                    <p className="mt-2 px-1.5 text-xs leading-snug text-slate-600 dark:text-slate-400">
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
                  : "Se piden desde la ficha de una acción del calendario: «Crear tarea», elegís qué se pide y quién la hace."}
              </p>
            </div>
          )}

          {/* Solo para Tienda Inglesa (Ivan, 24/11/2026: "cada agencia no
              debería de ver su análisis de entrega"); el servidor también se lo niega. */}
          {!externo && (
          <section className="mt-6">
            <button
              type="button"
              onClick={() => setVerMetricas(v => !v)}
              aria-expanded={verMetricas}
              className="flex min-h-[44px] items-center gap-2 rounded-xl px-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <BarChart3 className="h-4 w-4 text-brand-600 dark:text-brand-300" />
              Análisis de entregas
              <ChevronDown className={`h-4 w-4 transition-transform ${verMetricas ? "rotate-180" : ""}`} />
            </button>
            {verMetricas && claveMundo && <AnalisisDeEntregas mundo={claveMundo} />}
          </section>
          )}
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
          aparecen todas, para soltar en cualquiera. También en la tablet: con
          el dedo no hay scroll de costado mientras se arrastra, y las
          columnas que no entran no se alcanzaban. */}
      {arrastre?.conElDedo && (
        <div className="fixed inset-x-0 bottom-0 z-[85] border-t border-slate-300 bg-white/95 px-2 pb-[max(.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <p className="mb-1.5 text-center text-xs font-semibold text-slate-600 dark:text-slate-300">Soltala en:</p>
          <div className="grid grid-cols-5 gap-1.5">
            {COLUMNAS_DEL_TABLERO.map(c => {
              const vale = sePuedeSoltar(arrastre.tarjeta, c.clave);
              return (
                <div
                  key={c.clave}
                  data-columna={c.clave}
                  // La que no acepta la tarjeta ya se distingue por el fondo
                  // gris sin borde: el nombre igual se tiene que poder leer.
                  className={`flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl border-2 px-1 text-center text-[11px] font-bold leading-tight ${
                    !vale ? "border-transparent bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
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
          // El cuadro se cierra recién cuando el servidor dijo que sí: si no
          // (otra persona ya decidió, se cortó el wifi), lo escrito queda.
          onMandar={async texto => { const t = pidiendoCambios; if (await moverA(t, "en-proceso", texto)) setPidiendoCambios(null); }}
          onRevisionCompleta={() => { const t = pidiendoCambios; setPidiendoCambios(null); abrirDetalle(t.tareaId, "revisar", null, true); }}
        />
      )}
    </div>
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
  /** Termina cuando contestó el servidor. Si salió bien, el cuadro se cierra
   *  desde afuera; si no, queda abierto con lo escrito. */
  onMandar: (texto: string) => Promise<void>
  onRevisionCompleta: () => void
}) {
  const [texto, setTexto] = useState("");
  const [mandando, setMandando] = useState(false);
  async function mandar() {
    const limpio = texto.trim();
    if (!limpio || mandando) return;
    setMandando(true);
    try {
      await onMandar(limpio);
    } finally {
      setMandando(false);
    }
  }
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
        onSubmit={e => { e.preventDefault(); void mandar(); }}
        className="relative w-full max-w-lg animate-sheet-up rounded-t-3xl bg-white p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-panel dark:bg-slate-900 dark:ring-1 dark:ring-slate-700 sm:animate-scale-in sm:rounded-2xl"
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
          <button type="submit" disabled={!texto.trim() || mandando} className="flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 text-sm font-bold text-white shadow-sm hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400">
            {mandando ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />} Pedir cambios
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
function Buscador({ mundo, usuarioId, hoy, conMundo = false }: {
  mundo: string | null; usuarioId: number | null; hoy: string
  /** La agencia: busca en todos los mundos y cada tarjeta dice el suyo. */
  conMundo?: boolean
}) {
  const [q, setQ] = useState("");
  // El resultado queda atado a lo que se buscó: si la persona sigue
  // escribiendo, el de antes no se muestra como si fuera el de ahora.
  // Si la búsqueda falla, se dice (antes se mostraba "No hay tarjetas", como
  // si no existieran).
  const [hallado, setHallado] = useState<{ q: string; enTablero: Tarjeta[]; archivadas: Tarjeta[]; fallo?: boolean } | null>(null);
  const [intento, setIntento] = useState(0);
  const cambios = useVistaEntregas(s => s.cambios);
  const texto = q.trim();
  useEffect(() => {
    if (!mundo || texto.length < 2) return;
    let vivo = true;
    const reloj = window.setTimeout(() => {
      entregasApi.buscar(mundo === TODOS_LOS_MUNDOS ? null : mundo, texto)
        .then(({ data }) => { if (vivo) setHallado({ q: texto, enTablero: data.enTablero, archivadas: data.archivadas }); })
        .catch(() => { if (vivo) setHallado({ q: texto, enTablero: [], archivadas: [], fallo: true }); });
    }, 250);
    return () => { vivo = false; window.clearTimeout(reloj); };
  }, [texto, mundo, cambios, intento]);
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
          className="campo !pl-9 !pr-12 sm:!pr-9"
        />
        {/* 40 px para el dedo en el teléfono; en la compu, el de siempre. */}
        {q && (
          <button type="button" onClick={() => setQ("")} aria-label="Borrar la búsqueda"
            className="absolute right-1 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 sm:right-1.5 sm:h-8 sm:w-8">
            <X className="h-4 w-4" />
          </button>
        )}
      </label>
      {q.trim().length >= 2 && (
        <div className="absolute right-0 top-full z-30 mt-2 max-h-[70vh] w-[min(100vw-2rem,26rem)] overflow-y-auto rounded-2xl border border-slate-300 bg-white p-3 shadow-panel dark:border-slate-700 dark:bg-slate-900">
          {buscando && !resultado ? (
            <p className="flex items-center gap-2 p-2 text-sm text-slate-600 dark:text-slate-300"><Loader2 className="h-4 w-4 animate-spin" /> Buscando…</p>
          ) : resultado?.fallo ? (
            <div className="flex flex-wrap items-center gap-2 p-2">
              <p className="text-sm text-slate-700 dark:text-slate-200">No se pudo buscar. Probá de nuevo.</p>
              <button type="button" onClick={() => { setHallado(null); setIntento(n => n + 1); }}
                className="min-h-[40px] rounded-xl px-3 text-sm font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10">
                Reintentar
              </button>
            </div>
          ) : resultado && resultado.enTablero.length + resultado.archivadas.length === 0 ? (
            <p className="p-2 text-sm text-slate-600 dark:text-slate-300">No hay tarjetas con «{q.trim()}».</p>
          ) : resultado && (
            <div className="space-y-3">
              {resultado.enTablero.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">En el tablero · {resultado.enTablero.length}</p>
                  <ul className="space-y-2">
                    {resultado.enTablero.map(t => <TarjetaEntrega key={t.tareaId} tarjeta={t} usuarioId={usuarioId} hoy={hoy} conMundo={conMundo} />)}
                  </ul>
                </div>
              )}
              {resultado.archivadas.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Archivadas hace más de 30 días · {resultado.archivadas.length}</p>
                  <ul className="space-y-2">
                    {resultado.archivadas.map(t => <TarjetaEntrega key={t.tareaId} tarjeta={t} usuarioId={usuarioId} hoy={hoy} conMundo={conMundo} />)}
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
 * El análisis de entregas (ex «Retrabajo»; Ivan, 20/11/2026: "el retrabajo sí
 * sirve, pero sería más un análisis"): cuánto tarda cada agencia, cuántas
 * piezas se pasan de fecha y cuántas rondas llevó aprobar cada fase. Se pide
 * al abrirlo (no viaja con el tablero). Solo para Tienda Inglesa: la agencia no
 * lo ve (24/11/2026; antes veía el suyo).
 */
function AnalisisDeEntregas({ mundo }: { mundo: string }) {
  const [dias, setDias] = useState(90);
  // Las métricas quedan atadas al pedido (mundo y días) que las trajo; si
  // falla, se dice y se puede reintentar (antes quedaba el esqueleto para
  // siempre).
  const [metricas, setMetricas] = useState<{ clave: string; datos: Metricas | null } | null>(null);
  const [intento, setIntento] = useState(0);
  const [verDetalle, setVerDetalle] = useState(false);
  const clave = `${mundo}|${dias}|${intento}`;
  useEffect(() => {
    let vivo = true;
    entregasApi.metricas(mundo, dias)
      .then(({ data }) => { if (vivo) setMetricas({ clave, datos: data }); })
      .catch(() => { if (vivo) setMetricas({ clave, datos: null }); });
    return () => { vivo = false; };
  }, [mundo, dias, clave]);
  const actual = metricas && metricas.clave === clave ? metricas : null;
  const m = actual?.datos ?? null;
  return (
    <section aria-label="Análisis de entregas" className="mt-2 rounded-2xl border border-slate-300 bg-white p-4 shadow-card dark:border-slate-700 dark:bg-slate-900 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="segmentado !p-0.5" role="group" aria-label="Período">
          {[30, 90, 365].map(d => (
            <button key={d} type="button" aria-pressed={dias === d} onClick={() => setDias(d)} className="segmento !min-h-[40px] !flex-none whitespace-nowrap !px-2.5 text-xs">
              {d === 365 ? "1 año" : `${d} días`}
            </button>
          ))}
        </div>
      </div>
      {!actual ? (
        <div className="skeleton h-20 rounded-xl" />
      ) : !m ? (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm text-slate-700 dark:text-slate-200">No se pudo traer el análisis.</p>
          <button type="button" onClick={() => setIntento(n => n + 1)}
            className="min-h-[40px] rounded-xl px-3 text-sm font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10">
            Probar de nuevo
          </button>
        </div>
      ) : (
        <>
          {m.tiempos && <TiemposYFechas tiempos={m.tiempos} porAgencia={m.porAgencia ?? []} />}
          <h3 className={`mb-2 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400 ${m.tiempos ? "mt-5 border-t border-slate-200 pt-4 dark:border-slate-700" : ""}`}>
            Versiones
          </h3>
          {m.fases === 0 ? (
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Todavía no se aprobó ninguna fase en este período: cuando se aprueben, acá se ve cuántas versiones llevaron.
            </p>
              ) : (
            <>
              <div className="grid grid-cols-3 gap-2 sm:gap-3">
                <Dato etiqueta="Versiones hasta aprobar" valor={numero(m.rondasPromedio)} bajada="promedio por fase" />
                <Dato etiqueta="Aprobado a la primera" valor={m.aLaPrimera == null ? "—" : `${m.aLaPrimera}%`} bajada="de las fases" />
                <Dato etiqueta="Fases aprobadas" valor={String(m.fases)} bajada={dias === 365 ? "en el último año" : `en ${dias} días`} />
              </div>
              <button type="button" onClick={() => setVerDetalle(v => !v)} aria-expanded={verDetalle}
                className="-ml-2 mt-3 flex min-h-[40px] items-center gap-1 rounded-xl px-2 text-sm font-semibold text-brand-700 transition hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10">
                <ChevronDown className={`h-4 w-4 transition-transform ${verDetalle ? "rotate-180" : ""}`} />
                {verDetalle ? "Ocultar el detalle" : "Ver por tipo de pieza, responsable y mundo"}
              </button>
              {verDetalle && (
                <div className="mt-2 grid gap-5 lg:grid-cols-3">
                  <TablaDeRondas titulo="Por tipo de pieza" filas={m.porTipo} />
                  <TablaDeRondas titulo="Por responsable" filas={m.porResponsable} />
                  <TablaDeRondas titulo="Por mundo" filas={m.porMundo} />
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

/**
 * Cuánto tarda y cuántas piezas se pasan de fecha: el total y, para el
 * equipo, una fila por agencia (los tres tableros primero, después las demás
 * y el equipo al final: lo ordena el servidor).
 */
function TiemposYFechas({ tiempos: t, porAgencia }: {
  tiempos: TiemposDeEntrega; porAgencia: TiemposDeAgencia[];
}) {
  const titulo = (
    <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
      Tiempos y fechas
    </h3>
  );
  if (t.entregadas === 0 && t.aprobadas === 0 && t.vencidas === 0) {
    return (
      <>
        {titulo}
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Todavía no hay entregas en este período: cuando entreguen, acá se ve cuánto tarda cada agencia y cuántas piezas se pasan de fecha.
        </p>
      </>
    );
  }
  return (
    <>
      {titulo}
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        <Dato etiqueta="Días hasta entregar" valor={numero(t.diasHastaEntregar)} bajada="promedio, desde que se pide" />
        <Dato etiqueta="Entregado a tiempo" valor={t.aTiempo == null ? "—" : `${t.aTiempo}%`}
          bajada={cuantas(t.entregadas, "entregada", "entregadas")} />
        <Dato etiqueta="Se pasaron de fecha" valor={String(t.sePasaron)} alerta={t.sePasaron > 0}
          bajada={cuantas(t.vencidas, "vencida hoy", "vencidas hoy")} />
      </div>
      {t.aprobadas > 0 && (
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          Aprobarse del todo llevó{" "}
          <strong className="font-semibold text-slate-800 dark:text-slate-200">{dias(t.diasHastaAprobar)}</strong>{" "}
          en promedio desde que se pidió ({cuantas(t.aprobadas, "pieza aprobada", "piezas aprobadas")}).
        </p>
      )}
      {porAgencia.length > 0 && (
        <div className="mt-4">
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Por agencia</h4>
          <ul>
            {porAgencia.map(g => (
              <li key={g.clave} className="flex flex-col gap-1.5 border-b border-slate-200 py-2.5 last:border-0 dark:border-slate-700 sm:flex-row sm:items-center sm:gap-4">
                <div className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-slate-800 dark:text-slate-200" title={g.nombre}>{g.nombre}</span>
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {cuantas(g.entregadas, "entregada", "entregadas")} · {cuantas(g.aprobadas, "aprobada", "aprobadas")}
                    {g.vencidas > 0 && ` · ${cuantas(g.vencidas, "vencida hoy", "vencidas hoy")}`}
                  </span>
                </div>
                <dl className="grid grid-cols-3 gap-2 text-xs sm:w-[26rem] sm:flex-none">
                  <div>
                    <dt className="text-slate-500 dark:text-slate-400">Hasta entregar</dt>
                    <dd className="font-semibold tabular-nums text-slate-800 dark:text-slate-200">{dias(g.diasHastaEntregar)}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500 dark:text-slate-400">Hasta aprobarse</dt>
                    <dd className="font-semibold tabular-nums text-slate-800 dark:text-slate-200">{dias(g.diasHastaAprobar)}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500 dark:text-slate-400">Se pasaron de fecha</dt>
                    <dd className={`font-semibold tabular-nums ${g.sePasaron > 0 ? "text-amber-700 dark:text-amber-300" : "text-slate-800 dark:text-slate-200"}`}>
                      {g.sePasaron}
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        «Hasta entregar»: los días desde que se pidió la pieza hasta su primera entrega. «Se pasaron de fecha»: la
        primera entrega llegó después del vencimiento, o hoy está vencida y le toca a quien la hace (sin entregar o con
        cambios pedidos). Lo que espera la revisión del equipo no cuenta.
      </p>
    </>
  );
}

function cuantas(n: number, una: string, varias: string): string {
  return n === 1 ? `1 ${una}` : `${n} ${varias}`;
}

function dias(n: number | null): string {
  if (n == null) return "—";
  return `${numero(n)} ${n === 1 ? "día" : "días"}`;
}

function Dato({ etiqueta, valor, bajada, alerta = false }: { etiqueta: string; valor: string; bajada: string; alerta?: boolean }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-slate-800/50">
      <p className="text-xs font-semibold leading-tight text-slate-600 dark:text-slate-400">{etiqueta}</p>
      <p className={`mt-1 text-2xl font-bold sm:text-3xl ${alerta ? "text-amber-700 dark:text-amber-300" : "text-slate-900 dark:text-slate-100"}`}>{valor}</p>
      <p className="text-xs text-slate-600 dark:text-slate-400">{bajada}</p>
    </div>
  );
}

/** Una fila por grupo: cuántas fases, rondas promedio y una barra con el %
 *  aprobado a la primera (sobre el 100 %), con el número al lado. */
function TablaDeRondas({ titulo, filas }: { titulo: string; filas: Metricas["porTipo"] }) {
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
                <span className="text-xs text-slate-500 dark:text-slate-400">{f.fases === 1 ? "1 fase" : `${f.fases} fases`} · {numero(f.rondasPromedio)} versiones</span>
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

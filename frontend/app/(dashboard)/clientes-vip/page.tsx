"use client";
// Clientes VIP (25/11/2026). Ivan: "dashboard con un agente que analice…
// prever el comportamiento futuro de los clientes VIP… tengo acceso yo y Emi
// Perdomo… que tenga permiso para ver la sección así se le da a un usuario".
// Ver: clientes_vip.view. Cargar: clientes_vip.cargar. El servidor:
// backend/app/services/clientes_vip.py.
import { useCallback, useEffect, useRef, useState } from "react";
import { FileUp, Loader2, Lock, Star } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import { clientesVipApi } from "@/lib/api";
import { extractErrorDetail } from "@/lib/errors";
import type { Tablero } from "@/lib/clientes-vip/tipos";
import { mesLargo } from "@/lib/clientes-vip/tipos";
import CargarArchivo from "@/components/clientes-vip/CargarArchivo";
import ListaClientes from "@/components/clientes-vip/ListaClientes";
import {
  CAJA, Cargas, Dimensiones, GraficoVentas, Indicadores, InformeDelMes, LoQueViene, Segmentos,
} from "@/components/clientes-vip/Piezas";

export default function ClientesVipPage() {
  const { user } = useCurrentUser();
  const ve = hasPermission(user, "clientes_vip.view");
  const carga = ve && hasPermission(user, "clientes_vip.cargar");
  const [tablero, setTablero] = useState<Tablero | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [segmento, setSegmento] = useState<string | null>(null);
  const [vuelta, setVuelta] = useState(0);
  const lista = useRef<HTMLDivElement>(null);

  const traer = useCallback(() => {
    clientesVipApi.tablero()
      .then(({ data }) => { setTablero(data); setError(null); })
      .catch((e) => setError(extractErrorDetail(e, "No se pudo traer el tablero.")));
  }, []);

  useEffect(() => { if (ve) traer(); }, [ve, traer]);

  // Después de una carga el informe tarda unos minutos: se mira de nuevo cada
  // 30 segundos hasta que llega el del último mes (10 veces como mucho).
  useEffect(() => {
    if (!tablero?.ultimo_mes || tablero.informe?.mes === tablero.ultimo_mes || vuelta >= 10) return;
    const t = setTimeout(() => { setVuelta((v) => v + 1); traer(); }, 30_000);
    return () => clearTimeout(t);
  }, [tablero, vuelta, traer]);

  if (user && !ve) {
    return (
      <div className={`${CAJA} p-8 max-w-lg mx-auto mt-10 text-center`}>
        <Lock className="mx-auto text-slate-400" size={22} />
        <p className="mt-3 text-sm text-slate-700 dark:text-slate-200">No tenés permiso para ver Clientes VIP.</p>
        <p className="mt-1 text-xs text-slate-500">Si lo necesitás, pedíselo a quien administra Core Tienda.</p>
      </div>
    );
  }

  const elegirSegmento = (s: string | null) => {
    setSegmento(s);
    if (s) lista.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="animate-fade-in w-full space-y-5">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <Star size={20} className="text-slate-400" />
          <div>
            <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Clientes VIP</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {tablero?.ultimo_mes
                ? `Sus compras mes a mes, con datos hasta ${mesLargo(tablero.ultimo_mes)}. Confidencial.`
                : "Sus compras mes a mes. Confidencial."}
            </p>
          </div>
        </div>
        {carga && !cargando && (
          <button onClick={() => setCargando(true)} className="btn-primary flex items-center gap-2 text-sm">
            <FileUp size={15} /> Cargar archivo
          </button>
        )}
      </div>

      {cargando && (
        <CargarArchivo
          mesesCargados={tablero?.meses.map((m) => m.mes) ?? []}
          onCerrar={() => setCargando(false)}
          onCargado={() => { setVuelta(0); traer(); }}
        />
      )}

      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      {!tablero && !error && <div className="py-20 flex justify-center"><Loader2 className="animate-spin text-slate-400" size={22} /></div>}

      {tablero && !tablero.ultimo_mes && !cargando && (
        <div className={`${CAJA} p-8 text-center`}>
          <p className="text-sm text-slate-700 dark:text-slate-200">Todavía no hay datos cargados.</p>
          <p className="mt-1 text-xs text-slate-500">
            {carga ? "Cargá el CSV (o el zip) de compras de los clientes VIP: se lee en tu computadora y se sube solo el resumen."
                   : "Cuando alguien cargue el archivo del mes, aparece acá."}
          </p>
          {carga && <button onClick={() => setCargando(true)} className="mt-4 btn-primary text-sm">Cargar archivo</button>}
        </div>
      )}

      {tablero?.ultimo_mes && (
        <>
          <Indicadores meses={tablero.meses} totalClientes={tablero.clientes} />
          <div className="grid lg:grid-cols-3 gap-5">
            <div className="lg:col-span-2"><GraficoVentas meses={tablero.meses} prediccion={tablero.prediccion} /></div>
            <LoQueViene p={tablero.prediccion} ultimo={tablero.meses[tablero.meses.length - 1]} />
          </div>
          <InformeDelMes informe={tablero.informe} ultimoMes={tablero.ultimo_mes} />
          <Segmentos segmentos={tablero.segmentos} elegido={segmento} onElegir={elegirSegmento} />
          <Dimensiones dims={tablero.dimensiones} />
          <div ref={lista} className="scroll-mt-4"><ListaClientes segmento={segmento} onSegmento={setSegmento} ultimoMes={tablero.ultimo_mes} /></div>
          <Cargas cargas={tablero.cargas} />
        </>
      )}
    </div>
  );
}

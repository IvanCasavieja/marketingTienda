"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { facturacionApi, type FacturacionDashboardResponse, type FacturacionMovimiento } from "@/lib/api";
import { fMoney } from "@/lib/format";
import DonutCard, { type DonutDatum } from "./DonutCard";
import LedgerList from "./LedgerList";

const PAGE_SIZE = 20;

// Mismos colores que ya usa esta app en otras pantallas -- ver plan de
// implementación para la justificación de cada par (accesibilidad, choque
// de significado entre tortas vecinas, etc.)
const COLOR_ENTRADA = "#10b981";
const COLOR_SALIDA = "#ef4444";
const COLOR_CANJE_ESTADO: Record<string, string> = {
  pendiente: "#f59e0b",
  activo: "#10b981",
  cerrado: "#94a3b8",
};
// Paleta categórica para el desglose por cuenta en la torta general -- las
// cuentas son dinámicas (no hay un mapa fijo clave->color posible).
const CUENTA_COLORS = ["#6366f1", "#8b5cf6", "#0ea5e9", "#f43f5e", "#14b8a6", "#f59e0b"];
const COLOR_SIN_CUENTA = "#94a3b8";

interface FacturacionDashboardProps {
  /** Incrementarlo fuerza un refetch -- lo sube page.tsx cuando se confirma
   * una factura desde el modal de subida. */
  refreshToken: number;
}

function CuentaSelect({
  cuentas, value, onChange,
}: {
  cuentas: { id: number; nombre: string }[];
  value: number | null;
  onChange: (id: number) => void;
}) {
  const { t } = useTranslation();
  if (cuentas.length === 0) {
    return (
      <Link href="/facturacion/cuentas" className="text-xs text-brand-600 dark:text-brand-400 hover:underline shrink-0 whitespace-nowrap">
        {t("facturacion.cuentas.crearPrimera")}
      </Link>
    );
  }
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(Number(e.target.value))}
      className="input text-xs py-1.5 px-2 w-auto max-w-[160px] shrink-0"
    >
      {cuentas.map((c) => (
        <option key={c.id} value={c.id}>{c.nombre}</option>
      ))}
    </select>
  );
}

export default function FacturacionDashboard({ refreshToken }: FacturacionDashboardProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<FacturacionDashboardResponse | null>(null);
  const [movimientos, setMovimientos] = useState<FacturacionMovimiento[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  // Separado de "data === null" a propósito -- antes un error de red/permiso
  // se veía IGUAL que "todavía no hay datos", sin ninguna pista de qué
  // falló realmente. Guarda el detalle tal cual lo manda el backend cuando
  // lo tiene (403 "Permiso requerido: ...", etc.), o un mensaje genérico si
  // ni siquiera hubo respuesta (backend caído/dormido, red).
  const [error, setError] = useState<string | null>(null);

  async function refetch(overrides?: { presupuesto_cuenta_id?: number; canjes_cuenta_id?: number }) {
    setLoading(true);
    setError(null);
    try {
      const { data: res } = await facturacionApi.dashboard({
        limit: PAGE_SIZE,
        offset: 0,
        presupuesto_cuenta_id: overrides?.presupuesto_cuenta_id ?? data?.presupuesto.cuenta_id ?? undefined,
        canjes_cuenta_id: overrides?.canjes_cuenta_id ?? data?.canjes.cuenta_id ?? undefined,
      });
      setData(res);
      setMovimientos(res.presupuesto.movimientos);
    } catch (err: any) {
      setData(null);
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      setError(
        detail ? `Error ${status ?? ""}: ${detail}` : `No se pudo cargar el dashboard (${err?.message ?? "error desconocido"})`
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  async function loadMore() {
    if (!data) return;
    setLoadingMore(true);
    try {
      const { data: res } = await facturacionApi.dashboard({
        limit: PAGE_SIZE,
        offset: movimientos.length,
        presupuesto_cuenta_id: data.presupuesto.cuenta_id ?? undefined,
        canjes_cuenta_id: data.canjes.cuenta_id ?? undefined,
      });
      setMovimientos((prev) => [...prev, ...res.presupuesto.movimientos]);
    } finally {
      setLoadingMore(false);
    }
  }

  const presupuestoData: DonutDatum[] = data
    ? [
        { key: "entrada", label: t("facturacion.entrada"), value: data.presupuesto.entradas_total, color: COLOR_ENTRADA },
        { key: "salida", label: t("facturacion.salida"), value: data.presupuesto.salidas_total, color: COLOR_SALIDA },
      ]
    : [];

  const canjesData: DonutDatum[] = data
    ? Object.entries(data.canjes.por_estado).map(([estado, valor]) => ({
        key: estado,
        label: t(`facturacion.estados.${estado}`, estado),
        value: valor,
        color: COLOR_CANJE_ESTADO[estado] ?? "#94a3b8",
      }))
    : [];

  const generalData: DonutDatum[] = data
    ? data.general.por_cuenta.map((c, i) => ({
        key: String(c.cuenta_id ?? "sin-cuenta"),
        label: c.cuenta,
        value: c.monto,
        color: c.cuenta_id === null ? COLOR_SIN_CUENTA : CUENTA_COLORS[i % CUENTA_COLORS.length],
      }))
    : [];

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-500/10 rounded-lg px-4 py-3">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Torta general -- el total (saldo de presupuesto + canjes, todas las
          cuentas juntas) al centro, desglosado por cuenta alrededor. */}
      <DonutCard
        title={t("facturacion.charts.general.title")}
        subtitle={t("facturacion.charts.general.subtitle")}
        data={generalData}
        loading={loading}
        emptyLabel={t("facturacion.noData")}
        valueFormatter={fMoney}
        centerValue={data ? fMoney(data.general.total) : undefined}
        centerSubLabel={t("facturacion.charts.general.centerSubLabel")}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        {/* Presupuesto: entradas/salidas + ledger tipo cuenta de débito, de UNA cuenta a la vez */}
        <DonutCard
          title={t("facturacion.charts.presupuesto.title")}
          subtitle={t("facturacion.charts.presupuesto.subtitle")}
          data={presupuestoData}
          loading={loading}
          emptyLabel={data && data.cuentas.length === 0 ? t("facturacion.cuentas.sinCuentas") : t("facturacion.noData")}
          valueFormatter={fMoney}
          headerAction={
            data && (
              <CuentaSelect
                cuentas={data.cuentas}
                value={data.presupuesto.cuenta_id}
                onChange={(id) => refetch({ presupuesto_cuenta_id: id })}
              />
            )
          }
        >
          {data && data.presupuesto.cuenta_id !== null && (
            <LedgerList
              movimientos={movimientos}
              total={data.presupuesto.movimientos_total}
              onLoadMore={loadMore}
              loadingMore={loadingMore}
            />
          )}
        </DonutCard>

        {/* Canjes por estado, de UNA cuenta a la vez */}
        <DonutCard
          title={t("facturacion.charts.canjes.title")}
          subtitle={t("facturacion.charts.canjes.subtitle")}
          data={canjesData}
          loading={loading}
          emptyLabel={data && data.cuentas.length === 0 ? t("facturacion.cuentas.sinCuentas") : t("facturacion.noData")}
          valueFormatter={fMoney}
          headerAction={
            data && (
              <CuentaSelect
                cuentas={data.cuentas}
                value={data.canjes.cuenta_id}
                onChange={(id) => refetch({ canjes_cuenta_id: id })}
              />
            )
          }
        />
      </div>
    </div>
  );
}

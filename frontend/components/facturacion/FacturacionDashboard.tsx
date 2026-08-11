"use client";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
// Paleta categórica para el desglose de salidas por proveedor -- a
// diferencia de entrada/salida y canjes por estado, acá los "proveedor"
// son dinámicos (no hay un mapa fijo clave->color posible). "Otros" siempre
// gris, mismo criterio de "recede" que "cerrado" en canjes por estado.
const PROVEEDOR_COLORS = ["#6366f1", "#8b5cf6", "#0ea5e9", "#f43f5e", "#14b8a6"];
const COLOR_OTROS = "#94a3b8";

interface FacturacionDashboardProps {
  /** Incrementarlo fuerza un refetch -- lo sube page.tsx cuando se confirma
   * una factura desde el modal de subida. */
  refreshToken: number;
}

export default function FacturacionDashboard({ refreshToken }: FacturacionDashboardProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<FacturacionDashboardResponse | null>(null);
  const [movimientos, setMovimientos] = useState<FacturacionMovimiento[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    setLoading(true);
    facturacionApi
      .dashboard({ limit: PAGE_SIZE, offset: 0 })
      .then(({ data: res }) => {
        setData(res);
        setMovimientos(res.presupuesto.movimientos);
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [refreshToken]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const { data: res } = await facturacionApi.dashboard({ limit: PAGE_SIZE, offset: movimientos.length });
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
    ? data.general.salidas_por_proveedor.map((s, i) => ({
        key: s.proveedor,
        label: s.proveedor,
        value: s.monto,
        color: s.proveedor === "Otros" ? COLOR_OTROS : PROVEEDOR_COLORS[i % PROVEEDOR_COLORS.length],
      }))
    : [];

  return (
    <div className="space-y-4">
      {/* Torta general -- el total (saldo de presupuesto + canjes) al centro,
          desglosado en salidas por proveedor alrededor. */}
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
        {/* Presupuesto: entradas/salidas + ledger tipo cuenta de débito */}
        <DonutCard
          title={t("facturacion.charts.presupuesto.title")}
          subtitle={t("facturacion.charts.presupuesto.subtitle")}
          data={presupuestoData}
          loading={loading}
          emptyLabel={t("facturacion.noData")}
          valueFormatter={fMoney}
        >
          {data && (
            <LedgerList
              movimientos={movimientos}
              total={data.presupuesto.movimientos_total}
              onLoadMore={loadMore}
              loadingMore={loadingMore}
            />
          )}
        </DonutCard>

        {/* Canjes por estado */}
        <DonutCard
          title={t("facturacion.charts.canjes.title")}
          subtitle={t("facturacion.charts.canjes.subtitle")}
          data={canjesData}
          loading={loading}
          emptyLabel={t("facturacion.noData")}
          valueFormatter={fMoney}
        />
      </div>
    </div>
  );
}

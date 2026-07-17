"use client";
import Link from "next/link";
import {
  LayoutDashboard, Megaphone, Brain, Presentation, Layers,
  Settings, MessageCircle, BarChart2, Upload,
  Download, Eye, GitBranch, Variable, Users, RefreshCw,
  CheckCircle2, AlertTriangle, Clock, Tag, SlidersHorizontal, LineChart, ClipboardList,
  Loader2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { RobotMascot, RobotMini } from "@/components/RobotMascot";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function SectionTitle({ icon: Icon, title, color = "text-brand-600" }: {
  icon: React.ElementType; title: string; color?: string;
}) {
  return (
    <div className="flex items-center gap-2.5 mb-5">
      <div className="w-8 h-8 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0">
        <Icon size={16} className={color} />
      </div>
      <h2 className="text-lg font-bold text-slate-800 dark:text-slate-200">{title}</h2>
    </div>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-5 ${className}`}>
      {children}
    </div>
  );
}

function Step({ n, title, description }: { n: number; title: string; description: string }) {
  return (
    <div className="flex gap-4">
      <div className="w-7 h-7 rounded-full bg-brand-600 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
        {n}
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{title}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">{description}</p>
      </div>
    </div>
  );
}

function Chip({ icon: Icon, label, color = "bg-slate-100 text-slate-600" }: {
  icon: React.ElementType; label: string; color?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${color}`}>
      <Icon size={11} />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Page — cada sección solo se muestra si el usuario tiene el permiso de
// "ver" esa parte de la plataforma. Un Viewer sin cenefas.view, por ejemplo,
// no ve la guía de Cenefas porque tampoco puede entrar a esa sección real.
// ---------------------------------------------------------------------------
export default function AyudaPage() {
  const { t } = useTranslation();
  const { user: me, loading } = useCurrentUser();

  const hasPerm = (p: string) => hasPermission(me, p);

  const showAnalytics  = hasPerm("analytics.view");
  const showIA         = hasPerm("ai.use");
  const showPrecios    = hasPerm("precios.search");
  const showCenefas    = hasPerm("cenefas.view");
  const showConexiones = hasPerm("connections.view");
  const showRoles      = hasPerm("platform.users.view");

  const dashboardMetrics = [
    { label: "Spend", desc: t("ayuda.dashboard.metrics.spend") },
    { label: "CTR",   desc: t("ayuda.dashboard.metrics.ctr") },
    { label: "CPM",   desc: t("ayuda.dashboard.metrics.cpm") },
    { label: "ROAS",  desc: t("ayuda.dashboard.metrics.roas") },
    { label: "CPC",   desc: t("ayuda.dashboard.metrics.cpc") },
  ];

  const campanasFeatures = [
    { icon: RefreshCw, label: t("ayuda.campanas.features.sync.label"),     desc: t("ayuda.campanas.features.sync.desc") },
    { icon: Download,  label: t("ayuda.campanas.features.export.label"),   desc: t("ayuda.campanas.features.export.desc") },
    { icon: Eye,       label: t("ayuda.campanas.features.filtros.label"),  desc: t("ayuda.campanas.features.filtros.desc") },
    { icon: BarChart2, label: t("ayuda.campanas.features.comparacion.label"), desc: t("ayuda.campanas.features.comparacion.desc") },
  ];

  const conexionesPlataformas = [
    { name: "Google Ads", color: "#4285F4", req: t("ayuda.conexiones.googleAds") },
    { name: "TikTok Ads", color: "#FF0050", req: t("ayuda.conexiones.tiktokAds") },
    { name: "DV360",      color: "#34A853", req: t("ayuda.conexiones.dv360") },
  ];

  const cenefasFormats = [
    { label: "A4",      desc: t("ayuda.cenefas.formats.a4.desc"),      sub: t("ayuda.cenefas.formats.a4.sub") },
    { label: "A3",      desc: t("ayuda.cenefas.formats.a3.desc"),      sub: t("ayuda.cenefas.formats.a3.sub") },
    { label: "3×A4",    desc: t("ayuda.cenefas.formats.tresXa4.desc"), sub: t("ayuda.cenefas.formats.tresXa4.sub") },
    { label: "Pinchos", desc: t("ayuda.cenefas.formats.pinchos.desc"), sub: t("ayuda.cenefas.formats.pinchos.sub") },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={22} className="animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto py-6 space-y-10">

      {/* ── Hero ── */}
      <div className="flex flex-col items-center text-center gap-3 py-4">
        <div className="relative">
          <RobotMascot size={110} />
          <span className="absolute -bottom-1 -right-1 w-5 h-5 bg-emerald-500 rounded-full border-2 border-white" />
        </div>
        <div>
          <p className="text-xs font-semibold text-brand-500 uppercase tracking-widest mb-1">{t("sidebar.guiaUso")}</p>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">{t("ayuda.title")}</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-lg">
            {t("ayuda.subtitle")}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap justify-center mt-1">
          {showAnalytics  && <Chip icon={BarChart2}    label={t("ayuda.chips.analytics")}    color="bg-blue-50 text-blue-600" />}
          {showIA         && <Chip icon={Brain}        label={t("ayuda.chips.ia")}           color="bg-purple-50 text-purple-600" />}
          {showCenefas    && <Chip icon={Presentation} label={t("ayuda.chips.cenefas")}      color="bg-emerald-50 text-emerald-600" />}
          {showPrecios    && <Chip icon={Tag}          label={t("ayuda.chips.precios")}      color="bg-cyan-50 text-cyan-600" />}
          <Chip icon={ClipboardList} label={t("ayuda.chips.pedidos")}   color="bg-orange-50 text-orange-600" />
          <Chip icon={MessageCircle} label={t("ayuda.chips.asistente")} color="bg-amber-50 text-amber-600" />
        </div>
      </div>

      {/* ── Dashboard ── */}
      {showAnalytics && (
      <section>
        <SectionTitle icon={LayoutDashboard} title={t("common.dashboard")} />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="md:col-span-2">
            <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-3">
              {t("ayuda.dashboard.introPre")} <strong>{t("common.dashboard")}</strong> {t("ayuda.dashboard.introPost")}
            </p>
            <ul className="space-y-2 text-xs text-slate-600">
              <li className="flex items-start gap-2 text-slate-600 dark:text-slate-400"><CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />{t("ayuda.dashboard.bullet1")}</li>
              <li className="flex items-start gap-2 text-slate-600 dark:text-slate-400"><CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />{t("ayuda.dashboard.bullet2")}</li>
              <li className="flex items-start gap-2 text-slate-600 dark:text-slate-400"><CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />{t("ayuda.dashboard.bullet3")}</li>
            </ul>
          </Card>
          <Card>
            <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3">{t("ayuda.dashboard.metricsTitle")}</p>
            <div className="space-y-2">
              {dashboardMetrics.map(({ label, desc }) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800 dark:text-slate-200">{label}</span>
                  <span className="text-xs text-slate-400 dark:text-slate-500">{desc}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </section>
      )}

      {/* ── Campañas ── */}
      {showAnalytics && (
      <section>
        <SectionTitle icon={Megaphone} title={t("common.campaigns")} />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            {t("ayuda.campanas.intro")}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {campanasFeatures.map(({ icon: Icon, label, desc }) => (
              <div key={label} className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3 text-center">
                <Icon size={16} className="text-brand-600 mx-auto mb-1.5" />
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{label}</p>
                <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">{desc}</p>
              </div>
            ))}
          </div>
        </Card>
      </section>
      )}

      {/* ── Análisis IA ── */}
      {showIA && (
      <section>
        <SectionTitle icon={Brain} title={t("ayuda.analisisIA.title")} color="text-purple-600" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-3">
            {t("ayuda.analisisIA.introPre")} <strong>Doña Tina</strong> {t("ayuda.analisisIA.introPost")}
          </p>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <span className="w-6 h-6 rounded-full bg-purple-100 text-purple-700 font-bold flex items-center justify-center text-[10px]">C</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">Claude</strong> — {t("ayuda.analisisIA.claude")}</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 font-bold flex items-center justify-center text-[10px]">G</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">ChatGPT</strong> — {t("ayuda.analisisIA.chatgpt")}</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-6 h-6 rounded-full bg-orange-100 text-orange-700 font-bold flex items-center justify-center text-[10px]">L</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">Llama</strong> — {t("ayuda.analisisIA.llama")}</span>
            </div>
          </div>
        </Card>
      </section>
      )}

      {/* ── Buscador de precios ── */}
      {showPrecios && (
      <section>
        <SectionTitle icon={Tag} title={t("sidebar.buscarPrecios")} color="text-cyan-600" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            {t("ayuda.precios.introPre")} <strong>{t("ayuda.precios.introBold")}</strong> {t("ayuda.precios.introPost")}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <SlidersHorizontal size={12} className="text-cyan-600" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">{t("ayuda.precios.filtros.title")}</p>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                {t("ayuda.precios.filtros.desc")}
              </p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <LineChart size={12} className="text-cyan-600" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">{t("ayuda.precios.grafico.title")}</p>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                {t("ayuda.precios.grafico.desc")}
              </p>
            </div>
          </div>
          <div className="bg-brand-50 dark:bg-brand-950/30 rounded-xl p-3 flex gap-2">
            <MessageCircle size={14} className="text-brand-500 shrink-0 mt-0.5" />
            <p className="text-xs text-brand-700 dark:text-brand-400">
              {t("ayuda.precios.donTinoPre")} <strong>Don Tino</strong> {t("ayuda.precios.donTinoPost")}
            </p>
          </div>
        </Card>
      </section>
      )}

      {/* ── Generar Cenefas ── */}
      {showCenefas && (
      <section>
        <SectionTitle icon={Presentation} title={t("sidebar.cenefas")} color="text-emerald-600" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-5">
            {t("ayuda.cenefas.intro")}
          </p>
          <div className="space-y-4 mb-5">
            <Step n={1} title={t("ayuda.cenefas.steps.destino.title")}       description={t("ayuda.cenefas.steps.destino.desc")} />
            <Step n={2} title={t("ayuda.cenefas.steps.excel.title")}         description={t("ayuda.cenefas.steps.excel.desc")} />
            <Step n={3} title={t("ayuda.cenefas.steps.preview.title")}       description={t("ayuda.cenefas.steps.preview.desc")} />
            <Step n={4} title={t("ayuda.cenefas.steps.confirmar.title")}     description={t("ayuda.cenefas.steps.confirmar.desc")} />
          </div>
          <div className="bg-amber-50 border border-amber-100 rounded-xl p-3 flex gap-2">
            <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700">
              {t("ayuda.cenefas.warningPre")} <strong>{t("ayuda.cenefas.warningBold")}</strong> {t("ayuda.cenefas.warningPost")}
            </p>
          </div>
        </Card>

        {/* Formatos disponibles */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          {cenefasFormats.map(({ label, desc, sub }) => (
            <Card key={label} className="text-center py-4">
              <p className="text-base font-bold text-brand-600 mb-1">{label}</p>
              <p className="text-[10px] text-slate-500">{desc}</p>
              <p className="text-[10px] text-slate-400">{sub}</p>
            </Card>
          ))}
        </div>
      </section>
      )}

      {/* ── Editor de Plantillas ── */}
      {showCenefas && (
      <section>
        <SectionTitle icon={Layers} title={t("ayuda.editorPlantillas.title")} color="text-indigo-600" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <Card>
            <div className="flex items-center gap-2 mb-2">
              <Eye size={14} className="text-indigo-500" />
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{t("ayuda.editorPlantillas.canvas.title")}</p>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              {t("ayuda.editorPlantillas.canvas.desc")}
            </p>
          </Card>
          <Card>
            <div className="flex items-center gap-2 mb-2">
              <GitBranch size={14} className="text-indigo-500" />
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{t("ayuda.editorPlantillas.reglas.title")}</p>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              {t("ayuda.editorPlantillas.reglas.desc")}
            </p>
          </Card>
          <Card>
            <div className="flex items-center gap-2 mb-2">
              <Variable size={14} className="text-indigo-500" />
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{t("ayuda.editorPlantillas.variables.title")}</p>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              {t("ayuda.editorPlantillas.variables.desc")}
            </p>
          </Card>
        </div>
        <Card>
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3">{t("ayuda.editorPlantillas.startTitle")}</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-brand-50 rounded-xl p-3">
              <p className="text-xs font-semibold text-brand-700 mb-1">{t("ayuda.editorPlantillas.predeterminada.title")}</p>
              <p className="text-[11px] text-brand-600">{t("ayuda.editorPlantillas.predeterminada.desc")}</p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Upload size={11} className="text-slate-500" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">{t("ayuda.editorPlantillas.importar.title")}</p>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                {t("ayuda.editorPlantillas.importar.descPre")} <code className="bg-white dark:bg-slate-900 px-1 rounded text-[10px]">&lt;&lt;PRECIO&gt;&gt;</code> {t("ayuda.editorPlantillas.importar.descPost")}
              </p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Layers size={11} className="text-slate-500" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">{t("ayuda.editorPlantillas.desdeCero.title")}</p>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">{t("ayuda.editorPlantillas.desdeCero.desc")}</p>
            </div>
          </div>
        </Card>
      </section>
      )}

      {/* ── Conexiones ── */}
      {showConexiones && (
      <section>
        <SectionTitle icon={Settings} title={t("ayuda.conexiones.title")} />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            {t("ayuda.conexiones.introPre")} <strong>{t("sidebar.configuracion")} → {t("common.connections")}</strong> {t("ayuda.conexiones.introPost")}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {conexionesPlataformas.map(({ name, color, req }) => (
              <div key={name} className="rounded-xl border border-slate-100 dark:border-slate-800 p-3">
                <div className="w-6 h-6 rounded-md mb-2 flex items-center justify-center text-white text-[10px] font-bold"
                  style={{ backgroundColor: color }}>
                  {name[0]}
                </div>
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{name}</p>
                <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">{req}</p>
              </div>
            ))}
          </div>
        </Card>
      </section>
      )}

      {/* ── Historial ── */}
      {showCenefas && (
      <section>
        <SectionTitle icon={Clock} title={t("sidebar.historial")} />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-3">
            {t("ayuda.historial.introPre")} <strong>{t("sidebar.herramientas")} → {t("sidebar.historial")}</strong> {t("ayuda.historial.introPost")}
          </p>
          <div className="flex gap-3 flex-wrap">
            <Chip icon={CheckCircle2} label={t("ayuda.historial.status.done")}    color="bg-emerald-50 text-emerald-700" />
            <Chip icon={RefreshCw}    label={t("ayuda.historial.status.running")} color="bg-blue-50 text-blue-700" />
            <Chip icon={AlertTriangle}label={t("ayuda.historial.status.error")}   color="bg-red-50 text-red-700" />
            <Chip icon={Clock}        label={t("ayuda.historial.status.pending")} color="bg-amber-50 text-amber-700" />
          </div>
        </Card>
      </section>
      )}

      {/* ── Planilla de pedidos (Redexpres) — siempre visible, no depende de ningún permiso ── */}
      <section>
        <SectionTitle icon={ClipboardList} title={t("ayuda.pedidos.title")} color="text-orange-600" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            {t("ayuda.pedidos.intro")}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">{t("ayuda.pedidos.tuLocal.title")}</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                {t("ayuda.pedidos.tuLocal.desc")}
              </p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">{t("ayuda.pedidos.confirmar.title")}</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                {t("ayuda.pedidos.confirmar.desc")}
              </p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">{t("ayuda.pedidos.nuevoMes.title")}</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                {t("ayuda.pedidos.nuevoMes.desc")}
              </p>
            </div>
          </div>
        </Card>
      </section>

      {/* ── Asistente — siempre visible, no depende de ningún permiso especial ── */}
      <section>
        <SectionTitle icon={MessageCircle} title={t("ayuda.asistente.title")} color="text-amber-600" />
        <Card>
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-2xl bg-brand-500/10 flex items-center justify-center shrink-0">
              <RobotMini variant="tina" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-1">{t("ayuda.asistente.greeting")}</p>
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed mb-3">
                <strong className="text-slate-800 dark:text-slate-200">Doña Tina</strong> {t("ayuda.asistente.introPost")}
              </p>
              <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-400 mb-3">
                <li className="flex items-start gap-2"><Tag size={12} className="text-cyan-500 mt-0.5 shrink-0" />{t("ayuda.asistente.feature1")}</li>
                <li className="flex items-start gap-2"><Clock size={12} className="text-blue-500 mt-0.5 shrink-0" />{t("ayuda.asistente.feature2")}</li>
                <li className="flex items-start gap-2"><Brain size={12} className="text-purple-500 mt-0.5 shrink-0" />{t("ayuda.asistente.feature3")}</li>
              </ul>
              <p className="text-xs text-slate-400 dark:text-slate-500">
                {t("ayuda.asistente.footer")}
              </p>
            </div>
          </div>
        </Card>
      </section>

      {/* ── Roles y permisos ── */}
      {showRoles && (
      <section>
        <SectionTitle icon={Users} title={t("ayuda.roles.title")} />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            {t("ayuda.roles.introPre")} <strong>{t("ayuda.roles.introBold")}</strong> {t("ayuda.roles.introMid")}{" "}
            <Link href="/admin" className="text-brand-600 hover:underline">{t("sidebar.administrador")}</Link>.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-rose-50 dark:bg-rose-950/30 rounded-xl p-3">
              <p className="text-xs font-semibold text-rose-700 dark:text-rose-400 mb-1">{t("ayuda.roles.superAdmin.title")}</p>
              <p className="text-[11px] text-rose-600 dark:text-rose-400/80 leading-relaxed">
                {t("ayuda.roles.superAdmin.desc")}
              </p>
            </div>
            <div className="bg-brand-50 dark:bg-brand-950/30 rounded-xl p-3">
              <p className="text-xs font-semibold text-brand-700 dark:text-brand-400 mb-1">{t("ayuda.roles.admin.title")}</p>
              <p className="text-[11px] text-brand-600 dark:text-brand-400/80 leading-relaxed">
                {t("ayuda.roles.admin.desc")}
              </p>
            </div>
            <div className="bg-amber-50 dark:bg-amber-950/30 rounded-xl p-3">
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-1">{t("ayuda.roles.usuario.title")}</p>
              <p className="text-[11px] text-amber-600 dark:text-amber-400/80 leading-relaxed">
                {t("ayuda.roles.usuario.desc")}
              </p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">{t("ayuda.roles.viewer.title")}</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                {t("ayuda.roles.viewer.desc")}
              </p>
            </div>
          </div>
        </Card>
      </section>
      )}

      <div className="pb-4" />
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  LayoutDashboard, Megaphone, Brain, Presentation, Layers,
  Settings, MessageCircle, BarChart2, Upload,
  Download, Eye, GitBranch, Variable, Users, RefreshCw,
  CheckCircle2, AlertTriangle, Clock, ChevronRight, Tag, SlidersHorizontal, LineChart,
  Loader2,
} from "lucide-react";
import { RobotMascot, RobotMini } from "@/components/RobotMascot";
import { authApi } from "@/lib/api";
import type { CurrentUser } from "@/types";

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
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authApi.me()
      .then(({ data }) => setMe(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const perms = me?.permissions ?? [];
  const hasPerm = (p: string) => !!me?.is_superuser || perms.includes(p);

  const showAnalytics  = hasPerm("analytics.view");
  const showIA         = hasPerm("ai.use");
  const showPrecios    = hasPerm("precios.search");
  const showCenefas    = hasPerm("cenefas.view");
  const showConexiones = hasPerm("connections.view");
  const showRoles      = hasPerm("platform.users.view");
  const showCtaButtons = showConexiones || showPrecios || showCenefas;

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
          <p className="text-xs font-semibold text-brand-500 uppercase tracking-widest mb-1">Guía de uso</p>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">¿Cómo funciona la plataforma?</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-lg">
            Todo lo que necesitás saber para usar MKTG Platform, según lo que tu cuenta puede ver y hacer.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap justify-center mt-1">
          {showAnalytics  && <Chip icon={BarChart2}    label="Analytics"    color="bg-blue-50 text-blue-600" />}
          {showIA         && <Chip icon={Brain}        label="IA integrada" color="bg-purple-50 text-purple-600" />}
          {showCenefas    && <Chip icon={Presentation} label="Cenefas"      color="bg-emerald-50 text-emerald-600" />}
          {showPrecios    && <Chip icon={Tag}          label="Precios"      color="bg-cyan-50 text-cyan-600" />}
          <Chip icon={MessageCircle} label="Asistente" color="bg-amber-50 text-amber-600" />
        </div>
      </div>

      {/* ── Dashboard ── */}
      {showAnalytics && (
      <section>
        <SectionTitle icon={LayoutDashboard} title="Dashboard" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="md:col-span-2">
            <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-3">
              El <strong>Dashboard</strong> muestra el resumen de rendimiento de todas tus plataformas publicitarias conectadas
              en un solo lugar: gasto total, impresiones, clics, conversiones y ROAS.
            </p>
            <ul className="space-y-2 text-xs text-slate-600">
              <li className="flex items-start gap-2 text-slate-600 dark:text-slate-400"><CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />Filtrá por rango de fechas y plataforma</li>
              <li className="flex items-start gap-2 text-slate-600 dark:text-slate-400"><CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />Alerta automáticamente si una campaña cae más de 30% vs el período anterior</li>
              <li className="flex items-start gap-2 text-slate-600 dark:text-slate-400"><CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />Tendencias y variaciones respecto al período anterior</li>
            </ul>
          </Card>
          <Card>
            <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3">Métricas clave</p>
            <div className="space-y-2">
              {[
                { label: "Spend", desc: "Inversión total" },
                { label: "CTR",   desc: "Tasa de clics" },
                { label: "CPM",   desc: "Costo por mil impresiones" },
                { label: "ROAS",  desc: "Retorno sobre inversión" },
                { label: "CPC",   desc: "Costo por clic" },
              ].map(({ label, desc }) => (
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
        <SectionTitle icon={Megaphone} title="Campañas" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            Tabla detallada de todas las campañas de todas las plataformas. Podés ordenar, filtrar y exportar los datos.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { icon: RefreshCw,       label: "Sync manual",  desc: "Actualizá métricas al instante" },
              { icon: Download,        label: "Exportar CSV", desc: "Descargá el reporte completo" },
              { icon: Eye,             label: "Filtros",      desc: "Por plataforma, fecha, campaña" },
              { icon: BarChart2,       label: "Comparación",  desc: "Período actual vs anterior" },
            ].map(({ icon: Icon, label, desc }) => (
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
        <SectionTitle icon={Brain} title="Análisis IA — La Triada" color="text-purple-600" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-3">
            Elegís plataformas y rango de fechas: tres modelos debaten tus métricas reales desde
            perspectivas distintas, en una conversación que podés seguir pregunta a pregunta.
            Cada debate queda guardado — podés retomarlo más tarde o pedirle a <strong>Don Tino</strong> que
            te lo resuma directo en el chat de Home.
          </p>
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <span className="w-6 h-6 rounded-full bg-purple-100 text-purple-700 font-bold flex items-center justify-center text-[10px]">C</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">Claude</strong> — analista cuantitativo, foco estadístico</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 font-bold flex items-center justify-center text-[10px]">G</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">ChatGPT</strong> — estratega creativo, con búsqueda web para contexto local</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-6 h-6 rounded-full bg-orange-100 text-orange-700 font-bold flex items-center justify-center text-[10px]">L</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">Llama</strong> — moderador pragmático, síntesis y plan de acción</span>
            </div>
          </div>
        </Card>
      </section>
      )}

      {/* ── Buscador de precios ── */}
      {showPrecios && (
      <section>
        <SectionTitle icon={Tag} title="Buscador de precios" color="text-cyan-600" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            Compará precios <strong>en vivo</strong> (se busca en el momento, no hay base propia) en{" "}
            <strong>13 cadenas uruguayas</strong>: supermercados (Disco, Devoto, Géant, Ta-Ta, El Dorado),
            farmacias (FarmaShop, Botiga) y electrodomésticos/electrónica (Fama, Stienda, Black Dog,
            Cover Company, DIMM, Electrohogar). Los precios de electrodomésticos suelen venir en dólares —
            cada resultado muestra su moneda real, no se convierte automáticamente.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <SlidersHorizontal size={12} className="text-cyan-600" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Filtros que se suman</p>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                Los chips de cadena se van sumando al tocarlos (multi-selección) — solo el chip "Todas" los apaga a todos de una.
              </p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <LineChart size={12} className="text-cyan-600" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Gráfico comparativo</p>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                Botón "Ver gráfico": elegís qué productos entran con un checklist buscable, y podés cargar tu propio precio para verte posicionado contra la competencia.
              </p>
            </div>
          </div>
          <div className="bg-brand-50 dark:bg-brand-950/30 rounded-xl p-3 flex gap-2">
            <MessageCircle size={14} className="text-brand-500 shrink-0 mt-0.5" />
            <p className="text-xs text-brand-700 dark:text-brand-400">
              También podés pedirle el precio de un producto directo a <strong>Don Tino</strong> en el chat de Home, sin ir a esta pantalla.
            </p>
          </div>
        </Card>
      </section>
      )}

      {/* ── Generar Cenefas ── */}
      {showCenefas && (
      <section>
        <SectionTitle icon={Presentation} title="Generar Cenefas" color="text-emerald-600" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-5">
            Convertí un Excel con productos en una presentación PowerPoint lista para imprimir.
            El sistema genera automáticamente las láminas con precios, descripciones y promociones formateadas.
          </p>
          <div className="space-y-4 mb-5">
            <Step n={1} title="Elegir template y formato"
              description="Seleccionás la plantilla (A4, Pinchos, 3xA4 o un template personalizado) y el formato de salida." />
            <Step n={2} title="Subir el Excel"
              description="Cargás el archivo con los productos. Las columnas detectadas automáticamente incluyen DESCRIPCION, PRECIO, OFERTA, CATEGORIA, etc." />
            <Step n={3} title="Validar (solo templates v2)"
              description="El sistema revisa errores: precios en cero, descripciones vacías o muy largas, campos requeridos faltantes." />
            <Step n={4} title="Generar y descargar"
              description="Se genera el PPTX en segundos. Podés descargar el resultado desde la misma pantalla o desde el Historial." />
          </div>
          <div className="bg-amber-50 border border-amber-100 rounded-xl p-3 flex gap-2">
            <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700">
              Los archivos generados se guardan por <strong>24 horas</strong>. Descargalos antes de que venzan.
            </p>
          </div>
        </Card>

        {/* Formatos disponibles */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          {[
            { label: "A4",      desc: "21 × 29.7 cm · 1 slot",    sub: "1 producto por slide" },
            { label: "A3",      desc: "29.7 × 42 cm",             sub: "Formato grande" },
            { label: "3×A4",    desc: "3 franjas verticales",      sub: "3 productos por slide" },
            { label: "Pinchos", desc: "7 × 14.85 cm · grid 3×2",  sub: "6 por slide" },
          ].map(({ label, desc, sub }) => (
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
        <SectionTitle icon={Layers} title="Editor de Plantillas" color="text-indigo-600" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <Card>
            <div className="flex items-center gap-2 mb-2">
              <Eye size={14} className="text-indigo-500" />
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">Canvas visual</p>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Editor WYSIWYG basado en Konva.js. Ves en tiempo real cómo se verá cada componente en el formato elegido.
            </p>
          </Card>
          <Card>
            <div className="flex items-center gap-2 mb-2">
              <GitBranch size={14} className="text-indigo-500" />
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">Reglas de visibilidad</p>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Definís cuándo aparece cada componente según los datos del producto. Condiciones AND/OR/NOT con múltiples operadores.
            </p>
          </Card>
          <Card>
            <div className="flex items-center gap-2 mb-2">
              <Variable size={14} className="text-indigo-500" />
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">Variables</p>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Mapeás cada campo del Excel a un componente del template: precio, descripción, mecánica, combo, etc.
            </p>
          </Card>
        </div>
        <Card>
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3">Formas de empezar un template</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-brand-50 rounded-xl p-3">
              <p className="text-xs font-semibold text-brand-700 mb-1">Plantilla predeterminada</p>
              <p className="text-[11px] text-brand-600">Cenefa A4, Pinchos o 3xA4 ya configurados y listos para usar.</p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Upload size={11} className="text-slate-500" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Importar PPTX</p>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">Subís tu propio .pptx y los placeholders <code className="bg-white dark:bg-slate-900 px-1 rounded text-[10px]">&lt;&lt;PRECIO&gt;&gt;</code> se detectan automáticamente.</p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Layers size={11} className="text-slate-500" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">Desde cero</p>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">Creás cada componente manualmente, definís bounds, estilos y transforms.</p>
            </div>
          </div>
        </Card>
      </section>
      )}

      {/* ── Conexiones ── */}
      {showConexiones && (
      <section>
        <SectionTitle icon={Settings} title="Conexiones de plataformas" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            Desde <strong>Configuración → Conexiones</strong> conectás cada cuenta publicitaria.
            Los tokens se guardan cifrados. Una vez conectados, la sincronización es automática.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              // { name: "Meta Ads", color: "#1877F2", req: "Access Token + Account ID" }, // pausado — ver settings/page.tsx
              { name: "Google Ads", color: "#4285F4", req: "OAuth 2.0 (refresh token)" },
              { name: "TikTok Ads", color: "#FF0050", req: "Access Token + Advertiser ID" },
              { name: "DV360",      color: "#34A853", req: "Service Account JSON" },
            ].map(({ name, color, req }) => (
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
        <SectionTitle icon={Clock} title="Historial de generaciones" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-3">
            En <strong>Herramientas → Historial</strong> encontrás todos los trabajos de generación de cenefas:
            estado, formato usado, fecha y el botón de descarga (disponible por 24 hs desde la generación).
          </p>
          <div className="flex gap-3 flex-wrap">
            <Chip icon={CheckCircle2} label="done — listo para descargar"   color="bg-emerald-50 text-emerald-700" />
            <Chip icon={RefreshCw}    label="running — en proceso"          color="bg-blue-50 text-blue-700" />
            <Chip icon={AlertTriangle}label="error — revisar validación"    color="bg-red-50 text-red-700" />
            <Chip icon={Clock}        label="pending — en cola"             color="bg-amber-50 text-amber-700" />
          </div>
        </Card>
      </section>
      )}

      {/* ── Asistente — siempre visible, no depende de ningún permiso especial ── */}
      <section>
        <SectionTitle icon={MessageCircle} title="Asistente virtual" color="text-amber-600" />
        <Card>
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-2xl bg-brand-500/10 flex items-center justify-center shrink-0">
              <RobotMini />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-1">¿En qué te ayudo?</p>
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed mb-3">
                <strong className="text-slate-800 dark:text-slate-200">Don Tino</strong> (Llama 3.3 70B via Groq) conoce todas las funcionalidades de la plataforma
                y además puede hacer cosas por vos, no solo describirlas:
              </p>
              <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-400 mb-3">
                <li className="flex items-start gap-2"><Tag size={12} className="text-cyan-500 mt-0.5 shrink-0" />Buscarte el precio de un producto en las 13 cadenas, en vivo</li>
                <li className="flex items-start gap-2"><Clock size={12} className="text-blue-500 mt-0.5 shrink-0" />Consultarte el estado de un trabajo de cenefas por su ID</li>
                <li className="flex items-start gap-2"><Brain size={12} className="text-purple-500 mt-0.5 shrink-0" />Resumirte tu último debate de La Triada</li>
              </ul>
              <p className="text-xs text-slate-400 dark:text-slate-500">
                Disponible desde el Home — abrí la tarjeta de chat debajo del saludo de Don Tino.
              </p>
            </div>
          </div>
        </Card>
      </section>

      {/* ── Roles y permisos ── */}
      {showRoles && (
      <section>
        <SectionTitle icon={Users} title="Roles y permisos" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            No hay equipos ni organizaciones separadas: todos los usuarios comparten la misma plataforma.
            Los permisos viven <strong>por usuario</strong>, no por rol — el rol solo define el punto de
            partida al asignarlo; después cada permiso se prende o apaga individualmente desde el perfil
            de esa persona en el <Link href="/admin" className="text-brand-600 hover:underline">Panel de Admin</Link>.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-rose-50 dark:bg-rose-950/30 rounded-xl p-3">
              <p className="text-xs font-semibold text-rose-700 dark:text-rose-400 mb-1">Super Admin</p>
              <p className="text-[11px] text-rose-600 dark:text-rose-400/80 leading-relaxed">
                Acceso total sin restricciones. Reservado para la cuenta principal — no se asigna desde el panel.
              </p>
            </div>
            <div className="bg-brand-50 dark:bg-brand-950/30 rounded-xl p-3">
              <p className="text-xs font-semibold text-brand-700 dark:text-brand-400 mb-1">Admin</p>
              <p className="text-[11px] text-brand-600 dark:text-brand-400/80 leading-relaxed">
                Arranca con todos los permisos tildados; se pueden destildar puntualmente por usuario.
                No puede modificar a otro Admin ni al Super Admin.
              </p>
            </div>
            <div className="bg-amber-50 dark:bg-amber-950/30 rounded-xl p-3">
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-1">Usuario</p>
              <p className="text-[11px] text-amber-600 dark:text-amber-400/80 leading-relaxed">
                Arranca con un set operativo estándar (cenefas, analytics, precios e IA completos,
                sin gestión de usuarios ni de conexiones) — se puede ajustar por persona.
              </p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Viewer</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                Arranca sin permisos y solo puede tener tildados permisos de "ver" — nunca uno de
                generar, editar, eliminar o gestionar.
              </p>
            </div>
          </div>
        </Card>
      </section>
      )}

      {/* ── CTA ── */}
      <div className="bg-gradient-to-br from-brand-600 to-indigo-700 rounded-2xl p-6 text-center text-white">
        <p className="text-lg font-bold mb-1">¿Todo claro?</p>
        <p className="text-sm text-white/70 mb-4">
          {showCtaButtons ? "Empezá por acá:" : "Cualquier duda, preguntale a Don Tino desde el Home."}
        </p>
        {showCtaButtons && (
          <div className="flex gap-3 justify-center flex-wrap">
            {showConexiones && (
              <Link href="/settings"
                className="flex items-center gap-1.5 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-xl text-sm font-medium transition-colors">
                <Settings size={14} /> Conectar plataformas
              </Link>
            )}
            {showPrecios && (
              <Link href="/precios"
                className="flex items-center gap-1.5 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-xl text-sm font-medium transition-colors">
                <Tag size={14} /> Buscar precios
              </Link>
            )}
            {showCenefas && (
              <Link href="/herramientas/cenefas"
                className="flex items-center gap-1.5 px-4 py-2 bg-white text-brand-700 hover:bg-white/90 rounded-xl text-sm font-medium transition-colors">
                <Presentation size={14} /> Generar cenefas <ChevronRight size={14} />
              </Link>
            )}
          </div>
        )}
      </div>

      <div className="pb-4" />
    </div>
  );
}

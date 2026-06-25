"use client";
import Link from "next/link";
import {
  LayoutDashboard, Megaphone, Brain, Presentation, Layers,
  Settings, MessageCircle, BarChart2, Upload, FileSpreadsheet,
  Download, Eye, GitBranch, Variable, Zap, Users, RefreshCw,
  CheckCircle2, AlertTriangle, Clock, ChevronRight,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Robot mascot (same as home page)
// ---------------------------------------------------------------------------
function RobotMascot() {
  return (
    <>
      <style>{`
        @keyframes robot-float  { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)} }
        @keyframes robot-shadow { 0%,100%{transform:scaleX(1);opacity:.15} 50%{transform:scaleX(.7);opacity:.07} }
        @keyframes robot-blink  { 0%,88%,100%{transform:scaleY(1)} 92%{transform:scaleY(.08)} }
        @keyframes antenna-pulse{ 0%,100%{opacity:1;r:3} 50%{opacity:.4;r:4.5} }
        @keyframes light-1 { 0%,100%{opacity:1} 20%,60%{opacity:.2} }
        @keyframes light-2 { 0%,100%{opacity:.2} 40%{opacity:1} }
        @keyframes light-3 { 0%,100%{opacity:.2} 70%{opacity:1} }
        @keyframes arm-wave {
          0%,100%{transform:rotate(0deg);transform-origin:20px 40px}
          25%{transform:rotate(-18deg);transform-origin:20px 40px}
          75%{transform:rotate(10deg);transform-origin:20px 40px}
        }
        .rb-body{animation:robot-float 2.8s ease-in-out infinite}
        .rb-shadow{animation:robot-shadow 2.8s ease-in-out infinite}
        .rb-eye-l{animation:robot-blink 3.5s ease-in-out infinite;transform-origin:32px 24px}
        .rb-eye-r{animation:robot-blink 3.5s ease-in-out infinite;transform-origin:48px 24px;animation-delay:.05s}
        .rb-ant{animation:antenna-pulse 1.4s ease-in-out infinite}
        .rb-l1{animation:light-1 1.8s ease-in-out infinite}
        .rb-l2{animation:light-2 1.8s ease-in-out infinite}
        .rb-l3{animation:light-3 1.8s ease-in-out infinite}
        .rb-arm{animation:arm-wave 2.8s ease-in-out infinite}
      `}</style>
      <svg width="110" height="110" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
        <ellipse className="rb-shadow" cx="40" cy="76" rx="22" ry="4" fill="#6366f1" />
        <g className="rb-body">
          <rect x="22" y="38" width="36" height="26" rx="8" fill="#4f46e5" />
          <rect x="29" y="44" width="22" height="13" rx="4" fill="#4338ca" />
          <circle className="rb-l1" cx="34" cy="50" r="2.5" fill="#a5f3fc" />
          <circle className="rb-l2" cx="40" cy="50" r="2.5" fill="#6ee7b7" />
          <circle className="rb-l3" cx="46" cy="50" r="2.5" fill="#fca5a5" />
          <g className="rb-arm">
            <rect x="10" y="40" width="10" height="18" rx="5" fill="#4f46e5" />
            <circle cx="15" cy="60" r="5" fill="#6366f1" />
          </g>
          <rect x="60" y="40" width="10" height="18" rx="5" fill="#4f46e5" />
          <circle cx="65" cy="60" r="5" fill="#6366f1" />
          <rect x="35" y="32" width="10" height="8" rx="3" fill="#6366f1" />
          <rect x="18" y="10" width="44" height="30" rx="12" fill="#6366f1" />
          <rect x="26" y="19" width="12" height="10" rx="5" fill="white" />
          <rect x="42" y="19" width="12" height="10" rx="5" fill="white" />
          <circle className="rb-eye-l" cx="32" cy="24" r="4" fill="#1e1b4b" />
          <circle className="rb-eye-r" cx="48" cy="24" r="4" fill="#1e1b4b" />
          <circle cx="33" cy="22" r="1.5" fill="white" />
          <circle cx="49" cy="22" r="1.5" fill="white" />
          <path d="M30 33 Q40 39 50 33" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
          <line x1="40" y1="10" x2="40" y2="3" stroke="#818cf8" strokeWidth="2.5" strokeLinecap="round" />
          <circle className="rb-ant" cx="40" cy="2" r="3" fill="#a5b4fc" />
        </g>
      </svg>
    </>
  );
}

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
// Page
// ---------------------------------------------------------------------------
export default function AyudaPage() {
  return (
    <div className="max-w-4xl mx-auto py-6 space-y-10">

      {/* ── Hero ── */}
      <div className="flex flex-col items-center text-center gap-3 py-4">
        <div className="relative">
          <RobotMascot />
          <span className="absolute -bottom-1 -right-1 w-5 h-5 bg-emerald-500 rounded-full border-2 border-white" />
        </div>
        <div>
          <p className="text-xs font-semibold text-brand-500 uppercase tracking-widest mb-1">Guía de uso</p>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">¿Cómo funciona la plataforma?</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-2 max-w-lg">
            Todo lo que necesitás saber para usar MKTG Platform: métricas, análisis IA, generación de cenefas y más.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap justify-center mt-1">
          <Chip icon={BarChart2}   label="Analytics"        color="bg-blue-50 text-blue-600" />
          <Chip icon={Brain}       label="IA integrada"     color="bg-purple-50 text-purple-600" />
          <Chip icon={Presentation}label="Cenefas"          color="bg-emerald-50 text-emerald-600" />
          <Chip icon={MessageCircle} label="Asistente"      color="bg-amber-50 text-amber-600" />
        </div>
      </div>

      {/* ── Dashboard ── */}
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
              <li className="flex items-start gap-2 text-slate-600 dark:text-slate-400"><CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />Detecta anomalías automáticamente con IA</li>
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

      {/* ── Campañas ── */}
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

      {/* ── Análisis IA ── */}
      <section>
        <SectionTitle icon={Brain} title="Análisis IA" color="text-purple-600" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <p className="text-xs font-semibold text-purple-600 uppercase tracking-wider mb-2">Análisis con Claude</p>
            <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
              Seleccionás plataforma y rango de fechas. Claude (Anthropic) analiza tus métricas y
              genera un reporte con insights, anomalías detectadas y recomendaciones accionables.
            </p>
          </Card>
          <Card>
            <p className="text-xs font-semibold text-amber-600 uppercase tracking-wider mb-2">Modo Debate</p>
            <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-3">
              Tres IAs debaten tus métricas en 3 rondas:
            </p>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <span className="w-6 h-6 rounded-full bg-purple-100 text-purple-700 font-bold flex items-center justify-center text-[10px]">C</span>
                <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">Claude</strong> — analista cuantitativo, foco estadístico</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 font-bold flex items-center justify-center text-[10px]">G</span>
                <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">ChatGPT</strong> — estratega creativo, ideas disruptivas</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="w-6 h-6 rounded-full bg-orange-100 text-orange-700 font-bold flex items-center justify-center text-[10px]">L</span>
                <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-800 dark:text-slate-200">Llama</strong> — moderador pragmático, síntesis final</span>
              </div>
            </div>
          </Card>
        </div>
      </section>

      {/* ── Generar Cenefas ── */}
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

      {/* ── Editor de Plantillas ── */}
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

      {/* ── Conexiones ── */}
      <section>
        <SectionTitle icon={Settings} title="Conexiones de plataformas" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            Desde <strong>Configuración → Conexiones</strong> conectás cada cuenta publicitaria.
            Los tokens se guardan cifrados. Una vez conectados, la sincronización es automática.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { name: "Meta Ads",   color: "#1877F2", req: "Access Token + Account ID" },
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

      {/* ── Historial ── */}
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

      {/* ── Asistente ── */}
      <section>
        <SectionTitle icon={MessageCircle} title="Asistente virtual" color="text-amber-600" />
        <Card>
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-2xl bg-brand-500/10 flex items-center justify-center shrink-0">
              <svg width="20" height="20" viewBox="0 0 80 80" fill="none">
                <rect x="18" y="10" width="44" height="30" rx="12" fill="#6366f1" />
                <rect x="26" y="19" width="12" height="10" rx="5" fill="white" />
                <rect x="42" y="19" width="12" height="10" rx="5" fill="white" />
                <circle cx="32" cy="24" r="4" fill="#1e1b4b" />
                <circle cx="48" cy="24" r="4" fill="#1e1b4b" />
                <path d="M30 33 Q40 39 50 33" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
                <rect x="22" y="38" width="36" height="26" rx="8" fill="#4f46e5" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-1">¿En qué te ayudo?</p>
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                El asistente (Llama 3.3 70B via Groq) conoce todas las funcionalidades de la plataforma.
                Podés preguntarle cómo navegar hacia alguna sección, cómo generar un reporte,
                qué significan las métricas o cualquier duda operativa.
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-2">
                Disponible desde el menú principal → ícono del robot (esquina superior izquierda del dashboard).
              </p>
            </div>
          </div>
        </Card>
      </section>

      {/* ── Equipos ── */}
      <section>
        <SectionTitle icon={Users} title="Equipos y accesos" />
        <Card>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed mb-4">
            La plataforma soporta múltiples equipos dentro de una misma organización. Cada equipo tiene su propio
            código de invitación y tipo de acceso.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-blue-50 rounded-xl p-3">
              <p className="text-xs font-semibold text-blue-700 mb-1">Medios Digitales</p>
              <p className="text-[11px] text-blue-600 leading-relaxed">
                Acceso completo: Dashboard, Campañas, Análisis IA y Herramientas.
              </p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3">
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Otros equipos</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                Acceso restringido a Herramientas (cenefas, editor, historial) sin métricas de plataformas.
              </p>
            </div>
          </div>
        </Card>
      </section>

      {/* ── CTA ── */}
      <div className="bg-gradient-to-br from-brand-600 to-indigo-700 rounded-2xl p-6 text-center text-white">
        <p className="text-lg font-bold mb-1">¿Todo claro?</p>
        <p className="text-sm text-white/70 mb-4">Empezá por conectar tus plataformas o generá tu primera cenefa.</p>
        <div className="flex gap-3 justify-center flex-wrap">
          <Link href="/settings"
            className="flex items-center gap-1.5 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-xl text-sm font-medium transition-colors">
            <Settings size={14} /> Conectar plataformas
          </Link>
          <Link href="/herramientas/cenefas"
            className="flex items-center gap-1.5 px-4 py-2 bg-white text-brand-700 hover:bg-white/90 rounded-xl text-sm font-medium transition-colors">
            <Presentation size={14} /> Generar cenefas <ChevronRight size={14} />
          </Link>
        </div>
      </div>

      <div className="pb-4" />
    </div>
  );
}

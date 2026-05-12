"use client";
import { useEffect, useState } from "react";
import { connectionsApi } from "@/lib/api";
import { Connection, PLATFORM_LABELS } from "@/types";
import { Plus, Trash2, CheckCircle2, XCircle, ChevronDown, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

const PLATFORM_OPTIONS = [
  { value: "meta",       label: "Meta Ads",    color: "#1877F2", initial: "M", desc: "Facebook & Instagram Ads" },
  { value: "google_ads", label: "Google Ads",  color: "#4285F4", initial: "G", desc: "Search, Display & YouTube" },
  { value: "tiktok",     label: "TikTok Ads",  color: "#FF0050", initial: "T", desc: "TikTok for Business" },
  { value: "dv360",      label: "DV360",       color: "#34A853", initial: "D", desc: "Display & Video 360" },
];

const TOKEN_GUIDES: Record<string, { steps: string[]; link: string }> = {
  meta: {
    steps: ["Andá a developers.facebook.com", "Creá una app tipo 'Business'", "En Herramientas → Explorador de API → Generá token con permisos ads_read, read_insights"],
    link: "https://developers.facebook.com/tools/explorer",
  },
  google_ads: {
    steps: ["Andá a Google Cloud Console", "Creá credenciales OAuth 2.0", "Habilitá la Google Ads API", "Obtenés el access token con scope: https://www.googleapis.com/auth/adwords"],
    link: "https://console.cloud.google.com/",
  },
  tiktok: {
    steps: ["Andá a ads.tiktok.com/marketing_api", "Creá una app en el developer portal", "Obtenés el access token desde la sección de autorización"],
    link: "https://ads.tiktok.com/marketing_api/homepage",
  },
  dv360: {
    steps: ["Usá las mismas credenciales OAuth de Google Cloud", "Habilitá la Display & Video 360 API", "El token es el mismo que Google Ads si usás el mismo OAuth scope"],
    link: "https://console.cloud.google.com/",
  },
};

export default function SettingsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [showForm, setShowForm]       = useState(false);
  const [showGuide, setShowGuide]     = useState<string | null>(null);
  const [showTokens, setShowTokens]   = useState<Record<string, boolean>>({});
  const [form, setForm] = useState({
    platform: "meta", account_id: "", account_name: "",
    access_token: "", refresh_token: "",
  });

  async function load() {
    connectionsApi.list().then(({ data }) => setConnections(data)).catch(() => {});
  }
  useEffect(() => { load(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await connectionsApi.create(form);
      toast.success("Conexión guardada correctamente");
      setShowForm(false);
      setForm({ platform: "meta", account_id: "", account_name: "", access_token: "", refresh_token: "" });
      await load();
    } catch {
      toast.error("Error al guardar la conexión");
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("¿Eliminar esta conexión? Se perderán los tokens guardados.")) return;
    try {
      await connectionsApi.delete(id);
      toast.success("Conexión eliminada");
      await load();
    } catch { toast.error("Error al eliminar"); }
  }

  const selectedPlatform = PLATFORM_OPTIONS.find((p) => p.value === form.platform);

  return (
    <div className="animate-fade-in space-y-6 max-w-3xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Conexiones</h1>
          <p className="text-sm text-slate-500 mt-0.5">Conectá tus cuentas de advertising</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary">
          <Plus size={16} />
          Nueva conexión
        </button>
      </div>

      {/* Form */}
      {showForm && (
        <div className="card p-6 animate-slide-up">
          <h2 className="section-title mb-4">Agregar conexión</h2>
          <form onSubmit={handleCreate} className="space-y-4">
            {/* Platform selector */}
            <div>
              <label className="text-sm font-medium text-slate-700 mb-2 block">Plataforma</label>
              <div className="grid grid-cols-2 gap-2">
                {PLATFORM_OPTIONS.map((p) => (
                  <button key={p.value} type="button" onClick={() => setForm({ ...form, platform: p.value })}
                    className={`flex items-center gap-3 p-3 rounded-xl border-2 transition-all ${
                      form.platform === p.value ? "border-brand-500 bg-brand-50/40" : "border-slate-200 hover:border-slate-300"
                    }`}>
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-bold shrink-0"
                      style={{ backgroundColor: p.color }}>
                      {p.initial}
                    </div>
                    <div className="text-left">
                      <p className="text-sm font-semibold text-slate-800">{p.label}</p>
                      <p className="text-xs text-slate-400">{p.desc}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Guide */}
            {selectedPlatform && (
              <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-100">
                <button type="button" onClick={() => setShowGuide(showGuide === form.platform ? null : form.platform)}
                  className="flex items-center justify-between w-full text-left">
                  <span className="text-xs font-semibold text-slate-600">¿Cómo obtengo el token de {selectedPlatform.label}?</span>
                  <ChevronDown size={14} className={`text-slate-400 transition-transform ${showGuide === form.platform ? "rotate-180" : ""}`} />
                </button>
                {showGuide === form.platform && (
                  <div className="mt-3 space-y-1.5">
                    {TOKEN_GUIDES[form.platform]?.steps.map((step, i) => (
                      <p key={i} className="text-xs text-slate-600 flex gap-2">
                        <span className="w-4 h-4 rounded-full bg-brand-100 text-brand-600 font-bold text-[10px] flex items-center justify-center shrink-0 mt-px">
                          {i + 1}
                        </span>
                        {step}
                      </p>
                    ))}
                    <a href={TOKEN_GUIDES[form.platform]?.link} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline mt-2 font-medium">
                      Abrir portal →
                    </a>
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">Account ID *</label>
                <input required value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })}
                  className="input text-sm" placeholder="123456789" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">Nombre de cuenta</label>
                <input value={form.account_name} onChange={(e) => setForm({ ...form, account_name: e.target.value })}
                  className="input text-sm" placeholder="Mi cuenta principal" />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">Access Token *</label>
                <div className="relative">
                  <input required type={showTokens.access ? "text" : "password"} value={form.access_token}
                    onChange={(e) => setForm({ ...form, access_token: e.target.value })}
                    className="input text-sm pr-10 font-mono" placeholder="EAABxxxxxx..." />
                  <button type="button" onClick={() => setShowTokens({ ...showTokens, access: !showTokens.access })}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    {showTokens.access ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">Refresh Token <span className="text-slate-400 font-normal">(opcional)</span></label>
                <div className="relative">
                  <input type={showTokens.refresh ? "text" : "password"} value={form.refresh_token}
                    onChange={(e) => setForm({ ...form, refresh_token: e.target.value })}
                    className="input text-sm pr-10 font-mono" />
                  <button type="button" onClick={() => setShowTokens({ ...showTokens, refresh: !showTokens.refresh })}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    {showTokens.refresh ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
            </div>

            <div className="flex gap-3 pt-1">
              <button type="submit" className="btn-primary">Guardar conexión</button>
              <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancelar</button>
            </div>
          </form>
        </div>
      )}

      {/* Connections list */}
      <div className="space-y-3">
        {connections.length === 0 && !showForm ? (
          <div className="card p-14 flex flex-col items-center text-center">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
              <Plus size={24} className="text-slate-300" />
            </div>
            <p className="text-sm font-medium text-slate-500">Sin conexiones configuradas</p>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">Agregá tu primera plataforma para empezar a importar métricas</p>
          </div>
        ) : (
          connections.map((c) => {
            const plat = PLATFORM_OPTIONS.find((p) => p.value === c.platform);
            return (
              <div key={c.id} className="card card-hover p-4 flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-sm shrink-0"
                  style={{ backgroundColor: plat?.color || "#6366f1" }}>
                  {plat?.initial || "?"}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-slate-800 text-sm">{plat?.label || c.platform}</p>
                    {c.is_active
                      ? <span className="badge badge-green flex items-center gap-1"><CheckCircle2 size={10} />Activa</span>
                      : <span className="badge badge-red flex items-center gap-1"><XCircle size={10} />Inactiva</span>}
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {c.account_name ? `${c.account_name} · ` : ""}{c.account_id}
                  </p>
                </div>
                <button onClick={() => handleDelete(c.id)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 transition-all">
                  <Trash2 size={15} />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Security note */}
      <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4 flex gap-3">
        <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center shrink-0 mt-0.5">
          <CheckCircle2 size={12} className="text-emerald-600" />
        </div>
        <div>
          <p className="text-xs font-semibold text-slate-700">Almacenamiento seguro de tokens</p>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
            Todos los tokens se encriptan con AES-256 antes de guardarse en la base de datos. Nunca se almacenan en texto plano.
          </p>
        </div>
      </div>
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import { connectionsApi, authApi } from "@/lib/api";
import { Connection, CurrentUser, PLATFORM_LABELS } from "@/types";
import { Plus, Trash2, CheckCircle2, XCircle, ChevronDown, Eye, EyeOff, Users, Copy, UserMinus } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

interface TeamMember { id: number; email: string; full_name: string; is_superuser: boolean; }

const TEAM_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  medios: { label: "Medios Digitales", color: "bg-brand-100 text-brand-700" },
  marca:  { label: "Marca",            color: "bg-amber-100 text-amber-700" },
  promo:  { label: "Promo",            color: "bg-emerald-100 text-emerald-700" },
};

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
  const { t } = useTranslation();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [showForm, setShowForm]       = useState(false);
  const [showGuide, setShowGuide]     = useState<string | null>(null);
  const [showTokens, setShowTokens]   = useState<Record<string, boolean>>({});
  const [members, setMembers]         = useState<TeamMember[]>([]);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [form, setForm] = useState({
    platform: "meta", account_id: "", account_name: "",
    access_token: "", refresh_token: "",
  });

  async function load() {
    connectionsApi.list().then(({ data }) => setConnections(data)).catch(() => {});
    authApi.me().then(({ data }) => setCurrentUser(data)).catch(() => {});
    authApi.teamMembers().then(({ data }) => setMembers(data)).catch(() => {});
  }
  useEffect(() => { load(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await connectionsApi.create(form);
      toast.success(t("settings.saveSuccess"));
      setShowForm(false);
      setForm({ platform: "meta", account_id: "", account_name: "", access_token: "", refresh_token: "" });
      await load();
    } catch {
      toast.error(t("settings.saveError"));
    }
  }

  async function handleDelete(id: number) {
    if (!confirm(t("settings.deleteConfirm"))) return;
    try {
      await connectionsApi.delete(id);
      toast.success(t("settings.deleteSuccess"));
      await load();
    } catch { toast.error(t("settings.deleteError")); }
  }

  async function handleRemoveMember(id: number, email: string) {
    if (!confirm(t("settings.removeMember", { email }))) return;
    try {
      await authApi.removeTeamMember(id);
      toast.success(t("settings.removeMemberSuccess"));
      setMembers((prev) => prev.filter((m) => m.id !== id));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("settings.removeMemberError"));
    }
  }

  async function handleUpdateTeamType(team_type: string) {
    try {
      await authApi.updateTeamType(team_type);
      authApi.me().then(({ data }) => setCurrentUser(data)).catch(() => {});
      toast.success("Tipo de equipo actualizado");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al actualizar el tipo de equipo");
    }
  }

  function copyJoinCode() {
    if (currentUser?.join_code) {
      navigator.clipboard.writeText(currentUser.join_code);
      toast.success(t("settings.codeCopied"));
    }
  }

  const selectedPlatform = PLATFORM_OPTIONS.find((p) => p.value === form.platform);

  return (
    <div className="animate-fade-in space-y-6 max-w-3xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{t("settings.title")}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t("settings.subtitle")}</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary">
          <Plus size={16} />
          {t("settings.newConnection")}
        </button>
      </div>

      {/* Form */}
      {showForm && (
        <div className="card p-6 animate-slide-up">
          <h2 className="section-title mb-4">{t("settings.addConnection")}</h2>
          <form onSubmit={handleCreate} className="space-y-4">
            {/* Platform selector */}
            <div>
              <label className="text-sm font-medium text-slate-700 mb-2 block">{t("settings.platform")}</label>
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
                  <span className="text-xs font-semibold text-slate-600">{t("settings.howToGet", { platform: selectedPlatform.label })}</span>
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
                      {t("settings.openPortal")}
                    </a>
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">{t("settings.accountId")}</label>
                <input required value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })}
                  className="input text-sm" placeholder="123456789" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">{t("settings.accountName")}</label>
                <input value={form.account_name} onChange={(e) => setForm({ ...form, account_name: e.target.value })}
                  className="input text-sm" placeholder="Mi cuenta principal" />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">{t("settings.accessToken")}</label>
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
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">
                  {t("settings.refreshToken")} <span className="text-slate-400 font-normal">({t("settings.optional")})</span>
                </label>
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
              <button type="submit" className="btn-primary">{t("settings.saveConnection")}</button>
              <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">{t("common.cancel")}</button>
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
            <p className="text-sm font-medium text-slate-500">{t("settings.noConnections")}</p>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">{t("settings.noConnectionsSub")}</p>
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
                      ? <span className="badge badge-green flex items-center gap-1"><CheckCircle2 size={10} />{t("settings.active")}</span>
                      : <span className="badge badge-red flex items-center gap-1"><XCircle size={10} />{t("settings.inactive")}</span>}
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

      {/* Team members */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900">{t("settings.teamTitle")}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <p className="text-sm text-slate-500">{currentUser?.team_name ?? t("common.noTeam")}</p>
              {currentUser?.team_type && (
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${TEAM_TYPE_LABELS[currentUser.team_type]?.color ?? "bg-slate-100 text-slate-500"}`}>
                  {TEAM_TYPE_LABELS[currentUser.team_type]?.label ?? currentUser.team_type}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {currentUser?.is_superuser && currentUser?.team_type && (
              <select
                value={currentUser.team_type}
                onChange={(e) => handleUpdateTeamType(e.target.value)}
                className="text-xs px-2 py-1.5 rounded-lg border border-slate-200 text-slate-600 bg-white outline-none cursor-pointer hover:border-slate-300"
                title="Cambiar tipo de equipo"
              >
                <option value="medios">Medios Digitales</option>
                <option value="marca">Marca</option>
                <option value="promo">Promo</option>
              </select>
            )}
            {currentUser?.join_code && (
              <button onClick={copyJoinCode}
                className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs font-medium transition-colors">
                <Copy size={13} /> {t("settings.copyCode")}
              </button>
            )}
          </div>
        </div>

        {members.length > 0 ? (
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-50 flex items-center gap-2">
              <Users size={14} className="text-slate-400" />
              <p className="text-sm font-semibold text-slate-700">
                {members.length !== 1
                  ? t("settings.members_plural", { n: members.length })
                  : t("settings.members", { n: members.length })}
              </p>
            </div>
            <div className="divide-y divide-slate-50">
              {members.map((m) => (
                <div key={m.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 font-semibold text-sm shrink-0">
                    {m.full_name.charAt(0).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">{m.full_name}</p>
                    <p className="text-xs text-slate-400 truncate">{m.email}</p>
                  </div>
                  {m.is_superuser && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-100 text-brand-600">{t("settings.admin")}</span>
                  )}
                  {currentUser?.is_superuser && !m.is_superuser && (
                    <button onClick={() => handleRemoveMember(m.id, m.email)}
                      className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-red-500 hover:bg-red-50 transition-all">
                      <UserMinus size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="card p-6 text-center text-sm text-slate-400">
            {t("settings.noMembers")}
          </div>
        )}
      </div>

      {/* Security note */}
      <div className="bg-slate-50 rounded-2xl border border-slate-100 p-4 flex gap-3">
        <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center shrink-0 mt-0.5">
          <CheckCircle2 size={12} className="text-emerald-600" />
        </div>
        <div>
          <p className="text-xs font-semibold text-slate-700">{t("settings.securityTitle")}</p>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{t("settings.securitySub")}</p>
        </div>
      </div>
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import { api, authApi } from "@/lib/api";
import { CurrentUser } from "@/types";
import {
  Users, UserPlus, KeyRound, Building2, ShieldAlert,
  Loader2, CheckCircle2, XCircle, ChevronDown, Presentation, Upload,
} from "lucide-react";
import { toast } from "sonner";

interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  team_group_id: number | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string | null;
}

interface TeamGroup {
  id: number;
  name: string;
  team_type: string;
}

const TEAM_TYPE_BADGE: Record<string, string> = {
  medios: "bg-brand-100 text-brand-700",
  marca:  "bg-amber-100 text-amber-700",
  promo:  "bg-emerald-100 text-emerald-700",
};

const BUILTIN_SLUGS = [
  { slug: "a4",      name: "Cenefa A4",    format: "A4" },
  { slug: "pinchos", name: "Pinchos",      format: "Pinchos" },
  { slug: "black",   name: "Cenefas 3xA4", format: "3xA4" },
];

function BuiltinTemplatesSection() {
  const [uploading, setUploading] = useState<string | null>(null);

  async function handleUpload(slug: string, file: File) {
    setUploading(slug);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.put(`/tools/cenefas/builtin-templates/${slug}`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Plantilla actualizada correctamente");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al actualizar plantilla");
    } finally {
      setUploading(null);
    }
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-3 border-b border-slate-50 flex items-center gap-2">
        <Presentation size={15} className="text-slate-400" />
        <p className="text-sm font-semibold text-slate-700">Plantillas predeterminadas</p>
      </div>
      <div className="divide-y divide-slate-50">
        {BUILTIN_SLUGS.map((t) => (
          <div key={t.slug} className="flex items-center gap-4 px-5 py-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-800">{t.name}</p>
              <p className="text-xs text-slate-400">{t.format} · slug: {t.slug}</p>
            </div>
            <label className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-all ${
              uploading === t.slug
                ? "bg-slate-100 text-slate-400 pointer-events-none"
                : "bg-brand-50 text-brand-600 hover:bg-brand-100"
            }`}>
              {uploading === t.slug
                ? <Loader2 size={13} className="animate-spin" />
                : <Upload size={13} />
              }
              {uploading === t.slug ? "Subiendo…" : "Reemplazar PPTX"}
              <input
                type="file"
                accept=".pptx"
                className="hidden"
                disabled={!!uploading}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleUpload(t.slug, file);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const [me,       setMe]       = useState<CurrentUser | null>(null);
  const [users,    setUsers]    = useState<AdminUser[]>([]);
  const [groups,   setGroups]   = useState<TeamGroup[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [tempPwd,  setTempPwd]  = useState<{ userId: number; pwd: string } | null>(null);

  const [form, setForm] = useState({
    email: "", full_name: "", password: "",
    team_group_id: "" as string | number,
    is_superuser: false,
  });

  useEffect(() => {
    authApi.me()
      .then(({ data }) => setMe(data))
      .catch(() => {});
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const [u, g] = await Promise.all([
        api.get("/admin/users"),
        api.get("/admin/team-groups"),
      ]);
      setUsers(u.data);
      setGroups(g.data);
    } catch {
      toast.error("Error cargando datos de administración");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.post("/admin/users", {
        ...form,
        team_group_id: form.team_group_id === "" ? null : Number(form.team_group_id),
      });
      toast.success("Usuario creado");
      setShowForm(false);
      setForm({ email: "", full_name: "", password: "", team_group_id: "", is_superuser: false });
      await load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al crear usuario");
    }
  }

  async function handleResetPassword(userId: number) {
    if (!confirm("¿Resetear la contraseña de este usuario?")) return;
    try {
      const { data } = await api.post(`/admin/users/${userId}/reset-password`);
      setTempPwd({ userId, pwd: data.temp_password });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al resetear contraseña");
    }
  }

  async function handleAssignTeam(userId: number, groupId: string) {
    try {
      await api.patch(`/admin/users/${userId}/team`, {
        team_group_id: groupId === "" ? null : Number(groupId),
      });
      toast.success("Equipo actualizado");
      setUsers((prev) =>
        prev.map((u) =>
          u.id === userId
            ? { ...u, team_group_id: groupId === "" ? null : Number(groupId) }
            : u
        )
      );
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al asignar equipo");
    }
  }

  async function handleToggleActive(user: AdminUser) {
    try {
      await api.patch(`/admin/users/${user.id}/activate`, { is_active: !user.is_active });
      setUsers((prev) =>
        prev.map((u) => u.id === user.id ? { ...u, is_active: !user.is_active } : u)
      );
    } catch {
      toast.error("Error al cambiar estado del usuario");
    }
  }

  if (!loading && me && !me.is_superuser) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <ShieldAlert size={40} className="text-rose-400" />
        <p className="text-slate-600 font-medium">Acceso denegado — solo administradores</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Panel de Administrador</h1>
          <p className="text-sm text-slate-500 mt-0.5">Gestión de usuarios, contraseñas y equipos</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-all"
        >
          <UserPlus size={15} /> Nuevo usuario
        </button>
      </div>

      {/* Formulario de nuevo usuario */}
      {showForm && (
        <form onSubmit={handleCreate} className="card p-5 space-y-4 border-brand-200 border">
          <p className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <UserPlus size={15} className="text-brand-500" /> Crear nuevo usuario
          </p>
          <div className="grid grid-cols-2 gap-3">
            <input
              required
              className="input text-sm"
              placeholder="Nombre completo"
              value={form.full_name}
              onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
            />
            <input
              required type="email"
              className="input text-sm"
              placeholder="Email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
            <input
              required
              className="input text-sm"
              placeholder="Contraseña (mín. 12 chars, mayúscula, número, símbolo)"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            />
            <div className="relative">
              <select
                className="input text-sm w-full appearance-none pr-8"
                value={form.team_group_id}
                onChange={(e) => setForm((f) => ({ ...f, team_group_id: e.target.value }))}
              >
                <option value="">Sin equipo</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>{g.name} ({g.team_type})</option>
                ))}
              </select>
              <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_superuser}
              onChange={(e) => setForm((f) => ({ ...f, is_superuser: e.target.checked }))}
              className="rounded"
            />
            Superusuario (acceso admin)
          </label>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-sm px-4 py-2">Crear</button>
            <button type="button" onClick={() => setShowForm(false)} className="btn-secondary text-sm px-4 py-2">Cancelar</button>
          </div>
        </form>
      )}

      {/* Contraseña temporal */}
      {tempPwd && (
        <div className="card p-4 border-amber-300 border bg-amber-50 flex items-start gap-3">
          <KeyRound size={18} className="text-amber-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-amber-800">Contraseña temporal generada</p>
            <p className="text-xs text-amber-700 mt-0.5">Compartila de forma segura. El usuario deberá cambiarla.</p>
            <code className="mt-2 block bg-white border border-amber-200 rounded-lg px-3 py-2 text-sm font-mono text-amber-900 select-all">
              {tempPwd.pwd}
            </code>
          </div>
          <button onClick={() => setTempPwd(null)} className="text-amber-600 hover:text-amber-800">
            <XCircle size={16} />
          </button>
        </div>
      )}

      {/* Plantillas predeterminadas */}
      <BuiltinTemplatesSection />

      {/* Tabla de grupos */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-50 flex items-center gap-2">
          <Building2 size={15} className="text-slate-400" />
          <p className="text-sm font-semibold text-slate-700">Grupos de equipo</p>
        </div>
        <div className="divide-y divide-slate-50">
          {groups.map((g) => (
            <div key={g.id} className="flex items-center gap-3 px-5 py-3">
              <span className="text-sm font-medium text-slate-700">{g.name}</span>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${TEAM_TYPE_BADGE[g.team_type] ?? "bg-slate-100 text-slate-500"}`}>
                {g.team_type}
              </span>
              <span className="text-xs text-slate-400 ml-auto">ID: {g.id}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Tabla de usuarios */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-50 flex items-center gap-2">
          <Users size={15} className="text-slate-400" />
          <p className="text-sm font-semibold text-slate-700">
            Usuarios ({users.length})
          </p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-10">
            <Loader2 size={20} className="animate-spin text-slate-400" />
          </div>
        ) : (
          <div className="divide-y divide-slate-50">
            {users.map((u) => (
              <div key={u.id} className="flex items-center gap-4 px-5 py-3">
                {/* Avatar */}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                  u.is_active ? "bg-brand-100 text-brand-600" : "bg-slate-100 text-slate-400"
                }`}>
                  {u.full_name.charAt(0).toUpperCase()}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-slate-800 truncate">{u.full_name}</p>
                    {u.is_superuser && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-rose-100 text-rose-600">ADMIN</span>
                    )}
                    {!u.is_active && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">INACTIVO</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 truncate">{u.email}</p>
                </div>

                {/* Asignar equipo */}
                <div className="relative shrink-0">
                  <select
                    value={u.team_group_id ?? ""}
                    onChange={(e) => handleAssignTeam(u.id, e.target.value)}
                    className="appearance-none text-xs px-2 pr-6 py-1.5 rounded-lg border border-slate-200 text-slate-600 bg-white outline-none cursor-pointer hover:border-slate-300"
                  >
                    <option value="">Sin equipo</option>
                    {groups.map((g) => (
                      <option key={g.id} value={g.id}>{g.name}</option>
                    ))}
                  </select>
                  <ChevronDown size={11} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                </div>

                {/* Resetear contraseña */}
                <button
                  onClick={() => handleResetPassword(u.id)}
                  title="Resetear contraseña"
                  className="p-1.5 rounded-lg text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition-all"
                >
                  <KeyRound size={15} />
                </button>

                {/* Activar / desactivar */}
                <button
                  onClick={() => handleToggleActive(u)}
                  title={u.is_active ? "Desactivar usuario" : "Activar usuario"}
                  className={`p-1.5 rounded-lg transition-all ${
                    u.is_active
                      ? "text-emerald-500 hover:text-rose-500 hover:bg-rose-50"
                      : "text-slate-300 hover:text-emerald-500 hover:bg-emerald-50"
                  }`}
                >
                  {u.is_active ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

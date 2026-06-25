"use client";
import { useEffect, useState } from "react";
import { api, authApi } from "@/lib/api";
import { CurrentUser } from "@/types";
import {
  Users, UserPlus, KeyRound, ShieldAlert, ShieldCheck,
  Loader2, CheckCircle2, XCircle, ChevronDown, Presentation,
  Upload, Plus, Trash2, Pencil, X, Shield,
} from "lucide-react";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  role_id: number | null;
  role_name: string | null;
  permissions: string[];
  is_active: boolean;
  is_superuser: boolean;
  created_at: string | null;
}

interface RoleItem {
  id: number;
  name: string;
  description: string;
  permissions: string[];
  is_system: boolean;
}

interface PermissionDef {
  key: string;
  description: string;
}

// ---------------------------------------------------------------------------
// Permission group labels for display
// ---------------------------------------------------------------------------
const PERM_GROUPS: Record<string, string> = {
  "platform": "Plataforma",
  "cenefas":  "Cenefas",
  "analytics":"Analytics",
  "connections":"Conexiones",
  "ai":       "Inteligencia Artificial",
};

function groupPermissions(perms: PermissionDef[]) {
  const groups: Record<string, PermissionDef[]> = {};
  for (const p of perms) {
    const ns = p.key.split(".")[0];
    if (!groups[ns]) groups[ns] = [];
    groups[ns].push(p);
  }
  return groups;
}

// ---------------------------------------------------------------------------
// Builtin templates section
// ---------------------------------------------------------------------------
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
              {uploading === t.slug ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              {uploading === t.slug ? "Subiendo…" : "Reemplazar PPTX"}
              <input type="file" accept=".pptx" className="hidden" disabled={!!uploading}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(t.slug, f); e.target.value = ""; }}
              />
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// User editor modal
// ---------------------------------------------------------------------------
function UserEditorModal({
  user, onClose, onSaved,
}: {
  user: AdminUser;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [fullName, setFullName] = useState(user.full_name);
  const [email,    setEmail]    = useState(user.email);
  const [saving,   setSaving]   = useState(false);

  async function save() {
    if (!fullName.trim()) { toast.error("El nombre es obligatorio"); return; }
    if (!email.trim())    { toast.error("El email es obligatorio");  return; }
    setSaving(true);
    try {
      await api.patch(`/admin/users/${user.id}`, { full_name: fullName, email });
      toast.success("Usuario actualizado");
      onSaved();
      onClose();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm">
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
          <Pencil size={16} className="text-brand-500" />
          <h2 className="text-base font-semibold text-slate-800">Editar usuario</h2>
          <button onClick={onClose} className="ml-auto text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        <div className="px-6 py-5 space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Nombre completo</label>
            <input
              className="input text-sm w-full"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Nombre completo"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Email</label>
            <input
              type="email"
              className="input text-sm w-full"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@empresa.com"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 px-6 pb-5">
          <button onClick={onClose} className="btn-secondary text-sm px-4 py-2">Cancelar</button>
          <button onClick={save} disabled={saving} className="btn-primary text-sm px-4 py-2 flex items-center gap-2">
            {saving && <Loader2 size={13} className="animate-spin" />}
            Guardar
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Role editor modal
// ---------------------------------------------------------------------------
function RoleEditorModal({
  role, allPerms, onClose, onSaved,
}: {
  role: RoleItem | null;    // null = create new
  allPerms: PermissionDef[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name,        setName]        = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [selected,    setSelected]    = useState<Set<string>>(new Set(role?.permissions ?? []));
  const [saving,      setSaving]      = useState(false);

  const grouped = groupPermissions(allPerms);

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  async function save() {
    if (!name.trim()) { toast.error("El nombre del rol es obligatorio"); return; }
    setSaving(true);
    try {
      if (role) {
        await api.patch(`/admin/roles/${role.id}`, {
          description,
          permissions: [...selected],
          ...(!role.is_system ? { name } : {}),
        });
        toast.success("Rol actualizado");
      } else {
        await api.post("/admin/roles", { name, description, permissions: [...selected] });
        toast.success(`Rol "${name}" creado`);
      }
      onSaved();
      onClose();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al guardar rol");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
          <Shield size={18} className="text-brand-500" />
          <h2 className="text-base font-semibold text-slate-800">
            {role ? `Editar rol: ${role.name}` : "Crear nuevo rol"}
          </h2>
          <button onClick={onClose} className="ml-auto text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Nombre del rol</label>
              <input
                className="input text-sm w-full"
                placeholder="Ej: Editor Comercial"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={role?.is_system}
              />
              {role?.is_system && <p className="text-[10px] text-slate-400 mt-1">Los roles del sistema no se pueden renombrar</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Descripción</label>
              <input
                className="input text-sm w-full"
                placeholder="Breve descripción del rol…"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>

          {/* Permissions */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Permisos</p>
            <div className="space-y-4">
              {Object.entries(grouped).map(([ns, perms]) => (
                <div key={ns}>
                  <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                    {PERM_GROUPS[ns] ?? ns}
                  </p>
                  <div className="space-y-1.5">
                    {perms.map((p) => (
                      <label key={p.key} className="flex items-start gap-3 cursor-pointer group">
                        <div className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-all ${
                          selected.has(p.key)
                            ? "bg-brand-600 border-brand-600"
                            : "border-slate-300 group-hover:border-brand-400"
                        }`}
                          onClick={() => toggle(p.key)}
                        >
                          {selected.has(p.key) && <CheckCircle2 size={11} className="text-white" />}
                        </div>
                        <div onClick={() => toggle(p.key)}>
                          <p className="text-xs font-medium text-slate-700 font-mono">{p.key}</p>
                          <p className="text-[11px] text-slate-400 leading-snug">{p.description}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100">
          <p className="text-xs text-slate-400">{selected.size} permiso{selected.size !== 1 ? "s" : ""} seleccionado{selected.size !== 1 ? "s" : ""}</p>
          <div className="flex gap-2">
            <button onClick={onClose} className="btn-secondary text-sm px-4 py-2">Cancelar</button>
            <button onClick={save} disabled={saving} className="btn-primary text-sm px-4 py-2 flex items-center gap-2">
              {saving && <Loader2 size={13} className="animate-spin" />}
              {role ? "Guardar cambios" : "Crear rol"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function AdminPage() {
  const [me,          setMe]          = useState<CurrentUser | null>(null);
  const [users,       setUsers]       = useState<AdminUser[]>([]);
  const [roles,       setRoles]       = useState<RoleItem[]>([]);
  const [allPerms,    setAllPerms]    = useState<PermissionDef[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [showForm,    setShowForm]    = useState(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null | "new">(undefined as any);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [tempPwd,     setTempPwd]     = useState<{ userId: number; pwd: string } | null>(null);

  const [form, setForm] = useState({
    email: "", full_name: "", password: "",
    role_id: "" as string | number,
    is_superuser: false,
  });

  useEffect(() => {
    authApi.me().then(({ data }) => setMe(data)).catch(() => {});
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const [u, r, p] = await Promise.all([
        api.get("/admin/users"),
        api.get("/admin/roles"),
        api.get("/admin/permissions"),
      ]);
      setUsers(u.data);
      setRoles(r.data);
      setAllPerms(p.data);
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
        role_id: form.role_id === "" ? null : Number(form.role_id),
      });
      toast.success("Usuario creado");
      setShowForm(false);
      setForm({ email: "", full_name: "", password: "", role_id: "", is_superuser: false });
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

  async function handleAssignRole(userId: number, roleId: string) {
    try {
      await api.patch(`/admin/users/${userId}/role`, {
        role_id: roleId === "" ? null : Number(roleId),
      });
      toast.success("Rol actualizado");
      await load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al asignar rol");
    }
  }

  async function handleToggleActive(user: AdminUser) {
    try {
      await api.patch(`/admin/users/${user.id}/activate`, { is_active: !user.is_active });
      setUsers((prev) => prev.map((u) => u.id === user.id ? { ...u, is_active: !user.is_active } : u));
    } catch {
      toast.error("Error al cambiar estado del usuario");
    }
  }

  async function handleDeleteRole(role: RoleItem) {
    if (!confirm(`¿Eliminar el rol "${role.name}"? Los usuarios con este rol quedarán sin rol asignado.`)) return;
    try {
      await api.delete(`/admin/roles/${role.id}`);
      toast.success("Rol eliminado");
      await load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Error al eliminar rol");
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

  const ROLE_COLORS: Record<string, string> = {
    Superadmin: "bg-rose-100 text-rose-700",
    Admin:      "bg-brand-100 text-brand-700",
    Editor:     "bg-amber-100 text-amber-700",
    Viewer:     "bg-slate-100 text-slate-500",
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Panel de Administrador</h1>
          <p className="text-sm text-slate-500 mt-0.5">Gestión de usuarios, roles y permisos</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-all"
        >
          <UserPlus size={15} /> Nuevo usuario
        </button>
      </div>

      {/* Create user form */}
      {showForm && (
        <form onSubmit={handleCreate} className="card p-5 space-y-4 border-brand-200 border">
          <p className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <UserPlus size={15} className="text-brand-500" /> Crear nuevo usuario
          </p>
          <div className="grid grid-cols-2 gap-3">
            <input required className="input text-sm" placeholder="Nombre completo"
              value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
            <input required type="email" className="input text-sm" placeholder="Email"
              value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
            <input required className="input text-sm" placeholder="Contraseña (mín. 12 chars, mayúscula, número, símbolo)"
              value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
            <div className="relative">
              <select className="input text-sm w-full appearance-none pr-8" value={form.role_id}
                onChange={(e) => setForm((f) => ({ ...f, role_id: e.target.value }))}>
                <option value="">Sin rol</option>
                {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-sm px-4 py-2">Crear</button>
            <button type="button" onClick={() => setShowForm(false)} className="btn-secondary text-sm px-4 py-2">Cancelar</button>
          </div>
        </form>
      )}

      {/* Temp password banner */}
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
          <button onClick={() => setTempPwd(null)} className="text-amber-600 hover:text-amber-800"><XCircle size={16} /></button>
        </div>
      )}

      {/* Plantillas predeterminadas */}
      <BuiltinTemplatesSection />

      {/* Roles */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-50 flex items-center gap-2">
          <Shield size={15} className="text-slate-400" />
          <p className="text-sm font-semibold text-slate-700">Roles y permisos</p>
          <button onClick={() => setEditingRole("new")}
            className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-medium transition-all">
            <Plus size={12} /> Nuevo rol
          </button>
        </div>
        {loading ? (
          <div className="flex items-center justify-center p-8"><Loader2 size={18} className="animate-spin text-slate-400" /></div>
        ) : (
          <div className="divide-y divide-slate-50">
            {roles.map((r) => (
              <div key={r.id} className="flex items-start gap-3 px-5 py-3">
                <ShieldCheck size={15} className="text-slate-400 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-slate-800">{r.name}</span>
                    {r.is_system && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">SISTEMA</span>
                    )}
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${ROLE_COLORS[r.name] ?? "bg-violet-100 text-violet-700"}`}>
                      {r.permissions.length} permiso{r.permissions.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                  {r.description && <p className="text-xs text-slate-400 mt-0.5 leading-snug">{r.description}</p>}
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {r.permissions.slice(0, 6).map((p) => (
                      <span key={p} className="text-[10px] bg-slate-50 border border-slate-100 text-slate-500 rounded px-1.5 py-0.5 font-mono">{p}</span>
                    ))}
                    {r.permissions.length > 6 && (
                      <span className="text-[10px] text-slate-400 px-1.5 py-0.5">+{r.permissions.length - 6} más</span>
                    )}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => setEditingRole(r)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-brand-600 hover:bg-brand-50 transition-all" title="Editar rol">
                    <Pencil size={13} />
                  </button>
                  {!r.is_system && (
                    <button onClick={() => handleDeleteRole(r)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-all" title="Eliminar rol">
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Users */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-50 flex items-center gap-2">
          <Users size={15} className="text-slate-400" />
          <p className="text-sm font-semibold text-slate-700">Usuarios ({users.length})</p>
        </div>
        {loading ? (
          <div className="flex items-center justify-center p-10"><Loader2 size={20} className="animate-spin text-slate-400" /></div>
        ) : (
          <div className="divide-y divide-slate-50">
            {users.map((u) => (
              <div key={u.id} className="flex items-center gap-4 px-5 py-3">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                  u.is_active ? "bg-brand-100 text-brand-600" : "bg-slate-100 text-slate-400"
                }`}>
                  {u.full_name.charAt(0).toUpperCase()}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium text-slate-800 truncate">{u.full_name}</p>
                    {u.role_name && (
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${ROLE_COLORS[u.role_name] ?? "bg-violet-100 text-violet-700"}`}>
                        {u.role_name.toUpperCase()}
                      </span>
                    )}
                    {!u.is_active && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">INACTIVO</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 truncate">{u.email}</p>
                </div>

                {/* Role selector */}
                <div className="relative shrink-0">
                  <select
                    value={u.role_id ?? ""}
                    onChange={(e) => handleAssignRole(u.id, e.target.value)}
                    className="appearance-none text-xs px-2 pr-6 py-1.5 rounded-lg border border-slate-200 text-slate-600 bg-white outline-none cursor-pointer hover:border-slate-300"
                  >
                    <option value="">Sin rol</option>
                    {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </select>
                  <ChevronDown size={11} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                </div>

                <button onClick={() => setEditingUser(u)} title="Editar usuario"
                  className="p-1.5 rounded-lg text-slate-400 hover:text-brand-600 hover:bg-brand-50 transition-all">
                  <Pencil size={15} />
                </button>

                <button onClick={() => handleResetPassword(u.id)} title="Resetear contraseña"
                  className="p-1.5 rounded-lg text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition-all">
                  <KeyRound size={15} />
                </button>

                <button onClick={() => handleToggleActive(u)}
                  title={u.is_active ? "Desactivar usuario" : "Activar usuario"}
                  className={`p-1.5 rounded-lg transition-all ${
                    u.is_active ? "text-emerald-500 hover:text-rose-500 hover:bg-rose-50" : "text-slate-300 hover:text-emerald-500 hover:bg-emerald-50"
                  }`}>
                  {u.is_active ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Role editor modal */}
      {editingRole !== undefined && editingRole !== (undefined as any) && (
        <RoleEditorModal
          role={editingRole === "new" ? null : editingRole}
          allPerms={allPerms}
          onClose={() => setEditingRole(undefined as any)}
          onSaved={load}
        />
      )}

      {/* User editor modal */}
      {editingUser && (
        <UserEditorModal
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onSaved={load}
        />
      )}
    </div>
  );
}

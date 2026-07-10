"use client";
import { useEffect, useState } from "react";
import { api, authApi } from "@/lib/api";
import { CurrentUser } from "@/types";
import {
  Users, UserPlus, KeyRound, ShieldAlert, ShieldCheck,
  Loader2, CheckCircle2, XCircle, ChevronDown,
  Plus, Trash2, Pencil, X, Shield, History, Cpu,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import AuditLogTab from "./AuditLogTab";
import AiUsageTab from "./AiUsageTab";

type AdminTab = "usuarios" | "auditoria" | "ia";

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
  view_only: boolean;
}

interface PermissionDef {
  key: string;
  description: string;
}

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
// User editor modal
// ---------------------------------------------------------------------------
function UserEditorModal({
  user, allRoles, allPerms, onClose, onSaved,
}: {
  user: AdminUser;
  allRoles: RoleItem[];
  allPerms: PermissionDef[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [fullName, setFullName] = useState(user.full_name);
  const [email,    setEmail]    = useState(user.email);
  const [selected, setSelected] = useState<Set<string>>(new Set(user.permissions));
  const [saving,   setSaving]   = useState(false);

  const role     = allRoles.find((r) => r.id === user.role_id) ?? null;
  const viewOnly = role?.view_only ?? false;
  const visiblePerms = viewOnly ? allPerms.filter((p) => p.key.endsWith(".view")) : allPerms;
  const grouped  = groupPermissions(visiblePerms);

  const PERM_GROUPS: Record<string, string> = {
    "platform":    t("admin.permGroups.platform"),
    "cenefas":     t("admin.permGroups.cenefas"),
    "analytics":   t("admin.permGroups.analytics"),
    "connections": t("admin.permGroups.connections"),
    "ai":          t("admin.permGroups.ai"),
  };

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  async function save() {
    if (!fullName.trim()) { toast.error(t("admin.userEditor.nameRequired")); return; }
    if (!email.trim())    { toast.error(t("admin.userEditor.emailRequired"));  return; }
    setSaving(true);
    try {
      await api.patch(`/admin/users/${user.id}`, { full_name: fullName, email });
      try {
        await api.patch(`/admin/users/${user.id}/permissions`, { permissions: [...selected] });
      } catch (err: any) {
        toast.error(err?.response?.data?.detail ?? t("admin.userEditor.permissionsSaveError"));
        return;
      }
      toast.success(t("admin.userEditor.updated"));
      onSaved();
      onClose();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("admin.userEditor.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100 dark:border-slate-800">
          <Pencil size={16} className="text-brand-500" />
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">{t("admin.userEditor.title")}</h2>
          <button onClick={onClose} className="ml-auto text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"><X size={18} /></button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{t("admin.userEditor.fullName")}</label>
              <input
                className="input text-sm w-full"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder={t("admin.userEditor.fullName")}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{t("admin.userEditor.email")}</label>
              <input
                type="email"
                className="input text-sm w-full"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("admin.userEditor.emailPlaceholder")}
              />
            </div>
          </div>

          {/* Permisos individuales — se prenden/apagan por usuario, no por rol */}
          <div>
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-1">{t("admin.roleEditor.permissionsLabel")}</p>
            {viewOnly && (
              <p className="text-[11px] text-amber-600 dark:text-amber-400 mb-2">{t("admin.userEditor.viewOnlyNotice")}</p>
            )}
            <div className="space-y-4">
              {Object.entries(grouped).map(([ns, perms]) => (
                <div key={ns}>
                  <p className="text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
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
                          <p className="text-xs font-medium text-slate-700 dark:text-slate-300 font-mono">{p.key}</p>
                          <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-snug">{p.description}</p>
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
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-slate-100 dark:border-slate-800">
          <button onClick={onClose} className="btn-secondary text-sm px-4 py-2">{t("common.cancel")}</button>
          <button onClick={save} disabled={saving} className="btn-primary text-sm px-4 py-2 flex items-center gap-2">
            {saving && <Loader2 size={13} className="animate-spin" />}
            {t("common.save")}
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
  const { t } = useTranslation();
  const [name,        setName]        = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [selected,    setSelected]    = useState<Set<string>>(new Set(role?.permissions ?? []));
  const [saving,      setSaving]      = useState(false);

  const PERM_GROUPS: Record<string, string> = {
    "platform":    t("admin.permGroups.platform"),
    "cenefas":     t("admin.permGroups.cenefas"),
    "analytics":   t("admin.permGroups.analytics"),
    "connections": t("admin.permGroups.connections"),
    "ai":          t("admin.permGroups.ai"),
  };
  const grouped = groupPermissions(allPerms);

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  async function save() {
    if (!name.trim()) { toast.error(t("admin.roleEditor.nameRequired")); return; }
    setSaving(true);
    try {
      if (role) {
        await api.patch(`/admin/roles/${role.id}`, {
          description,
          permissions: [...selected],
          ...(!role.is_system ? { name } : {}),
        });
        toast.success(t("admin.roleEditor.updated"));
      } else {
        await api.post("/admin/roles", { name, description, permissions: [...selected] });
        toast.success(t("admin.roleEditor.created", { name }));
      }
      onSaved();
      onClose();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("admin.roleEditor.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100 dark:border-slate-800">
          <Shield size={18} className="text-brand-500" />
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">
            {role ? t("admin.roleEditor.editTitle", { name: role.name }) : t("admin.roleEditor.createTitle")}
          </h2>
          <button onClick={onClose} className="ml-auto text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"><X size={18} /></button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{t("admin.roleEditor.nameLabel")}</label>
              <input
                className="input text-sm w-full"
                placeholder={t("admin.roleEditor.namePlaceholder")}
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={role?.is_system}
              />
              {role?.is_system && <p className="text-[10px] text-slate-400 mt-1">{t("admin.roleEditor.systemNoRename")}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{t("admin.roleEditor.descriptionLabel")}</label>
              <input
                className="input text-sm w-full"
                placeholder={t("admin.roleEditor.descriptionPlaceholder")}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>

          {/* Permissions */}
          <div>
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-3">{t("admin.roleEditor.permissionsLabel")}</p>
            <div className="space-y-4">
              {Object.entries(grouped).map(([ns, perms]) => (
                <div key={ns}>
                  <p className="text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
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
                          <p className="text-xs font-medium text-slate-700 dark:text-slate-300 font-mono">{p.key}</p>
                          <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-snug">{p.description}</p>
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
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 dark:border-slate-800">
          <p className="text-xs text-slate-400 dark:text-slate-500">{t("admin.roleEditor.permsSelected", { count: selected.size })}</p>
          <div className="flex gap-2">
            <button onClick={onClose} className="btn-secondary text-sm px-4 py-2">{t("common.cancel")}</button>
            <button onClick={save} disabled={saving} className="btn-primary text-sm px-4 py-2 flex items-center gap-2">
              {saving && <Loader2 size={13} className="animate-spin" />}
              {role ? t("admin.roleEditor.saveChanges") : t("admin.roleEditor.createRole")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AdminPage() {
  const { t } = useTranslation();
  const [me,          setMe]          = useState<CurrentUser | null>(null);
  const [users,       setUsers]       = useState<AdminUser[]>([]);
  const [roles,       setRoles]       = useState<RoleItem[]>([]);
  const [allPerms,    setAllPerms]    = useState<PermissionDef[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [showForm,    setShowForm]    = useState(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null | "new">(undefined as any);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [tempPwd,     setTempPwd]     = useState<{ userId: number; pwd: string } | null>(null);
  const [activeTab,   setActiveTab]   = useState<AdminTab>("usuarios");

  const [form, setForm] = useState({
    email: "", full_name: "", password: "",
    role_id: "" as string | number,
  });

  // Superadmin no se ofrece como rol asignable desde el panel — es un flag
  // reservado para la cuenta principal, no algo que se elija en un select.
  const assignableRoles = roles.filter((r) => r.name !== "Superadmin");

  useEffect(() => {
    // No disparamos /admin/* hasta confirmar que el usuario es superuser —
    // evita requests innecesarios (y un toast de error confuso) para
    // cualquier usuario logueado que entre a esta ruta sin ser admin.
    authApi
      .me()
      .then(({ data }) => {
        setMe(data);
        if (data.is_superuser) {
          load();
        } else {
          setLoading(false);
        }
      })
      .catch(() => setLoading(false));
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
      toast.error(t("admin.loadError"));
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
      toast.success(t("admin.createForm.created"));
      setShowForm(false);
      setForm({ email: "", full_name: "", password: "", role_id: "" });
      await load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("admin.createForm.createError"));
    }
  }

  async function handleResetPassword(userId: number) {
    if (!confirm(t("admin.resetPasswordConfirm"))) return;
    try {
      const { data } = await api.post(`/admin/users/${userId}/reset-password`);
      setTempPwd({ userId, pwd: data.temp_password });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("admin.resetPasswordError"));
    }
  }

  async function handleAssignRole(userId: number, roleId: string) {
    try {
      await api.patch(`/admin/users/${userId}/role`, {
        role_id: roleId === "" ? null : Number(roleId),
      });
      toast.success(t("admin.roleUpdated"));
      await load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("admin.roleAssignError"));
    }
  }

  async function handleToggleActive(user: AdminUser) {
    try {
      await api.patch(`/admin/users/${user.id}/activate`, { is_active: !user.is_active });
      setUsers((prev) => prev.map((u) => u.id === user.id ? { ...u, is_active: !user.is_active } : u));
    } catch {
      toast.error(t("admin.toggleActiveError"));
    }
  }

  async function handleDeleteRole(role: RoleItem) {
    if (!confirm(t("admin.deleteRoleConfirm", { name: role.name }))) return;
    try {
      await api.delete(`/admin/roles/${role.id}`);
      toast.success(t("admin.roleDeleted"));
      await load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("admin.roleDeleteError"));
    }
  }

  if (!loading && me && !me.is_superuser) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <ShieldAlert size={40} className="text-rose-400" />
        <p className="text-slate-600 dark:text-slate-400 font-medium">{t("admin.accessDenied")}</p>
      </div>
    );
  }

  const ROLE_COLORS: Record<string, string> = {
    Superadmin: "bg-rose-100 text-rose-700",
    Admin:      "bg-brand-100 text-brand-700",
    Usuario:    "bg-amber-100 text-amber-700",
    Viewer:     "bg-slate-100 text-slate-500",
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("admin.title")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("admin.subtitle")}</p>
        </div>
        {activeTab === "usuarios" && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-all"
          >
            <UserPlus size={15} /> {t("admin.newUser")}
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-xl p-1 w-fit">
        <button onClick={() => setActiveTab("usuarios")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
            activeTab === "usuarios"
              ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
              : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
          }`}>
          <Users size={13} /> Usuarios y Roles
        </button>
        <button onClick={() => setActiveTab("auditoria")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
            activeTab === "auditoria"
              ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
              : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
          }`}>
          <History size={13} /> Auditoría
        </button>
        <button onClick={() => setActiveTab("ia")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
            activeTab === "ia"
              ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
              : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
          }`}>
          <Cpu size={13} /> Uso de IA
        </button>
      </div>

      {activeTab === "auditoria" && <AuditLogTab />}
      {activeTab === "ia" && <AiUsageTab />}

      {activeTab === "usuarios" && (
      <>
      {/* Create user form */}
      {showForm && (
        <form onSubmit={handleCreate} className="card p-5 space-y-4 border-brand-200 border">
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
            <UserPlus size={15} className="text-brand-500" /> {t("admin.createForm.title")}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <input required className="input text-sm" placeholder={t("admin.createForm.namePlaceholder")}
              value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
            <input required type="email" className="input text-sm" placeholder={t("admin.createForm.emailPlaceholder")}
              value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
            <input required className="input text-sm" placeholder={t("admin.createForm.passwordPlaceholder")}
              value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
            <div className="relative">
              <select className="input text-sm w-full appearance-none pr-8" value={form.role_id}
                onChange={(e) => setForm((f) => ({ ...f, role_id: e.target.value }))}>
                <option value="">{t("admin.noRole")}</option>
                {assignableRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-sm px-4 py-2">{t("admin.createForm.create")}</button>
            <button type="button" onClick={() => setShowForm(false)} className="btn-secondary text-sm px-4 py-2">{t("admin.createForm.cancel")}</button>
          </div>
        </form>
      )}

      {/* Temp password banner */}
      {tempPwd && (
        <div className="card p-4 border-amber-300 border bg-amber-50 flex items-start gap-3">
          <KeyRound size={18} className="text-amber-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-amber-800">{t("admin.tempPassword.title")}</p>
            <p className="text-xs text-amber-700 mt-0.5">{t("admin.tempPassword.subtitle")}</p>
            <code className="mt-2 block bg-white border border-amber-200 rounded-lg px-3 py-2 text-sm font-mono text-amber-900 select-all">
              {tempPwd.pwd}
            </code>
          </div>
          <button onClick={() => setTempPwd(null)} className="text-amber-600 hover:text-amber-800"><XCircle size={16} /></button>
        </div>
      )}

      {/* Roles */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-50 dark:border-slate-800 flex items-center gap-2">
          <Shield size={15} className="text-slate-400" />
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">{t("admin.roles.title")}</p>
          <button onClick={() => setEditingRole("new")}
            className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-medium transition-all">
            <Plus size={12} /> {t("admin.roles.newRole")}
          </button>
        </div>
        {loading ? (
          <div className="flex items-center justify-center p-8"><Loader2 size={18} className="animate-spin text-slate-400" /></div>
        ) : (
          <div className="divide-y divide-slate-50 dark:divide-slate-800">
            {roles.map((r) => (
              <div key={r.id} className="flex items-start gap-3 px-5 py-3">
                <ShieldCheck size={15} className="text-slate-400 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{r.name}</span>
                    {r.is_system && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">{t("admin.roles.system")}</span>
                    )}
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${ROLE_COLORS[r.name] ?? "bg-violet-100 text-violet-700"}`}>
                      {t("admin.roles.permCount", { count: r.permissions.length })}
                    </span>
                  </div>
                  {r.description && <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5 leading-snug">{r.description}</p>}
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {r.permissions.slice(0, 6).map((p) => (
                      <span key={p} className="text-[10px] bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700 text-slate-500 dark:text-slate-400 rounded px-1.5 py-0.5 font-mono">{p}</span>
                    ))}
                    {r.permissions.length > 6 && (
                      <span className="text-[10px] text-slate-400 dark:text-slate-500 px-1.5 py-0.5">{t("admin.roles.more", { count: r.permissions.length - 6 })}</span>
                    )}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => setEditingRole(r)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-brand-600 hover:bg-brand-50 transition-all" title={t("admin.roles.edit")}>
                    <Pencil size={13} />
                  </button>
                  {!r.is_system && (
                    <button onClick={() => handleDeleteRole(r)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-all" title={t("admin.roles.delete")}>
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
        <div className="px-5 py-3 border-b border-slate-50 dark:border-slate-800 flex items-center gap-2">
          <Users size={15} className="text-slate-400" />
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">{t("admin.usersTitle", { count: users.length })}</p>
        </div>
        {loading ? (
          <div className="flex items-center justify-center p-10"><Loader2 size={20} className="animate-spin text-slate-400" /></div>
        ) : (
          <div className="divide-y divide-slate-50 dark:divide-slate-800">
            {users.map((u) => (
              <div key={u.id} className="flex items-center gap-4 px-5 py-3">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                  u.is_active ? "bg-brand-100 text-brand-600" : "bg-slate-100 text-slate-400"
                }`}>
                  {u.full_name.charAt(0).toUpperCase()}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{u.full_name}</p>
                    {u.role_name && (
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${ROLE_COLORS[u.role_name] ?? "bg-violet-100 text-violet-700"}`}>
                        {u.role_name.toUpperCase()}
                      </span>
                    )}
                    {!u.is_active && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">{t("admin.inactive")}</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 dark:text-slate-500 truncate">{u.email}</p>
                </div>

                {/* Role selector — el Super Admin no se reasigna desde acá */}
                {u.is_superuser ? (
                  <span className="text-[11px] text-slate-400 dark:text-slate-500 italic shrink-0 px-1">—</span>
                ) : (
                  <div className="relative shrink-0">
                    <select
                      value={u.role_id ?? ""}
                      onChange={(e) => handleAssignRole(u.id, e.target.value)}
                      className="appearance-none text-xs px-2 pr-6 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-800 outline-none cursor-pointer hover:border-slate-300 dark:hover:border-slate-600"
                    >
                      <option value="">{t("admin.noRole")}</option>
                      {assignableRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                    <ChevronDown size={11} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                  </div>
                )}

                <button onClick={() => setEditingUser(u)} title={t("admin.editUser")}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-brand-600 hover:bg-brand-50 transition-all">
                  <Pencil size={15} />
                </button>

                <button onClick={() => handleResetPassword(u.id)} title={t("admin.resetPasswordTitle")}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition-all">
                  <KeyRound size={15} />
                </button>

                <button onClick={() => handleToggleActive(u)}
                  title={u.is_active ? t("admin.deactivateUser") : t("admin.activateUser")}
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
      </>
      )}

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
          allRoles={roles}
          allPerms={allPerms}
          onClose={() => setEditingUser(null)}
          onSaved={load}
        />
      )}
    </div>
  );
}

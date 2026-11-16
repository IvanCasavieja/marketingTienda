"use client";
import { MUNDOS } from "@/lib/mundos";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import { useCurrentUserStore } from "@/store/currentUser";
import {
  Users, UserPlus, KeyRound, ShieldAlert, ShieldCheck,
  Loader2, CheckCircle2, XCircle, ChevronDown,
  Plus, Trash2, Pencil, X, Shield, History, Cpu, Store, Building2,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import AuditLogTab from "./AuditLogTab";
import AiUsageTab from "./AiUsageTab";
import UserActivityModal from "./UserActivityModal";

type AdminTab = "usuarios" | "auditoria" | "ia";

// Dentro de la pestaña de usuarios: las personas y los logins de sucursal se
// listaban mezclados (29 personas perdidas entre 60 sucursales). Se separan en
// tres listas; la de Tienda todavía no tiene ninguna, llegan más adelante.
// Las cuentas externas (la agencia, 15/11/2026) van en la suya: son de afuera
// y se administran distinto (sin rol, solo ven el calendario de su mes).
type ListaDeUsuarios = "personas" | "externas" | "redex" | "tienda";

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
  /** Los mundos a los que entra: claves de lib/mundos.ts. Siempre hay al menos uno. */
  mundos?: string[];
  is_active: boolean;
  is_superuser: boolean;
  created_at: string | null;
  login_count: number;
  last_login_at: string | null;
  /** Sucursales asignadas. Vacío = es una persona, no un login de sucursal. */
  sucursales: string[];
  /** "redex" | "tienda" — null si no tiene sucursales. */
  sucursal_tipo: string | null;
  /** Cuenta externa (la agencia): solo ve el calendario de su mes y sus tareas. */
  es_externo?: boolean;
  empresa?: string | null;
}

/** El cartelito de una cuenta externa, en la lista y en el editor. */
function MarcaExterna({ empresa }: { empresa?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-sky-800 dark:bg-sky-500/15 dark:text-sky-200">
      <Building2 size={10} aria-hidden /> Externa{empresa ? ` · ${empresa}` : ""}
    </span>
  );
}

/** Los mundos de una cuenta nueva o externa, como chips que se tildan. */
function ChipsDeMundos({ elegidos, puedoDar, onAlternar }: {
  elegidos: Set<string>;
  puedoDar: Set<string>;
  onAlternar: (clave: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {MUNDOS.map((m) => {
        const activo = elegidos.has(m.clave);
        const ajeno = !activo && !puedoDar.has(m.clave);
        return (
          <button
            key={m.clave}
            type="button"
            onClick={() => onAlternar(m.clave)}
            disabled={ajeno}
            aria-pressed={activo}
            title={ajeno ? "No entrás a este mundo: no lo podés dar" : undefined}
            className={`flex min-h-[36px] items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
              activo
                ? "border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-950/40 dark:text-brand-200"
                : "border-slate-300 text-slate-500 hover:border-slate-300 dark:border-slate-700 dark:text-slate-400"
            }`}
          >
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: m.color, opacity: activo ? 1 : 0.35 }} />
            {m.nombre}
          </button>
        );
      })}
    </div>
  );
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
  const [mundos,   setMundos]   = useState<Set<string>>(new Set(user.mundos ?? []));
  // Cuenta externa (la agencia): sin rol y con solo ver el calendario de su
  // mes. El servidor le saca todo lo demás al marcarla (y no deja dárselo).
  const [externo,  setExterno]  = useState<boolean>(!!user.es_externo);
  const [empresa,  setEmpresa]  = useState<string>(user.empresa ?? "");
  // Los mundos que quien edita puede dar: los suyos (un Super Admin, todos).
  const yo = useCurrentUserStore((s) => s.user);
  const puedoDar = new Set(yo?.is_superuser ? MUNDOS.map((m) => m.clave) : (yo?.mundos ?? []));
  const [saving,   setSaving]   = useState(false);

  function toggleMundo(clave: string) {
    setMundos((prev) => {
      const next = new Set(prev);
      if (next.has(clave)) {
        // Sin ningún mundo no se puede entrar a la plataforma: el último no se
        // destilda. Para sacarle el acceso a alguien se desactiva la cuenta.
        if (next.size === 1) { toast.error("Tiene que quedar al menos un mundo."); return prev; }
        next.delete(clave);
      } else {
        next.add(clave);
      }
      return next;
    });
  }

  const role     = allRoles.find((r) => r.id === user.role_id) ?? null;
  const viewOnly = role?.view_only ?? false;
  // Un login de sucursal entra con el nombre del local, no con un mail. Mandar
  // ese "mail" al guardar hacía que el servidor rechazara TODO el guardado
  // (nombre y permisos incluidos): para las sucursales el campo no viaja.
  const esSucursal = user.sucursal_tipo != null || user.sucursales.length > 0;
  const visiblePerms = viewOnly ? allPerms.filter((p) => p.key.endsWith(".view")) : allPerms;
  const grouped  = groupPermissions(visiblePerms);

  const PERM_GROUPS: Record<string, string> = {
    "platform":    t("admin.permGroups.platform"),
    "cenefas":     t("admin.permGroups.cenefas"),
    "analytics":   t("admin.permGroups.analytics"),
    "connections": t("admin.permGroups.connections"),
    "facturacion": t("admin.permGroups.facturacion"),
    "rrss":        t("admin.permGroups.rrss"),
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
    if (!esSucursal && !email.trim()) { toast.error(t("admin.userEditor.emailRequired")); return; }
    if (externo && !empresa.trim()) { toast.error("Decí de qué empresa es la cuenta externa."); return; }
    setSaving(true);
    try {
      await api.patch(`/admin/users/${user.id}`, esSucursal ? { full_name: fullName } : { full_name: fullName, email });
      // Externa o del equipo, antes que los permisos: al pasarla a externa el
      // servidor le saca lo que no le corresponde.
      if (externo !== !!user.es_externo || (externo && empresa.trim() !== (user.empresa ?? ""))) {
        await api.patch(`/admin/users/${user.id}/externo`, { es_externo: externo, empresa: externo ? empresa.trim() : null });
      }
      // Los mundos van antes que los permisos: uno se los puede cambiar a sí
      // mismo, y los permisos propios no (el servidor lo rechaza y corta acá).
      const distintos = (a: Set<string>, b: Set<string>) => a.size !== b.size || [...a].some((x) => !b.has(x));
      const cambiaronMundos = distintos(mundos, new Set(user.mundos ?? []));
      if (cambiaronMundos) {
        await api.patch(`/admin/users/${user.id}/mundos`, { mundos: [...mundos] });
        // Si se editó a sí misma, el menú y el mundo en el que está tienen que
        // enterarse ya, no en la próxima recarga.
        if (useCurrentUserStore.getState().user?.id === user.id) void useCurrentUserStore.getState().refetch();
      }
      // Los permisos viajan solo si cambiaron: los propios el servidor no deja
      // tocarlos, y mandarlos igual daba error aunque nadie los hubiera tocado.
      // A una externa no: tiene los suyos fijos.
      if (!externo && distintos(selected, new Set(user.permissions))) {
        try {
          await api.patch(`/admin/users/${user.id}/permissions`, { permissions: [...selected] });
        } catch (err: any) {
          toast.error(err?.response?.data?.detail ?? t("admin.userEditor.permissionsSaveError"));
          return;
        }
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
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                {esSucursal ? t("admin.userEditor.usuarioLocal") : t("admin.userEditor.email")}
              </label>
              <input
                type={esSucursal ? "text" : "email"}
                className="input text-sm w-full disabled:opacity-60"
                value={email}
                disabled={esSucursal}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("admin.userEditor.emailPlaceholder")}
              />
              {esSucursal && (
                <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">{t("admin.userEditor.sucursalSinMail")}</p>
              )}
            </div>
          </div>

          {/* Mundos: a qué negocios entra. Cada mundo es la plataforma entera
              para ese negocio. Con uno solo entra derecho; con varios, elige. */}
          <div>
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-1">Mundos</p>
            <p className="text-[11px] text-slate-400 dark:text-slate-500 mb-2">
              {user.is_superuser
                ? "Un Super Admin entra a todos los mundos, estén tildados o no."
                : "A qué negocios entra. En cada mundo ve solo lo de ese negocio: su calendario, sus tareas, sus cenefas y sus herramientas. Con uno solo entra directo; con varios, elige al entrar. Qué puede hacer adentro lo siguen diciendo los permisos de abajo."}
            </p>
            <div className="flex flex-wrap gap-2">
              {MUNDOS.map((m) => {
                const activo = mundos.has(m.clave);
                // Nadie da un mundo al que no entra (el servidor lo rechaza):
                // se ve, pero no se puede tildar. Sacarlo sí, si ya lo tenía.
                const ajeno = !activo && !(user.mundos ?? []).includes(m.clave) && !puedoDar.has(m.clave);
                return (
                  <button
                    key={m.clave}
                    type="button"
                    onClick={() => toggleMundo(m.clave)}
                    disabled={ajeno}
                    aria-pressed={activo}
                    title={ajeno ? "No entrás a este mundo: no lo podés dar" : undefined}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
                      activo
                        ? "border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-950/40 dark:text-brand-200"
                        : "border-slate-200 text-slate-500 hover:border-slate-300 dark:border-slate-700 dark:text-slate-400"
                    }`}
                  >
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: m.color, opacity: activo ? 1 : 0.35 }} />
                    {m.nombre}
                  </button>
                );
              })}
            </div>
            {MUNDOS.some((m) => !puedoDar.has(m.clave)) && (
              <p className="mt-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                Los apagados son mundos a los que vos no entrás: solo los puede dar quien entra a ellos.
              </p>
            )}
          </div>

          {/* Cuenta externa: la agencia o un diseñador de afuera. */}
          {!user.is_superuser && !esSucursal && (
            <div className="rounded-xl border border-sky-200 bg-sky-50/60 p-3 dark:border-sky-500/25 dark:bg-sky-500/5">
              <label className="flex cursor-pointer items-start gap-2.5">
                <input
                  type="checkbox"
                  checked={externo}
                  onChange={(e) => setExterno(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-sky-600"
                />
                <span>
                  <span className="block text-sm font-semibold text-slate-800 dark:text-slate-100">Cuenta externa (agencia o diseñador de afuera)</span>
                  <span className="block text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                    Ve solo el calendario del mes actual (con una semana de margen), sus tareas y sus entregas.
                    No ve avisos, notas internas ni ninguna herramienta, y no se le pueden dar permisos de gestión.
                  </span>
                </span>
              </label>
              {externo && (
                <label className="mt-2.5 block">
                  <span className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Empresa</span>
                  <input
                    className="input w-full text-sm"
                    value={empresa}
                    maxLength={120}
                    onChange={(e) => setEmpresa(e.target.value)}
                    placeholder="Agencia, estudio…"
                  />
                </label>
              )}
            </div>
          )}

          {/* Permisos individuales — se prenden/apagan por usuario, no por rol */}
          {externo ? (
            <p className="rounded-xl bg-slate-50 px-3 py-2.5 text-xs text-slate-600 dark:bg-slate-800/50 dark:text-slate-300">
              Una cuenta externa tiene un solo permiso, fijo: ver el calendario de su mes (calendario.view).
            </p>
          ) : (
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
          )}
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
    "facturacion": t("admin.permGroups.facturacion"),
    "rrss":        t("admin.permGroups.rrss"),
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
  const { t, i18n } = useTranslation();
  // "platform.admin" (no requireSuperuser) — el backend (_require_admin_panel
  // en admin.py) ya permite entrar a un Admin no-superuser con ese permiso;
  // el guard client-side tiene que reflejar el mismo criterio, sino un Admin
  // real queda con acceso solo por API directa y nunca desde la UI.
  const { allowed, checked } = usePermissionGuard({ permission: "platform.admin" });
  const [users,       setUsers]       = useState<AdminUser[]>([]);
  const [roles,       setRoles]       = useState<RoleItem[]>([]);
  const [allPerms,    setAllPerms]    = useState<PermissionDef[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [showForm,    setShowForm]    = useState(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null | "new">(undefined as any);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [tempPwd,     setTempPwd]     = useState<{ userId: number; pwd: string } | null>(null);
  const [activeTab,   setActiveTab]   = useState<AdminTab>("usuarios");
  const [lista,       setLista]       = useState<ListaDeUsuarios>("personas");
  const [activityUser, setActivityUser] = useState<AdminUser | null>(null);

  const [form, setForm] = useState({
    email: "", full_name: "", password: "",
    role_id: "" as string | number,
    // Cuenta externa (la agencia): sin rol, con su empresa y sus mundos.
    es_externo: false, empresa: "",
  });
  const [mundosNuevos, setMundosNuevos] = useState<Set<string>>(new Set(["tienda_inglesa"]));
  const yo = useCurrentUserStore((s) => s.user);
  const puedoDarMundos = new Set(yo?.is_superuser ? MUNDOS.map((m) => m.clave) : (yo?.mundos ?? []));
  function alternarMundoNuevo(clave: string) {
    setMundosNuevos((prev) => {
      const next = new Set(prev);
      if (next.has(clave)) {
        if (next.size === 1) { toast.error("Tiene que quedar al menos un mundo."); return prev; }
        next.delete(clave);
      } else {
        next.add(clave);
      }
      return next;
    });
  }

  // Superadmin no se ofrece como rol asignable desde el panel — es un flag
  // reservado para la cuenta principal, no algo que se elija en un select.
  const assignableRoles = roles.filter((r) => r.name !== "Superadmin");

  // Un login de sucursal es un User igual que los demás: lo único que lo
  // distingue es tener una asignación (LocalAsignacion), que el backend
  // devuelve en `sucursales` junto con su tipo.
  const esSucursal = (u: AdminUser) => u.sucursales.length > 0;
  const usuariosPorLista: Record<ListaDeUsuarios, AdminUser[]> = {
    personas: users.filter((u) => !esSucursal(u) && !u.es_externo),
    externas: users.filter((u) => !!u.es_externo),
    redex:    users.filter((u) => esSucursal(u) && u.sucursal_tipo !== "tienda"),
    tienda:   users.filter((u) => esSucursal(u) && u.sucursal_tipo === "tienda"),
  };
  const usuariosVisibles = usuariosPorLista[lista];

  // No disparamos /admin/* hasta confirmar que el usuario tiene acceso al
  // panel (superuser o permiso platform.admin) — evita requests innecesarios
  // (y un toast de error confuso) para cualquier logueado que entre sin serlo.
  useEffect(() => {
    if (!checked) return;
    if (allowed) {
      load();
    } else {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checked, allowed]);

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
      await api.post("/admin/users", form.es_externo
        ? {
          email: form.email, full_name: form.full_name, password: form.password,
          es_externo: true, empresa: form.empresa.trim(), mundos: [...mundosNuevos],
        }
        : {
          email: form.email, full_name: form.full_name, password: form.password,
          role_id: form.role_id === "" ? null : Number(form.role_id),
        });
      toast.success(form.es_externo
        ? `Listo: ${form.full_name} ya puede entrar. Ve su trabajo y el calendario del mes; la primera vez elige su contraseña.`
        : t("admin.createForm.created"));
      setShowForm(false);
      if (form.es_externo) setLista("externas");
      setForm({ email: "", full_name: "", password: "", role_id: "", es_externo: false, empresa: "" });
      setMundosNuevos(new Set(["tienda_inglesa"]));
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
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("admin.toggleActiveError"));
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

  if (checked && !allowed) {
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
        {activeTab === "usuarios" && (lista === "personas" || lista === "externas") && (
          <button
            onClick={() => {
              // Desde la lista de externas, el alta arranca como cuenta externa.
              if (!showForm) setForm((f) => ({ ...f, es_externo: lista === "externas" }));
              setShowForm((v) => !v);
            }}
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
          <Users size={13} /> {t("admin.tabs.users")}
        </button>
        <button onClick={() => setActiveTab("auditoria")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
            activeTab === "auditoria"
              ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
              : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
          }`}>
          <History size={13} /> {t("admin.tabs.auditLog")}
        </button>
        <button onClick={() => setActiveTab("ia")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
            activeTab === "ia"
              ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
              : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
          }`}>
          <Cpu size={13} /> {t("admin.tabs.aiUsage")}
        </button>
      </div>

      {activeTab === "auditoria" && <AuditLogTab />}
      {activeTab === "ia" && (
        <AiUsageTab
          onSelectUser={(u) => {
            if (u.user_id == null) return;
            const known = users.find((x) => x.id === u.user_id);
            setActivityUser(known ?? {
              id: u.user_id, full_name: u.user_email ?? "?", email: u.user_email ?? "",
              role_id: null, role_name: null, permissions: [], is_active: true, is_superuser: false,
              created_at: null, login_count: 0, last_login_at: null, sucursales: [], sucursal_tipo: null,
            });
          }}
        />
      )}

      {activeTab === "usuarios" && (
      <>
      {/* Create user form */}
      {showForm && (
        <form onSubmit={handleCreate} className="card p-5 space-y-4 border-brand-200 border">
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
            <UserPlus size={15} className="text-brand-500" /> {t("admin.createForm.title")}
          </p>
          {/* Del equipo o de afuera: la agencia entra con la vista limitada. */}
          <div className="segmentado w-full sm:w-fit" role="group" aria-label="Tipo de cuenta">
            <button type="button" aria-pressed={!form.es_externo}
              onClick={() => setForm((f) => ({ ...f, es_externo: false }))}
              className="segmento !min-h-[40px] !px-3 text-sm">
              <Users size={14} aria-hidden /> Del equipo
            </button>
            <button type="button" aria-pressed={form.es_externo}
              onClick={() => setForm((f) => ({ ...f, es_externo: true, role_id: "" }))}
              className="segmento !min-h-[40px] !px-3 text-sm">
              <Building2 size={14} aria-hidden /> Externa (agencia)
            </button>
          </div>
          {form.es_externo && (
            <p className="rounded-xl bg-sky-50 px-3 py-2.5 text-xs leading-relaxed text-sky-900 dark:bg-sky-500/10 dark:text-sky-100">
              Entra directo a sus entregas y a sus tareas. Del calendario ve solo el mes actual, con una semana de margen;
              no ve avisos, notas internas ni ninguna herramienta, y no se le pueden dar permisos de gestión.
            </p>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <input required className="input text-sm" placeholder={t("admin.createForm.namePlaceholder")}
              value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
            <input required type="email" className="input text-sm" placeholder={t("admin.createForm.emailPlaceholder")}
              value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
            <input required className="input text-sm" placeholder={t("admin.createForm.passwordPlaceholder")}
              value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
            {form.es_externo ? (
              <input required className="input text-sm" placeholder="Empresa (la agencia, el estudio…)" maxLength={120}
                aria-label="Empresa"
                value={form.empresa} onChange={(e) => setForm((f) => ({ ...f, empresa: e.target.value }))} />
            ) : (
            <div className="relative">
              <select className="input text-sm w-full appearance-none pr-8" value={form.role_id}
                onChange={(e) => setForm((f) => ({ ...f, role_id: e.target.value }))}>
                <option value="">{t("admin.noRole")}</option>
                {assignableRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            </div>
            )}
          </div>
          {form.es_externo && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Mundos donde trabaja</p>
              <ChipsDeMundos elegidos={mundosNuevos} puedoDar={puedoDarMundos} onAlternar={alternarMundoNuevo} />
            </div>
          )}
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
        <div className="px-5 py-3 border-b border-slate-50 dark:border-slate-800 flex items-center gap-3 flex-wrap">
          <Users size={15} className="text-slate-400 shrink-0" />
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            {t("admin.usersTitle", { count: usuariosVisibles.length })}
          </p>
          <div className="ml-auto flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-0.5">
            {([
              ["personas", t("admin.listas.personas"), Users],
              ["externas", t("admin.listas.externas", "Externas"), Building2],
              ["redex",    t("admin.listas.redex"),    Store],
              ["tienda",   t("admin.listas.tienda"),   Store],
            ] as const).map(([clave, etiqueta, Icono]) => (
              <button key={clave} onClick={() => setLista(clave)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all duration-150 ${
                  lista === clave
                    ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
                    : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                }`}>
                <Icono size={12} /> {etiqueta}
                <span className="text-[10px] font-normal text-slate-400">{usuariosPorLista[clave].length}</span>
              </button>
            ))}
          </div>
        </div>
        {loading ? (
          <div className="flex items-center justify-center p-10"><Loader2 size={20} className="animate-spin text-slate-400" /></div>
        ) : (
          <div className="divide-y divide-slate-50 dark:divide-slate-800">
            {usuariosVisibles.length === 0 && (
              <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-10">
                {t("admin.listas.vacia")}
              </p>
            )}
            {usuariosVisibles.map((u) => (
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
                    {u.es_externo && <MarcaExterna empresa={u.empresa} />}
                    {!u.is_active && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">{t("admin.inactive")}</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 dark:text-slate-500 truncate">{u.email}</p>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500">
                    {u.last_login_at
                      ? t("admin.lastLoginWithCount", {
                          date: new Date(u.last_login_at).toLocaleString(i18n.language, {
                            day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
                          }),
                          count: u.login_count,
                        })
                      : t("admin.neverLoggedIn")}
                  </p>
                </div>

                <button onClick={() => setActivityUser(u)} title={t("admin.viewActivity")}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-brand-600 hover:bg-brand-50 transition-all shrink-0">
                  <History size={15} />
                </button>

                {/* Role selector — el Super Admin no se reasigna desde acá, y
                    una cuenta externa no lleva rol (el servidor lo rechaza). */}
                {u.is_superuser ? (
                  <span className="text-[11px] text-slate-400 dark:text-slate-500 italic shrink-0 px-1">—</span>
                ) : u.es_externo ? (
                  <span className="hidden shrink-0 px-1 text-[11px] text-slate-500 dark:text-slate-400 sm:inline">Sin rol</span>
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

      {/* User activity modal */}
      {activityUser && (
        <UserActivityModal
          user={activityUser}
          onClose={() => setActivityUser(null)}
        />
      )}
    </div>
  );
}

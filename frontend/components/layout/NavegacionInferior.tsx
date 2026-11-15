"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarDays, ListChecks, Menu } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";

/**
 * La barra de abajo del teléfono: el calendario, mis tareas y el resto del
 * menú, donde llega el pulgar. Son los mismos links del núcleo del menú
 * lateral, con el mismo permiso; quien no ve el calendario no tiene barra.
 */
export default function NavegacionInferior({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const { t } = useTranslation();
  const { user } = useCurrentUser();
  if (!hasPermission(user, "calendario.view")) return null;

  const items = [
    { href: "/calendario", label: t("sidebar.calendario"), Icono: CalendarDays },
    { href: "/mis-tareas", label: t("sidebar.misTareas", "Mis tareas"), Icono: ListChecks },
  ];

  return (
    <nav
      aria-label={t("sidebar.navegacion", "Navegación principal")}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md dark:border-white/10 dark:bg-navy-900/90 md:hidden"
    >
      <div className="mx-auto flex max-w-md items-stretch px-2">
        {items.map(({ href, label, Icono }) => {
          const activo = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              aria-current={activo ? "page" : undefined}
              className="group flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold"
            >
              <span className={clsx(
                "flex h-8 w-14 items-center justify-center rounded-full transition-all duration-200 ease-suave group-active:scale-90",
                activo ? "bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-200" : "text-slate-500 dark:text-slate-400"
              )}>
                <Icono size={20} />
              </span>
              <span className={activo ? "text-brand-700 dark:text-brand-200" : "text-slate-500 dark:text-slate-400"}>{label}</span>
            </Link>
          );
        })}
        <button
          type="button"
          onClick={onMenu}
          className="group flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400"
        >
          <span className="flex h-8 w-14 items-center justify-center rounded-full transition-all duration-200 group-active:scale-90">
            <Menu size={20} />
          </span>
          {t("sidebar.mas", "Más")}
        </button>
      </div>
    </nav>
  );
}

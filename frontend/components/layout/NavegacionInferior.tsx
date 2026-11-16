"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, CalendarDays, Camera, ClipboardList, Layers, ListChecks, Menu } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import { esExterno } from "@/lib/externos";
import { useAvisos } from "@/store/avisos";
import { usePendientesDeFotos } from "@/lib/colocacion/store";
import { mundoEfectivo, rutaEnMundo, useMundoElegido } from "@/lib/mundos";

/**
 * La barra de abajo del teléfono: el calendario, mis tareas, las entregas y
 * el resto del menú, donde llega el pulgar. Son los mismos links del núcleo del menú
 * lateral, con el mismo permiso; quien no ve el calendario no tiene barra.
 * Los avisos van con su número, como en la campanita: antes solo se veían
 * abriendo el menú.
 *
 * Un local (login de sucursal) no ve el calendario, pero también usa el
 * teléfono: su barra lleva "Fotos" (lo que le pidieron subir, con cuántas le
 * faltan) y "Mi pedido". Antes no tenía barra y todo estaba en el menú.
 */
export default function NavegacionInferior({ onMenu, onAvisos }: { onMenu: () => void; onAvisos: () => void }) {
  const pathname = usePathname();
  const { t } = useTranslation();
  const { user } = useCurrentUser();
  const noLeidos = useAvisos((s) => s.noLeidos);
  const fotos = usePendientesDeFotos((s) => s.pendientes) ?? 0;
  const elegido = useMundoElegido((s) => s.elegido);
  const mundo = mundoEfectivo(user, elegido);
  const veCalendario = hasPermission(user, "calendario.view");
  const esLocal = (user?.assigned_locales?.length ?? 0) > 0;
  if (!veCalendario && !esLocal) return null;

  // Una cuenta externa (la agencia): su trabajo primero, como en el menú.
  const items: { href: string; label: string; Icono: typeof CalendarDays; numero?: number }[] = veCalendario && esExterno(user)
    ? [
      { href: "/entregas", label: t("sidebar.entregas", "Entregas"), Icono: Layers },
      { href: "/mis-tareas", label: t("sidebar.misTareas", "Mis tareas"), Icono: ListChecks },
      { href: "/calendario", label: t("sidebar.calendario"), Icono: CalendarDays },
    ]
    : veCalendario
    ? [
      { href: "/calendario", label: t("sidebar.calendario"), Icono: CalendarDays },
      { href: "/mis-tareas", label: t("sidebar.misTareas", "Mis tareas"), Icono: ListChecks },
      { href: "/entregas", label: t("sidebar.entregas", "Entregas"), Icono: Layers },
    ]
    : [
      { href: "/fotos", label: t("sidebar.fotos", "Fotos"), Icono: Camera, numero: fotos },
      // "Mi pedido" es de Redexpres: en otro mundo no está.
      ...(!mundo || rutaEnMundo("/redexpres/mi-pedido", mundo.clave)
        ? [{ href: "/redexpres/mi-pedido", label: t("sidebar.miPedido"), Icono: ClipboardList }]
        : []),
    ];

  return (
    <nav
      aria-label={t("sidebar.navegacion", "Navegación principal")}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-300 bg-white/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md dark:border-white/10 dark:bg-navy-900/90 md:hidden"
    >
      <div className="mx-auto flex max-w-md items-stretch px-2">
        {items.map(({ href, label, Icono, numero }) => {
          const activo = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              aria-current={activo ? "page" : undefined}
              className="group flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold"
            >
              <span className={clsx(
                "relative flex h-8 w-14 items-center justify-center rounded-full transition-all duration-200 ease-suave group-active:scale-90",
                activo ? "bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-200" : "text-slate-500 dark:text-slate-400"
              )}>
                <Icono size={20} />
                {!!numero && (
                  <span className="absolute right-2.5 top-0 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-none text-white ring-2 ring-white dark:ring-navy-900">
                    {numero > 9 ? "9+" : numero}
                  </span>
                )}
              </span>
              <span className={activo ? "text-brand-700 dark:text-brand-200" : "text-slate-500 dark:text-slate-400"}>{label}</span>
            </Link>
          );
        })}
        <button
          type="button"
          onClick={onAvisos}
          aria-label={noLeidos > 0 ? `${t("sidebar.avisos", "Avisos")}: ${noLeidos} sin leer` : t("sidebar.avisos", "Avisos")}
          className="group flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400"
        >
          <span className="relative flex h-8 w-14 items-center justify-center rounded-full transition-all duration-200 group-active:scale-90">
            <Bell size={20} />
            {noLeidos > 0 && (
              <span className="absolute right-2.5 top-0 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-none text-white ring-2 ring-white dark:ring-navy-900">
                {noLeidos > 9 ? "9+" : noLeidos}
              </span>
            )}
          </span>
          {t("sidebar.avisos", "Avisos")}
        </button>
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

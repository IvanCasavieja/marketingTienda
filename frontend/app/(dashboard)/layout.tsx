"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { useCurrentUserStore } from "@/store/currentUser";
import ErrorBoundary from "@/components/ErrorBoundary";
import ChangePasswordForm from "@/components/ChangePasswordForm";
import { Menu, CalendarDays, ShieldAlert } from "lucide-react";
import { MARCA, mundoEfectivo, mundosDe, rutaEnMundo, useMundoElegido } from "@/lib/mundos";
import FueraDeMundo from "@/components/layout/FueraDeMundo";
import { useTranslation } from "react-i18next";

const Sidebar = dynamic(() => import("@/components/layout/Sidebar"), { ssr: false });
// Dashboard pages use useTranslation() which produces server/client HTML mismatches.
// Wrapping children with ssr:false means the server sends null, the client mounts
// fresh — no hydration reconciliation needed, no #418 errors on any dashboard page.
const ClientOnly = dynamic(() => import("@/components/ClientOnly"), { ssr: false });

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useTranslation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // No hay middleware server-side posible acá: el token vive en localStorage
  // (necesario para mobile Safari, que bloquea la cookie cross-site del backend
  // en Render) y esa cookie tampoco es visible para un middleware.ts del frontend
  // en Vercel, porque pertenece a otro dominio. Por eso la única fuente de verdad
  // es esta llamada a /auth/me — y no pintamos contenido protegido hasta tenerla.
  const [authChecked, setAuthChecked] = useState(false);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const fetchCurrentUser = useCurrentUserStore((s) => s.fetch);

  // El mundo es toda la plataforma vista para un negocio (lib/mundos.ts). Quien
  // entra a varios tiene que elegir uno antes de ver nada; quien entra a uno
  // solo ya está en él.
  const user = useCurrentUserStore((s) => s.user);
  const elegido = useMundoElegido((s) => s.elegido);
  const mundo = mundoEfectivo(user, elegido);
  const faltaElegir = authChecked && !mustChangePassword && !!user && !mundo
    && mundosDe(user).length > 1 && pathname !== "/mundos";
  useEffect(() => {
    if (faltaElegir) router.replace("/mundos");
  }, [faltaElegir, router]);

  // Este es el fetch que dispara el store compartido de currentUser (ver
  // hooks/useCurrentUser.ts) — cualquier página/componente que lo consuma
  // después reusa este resultado en vez de pedir /auth/me de nuevo.
  useEffect(() => {
    fetchCurrentUser()
      .then((data) => {
        setMustChangePassword(!!data?.must_change_password);
        setAuthChecked(true);
      })
      .catch((err) => {
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          router.replace("/login");
        } else {
          // Error de red/servidor: no dejamos al usuario trabado en la pantalla
          // de carga, cada fetch individual va a manejar su propio error.
          setAuthChecked(true);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!authChecked || faltaElegir) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // El backend ya rechaza cualquier otro endpoint con 403 mientras esto esté
  // pendiente (ver PASSWORD_CHANGE_REQUIRED) — este gate es la contraparte en
  // el front: no deja montar ninguna pantalla real hasta que se resuelva.
  if (mustChangePassword) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
        <div className="card w-full max-w-md p-6 animate-fade-in">
          <div className="flex items-center gap-2 mb-1">
            <ShieldAlert size={18} className="text-amber-500" />
            <h1 className="text-base font-bold text-slate-900 dark:text-slate-100">{t("passwordGate.title")}</h1>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
            {t("passwordGate.subtitle")}
          </p>
          <ChangePasswordForm onSuccess={() => setMustChangePassword(false)} />
        </div>
      </div>
    );
  }

  // Elegir el mundo es una pantalla entera, sin menú: todavía no se está en
  // ningún lado.
  if (pathname === "/mundos") {
    return (
      <div className="min-h-screen bg-slate-50 px-4 dark:bg-slate-950 sm:px-8">
        <ErrorBoundary>
          <ClientOnly>{children}</ClientOnly>
        </ErrorBoundary>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="md:hidden flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200 dark:bg-navy-900 dark:border-white/5 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1.5 text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors"
            aria-label={t("common.openMenu")}
          >
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center shrink-0">
              <CalendarDays size={14} className="text-white" />
            </div>
            <p className="text-slate-900 dark:text-white font-bold text-sm">{MARCA}</p>
          </div>
        </header>

        <main className="flex-1 p-3 sm:p-5 lg:p-6 overflow-auto">
          <ErrorBoundary>
            {/* Una herramienta que no es de este mundo no se muestra: se dice
                dónde está y se ofrece pasar. */}
            <ClientOnly>
              {mundo && !rutaEnMundo(pathname, mundo.clave)
                ? <FueraDeMundo pathname={pathname} mundo={mundo} />
                : children}
            </ClientOnly>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}

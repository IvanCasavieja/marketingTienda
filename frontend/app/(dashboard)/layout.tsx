"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { useCurrentUserStore } from "@/store/currentUser";
import ErrorBoundary from "@/components/ErrorBoundary";
import ChangePasswordForm from "@/components/ChangePasswordForm";
import Link from "next/link";
import { Menu, CalendarDays, ShieldAlert, ArrowLeftRight } from "lucide-react";
import { MARCA, mundoEfectivo, mundosDe, rutaEnMundo, useMundoElegido } from "@/lib/mundos";
import FueraDeMundo from "@/components/layout/FueraDeMundo";
import NavegacionInferior from "@/components/layout/NavegacionInferior";
import AvisoDeVentana from "@/components/layout/AvisoDeVentana";
import { INICIO_DE_EXTERNOS, esExterno, rutaDeExterno } from "@/lib/externos";
import { useAvisos } from "@/store/avisos";
import { useTranslation } from "react-i18next";

const Sidebar = dynamic(() => import("@/components/layout/Sidebar"), { ssr: false });
// Dashboard pages use useTranslation() which produces server/client HTML mismatches.
// Wrapping children with ssr:false means the server sends null, the client mounts
// fresh — no hydration reconciliation needed, no #418 errors on any dashboard page.
const ClientOnly = dynamic(() => import("@/components/ClientOnly"), { ssr: false });
// Las entregas de una tarea, encima de todo. Una sola para toda la plataforma:
// la abren la ficha de la acción, el tablero, "Mis tareas" y los avisos.
const VistaEntregas = dynamic(() => import("@/components/calendario/entregas/VistaEntregas"), { ssr: false });

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

  // Una cuenta externa (la agencia) solo tiene sus pantallas: si llega a otra
  // (un link viejo, la barra de direcciones) va a su trabajo. El servidor igual
  // le contesta 403 a todo lo interno: esto es para que no vea una pantalla rota.
  const externo = esExterno(user);
  const fueraDeLoSuyo = authChecked && !mustChangePassword && externo && !rutaDeExterno(pathname);
  useEffect(() => {
    if (fueraDeLoSuyo) router.replace(INICIO_DE_EXTERNOS);
  }, [fueraDeLoSuyo, router]);

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

  if (!authChecked || faltaElegir || fueraDeLoSuyo) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-slate-50 dark:bg-slate-950" role="status" aria-label={t("common.loading")}>
        <div className="relative flex h-14 w-14 items-center justify-center">
          <span className="absolute inset-0 rounded-2xl border-2 border-brand-500/20 border-t-brand-500 animate-spin" />
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-sm shadow-brand-600/30">
            <CalendarDays size={18} className="text-white" />
          </span>
        </div>
        <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">{MARCA}</p>
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
        {/* Mobile top bar: el menú, la marca y en qué mundo se está */}
        <header className="md:hidden flex items-center gap-2 px-2 py-1.5 bg-white/90 backdrop-blur-md border-b border-slate-200 dark:bg-navy-900/90 dark:border-white/5 shrink-0">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="boton-icono"
            aria-label={t("common.openMenu")}
          >
            <Menu size={20} />
          </button>
          <div className="flex min-w-0 items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shrink-0">
              <CalendarDays size={14} className="text-white" />
            </div>
            <p className="truncate text-slate-900 dark:text-white font-bold text-sm">{MARCA}</p>
          </div>
          {mundo && (
            mundosDe(user).length > 1 ? (
              <Link
                href="/mundos"
                title={t("sidebar.cambiarMundo", "Cambiar de mundo")}
                className="ml-auto flex min-h-[36px] min-w-0 items-center gap-1.5 rounded-full border border-slate-200 bg-white py-1 pl-2.5 pr-2 text-xs font-semibold text-slate-700 shadow-sm transition active:scale-95 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
              >
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: mundo.color }} />
                <span className="max-w-[8.5rem] truncate">{mundo.nombre}</span>
                <ArrowLeftRight size={13} className="shrink-0 text-slate-400" />
              </Link>
            ) : (
              <span className="ml-auto flex min-w-0 items-center gap-1.5 px-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: mundo.color }} />
                <span className="max-w-[8.5rem] truncate">{mundo.nombre}</span>
              </span>
            )
          )}
        </header>

        {/* En el teléfono deja lugar abajo para la barra de navegación */}
        <main className="flex-1 p-3 pb-24 sm:p-5 sm:pb-24 md:pb-5 lg:p-6 overflow-auto">
          <ErrorBoundary>
            {/* Una herramienta que no es de este mundo no se muestra: se dice
                dónde está y se ofrece pasar. */}
            <ClientOnly>
              {/* A la agencia, arriba de su trabajo: qué parte del calendario ve. */}
              {externo && user && pathname !== "/perfil" && <AvisoDeVentana user={user} />}
              {mundo && !rutaEnMundo(pathname, mundo.clave)
                ? <FueraDeMundo pathname={pathname} mundo={mundo} />
                : children}
            </ClientOnly>
          </ErrorBoundary>
        </main>
      </div>

      <NavegacionInferior
        onMenu={() => setSidebarOpen(true)}
        onAvisos={() => { setSidebarOpen(true); useAvisos.getState().pedirAbrir(); }}
      />
      <VistaEntregas />
    </div>
  );
}

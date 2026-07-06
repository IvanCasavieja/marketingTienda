"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { authApi } from "@/lib/api";
import ErrorBoundary from "@/components/ErrorBoundary";
import { Menu, BarChart3 } from "lucide-react";
import { useTranslation } from "react-i18next";

const Sidebar = dynamic(() => import("@/components/layout/Sidebar"), { ssr: false });
// Dashboard pages use useTranslation() which produces server/client HTML mismatches.
// Wrapping children with ssr:false means the server sends null, the client mounts
// fresh — no hydration reconciliation needed, no #418 errors on any dashboard page.
const ClientOnly = dynamic(() => import("@/components/ClientOnly"), { ssr: false });

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { t } = useTranslation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // No hay middleware server-side posible acá: el token vive en localStorage
  // (necesario para mobile Safari, que bloquea la cookie cross-site del backend
  // en Render) y esa cookie tampoco es visible para un middleware.ts del frontend
  // en Vercel, porque pertenece a otro dominio. Por eso la única fuente de verdad
  // es esta llamada a /auth/me — y no pintamos contenido protegido hasta tenerla.
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    authApi
      .me()
      .then(() => setAuthChecked(true))
      .catch((err) => {
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          router.replace("/login");
        } else {
          // Error de red/servidor: no dejamos al usuario trabado en la pantalla
          // de carga, cada fetch individual va a manejar su propio error.
          setAuthChecked(true);
        }
      });
  }, []);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="md:hidden flex items-center gap-3 px-4 py-3 bg-navy-900 border-b border-white/5 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1.5 text-slate-400 hover:text-white transition-colors"
            aria-label={t("common.openMenu")}
          >
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-brand-500 flex items-center justify-center shrink-0">
              <BarChart3 size={14} className="text-white" />
            </div>
            <p className="text-white font-bold text-sm">MKTG Platform</p>
          </div>
        </header>

        <main className="flex-1 p-4 sm:p-6 md:p-8 overflow-auto">
          <ErrorBoundary>
            <ClientOnly>{children}</ClientOnly>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}

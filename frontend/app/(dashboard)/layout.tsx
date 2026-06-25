"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { authApi } from "@/lib/api";
import ErrorBoundary from "@/components/ErrorBoundary";
import { Menu, BarChart3 } from "lucide-react";

const Sidebar = dynamic(() => import("@/components/layout/Sidebar"), { ssr: false });
// Dashboard pages use useTranslation() which produces server/client HTML mismatches.
// Wrapping children with ssr:false means the server sends null, the client mounts
// fresh — no hydration reconciliation needed, no #418 errors on any dashboard page.
const ClientOnly = dynamic(() => import("@/components/ClientOnly"), { ssr: false });

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    authApi.me().catch((err) => {
      if (err?.response?.status === 401 || err?.response?.status === 403) {
        router.replace("/login");
      }
    });
  }, []);

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="md:hidden flex items-center gap-3 px-4 py-3 bg-navy-900 border-b border-white/5 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1.5 text-slate-400 hover:text-white transition-colors"
            aria-label="Abrir menú"
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

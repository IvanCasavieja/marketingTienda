"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/layout/Sidebar";
import { authApi } from "@/lib/api";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    authApi.me().catch((err) => {
      // Solo redirigir al login en errores de auth, no en errores de red
      if (err?.response?.status === 401 || err?.response?.status === 403) {
        router.replace("/login");
      }
    });
  }, []);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto max-w-[1400px]">
        {children}
      </main>
    </div>
  );
}

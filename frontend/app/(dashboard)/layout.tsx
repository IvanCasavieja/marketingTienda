"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/layout/Sidebar";
import { authApi } from "@/lib/api";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    authApi.me().catch(() => router.replace("/login"));
  }, []);

  return (
    <div className="flex min-h-screen bg-red-500">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto max-w-[1400px]">
        {children}
      </main>
    </div>
  );
}

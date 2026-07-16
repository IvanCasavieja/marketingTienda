"use client";
import { useEffect } from "react";
import { useCurrentUserStore } from "@/store/currentUser";

/** Usuario actual, compartido entre todos los componentes que lo consumen
 * (ver store/currentUser.ts) — dispara el fetch una sola vez por sesión. */
export function useCurrentUser() {
  const user = useCurrentUserStore((s) => s.user);
  const status = useCurrentUserStore((s) => s.status);
  const fetch = useCurrentUserStore((s) => s.fetch);
  const refetch = useCurrentUserStore((s) => s.refetch);

  useEffect(() => {
    fetch().catch(() => {});
  }, [fetch]);

  return {
    user,
    loading: status === "idle" || status === "loading",
    error: status === "error",
    refetch,
  };
}

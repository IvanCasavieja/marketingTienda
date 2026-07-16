"use client";
import { create } from "zustand";
import { authApi } from "@/lib/api";
import type { CurrentUser } from "@/types";

type Status = "idle" | "loading" | "loaded" | "error";

interface CurrentUserState {
  user: CurrentUser | null;
  status: Status;
  promise: Promise<CurrentUser | null> | null;
  fetch: () => Promise<CurrentUser | null>;
  refetch: () => Promise<CurrentUser | null>;
}

// Antes, cada componente que necesitaba el usuario actual (Sidebar, guards de
// permisos, perfil, etc.) llamaba authApi.me() por su cuenta en su propio
// useEffect — 8+ requests redundantes a /auth/me en cada navegación. Este
// store centraliza el fetch: el primer consumidor que monta dispara la
// llamada, cualquier otro que monte mientras está en vuelo reusa la misma
// promise, y una vez cargado nadie vuelve a pedirlo hasta un refetch() explícito.
export const useCurrentUserStore = create<CurrentUserState>((set, get) => ({
  user: null,
  status: "idle",
  promise: null,

  fetch: () => {
    const state = get();
    if (state.status === "loaded") return Promise.resolve(state.user);
    if (state.promise) return state.promise;

    const promise = authApi.me()
      .then(({ data }) => {
        set({ user: data, status: "loaded", promise: null });
        return data as CurrentUser;
      })
      .catch((err) => {
        set({ status: "error", promise: null });
        throw err;
      });
    set({ status: "loading", promise });
    return promise;
  },

  refetch: () => {
    set({ status: "idle", promise: null });
    return get().fetch();
  },
}));

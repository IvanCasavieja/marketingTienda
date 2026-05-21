"use client";
import { useEffect } from "react";
import { I18nextProvider } from "react-i18next";
import i18n from "@/lib/i18n";

export default function I18nProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Re-apply stored language after hydration
    const stored = localStorage.getItem("mktg_lang");
    if (stored && stored !== i18n.language) {
      i18n.changeLanguage(stored);
    }
  }, []);

  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}

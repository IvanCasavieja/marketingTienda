import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import es from "./locales/es.json";
import en from "./locales/en.json";
import pt from "./locales/pt.json";

const STORAGE_KEY = "mktg_lang";

export const LANGUAGES = [
  { code: "es", label: "Español", flag: "🇪🇸" },
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "pt", label: "Português", flag: "🇧🇷" },
] as const;

export type LangCode = "es" | "en" | "pt";

function getInitialLang(): LangCode {
  if (typeof window === "undefined") return "es";
  return (localStorage.getItem(STORAGE_KEY) as LangCode) ?? "es";
}

i18n.use(initReactI18next).init({
  resources: {
    es: { translation: es },
    en: { translation: en },
    pt: { translation: pt },
  },
  lng: getInitialLang(),
  fallbackLng: "es",
  interpolation: { escapeValue: false },
});

export function setLanguage(code: LangCode) {
  i18n.changeLanguage(code);
  if (typeof window !== "undefined") localStorage.setItem(STORAGE_KEY, code);
}

export default i18n;

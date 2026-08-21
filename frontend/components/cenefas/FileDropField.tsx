"use client";
import { ChangeEvent } from "react";

// Compartido entre RedExpresPanel, RompePreciosPanel y ConvertidorPanel —
// antes vivía adentro de RedExpresPanel.tsx y los otros dos lo importaban
// de ahí (RompePreciosPanel de RedExpresPanel, y RedExpresPanel a su vez de
// RompePreciosPanel tras la unificación a v2), lo que dejó un import
// circular sin que ninguno de los dos lo definiera realmente — rompía el
// build de Next ("Export FileDropField doesn't exist in target module").

export function FileDropField({
  label, hint, accept, file, onChange, icon: Icon, accentColor,
  chooseLabel, readyLabel, searchLabel, dimmed,
}: {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  icon: React.ElementType;
  accentColor: "emerald" | "brand";
  chooseLabel: string;
  readyLabel: string;
  searchLabel: string;
  dimmed?: boolean;
}) {
  const id = label.replace(/\s+/g, "-").toLowerCase();
  const active = !!file;
  const colors = {
    emerald: {
      border: active ? "border-emerald-400 bg-emerald-50" : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-white dark:hover:bg-slate-700",
      icon: active ? "text-emerald-500" : "text-slate-400",
      text: active ? "text-emerald-700 font-medium" : "text-slate-500 dark:text-slate-400",
      badge: "bg-emerald-100 text-emerald-700",
    },
    brand: {
      border: active ? "border-brand-400 bg-brand-50" : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-white dark:hover:bg-slate-700",
      icon: active ? "text-brand-500" : "text-slate-400",
      text: active ? "text-brand-700 font-medium" : "text-slate-500 dark:text-slate-400",
      badge: "bg-brand-100 text-brand-700",
    },
  }[accentColor];

  return (
    <label htmlFor={id} className={`flex flex-col gap-1.5 cursor-pointer transition-opacity ${dimmed ? "opacity-40 pointer-events-none" : ""}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
        <span className="text-xs text-slate-400 dark:text-slate-500">{hint}</span>
      </div>
      <div className={`flex items-center gap-3 px-4 py-3.5 rounded-xl border-2 transition-all duration-150 ${colors.border}`}>
        <Icon size={18} className={`shrink-0 ${colors.icon}`} />
        <span className={`text-sm flex-1 truncate ${colors.text}`}>
          {file ? file.name : chooseLabel}
        </span>
        {!file && (
          <span className="text-xs px-2.5 py-1 rounded-lg bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400 font-medium shrink-0">
            {searchLabel}
          </span>
        )}
        {file && (
          <span className={`text-xs px-2.5 py-1 rounded-lg font-medium shrink-0 ${colors.badge}`}>
            {readyLabel}
          </span>
        )}
      </div>
      <input id={id} type="file" accept={accept} onChange={onChange} className="hidden" />
    </label>
  );
}

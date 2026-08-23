"use client";
import { useState, useRef, useEffect, ChangeEvent } from "react";
import { ChevronDown, Check, Pencil, Trash2, X } from "lucide-react";
import { toast } from "sonner";

// Campos de formulario compartidos por las pantallas de cenefas. Vivían
// dentro de RedExpresPanel y los importaban desde ahí otros paneles, lo que
// ataba componentes genéricos a un destino puntual; al unificarse los
// paneles (08/2026) se mudaron a este archivo.

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

export function ComboField({
  label, value, onChange, storageKey,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  storageKey: string;
}) {
  const [options, setOptions] = useState<string[]>([]);
  const [open,       setOpen]       = useState(false);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editingVal, setEditingVal] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) setOptions(JSON.parse(saved));
    } catch {}
  }, [storageKey]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setEditingIdx(null);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function persist(next: string[]) {
    setOptions(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  }

  function handleSaveCurrent() {
    const v = value.trim();
    if (!v || options.includes(v)) return;
    persist([...options, v]);
    toast.success("Opción guardada");
  }

  function handleDelete(idx: number) {
    persist(options.filter((_, i) => i !== idx));
  }

  function handleEditSave(idx: number) {
    if (!editingVal.trim()) return;
    const next = [...options];
    next[idx] = editingVal.trim();
    persist(next);
    setEditingIdx(null);
  }

  const canSave = !!value.trim() && !options.includes(value.trim());

  return (
    <div ref={ref} className="relative flex flex-col gap-1.5">
      <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
      <div className="flex gap-1 items-stretch">
        <input
          className="input text-sm flex-1 min-w-0"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setOpen(true)}
        />
        {canSave && (
          <button
            type="button"
            onClick={handleSaveCurrent}
            className="shrink-0 px-2.5 text-xs rounded-lg border border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 transition-colors"
          >
            Guardar
          </button>
        )}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 px-2 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
        >
          <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
      </div>

      {open && (
        <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg max-h-52 overflow-y-auto">
          {options.length === 0 ? (
            <p className="px-3 py-3 text-xs text-slate-400 text-center">
              Sin opciones guardadas — escribí un valor y hacé clic en &quot;Guardar&quot;.
            </p>
          ) : options.map((opt, idx) => (
            <div
              key={idx}
              className="flex items-center gap-1.5 px-3 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800 group border-b border-slate-100 dark:border-slate-800 last:border-0"
            >
              {editingIdx === idx ? (
                <>
                  <input
                    autoFocus
                    className="flex-1 text-sm outline-none border-b border-brand-400 bg-transparent"
                    value={editingVal}
                    onChange={(e) => setEditingVal(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleEditSave(idx);
                      if (e.key === "Escape") setEditingIdx(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <button onClick={(e) => { e.stopPropagation(); handleEditSave(idx); }} className="shrink-0 text-emerald-600 hover:text-emerald-700"><Check size={13} /></button>
                  <button onClick={(e) => { e.stopPropagation(); setEditingIdx(null); }} className="shrink-0 text-slate-400 hover:text-slate-600"><X size={13} /></button>
                </>
              ) : (
                <>
                  <span className="flex-1 text-sm text-slate-700 dark:text-slate-300 cursor-pointer truncate" onClick={() => { onChange(opt); setOpen(false); }}>{opt}</span>
                  <button onClick={(e) => { e.stopPropagation(); setEditingIdx(idx); setEditingVal(opt); }} className="shrink-0 p-0.5 text-slate-300 hover:text-brand-500 opacity-0 group-hover:opacity-100"><Pencil size={11} /></button>
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(idx); }} className="shrink-0 p-0.5 text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100"><Trash2 size={11} /></button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Field({ label, placeholder, value, onChange }: {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="input text-sm" />
    </label>
  );
}


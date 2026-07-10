"use client";
import { useMemo, useState } from "react";
import { Search, CheckCircle2 } from "lucide-react";

interface SearchableChecklistProps<T> {
  items: T[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  getId: (item: T) => string;
  getSearchText: (item: T) => string;
  getGroup?: (item: T) => string;
  renderGroupHeader?: (group: string) => React.ReactNode;
  renderLabel: (item: T) => React.ReactNode;
  renderSubtitle?: (item: T) => React.ReactNode;
  renderExtra?: (item: T) => React.ReactNode;
  searchPlaceholder?: string;
  emptyMessage?: (query: string) => string;
}

/** Buscar + tildar un subconjunto de items, con selección persistente (Set de
 * ids) y agrupación opcional. Extraído de ComparisonModal.tsx (precios) para
 * reusar el mismo patrón en otras pantallas (ej. selector de campañas). */
export default function SearchableChecklist<T>({
  items, selected, onToggle, getId, getSearchText, getGroup,
  renderGroupHeader, renderLabel, renderSubtitle, renderExtra,
  searchPlaceholder = "Buscar...", emptyMessage,
}: SearchableChecklistProps<T>) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) => getSearchText(it).toLowerCase().includes(q));
  }, [items, query, getSearchText]);

  const grouped = useMemo(() => {
    if (!getGroup) return { "": filtered };
    const groups: Record<string, T[]> = {};
    for (const it of filtered) {
      const g = getGroup(it);
      if (!groups[g]) groups[g] = [];
      groups[g].push(it);
    }
    return groups;
  }, [filtered, getGroup]);

  return (
    <div className="flex flex-col min-h-0 h-full">
      <div className="p-3 border-b border-slate-100 dark:border-slate-800">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={searchPlaceholder}
            className="input text-xs w-full pl-7 py-1.5"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-4">
        {Object.entries(grouped).map(([group, groupItems]) => (
          <div key={group || "_all"}>
            {getGroup && (
              <div className="mb-1.5">
                {renderGroupHeader ? renderGroupHeader(group) : (
                  <span className="text-xs font-semibold text-slate-500">{group}</span>
                )}
              </div>
            )}
            <div className="space-y-1.5">
              {groupItems.map((it) => {
                const id = getId(it);
                const isSelected = selected.has(id);
                return (
                  <div key={id} className="flex items-start gap-2 group">
                    <div
                      className={`mt-0.5 w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-all cursor-pointer ${
                        isSelected ? "bg-brand-600 border-brand-600" : "border-slate-300 group-hover:border-brand-400"
                      }`}
                      onClick={() => onToggle(id)}
                    >
                      {isSelected && <CheckCircle2 size={9} className="text-white" />}
                    </div>
                    <div onClick={() => onToggle(id)} className="min-w-0 flex-1 cursor-pointer">
                      <p className="text-[11.5px] font-medium text-slate-700 dark:text-slate-300 truncate leading-snug">
                        {renderLabel(it)}
                      </p>
                      {renderSubtitle && (
                        <p className="text-[10.5px] text-slate-400">{renderSubtitle(it)}</p>
                      )}
                    </div>
                    {renderExtra?.(it)}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-xs text-slate-400 text-center py-6">
            {emptyMessage ? emptyMessage(query) : `Sin resultados para "${query}"`}
          </p>
        )}
      </div>
    </div>
  );
}

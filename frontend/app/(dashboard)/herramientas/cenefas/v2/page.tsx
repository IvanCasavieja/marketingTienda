"use client";
import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  Save, Loader2, AlertCircle, CheckCircle2,
  ChevronLeft, ChevronRight, Layers, GitBranch,
  Variable, FolderOpen, Play,
} from "lucide-react";
import { toast } from "sonner";
import { cenefasV2Api } from "@/lib/api";
import { useEditorStore } from "@/store/editor";
import type { CenefaFormat, CenefaTemplateRecord } from "@/types/cenefas";
import ComponentPanel  from "@/components/cenefas/editor/ComponentPanel";
import PropertiesPanel from "@/components/cenefas/editor/PropertiesPanel";
import RulesPanel      from "@/components/cenefas/editor/RulesPanel";
import VariablesPanel  from "@/components/cenefas/editor/VariablesPanel";
import FormatSelector  from "@/components/cenefas/editor/FormatSelector";

const Canvas = dynamic(
  () => import("@/components/cenefas/editor/Canvas"),
  { ssr: false, loading: () => <CanvasPlaceholder /> }
);

function CanvasPlaceholder() {
  return (
    <div className="flex-1 flex items-center justify-center bg-slate-200 rounded-lg">
      <Loader2 size={24} className="animate-spin text-slate-400" />
    </div>
  );
}

export type LeftPanel = "components" | "rules" | "variables";

// ---------------------------------------------------------------------------
// Página principal del editor
// ---------------------------------------------------------------------------

export default function EditorPage() {
  const {
    template, templateId, isDirty,
    leftPanel, setLeftPanel,
    initNew, loadTemplate, markSaved,
    setTemplateName,
  } = useEditorStore();

  const [formats,      setFormats]      = useState<CenefaFormat[]>([]);
  const [savedTmpls,   setSavedTmpls]   = useState<CenefaTemplateRecord[]>([]);
  const [saving,       setSaving]       = useState(false);
  const [nameEditing,  setNameEditing]  = useState(false);
  const [showTmplMenu, setShowTmplMenu] = useState(false);
  const [loadingTmpl,  setLoadingTmpl]  = useState(false);
  const tmplMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    cenefasV2Api.getFormats().then(({ data }) => setFormats(data)).catch(() => {});
    cenefasV2Api.listTemplates().then(({ data }) => setSavedTmpls(data)).catch(() => {});
    initNew();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Cerrar menú de templates al hacer clic fuera
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (tmplMenuRef.current && !tmplMenuRef.current.contains(e.target as Node)) {
        setShowTmplMenu(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  async function handleLoadTemplate(id: string) {
    setLoadingTmpl(true);
    setShowTmplMenu(false);
    try {
      const { data } = await cenefasV2Api.getTemplate(id);
      if (data.definition) loadTemplate(data.id, data.definition);
      else toast.error("Este template no tiene definición de componentes");
    } catch {
      toast.error("Error al cargar el template");
    } finally {
      setLoadingTmpl(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      const payload = { ...template };
      if (templateId) {
        await cenefasV2Api.updateTemplate(templateId, payload);
        toast.success("Template guardado");
      } else {
        const { data } = await cenefasV2Api.createTemplate(payload);
        loadTemplate(data.id, payload);
        // Actualizar lista
        cenefasV2Api.listTemplates().then(({ data: list }) => setSavedTmpls(list)).catch(() => {});
        toast.success("Template creado");
      }
      markSaved();
    } catch {
      toast.error("Error al guardar el template");
    } finally {
      setSaving(false);
    }
  }

  const leftPanelDef: { id: LeftPanel; label: string; icon: React.ReactNode }[] = [
    { id: "components", label: "Componentes", icon: <Layers size={13} />    },
    { id: "rules",      label: "Reglas",       icon: <GitBranch size={13} /> },
    { id: "variables",  label: "Variables",    icon: <Variable size={13} />  },
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)] -m-8 rounded-2xl overflow-hidden border border-slate-200 shadow-card bg-white">

      {/* ── Barra superior ── */}
      <header className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-100 bg-white flex-shrink-0">
        <a
          href="/herramientas/cenefas"
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
        >
          <ChevronLeft size={16} />
        </a>

        {/* Nombre editable */}
        <div className="flex-1 min-w-0">
          {nameEditing ? (
            <input
              autoFocus
              className="text-sm font-semibold text-slate-800 bg-transparent border-b border-brand-400 focus:outline-none w-64"
              value={template.name}
              onChange={(e) => setTemplateName(e.target.value)}
              onBlur={() => setNameEditing(false)}
              onKeyDown={(e) => e.key === "Enter" && setNameEditing(false)}
            />
          ) : (
            <button
              onClick={() => setNameEditing(true)}
              className="text-sm font-semibold text-slate-800 hover:text-brand-600 transition-colors"
            >
              {template.name}
            </button>
          )}
          {isDirty && (
            <span className="ml-2 text-[10px] text-amber-500 font-medium">● Sin guardar</span>
          )}
        </div>

        {/* Selector de formatos */}
        {formats.length > 0 && <FormatSelector formats={formats} />}

        {/* Stats */}
        <div className="flex items-center gap-3 text-xs text-slate-400 border-l border-slate-100 pl-3">
          <span>{template.components.length} comp.</span>
          <span>{template.rules.length} reglas</span>
          <span>{template.variables.length} vars</span>
        </div>

        {/* Cargar template existente */}
        <div className="relative" ref={tmplMenuRef}>
          <button
            onClick={() => setShowTmplMenu((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-600 hover:border-slate-300 hover:text-slate-800 transition-all"
          >
            {loadingTmpl ? <Loader2 size={13} className="animate-spin" /> : <FolderOpen size={13} />}
            Cargar
          </button>
          {showTmplMenu && (
            <div className="absolute right-0 top-full mt-1 w-64 bg-white border border-slate-200 rounded-xl shadow-lg z-50 overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-100">
                <p className="text-[10px] font-semibold text-slate-400 uppercase">Templates guardados</p>
              </div>
              {savedTmpls.length === 0 ? (
                <p className="px-3 py-4 text-xs text-slate-400 text-center">Sin templates guardados</p>
              ) : (
                <div className="max-h-52 overflow-y-auto">
                  {savedTmpls.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => handleLoadTemplate(t.id)}
                      className="w-full text-left px-3 py-2.5 hover:bg-slate-50 text-sm text-slate-700 border-b border-slate-50 last:border-0"
                    >
                      <p className="font-medium truncate">{t.name}</p>
                      <p className="text-[10px] text-slate-400">{t.formats.join(", ")}</p>
                    </button>
                  ))}
                </div>
              )}
              <div className="px-3 py-2 border-t border-slate-100">
                <button
                  onClick={() => { initNew(); setShowTmplMenu(false); }}
                  className="text-xs text-brand-600 hover:text-brand-700 font-medium"
                >
                  + Nuevo template
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Ir al generador */}
        {templateId && (
          <a
            href={`/herramientas/cenefas/v2/generar`}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500 hover:bg-emerald-600 text-white transition-all"
          >
            <Play size={13} />
            Generar
          </a>
        )}

        {/* Guardar */}
        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            isDirty
              ? "bg-brand-600 hover:bg-brand-700 text-white"
              : "bg-slate-100 text-slate-400 cursor-default"
          }`}
        >
          {saving ? (
            <Loader2 size={13} className="animate-spin" />
          ) : isDirty ? (
            <Save size={13} />
          ) : (
            <CheckCircle2 size={13} />
          )}
          {saving ? "Guardando…" : isDirty ? "Guardar" : "Guardado"}
        </button>
      </header>

      {/* ── Área de trabajo ── */}
      <div className="flex flex-1 min-h-0">
        {/* Panel izquierdo */}
        <aside className="w-56 flex-shrink-0 border-r border-slate-100 flex flex-col">
          <div className="flex border-b border-slate-100">
            {leftPanelDef.map(({ id, label, icon }) => (
              <button
                key={id}
                onClick={() => setLeftPanel(id as Parameters<typeof setLeftPanel>[0])}
                className={`flex-1 flex items-center justify-center gap-1 py-2 text-[10px] font-medium transition-colors ${
                  leftPanel === id
                    ? "text-brand-600 border-b-2 border-brand-600"
                    : "text-slate-400 hover:text-slate-600"
                }`}
                title={label}
              >
                {icon}
                <span className="hidden sm:inline">{label.split(" ")[0]}</span>
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-hidden">
            {leftPanel === "components" && <ComponentPanel />}
            {leftPanel === "rules"      && <RulesPanel />}
            {leftPanel === "variables"  && <VariablesPanel />}
          </div>
        </aside>

        {/* Canvas central */}
        <main className="flex-1 overflow-auto bg-slate-100 flex flex-col items-center p-6 gap-4">
          {template.components.length === 0 && (
            <div className="flex items-center gap-2 text-xs text-slate-400 bg-white rounded-lg px-3 py-2 border border-slate-200 self-start">
              <AlertCircle size={13} />
              Agregá componentes desde el panel izquierdo para comenzar a diseñar
            </div>
          )}
          <Canvas />
        </main>

        {/* Panel derecho */}
        <aside className="w-64 flex-shrink-0 border-l border-slate-100">
          <div className="px-4 py-2.5 border-b border-slate-100">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Propiedades
            </p>
          </div>
          <PropertiesPanel />
        </aside>
      </div>
    </div>
  );
}

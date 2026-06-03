"use client";
import { create } from "zustand";
import type {
  CenefaComponent,
  CenefaRule,
  CenefaTemplate,
  CenefaVariable,
} from "@/types/cenefas";

const EMPTY_TEMPLATE: CenefaTemplate = {
  version: "2.0",
  name: "Nuevo template",
  master_format: "a4",
  formats: ["a4"],
  variables: [
    { name: "descripcion",    type: "text",  required: true,  csv_column: "DESCRIPCION" },
    { name: "precio",         type: "price", required: true,  csv_column: "PRECIO"      },
    { name: "oferta",         type: "text",  required: false, csv_column: "OFERTA"      },
    { name: "tipo_promocion", type: "text",  required: false, csv_column: "OFERTADET"   },
  ],
  components: [],
  rules: [],
};

export type LeftPanel = "components" | "rules" | "variables";

interface EditorStore {
  // Datos del template
  templateId: string | null;
  template: CenefaTemplate;
  isDirty: boolean;

  // Estado del editor
  selectedComponentId: string | null;
  activeFormat: string;
  leftPanel: LeftPanel;

  // Inicialización
  initNew: () => void;
  loadTemplate: (id: string, template: CenefaTemplate) => void;
  loadDefinition: (template: CenefaTemplate) => void;
  markSaved: () => void;

  // Template metadata
  setTemplateName: (name: string) => void;
  toggleFormat: (formatId: string) => void;

  // Componentes
  addComponent: (comp: CenefaComponent) => void;
  selectComponent: (id: string | null) => void;
  updateComponent: (id: string, updates: Partial<CenefaComponent>) => void;
  deleteComponent: (id: string) => void;

  // Reglas
  addRule: (rule: CenefaRule) => void;
  updateRule: (id: string, updates: Partial<CenefaRule>) => void;
  deleteRule: (id: string) => void;

  // Variables
  upsertVariable: (variable: CenefaVariable) => void;
  deleteVariable: (name: string) => void;

  // UI
  setActiveFormat: (format: string) => void;
  setLeftPanel: (panel: LeftPanel) => void;

  // Computed (no son estado reactivo — se leen en componentes)
  getSelectedComponent: () => CenefaComponent | null;
}

export const useEditorStore = create<EditorStore>((set, get) => ({
  templateId: null,
  template: { ...EMPTY_TEMPLATE, components: [], rules: [] },
  isDirty: false,
  selectedComponentId: null,
  activeFormat: "a4",
  leftPanel: "components",

  initNew: () =>
    set({
      templateId: null,
      template: { ...EMPTY_TEMPLATE, components: [], rules: [] },
      isDirty: false,
      selectedComponentId: null,
      activeFormat: "a4",
    }),

  loadTemplate: (id, template) =>
    set({
      templateId: id,
      template,
      isDirty: false,
      selectedComponentId: null,
      activeFormat: template.master_format,
    }),

  loadDefinition: (template) =>
    set({
      templateId: null,
      template,
      isDirty: true,
      selectedComponentId: null,
      activeFormat: template.master_format,
    }),

  markSaved: () => set({ isDirty: false }),

  setTemplateName: (name) =>
    set((s) => ({ template: { ...s.template, name }, isDirty: true })),

  toggleFormat: (formatId) =>
    set((s) => {
      const cur = s.template.formats;
      const formats = cur.includes(formatId)
        ? cur.filter((f) => f !== formatId)
        : [...cur, formatId];
      return { template: { ...s.template, formats }, isDirty: true };
    }),

  addComponent: (comp) =>
    set((s) => ({
      template: {
        ...s.template,
        components: [...s.template.components, comp],
      },
      selectedComponentId: comp.id,
      isDirty: true,
    })),

  selectComponent: (id) => set({ selectedComponentId: id }),

  updateComponent: (id, updates) =>
    set((s) => ({
      template: {
        ...s.template,
        components: s.template.components.map((c) =>
          c.id === id ? { ...c, ...updates } : c
        ),
      },
      isDirty: true,
    })),

  deleteComponent: (id) =>
    set((s) => ({
      template: {
        ...s.template,
        components: s.template.components.filter((c) => c.id !== id),
      },
      selectedComponentId:
        s.selectedComponentId === id ? null : s.selectedComponentId,
      isDirty: true,
    })),

  addRule: (rule) =>
    set((s) => ({
      template: { ...s.template, rules: [...s.template.rules, rule] },
      isDirty: true,
    })),

  updateRule: (id, updates) =>
    set((s) => ({
      template: {
        ...s.template,
        rules: s.template.rules.map((r) =>
          r.id === id ? { ...r, ...updates } : r
        ),
      },
      isDirty: true,
    })),

  deleteRule: (id) =>
    set((s) => ({
      template: {
        ...s.template,
        rules: s.template.rules.filter((r) => r.id !== id),
      },
      isDirty: true,
    })),

  upsertVariable: (variable) =>
    set((s) => {
      const exists = s.template.variables.find((v) => v.name === variable.name);
      const variables = exists
        ? s.template.variables.map((v) =>
            v.name === variable.name ? variable : v
          )
        : [...s.template.variables, variable];
      return { template: { ...s.template, variables }, isDirty: true };
    }),

  deleteVariable: (name) =>
    set((s) => ({
      template: {
        ...s.template,
        variables: s.template.variables.filter((v) => v.name !== name),
      },
      isDirty: true,
    })),

  setActiveFormat: (format) => set({ activeFormat: format }),

  setLeftPanel: (panel) => set({ leftPanel: panel }),

  getSelectedComponent: () => {
    const { template, selectedComponentId } = get();
    return (
      template.components.find((c) => c.id === selectedComponentId) ?? null
    );
  },
}));

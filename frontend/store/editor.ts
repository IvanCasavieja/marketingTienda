"use client";
import { create } from "zustand";
import type {
  CenefaComponent,
  CenefaRule,
  CenefaTemplate,
  CenefaVariable,
} from "@/types/cenefas";

// 21 variables estándares para cenefas (2026)
const STANDARD_VARIABLES: CenefaVariable[] = [
  // Precios
  { name: "precioRegular",     type: "price",  required: false, csv_column: "precioRegular"     },
  { name: "precioOferta",      type: "price",  required: false, csv_column: "precioOferta"      },
  { name: "precioOferta2",     type: "price",  required: false, csv_column: "precioOferta2"     },
  { name: "precioOferta3",     type: "price",  required: false, csv_column: "precioOferta3"     },
  { name: "precioOferta4",     type: "price",  required: false, csv_column: "precioOferta4"     },
  // Decimales
  { name: "decimalRegular",    type: "text",   required: false, csv_column: "decimalRegular"    },
  { name: "decimalOferta",     type: "text",   required: false, csv_column: "decimalOferta"     },
  { name: "decimalOferta2",    type: "text",   required: false, csv_column: "decimalOferta2"    },
  { name: "decimalOferta3",    type: "text",   required: false, csv_column: "decimalOferta3"    },
  { name: "decimalOferta4",    type: "text",   required: false, csv_column: "decimalOferta4"    },
  // Identificación y texto
  { name: "codigo",            type: "text",   required: false, csv_column: "codigo"            },
  { name: "descripcion",       type: "text",   required: false, csv_column: "descripcion"       },
  { name: "vigencia",          type: "text",   required: false, csv_column: "vigencia"          },
  { name: "mecanica",          type: "text",   required: false, csv_column: "mecanica"          },
  { name: "aclaracion1",       type: "text",   required: false, csv_column: "aclaracion1"       },
  { name: "aclaracion2",       type: "text",   required: false, csv_column: "aclaracion2"       },
  { name: "aclaracion3",       type: "text",   required: false, csv_column: "aclaracion3"       },
  { name: "legales",           type: "text",   required: false, csv_column: "legales"           },
  // Banco
  { name: "precioBanco",       type: "price",  required: false, csv_column: "precioBanco"       },
  { name: "decimalBanco",      type: "text",   required: false, csv_column: "decimalBanco"      },
  { name: "banco",             type: "text",   required: false, csv_column: "banco"             },
];

const EMPTY_TEMPLATE: CenefaTemplate = {
  version: "2.0",
  name: "Nuevo template",
  master_format: "a4",
  formats: ["a4"],
  variables: STANDARD_VARIABLES,
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

  loadTemplate: (id, template) => {
    // Asegurar que las variables base siempre están presentes
    const existing = new Set(template.variables.map((v) => v.name));
    const merged   = [
      ...template.variables,
      ...EMPTY_TEMPLATE.variables.filter((v) => !existing.has(v.name)),
    ];
    set({
      templateId: id,
      template: { ...template, variables: merged },
      isDirty: false,
      selectedComponentId: null,
      activeFormat: template.master_format,
    });
  },

  loadDefinition: (template) => {
    // Merge: mantener las variables importadas + agregar las base que falten
    const existing = new Set(template.variables.map((v) => v.name));
    const merged   = [
      ...template.variables,
      ...EMPTY_TEMPLATE.variables.filter((v) => !existing.has(v.name)),
    ];
    set({
      templateId: null,
      template: { ...template, variables: merged },
      isDirty: true,
      selectedComponentId: null,
      activeFormat: template.master_format,
    });
  },

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

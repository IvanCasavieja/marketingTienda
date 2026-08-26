"use client";
import { useState } from "react";
import {
  Apple, Beef, Check, Flame, Gift, Loader2, Percent, PartyPopper, Plus,
  ShoppingCart, Snowflake, Sparkles, Store, Tag, Trash2, Wine, X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaDestino } from "@/types/cenefas";

// Primer paso al entrar a Cenefas: elegir a qué mundo se va.
//
// Los mundos son filas de la base, no una lista hardcodeada: desde 08/2026 se
// pueden crear desde acá mismo, sin tocar código ni desplegar. Un mundo solo
// agrupa plantillas — no cambia el Excel, las variables ni el motor.

// Íconos y colores que el backend acepta (ver _ICONOS_VALIDOS /
// _COLORES_VALIDOS en cenefas_v2.py). Se mapean por nombre, no por import
// dinámico: un valor desconocido cae al default en vez de romper la pantalla.
const ICONOS: Record<string, React.ElementType> = {
  Store, PartyPopper, Wine, ShoppingCart, Tag, Percent,
  Sparkles, Flame, Gift, Beef, Apple, Snowflake,
};

const COLORES: Record<string, string> = {
  emerald: "text-emerald-500 bg-emerald-500/10",
  rose:    "text-rose-500 bg-rose-500/10",
  purple:  "text-purple-600 bg-purple-600/10",
  amber:   "text-amber-500 bg-amber-500/10",
  sky:     "text-sky-500 bg-sky-500/10",
  indigo:  "text-indigo-500 bg-indigo-500/10",
  orange:  "text-orange-500 bg-orange-500/10",
  teal:    "text-teal-500 bg-teal-500/10",
};

const COLOR_KEYS = Object.keys(COLORES);
const ICONO_KEYS = Object.keys(ICONOS);

interface DestinoModalProps {
  destinos: CenefaDestino[];
  loading: boolean;
  puedeEditar: boolean;
  onSelect: (slug: string) => void;
  onCreated: (destino: CenefaDestino) => void;
  onDeleted: (slug: string) => void;
}

export default function DestinoModal({
  destinos, loading, puedeEditar, onSelect, onCreated, onDeleted,
}: DestinoModalProps) {
  const { t } = useTranslation();
  const [creando, setCreando] = useState(false);
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [icono, setIcono] = useState("Store");
  const [color, setColor] = useState("emerald");
  // Un mundo nace cobrable. Se destilda para los que pasan por el motor pero
  // no son trabajo facturable: Redexpres y el mundo de pruebas.
  const [cobrable, setCobrable] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [borrando, setBorrando] = useState<string | null>(null);

  function resetForm() {
    setNombre(""); setDescripcion(""); setIcono("Store"); setColor("emerald");
    setCobrable(true);
    setCreando(false);
  }

  async function handleCrear() {
    if (!nombre.trim()) return;
    setGuardando(true);
    try {
      const { data } = await cenefasV2Api.createDestino({
        nombre: nombre.trim(), descripcion: descripcion.trim(), icono, color, cobrable,
      });
      onCreated(data);
      resetForm();
      toast.success(t("cenefas.destino.creado"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setGuardando(false);
    }
  }

  async function handleBorrar(d: CenefaDestino) {
    if (!confirm(t("cenefas.destino.borrarConfirm", { nombre: d.nombre }))) return;
    setBorrando(d.slug);
    try {
      await cenefasV2Api.deleteDestino(d.slug);
      onDeleted(d.slug);
      toast.success(t("cenefas.destino.borrado"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setBorrando(null);
    }
  }

  return (
    <div className="flex items-start justify-center pt-12">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800 w-full max-w-2xl p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">{t("cenefas.destino.title")}</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("cenefas.destino.subtitle")}</p>
          </div>
          {puedeEditar && !creando && (
            <button
              onClick={() => setCreando(true)}
              className="shrink-0 flex items-center gap-1.5 text-xs font-semibold text-brand-600 hover:text-brand-700 transition-colors"
            >
              <Plus size={14} /> {t("cenefas.destino.nuevo")}
            </button>
          )}
        </div>

        {creando && (
          <div className="bg-slate-50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-brand-600 dark:text-brand-400 uppercase tracking-wide">
                {t("cenefas.destino.nuevo")}
              </p>
              <button onClick={resetForm} className="text-slate-400 hover:text-slate-600"><X size={14} /></button>
            </div>

            <input
              autoFocus
              className="input w-full text-sm"
              placeholder={t("cenefas.destino.nombrePlaceholder")}
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && nombre.trim()) handleCrear(); }}
              maxLength={120}
            />
            <input
              className="input w-full text-sm"
              placeholder={t("cenefas.destino.descripcionPlaceholder")}
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              maxLength={300}
            />

            <div className="flex flex-wrap gap-1.5">
              {ICONO_KEYS.map((k) => {
                const Ico = ICONOS[k];
                return (
                  <button
                    key={k}
                    onClick={() => setIcono(k)}
                    className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all border-2 ${
                      icono === k ? "border-brand-400 " + COLORES[color] : "border-transparent bg-slate-100 dark:bg-slate-800 text-slate-400"
                    }`}
                    title={k}
                  >
                    <Ico size={16} />
                  </button>
                );
              })}
            </div>

            <div className="flex flex-wrap gap-1.5">
              {COLOR_KEYS.map((c) => (
                <button
                  key={c}
                  onClick={() => setColor(c)}
                  className={`w-7 h-7 rounded-lg flex items-center justify-center transition-all ${COLORES[c]} ${
                    color === c ? "ring-2 ring-offset-1 ring-brand-400 dark:ring-offset-slate-900" : ""
                  }`}
                  title={c}
                >
                  {color === c && <Check size={12} />}
                </button>
              ))}
            </div>

            <label className="flex items-start gap-2 cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={!cobrable}
                onChange={(e) => setCobrable(!e.target.checked)}
                className="mt-0.5 shrink-0"
              />
              <span className="text-xs text-slate-500 dark:text-slate-400">
                No suma al informe de producción
                <span className="block text-[10px] text-slate-400">
                  Para mundos que no son trabajo facturable (pruebas, Redexpres).
                  Sus cenefas se cuentan igual, pero valorizadas en cero.
                </span>
              </span>
            </label>

            <div className="flex gap-2 pt-1">
              <button
                onClick={handleCrear}
                disabled={!nombre.trim() || guardando}
                className="btn-primary text-xs px-3 py-1.5 disabled:opacity-40"
              >
                {guardando ? <Loader2 size={13} className="animate-spin" /> : null}
                {t("cenefas.destino.crear")}
              </button>
              <button onClick={resetForm} className="btn-secondary text-xs px-3 py-1.5">
                {t("cenefas.cancel")}
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-10">
            <Loader2 size={22} className="animate-spin text-slate-400" />
          </div>
        ) : destinos.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-10">{t("cenefas.destino.vacio")}</p>
        ) : (
          <div className="grid grid-cols-3 gap-3">
            {destinos.map((d) => {
              const Icon = ICONOS[d.icono] ?? Store;
              const colorClass = COLORES[d.color] ?? COLORES.emerald;
              return (
                <div key={d.slug} className="relative group">
                  <button
                    onClick={() => onSelect(d.slug)}
                    className="w-full h-full flex flex-col items-start gap-3 p-4 rounded-xl border-2 border-slate-200 dark:border-slate-700 hover:border-brand-400 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-all text-left"
                  >
                    <span className={`w-10 h-10 rounded-xl flex items-center justify-center ${colorClass}`}>
                      <Icon size={20} />
                    </span>
                    <span>
                      <span className="block text-sm font-semibold text-slate-800 dark:text-slate-100">{d.nombre}</span>
                      <span className="block text-xs text-slate-500 dark:text-slate-400 mt-0.5">{d.descripcion}</span>
                    </span>
                  </button>
                  {puedeEditar && (
                    <button
                      onClick={() => handleBorrar(d)}
                      disabled={borrando === d.slug}
                      className="absolute top-2 right-2 p-1 rounded-lg text-slate-300 dark:text-slate-600 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 opacity-0 group-hover:opacity-100 transition-all"
                      title={t("cenefas.destino.borrar")}
                    >
                      {borrando === d.slug
                        ? <Loader2 size={12} className="animate-spin" />
                        : <Trash2 size={12} />}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

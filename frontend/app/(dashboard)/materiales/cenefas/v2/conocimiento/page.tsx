"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, ChevronLeft, Loader2, Pencil, X } from "lucide-react";
import { toast } from "sonner";
import { cenefasV2Api, type CenefaConocimiento } from "@/lib/api";
import { useSuperuserGuard } from "@/hooks/useSuperuserGuard";

// Lo que el modulo aprendio de como se lo usa, y la decision humana sobre eso.
//
// Nada de lo que aprende se activa solo: nace "propuesto" y alguien aprueba,
// corrige o descarta. Recien lo aprobado entra al contexto del agente. Un
// agente que se auto-alimenta sin control aprende tambien los errores y
// despues los repite con confianza.

const PESTANAS = [
  { estado: "propuesto",  label: "Esperando" },
  { estado: "activo",     label: "Aprobado" },
  { estado: "descartado", label: "Descartado" },
] as const;

const ORIGEN_TEXTO: Record<string, string> = {
  mapeo:           "de un mapeo de columnas que guardaste",
  revision_previa: "de la revisión previa de un Excel",
  grilla:          "de una corrección hecha a mano",
  job:             "de cómo salió una generación",
  manual:          "escrito a mano",
};

const TIPO_TEXTO: Record<string, string> = {
  alias_columna: "Nombre de columna",
  plantilla:     "Plantilla",
  aviso:         "Aviso",
  correccion:    "Corrección",
  preferencia:   "Preferencia",
};

export default function ConocimientoPage() {
  const allowed = useSuperuserGuard();
  const [items, setItems] = useState<CenefaConocimiento[]>([]);
  const [conteos, setConteos] = useState<Record<string, number>>({});
  const [pestana, setPestana] = useState<string>("propuesto");
  const [cargando, setCargando] = useState(true);
  const [trabajando, setTrabajando] = useState<string | null>(null);
  const [editando, setEditando] = useState<string | null>(null);
  const [texto, setTexto] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const [prop, act, desc] = await Promise.all(
        PESTANAS.map((p) => cenefasV2Api.listarConocimiento({ estado: p.estado })),
      );
      setConteos({
        propuesto: prop.data.length,
        activo: act.data.length,
        descartado: desc.data.length,
      });
      setItems({ propuesto: prop.data, activo: act.data, descartado: desc.data }[pestana] ?? []);
    } catch {
      toast.error("No se pudo cargar lo que aprendió");
    } finally {
      setCargando(false);
    }
  }, [pestana]);

  useEffect(() => { cargar(); }, [cargar]);

  async function decidir(item: CenefaConocimiento, estado: string, contenido?: string) {
    setTrabajando(item.id);
    try {
      await cenefasV2Api.decidirConocimiento(item.id, estado, contenido);
      // Se saca de la lista en el acto: ya no pertenece a esta pestaña.
      setItems((prev) => prev.filter((x) => x.id !== item.id));
      setConteos((prev) => ({
        ...prev,
        [pestana]: Math.max(0, (prev[pestana] ?? 1) - 1),
        [estado]: (prev[estado] ?? 0) + 1,
      }));
      setEditando(null);
      toast.success(
        estado === "activo" ? "Aprobado: ya es parte de lo que sabe Tinín"
        : estado === "descartado" ? "Descartado: no se vuelve a proponer"
        : "Guardado",
      );
    } catch {
      toast.error("No se pudo guardar");
    } finally {
      setTrabajando(null);
    }
  }

  if (!allowed) return null;

  return (
    <div className="p-6 space-y-5 max-w-4xl mx-auto">
      <div className="flex items-center gap-3">
        <Link
          href="/materiales/cenefas"
          className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        >
          <ChevronLeft size={18} />
        </Link>
        <div>
          <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">
            Lo que aprendió Tinín
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            El módulo va anotando lo que nota trabajando. Nada se usa hasta que vos lo aprobás.
          </p>
        </div>
      </div>

      <div className="flex gap-1 p-1 rounded-xl bg-slate-100 dark:bg-slate-800/60 w-fit">
        {PESTANAS.map((p) => (
          <button
            key={p.estado}
            onClick={() => setPestana(p.estado)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              pestana === p.estado
                ? "bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-100 shadow-sm"
                : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            }`}
          >
            {p.label}
            {(conteos[p.estado] ?? 0) > 0 && (
              <span className="ml-1.5 text-[10px] opacity-70">{conteos[p.estado]}</span>
            )}
          </button>
        ))}
      </div>

      {cargando && (
        <div className="card p-10 flex items-center justify-center text-slate-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}

      {!cargando && items.length === 0 && (
        <div className="card p-8 text-center space-y-1">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {pestana === "propuesto"
              ? "Nada esperando. Cuando el módulo note algo, aparece acá."
              : pestana === "activo"
              ? "Todavía no aprobaste nada."
              : "Nada descartado."}
          </p>
          {pestana === "propuesto" && (
            <p className="text-[11px] text-slate-400">
              Aprende de los mapeos de columnas que guardás y de las revisiones de los Excel.
            </p>
          )}
        </div>
      )}

      {!cargando && items.map((item) => (
        <div key={item.id} className="card p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              {editando === item.id ? (
                <textarea
                  className="input text-sm w-full resize-none"
                  rows={2}
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  autoFocus
                />
              ) : (
                <p className="text-sm text-slate-700 dark:text-slate-200">{item.contenido}</p>
              )}
              <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1.5">
                {TIPO_TEXTO[item.tipo] ?? item.tipo}
                {" · "}
                {item.veces_visto === 1 ? "visto 1 vez" : `visto ${item.veces_visto} veces`}
                {" · "}
                {ORIGEN_TEXTO[item.origen] ?? item.origen}
                {item.detalle?.confianza ? ` · confianza ${item.detalle.confianza}` : ""}
              </p>
            </div>
            {item.veces_visto > 1 && (
              <span className="shrink-0 text-[10px] font-semibold px-2 py-1 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500">
                {item.veces_visto}×
              </span>
            )}
          </div>

          {item.estado === "propuesto" && (
            <div className="flex gap-2 flex-wrap">
              {editando === item.id ? (
                <>
                  <button
                    onClick={() => decidir(item, "activo", texto)}
                    disabled={trabajando === item.id || !texto.trim()}
                    className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5 disabled:opacity-40"
                  >
                    {trabajando === item.id
                      ? <Loader2 size={12} className="animate-spin" />
                      : <Check size={12} />}
                    Guardar y aprobar
                  </button>
                  <button onClick={() => setEditando(null)} className="btn-secondary text-xs px-3 py-1.5">
                    Cancelar
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => decidir(item, "activo")}
                    disabled={trabajando === item.id}
                    className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5 disabled:opacity-40"
                  >
                    {trabajando === item.id
                      ? <Loader2 size={12} className="animate-spin" />
                      : <Check size={12} />}
                    Aprobar
                  </button>
                  <button
                    onClick={() => { setEditando(item.id); setTexto(item.contenido); }}
                    className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5"
                  >
                    <Pencil size={12} /> Corregir
                  </button>
                  <button
                    onClick={() => decidir(item, "descartado")}
                    disabled={trabajando === item.id}
                    className="text-xs px-3 py-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors flex items-center gap-1.5"
                  >
                    <X size={12} /> Descartar
                  </button>
                </>
              )}
            </div>
          )}

          {item.estado === "activo" && (
            <button
              onClick={() => decidir(item, "descartado")}
              disabled={trabajando === item.id}
              className="text-xs text-slate-400 hover:text-rose-600 transition-colors"
            >
              Sacar de lo que sabe Tinín
            </button>
          )}
          {item.estado === "descartado" && (
            <button
              onClick={() => decidir(item, "propuesto")}
              disabled={trabajando === item.id}
              className="text-xs text-slate-400 hover:text-brand-600 transition-colors"
            >
              Volver a considerarlo
            </button>
          )}
        </div>
      ))}

      {!cargando && pestana === "propuesto" && items.length > 0 && (
        <p className="text-[11px] text-slate-400 dark:text-slate-500">
          «Visto N veces» es cuántas veces el módulo se topó con lo mismo. Cuanto más alto,
          más evidencia: algo que pasó una sola vez puede ser el error de ese día.
        </p>
      )}
    </div>
  );
}

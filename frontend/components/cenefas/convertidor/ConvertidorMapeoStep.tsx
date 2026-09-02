"use client";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Loader2, Save, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  convertidorApi,
  type BancoPreset,
  type ConvertidorColumna,
  type ConvertidorMapeo,
  type OfertaConPrecios,
} from "@/lib/api";
import { varDef } from "@/lib/cenefaVariables";
import TininMapeo from "./TininMapeo";

// Paso previo a convertir: resolver las variables EXTRA, las que el
// Convertidor no puede deducir solo. Ninguna es obligatoria.
//
// Cada una se resuelve de una de dos formas, a elección:
//
//   Columna  -> se lee de una columna del Excel, fila por fila.
//   Escribir -> el mismo texto para todas las filas.
//
// La segunda hace falta porque el export de gestión no trae nunca vigencia
// ni legales: esos textos los escribe una persona, no salen de ninguna
// columna. Por eso esas dos arrancan en modo "Escribir".
//
// Las demás variables (codigo, descripcion, precioRegular, precioOferta,
// mecanica y los decimales) no aparecen acá porque el Convertidor las
// resuelve solo: salen de columnas fijas del export o las calcula.

const SIN_MAPEAR = "";

type Modo = "columna" | "texto" | "calcular";

// "calcular" es un modo aparte, SOLO para precioBanco: precioBanco =
// precioOferta × multiplicador, para descuentos bancarios que Tienda Inglesa
// define como porcentaje fijo ("15% extra con Club Card Scotia") en vez de
// una columna que gestión traiga calculada por producto (ver
// ConvertidorBancoPreset en el backend).
const MODOS_PRECIO_BANCO: Modo[] = ["columna", "texto", "calcular"];
const MODOS_DEFAULT: Modo[] = ["columna", "texto"];

// Sentinel del <select> de bancos para "ninguno de la lista, quiero cargar
// uno nuevo" -- nunca puede chocar con un id real (son UUID).
const BANCO_NUEVO = "__nuevo__";

// Variables que no vienen nunca en el export de gestión: arrancan listas para
// escribir, en vez de obligar a buscar una columna que no existe.
//
// precioBanco queda afuera a propósito: es un precio y lo normal es que salga
// de una columna, no que alguien escriba el mismo importe para todas las
// filas.
const ARRANCAN_EN_TEXTO = new Set([
  "vigencia", "legales", "banco", "dia", "mes", "año",
]);

interface Props {
  columnas: ConvertidorColumna[];
  variablesMapeables: string[];
  /**
   * Campos de entrada que el Convertidor ya reconoció en esta hoja (codigo,
   * precio, oferta, ofertaDet...).
   */
  camposReconocidos: string[];
  /**
   * {variable: campo_de_entrada} -- si ese campo está en camposReconocidos, la
   * variable NO se pide a mano: el Convertidor ya la calcula. Hoy es una sola,
   * tipoOferta ← la columna OFERTA (leída junto con OFERTADET).
   */
  resueltaPorCampo: Record<string, string>;
  /**
   * La columna OFERTA trae precios en vez del titular de la mecánica. null = está
   * bien. La app no lo cambia sola: lo propone y la persona decide.
   */
  ofertaConPrecios: OfertaConPrecios | null;
  /** {campo: qué es} -- a qué campos se puede reasignar una columna. */
  camposAsignables: Record<string, string>;
  totalFilas: number;
  /**
   * El archivo subido y la hoja que se está mapeando. Van juntos porque el
   * panel de Tinín vuelve a leer el Excel para mirar las columnas que el
   * Convertidor NO reconoció -- que son justo las que no aparecen en esta
   * pantalla, porque acá se mapea al revés (variable -> columna).
   */
  excel?: File | null;
  hoja?: string;
  /** Mundo al que se apunta, para filtrar y etiquetar las plantillas. */
  destino?: string | null;
  onBack: () => void;
  onConfirm: (
    mapeo: Record<string, string>,
    valores: Record<string, string>,
    campos: Record<string, string>,
    bancoCalculado: { nombre: string; multiplicador: number } | null,
  ) => void;
  converting: boolean;
}

export default function ConvertidorMapeoStep({
  columnas, variablesMapeables, camposReconocidos, resueltaPorCampo,
  ofertaConPrecios, camposAsignables, totalFilas,
  destino, excel, hoja, onBack, onConfirm, converting,
}: Props) {
  const { t } = useTranslation();
  const [mapeo, setMapeo] = useState<Record<string, string>>({});
  const [valores, setValores] = useState<Record<string, string>>({});
  const [modos, setModos] = useState<Record<string, Modo>>(() =>
    Object.fromEntries(
      variablesMapeables.map((v) => [v, ARRANCAN_EN_TEXTO.has(v) ? "texto" : "columna"]),
    ),
  );
  const [plantillas, setPlantillas] = useState<ConvertidorMapeo[]>([]);
  const [plantillaId, setPlantillaId] = useState("");
  const [nombreNuevo, setNombreNuevo] = useState("");
  const [guardando, setGuardando] = useState(false);
  // {nombre_de_columna: campo} -- el override de esta corrida. Arranca vacío: si
  // nadie acepta el aviso, el archivo se lee exactamente como se leía antes.
  const [camposForzados, setCamposForzados] = useState<Record<string, string>>({});

  // Presets de banco (modo "calcular" de precioBanco) -- ver BANCO_NUEVO.
  const [bancos, setBancos] = useState<BancoPreset[]>([]);
  const [bancoPresetId, setBancoPresetId] = useState("");
  const [bancoNombreNuevo, setBancoNombreNuevo] = useState("");
  const [bancoMultiplicadorNuevo, setBancoMultiplicadorNuevo] = useState("");
  const [guardandoBanco, setGuardandoBanco] = useState(false);

  useEffect(() => {
    convertidorApi.listarMapeos(destino ?? undefined)
      .then(({ data }) => setPlantillas(data))
      .catch(() => toast.error(t("convertidor.mapeo.errorPlantillas")));
  }, [destino, t]);

  useEffect(() => {
    convertidorApi.listarBancos()
      .then(({ data }) => setBancos(data))
      .catch(() => toast.error(t("convertidor.mapeo.errorBancos")));
  }, [t]);

  // Elegir un preset de la lista completa el nombre del banco como
  // conveniencia (para el cartel de Club Card) -- se puede editar o borrar
  // a mano después, no queda bloqueado.
  function elegirBancoPreset(id: string) {
    setBancoPresetId(id);
    const b = bancos.find((x) => x.id === id);
    if (b) {
      setValores((prev) => ({ ...prev, banco: b.nombre }));
      setModos((prev) => ({ ...prev, banco: "texto" }));
    }
  }

  async function guardarBancoPreset() {
    const nombre = bancoNombreNuevo.trim();
    const multiplicador = parseFloat(bancoMultiplicadorNuevo.replace(",", "."));
    if (!nombre || !Number.isFinite(multiplicador) || multiplicador <= 0) return;
    setGuardandoBanco(true);
    try {
      const { data } = await convertidorApi.guardarBanco({ nombre, multiplicador });
      setBancos((prev) => {
        const resto = prev.filter((b) => b.id !== data.id);
        return [...resto, data].sort((a, b) => a.nombre.localeCompare(b.nombre));
      });
      elegirBancoPreset(data.id);
      setBancoNombreNuevo("");
      setBancoMultiplicadorNuevo("");
      toast.success(t("convertidor.mapeo.bancoGuardado"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setGuardandoBanco(false);
    }
  }

  const bancoSeleccionado = bancos.find((b) => b.id === bancoPresetId);
  // Solo cuenta si precioBanco de verdad está en modo "calcular" -- cambiar a
  // "Columna"/"Texto" sin tocar el preset elegido no debe seguir aplicándolo.
  const bancoCalculado = modos["precioBanco"] === "calcular" && bancoSeleccionado
    ? { nombre: bancoSeleccionado.nombre, multiplicador: bancoSeleccionado.multiplicador }
    : null;

  // Si el archivo no trae la columna que la plantilla nombra, ese campo queda
  // vacío en vez de aplicarse a ciegas: mejor que la persona lo vea faltar.
  function aplicarPlantilla(id: string) {
    setPlantillaId(id);
    if (!id) {
      setMapeo({});
      setValores({});
      return;
    }
    const p = plantillas.find((x) => x.id === id);
    if (!p) return;
    const disponibles = new Set(columnas.map((c) => c.nombre));
    const aplicado: Record<string, string> = {};
    const faltantes: string[] = [];
    for (const [variable, col] of Object.entries(p.mapeo)) {
      if (disponibles.has(col)) aplicado[variable] = col;
      else faltantes.push(col);
    }
    const fijos = p.valores ?? {};
    setMapeo(aplicado);
    setValores(fijos);
    // El modo de cada variable sale de la plantilla: si trae texto fijo va a
    // "Escribir", si trae columna va a "Columna", y si no trae nada queda
    // como estaba.
    setModos((prev) => {
      const next = { ...prev };
      for (const v of variablesMapeables) {
        if (fijos[v]) next[v] = "texto";
        else if (aplicado[v]) next[v] = "columna";
      }
      return next;
    });
    setNombreNuevo(p.nombre);
    if (faltantes.length) {
      toast.warning(t("convertidor.mapeo.columnasFaltantes", { columnas: faltantes.join(", ") }));
    }
  }

  async function guardarPlantilla() {
    const nombre = nombreNuevo.trim();
    if (!nombre) return;
    setGuardando(true);
    try {
      const { data } = await convertidorApi.guardarMapeo({ nombre, destino: destino ?? null, mapeo, valores });
      setPlantillas((prev) => {
        const resto = prev.filter((p) => p.id !== data.id);
        return [...resto, data].sort((a, b) => a.nombre.localeCompare(b.nombre));
      });
      setPlantillaId(data.id);
      toast.success(t("convertidor.mapeo.plantillaGuardada"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setGuardando(false);
    }
  }

  async function borrarPlantilla() {
    const p = plantillas.find((x) => x.id === plantillaId);
    if (!p || !confirm(t("convertidor.mapeo.borrarConfirm", { nombre: p.nombre }))) return;
    try {
      await convertidorApi.borrarMapeo(p.id);
      setPlantillas((prev) => prev.filter((x) => x.id !== p.id));
      setPlantillaId("");
      toast.success(t("convertidor.mapeo.plantillaBorrada"));
    } catch {
      toast.error(t("convertidor.unknownError"));
    }
  }

  // Una misma columna asignada a dos variables casi siempre es un descuido.
  const duplicadas = useMemo(() => {
    const cuenta = new Map<string, number>();
    Object.values(mapeo).forEach((c) => c && cuenta.set(c, (cuenta.get(c) ?? 0) + 1));
    return new Set([...cuenta.entries()].filter(([, n]) => n > 1).map(([c]) => c));
  }, [mapeo]);

  // Variables que el Convertidor ya resuelve solo en esta hoja, así que no hay
  // nada que preguntar. El caso real: el export de gestión trae una columna
  // OFERTA y de ahí sale tipoOferta (leída junto con OFERTADET), pero tipoOferta
  // igual aparecía en esta lista pidiendo que alguien la mapeara. Y lo mapeado a
  // mano GANA sobre lo calculado, así que mapearla "por prolijidad" empeoraba el
  // resultado: a la cocarda iba el texto crudo de OFERTA ("Coca Cola Zero 2.25 L
  // 2x$299") en vez del literal limpio que extrae el motor.
  const yaResueltas = useMemo(() => {
    const campos = new Set(camposReconocidos);
    return new Set(
      Object.entries(resueltaPorCampo)
        .filter(([variable, campo]) => variablesMapeables.includes(variable) && campos.has(campo))
        .map(([variable]) => variable),
    );
  }, [camposReconocidos, resueltaPorCampo, variablesMapeables]);

  // Una ya resuelta que TIENE algo puesto sigue mostrándose: pasa cuando una
  // plantilla guardada de antes trae ese mapeo. Se ve y se puede sacar, en vez
  // de desaparecer con un valor activo escondido atrás.
  const variablesVisibles = useMemo(
    () => variablesMapeables.filter(
      (v) => !yaResueltas.has(v) || mapeo[v] || valores[v]?.trim(),
    ),
    [variablesMapeables, yaResueltas, mapeo, valores],
  );

  // Solo viaja lo del modo activo de cada variable: si alguien mapeó una
  // columna y después pasó a "Escribir", esa columna ya no cuenta. Y solo de las
  // visibles: una variable que el Convertidor ya resuelve no manda mapeo, ni
  // aunque una plantilla vieja la traiga.
  const mapeoEfectivo = useMemo(
    () => Object.fromEntries(
      variablesVisibles
        .filter((v) => (modos[v] ?? "columna") === "columna" && mapeo[v])
        .map((v) => [v, mapeo[v]]),
    ),
    [variablesVisibles, modos, mapeo],
  );
  const valoresEfectivos = useMemo(
    () => Object.fromEntries(
      variablesVisibles
        .filter((v) => modos[v] === "texto" && valores[v]?.trim())
        .map((v) => [v, valores[v].trim()]),
    ),
    [variablesVisibles, modos, valores],
  );

  // Cuenta las resueltas de las tres formas: una variable con texto escrito
  // o con un preset de banco elegido está tan resuelta como una con columna
  // asignada.
  const asignadas = variablesVisibles.filter((v) => {
    if (v === "precioBanco" && modos[v] === "calcular") return !!bancoCalculado;
    return (modos[v] === "texto" ? valores[v] : mapeo[v])?.trim();
  }).length;

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      <div className="card p-5 space-y-1">
        <h2 className="text-base font-bold text-slate-800 dark:text-slate-100">
          {t("convertidor.mapeo.titulo")}
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {t("convertidor.mapeo.subtitulo", { filas: totalFilas, columnas: columnas.length })}
        </p>
      </div>

      {/* Las columnas que el Convertidor NO reconoce no aparecen en esta
          pantalla -- acá se mapea variable -> columna, y esas quedan afuera de
          las dos puntas. Antes se ignoraban en silencio; ahora Tinín las
          levanta acá, que es el único momento del flujo en que alguien está
          mirando las columnas del archivo. */}
      {ofertaConPrecios && (
        <AvisoOfertaConPrecios
          aviso={ofertaConPrecios}
          campos={camposAsignables}
          elegido={camposForzados[ofertaConPrecios.columna]}
          onElegir={(campo) =>
            setCamposForzados((prev) => {
              const next = { ...prev };
              if (campo === undefined) delete next[ofertaConPrecios.columna];
              else next[ofertaConPrecios.columna] = campo;
              return next;
            })
          }
        />
      )}

      {excel && <TininMapeo excel={excel} hoja={hoja} />}

      {/* Plantillas guardadas */}
      <div className="card p-5 space-y-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
          {t("convertidor.mapeo.plantillas")}
        </p>
        <div className="flex gap-2 items-center flex-wrap">
          <select
            className="input text-sm flex-1 min-w-[220px]"
            value={plantillaId}
            onChange={(e) => aplicarPlantilla(e.target.value)}
          >
            <option value="">{t("convertidor.mapeo.sinPlantilla")}</option>
            {plantillas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}{p.destino ? "" : ` · ${t("convertidor.mapeo.paraTodos")}`}
              </option>
            ))}
          </select>
          {plantillaId && (
            <button
              type="button"
              onClick={borrarPlantilla}
              className="shrink-0 p-2 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors"
              title={t("convertidor.mapeo.borrar")}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
        <div className="flex gap-2 items-center">
          <input
            className="input text-sm flex-1"
            placeholder={t("convertidor.mapeo.nombrePlantillaPlaceholder")}
            value={nombreNuevo}
            onChange={(e) => setNombreNuevo(e.target.value)}
            maxLength={120}
          />
          <button
            type="button"
            onClick={guardarPlantilla}
            disabled={!nombreNuevo.trim() || asignadas === 0 || guardando}
            className="btn-secondary text-xs px-3 py-2 flex items-center gap-1.5 disabled:opacity-40 shrink-0"
          >
            {guardando ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            {t("convertidor.mapeo.guardarPlantilla")}
          </button>
        </div>
      </div>

      {/* Mapeo variable -> columna */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            {t("convertidor.mapeo.variables")}
          </p>
          <span className="text-xs text-slate-400">
            {t("convertidor.mapeo.asignadas", { n: asignadas, total: variablesVisibles.length })}
          </span>
        </div>

        {/* Sin banner de "ya resueltas" (2026-08-29): una variable que el
            Convertidor resuelve solo directamente no aparece en la lista, y
            eso alcanza — anunciarlo era ruido. */}
        <div className="space-y-2">
          {variablesVisibles.map((variable) => {
            const def = varDef(variable);
            const modo = modos[variable] ?? "columna";
            const valor = mapeo[variable] ?? SIN_MAPEAR;
            const texto = valores[variable] ?? "";
            const col = columnas.find((c) => c.nombre === valor);
            return (
              <div key={variable} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-3 items-start">
                <div className="min-w-0 pt-1.5">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 font-mono truncate">
                    {variable}
                  </p>
                  {def && (
                    <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">{def.desc}</p>
                  )}
                </div>
                <div className="min-w-0 space-y-1.5">
                  {/* Columna del Excel, un texto igual para todas las filas,
                      o (solo precioBanco) calculado como precioOferta ×
                      multiplicador de un preset de banco. */}
                  <div className="flex gap-1 p-0.5 rounded-lg bg-slate-100 dark:bg-slate-800/60 w-fit">
                    {(variable === "precioBanco" ? MODOS_PRECIO_BANCO : MODOS_DEFAULT).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setModos((prev) => ({ ...prev, [variable]: m }))}
                        className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                          modo === m
                            ? "bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-100 shadow-sm"
                            : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                        }`}
                      >
                        {t(
                          m === "columna" ? "convertidor.mapeo.modoColumna"
                          : m === "texto" ? "convertidor.mapeo.modoTexto"
                          : "convertidor.mapeo.modoCalcular",
                        )}
                      </button>
                    ))}
                  </div>

                  {modo === "calcular" ? (
                    <div className="space-y-1.5">
                      <select
                        className="input text-sm w-full"
                        value={bancoPresetId}
                        onChange={(e) =>
                          e.target.value === BANCO_NUEVO
                            ? setBancoPresetId(BANCO_NUEVO)
                            : elegirBancoPreset(e.target.value)
                        }
                      >
                        <option value="">{t("convertidor.mapeo.elegiBanco")}</option>
                        {bancos.map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.nombre} · ×{b.multiplicador}
                          </option>
                        ))}
                        <option value={BANCO_NUEVO}>{t("convertidor.mapeo.agregarBanco")}</option>
                      </select>
                      {bancoPresetId === BANCO_NUEVO && (
                        <div className="flex gap-1.5">
                          <input
                            className="input text-sm flex-1"
                            placeholder={t("convertidor.mapeo.nombreBancoPlaceholder")}
                            value={bancoNombreNuevo}
                            onChange={(e) => setBancoNombreNuevo(e.target.value)}
                            maxLength={120}
                          />
                          <input
                            className="input text-sm w-24"
                            placeholder={t("convertidor.mapeo.multiplicadorPlaceholder")}
                            value={bancoMultiplicadorNuevo}
                            onChange={(e) => setBancoMultiplicadorNuevo(e.target.value)}
                          />
                          <button
                            type="button"
                            onClick={guardarBancoPreset}
                            disabled={!bancoNombreNuevo.trim() || !bancoMultiplicadorNuevo.trim() || guardandoBanco}
                            className="btn-secondary text-xs px-2.5 shrink-0 disabled:opacity-40"
                            title={t("convertidor.mapeo.guardarBanco")}
                          >
                            {guardandoBanco ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                          </button>
                        </div>
                      )}
                      {bancoSeleccionado && (
                        <p className="text-[11px] text-slate-400 dark:text-slate-500">
                          {t("convertidor.mapeo.bancoAplicado", { multiplicador: bancoSeleccionado.multiplicador })}
                        </p>
                      )}
                    </div>
                  ) : modo === "columna" ? (
                    <>
                      <select
                        className={`input text-sm w-full ${duplicadas.has(valor) ? "border-amber-400" : ""}`}
                        value={valor}
                        onChange={(e) =>
                          setMapeo((prev) => {
                            const next = { ...prev };
                            if (e.target.value) next[variable] = e.target.value;
                            else delete next[variable];
                            return next;
                          })
                        }
                      >
                        <option value="">{t("convertidor.mapeo.sinAsignar")}</option>
                        {columnas.map((c) => (
                          <option key={c.nombre} value={c.nombre}>{c.nombre}</option>
                        ))}
                      </select>
                      {col && col.muestras.length > 0 && (
                        <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">
                          {col.muestras.join(" · ")}
                        </p>
                      )}
                      {duplicadas.has(valor) && (
                        <p className="text-[11px] text-amber-600 dark:text-amber-400">
                          {t("convertidor.mapeo.columnaRepetida")}
                        </p>
                      )}
                    </>
                  ) : (
                    <input
                      className="input text-sm w-full"
                      value={texto}
                      placeholder={t("convertidor.mapeo.textoPlaceholder", { n: totalFilas })}
                      onChange={(e) =>
                        setValores((prev) => {
                          const next = { ...prev };
                          if (e.target.value) next[variable] = e.target.value;
                          else delete next[variable];
                          return next;
                        })
                      }
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <p className="text-xs text-slate-400 dark:text-slate-500 pt-1">
          {t("convertidor.mapeo.opcional")}
        </p>
      </div>

      <div className="flex justify-between gap-3">
        <button onClick={onBack} className="btn-secondary flex items-center gap-2">
          <ArrowLeft size={15} /> {t("convertidor.mapeo.volver")}
        </button>
        <button
          onClick={() => onConfirm(mapeoEfectivo, valoresEfectivos, camposForzados, bancoCalculado)}
          disabled={converting}
          className="btn-primary flex items-center gap-2 disabled:opacity-50"
        >
          {converting ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
          {converting ? t("convertidor.processing") : t("convertidor.mapeo.convertir")}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// "La columna OFERTA trae precios, no mecánicas"
// ---------------------------------------------------------------------------
//
// OFERTA tiene que traer el TITULAR de la mecánica ("2x$299", "6x4", "2da
// unidad al 50%"). Cuando alguien edita el Excel a mano a veces escribe ahí los
// precios, y el Convertidor la seguía leyendo como titular: la mecánica quedaba
// sin parsear y el precio que estaba ahí al lado no lo usaba nadie.
//
// Este aviso NO arregla nada solo, y es a propósito: cuál es el precio de oferta
// cuando hay una columna PRECIO y además una OFERTA con números es una pregunta
// de negocio. Se muestran los valores que lo delatan y la persona decide -- y
// puede decir "dejala como está", que es una respuesta tan válida como las otras.
function AvisoOfertaConPrecios({
  aviso, campos, elegido, onElegir,
}: {
  aviso: OfertaConPrecios;
  campos: Record<string, string>;
  /** undefined = todavía no decidió; "" = ignorar la columna. */
  elegido: string | undefined;
  onElegir: (campo: string | undefined) => void;
}) {
  const { t } = useTranslation();
  const [abierto, setAbierto] = useState(false);

  return (
    <div className="card p-4 space-y-2 border-amber-300 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-950/20">
      <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
        {t("convertidor.ofertaPrecios.titulo", { columna: aviso.columna })}
      </p>
      <p className="text-xs text-amber-700 dark:text-amber-400">
        {t("convertidor.ofertaPrecios.detalle")}
      </p>
      <p className="text-[11px] font-mono text-amber-700/80 dark:text-amber-400/80 break-words">
        {aviso.muestras.join("   ·   ")}
      </p>

      {elegido === undefined ? (
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={() => onElegir(aviso.campo_propuesto)}
            className="btn-primary text-xs"
          >
            {t("convertidor.ofertaPrecios.pasarAPrecio")}
          </button>
          <button type="button" onClick={() => onElegir("")} className="btn-secondary text-xs">
            {t("convertidor.ofertaPrecios.ignorar")}
          </button>
          {/* "Dejala como está" no escribe nada en camposForzados, así que hay
              que poder marcar la decisión sin cambiar el comportamiento: se
              esconde el aviso y el archivo se lee igual que siempre. */}
          <button type="button" onClick={() => setAbierto(true)} className="btn-secondary text-xs">
            {t("convertidor.ofertaPrecios.otroCampo")}
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <p className="text-xs text-emerald-700 dark:text-emerald-400">
            {elegido === ""
              ? t("convertidor.ofertaPrecios.aplicadoIgnorar", { columna: aviso.columna })
              : t("convertidor.ofertaPrecios.aplicado", {
                  columna: aviso.columna,
                  campo: elegido,
                  que: campos[elegido] ?? "",
                })}
          </p>
          <button type="button" onClick={() => onElegir(undefined)} className="btn-secondary text-xs">
            {t("convertidor.ofertaPrecios.deshacer")}
          </button>
        </div>
      )}

      {abierto && elegido === undefined && (
        <select
          className="input text-xs w-full mt-1"
          value=""
          onChange={(e) => e.target.value && onElegir(e.target.value)}
        >
          <option value="">{t("convertidor.ofertaPrecios.elegiCampo")}</option>
          {Object.entries(campos).map(([campo, que]) => (
            <option key={campo} value={campo}>
              {campo} — {que}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

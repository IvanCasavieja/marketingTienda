"use client";
import { useMemo, useRef, useState } from "react";
import { Download, FolderTree, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { convertidorApi, type ConvertidorRow } from "@/lib/api";
import { useEscapeKey } from "@/hooks/useEscapeKey";

// Espejo de _STOCK_MINIMO en backend/app/services/cenefas/convertidor.py.
// Está duplicado a propósito (no hay endpoint que lo exponga) porque el resumen
// de este modal se calcula acá, en el browser, y tiene que dar EXACTAMENTE lo
// mismo que después arma el ZIP: si la pantalla dice "12 archivos" y bajan 57,
// la próxima vez nadie le cree al resumen. Ivan lo fijó el 15/09/2026 ("mayor
// o igual a 1", corrigiendo el "mayor a 1" del pedido original).
const STOCK_MINIMO = 1;

// El nombre de la carpeta/archivo de las filas que no tienen categoría. Tiene
// que decir lo mismo que armar_zip_dividido en el backend: el resumen promete
// "N filas van a Sin categoría" y el ZIP tiene que traer ese archivo con ese
// nombre, si no la promesa no se puede verificar contra lo que bajó.
const SIN_CATEGORIA = "Sin categoría";

// Con qué nombre se pide el ZIP. Es el mismo prefijo que ya usa la descarga del
// Excel entero ("convertidor_cenefas.xlsx" en handleExport), así que los dos
// archivos quedan juntos y ordenados en la carpeta de Descargas. Es también la
// base con la que este modal arma el nombre por su cuenta: ver
// nombreDeLaDescarga, que es el camino normal y no el de excepción.
const NOMBRE_BASE = "convertidor_cenefas";

// Cuántas sucursales/categorías se listan antes de cortar con un "+N". Un
// listado de electro puede traer ocho sucursales y veinte categorías: sin tope,
// el resumen ocupa más pantalla que los dos interruptores que lo generan.
const MAX_CHIPS = 12;

interface Props {
  /**
   * Las filas VIVAS de la grilla, no un snapshot como en ConvertidorAiModal o
   * ConvertidorUnifyModal. Acá es al revés a propósito: el ZIP se arma con lo
   * que hay en la grilla en el momento de bajarlo, así que el resumen tiene que
   * estar mirando exactamente esas filas y no una copia de cuando se abrió.
   */
  rows: ConvertidorRow[];
  /**
   * flushPendientes() de la grilla. Se espera ANTES de pedir el ZIP por lo
   * mismo que en handleExport: una descripción recién tipeada todavía puede
   * estar esperando el debounce de 800 ms, y bajar el archivo sin ella es bajar
   * algo distinto de lo que está en pantalla.
   */
  onAntesDeDescargar: () => Promise<void>;
  onClose: () => void;
}

interface Resumen {
  archivos: number;
  carpetas: number;
  sucursales: string[];
  categorias: string[];
  filasSinStock: number;
  filasSinCategoria: number;
}

/**
 * El interruptor. No existe components/ui/Switch.tsx en el repo: el molde es el
 * de PropertiesPanel.tsx (el de "texto compuesto"), copiado acá en vez de
 * extraerlo a un componente compartido — son dos usos, y el día que haya un
 * tercero recién ahí vale la pena un componente.
 *
 * Toda la fila es UN botón, no un <label> con un <button> adentro: un button es
 * un elemento etiquetable, así que envolverlo en un label hace que el click
 * llegue dos veces en algunos navegadores y el interruptor vuelva solo a donde
 * estaba.
 */
function Interruptor({
  activo, onChange, titulo, ayuda,
}: { activo: boolean; onChange: (v: boolean) => void; titulo: string; ayuda: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={activo}
      aria-label={titulo}
      onClick={() => onChange(!activo)}
      className="w-full flex items-start gap-3 text-left"
    >
      <span
        className={`relative inline-flex shrink-0 w-9 h-5 mt-0.5 rounded-full transition-colors ${
          activo ? "bg-brand-500" : "bg-slate-200 dark:bg-slate-700"
        }`}
      >
        <span
          className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
            activo ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-slate-700 dark:text-slate-300">{titulo}</span>
        <span className="block text-xs text-slate-400 dark:text-slate-500">{ayuda}</span>
      </span>
    </button>
  );
}

/**
 * El nombre con el que se guarda el ZIP cuando NO se puede leer el que armó el
 * backend.
 *
 * Este respaldo no es un caso de borde, es lo que pasa SIEMPRE en producción:
 * el front vive en Vercel y la API en Render, así que toda llamada es
 * cross-origin, y CORS solo deja leer un puñado de headers salvo que el server
 * los liste en expose_headers — cosa que backend/app/main.py:268-274 no hace
 * para Content-Disposition. O sea que headers["content-disposition"] llega
 * vacío en producción y solo trae algo cuando el front y la API corren en el
 * mismo origen, que es únicamente en desarrollo. Sin este respaldo el ZIP bajaba
 * con el nombre que inventa el browser a partir de la URL ("export-dividido",
 * sin extensión) y Windows no sabía con qué abrirlo.
 *
 * El backend no se toca a propósito: expose_headers es configuración de TODA la
 * API, no de este endpoint, y cambiarla por una descarga es mover algo que hoy
 * funciona para todo lo demás.
 *
 * El nombre dice qué se dividió, igual que el que arma el backend, para que dos
 * descargas seguidas del mismo listado con interruptores distintos no se pisen
 * en la carpeta de Descargas.
 */
function nombreDeLaDescarga(porCategoria: boolean, porSucursal: boolean): string {
  const partes = [NOMBRE_BASE];
  if (porSucursal) partes.push("sucursales");
  if (porCategoria) partes.push("categorias");
  return `${partes.join("_")}.zip`;
}

/**
 * El motivo real de un error que vino con responseType: "blob".
 *
 * Con esa opción axios NO parsea la respuesta de error: err.response.data es un
 * Blob, así que el err?.response?.data?.detail que usa todo el resto del repo
 * da undefined y cualquier error (el 400 de "elegí una forma de dividir", un
 * 403, un 500) se ve igual, como "Error desconocido". Hay que leer el Blob como
 * texto y parsearlo a mano. Es el único lugar del repo que lo hace.
 */
async function motivoDelError(err: any): Promise<string | null> {
  const data = err?.response?.data;
  if (!data) return null;
  // Un error de red (sin response) o una respuesta que sí vino parseada: se
  // resuelve por el camino de siempre.
  if (typeof data?.detail === "string") return data.detail;
  if (typeof Blob === "undefined" || !(data instanceof Blob)) return null;
  try {
    const json = JSON.parse(await data.text());
    return typeof json?.detail === "string" ? json.detail : null;
  } catch {
    // El cuerpo no era JSON (un 502 del proxy devuelve HTML): no hay motivo que
    // mostrar y se cae al mensaje genérico de siempre.
    return null;
  }
}

export default function ConvertidorDividirModal({
  rows, onAntesDeDescargar, onClose,
}: Props) {
  const { t } = useTranslation();
  // Los dos arrancan apagados: nada se divide solo. Misma doctrina que el aviso
  // de columnas de stock en el mapeo — el backend detecta, la pantalla avisa,
  // la persona decide.
  const [porCategoria, setPorCategoria] = useState(false);
  const [porSucursal, setPorSucursal] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const dlRef = useRef<HTMLAnchorElement>(null);

  useEscapeKey(onClose);

  /**
   * El resumen, calculado acá mismo con las filas que la grilla ya tiene
   * (stockPorSucursal y categoriaProducto vienen en cada una desde el preview).
   * No se le pide nada al backend: la gracia es poder mover los interruptores y
   * ver el número cambiar en el acto, ANTES de bajar nada.
   *
   * Esto es lo que evita la sorpresa de 57 archivos: prender los dos
   * interruptores sobre un listado con ocho sucursales y veinte categorías
   * multiplica, y hasta que el resumen no lo dijo en pantalla nadie lo veía
   * venir hasta descomprimir el ZIP.
   *
   * Espejo de armar_zip_dividido: mismo orden (primero la sucursal, la
   * categoría adentro) y mismo umbral. Si allá cambia el criterio, acá también.
   */
  const resumen = useMemo<Resumen>(() => {
    // Clave de carpeta -> filas que caen ahí. Sin dividir por sucursal hay un
    // solo grupo con TODAS las filas y sin filtrar por stock: el filtro de
    // stock es parte de "dividir por sucursales" (una fila va donde hay stock),
    // no un filtro general del listado.
    const grupos = new Map<string, ConvertidorRow[]>();
    const enElZip = new Set<number>();
    let filasSinStock = 0;

    if (porSucursal) {
      for (const r of rows) {
        // Tipado a mano: con el `?? {}` pelado, Object.entries cae en la
        // sobrecarga de {} y las cantidades llegan como any.
        const stock: Record<string, number> = r.stockPorSucursal ?? {};
        const conStock = Object.entries(stock)
          .filter(([, cantidad]) => Number(cantidad) >= STOCK_MINIMO)
          .map(([sucursal]) => sucursal);
        if (conStock.length === 0) {
          filasSinStock += 1;
          continue;
        }
        enElZip.add(r.row_id);
        for (const sucursal of conStock) {
          const ya = grupos.get(sucursal);
          if (ya) ya.push(r);
          else grupos.set(sucursal, [r]);
        }
      }
    } else {
      grupos.set("", rows);
      for (const r of rows) enElZip.add(r.row_id);
    }

    let archivos = 0;
    const categorias = new Set<string>();
    for (const filas of grupos.values()) {
      if (!porCategoria) {
        archivos += 1;
        continue;
      }
      const deEsteGrupo = new Set<string>();
      for (const r of filas) {
        const cat = (r.categoriaProducto ?? "").trim() || SIN_CATEGORIA;
        deEsteGrupo.add(cat);
        categorias.add(cat);
      }
      archivos += deEsteGrupo.size;
    }

    // Se cuentan FILAS del listado, una sola vez cada una, aunque la misma fila
    // caiga en tres sucursales: el texto habla de filas, y una fila repetida en
    // tres carpetas sigue siendo una sola fila para ir a revisar a la grilla.
    const filasSinCategoria = rows.filter(
      (r) => enElZip.has(r.row_id) && !(r.categoriaProducto ?? "").trim(),
    ).length;

    const sucursales = porSucursal ? [...grupos.keys()].sort() : [];
    return {
      archivos,
      // El ZIP trae carpetas SOLO cuando están prendidos los dos interruptores:
      // recién ahí armar_zip_dividido escribe rutas "{sucursal}/{categoria}.xlsx".
      // Con uno solo las rutas son "{sucursal}.xlsx" o "{categoria}.xlsx", planas
      // en la raíz, y el resumen prometía "8 archivos en 8 carpetas" para un ZIP
      // que al descomprimir no traía ninguna. Esta condición es el espejo exacto
      // de las rutas del backend: si allá cambian, acá también.
      carpetas: porSucursal && porCategoria ? sucursales.length : 0,
      sucursales,
      categorias: porCategoria ? [...categorias].sort() : [],
      filasSinStock,
      filasSinCategoria,
    };
  }, [rows, porCategoria, porSucursal]);

  const algunoPrendido = porCategoria || porSucursal;
  // Con el resumen en cero no hay nada que bajar. Pasa cuando se divide por
  // sucursales y ninguna fila tiene stock >= 1 en ninguna (un listado cuyas
  // columnas de stock vinieron vacías, o que se destildaron todas en el mapeo),
  // y también con la grilla vacía. Antes el botón seguía habilitado: bajaba un
  // ZIP de cero archivos y el toast decía "ZIP descargado", la peor combinación
  // posible — no se rompe nada y nadie se entera de que no hay datos hasta
  // descomprimirlo. El backend además contesta 400, pero el número ya está acá:
  // no hace falta ir hasta el server para no dejar apretar.
  const puedeDescargar = algunoPrendido && resumen.archivos > 0;

  async function descargar() {
    if (!puedeDescargar) return;
    setDescargando(true);
    try {
      await onAntesDeDescargar();
      const { data, headers } = await convertidorApi.exportDividido(rows, {
        por_categoria: porCategoria,
        por_sucursal: porSucursal,
        nombre_base: NOMBRE_BASE,
      });
      const url = URL.createObjectURL(new Blob([data], { type: "application/zip" }));
      // El backend manda el nombre en el content-disposition y se usa si está,
      // pero cross-origin ese header no se puede leer y `cd` viene vacío: el
      // nombre que arma nombreDeLaDescarga es el que se ve en producción, no un
      // respaldo teórico.
      const cd = String(headers?.["content-disposition"] ?? "");
      const m = cd.match(/filename="?([^";]+)"?/);
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = m?.[1] ?? nombreDeLaDescarga(porCategoria, porSucursal);
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
      toast.success(t("convertidor.dividir.listo"));
      onClose();
    } catch (err: any) {
      toast.error((await motivoDelError(err)) ?? t("convertidor.unknownError"));
    } finally {
      setDescargando(false);
    }
  }

  function chips(valores: string[]) {
    const visibles = valores.slice(0, MAX_CHIPS);
    const resto = valores.length - visibles.length;
    return (
      <div className="flex flex-wrap gap-1">
        {visibles.map((v) => (
          <span
            key={v}
            className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-[10px] text-slate-600 dark:text-slate-300"
          >
            {v}
          </span>
        ))}
        {resto > 0 && <span className="px-1.5 py-0.5 text-[10px] text-slate-400">+{resto}</span>}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <a ref={dlRef} className="hidden" />
      <div
        role="dialog"
        aria-modal="true"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-lg max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <p className="text-sm font-semibold flex items-center gap-1.5 text-slate-800 dark:text-slate-100">
            <FolderTree size={15} className="text-brand-500" /> {t("convertidor.dividir.titulo")}
          </p>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <Interruptor
            activo={porCategoria}
            onChange={setPorCategoria}
            titulo={t("convertidor.dividir.porCategoria")}
            ayuda={t("convertidor.dividir.porCategoriaHint")}
          />
          <Interruptor
            activo={porSucursal}
            onChange={setPorSucursal}
            titulo={t("convertidor.dividir.porSucursal")}
            ayuda={t("convertidor.dividir.porSucursalHint")}
          />

          <div className="rounded-lg border border-slate-100 dark:border-slate-800 p-3 space-y-2">
            {!algunoPrendido ? (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                {t("convertidor.dividir.elegirUno")}
              </p>
            ) : (
              <>
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                  {t("convertidor.dividir.resumen", {
                    archivos: resumen.archivos,
                    carpetas: resumen.carpetas,
                  })}
                </p>
                {porSucursal && resumen.sucursales.length > 0 && chips(resumen.sucursales)}
                {porCategoria && resumen.categorias.length > 0 && chips(resumen.categorias)}
                {porSucursal && resumen.filasSinStock > 0 && (
                  <p className="text-[11px] text-amber-600 dark:text-amber-400">
                    {t("convertidor.dividir.sinStock", { count: resumen.filasSinStock })}
                  </p>
                )}
                {porCategoria && resumen.filasSinCategoria > 0 && (
                  <p className="text-[11px] text-amber-600 dark:text-amber-400">
                    {t("convertidor.dividir.sinCategoria", { count: resumen.filasSinCategoria })}
                  </p>
                )}
              </>
            )}
          </div>

          {/* Acá estaba el botón "Clasificar con Tinín" (con su prop onCategorias): se sacó el 15/09/2026 porque la categoría sale de dsc_subfamilia y lo que falte se corrige a mano en la columna de la grilla. */}
        </div>

        <div className="flex justify-end px-5 py-4 border-t border-slate-100 dark:border-slate-800">
          <button
            type="button"
            onClick={descargar}
            disabled={!puedeDescargar || descargando}
            className="btn-primary flex items-center gap-2 text-sm disabled:opacity-50"
          >
            {descargando ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            {t("convertidor.dividir.descargar")}
          </button>
        </div>
      </div>
    </div>
  );
}

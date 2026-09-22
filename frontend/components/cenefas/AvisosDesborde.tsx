"use client";
import { AlertTriangle } from "lucide-react";
import type { AvisoDesborde, CenefaTemplate } from "@/types/cenefas";

// Aviso de "esto se va a imprimir FUERA de la hoja".
//
// De dónde sale. El 18/09/2026 Ivan exportó una 3xA4 SOLO X 25 y el texto
// salió impreso fuera del papel mientras el preview se lo mostraba adentro.
// No era un error de medición: el preview AGRANDABA la hoja hasta que le
// entrara el contenido, así que nada se veía nunca saliéndose. Eso se sacó —
// ahora el preview dibuja el papel y lo que sobra queda sobre la mesa gris,
// con el borde de la hoja marcado en rojo.
//
// Pero verlo no alcanza, y por eso además existe este aviso: el desborde
// depende de la FILA DE DATOS, no solo del diseño. La plantilla de Ivan entra
// con "DETERGENTE LÍQUIDO CONCENTRADO" y se sale con una descripción tres
// palabras más larga. El aviso se calcula con los productos reales de la
// corrida —todas las filas, no solo la primera—, contra el papel real,
// midiendo la TINTA que se va a imprimir y no la caja declarada — ver
// `detectar_desbordes` en component_renderer.py, que explica por qué esa
// distinción es la que decide si el aviso sirve o si lo saltea todo el mundo.
//
// NO BLOQUEA NADA, igual que los avisos de solape desde el 14/09/2026: hay
// diseños que desbordan a propósito y quien decide es la persona.

const NOMBRE_DEL_LADO: Record<AvisoDesborde["lado"], string> = {
  izquierda: "por la izquierda",
  derecha:   "por la derecha",
  arriba:    "por arriba",
  abajo:     "por abajo",
};

export default function AvisosDesborde({
  avisos,
  template,
}: {
  avisos?: AvisoDesborde[];
  template: CenefaTemplate | null;
}) {
  if (!avisos?.length) return null;

  const nombre = (id: string) =>
    template?.components.find((c) => c.id === id)?.name || id;

  // Primero los que cortan texto al imprimir. Un desborde por arriba o por
  // abajo suele venir de una caja de texto altísima de PowerPoint con el texto
  // anclado arriba, y casi nunca corta nada; el que arruina el cartel es el
  // de los costados. Se ordena en vez de esconderlos: esconder algo es cómo
  // empezó este problema.
  const ordenados = [...avisos].sort((a, b) =>
    (Number(b.corta_texto) - Number(a.corta_texto)) || (b.cm - a.cm),
  );
  const cortan = ordenados.filter((a) => a.corta_texto).length;
  const hoja = avisos.find((a) => a.hoja_cm)?.hoja_cm;

  return (
    <div className="rounded-lg border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/30 px-3 py-2.5 mb-3">
      <div className="flex items-start gap-2">
        <AlertTriangle size={14} className="text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-xs font-semibold text-red-800 dark:text-red-300">
            {avisos.length === 1
              ? "Un texto se imprime fuera de la hoja"
              : `${avisos.length} textos se imprimen fuera de la hoja`}
            {cortan > 0 && avisos.length !== cortan
              ? ` — ${cortan} se corta${cortan === 1 ? "" : "n"} por el costado`
              : ""}
            {hoja ? (
              <span className="font-normal opacity-70"> (hoja de {hoja[0]} × {hoja[1]} cm)</span>
            ) : null}
          </p>
          <ul className="mt-1 space-y-0.5">
            {ordenados.map((a, i) => (
              <li key={i} className="text-[11px] text-red-700 dark:text-red-400/90">
                <span className="font-medium">{nombre(a.component_id)}</span>
                {a.texto ? <span className="opacity-70"> «{a.texto}»</span> : null}
                {" se sale "}
                {NOMBRE_DEL_LADO[a.lado]}
                <span className="font-medium"> {a.cm} cm</span>
                {a.filas && a.filas > 1 ? (
                  <span className="opacity-60"> — en {a.filas} filas, peor la {a.fila}</span>
                ) : null}
                {!a.corta_texto ? (
                  <span className="opacity-60"> — no corta texto, pero se sale</span>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-red-600 dark:text-red-500/80 mt-1.5">
            En el preview lo vas a ver sobre el gris, con el borde de la hoja
            marcado. Se arregla en el editor: moviendo o angostando el cuadro, o
            poniéndole una regla de <span className="font-medium">Tamaño</span>{" "}
            para los textos largos. Nadie lo achica solo.
          </p>
        </div>
      </div>
    </div>
  );
}

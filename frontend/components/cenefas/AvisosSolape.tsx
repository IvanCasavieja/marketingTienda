"use client";
import { AlertTriangle } from "lucide-react";
import type { AvisoSolape, CenefaTemplate } from "@/types/cenefas";

// Aviso de "este texto se va a imprimir encima de este otro".
//
// Hasta el 14/09/2026 esto no se avisaba: el motor achicaba solo el cuadro más
// grande del par, de a 5% por pasada, hasta despejar. Ese achique se eliminó
// entero (decisión de Ivan) porque su piso se multiplicaba con el de la etapa
// anterior --0,55 sobre 0,55, o sea 30% del cuerpo de diseño-- y porque
// dependía de mediciones que el navegador no replicaba, así que el preview
// mostraba una cosa y el PPTX salía con otra.
//
// Lo que NO se quiso perder al sacarlo es la red de seguridad: un precio
// impreso sobre otro texto es un cartel inservible, y enterarse en la góndola
// cuesta la corrida entera reimpresa. Por eso se sigue detectando, con el
// mismo criterio de siempre (no cualquier roce cuenta: el "$" adentro de la
// caja del precio o el decimal pegado a su entero están así por diseño), pero
// ahora se muestra acá y lo resuelve una persona.

export default function AvisosSolape({
  avisos,
  template,
}: {
  avisos?: AvisoSolape[];
  template: CenefaTemplate | null;
}) {
  if (!avisos?.length) return null;

  const nombre = (id: string) =>
    template?.components.find((c) => c.id === id)?.name || id;

  return (
    <div className="rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 px-3 py-2.5 mb-3">
      <div className="flex items-start gap-2">
        <AlertTriangle size={14} className="text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
            {avisos.length === 1
              ? "Un texto se imprime encima de otro"
              : `${avisos.length} textos se imprimen encima de otros`}
          </p>
          <ul className="mt-1 space-y-0.5">
            {avisos.map((a, i) => (
              <li key={i} className="text-[11px] text-amber-700 dark:text-amber-400/90">
                <span className="font-medium">{nombre(a.component_id)}</span>
                {a.font_size ? ` (${a.font_size} pt)` : ""} pisa a{" "}
                <span className="font-medium">{nombre(a.contra_id)}</span>
                <span className="opacity-70"> — {a.area_cm2} cm²</span>
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-amber-600 dark:text-amber-500/80 mt-1.5">
            Ya no se achica solo. Si querés que entre, seleccioná el cuadro y
            agregale una regla de <span className="font-medium">Tamaño</span> —
            por ejemplo &ldquo;si tiene más de 3 caracteres, 90 pt&rdquo;.
          </p>
        </div>
      </div>
    </div>
  );
}

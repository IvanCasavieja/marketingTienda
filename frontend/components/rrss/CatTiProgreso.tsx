"use client";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { CatTiCarita } from "./CatTiMascota";

// ---------------------------------------------------------------------------
// Las dos piezas que acompañan a CatTi mientras revisa un lote de placas.
//
// La idea es la misma que la de Tinín picando piedra en el Convertidor, pero
// acá hay algo que Tinín no tiene: el motor SÍ sabe cuántas placas lleva de
// cuántas (page.tsx arma el Progreso placa por placa). Así que la sensación de
// avance no se finge con un spinner — la gata camina sobre la barra y la barra
// dice el número real.
// ---------------------------------------------------------------------------

/** Las frases que va diciendo CatTi mientras revisa.
 *
 *  Rotan por dos motivos y los dos importan: cada vez que termina una placa
 *  (`paso` cambia) y, si una placa se está haciendo larga, cada 5 segundos. De
 *  esa forma el cambio de frase es, casi siempre, una placa terminada de
 *  verdad y no un reloj corriendo solo.
 *
 *  Los textos viven en lib/locales/*.json bajo rrss.catti.frases, al lado de
 *  los de Tinín (convertidor.ai.loading): se editan ahí y en ningún otro lado. */
export function FraseCatTi({ paso, className }: { paso?: number; className?: string }) {
  const { t } = useTranslation();
  const crudas = t("rrss.catti.frases", { returnObjects: true });
  const frases: string[] = Array.isArray(crudas) ? crudas : [];

  const [i, setI] = useState(0);
  const primera = useRef(true);

  useEffect(() => {
    const id = setInterval(() => setI((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    // El efecto también corre al montar: ahí no hay placa terminada todavía,
    // así que la primera vuelta no cuenta y arrancamos por la frase 1.
    if (primera.current) {
      primera.current = false;
      return;
    }
    setI((n) => n + 1);
  }, [paso]);

  if (frases.length === 0) return null;
  const frase = frases[i % frases.length];
  return (
    <p key={frase} className={clsx("animate-fade-in", className)}>
      {frase}
    </p>
  );
}

/** La barra de progreso con CatTi caminando encima.
 *
 *  La posición de la carita ES el progreso (hechas/total), no una animación en
 *  loop: si el lote se frena, la gata se frena. El trotecito solo existe
 *  mientras algo está efectivamente corriendo. */
export function BarraCatTi({ hechas, total, enVivo = true }: { hechas: number; total: number; enVivo?: boolean }) {
  const pct = Math.max(0, Math.min(100, (hechas / Math.max(1, total)) * 100));
  return (
    <>
      <style>{`
        @keyframes ctp-trote { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-2.5px); } }
        .ctp-trote { animation: ctp-trote 0.6s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .ctp-trote { animation: none !important; }
        }
      `}</style>
      {/* El pt-5 es para que la gata, que va por arriba de la barra, no se
          monte sobre el texto de la línea de arriba. */}
      <div className="pt-5 mt-0.5">
        <div className="relative h-1.5 rounded-full bg-slate-100 dark:bg-slate-800">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-brand-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
          <div
            className="absolute -top-4 transition-all duration-500"
            style={{ left: `${pct}%`, transform: "translateX(-50%)" }}
          >
            <span className={clsx("block", enVivo && "ctp-trote")}>
              <CatTiCarita size={17} />
            </span>
          </div>
        </div>
      </div>
    </>
  );
}

"use client";
import { clsx } from "clsx";
import { CatTiMascota } from "./CatTiMascota";

/** CatTi, la gata de la familia Tino, en su baldosita violeta.
 *
 *  El marco redondeado es el que ya estaba y se queda: es lo que la hace
 *  encajar al lado del título de la pantalla y en la barra de progreso. Lo que
 *  cambió es lo de adentro — antes un ícono de lucide con animate-pulse, ahora
 *  la mascota dibujada (CatTiMascota.tsx), que además se pone la lupa cuando
 *  `trabajando` es true. El pulse se fue: la gata ya se mueve sola, y dos
 *  movimientos encimados quedaban nerviosos. */
export default function CatTiBadge({ trabajando = false, size = 44 }: { trabajando?: boolean; size?: number }) {
  return (
    <div
      className={clsx(
        "rounded-2xl flex items-center justify-center shrink-0 transition-colors",
        trabajando ? "bg-violet-500/15" : "bg-violet-500/10",
      )}
      style={{ width: size, height: size }}
      title="CatTi"
    >
      <CatTiMascota size={Math.round(size * 0.92)} trabajando={trabajando} />
    </div>
  );
}

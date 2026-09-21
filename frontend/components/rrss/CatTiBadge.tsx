"use client";
import { Cat } from "lucide-react";
import { clsx } from "clsx";

/** CatTi, la gata de la familia Tino. Un ícono por ahora: cuando haya una
 *  mascota dibujada (como DogTiMascot) se cambia acá y en ningún otro lado. */
export default function CatTiBadge({ trabajando = false, size = 44 }: { trabajando?: boolean; size?: number }) {
  return (
    <div
      className={clsx(
        "rounded-2xl bg-violet-500/10 flex items-center justify-center shrink-0",
        trabajando && "animate-pulse",
      )}
      style={{ width: size, height: size }}
      title="CatTi"
    >
      <Cat size={Math.round(size * 0.55)} className="text-violet-500" />
    </div>
  );
}

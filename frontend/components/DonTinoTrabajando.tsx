"use client";
import { Pickaxe } from "lucide-react";
import { RobotMascot } from "./RobotMascot";

// Variante de Don Tino para pantallas de carga con IA trabajando "atrás de
// escena" (ej. generando descripciones en el Convertidor de Excel) — el
// mismo robot de siempre (Home/Ayuda/Login, RobotMascot.tsx, sin tocar ese
// archivo para no afectar dónde ya se usa) con un pico picando piedra al
// lado, para dejar claro visualmente que hay laburo pesado en curso.
export function DonTinoTrabajando({ size = 72 }: { size?: number }) {
  return (
    <div className="relative inline-flex items-end justify-center" style={{ width: size + 24, height: size + 10 }}>
      <style>{`
        @keyframes pickaxe-swing {
          0%, 100% { transform: rotate(-40deg); }
          50%       { transform: rotate(20deg); }
        }
        .pickaxe-swing { animation: pickaxe-swing 0.85s ease-in-out infinite; transform-origin: bottom left; }
      `}</style>
      <RobotMascot size={size} />
      <span
        className="absolute bottom-1 right-0 text-amber-600 dark:text-amber-500 pickaxe-swing"
        style={{ transform: "rotate(-40deg)" }}
      >
        <Pickaxe size={Math.max(18, Math.round(size * 0.32))} strokeWidth={2.5} />
      </span>
    </div>
  );
}

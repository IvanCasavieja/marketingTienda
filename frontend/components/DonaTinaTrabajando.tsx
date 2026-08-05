"use client";

// Doña Tina — la experta en precios, trabajando en su notebook mientras la
// búsqueda en vivo termina de correr y Doña Tina revisa los resultados marca
// por marca. Mismo criterio que DonTinoTrabajando.tsx: dibuja su propia copia
// del robot (variante "tina" de RobotMascot.tsx, moño incluido) en vez de
// componer, porque las manos tienen que quedar apoyadas sobre el teclado y
// moverse CON el brazo — necesita ser parte del mismo grupo animado.
export function DonaTinaTrabajando({ size = 90 }: { size?: number }) {
  return (
    <>
      <style>{`
        @keyframes dtn-float    { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-6px); } }
        @keyframes dtn-shadow   { 0%, 100% { transform: scaleX(1);   opacity: 0.15; } 50% { transform: scaleX(0.7); opacity: 0.07; } }
        @keyframes dtn-blink    { 0%, 88%, 100% { transform: scaleY(1); } 92% { transform: scaleY(0.08); } }
        @keyframes dtn-antenna  { 0%, 100% { opacity: 1;   r: 3; } 50% { opacity: 0.4; r: 4.5; } }
        @keyframes dtn-light-1  { 0%,100% { opacity:1 } 20%,60% { opacity:0.2 } }
        @keyframes dtn-light-2  { 0%,100% { opacity:0.2 } 40% { opacity:1 } }
        @keyframes dtn-light-3  { 0%,100% { opacity:0.2 } 70% { opacity:1 } }
        @keyframes dtn-type-l   { 0%, 100% { transform: translateY(0px); } 25% { transform: translateY(2.5px); } 50% { transform: translateY(0px); } }
        @keyframes dtn-type-r   { 0%, 100% { transform: translateY(0px); } 75% { transform: translateY(2.5px); } 50% { transform: translateY(0px); } }
        @keyframes dtn-screen   { 0%, 100% { opacity: 0.55; } 50% { opacity: 1; } }
        .dtn-body    { animation: dtn-float 2.6s ease-in-out infinite; }
        .dtn-shadow  { animation: dtn-shadow 2.6s ease-in-out infinite; }
        .dtn-eye-l   { animation: dtn-blink 3.5s ease-in-out infinite; transform-origin: 32px 24px; }
        .dtn-eye-r   { animation: dtn-blink 3.5s ease-in-out infinite; transform-origin: 48px 24px; animation-delay: 0.05s; }
        .dtn-ant     { animation: dtn-antenna 1.4s ease-in-out infinite; }
        .dtn-l1      { animation: dtn-light-1 1.8s ease-in-out infinite; }
        .dtn-l2      { animation: dtn-light-2 1.8s ease-in-out infinite; }
        .dtn-l3      { animation: dtn-light-3 1.8s ease-in-out infinite; }
        /* Pivot en el hombro -- el antebrazo entero "tipea" apoyado en el teclado. */
        .dtn-arm-l   { animation: dtn-type-l 0.7s ease-in-out infinite; transform-origin: 15px 40px; }
        .dtn-arm-r   { animation: dtn-type-r 0.7s ease-in-out infinite; transform-origin: 65px 40px; animation-delay: 0.15s; }
        .dtn-screen  { animation: dtn-screen 1.6s ease-in-out infinite; }
      `}</style>

      <svg width={size} height={size} viewBox="0 0 80 84" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ overflow: "visible" }}>
        <ellipse className="dtn-shadow" cx="40" cy="80" rx="24" ry="4" fill="#6366f1" />

        <g className="dtn-body">
          {/* Notebook -- base + pantalla, apoyada justo debajo de las manos */}
          <rect x="20" y="66" width="40" height="4" rx="1.5" fill="#334155" />
          <path d="M25 66 L28 54 L52 54 L55 66 Z" fill="#475569" />
          <rect x="30" y="55.5" width="20" height="9" rx="1" fill="#0f172a" />
          <rect className="dtn-screen" x="31.5" y="57" width="17" height="6" rx="0.5" fill="#67e8f9" />

          {/* Cuerpo */}
          <rect x="22" y="34" width="36" height="26" rx="8" fill="#4f46e5" />
          <rect x="29" y="40" width="22" height="13" rx="4" fill="#4338ca" />
          <circle className="dtn-l1" cx="34" cy="46" r="2.5" fill="#a5f3fc" />
          <circle className="dtn-l2" cx="40" cy="46" r="2.5" fill="#6ee7b7" />
          <circle className="dtn-l3" cx="46" cy="46" r="2.5" fill="#fca5a5" />

          {/* Brazos, los dos "tipeando" sobre el teclado */}
          <g className="dtn-arm-l">
            <rect x="10" y="36" width="10" height="18" rx="5" fill="#4f46e5" />
            <circle cx="15" cy="56" r="5" fill="#6366f1" />
          </g>
          <g className="dtn-arm-r">
            <rect x="60" y="36" width="10" height="18" rx="5" fill="#4f46e5" />
            <circle cx="65" cy="56" r="5" fill="#6366f1" />
          </g>

          {/* Cuello + cabeza */}
          <rect x="35" y="28" width="10" height="8" rx="3" fill="#6366f1" />
          <rect x="18" y="6" width="44" height="30" rx="12" fill="#6366f1" />
          <rect x="26" y="15" width="12" height="10" rx="5" fill="white" />
          <rect x="42" y="15" width="12" height="10" rx="5" fill="white" />
          <circle className="dtn-eye-l" cx="32" cy="20" r="4" fill="#1e1b4b" />
          <circle className="dtn-eye-r" cx="48" cy="20" r="4" fill="#1e1b4b" />
          <circle cx="33" cy="18" r="1.5" fill="white" />
          <circle cx="49" cy="18" r="1.5" fill="white" />
          <path d="M30 29 Q40 35 50 29" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
          <line x1="40" y1="6" x2="40" y2="-1" stroke="#818cf8" strokeWidth="2.5" strokeLinecap="round" />
          <circle className="dtn-ant" cx="40" cy="-2" r="3" fill="#a5b4fc" />

          {/* Moño de Doña Tina */}
          <g>
            <path d="M50 4 L44 8 L50 12 Z" fill="#f472b6" />
            <path d="M54 4 L60 8 L54 12 Z" fill="#f472b6" />
            <circle cx="52" cy="8" r="2" fill="#db2777" />
          </g>
        </g>
      </svg>
    </>
  );
}

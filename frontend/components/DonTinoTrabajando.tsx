"use client";

// Variante de Don Tino para pantallas de carga con IA trabajando "atrás de
// escena" (ej. generando descripciones en el Convertidor de Excel). No
// reusa <RobotMascot size={...}/> por composición: el pico tiene que ir
// agarrado de la mano y moverse CON el brazo y CON el float del cuerpo, así
// que necesita ser parte del mismo SVG/grupo animado, no un ícono aparte
// superpuesto encima (esa primera versión quedaba con el pico flotando
// suelto, sin agarrarse a ninguna mano). Por eso este archivo dibuja su
// propia copia del robot — mismo diseño que RobotMascot.tsx, sin tocar ese
// componente para no afectar Home/Ayuda/Login — con el brazo derecho
// modificado para sostener el pico y el swing de minero en vez del wave.
export function DonTinoTrabajando({ size = 90 }: { size?: number }) {
  return (
    <>
      <style>{`
        @keyframes dt-float   { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-8px); } }
        @keyframes dt-shadow  { 0%, 100% { transform: scaleX(1);   opacity: 0.15; } 50% { transform: scaleX(0.7); opacity: 0.07; } }
        @keyframes dt-blink   { 0%, 88%, 100% { transform: scaleY(1); } 92% { transform: scaleY(0.08); } }
        @keyframes dt-antenna { 0%, 100% { opacity: 1;   r: 3; } 50% { opacity: 0.4; r: 4.5; } }
        @keyframes dt-light-1 { 0%,100% { opacity:1 } 20%,60% { opacity:0.2 } }
        @keyframes dt-light-2 { 0%,100% { opacity:0.2 } 40% { opacity:1 } }
        @keyframes dt-light-3 { 0%,100% { opacity:0.2 } 70% { opacity:1 } }
        @keyframes dt-pickaxe {
          0%   { transform: rotate(8deg); }
          35%  { transform: rotate(-58deg); }
          55%  { transform: rotate(-58deg); }
          100% { transform: rotate(8deg); }
        }
        .dt-body   { animation: dt-float 2.8s ease-in-out infinite; }
        .dt-shadow { animation: dt-shadow 2.8s ease-in-out infinite; }
        .dt-eye-l  { animation: dt-blink 3.5s ease-in-out infinite; transform-origin: 32px 24px; }
        .dt-eye-r  { animation: dt-blink 3.5s ease-in-out infinite; transform-origin: 48px 24px; animation-delay: 0.05s; }
        .dt-ant    { animation: dt-antenna 1.4s ease-in-out infinite; }
        .dt-l1     { animation: dt-light-1 1.8s ease-in-out infinite; }
        .dt-l2     { animation: dt-light-2 1.8s ease-in-out infinite; }
        .dt-l3     { animation: dt-light-3 1.8s ease-in-out infinite; }
        /* Pivot en el hombro (62, 44) -- todo el brazo + pico rota junto,
           el pico nunca se despega de la mano. */
        .dt-pickaxe-arm { animation: dt-pickaxe 1.1s cubic-bezier(.45,0,.55,1) infinite; transform-origin: 62px 44px; }
      `}</style>

      <svg width={size} height={size} viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ overflow: "visible" }}>
        <ellipse className="dt-shadow" cx="40" cy="76" rx="22" ry="4" fill="#6366f1" />

        <g className="dt-body">
          {/* Cuerpo */}
          <rect x="22" y="38" width="36" height="26" rx="8" fill="#4f46e5" />
          <rect x="29" y="44" width="22" height="13" rx="4" fill="#4338ca" />
          <circle className="dt-l1" cx="34" cy="50" r="2.5" fill="#a5f3fc" />
          <circle className="dt-l2" cx="40" cy="50" r="2.5" fill="#6ee7b7" />
          <circle className="dt-l3" cx="46" cy="50" r="2.5" fill="#fca5a5" />

          {/* Brazo izquierdo — quieto acá (apoyo), el laburo lo hace el derecho */}
          <rect x="10" y="40" width="10" height="18" rx="5" fill="#4f46e5" />
          <circle cx="15" cy="60" r="5" fill="#6366f1" />

          {/* Brazo derecho + pico, un solo grupo que gira desde el hombro */}
          <g className="dt-pickaxe-arm">
            <rect x="60" y="40" width="10" height="18" rx="5" fill="#4f46e5" />
            <circle cx="65" cy="60" r="5" fill="#6366f1" />
            {/* Mango, sale de adentro del puño hacia arriba-derecha */}
            <rect x="63.3" y="44" width="3.4" height="20" rx="1.7" fill="#b45309" transform="rotate(28 65 60)" />
            {/* Cabeza del pico, en la punta del mango */}
            <path
              d="M 65 40.5 C 60.5 36 55.5 35.3 51 37.6 C 54.3 39.7 57 42.8 58.6 46.6 C 60.8 43.9 63 41.9 65 40.5 Z"
              fill="#64748b"
            />
            <path
              d="M 65 40.5 C 69.5 36 74.5 35.3 79 37.6 C 75.7 39.7 73 42.8 71.4 46.6 C 69.2 43.9 67 41.9 65 40.5 Z"
              fill="#94a3b8"
            />
          </g>

          {/* Cuello + cabeza */}
          <rect x="35" y="32" width="10" height="8" rx="3" fill="#6366f1" />
          <rect x="18" y="10" width="44" height="30" rx="12" fill="#6366f1" />
          <rect x="26" y="19" width="12" height="10" rx="5" fill="white" />
          <rect x="42" y="19" width="12" height="10" rx="5" fill="white" />
          <circle className="dt-eye-l" cx="32" cy="24" r="4" fill="#1e1b4b" />
          <circle className="dt-eye-r" cx="48" cy="24" r="4" fill="#1e1b4b" />
          <circle cx="33" cy="22" r="1.5" fill="white" />
          <circle cx="49" cy="22" r="1.5" fill="white" />
          <path d="M30 33 Q40 39 50 33" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
          <line x1="40" y1="10" x2="40" y2="3" stroke="#818cf8" strokeWidth="2.5" strokeLinecap="round" />
          <circle className="dt-ant" cx="40" cy="2" r="3" fill="#a5b4fc" />
        </g>
      </svg>
    </>
  );
}

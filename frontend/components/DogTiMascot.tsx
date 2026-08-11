"use client";

// ---------------------------------------------------------------------------
// DogTi — el perro de la familia Tino (Don Tino/Doña Tina/Tinín son robots,
// DogTi no). Cuerpo propio, no una variante de RobotMascot.tsx: mismo
// patrón de <style> con @keyframes + clases scoped, pero con prefijo "dt-"
// para no colisionar con las clases "robot-*" si ambas mascotas conviven en
// la misma pantalla (ver DogTiFloating.tsx).
// ---------------------------------------------------------------------------

export function DogTiMascot({ size = 90 }: { size?: number } = {}) {
  return (
    <>
      <style>{`
        @keyframes dt-float {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-7px); }
        }
        @keyframes dt-shadow {
          0%, 100% { transform: scaleX(1);   opacity: 0.15; }
          50%       { transform: scaleX(0.7); opacity: 0.07; }
        }
        @keyframes dt-blink {
          0%, 90%, 100% { transform: scaleY(1); }
          95%            { transform: scaleY(0.1); }
        }
        @keyframes dt-tail-wag {
          0%, 100% { transform: rotate(-8deg); }
          50%       { transform: rotate(18deg); }
        }
        .dt-body   { animation: dt-float 2.8s ease-in-out infinite; }
        .dt-shadow { animation: dt-shadow 2.8s ease-in-out infinite; }
        .dt-eye-l  { animation: dt-blink 4s ease-in-out infinite; transform-origin: 31px 25px; }
        .dt-eye-r  { animation: dt-blink 4s ease-in-out infinite; transform-origin: 49px 25px; animation-delay: 0.05s; }
        .dt-tail   { animation: dt-tail-wag 0.9s ease-in-out infinite; transform-origin: 53px 49px; }
      `}</style>

      <svg width={size} height={size} viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ overflow: "visible" }}>
        {/* Shadow under DogTi */}
        <ellipse className="dt-shadow" cx="40" cy="76" rx="20" ry="4" fill="#92400e" />

        <g className="dt-body">
          {/* Tail (wags) */}
          <path className="dt-tail" d="M53 49 Q67 45 65 32" stroke="#a8672e" strokeWidth="7" strokeLinecap="round" fill="none" />

          {/* Torso */}
          <rect x="25" y="42" width="30" height="24" rx="13" fill="#d99a52" />
          {/* Belly patch */}
          <ellipse cx="40" cy="56" rx="8" ry="7" fill="#f3d9b1" />
          {/* Front paws */}
          <rect x="28" y="60" width="7" height="9" rx="3.5" fill="#c2793d" />
          <rect x="45" y="60" width="7" height="9" rx="3.5" fill="#c2793d" />

          {/* Collar */}
          <rect x="25" y="39" width="30" height="4.5" rx="2.25" fill="#f59e0b" />
          <circle cx="40" cy="46" r="2.5" fill="#fbbf24" />

          {/* Ears (floppy, behind head) */}
          <ellipse cx="19" cy="27" rx="7" ry="13.5" fill="#a8672e" transform="rotate(-18 19 27)" />
          <ellipse cx="61" cy="27" rx="7" ry="13.5" fill="#a8672e" transform="rotate(18 61 27)" />

          {/* Head */}
          <rect x="21" y="13" width="38" height="30" rx="15" fill="#d99a52" />

          {/* Eye whites */}
          <ellipse cx="31" cy="25" rx="6" ry="5.5" fill="white" />
          <ellipse cx="49" cy="25" rx="6" ry="5.5" fill="white" />
          {/* Pupils */}
          <circle className="dt-eye-l" cx="31" cy="25" r="3.4" fill="#1e1b4b" />
          <circle className="dt-eye-r" cx="49" cy="25" r="3.4" fill="#1e1b4b" />
          {/* Eye shine */}
          <circle cx="32.3" cy="23.3" r="1.2" fill="white" />
          <circle cx="50.3" cy="23.3" r="1.2" fill="white" />

          {/* Snout */}
          <rect x="30" y="30" width="20" height="13" rx="6.5" fill="#f3d9b1" />
          {/* Nose */}
          <ellipse cx="40" cy="35" rx="3.2" ry="2.4" fill="#3f2a1a" />
          {/* Mouth */}
          <path d="M40 37.5 Q40 40 36 40.5" stroke="#3f2a1a" strokeWidth="1.4" strokeLinecap="round" fill="none" />
          <path d="M40 37.5 Q40 40 44 40.5" stroke="#3f2a1a" strokeWidth="1.4" strokeLinecap="round" fill="none" />
        </g>
      </svg>
    </>
  );
}

export function DogTiMini() {
  return (
    <svg width="16" height="16" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="19" cy="27" rx="7" ry="13.5" fill="#a8672e" transform="rotate(-18 19 27)" />
      <ellipse cx="61" cy="27" rx="7" ry="13.5" fill="#a8672e" transform="rotate(18 61 27)" />
      <rect x="21" y="13" width="38" height="30" rx="15" fill="#d99a52" />
      <ellipse cx="31" cy="25" rx="6" ry="5.5" fill="white" />
      <ellipse cx="49" cy="25" rx="6" ry="5.5" fill="white" />
      <circle cx="31" cy="25" r="3.4" fill="#1e1b4b" />
      <circle cx="49" cy="25" r="3.4" fill="#1e1b4b" />
      <rect x="30" y="30" width="20" height="13" rx="6.5" fill="#f3d9b1" />
      <ellipse cx="40" cy="35" rx="3.2" ry="2.4" fill="#3f2a1a" />
      <rect x="25" y="42" width="30" height="24" rx="13" fill="#d99a52" />
    </svg>
  );
}

"use client";

// ---------------------------------------------------------------------------
// Don Tino — mascota robot de la plataforma (Home, Ayuda, Login)
// ---------------------------------------------------------------------------

export function RobotMascot({ size = 90 }: { size?: number } = {}) {
  return (
    <>
      <style>{`
        @keyframes robot-float {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-8px); }
        }
        @keyframes robot-shadow {
          0%, 100% { transform: scaleX(1);   opacity: 0.15; }
          50%       { transform: scaleX(0.7); opacity: 0.07; }
        }
        @keyframes robot-blink {
          0%, 88%, 100% { transform: scaleY(1); }
          92%           { transform: scaleY(0.08); }
        }
        @keyframes antenna-pulse {
          0%, 100% { opacity: 1;   r: 3; }
          50%       { opacity: 0.4; r: 4.5; }
        }
        @keyframes light-1 {
          0%,100% { opacity:1 } 20%,60% { opacity:0.2 }
        }
        @keyframes light-2 {
          0%,100% { opacity:0.2 } 40% { opacity:1 }
        }
        @keyframes light-3 {
          0%,100% { opacity:0.2 } 70% { opacity:1 }
        }
        @keyframes arm-wave {
          0%,100% { transform: rotate(0deg);   transform-origin: 20px 40px; }
          25%      { transform: rotate(-18deg); transform-origin: 20px 40px; }
          75%      { transform: rotate(10deg);  transform-origin: 20px 40px; }
        }
        .robot-body  { animation: robot-float  2.8s ease-in-out infinite; }
        .robot-shadow{ animation: robot-shadow 2.8s ease-in-out infinite; }
        .robot-eye-l { animation: robot-blink  3.5s ease-in-out infinite; transform-origin: 32px 24px; }
        .robot-eye-r { animation: robot-blink  3.5s ease-in-out infinite; transform-origin: 48px 24px; animation-delay: 0.05s; }
        .robot-ant   { animation: antenna-pulse 1.4s ease-in-out infinite; }
        .robot-l1    { animation: light-1 1.8s ease-in-out infinite; }
        .robot-l2    { animation: light-2 1.8s ease-in-out infinite; }
        .robot-l3    { animation: light-3 1.8s ease-in-out infinite; }
        .robot-arm-l { animation: arm-wave 2.8s ease-in-out infinite; }
      `}</style>

      <svg width={size} height={size} viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Shadow under robot */}
      <ellipse className="robot-shadow" cx="40" cy="76" rx="22" ry="4" fill="#6366f1" />

      <g className="robot-body">
        {/* Body */}
        <rect x="22" y="38" width="36" height="26" rx="8" fill="#4f46e5" />
        {/* Belly panel */}
        <rect x="29" y="44" width="22" height="13" rx="4" fill="#4338ca" />
        {/* Belly lights */}
        <circle className="robot-l1" cx="34" cy="50" r="2.5" fill="#a5f3fc" />
        <circle className="robot-l2" cx="40" cy="50" r="2.5" fill="#6ee7b7" />
        <circle className="robot-l3" cx="46" cy="50" r="2.5" fill="#fca5a5" />
        {/* Left arm (waves) */}
        <g className="robot-arm-l">
          <rect x="10" y="40" width="10" height="18" rx="5" fill="#4f46e5" />
          <circle cx="15" cy="60" r="5" fill="#6366f1" />
        </g>
        {/* Right arm (static) */}
        <rect x="60" y="40" width="10" height="18" rx="5" fill="#4f46e5" />
        <circle cx="65" cy="60" r="5" fill="#6366f1" />
        {/* Neck */}
        <rect x="35" y="32" width="10" height="8" rx="3" fill="#6366f1" />
        {/* Head */}
        <rect x="18" y="10" width="44" height="30" rx="12" fill="#6366f1" />
        {/* Eye whites */}
        <rect x="26" y="19" width="12" height="10" rx="5" fill="white" />
        <rect x="42" y="19" width="12" height="10" rx="5" fill="white" />
        {/* Pupils */}
        <circle className="robot-eye-l" cx="32" cy="24" r="4" fill="#1e1b4b" />
        <circle className="robot-eye-r" cx="48" cy="24" r="4" fill="#1e1b4b" />
        {/* Eye shine */}
        <circle cx="33" cy="22" r="1.5" fill="white" />
        <circle cx="49" cy="22" r="1.5" fill="white" />
        {/* Smile */}
        <path d="M30 33 Q40 39 50 33" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
        {/* Antenna stem */}
        <line x1="40" y1="10" x2="40" y2="3" stroke="#818cf8" strokeWidth="2.5" strokeLinecap="round" />
        {/* Antenna ball */}
        <circle className="robot-ant" cx="40" cy="2" r="3" fill="#a5b4fc" />
      </g>
      </svg>
    </>
  );
}

export function RobotMini() {
  return (
    <svg width="16" height="16" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="18" y="10" width="44" height="30" rx="12" fill="#6366f1" />
      <rect x="26" y="19" width="12" height="10" rx="5" fill="white" />
      <rect x="42" y="19" width="12" height="10" rx="5" fill="white" />
      <circle cx="32" cy="24" r="4" fill="#1e1b4b" />
      <circle cx="48" cy="24" r="4" fill="#1e1b4b" />
      <path d="M30 33 Q40 39 50 33" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      <line x1="40" y1="10" x2="40" y2="3" stroke="#818cf8" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="40" cy="2" r="3" fill="#a5b4fc" />
      <rect x="22" y="38" width="36" height="26" rx="8" fill="#4f46e5" />
    </svg>
  );
}

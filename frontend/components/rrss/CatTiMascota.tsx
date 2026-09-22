"use client";

// ---------------------------------------------------------------------------
// CatTi — la gata de la familia Tino, la que revisa las placas de redes
// sociales contra el mailing. Antes era el ícono `Cat` de lucide adentro de un
// cuadradito: una carita, no una mascota. Acá pasa a tener cuerpo propio,
// siguiendo el mismo patrón que sus hermanos (DogTiMascot.tsx,
// DonTinoTrabajando.tsx, DonaTinaTrabajando.tsx): un solo <svg> inline con su
// <style> de @keyframes y clases con prefijo propio ("ct-") para que no
// choquen si dos mascotas conviven en la misma pantalla.
//
// Por qué la lupa va DENTRO del mismo SVG y no como un ícono encima: es la
// misma lección que dejó el pico de Tinín. Si la lupa es un elemento aparte
// superpuesto, queda flotando suelta y no se agarra de ninguna pata; tiene que
// girar con la pata, desde el mismo pivote, dentro del mismo grupo animado.
//
// La lupa solo aparece cuando CatTi está trabajando: el cambio de silueta es
// parte de cómo se avisa que está revisando, no un adorno.
//
// prefers-reduced-motion: la barra de progreso ya cuenta placas, así que si la
// persona pidió menos movimiento el gato se queda quieto y no se pierde nada.
// (Tinín y Doña Tina todavía no lo respetan; cuando se los toque, este es el
// bloque a copiar.)
// ---------------------------------------------------------------------------

export function CatTiMascota({ size = 80, trabajando = false }: { size?: number; trabajando?: boolean }) {
  return (
    <>
      <style>{`
        @keyframes ct-respira   { 0%, 100% { transform: scaleY(1); }      50% { transform: scaleY(1.035); } }
        @keyframes ct-sombra    { 0%, 100% { transform: scaleX(1);   opacity: 0.16; } 50% { transform: scaleX(0.82); opacity: 0.09; } }
        @keyframes ct-parpadeo  { 0%, 91%, 100% { transform: scaleY(1); } 95% { transform: scaleY(0.08); } }
        @keyframes ct-cola      { 0%, 100% { transform: rotate(-9deg); }  50% { transform: rotate(13deg); } }
        @keyframes ct-oreja     { 0%, 82%, 100% { transform: rotate(0deg); } 88% { transform: rotate(-9deg); } 94% { transform: rotate(4deg); } }
        @keyframes ct-bigotes   { 0%, 100% { transform: rotate(0deg); }   50% { transform: rotate(1.6deg); } }
        /* La lupa barre de izquierda a derecha y frena un toque en cada punta:
           se lee como "está mirando ahí", no como un péndulo. */
        @keyframes ct-lupa      { 0% { transform: rotate(-16deg); } 45% { transform: rotate(14deg); } 55% { transform: rotate(14deg); } 100% { transform: rotate(-16deg); } }
        /* La cabeza acompaña a la lupa (misma duración) para que se vea que
           mira lo que la lupa está apuntando. */
        @keyframes ct-cabeza    { 0% { transform: rotate(3deg); } 45% { transform: rotate(-3.5deg); } 55% { transform: rotate(-3.5deg); } 100% { transform: rotate(3deg); } }
        @keyframes ct-brillo    { 0%, 100% { opacity: 0.25; } 50% { opacity: 0.85; } }

        .ct-cuerpo    { animation: ct-respira 3.2s ease-in-out infinite; transform-origin: 40px 70px; }
        .ct-sombra    { animation: ct-sombra 3.2s ease-in-out infinite; transform-origin: 40px 76px; }
        .ct-ojo-l     { animation: ct-parpadeo 4.4s ease-in-out infinite; transform-origin: 31.5px 27px; }
        .ct-ojo-r     { animation: ct-parpadeo 4.4s ease-in-out infinite; transform-origin: 48.5px 27px; animation-delay: 0.06s; }
        .ct-cola      { animation: ct-cola 3s ease-in-out infinite; transform-origin: 29px 66px; }
        .ct-oreja-l   { animation: ct-oreja 5.5s ease-in-out infinite; transform-origin: 24px 20px; }
        .ct-oreja-r   { animation: ct-oreja 5.5s ease-in-out infinite; transform-origin: 56px 20px; animation-delay: 1.1s; }
        .ct-bigotes-l { animation: ct-bigotes 3.6s ease-in-out infinite; transform-origin: 31px 36.5px; }
        .ct-bigotes-r { animation: ct-bigotes 3.6s ease-in-out infinite; transform-origin: 49px 36.5px; animation-delay: 0.4s; }

        /* Todo lo que cambia solo mientras revisa cuelga de .ct-on. */
        .ct-on .ct-cola   { animation-duration: 0.85s; }
        .ct-on .ct-lupa   { animation: ct-lupa 2.1s ease-in-out infinite; transform-origin: 47px 66px; }
        .ct-on .ct-cabeza { animation: ct-cabeza 2.1s ease-in-out infinite; transform-origin: 40px 44px; }
        .ct-on .ct-vidrio { animation: ct-brillo 2.1s ease-in-out infinite; }

        @media (prefers-reduced-motion: reduce) {
          .ct-root, .ct-root * { animation: none !important; }
        }
      `}</style>

      <svg
        className={trabajando ? "ct-root ct-on" : "ct-root"}
        width={size} height={size} viewBox="0 0 80 80" fill="none"
        xmlns="http://www.w3.org/2000/svg" style={{ overflow: "visible" }}
        role="img" aria-label="CatTi"
      >
        <ellipse className="ct-sombra" cx="40" cy="76" rx="19" ry="3.6" fill="#7c3aed" />

        <g className="ct-cuerpo">
          {/* Cola: el grupo entero gira desde donde nace, así la punta clara
              nunca se despega del resto. Va del lado izquierdo a propósito —
              la lupa sale del lado derecho y, con las dos juntas, la silueta
              se empastaba.

              La punta lleva contorno y un violeta más cargado: en #ede9fe sin
              borde, sobre la tarjeta blanca, no contrastaba con nada y de lejos
              parecía un mordisco en la cola. En oscuro se veía bien, y por eso
              no saltaba a la vista. */}
          <g className="ct-cola">
            <path d="M29 66 Q8 66 14 45" stroke="#8b5cf6" strokeWidth="7" strokeLinecap="round" fill="none" />
            <circle cx="14" cy="45" r="3.8" fill="#ddd6fe" stroke="#7c3aed" strokeWidth="1.5" />
          </g>

          {/* Cuerpo sentado: se ensancha hacia abajo, como un gato posado. */}
          <path
            d="M40 40 C49 40 54 52 55.5 64 C56 68 53.5 70 50 70 H30 C26.5 70 24 68 24.5 64 C26 52 31 40 40 40 Z"
            fill="#a78bfa"
          />
          <ellipse cx="40" cy="61" rx="9" ry="7.5" fill="#ede9fe" />

          {/* Patas delanteras. La derecha es la que sostiene la lupa. */}
          <rect x="30.5" y="64" width="8" height="6" rx="3" fill="#c4b5fd" />
          <rect x="41.5" y="64" width="8" height="6" rx="3" fill="#c4b5fd" />
          <line x1="33.2" y1="65.6" x2="33.2" y2="68.4" stroke="#a78bfa" strokeWidth="1" strokeLinecap="round" />
          <line x1="35.8" y1="65.6" x2="35.8" y2="68.4" stroke="#a78bfa" strokeWidth="1" strokeLinecap="round" />
          <line x1="44.2" y1="65.6" x2="44.2" y2="68.4" stroke="#a78bfa" strokeWidth="1" strokeLinecap="round" />
          <line x1="46.8" y1="65.6" x2="46.8" y2="68.4" stroke="#a78bfa" strokeWidth="1" strokeLinecap="round" />

          {/* Collar con chapita — el mismo ámbar de la gorrita de Tinín y del
              collar de DogTi: es lo que hace que se vean de la misma familia. */}
          <rect x="30" y="44.5" width="20" height="4.5" rx="2.25" fill="#f59e0b" />
          <circle cx="40" cy="51" r="2.8" fill="#fbbf24" />

          <g className="ct-cabeza">
            {/* Orejas: cada una gira desde su base, por eso van en su propio grupo. */}
            <g className="ct-oreja-l">
              <path d="M22.5 21 L24 5 L37 13.5 Z" fill="#a78bfa" />
              <path d="M25 19 L26 9.5 L33.5 14.5 Z" fill="#f9a8d4" />
            </g>
            <g className="ct-oreja-r">
              <path d="M57.5 21 L56 5 L43 13.5 Z" fill="#a78bfa" />
              <path d="M55 19 L54 9.5 L46.5 14.5 Z" fill="#f9a8d4" />
            </g>

            <rect x="21" y="15" width="38" height="29" rx="14.5" fill="#a78bfa" />

            {/* Ojos. La pupila es una rendija vertical y el iris es verde: es
                literalmente el "ojo de gato para el detalle" con el que se le
                habla al modelo (tino_personas.py, CATTI_BASE). Mientras revisa
                la pupila se dilata, como cuando un gato fija la vista. */}
            <ellipse cx="31.5" cy="27" rx="6" ry="5.6" fill="white" />
            <ellipse cx="48.5" cy="27" rx="6" ry="5.6" fill="white" />
            <g className="ct-ojo-l">
              <circle cx="31.5" cy="27" r="4.2" fill="#34d399" />
              <ellipse cx="31.5" cy="27" rx={trabajando ? 2.4 : 1.5} ry="4" fill="#1e1b4b" />
              <circle cx="33.1" cy="24.9" r="1.2" fill="white" />
            </g>
            <g className="ct-ojo-r">
              <circle cx="48.5" cy="27" r="4.2" fill="#34d399" />
              <ellipse cx="48.5" cy="27" rx={trabajando ? 2.4 : 1.5} ry="4" fill="#1e1b4b" />
              <circle cx="50.1" cy="24.9" r="1.2" fill="white" />
            </g>

            {/* Hocico */}
            <ellipse cx="35.5" cy="36.5" rx="6" ry="4.6" fill="#ede9fe" />
            <ellipse cx="44.5" cy="36.5" rx="6" ry="4.6" fill="#ede9fe" />
            <path d="M37 33 H43 L40 36.2 Z" fill="#f472b6" />
            <path d="M40 36.2 Q40 39.2 36.6 39.6" stroke="#7c3aed" strokeWidth="1.3" strokeLinecap="round" fill="none" />
            <path d="M40 36.2 Q40 39.2 43.4 39.6" stroke="#7c3aed" strokeWidth="1.3" strokeLinecap="round" fill="none" />

            {/* Bigotes: arrancan adentro del cachete y salen apenas 3px del
                contorno de la cabeza, para que no se pierdan sobre fondo claro
                ni sobre fondo oscuro. */}
            <g className="ct-bigotes-l" stroke="#7c3aed" strokeWidth="1.1" strokeLinecap="round">
              <line x1="31" y1="34.5" x2="18" y2="31.5" />
              <line x1="30.5" y1="36.5" x2="17" y2="36.5" />
              <line x1="31" y1="38.5" x2="18" y2="41.5" />
            </g>
            <g className="ct-bigotes-r" stroke="#7c3aed" strokeWidth="1.1" strokeLinecap="round">
              <line x1="49" y1="34.5" x2="62" y2="31.5" />
              <line x1="49.5" y1="36.5" x2="63" y2="36.5" />
              <line x1="49" y1="38.5" x2="62" y2="41.5" />
            </g>
          </g>

          {/* Lupa: mango + aro + vidrio, todo girando desde la pata derecha. */}
          {trabajando && (
            <g className="ct-lupa">
              <line x1="47" y1="66" x2="57.5" y2="52.5" stroke="#b45309" strokeWidth="3.4" strokeLinecap="round" />
              <circle className="ct-vidrio" cx="62" cy="46" r="8" fill="#a5f3fc" fillOpacity="0.45" />
              <circle cx="62" cy="46" r="8" stroke="#64748b" strokeWidth="3" fill="none" />
              <path d="M57.8 43.2 Q59.8 40.2 63 39.6" stroke="white" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity="0.85" />
            </g>
          )}
        </g>
      </svg>
    </>
  );
}

/** La carita sola, quieta y chiquita. La usa la barra de progreso para marcar
 *  por dónde va CatTi; no tiene animación propia, la mueve la barra.
 *
 *  El viewBox va recortado a la cabeza (y no 0 0 80 80 como el gato entero):
 *  a 17 px, con el viewBox completo, la carita quedaba minúscula y colgada
 *  arriba de una caja mayormente vacía. `size` es la altura. */
export function CatTiCarita({ size = 18 }: { size?: number }) {
  return (
    <svg width={Math.round((size * 40) / 43)} height={size} viewBox="20 3 40 43" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M22.5 21 L24 5 L37 13.5 Z" fill="#a78bfa" />
      <path d="M25 19 L26 9.5 L33.5 14.5 Z" fill="#f9a8d4" />
      <path d="M57.5 21 L56 5 L43 13.5 Z" fill="#a78bfa" />
      <path d="M55 19 L54 9.5 L46.5 14.5 Z" fill="#f9a8d4" />
      <rect x="21" y="15" width="38" height="29" rx="14.5" fill="#a78bfa" />
      <ellipse cx="31.5" cy="27" rx="6" ry="5.6" fill="white" />
      <ellipse cx="48.5" cy="27" rx="6" ry="5.6" fill="white" />
      <circle cx="31.5" cy="27" r="4.2" fill="#34d399" />
      <circle cx="48.5" cy="27" r="4.2" fill="#34d399" />
      <ellipse cx="31.5" cy="27" rx="1.6" ry="4" fill="#1e1b4b" />
      <ellipse cx="48.5" cy="27" rx="1.6" ry="4" fill="#1e1b4b" />
      <ellipse cx="35.5" cy="36.5" rx="6" ry="4.6" fill="#ede9fe" />
      <ellipse cx="44.5" cy="36.5" rx="6" ry="4.6" fill="#ede9fe" />
      <path d="M37 33 H43 L40 36.2 Z" fill="#f472b6" />
    </svg>
  );
}

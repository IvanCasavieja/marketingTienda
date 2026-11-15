import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
          950: "#1e1b4b",
        },
        navy: {
          800: "#0f1629",
          900: "#080d1a",
        },
        platform: {
          meta:       "#1877F2",
          google:     "#4285F4",
          tiktok:     "#FF0050",
          dv360:      "#34A853",
          sfmc:       "#00A1E0",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      // Elevación: tres escalones y nada más. `card` para lo que está apoyado
      // en la página, `pop` para lo que flota cerca de donde se tocó (menús,
      // la campanita) y `panel` para lo que tapa la pantalla (la ficha, el
      // editor). Una sombra nueva tiene que ser uno de estos tres.
      boxShadow: {
        card:  "0 1px 4px 0 rgb(0 0 0 / .08), 0 1px 2px -1px rgb(0 0 0 / .06)",
        "card-hover": "0 6px 16px 0 rgb(0 0 0 / .10), 0 2px 4px -2px rgb(0 0 0 / .06)",
        pop:   "0 16px 40px -12px rgb(15 23 42 / .28), 0 4px 10px -4px rgb(15 23 42 / .10)",
        panel: "0 24px 64px -16px rgb(15 23 42 / .40), 0 0 0 1px rgb(15 23 42 / .04)",
        glow:  "0 0 20px rgb(99 102 241 / .25)",
        brand: "0 0 0 3px rgb(99 102 241 / .15)",
      },
      // Una sola curva para todo lo que entra: arranca rápido y se apoya
      // suave. Lo que sale usa la de siempre (ease-in), más corta.
      transitionTimingFunction: {
        suave: "cubic-bezier(.2,.8,.2,1)",
      },
      animation: {
        "fade-in":       "fadeIn .25s ease-out",
        "slide-up":      "slideUp .3s ease-out",
        "pulse-slow":    "pulse 3s ease-in-out infinite",
        shimmer:         "shimmer 1.5s infinite",
        "slide-in-left": "slideInLeft .28s ease-out",
        "slide-in-right":"slideInRight .28s ease-out",
        // Menús y la campanita: aparecen desde donde se tocaron.
        "scale-in":      "scaleIn .16s cubic-bezier(.2,.8,.2,1)",
        // El editor en el teléfono: sube desde abajo, como una hoja.
        "sheet-up":      "sheetUp .3s cubic-bezier(.2,.8,.2,1)",
        // Tildar una tarea: el tilde late una vez.
        tilde:           "tilde .34s cubic-bezier(.2,.8,.2,1)",
        // Listas que llegan: cada tarjeta sube un poquito.
        rise:            "rise .32s cubic-bezier(.2,.8,.2,1) both",
      },
      keyframes: {
        fadeIn:       { from: { opacity: "0" },               to: { opacity: "1" } },
        slideUp:      { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        shimmer:      { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        slideInLeft:  { from: { opacity: "0", transform: "translateX(-14px)" }, to: { opacity: "1", transform: "translateX(0)" } },
        slideInRight: { from: { opacity: "0", transform: "translateX(14px)"  }, to: { opacity: "1", transform: "translateX(0)" } },
        scaleIn:      { from: { opacity: "0", transform: "scale(.96) translateY(4px)" }, to: { opacity: "1", transform: "none" } },
        sheetUp:      { from: { transform: "translateY(100%)" }, to: { transform: "translateY(0)" } },
        tilde:        { "0%": { transform: "scale(.55)" }, "60%": { transform: "scale(1.18)" }, "100%": { transform: "scale(1)" } },
        rise:         { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
      },
    },
  },
  plugins: [],
};

export default config;

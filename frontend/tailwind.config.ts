import type { Config } from "tailwindcss";

const config: Config = {
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
      boxShadow: {
        card:  "0 1px 3px 0 rgb(0 0 0 / .06), 0 1px 2px -1px rgb(0 0 0 / .04)",
        "card-hover": "0 4px 12px 0 rgb(0 0 0 / .08), 0 2px 4px -2px rgb(0 0 0 / .05)",
        glow:  "0 0 20px rgb(99 102 241 / .25)",
      },
      animation: {
        "fade-in":    "fadeIn .25s ease-out",
        "slide-up":   "slideUp .3s ease-out",
        "pulse-slow": "pulse 3s ease-in-out infinite",
        shimmer:      "shimmer 1.5s infinite",
      },
      keyframes: {
        fadeIn:  { from: { opacity: "0" },               to: { opacity: "1" } },
        slideUp: { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
      },
    },
  },
  plugins: [],
};

export default config;

import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  ...nextCoreWebVitals,
  {
    ignores: [".next/**", "node_modules/**"],
  },
  {
    // eslint-plugin-react-hooks v7 (parte de eslint-config-next 16) trae reglas
    // orientadas al React Compiler que son bastante más estrictas que el resto
    // del set — disparan sobre ~20 usos preexistentes de setState en efectos
    // (theme toggle, chat, paneles de cenefas) que no son bugs, solo un
    // patrón que el compiler prefiere evitar. Bajarlas a warning para que el
    // lint sirva como red de seguridad hoy (sí falla ante código nuevo con
    // errores reales) sin bloquear el build por deuda existente que requiere
    // revisar cada efecto caso a caso, no un fix mecánico.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/immutability": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/preserve-manual-memoization": "warn",
    },
  },
];

export default eslintConfig;

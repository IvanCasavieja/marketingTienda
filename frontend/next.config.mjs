/** @type {import('next').NextConfig} */
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const apiOrigin = new URL(apiUrl).origin;

// Next.js inyecta scripts inline propios en cada página (el payload de
// hidratación) incluso en export estático, así que script-src necesita
// 'unsafe-inline' — la alternativa correcta (nonce por request) requiere
// desactivar el prerenderizado estático de todas las páginas (todas salen
// hoy como ○ Static) para poder generar un nonce distinto en cada request,
// un cambio de arquitectura más grande. El riesgo que esto reabre (inyectar
// HTML/texto sin escapar que termine siendo un <script>) ya lo bloquea React
// por su cuenta — no hay ningún dangerouslySetInnerHTML en toda la app.
// connect-src necesita el origen de la API (Render en prod, localhost en
// dev) para que fetch/axios no se bloqueen.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com", // Tailwind/Radix usan style="" inline en JSX
  "img-src 'self' data:",
  "font-src 'self' data: https://fonts.gstatic.com",
  `connect-src 'self' ${apiOrigin}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig = {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Content-Security-Policy", value: csp },
        ],
      },
    ];
  },
  env: {
    NEXT_PUBLIC_API_URL: apiUrl,
  },
};

export default nextConfig;

/** @type {import('next').NextConfig} */
// NEXT_PUBLIC_API_URL está configurada en Vercel para "Production and
// Preview" con un solo valor (el backend de producción) -- no hay forma de
// darle un valor distinto solo a Preview desde el dashboard sin duplicar la
// variable. VERCEL_ENV la inyecta Vercel automáticamente en cada build
// ("production" | "preview" | "development"), sin que nadie la configure a
// mano, así que un build de Preview (cualquier rama que no sea la de
// producción, incluida staging) usa el backend de staging aunque
// NEXT_PUBLIC_API_URL diga otra cosa. Sin esto, cualquier deploy de Preview
// le pegaba en silencio al backend de producción (bug real: login fallaba
// con CORS porque el backend de prod no tiene el origen de staging en su
// allowlist).
const isPreview = process.env.VERCEL_ENV === "preview";
const apiUrl = isPreview
  ? "https://marketingtienda-staging.onrender.com/api/v1"
  : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
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
//
// Vercel inyecta su propio widget de feedback (vercel.live) SOLO en deploys
// de Preview -- lo dejamos pasar únicamente ahí (script/connect/frame) para
// no abrirle ese hueco a producción, que no lo necesita ni lo carga.
const vercelLive = isPreview ? " https://vercel.live" : "";
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${vercelLive}`,
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com", // Tailwind/Radix usan style="" inline en JSX
  "img-src 'self' data:",
  "font-src 'self' data: https://fonts.gstatic.com",
  `connect-src 'self' ${apiOrigin}${vercelLive}`,
  // 'self' NO cubre blob: -- sin esto, el <iframe> de preview de PDF en
  // FacturaUploadModal (blob URL armado en el cliente a partir de la
  // respuesta del backend) queda bloqueado en silencio por el navegador,
  // sin ningún error visible más que la consola.
  `frame-src 'self' blob:${vercelLive}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig = {
  // El editor de cenefas (materiales/cenefas/v2) usa Konva directo; konva
  // soporta opcionalmente node-canvas para renderizar en Node y el bundler
  // intenta resolver ese require("canvas") al armar el bundle de servidor
  // aunque Canvas.tsx nunca ejecuta Konva ahi (todo el uso vive dentro de
  // useEffect, client-only). Sin este alias, el build falla con "Module not
  // found: Can't resolve 'canvas'".
  turbopack: {
    resolveAlias: {
      canvas: "./stubs/empty-canvas.js",
    },
  },
  // Redirects de compatibilidad tras los renames "Herramientas"->"Materiales"
  // y "redexpress"->"redexpres" — cualquier bookmark o link viejo guardado
  // sigue funcionando en vez de tirar 404.
  async redirects() {
    return [
      { source: "/herramientas", destination: "/materiales", permanent: true },
      { source: "/herramientas/:path*", destination: "/materiales/:path*", permanent: true },
      { source: "/redexpress", destination: "/redexpres", permanent: true },
      { source: "/redexpress/:path*", destination: "/redexpres/:path*", permanent: true },
    ];
  },
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

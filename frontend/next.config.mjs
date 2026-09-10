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
  // 'self' NO cubre blob: -- sin esto, el <iframe> de preview de PDF en
  // FacturaUploadModal (blob URL armado en el cliente a partir de la
  // respuesta del backend) queda bloqueado en silencio por el navegador,
  // sin ningún error visible más que la consola.
  "frame-src 'self' blob:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig = {
  // `output: "standalone"` hace que el build deje en .next/standalone un
  // servidor autocontenido (con solo las dependencias que realmente se usan),
  // que es exactamente lo que copia frontend/Dockerfile.
  //
  // Va CONDICIONADO a DOCKER_BUILD y no fijo a propósito: en Vercel no hace
  // falta —construye con su propio pipeline— y no queremos que el deploy de
  // producción, que se dispara solo en cada push a main, cambie de forma por
  // una necesidad del contenedor. Sin la variable, este config es idéntico al
  // que Vercel viene construyendo.
  //
  // Sin esto el Dockerfile del frontend copiaba una carpeta que Next nunca
  // generaba, así que fallaba en el COPY. Estuvo roto desde el commit inicial
  // (c689f0d, 12/05/2026, donde entró como andamiaje) hasta el 10/09/2026, y
  // no se notó nunca porque el frontend va a Vercel y ese Dockerfile no lo
  // corre nadie: un archivo que no se ejecuta no puede fallar.
  ...(process.env.DOCKER_BUILD ? { output: "standalone" } : {}),

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

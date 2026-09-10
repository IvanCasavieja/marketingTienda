# Imagen del frontend. NO es como se despliega hoy —el frontend va a Vercel,
# que construye con su propio pipeline e ignora este archivo— pero tiene que
# funcionar, porque es la única forma de levantar la plataforma en un servidor
# propio sin depender de Vercel.
#
# Estuvo roto desde el commit inicial (c689f0d, 12/05/2026) hasta el
# 10/09/2026, de tres formas a la vez, y ninguna se notó nunca porque nadie lo
# ejecutó: un archivo que no corre no puede fallar.
#   1. Copiaba .next/standalone, que Next solo genera con output:"standalone".
#      Esa opción nunca estuvo en next.config (verificado con git log -S sobre
#      las tres versiones del archivo). Hoy la activa DOCKER_BUILD, ver abajo.
#   2. Instalaba con `npm install` y sin copiar el lockfile, así que la imagen
#      quedaba con versiones distintas de las que usan CI y Vercel.
#   3. No pasaba --legacy-peer-deps, que es lo que vercel.json sí pasa. O sea
#      que iba a chocar con el mismo conflicto de peer dependencies que obligó
#      a agregar ese flag allá.

FROM node:20-alpine AS deps
WORKDIR /app
# El lockfile va sí o sí: `npm ci` lo exige, y es lo que hace que la imagen
# instale exactamente lo mismo que CI (.github/workflows/ci.yml) y que Vercel.
COPY package.json package-lock.json ./
# --legacy-peer-deps replica lo que declara frontend/vercel.json. Si se saca de
# un lado hay que sacarlo del otro: los dos instalan el mismo árbol.
RUN npm ci --legacy-peer-deps

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Enciende output:"standalone" solo para esta construcción (ver next.config.mjs).
ENV DOCKER_BUILD=1
# La URL del backend se INCRUSTA en el build, no se lee al arrancar: además de
# viajar en el bundle, next.config la mete en el connect-src del CSP. Apuntar
# el contenedor a otro backend exige reconstruir la imagen; si no, el navegador
# bloquea todos los pedidos en silencio, sin error de servidor ni log.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# El servidor standalone escucha en localhost si no se le dice otra cosa, y
# desde afuera del contenedor eso es indistinguible de un servicio caído.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

# No correr como root. La imagen de node ya trae el usuario `node`.
USER node

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
# NO se copia /app/public: este proyecto no tiene esa carpeta y nunca la tuvo
# (verificado con git ls-files). El único asset estático es app/icon.svg, que
# vive dentro de app/ por convención del App Router y sale ya empaquetado en
# el build. COPY falla si la ruta de origen no existe, así que la línea que
# copiaba public/ —que estaba acá desde el commit inicial— rompía la
# construcción aunque todo lo demás estuviera bien. Si algún día se agrega
# frontend/public/, hay que volver a copiarla.

EXPOSE 3000
CMD ["node", "server.js"]

# Cómo levantar MKTG Platform en una PC nueva

## Paso 1 — Instalar prerequisitos (si no los tenés)
- **Git:** https://git-scm.com/download/win
- **Node.js 20:** https://nodejs.org (bajá la versión LTS)
- **Python 3.11:** https://www.python.org/downloads/
- **VS Code:** https://code.visualstudio.com
- **Extensión Claude Code en VS Code:** buscala en el marketplace de VS Code

---

## Paso 2 — Clonar el proyecto
Abrí una terminal (cmd o PowerShell) y ejecutá:

```
git clone https://github.com/IvanCasavieja/marketingTienda.git "MKTG Platform"
cd "MKTG Platform"
code .
```

VS Code se abre con el proyecto. Desde acá trabajás con Claude Code.

---

## Paso 3 — Instalar dependencias del frontend

En la terminal de VS Code:

```
cd frontend
npm install
```

---

## Paso 4 — Configurar el frontend para que se conecte a producción

Creá el archivo `frontend/.env.local` con este contenido:

```
NEXT_PUBLIC_API_URL=https://[TU-BACKEND-RENDER].onrender.com/api/v1
```

> El URL exacto lo encontrás en: **Render dashboard → tu servicio backend → arriba a la derecha dice la URL**
> Ejemplo: `https://mktg-platform-api.onrender.com/api/v1`

---

## Paso 5 — Levantar el frontend

```
cd frontend
npm run dev
```

Abrí `http://localhost:3000` — el frontend corre local y se conecta al backend de producción en Render. **No necesitás instalar PostgreSQL ni configurar el backend localmente.**

---

## Si también necesitás correr el backend en local

Solo si vas a modificar código Python:

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Creá `backend/.env` — los valores exactos están en **Render dashboard → tu servicio → Environment**.
Copiá todas las variables de ahí y pegálas en el archivo `.env`.

Luego:
```
uvicorn app.main:app --reload --port 8000
```

Y cambiá `frontend/.env.local` a `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`

---

## Instrucción para Claude en esta PC

Una vez que tengas VS Code abierto con la carpeta del proyecto, decile a Claude:

> "Leé el ONBOARDING.md y el archivo CLAUDE.md si existe. Este proyecto es MKTG Platform, una plataforma de marketing con Next.js (frontend) y FastAPI (backend). El repo es https://github.com/IvanCasavieja/marketingTienda.git — ya lo cloné y está en esta carpeta. Quiero seguir desarrollando desde donde lo dejé."

---

## Resumen de lo que es el proyecto

- **Frontend:** Next.js 14 en `/frontend` — páginas en `app/(dashboard)/`
- **Backend:** FastAPI en `/backend` — rutas en `app/api/routes/`, servicios en `app/services/`
- **Producción:** Frontend en Vercel (`marketing-tienda.vercel.app`), Backend en Render
- **Para deployar cambios:** `git add -A && git commit -m "..." && git push origin main` — Vercel y Render se actualizan solos

## Funcionalidades principales
- Dashboard de métricas (Meta Ads, Google Ads, TikTok, DV360)
- Análisis con Claude AI + Mesa Redonda (debate Claude vs ChatGPT vs Llama)
- Generador de Cenefas PPTX con templates guardados
- Multi-idioma (ES/EN/PT)
- Sistema de equipos con join codes

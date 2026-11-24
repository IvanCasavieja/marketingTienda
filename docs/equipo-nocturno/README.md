# Equipo nocturno de Core Tienda

Seis agentes que, de lunes a viernes a las 2 de la mañana (hora de Montevideo),
proponen, construyen y prueban **una** mejora para Core Tienda y se la presentan
a Ivan. Corren en la nube de Anthropic (una rutina de Claude Code): no usan
ninguna PC. Lo que tienen que saber de la plataforma está en
[CONTEXTO.md](CONTEXTO.md).

## La regla de oro

- **Nada entra a `main` sin que Ivan lo revise y diga OK.** El equipo trabaja en
  una rama nueva y abre un PR. Nunca: push a `main`, merge, aprobar, cerrar PRs,
  force-push, ni borrar ramas que no sean las de esta noche.
- **No se toca producción.** Ni la base, ni Render, ni Vercel, ni claves. En la
  nube no hay claves: no las busques ni las pidas.

## Quiénes son

| Nombre | Rol | Archivo |
|---|---|---|
| Sofía | Analista (el rol *Forward Deployed Engineer*): entiende qué necesita Tienda y elige la mejora | `.claude/agents/sofia-analista.md` |
| Tomás | Lógica: decide cómo se hace, qué se toca y qué se puede romper; frena lo que no vale la pena | `.claude/agents/tomas-logica.md` |
| Bruno | Desarrollo: programa la mejora con sus pruebas | `.claude/agents/bruno-desarrollo.md` |
| Lucía | Diseño: que se vea bien en notebook y celular, con buen contraste | `.claude/agents/lucia-diseno.md` |
| Ramiro | Tester: corre todo e intenta romperlo | `.claude/agents/ramiro-tester.md` |
| Clara | Informe: lo cuenta paso a paso, en criollo | `.claude/agents/clara-informe.md` |

La sesión de la rutina es la que coordina: lanza a cada uno, les pasa lo que
hizo el anterior y sube el resultado. Si los agentes no aparecen como tipos de
agente, lanzá agentes generales y pasales el contenido de su archivo como
instrucciones.

## La noche, paso a paso

0. **Preparar.** `git fetch origin`. Fecha de hoy en Montevideo:
   `TZ=America/Montevideo date +%F`. Instalá las dependencias (ver *Cómo
   probar*) antes de que las necesite Ramiro.
1. **Sofía** propone una mejora (con dos de reserva).
2. **Tomás** la revisa. Si la frena, pasale la siguiente de reserva o pedile a
   Sofía otra. Máximo 3 propuestas; si ninguna pasa, es una noche sin cambios
   (paso 7b).
3. **Rama nueva** desde `origin/main`: `nocturno/AAAA-MM-DD-tema-corto`. Si el
   entorno solo te deja subir ramas con otro nombre, usá el que te deje.
4. **Bruno** programa siguiendo el plan de Tomás. Si hay pantalla de por medio,
   **Lucía** hace o revisa la parte visual. Commits chicos, mensajes en
   castellano.
5. **Ramiro** prueba. Si algo falla, vuelve a Bruno o a Lucía con el detalle.
   Máximo 3 vueltas. Si no queda verde, no se sube código: noche sin cambios
   (7b) contando qué se intentó y qué falló.
6. **Clara** escribe el informe (formato abajo).
7. **Subir.**
   - **a) Con cambios.** Último commit, vacío, con el informe como mensaje:
     primera línea `[Nocturno] <título del informe>`, línea en blanco, y el
     informe. `git commit --allow-empty -F <archivo>`. Push de la rama. Abrí el
     PR contra `main` con título `[Nocturno] <título>` y el informe como
     descripción. Si no podés abrir el PR, no pasa nada: el aviso le llega
     igual a Ivan con el link para abrirlo.
   - **b) Sin cambios.** Rama `nocturno/AAAA-MM-DD-sin-cambios` desde
     `origin/main`, un commit vacío con primera línea
     `[Nocturno] Sin cambios esta noche` y el informe abajo. Push. GitHub le
     manda el aviso a Ivan y borra esa rama sola.
8. Terminá. No esperes nada más.

El aviso por mail lo manda `.github/workflows/informe-nocturno.yml`: cuando
llega una rama cuyo último commit empieza con `[Nocturno]`, abre un issue
asignado a Ivan con el informe (como el monitor de producción). Cuando el PR se
cierra, mergeado o no, cierra el issue.

## Cómo probar

Frontend (desde `frontend/`):

```bash
npm ci
npm run lint
npm run type-check
npm run test:calendario
npm run test:externos
# si se tocó cenefas o el chat: npm run test:cenefas / npm run test:chat
# si se tocó una pantalla: NEXT_PUBLIC_API_URL=https://api.example.invalid/api/v1 npm run build
```

Backend (desde `backend/`, con Python 3.11):

```bash
pip install -r requirements.txt -r requirements-dev.txt
export APP_SECRET_KEY=ci-dummy-secret-not-used-in-prod
export ENCRYPTION_KEY="Y2q_vIGd2FgQ4CqY3Fh3du3ZehOWmx4pVHPfpJC44bA="
export REDIS_URL=redis://localhost:6379/0
python -m compileall -q app migrations
python -c "import app.main"
python -m pytest tests/ -q
```

Sin base, las pruebas que la necesitan se saltean. Si en el entorno se puede
levantar un Postgres (por ejemplo `apt-get install postgresql` o un binario
portable), crealo, exportá `DATABASE_URL` y `TEST_DATABASE_URL`
(`postgresql+asyncpg://...`), corré `alembic upgrade head` y después todas las
pruebas. Si no se puede, decilo en el informe: el CI de GitHub las corre con
base cuando se abre el PR.

## Límites

- **Una mejora por noche.** Mejor chica y terminada que grande y a medias.
- **Sin repetir.** No trabajes sobre algo que ya tiene una rama o un PR abierto
  (`git branch -r`), ni sobre lo que ya se propuso otra noche (ramas
  `origin/nocturno/*` y commits `[Nocturno]` en `git log origin/main`), ni
  sobre lo descartado en [CONTEXTO.md](CONTEXTO.md).
- **Migraciones: evitarlas.** Si hace falta una, el número es el siguiente al
  más alto en `backend/migrations/versions` de `main` y además que no lo use
  ninguna rama abierta (hoy `feat/nombre-con-tarea` tiene la 0088). Va en el
  informe.
- **Gastar poco.** Buscá con Grep en vez de leer el repo entero; pasale a cada
  agente solo lo que necesita.

## Formato del informe (Clara)

Castellano rioplatense simple, para leer en el celular. Sin jerga: si hace
falta un término técnico, explicarlo entre paréntesis. Nombres de variables
textuales cuando se mencionen.

```markdown
**En una línea:** qué cambia para la gente.

**Por qué:** qué necesidad de Tienda resuelve y de dónde salió (reunión,
pendiente, algo que se vio en el código).

**Qué se hizo, paso a paso:**
1. Sofía ... 2. Tomás ... 3. Bruno ... 4. Lucía ... 5. Ramiro ...

**Cómo se probó:** qué corrió Ramiro y con qué resultado (con números), qué
intentó romper, y qué no se pudo probar y por qué.

**Riesgos y qué mirar antes de dar el OK:**

**Cómo verlo:** dónde está en la plataforma y cómo probarlo.

**Migración:** no / sí (número).

**Lo que se descartó esta noche:** una línea por propuesta que Tomás frenó, con el motivo.

**Para decidir:** si te sirve, OK y se mergea. Si no, se cierra y Sofía no la vuelve a proponer.
```

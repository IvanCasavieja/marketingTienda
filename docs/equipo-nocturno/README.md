# Equipo nocturno de Core Tienda

Siete agentes que, de lunes a viernes a las 2 de la mañana (hora de
Montevideo), **recorren Core Tienda entera como las personas que la usan**,
anotan todo lo que encuentran en un cuaderno, eligen lo que más vale la pena,
lo construyen, lo prueban y se lo presentan a Ivan con el antes y el después.
Corren en la nube de Anthropic (una rutina de Claude Code): no usan ninguna PC.

Lo que tienen que saber de la plataforma: [CONTEXTO.md](CONTEXTO.md) (visión,
personas, reglas) y [el mapa](plataforma/README.md) (pantalla por pantalla).
Cómo hacen el trabajo: los skills `.claude/skills/recorrido-humano/` y
`.claude/skills/cuaderno-de-hallazgos/`.

## La regla de oro

- **Nada entra a `main` sin que Ivan lo revise y diga OK.** El equipo trabaja en
  una rama nueva y abre un PR. Nunca: push a `main`, merge, aprobar, cerrar PRs,
  force-push, ni borrar ramas que no sean las de esta noche. La única rama
  que se escribe directo es la del cuaderno (`equipo-nocturno/cuaderno`).
- **No se toca producción.** Ni la base, ni Render, ni Vercel, ni claves. En la
  nube no hay claves: no las busques ni las pidas.

## Quiénes son

| Nombre | Rol | Archivo |
|---|---|---|
| Sofía | Analista (Forward Deployed Engineer + investigación de usuarios + producto): recorre, mantiene el cuaderno y elige | `.claude/agents/sofia-analista.md` |
| Martina | Usuaria a ciegas: hace de persona nueva, solo ve capturas y toca por coordenadas | `.claude/agents/martina-usuaria.md` |
| Lucía | Diseñadora de producto: revisa todas las capturas con ojo de persona y hace la parte visual con antes/después | `.claude/agents/lucia-diseno.md` |
| Tomás | Líder técnico: decide si sigue, arma el plan y los riesgos | `.claude/agents/tomas-logica.md` |
| Bruno | Desarrollador: programa con pruebas, textos en 3 idiomas y permisos en el servidor | `.claude/agents/bruno-desarrollo.md` |
| Ramiro | QA: pruebas con base, punta a punta en el navegador, barrido antes/después, intenta romperla | `.claude/agents/ramiro-tester.md` |
| Clara | Informe: lo cuenta en criollo, con imágenes | `.claude/agents/clara-informe.md` |

La sesión de la rutina es la que coordina: lanza a cada uno, les pasa lo que
hizo el anterior (resumido, con las rutas a capturas y archivos) y sube el
resultado. Si los agentes no aparecen como tipos de agente, lanzá agentes
generales y pasales el contenido de su archivo como instrucciones. Los
subagentes no lanzan otros subagentes: eso lo hacés vos.

## La noche, paso a paso

Hay unas **3 horas**. Tiempos de referencia entre paréntesis: si una etapa se
pasa, cerrala con lo que haya y seguí.

0. **Preparar** (15 min). `git fetch origin`. Fecha y día en Montevideo:
   `TZ=America/Montevideo date +"%F %A"`. Instalá las dependencias (*Cómo
   probar*), levantá la plataforma con sus tres cuentas (*La plataforma
   andando*) y el navegador (skill `recorrido-humano`, *Preparar*). Traé el
   cuaderno (skill `cuaderno-de-hallazgos`, *Traerlo al empezar la noche*).
1. **Recorrido — Sofía** (45 min). Le pasás la dirección, el archivo de
   cuentas (`$S/cuentas.env`), el día de la semana, `$S` y dónde está el
   cuaderno. Hace las tareas reales (el ciclo completo con la agencia y la
   zona del día), el barrido automático con datos, mira todas las hojas de
   contacto y anota en el cuaderno. Devuelve dos consignas para Martina.
2. **A la vez** (25 min):
   - **Martina** hace las dos consignas a ciegas (le pasás las cuentas, la
     dirección y las consignas; nada más).
   - **Lucía** hace la revisión visual del barrido (`$S/recorrido`).
3. **Consolidar y proponer — Sofía** (15 min). Le pasás lo de Martina y
   Lucía. Lo suma al cuaderno, ordena y propone el trabajo de la noche (un
   arreglo o un paquete del mismo flujo) con dos reservas. **Subí el
   cuaderno ya** (aunque después no haya código).
4. **Tomás** lo revisa. Si la frena, pasale la reserva. Máximo 3 propuestas;
   si ninguna pasa, es una noche sin cambios (paso 8b), pero con recorrido.
5. **Rama nueva** desde `origin/main`: `nocturno/AAAA-MM-DD-tema-corto`. Si el
   entorno solo te deja subir ramas con otro nombre, usá el que te deje.
6. **Construir** (45 min). Si hay pantalla, primero **Lucía saca las capturas
   de antes**. **Bruno** programa siguiendo el plan y lo mira andando.
   **Lucía** hace o corrige lo visual y arma el antes/después. Commits chicos,
   en castellano. En el cuaderno, lo elegido pasa a «En curso».
7. **Ramiro** prueba las cinco capas (25 min). Si algo falla, vuelve a Bruno o
   a Lucía con el detalle. Máximo 3 vueltas. Si no queda verde, no se sube
   código: noche sin cambios (8b) contando qué se intentó y qué falló.
8. **Informe y subida** (10 min).
   - Subí al cuaderno las imágenes del antes/después y la evidencia de los 3
     hallazgos principales, con el historial de la noche. **Push del cuaderno
     antes del informe** (las imágenes del mail salen de ahí).
   - **Clara** escribe dos cosas (formato abajo), con las direcciones de esas
     imágenes: **el mail** (corto, para Ivan) y **el detalle** (para el PR).
   - **a) Con cambios.** Último commit, vacío, con **el mail** como mensaje:
     primera línea `[Nocturno] <título corto>`, línea en blanco, y el mail.
     `git commit --allow-empty -F <archivo>`. Push de la rama. Abrí el PR
     contra `main` con ese mismo título y **el detalle** como descripción. Si
     no podés abrir el PR, no pasa nada: el aviso le llega igual a Ivan con el
     link para abrirlo.
   - **b) Sin cambios.** Rama `nocturno/AAAA-MM-DD-sin-cambios` desde
     `origin/main`, un commit vacío con primera línea
     `[Nocturno] Sin cambios esta noche` y el mail abajo. Push. GitHub le
     manda el aviso a Ivan y borra esa rama sola.
9. Cerrá el navegador (`navegador.py cerrar`) y terminá. No esperes nada más.

Si un push falla (por ejemplo, GitHub dice que la app de Claude no tiene
acceso al repo), no te trabes: guardá el trabajo como parche en `$S`, escribí
el informe contando qué pasó y avisale a Ivan con lo que tengas a mano.

El aviso por mail lo manda `.github/workflows/informe-nocturno.yml`: cuando
llega una rama cuyo último commit empieza con `[Nocturno]`, abre un issue
que menciona a Ivan con el mail de Clara: le llega un solo mail (para eso, en
GitHub el repo tiene que estar en «Watch → Participating and @mentions»; si
lo sigue entero, le llega también el aviso del PR). Ivan decide
respondiendo ese mail con **ok** (se mergea si las pruebas están en verde) o
**no** (se cierra): lo hace `.github/workflows/ok-por-mail.yml`. Cuando el PR
se cierra, mergeado o no, se cierra el issue. La noche siguiente, Sofía pasa
el hallazgo a Hechos o a Descartados según lo que decidió Ivan.

## Cómo probar

Frontend (desde `frontend/`):

```bash
npm ci
npm run lint
npm run type-check
npm run test:calendario
npm run test:externos
npm run test:redexpres
# si se tocó cenefas, el chat o colocación: npm run test:cenefas / test:chat / test:colocacion
# si se tocó una pantalla: NEXT_PUBLIC_API_URL=https://api.example.invalid/api/v1 npm run build
```

(Mirá `frontend/package.json`: todas las `test:*` que existan.)

Backend (desde `backend/`, con Python 3.11, en un venv para que no choque con
el sistema):

```bash
python3.11 -m venv $S/venv && . $S/venv/bin/activate
pip install -q --prefer-binary -r requirements.txt -r requirements-dev.txt
export APP_SECRET_KEY=ci-dummy-secret-not-used-in-prod
export ENCRYPTION_KEY="Y2q_vIGd2FgQ4CqY3Fh3du3ZehOWmx4pVHPfpJC44bA="
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/core_pruebas
python -m compileall -q app migrations
python -c "import app.main"
python -m pytest tests/ -q
```

Sin base, las pruebas que la necesitan se saltean (y `import app.main` pide
`DATABASE_URL`, aunque sea de mentira). Con el Postgres de *La plataforma
andando*, creá otra base vacía solo para las pruebas (`createdb
core_tests`), corré `alembic upgrade head` con `DATABASE_URL` apuntando a ella
y después todas las pruebas con
`TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/core_tests`.
Si no se pudo levantar Postgres, decilo en el informe: el CI de GitHub las
corre con base cuando se abre el PR.

## La plataforma andando (entorno de pruebas)

Pedido de Ivan (24/11/2026): que el equipo no mire solo el código, que
**use** la plataforma como la usa la gente, también como la agencia, con
usuarios propios. Se levanta entera dentro de esta nube, desde cero cada
noche: base vacía, servidor, web y tres cuentas. Nada sale de acá ni toca
producción, y al terminar se borra sola.

| Cuenta | Usuario | Qué ve |
|---|---|---|
| Equipo nocturno (superadmin) | `equipo-nocturno@example.com` | Todo, como el equipo de Tienda (5 mundos) |
| Agencia de prueba (externa) | `agencia-de-prueba@example.com` | Solo su tablero y sus tareas, como Publicis |
| Local de prueba (Redexpres) | `local-de-prueba@example.com` | Lo de su local («Mi pedido», fotos) |

Las contraseñas se inventan cada noche (abajo); no van al repo ni al informe.
Las cuentas las crea `backend/scripts/cuentas_de_prueba.py`
(`app/services/cuentas_de_prueba.py`), que se niega a correr sin
`ENTORNO_DE_PRUEBAS=true`. Para ver la plataforma como alguien del equipo sin
superadmin, creá una cuenta desde `/admin` (ver el mapa).

```bash
S=<tu scratchpad>
# 1. Postgres. Si apt no anda, probá `pip install postgresql-wheel` (un
#    Postgres que se instala con pip) y si tampoco, seguí sin base y decilo.
apt-get update -qq && apt-get install -y -qq postgresql > $S/pg.log 2>&1
service postgresql start
su postgres -c "psql -qc \"ALTER USER postgres PASSWORD 'postgres'\""
su postgres -c "createdb core_pruebas"

# 2. Base y cuentas (desde backend/, con el venv de *Cómo probar* activo)
export APP_SECRET_KEY=solo-pruebas ENCRYPTION_KEY="Y2q_vIGd2FgQ4CqY3Fh3du3ZehOWmx4pVHPfpJC44bA="
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/core_pruebas
alembic upgrade head
export ENTORNO_DE_PRUEBAS=true
for v in CLAVE_EQUIPO_NOCTURNO CLAVE_AGENCIA_DE_PRUEBA CLAVE_LOCAL_DE_PRUEBA; do
  echo "$v=Np-$(python -c 'import secrets; print(secrets.token_urlsafe(12))')"
done > $S/cuentas.env
set -a; . $S/cuentas.env; set +a; python scripts/cuentas_de_prueba.py

# 3. El servidor, con la IA simulada: Don Tino y la revisión de piezas
#    contestan con reglas, sin clave y sin gastar (sirve para pantallas y
#    permisos, no para juzgar lo que diría Claude).
APP_ENV=development APP_ALLOWED_ORIGINS=http://localhost:3000 MANTENIMIENTO_AL_ARRANCAR=false \
SYNC_INTERVAL_HOURS=0 WATCHLIST_CHECK_INTERVAL_HOURS=0 CAMPAIGN_ALERTS_CHECK_INTERVAL_HOURS=0 \
COTIZACION_AUTO_UPDATE=false CENEFAS_CURADURIA=false MANTENER_DESPIERTO_MIN=0 \
  nohup python scripts/servidor_ia_simulada.py --port 8000 > $S/backend.log 2>&1 &

# 4. La web (desde frontend/, con npm ci ya hecho), armada como en producción
#    para que cada pantalla abra rápido en el barrido. El cartel amarillo de
#    abajo dice que es el entorno de pruebas.
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 NEXT_PUBLIC_ENTORNO=pruebas npm run build > $S/build.log 2>&1
nohup npx next start -p 3000 > $S/frontend.log 2>&1 &

# 5. El navegador (skill recorrido-humano)
pip install -q playwright pillow && python -m playwright install --with-deps chromium
```

Después de cambiar código: frená la web (`pkill -f "next start"`), volvé a
correr el paso 4; si cambió el servidor, frenalo y volvé a correr el paso 3.

Se entra por `http://localhost:3000/login`. La base arranca vacía: lo que se
quiera ver hay que crearlo como lo haría la gente (ver `tareas.md` del skill
`recorrido-humano` y el mapa). Si el servidor o la web no levantan, mirá
`backend.log` / `build.log` / `frontend.log`, y si no se arregla en unos
minutos, seguí con el código y contalo en el informe.

Si algún día hay un servidor de pruebas fijo (Render con su propia base, nunca
la de producción): `ENTORNO_DE_PRUEBAS=true` y las tres `CLAVE_...` en sus
variables, y las cuentas se crean solas al arrancar; `/health` dice
`"entorno": "pruebas"`. Su web lleva `NEXT_PUBLIC_ENTORNO=pruebas`.

## Límites

- **Un PR por noche:** un arreglo o un paquete de arreglos del mismo flujo,
  terminado. Mejor mediano y terminado que grande y a medias.
- **El recorrido no se saltea**, aunque la noche termine sin código: es lo
  que hace que el equipo conozca la plataforma.
- **Sin repetir.** No trabajes sobre algo que ya tiene una rama o un PR abierto
  (`git branch -r`), ni sobre lo que ya se propuso otra noche (ramas
  `origin/nocturno/*`, commits `[Nocturno]` en `git log origin/main`, «En
  curso» y «Descartados» del cuaderno), ni sobre lo descartado en
  [CONTEXTO.md](CONTEXTO.md).
- **Migraciones: evitarlas.** Si hace falta una, el número es el siguiente al
  más alto en `backend/migrations/versions` de `main` y además que no lo use
  ninguna rama abierta. Va en el informe.
- **Gastar con cabeza.** Buscá con Grep en vez de leer el repo entero; a cada
  agente pasale solo lo que necesita (rutas a archivos y capturas, no su
  contenido). Las capturas se miran: no las describas de memoria.

## Formato del informe (Clara)

Ivan, 25/11/2026: "no se entiende el mail, le falta info, no me explican en
el cuerpo las cosas, el asunto está horrendamente largo". Por eso son dos
textos: **el mail**, para que Ivan entienda y decida en un minuto desde el
celular, y **el detalle**, para el PR, con todo lo técnico.

### El título (el asunto del mail)

`[Nocturno] 🌙 <de 2 a 5 palabras>`, **45 caracteres como máximo** en total.
Sin dos puntos ni explicaciones: lo que cambia y dónde. GitHub le agrega la
fecha sola. El `[Nocturno]` del principio es obligatorio (sin eso no sale el
mail).

- Bien: `[Nocturno] 🌙 Redexpres sin trabas`, `[Nocturno] 🌙 Fotos panorámicas`
- Mal: `[Nocturno] Redexpres sin trabas: el local sabe qué pasa con su pedido y la Planilla queda a mano`

### El mail

Ivan lo lee en el celular (25/11/2026: "hacelo bonito… que de celular se vean
bien"). Hasta ~1500 caracteres sin contar las imágenes. Frases cortas, como
se lo contarías en persona. Cada cosa explicada: qué pantalla, quién la usa,
qué pasaba y qué pasa ahora. Los títulos de cada parte van con `###` y su
emoji, tal cual el molde: en el mail se ven como títulos grandes y separan
bien en una pantalla chica. Párrafos de 3 líneas como mucho; nada de tablas
(en el celular se cortan).

**Prohibido en el mail** (va en el detalle): códigos de hallazgo (H-0xx),
emojis o colores de gravedad (🔴🟠🟡), nombres de los agentes, palabras del
proceso (cuaderno, recorrido, zona, capas, «a ciegas», hallazgos), cuántas
pantallas o capturas se miraron, nombres de archivos, de variables o de
ramas, y links que no sean las imágenes.

```markdown
### ✨ Qué cambia
2 o 3 frases: quién lo va a notar, en qué pantalla y qué ve ahora. Ej.: «En
"Mi pedido", el encargado del local ahora ve un cartel verde cuando su pedido
ya está confirmado, y a quién pedirle si necesita cambiar algo.»

![Antes y ahora: el pedido confirmado en el celular del local](https://raw.githubusercontent.com/.../equipo-nocturno/cuaderno/cuaderno/recorridos/AAAA-MM-DD/...-antes-despues.jpg)

### 🤔 Por qué
La situación real, contada como un caso. Ej.: «Probando como un encargado de
local, quisimos corregir 300 a 30 cenefas y no se podía: el pedido ya estaba
confirmado, pero la pantalla no lo decía ni a quién pedirle.»

### 👀 Cómo verlo
Cuando esté publicado: pantalla → qué tocar → qué vas a ver.

### ✅ Probado
Una línea. Ej.: «Todo en verde, también en el celular.» Si algo no se pudo
probar, va acá.

### ⚠️ Ojo
Un riesgo en una línea, o «Nada que veamos».

### 🛠️ En qué anduvo el equipo
Una o dos frases: qué parte de la plataforma usaron esta noche y como quién.
Ej.: «Usamos Redexpres como un local y como el equipo, y armamos una pieza
con la agencia de punta a punta: anduvo bien.»

### 🔎 Además encontramos
- Hasta 3, una línea cada uno, con a quién le pasa y qué le pasa. Ej.: «El
  local no puede mandar una foto panorámica de la góndola: la rechaza.»
```

Una noche sin cambios: `### 🌙 Esta noche no hubo cambios` y por qué en una
frase, y después **En qué anduvo el equipo** y **Además encontramos**.

Al pie el aviso agrega solo el link al PR y cómo decidir (ok / no): no lo
repitas.

### El detalle (descripción del PR)

Para quien quiera ver todo: acá sí van los códigos, los números y los nombres.

```markdown
**Qué cambia:** lo mismo que el mail, en una línea.

**Hallazgos que resuelve:** H-0xx (gravedad) — una línea cada uno, de dónde salió.

**Qué vio el recorrido:** N pantallas × cuentas × vistas; N hallazgos nuevos
(🔴 n · 🟠 n · 🟡 n); cómo le fue a Martina a ciegas.
[Cuaderno completo](https://github.com/.../blob/equipo-nocturno/cuaderno/cuaderno/CUADERNO.md)

**Qué se hizo, paso a paso:** 1. Sofía ... 2. Martina ... 3. Lucía ... 4. Tomás ... 5. Bruno ... 6. Ramiro ...

**Cómo se probó:** las cinco capas de Ramiro con números, y qué no se pudo probar y por qué.

**Migración:** no / sí (número).

**Lo que se descartó esta noche:** una línea por propuesta que Tomás frenó, con el motivo.
```

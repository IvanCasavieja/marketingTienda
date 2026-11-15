# Migración a Azure — plan y guía paso a paso

> **Estado: preparado, no ejecutado.** Todavía no se creó nada en Azure. Este
> documento, `infra/azure/` y `.github/workflows/deploy-azure.yml` son el plan
> listo para usar. Hoy la plataforma sigue en Vercel + Render + Supabase y nada
> de lo que se agregó cambia eso.
>
> Lo que dice "**a confirmar**" es conocimiento general de Azure o de Supabase
> que no se pudo probar acá. Lo que cita un archivo (`ruta:línea`) se leyó en el
> código. Lo que dice "**verificado en la documentación**" se leyó en Microsoft
> Learn el 12/11/2026.

## 1. La respuesta corta

**Sí: `git push` a `main` va a seguir desplegando solo.** Hoy lo hacen Vercel y
Render mirando el repositorio; en Azure lo hace un workflow de GitHub Actions
(`.github/workflows/deploy-azure.yml`) que en cada push construye las dos
imágenes Docker, las sube al registro de la empresa y actualiza las dos
aplicaciones. Para quien programa no cambia nada: se sigue haciendo push y a los
pocos minutos está arriba. El avance se ve en la pestaña **Actions** de GitHub.

Tres cosas más, en una línea cada una:

- **Todo queda adentro del tenant de Azure de la empresa**: aplicación, base de
  datos, imágenes y logs. GitHub entra a Azure sin contraseña guardada (OIDC).
- **De la lista que mandó IT sobran cuatro piezas** (Entra External ID, Blob
  Storage, SignalR, Azure Functions): la plataforma no usa nada de Supabase
  salvo la base Postgres. Detalle en la sección 2.
- **El workflow está apagado** hasta que alguien ponga la variable
  `AZURE_DEPLOY_ENABLED` en `true`. Mientras tanto no hace nada.

## 2. Arquitectura elegida

| Hoy | En Azure | Notas |
| --- | --- | --- |
| Frontend en Vercel (Next.js 16) | **Azure Container Apps** — app `mktg-frontend`, puerto 3000, 1 a 2 réplicas | Usa `frontend/Dockerfile`, que CI ya construye en cada push (`.github/workflows/ci.yml:83`) |
| Backend en Render (FastAPI) | **Azure Container Apps** — app `mktg-backend`, puerto 8000, **siempre 1 réplica** | Usa `backend/Dockerfile`; CI ya lo arranca contra una base vacía (`ci.yml:85-108`) |
| Supabase (solo como Postgres) | **Azure Database for PostgreSQL Flexible Server** | Datos migrados con `pg_dump` / `pg_restore` |
| Deploy automático de Vercel y Render | **GitHub Actions** + **Azure Container Registry** | `.github/workflows/deploy-azure.yml` |
| Logs en los paneles de Render y Vercel | **Log Analytics** | Los contenedores escriben a stdout y Azure lo recoge |
| Variables de entorno en Render | **Secretos de la Container App** | Se cargan una vez con el Bicep |
| Mail de recuperar la contraseña por SendGrid | **Azure Communication Services Email** (por SMTP) | Opcional: SendGrid sigue andando igual. Ver "Mails" abajo |

### Mails

La plataforma manda un solo mail: el de **recuperar la contraseña** ("Olvidé
mi contraseña" en el login). Sale por SMTP o por SendGrid, según lo que esté
configurado (`backend/app/services/email_service.py`). Sin ninguno, la pantalla
avisa que la recuperación por mail no está activada y que hay que pedirle a
quien administra una contraseña nueva.

**En Render, por Resend.** El plan gratis de Render no deja salir conexiones
SMTP (15/11/2026: Zoho respondía desde una PC y desde Render se colgaba) y la
cuenta de SendGrid se quedó sin crédito. Resend manda por su API web, igual
que Tuki: `EMAIL_PROVIDER=resend`, `RESEND_API_KEY` (secreto) y `EMAIL_FROM`
con una dirección de un dominio verificado en Resend. Gratis hasta 3.000
mails por mes.

**La casilla de Zoho Mail** también está configurada, por SMTP, para cuando el
backend esté donde se pueda usar SMTP (Azure o un plan pago de Render). Datos de
Zoho para una casilla con dominio propio (a confirmar en la configuración de
Zoho; las cuentas del centro de datos europeo usan `smtppro.zoho.eu`):

| Variable | Valor |
| --- | --- |
| `EMAIL_PROVIDER` | `smtp` |
| `SMTP_HOST` | `smtppro.zoho.com` |
| `SMTP_PORT` | `465` |
| `SMTP_SEGURIDAD` | `ssl` |
| `SMTP_USER` | la dirección completa de la casilla |
| `SMTP_PASSWORD` | su contraseña, o una "contraseña de aplicación" de Zoho si la casilla tiene verificación en dos pasos (**secreto**) |
| `EMAIL_FROM` | vacío (sale de la casilla) o `Core Tienda <la misma casilla>`: Zoho rechaza otro remitente |

Para que no caiga en spam, el dominio de la casilla tiene que tener SPF y DKIM
configurados en Zoho.

En Azure no cambia nada: es la misma casilla y las mismas variables, con el
secreto en la Container App. Si más adelante se quiere mandar desde el tenant
de la empresa, lo natural es **Azure Communication Services Email**, que tiene un SMTP propio. Datos a confirmar con
la guía de Microsoft al configurarlo:

| Variable | Valor |
| --- | --- |
| `EMAIL_PROVIDER` | `smtp` |
| `SMTP_HOST` | `smtp.azurecomm.net` |
| `SMTP_PORT` | `587` |
| `SMTP_SEGURIDAD` | `starttls` |
| `SMTP_USER` | el usuario SMTP que da Communication Services (va atado a un app registration de Entra ID) |
| `SMTP_PASSWORD` | el secreto de ese app registration (**secreto**: va con los secretos de la Container App) |
| `EMAIL_FROM` | `Core Tienda <DoNotReply@<dominio verificado>>`: el remitente tiene que ser de un dominio conectado al recurso (el que da Azure o uno propio de la empresa) |

Microsoft 365 también tiene SMTP (`smtp.office365.com`), pero Microsoft viene
retirando el login con usuario y contraseña para SMTP en Exchange Online: no
conviene depender de eso.

Hasta que eso exista, si en Render está `SENDGRID_API_KEY`, se sigue usando
SendGrid sin tocar nada.

### Por qué Container Apps también para el frontend (y no Static Web Apps)

IT propuso Static Web Apps como primera opción para el frontend. Se eligió
Container Apps por tres motivos:

1. **El soporte de Next.js "híbrido" en Static Web Apps sigue en preview**, con
   límite de 250 MB por aplicación, y en ese modo **no se puede enlazar un
   backend en Container Apps** (verificado en la documentación:
   `learn.microsoft.com/azure/static-web-apps/deploy-nextjs-hybrid`). Montar
   producción sobre una función en preview no se justifica.
2. **El contenedor ya existe y se prueba solo.** `frontend/Dockerfile` construye
   el servidor autocontenido de Next (`output: "standalone"`,
   `frontend/next.config.mjs:53`) y CI lo construye en cada push.
3. **Una sola forma de desplegar** para las dos mitades: mismo registro, mismo
   workflow, mismos logs. Menos cosas distintas para que IT mantenga.

App Service (la otra alternativa de IT) también serviría para correr los mismos
contenedores. Container Apps es más simple de dejar en "una réplica fija" y se
cobra por uso; si IT ya opera App Service y lo prefiere, el cambio es de
infraestructura, no de código.

### Lo que NO hace falta de la lista de IT, y por qué

| Pieza propuesta | ¿Hace falta? | Qué se verificó |
| --- | --- | --- |
| **Entra External ID** (reemplazo de Supabase Auth) | No | El login es propio: usuarios y contraseñas en la base, tokens JWT firmados por el backend (`backend/app/core/security.py`, `backend/app/core/deps.py:62-95`, `backend/app/api/routes/auth.py:37-41`). No hay Supabase Auth que reemplazar. |
| **Blob Storage** (reemplazo de Supabase Storage) | No | Los archivos se guardan como bytes en Postgres (sección 5). No hay ningún cliente de Supabase Storage en el código. |
| **SignalR** (reemplazo de realtime) | No | No hay websockets ni Supabase Realtime. Lo que se ve "en vivo" (búsqueda de precios, análisis con IA) es una respuesta HTTP que va llegando de a partes desde el propio backend (`backend/app/api/routes/precios.py:311`, `backend/app/api/routes/analytics.py:301`). |
| **Azure Functions** (reemplazo de edge functions) | No | No hay edge functions. Todo el código de servidor está en el backend. |

Cómo se verificó: se buscó `supabase`, `createClient`, `storage.from`,
`realtime`, `signalr` y `WebSocket` en todo el repositorio. Supabase aparece
solo en comentarios sobre el *pooler* de conexiones de la base
(`backend/app/core/database.py:12-19`). No hay ninguna librería de Supabase ni
en `backend/requirements.txt` ni en el frontend.

IT tiene razón en que Supabase es lo que más fricción da, pero acá esa fricción
se reduce a **mover una base Postgres**, que es la parte más estándar.

Si más adelante se quiere que la gente entre con su usuario corporativo
(Entra ID), eso es un proyecto aparte, con cambios en el código de login. No es
parte de esta migración.

## 3. Qué hay que pedirle a IT

Para copiar y pegar en el mail:

1. **Una suscripción y un resource group** para la plataforma (por ejemplo
   `rg-mktg-platform-prod`), con los *resource providers* `Microsoft.App`,
   `Microsoft.ContainerRegistry`, `Microsoft.DBforPostgreSQL`,
   `Microsoft.OperationalInsights` y `Microsoft.ManagedIdentity` registrados.
2. **Región.** Sugerencia: **Brazil South**, la más cercana a Uruguay. Es una
   sugerencia: decide IT según sus políticas, y hay que confirmar que la
   suscripción tenga cupo ahí para PostgreSQL Flexible Server y Container Apps
   (a confirmar). El Bicep permite poner la base en otra región
   (`postgresLocation`), aunque lo ideal es todo junto.
3. **Quién corre el Bicep.** Necesita **Owner** sobre el resource group, o
   **Contributor + Role Based Access Control Administrator** (o User Access
   Administrator): la plantilla crea asignaciones de roles, y Contributor solo
   no alcanza para eso. Lo razonable es que lo corra IT.
4. **Un app registration en Entra ID para GitHub Actions**, con una
   **credencial federada**:
   - Emisor: `https://token.actions.githubusercontent.com`
   - Sujeto: `repo:IvanCasavieja/marketingTienda:ref:refs/heads/main`
   - Audiencia: `api://AzureADTokenExchange`
   - Sin *client secret*: no hay contraseña que guardar ni que rotar.
5. **Permisos para ese app registration**: `Contributor` sobre el resource group
   y `AcrPush` sobre el registro. El Bicep los asigna solo si se le pasa
   `githubPrincipalId` (el Object ID de la *Enterprise Application*); si no, IT
   los asigna a mano.
6. **Tres datos de vuelta**: *Application (client) ID*, *Directory (tenant) ID*
   y *Subscription ID*. No son secretos.
7. **Políticas del tenant que puedan frenar el despliegue**: si exigen red
   privada (VNet) para bases de datos, si prohíben aplicaciones con acceso
   público, etiquetas obligatorias, convención de nombres. Ver sección 7.
8. **Un subdominio**, si se quiere una dirección propia en vez de la que da
   Azure (por ejemplo `marketing.<dominio>` y `api-marketing.<dominio>`), y
   quién maneja ese DNS.
9. **Acceso de lectura** para quien mantiene la plataforma (`Reader` y
   `Log Analytics Reader` sobre el resource group) para poder ver los logs.
10. **Mails (opcional).** Un recurso de **Azure Communication Services Email**
    con un dominio conectado (el que da Azure o uno de la empresa) y el usuario
    y secreto SMTP para la plataforma. Es para el mail de recuperar la
    contraseña; ver "Mails" en la sección 2.
11. **Una definición sobre el repositorio.** Hoy está en una cuenta personal de
    GitHub (`IvanCasavieja/marketingTienda`). Si IT quiere pasarlo a una
    organización de la empresa, conviene hacerlo **antes**: la credencial
    federada del punto 4 lleva el nombre del repositorio.

## 4. Paso a paso

### Antes de empezar

- Herramientas (quien ejecute): Azure CLI (`az`), que trae Bicep, y el cliente
  de PostgreSQL (`pg_dump`, `pg_restore`, `psql`) en una versión **igual o mayor
  a la de las dos bases**.
- **Sobre la plantilla:** `infra/azure/main.bicep` y `main.bicepparam` compilan
  sin errores ni advertencias con Bicep 0.49.2 (`bicep build`, `build-params` y
  `lint`). Eso valida sintaxis y tipos, **nada más**. **Nunca se desplegó ni se
  corrió `what-if` contra una suscripción real**: la máquina donde se preparó no
  tiene Azure CLI ni acceso a Azure. El primer `what-if` (paso 1) es la prueba
  de verdad, y es esperable tener que ajustar algún detalle.
- Tener a mano las **variables de entorno actuales de Render** (panel →
  Environment). Se copian tal cual; tres importan especialmente:
  - `ENCRYPTION_KEY`: **tiene que ser exactamente la misma**. Con ella se cifran
    los tokens de las plataformas publicitarias guardados en la base
    (`backend/app/core/security.py:50-55`); con otra clave no se pueden leer y
    habría que volver a cargar todas las conexiones.
  - `APP_SECRET_KEY`: la misma. Es la clave del endpoint de sincronización del
    buscador de precios y, si `JWT_SECRET_KEY` no está definida, también la que
    firma las sesiones (`backend/app/core/config.py:20-21`).
  - `JWT_SECRET_KEY`: si en Render está definida, la misma.
- La versión de Postgres de Supabase: correr `SELECT version();`. El servidor
  de Azure tiene que ser de versión **igual o mayor** (parámetro
  `postgresVersion`; está en 16 por defecto).

### Paso 1 — Crear la infraestructura base (Fase 1)

Crea todo menos las dos aplicaciones: logs, registro de imágenes, identidad,
entorno de Container Apps y Postgres.

```bash
az login
az account set --subscription <SUBSCRIPTION_ID>

# Los secretos van por variables de entorno, no escritos en un archivo.
export MKTG_PG_PASSWORD='<solo letras y números, 32 o más>'
export MKTG_APP_SECRET_KEY='<la de Render>'
export MKTG_ENCRYPTION_KEY='<la de Render>'
# ...y el resto de las MKTG_* que lista infra/azure/main.bicepparam

# Primero mirar qué haría, sin crear nada:
az deployment group what-if -g <RESOURCE_GROUP> \
  -f infra/azure/main.bicep -p infra/azure/main.bicepparam

# Después, crear:
az deployment group create -g <RESOURCE_GROUP> \
  -f infra/azure/main.bicep -p infra/azure/main.bicepparam
```

> **La contraseña de Postgres tiene que ser solo letras y números.** Va adentro
> de `DATABASE_URL` sin escapar. Con símbolos habría que escaparla con `%`, y
> ese signo rompe las migraciones: Alembic guarda la URL en un archivo de
> configuración que interpreta el `%` (`backend/migrations/env.py:36-37`). Que
> sea larga compensa.

Anotar las **salidas** del despliegue: `acrName`, `backendAppName`,
`frontendAppName`, `apiUrl`, `postgresHost`. La dirección del backend ya se
conoce en este punto aunque la aplicación todavía no exista.

### Paso 2 — Configurar GitHub

En el repositorio: **Settings → Secrets and variables → Actions → pestaña
Variables**. Son todas *variables*; **no hace falta ningún secret**.

| Variable | Valor |
| --- | --- |
| `AZURE_CLIENT_ID` | *Application (client) ID* del app registration |
| `AZURE_TENANT_ID` | *Directory (tenant) ID* |
| `AZURE_SUBSCRIPTION_ID` | ID de la suscripción |
| `AZURE_RESOURCE_GROUP` | nombre del resource group |
| `AZURE_ACR_NAME` | salida `acrName` |
| `AZURE_BACKEND_APP` | salida `backendAppName` (`mktg-backend`) |
| `AZURE_FRONTEND_APP` | salida `frontendAppName` (`mktg-frontend`) |
| `AZURE_API_URL` | salida `apiUrl` (termina en `/api/v1`) |
| `AZURE_DEPLOY_ENABLED` | `true` — **recién en el paso 4** |

`AZURE_API_URL` queda **incrustada en la imagen del frontend** cuando se
construye, y además entra en la política de seguridad del navegador
(`frontend/Dockerfile:33-38`, `frontend/next.config.mjs:2-3`). Si algún día
cambia la dirección del backend, hay que cambiar la variable y volver a
desplegar; no alcanza con tocar algo en Azure.

### Paso 3 — Copiar los datos de Supabase (ensayo)

El primer pasaje es un **ensayo**: se copia la base mientras Render sigue siendo
producción, para probar todo con datos reales. El día del corte se repite
(paso 7).

1. **Abrir el firewall de Postgres para la máquina que migra**: volver a correr
   el paso 1 con `ipMigracion = '<IP pública>'`.
2. **Sacar la copia de Supabase**, usando la **conexión directa**, no el pooler:

   ```bash
   pg_dump --format=custom --no-owner --no-privileges --schema=public \
     --file=mktg.dump \
     "postgresql://postgres:<clave>@db.<ref>.supabase.co:5432/postgres"
   ```

   - El pooler en modo transacción (puerto 6543), que es el que usa el backend,
     **no sirve** para `pg_dump`.
   - La conexión directa de Supabase puede ser solo IPv6 (a confirmar). Si la
     red no tiene IPv6, usar el pooler en modo **sesión** (puerto 5432 del host
     `...pooler.supabase.com`).
   - `--schema=public` deja afuera los esquemas internos de Supabase (`auth`,
     `storage`, `realtime`, `extensions`, `vault`...), que no se usan y no
     existen en Azure.
   - `--no-owner --no-privileges` deja afuera los roles propios de Supabase
     (`anon`, `authenticated`, `service_role`, `supabase_admin`), que tampoco
     existen en Azure y harían fallar la restauración.
3. **Restaurar en Azure**:

   ```bash
   pg_restore --no-owner --no-privileges --exit-on-error \
     --dbname="postgresql://mktgadmin:<clave>@<postgresHost>:5432/mktg_platform?sslmode=require" \
     mktg.dump
   ```

   - Si se queja de que el esquema `public` ya existe, es esperable (a
     confirmar): en ese caso sacar `--exit-on-error` y revisar que sea el único
     error.
   - **Extensiones**: las tablas usan `gen_random_uuid()`
     (`backend/migrations/versions/0002_cenefas_v2_tables.py:25`, `0041`,
     `0052`), que desde Postgres 13 viene incluida, sin extensión. No se
     encontró ningún `CREATE EXTENSION` en las migraciones. Si la restauración
     igual pidiera una, en Azure hay que habilitarla antes en el parámetro del
     servidor `azure.extensions` (a confirmar).
4. **Comparar** las dos bases: misma cantidad de filas en las tablas grandes y
   el mismo valor en `SELECT version_num FROM alembic_version;`.

> **El orden importa: los datos van antes que el backend.** El backend crea las
> tablas solo apenas arranca (`backend/app/main.py:56-69`). Si arrancara contra
> la base vacía, la restauración chocaría con esas tablas. Por eso el Bicep
> tiene dos fases.

### Paso 4 — Primer despliegue (Fase 2)

1. **Subir las imágenes, sin desplegar.** En GitHub: poner
   `AZURE_DEPLOY_ENABLED = true`, ir a **Actions → Deploy a Azure → Run
   workflow**, rama `main`, y tildar **solo_imagenes**. Anotar el SHA completo
   del commit.
2. **Crear las aplicaciones en modo ensayo**: correr de nuevo el Bicep con

   ```
   param desplegarApps = true
   param imagenTag = '<SHA completo del paso anterior>'
   param mantenimientoAlArrancar = false
   ```

   `mantenimientoAlArrancar = false` es lo que lo hace un ensayo: el backend
   atiende la aplicación pero **no** corre las tareas automáticas —
   sincronización con las plataformas publicitarias, chequeo de precios,
   alertas, avisos del calendario, purga (`backend/app/main.py:98-151`). Sin
   esto habría dos servidores (Render y Azure) mandando avisos y pegándole a
   las APIs de Meta y Google a la vez.
3. Desde acá **cada push a `main` despliega solo** en Azure, además de en
   Vercel y Render, que siguen como siempre.

> **Ojo con volver a correr el Bicep más adelante:** deja las aplicaciones en la
> imagen que diga `imagenTag`. Si se pasa un SHA viejo, vuelve atrás la versión.
> Pasar siempre el SHA que esté desplegado (lo muestra `/health`).

### Paso 5 — Lista de verificación

- [ ] `https://<backend>/health` devuelve `{"status":"ok","db":"ok","commit":"<7 letras>"}`,
      y el commit coincide con el último push (`backend/app/main.py:289-312`).
- [ ] El frontend abre `/login` y **se puede entrar** con un usuario real.
- [ ] Después de entrar, las pantallas cargan datos. Si en la consola del
      navegador aparecen errores de CORS o de *Content Security Policy*, casi
      seguro `AZURE_API_URL` o `FRONTEND_URL` / `APP_ALLOWED_ORIGINS` no
      coinciden con las direcciones reales.
- [ ] **Cenefas**: generar un lote de punta a punta (subir Excel, vista previa,
      confirmar, descargar el PPTX). Es lo que más memoria usa.
- [ ] **Buscador de precios**: una búsqueda en todas las cadenas. El backend va
      a salir a internet desde otra dirección IP, y algún sitio podría tratar
      distinto a un centro de datos de Azure (a confirmar, solo se sabe
      probando).
- [ ] **Recuperación de contraseña**: pedir el mail y ver que el enlace apunte
      al frontend nuevo (`backend/app/api/routes/auth.py:208`).
- [ ] **Análisis con IA y chat**: una consulta de cada uno.
- [ ] **Conexiones a plataformas**: que se listen y que una sincronización
      manual funcione. Si falla al descifrar, `ENCRYPTION_KEY` no es la de
      Render.
- [ ] **Facturación y validación de RRSS**: abrir un documento o una imagen ya
      cargados (prueba que los archivos guardados en la base se migraron).
- [ ] En Azure, **Log stream** del backend: sin errores al arrancar.
- [ ] Un `git push` de prueba a `main`: el workflow termina en verde y `/health`
      muestra el commit nuevo.

### Paso 6 — Direcciones, dominio propio y CORS

Por defecto Azure da direcciones del tipo
`https://mktg-frontend.<algo>.<región>.azurecontainerapps.io`. Sirven para
producción; el dominio propio es opcional.

Lo que hay que mantener coherente:

| Qué | Dónde | Valor |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | variable de GitHub `AZURE_API_URL` | dirección pública del **backend** + `/api/v1` |
| `FRONTEND_URL` | parámetro `frontendUrl` del Bicep | dirección pública del **frontend**, sin barra final. Va en los mails de recuperación de contraseña y se agrega sola a CORS (`backend/app/core/config.py:23`, y la propiedad `allowed_origins` más abajo). Si no se define en Azure, queda el valor por defecto, que es el dominio de Vercel. |
| `APP_ALLOWED_ORIGINS` | parámetro `origenesPermitidos` | orígenes extra del frontend, separados por coma |

Con **dominio propio**: IT crea los registros DNS que pide Azure (un CNAME y un
TXT de validación por cada dominio; el certificado lo puede emitir Azure gratis
— a confirmar), se actualizan los tres valores de la tabla, se corre el Bicep y
se hace un push para que el frontend se reconstruya con la URL nueva.

Si frontend y backend quedan como subdominios del **mismo** dominio de la
empresa, la cookie de sesión deja de ser "de terceros" para el navegador. Hoy es
entre dominios distintos (`backend/app/core/deps.py:71-79`), y eso es lo que los
navegadores vienen restringiendo. Es una mejora sobre la situación actual, no un
requisito: el frontend manda igual el token en el encabezado.

**Redirect URIs de OAuth:** no hay que cambiar ninguna. Las variables
`META_REDIRECT_URI`, `GOOGLE_REDIRECT_URI`, `TIKTOK_REDIRECT_URI` y
`DV360_REDIRECT_URI` existen en la configuración
(`backend/app/core/config.py:109-125`), pero no se encontró ningún lugar del
backend que las lea ni ninguna ruta de *callback*: las conexiones usan tokens
cargados a mano. No hay nada que registrar en las consolas de Meta, Google o
TikTok por cambiar de dirección.

**Lo que sí apunta a Render y hay que actualizar después del corte:**

- `backend/scripts/cargar_calendario_desde_excel.py:62` y
  `backend/scripts/cargar_descripciones_aprobadas.py:36` usan por defecto
  `https://marketingtienda.onrender.com/api/v1` (se puede pisar con la variable
  `MKTG_API_URL`).
- `ONBOARDING.md`, `backend/.env.example` y el comentario final de
  `backend/Dockerfile` todavía hablan solo de Render.
- El `backend/.env` de cada PC de trabajo apunta a la base de Supabase: hay que
  cambiar `DATABASE_URL` a la de Azure y agregar la IP de esa PC al firewall de
  Postgres.

### Paso 7 — El corte

Elegir un horario sin uso. Lo que se escriba en la plataforma entre la copia
final y el cambio de dirección se pierde, así que hay que **frenar el uso**.

1. Avisar al equipo y esperar a que no haya cenefas generándose.
2. **Suspender el servicio en Render.** Así nadie escribe en la base vieja y sus
   tareas automáticas se detienen.
3. **Copia final**: repetir el paso 3, vaciando antes la base de Azure (agregar
   `--clean --if-exists` al `pg_restore`, o borrar y recrear la base).
4. **Pasar el backend de Azure a producción**: correr el Bicep con
   `mantenimientoAlArrancar = true` (y el `imagenTag` actual).
5. Repetir la lista de verificación del paso 5.
6. **Avisar la dirección nueva** (o cambiar el DNS si hay dominio propio). La
   gente va a tener que iniciar sesión de nuevo: la sesión se guarda por
   dirección.
7. Sacar `ipMigracion` del Bicep para cerrar el firewall.

**Durante una o dos semanas no se borra nada:** Supabase queda intacto (ya nadie
escribe), Render suspendido, Vercel funcionando.

### Vuelta atrás

- **Antes de avisar la dirección nueva (pasos 1 a 5 del corte):** reanudar el
  servicio de Render. Nadie llegó a usar Azure, no se pierde nada.
- **Después:** reanudar Render y avisar que se vuelve a la dirección de Vercel.
  **Lo cargado en Azure desde el corte no está en Supabase**: hay que traerlo
  con un `pg_dump` / `pg_restore` en sentido contrario, o aceptar perderlo.
  Por eso conviene decidir "seguimos o volvemos" en las primeras horas.
- **Un deploy que sale mal ya estando en Azure** no necesita nada de esto: si la
  versión nueva no arranca, Azure deja atendiendo a la anterior (a confirmar) y
  el workflow termina en rojo. Para volver a una versión anterior, revertir el
  commit y hacer push.

### Cuando esté estable

Desconectar el repositorio de Vercel y de Render (si no, siguen desplegando en
cada push), bajar un último respaldo de Supabase y recién ahí dar de baja los
tres servicios.

## 5. Archivos en disco y Redis

### Disco: no se pierde nada que importe

En Container Apps el disco del contenedor se borra en cada reinicio o deploy. Se
revisó todo el backend buscando escrituras a disco (`open(`, `tempfile`,
`write_text`, `write_bytes`, `mkdir`, `.save(`):

| Qué | Dónde vive | ¿Se pierde? |
| --- | --- | --- |
| Archivos que sube la gente (Excel, PPTX, facturas, placas) | Se leen en memoria (`backend/app/core/uploads.py:6-21`) y se guardan **en Postgres** como bytes: `backend/app/models/cenefa_job.py:80-82`, `cenefa_template.py:17`, `cenefa_template_v2.py:33`, `facturacion_documento.py:24`, `rrss_validacion.py:51,73` | No. Viajan con la base. |
| Archivos que genera la plataforma (PPTX de cenefas, Excel de informes) | Se arman en memoria y van a Postgres o directo a la descarga (`backend/app/services/cenefas/jobs.py:59-61`) | No |
| Plantillas base de cenefas y lista de sucursales | Adentro de la imagen (`backend/app/static/cenefa_templates/`, `backend/app/services/scraper/sucursales_gdu.json`) | No |
| Token de acceso a la API de precios de GDU (dura unos 15 días) | Archivo en `SCRAPER_DATA_DIR`, por defecto `/tmp/scraper` (`backend/app/services/scraper/gdu_rest.py:138-174`, `live_search.py:43`) | Sí, y **no importa**: se pide de nuevo solo en la siguiente búsqueda. |
| Cotización del dólar para esa búsqueda (dura 1 día) | Archivo en la misma carpeta (`gdu_rest.py:189-223`) | Sí, y se vuelve a bajar sola. Único matiz: si justo después de un reinicio la página del BROU no responde, no hay "cotización de ayer" de respaldo y usa un valor fijo de 40 (`gdu_rest.py:209-217`). |

**Conclusión: no hace falta Blob Storage ni un disco persistente.** Esos dos
archivos son las únicas escrituras a disco que se encontraron, y son cachés que
se regeneran. `/tmp` se puede escribir dentro del contenedor, así que tampoco
hay que configurar `SCRAPER_DATA_DIR`.

Consecuencia a tener presente: **los archivos están en la base**, así que el
tamaño de la base es el tamaño de los archivos. Hoy ronda el medio GB
(`backend/migrations/versions/0053_productos_indice_url_duplicado.py:12`). El
disco mínimo de Azure son 32 GB, así que desaparece el problema de cuota que
había en Supabase.

### Por qué el backend va con una sola réplica

No es por el disco, es por la memoria del proceso:

- Corre **adentro del proceso** las tareas periódicas: sincronización de
  métricas, chequeo de precios, alertas de campañas, cotización, curaduría,
  purga y avisos del calendario (`backend/app/main.py:98-151`). Con dos
  réplicas se harían dos veces; con cero (apagado por inactividad) no se harían.
- Los renders de cenefas se encolan con un semáforo en memoria
  (`backend/app/services/cenefas/jobs.py:36-49`). Con dos réplicas dejaría de
  encolar entre ellas.
- El límite de pedidos por minuto y un caché de búsquedas de 60 segundos también
  son por proceso (`backend/app/core/rate_limit.py:29`,
  `backend/app/services/scraper/live_search.py:1055-1057`).

Por eso el Bicep fija mínimo = máximo = 1. El frontend no guarda nada y puede
tener dos.

### Redis: no hace falta

Hoy producción funciona sin Redis (`backend/app/services/cenefas/jobs.py:63-65`)
y el código lo trata como opcional: si no responde, falla en 0,2 segundos y
sigue (`backend/app/core/redis_client.py:13-28`). Sin Redis se pierden dos cosas,
igual que hoy:

- El **candado** que evita que dos procesos sincronicen a la vez
  (`backend/app/services/auto_sync.py:70-81`, `watchlist_service.py:213-220`,
  `campaign_alerts_service.py:198-205`). Con una sola réplica no hace falta.
- La **memoria de "cuándo fue la última corrida"**: sin ella, la sincronización
  de métricas arranca 2 minutos después de **cada** reinicio o deploy
  (`backend/app/services/auto_sync.py:43-62`). Varios deploys en un día son
  varias sincronizaciones.

El login, el bloqueo por intentos fallidos y la recuperación de contraseña no
dependen de Redis: están en Postgres (`backend/app/models/user.py:26-29`,
`backend/app/models/password_reset_token.py:12-14`).

El Bicep **no crea Redis**. Si algún día se quiere, se agrega Azure Cache for
Redis y se pasa `REDIS_URL` como secreto, sin tocar código.

## 6. Cambios en el código

Mínimos, y sin cambiar nada en Render ni en una PC:

- `backend/app/core/config.py`: el backend se reconoce como "servidor
  desplegado" también cuando existe `CONTAINER_APP_NAME`, que Azure Container
  Apps pone sola en todo contenedor (verificado en la documentación:
  `learn.microsoft.com/azure/container-apps/environment-variables`). Antes solo
  miraba `RENDER_GIT_COMMIT`. Además, la función nueva `commit_desplegado()`
  lee el commit de `RENDER_GIT_COMMIT` o, si no está, de `GIT_COMMIT`, que es la
  que pasa el workflow.
- `backend/app/main.py`: `/health` usa esa función, y se actualizó el mensaje
  del log.
- `backend/tests/test_senal_azure.py`: tests nuevos para esas dos cosas.
- `backend/app/services/email_service.py` (15/11/2026): el mail de recuperar la
  contraseña sale por SMTP (Azure Communication Services) o por SendGrid, según
  lo configurado. Variables nuevas `EMAIL_PROVIDER` y `SMTP_*` en
  `backend/app/core/config.py`; tests en `backend/tests/test_mail_recuperacion.py`.

`GIT_COMMIT` sola **no** hace que una máquina se crea el servidor, a propósito:
ese freno es el que evita que una PC apuntada a la base de producción corra
migraciones y borre archivos (`backend/app/core/config.py:66-81`).

## 7. Decisiones abiertas y riesgos

**Para decidir con IT**

1. **Red privada o pública.** El Bicep arranca simple: la base acepta conexiones
   de "servicios de Azure" (la regla `0.0.0.0`), protegida por contraseña y
   TLS. Esa regla deja pasar a cualquier recurso de Azure, no solo a los
   nuestros. Lo más cerrado es poner el entorno de Container Apps en una VNet y
   la base detrás de un *private endpoint*. Eso **obliga a recrear el entorno**
   (a confirmar), así que si IT lo va a exigir conviene saberlo antes del corte.
2. **Tamaño de la base.** Con B1ms la base admite **35 conexiones de usuario**,
   y el backend puede abrir hasta **35** (15 fijas + 20 extra,
   `backend/app/core/database.py:8-9`), sin contar la de las migraciones ni el
   momento del deploy en que conviven la versión vieja y la nueva. El nivel
   Burstable no tiene el pooler integrado (PgBouncer). Ambos datos verificados
   en la documentación (`learn.microsoft.com/azure/postgresql/flexible-server/concepts-limits`).
   En uso normal difícilmente se llegue, pero **es justo**. Opciones: empezar
   con B1ms y mirar la métrica de conexiones, o ir directo a B2s (414). Es un
   parámetro del Bicep (`postgresSkuName`).
3. **Usuario de la base.** El backend se conecta con el usuario administrador
   del servidor. Funciona y es lo más simple; lo prolijo es crear un rol propio
   para la aplicación. Queda como mejora.
4. **Dónde se guardan los secretos.** Quedan como secretos de la Container App.
   Si IT exige Azure Key Vault, es un agregado en el Bicep, sin cambios de
   código.
5. **¿El deploy espera a los tests?** Hoy Vercel y Render despliegan sin esperar
   a CI, y el workflow de Azure hace lo mismo para no cambiar el comportamiento.
   Se puede hacer que espere.
6. **Dominio propio**: sí o no, y cuál.
7. **Repositorio en cuenta personal** (sección 3, punto 10).

**Riesgos conocidos**

- **La plantilla nunca se desplegó.** Compila, pero la primera corrida real
  puede encontrar un SKU sin cupo en la región, una política del tenant o una
  versión de API no disponible.
- **Conexión a la base sin verificar el certificado.** `DATABASE_URL` no lleva
  parámetro de SSL porque la usan dos librerías con sintaxis incompatible
  (asyncpg para la aplicación y psycopg2 para las migraciones,
  `backend/migrations/env.py:36`). Las dos negocian cifrado solas y Azure
  rechaza conexiones sin cifrar (a confirmar), pero no validan el certificado
  del servidor. Hoy contra Supabase es igual. Arreglarlo de fondo es un cambio
  chico en `backend/app/core/database.py` y `backend/migrations/env.py`.
- **Pedidos de más de 240 segundos se cortan.** Es el límite de Container Apps
  (verificado en la documentación:
  `learn.microsoft.com/azure/container-apps/ingress-overview`). Las cenefas no
  tienen problema: se generan en segundo plano y el navegador pregunta cada
  tanto. Lo que hay que probar son las respuestas largas en vivo: una búsqueda
  de precios en todas las cadenas y un análisis con IA extenso.
- **Un deploy en medio de un render de cenefas lo corta.** Al arrancar, la
  versión nueva marca como error los trabajos que estaban corriendo y les vacía
  el Excel y el PPTX (`backend/app/services/cenefas/jobs.py:634-644`). Ya pasa
  hoy en Render; en Azure, como la versión vieja sigue viva unos segundos
  mientras arranca la nueva (a confirmar), puede pasarle a un render que
  todavía estaba avanzando. Recomendación: no hacer push a `main` mientras
  alguien genera un lote grande.
- **La IP del usuario en la auditoría y en el límite de pedidos se puede
  falsear.** El código toma el **primer** valor del encabezado
  `X-Forwarded-For` (`backend/app/core/rate_limit.py:21-25`,
  `backend/app/core/deps.py:19-21`), y Container Apps solo garantiza el
  **último** (verificado en la documentación de ingress). El propio código ya
  lo reconoce (`backend/app/api/routes/auth.py:79`), y el bloqueo de cuentas
  por intentos fallidos no depende de la IP. No es nuevo, pero conviene
  corregirlo aprovechando la migración.
- **Memoria.** En Render (512 MB) el backend ya se cayó por falta de memoria
  generando cenefas (`backend/app/services/cenefas/jobs.py:41-43`). El Bicep le
  da 2 GB y 1 núcleo. Hay que mirarlo las primeras semanas.
- **Buscador de precios desde otra IP** (lista de verificación, paso 5).
- **Soporte de Next.js 16 en contenedor.** Se construye en CI en cada push,
  pero **nunca atendió usuarios reales**: producción siempre fue Vercel. El
  ensayo del paso 4 es justamente para eso.

## 8. De qué depende el costo mensual

**No se incluyen precios a propósito**: cambian por región, moneda y acuerdo de
la empresa con Microsoft. Hay que cargarlos en la calculadora de Azure
(`azure.microsoft.com/pricing/calculator`) con la región que elija IT. De mayor
a menor peso esperado:

1. **Backend en Container Apps.** Está prendido las 24 horas con 1 núcleo y
   2 GB, y se cobra por núcleo-segundo y GB-segundo. Es fijo, no depende del
   uso.
2. **PostgreSQL Flexible Server.** El cómputo (B1ms, o B2s si se sube) prendido
   las 24 horas, más el disco (32 GB) y los respaldos.
3. **Frontend en Container Apps.** Una réplica chica (0,5 núcleo, 1 GB) siempre
   prendida; la segunda solo con mucho tráfico.
4. **Log Analytics.** Se cobra por GB de logs. El backend escribe bastante;
   conviene mirar el volumen el primer mes y ajustar la retención (30 días en el
   Bicep).
5. **Container Registry Basic.** Cargo fijo chico. Se acumula una imagen por
   push: conviene una regla de limpieza de imágenes viejas.
6. **Tráfico de salida.** Menor para una herramienta interna.

Lo que lo haría subir: VNet con private endpoints, base más grande o con alta
disponibilidad, Redis, Key Vault, o un segundo ambiente de pruebas.

Las cuentas de terceros (Anthropic, OpenAI, Groq, SendGrid, las APIs
publicitarias) no cambian: se siguen pagando igual.

## 9. Archivos de esta preparación

| Archivo | Qué es |
| --- | --- |
| `infra/azure/main.bicep` | Toda la infraestructura, en dos fases |
| `infra/azure/main.bicepparam` | Ejemplo de parámetros (sin secretos) |
| `.github/workflows/deploy-azure.yml` | El deploy automático, apagado hasta `AZURE_DEPLOY_ENABLED=true` |
| `backend/app/core/config.py`, `backend/app/main.py` | Señal de "servidor desplegado" y commit de `/health` también en Azure |
| `backend/tests/test_senal_azure.py` | Tests de lo anterior |
| `docs/AZURE.md` | Este documento |

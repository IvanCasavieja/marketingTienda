// EJEMPLO de parámetros. Copiar a un archivo que NO se suba al repositorio
// (por ejemplo main.local.bicepparam) si se van a escribir valores reales, o
// —mejor— dejar los secretos afuera y pasarlos por variables de entorno, como
// se hace acá con readEnvironmentVariable().
//
// Uso (Fase 1, sin las apps):
//   az deployment group create -g <resource-group> \
//     -f infra/azure/main.bicep -p infra/azure/main.bicepparam
//
// Uso (Fase 2, con las apps): igual, con desplegarApps = true e imagenTag = el
// SHA que subió el workflow. Ver docs/AZURE.md.

using './main.bicep'

param location = 'brazilsouth' // sugerencia, la define IT
param prefijo = 'mktg'

// ── Fase ─────────────────────────────────────────────────────────────────────
param desplegarApps = false
param imagenTag = '' // Fase 2: el SHA completo del commit, ej. '3f2a…'

// ── Postgres ─────────────────────────────────────────────────────────────────
param postgresVersion = '16' // igual o mayor que la de Supabase
param postgresSkuName = 'Standard_B1ms'
param postgresSkuTier = 'Burstable'
// Solo letras y números, 32+ caracteres. Ver la descripción en main.bicep.
param postgresAdminPassword = readEnvironmentVariable('MKTG_PG_PASSWORD')
param ipMigracion = '' // la IP pública de quien corre pg_restore; vaciar después

// ── Backend: secretos (los mismos valores que hoy están en Render) ───────────
param appSecretKey = readEnvironmentVariable('MKTG_APP_SECRET_KEY')
param encryptionKey = readEnvironmentVariable('MKTG_ENCRYPTION_KEY')
param secretosBackend = {
  JWT_SECRET_KEY: readEnvironmentVariable('MKTG_JWT_SECRET_KEY', '')
  ANTHROPIC_API_KEY: readEnvironmentVariable('MKTG_ANTHROPIC_API_KEY', '')
  OPENAI_API_KEY: readEnvironmentVariable('MKTG_OPENAI_API_KEY', '')
  GROQ_API_KEY: readEnvironmentVariable('MKTG_GROQ_API_KEY', '')
  META_APP_SECRET: readEnvironmentVariable('MKTG_META_APP_SECRET', '')
  GOOGLE_CLIENT_SECRET: readEnvironmentVariable('MKTG_GOOGLE_CLIENT_SECRET', '')
  GOOGLE_DEVELOPER_TOKEN: readEnvironmentVariable('MKTG_GOOGLE_DEVELOPER_TOKEN', '')
  TIKTOK_APP_SECRET: readEnvironmentVariable('MKTG_TIKTOK_APP_SECRET', '')
  DV360_CLIENT_SECRET: readEnvironmentVariable('MKTG_DV360_CLIENT_SECRET', '')
  SFMC_CLIENT_SECRET: readEnvironmentVariable('MKTG_SFMC_CLIENT_SECRET', '')
  SENDGRID_API_KEY: readEnvironmentVariable('MKTG_SENDGRID_API_KEY', '')
  SMTP_PASSWORD: readEnvironmentVariable('MKTG_SMTP_PASSWORD', '')
}

// true = producción. false = ensayo (sin migraciones ni loops periódicos).
param mantenimientoAlArrancar = true

// ── Backend: configuración no secreta ────────────────────────────────────────
// Copiar de Render solo las que hoy estén definidas ahí. Las *_REDIRECT_URI de
// backend/.env.example no hacen falta: el código no las lee en ningún lado.
param envBackend = {
  // META_APP_ID: ''
  // GOOGLE_CLIENT_ID: ''
  // TIKTOK_APP_ID: ''
  // DV360_CLIENT_ID: ''
  // SFMC_CLIENT_ID: ''
  // SFMC_SUBDOMAIN: ''
  // SFMC_ACCOUNT_ID: ''
  // EMAIL_FROM: 'Core Tienda <DoNotReply@dominio-verificado>'
  // Mails por Azure Communication Services (ver docs/AZURE.md, "Mails"):
  // EMAIL_PROVIDER: 'smtp'
  // SMTP_HOST: 'smtp.azurecomm.net'
  // SMTP_PORT: '587'
  // SMTP_USER: ''
}

// Vacío = la URL por defecto de la app del frontend. Con dominio propio:
// 'https://marketing.ejemplo.com.uy' (sin barra final).
param frontendUrl = ''
// Durante la transición, sumar el dominio de Vercel:
// 'https://<frontend-azure>,https://marketing-tienda.vercel.app'
param origenesPermitidos = ''

// ── GitHub Actions ───────────────────────────────────────────────────────────
// Object ID de la Enterprise Application del app registration de GitHub.
// Vacío = IT asigna AcrPush y Contributor a mano.
param githubPrincipalId = ''

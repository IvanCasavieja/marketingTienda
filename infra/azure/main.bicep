// ─────────────────────────────────────────────────────────────────────────────
// MKTG Platform en Azure — infraestructura completa, a nivel de resource group.
//
// Qué crea:
//   - Log Analytics (logs de los contenedores)
//   - Azure Container Registry, Basic (las imágenes Docker)
//   - Identidad administrada (user-assigned) con AcrPull sobre el registro
//   - Entorno de Container Apps (plan Consumo)
//   - Azure Database for PostgreSQL Flexible Server + una base
//   - Container App del backend  (FastAPI, puerto 8000, SIEMPRE 1 réplica)
//   - Container App del frontend (Next.js, puerto 3000, 1 a 2 réplicas)
//
// Se despliega en DOS FASES con el mismo archivo (ver docs/AZURE.md):
//   Fase 1  desplegarApps=false  → todo menos las dos Container Apps. Con esto
//           ya existen el registro (para subir las imágenes) y la base (para
//           restaurar los datos de Supabase ANTES de que arranque el backend).
//   Fase 2  desplegarApps=true + imagenTag=<sha> → crea las dos apps apuntando
//           a imágenes que ya están en el registro.
// Las dos fases existen porque una Container App no se puede crear sin una
// imagen que exista, y porque el backend migra/crea tablas apenas arranca: si
// arrancara contra la base vacía, el pg_restore posterior chocaría con ellas.
//
// ESTADO (12/11/2026): compila sin errores ni advertencias con Bicep 0.49.2
// (`bicep build` y `bicep build-params`, corridos en un contenedor). Eso valida
// la sintaxis y los tipos, NADA MÁS: nunca se desplegó ni se corrió what-if
// contra una suscripción real, así que nombres de SKU, versiones de API
// disponibles en la región, cupos y políticas del tenant están sin probar.
// Antes de crear nada:
//   az deployment group what-if -g <rg> -f infra/azure/main.bicep -p infra/azure/main.bicepparam
// ─────────────────────────────────────────────────────────────────────────────

targetScope = 'resourceGroup'

// ── Generales ────────────────────────────────────────────────────────────────

@description('Región de todos los recursos. Brazil South es una SUGERENCIA por cercanía a Uruguay; la decide IT.')
param location string = resourceGroup().location

@description('Región del servidor Postgres. Normalmente la misma; existe por si la suscripción no tiene cupo de Flexible Server en la región principal.')
param postgresLocation string = location

@description('Prefijo corto para los nombres (minúsculas, sin guiones al final).')
@minLength(3)
@maxLength(12)
param prefijo string = 'mktg'

@description('Sufijo para los nombres que tienen que ser únicos en todo Azure (registro y servidor Postgres).')
param sufijoUnico string = substring(uniqueString(resourceGroup().id), 0, 6)

param tags object = {
  proyecto: 'mktg-platform'
}

// ── Fases ────────────────────────────────────────────────────────────────────

@description('false = Fase 1 (sin Container Apps). true = Fase 2 (con las apps).')
param desplegarApps bool = false

@description('Tag de las imágenes en el registro (el SHA del commit que subió el workflow). Obligatorio en Fase 2. OJO: volver a correr este Bicep con un tag viejo VUELVE las apps a esa versión.')
param imagenTag string = ''

@description('Nombre del repositorio de la imagen del backend dentro del registro.')
param repoBackend string = 'mktg-backend'

@description('Nombre del repositorio de la imagen del frontend dentro del registro.')
param repoFrontend string = 'mktg-frontend'

// ── Postgres ─────────────────────────────────────────────────────────────────

@description('Usuario administrador de Postgres. Solo letras, números y guion bajo.')
param postgresAdminUser string = 'mktgadmin'

@description('Contraseña del administrador de Postgres. SOLO LETRAS Y NÚMEROS (32+ caracteres): va adentro de DATABASE_URL sin escapar, y Alembic (configparser) se rompe con el signo % que aparecería al escaparla.')
@secure()
@minLength(16)
param postgresAdminPassword string

@description('Nombre de la base de datos.')
param postgresDatabase string = 'mktg_platform'

@description('Versión mayor de Postgres. Tiene que ser IGUAL O MAYOR a la de Supabase (SELECT version()), o el pg_restore puede fallar.')
@allowed(['15', '16', '17'])
param postgresVersion string = '16'

@description('SKU de Postgres. B1ms es lo más chico, pero admite solo 35 conexiones de usuario y el backend puede abrir hasta 35 (pool 15 + overflow 20, backend/app/core/database.py). Ver docs/AZURE.md, riesgos.')
param postgresSkuName string = 'Standard_B1ms'

@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param postgresSkuTier string = 'Burstable'

@description('Disco de Postgres en GB (32 es el mínimo).')
param postgresStorageGb int = 32

@description('IP pública desde la que se va a correr pg_restore (la PC o el servidor de quien migra). Vacío = no se abre. Sacarla después de migrar.')
param ipMigracion string = ''

// ── Backend ──────────────────────────────────────────────────────────────────

@description('APP_SECRET_KEY. Usar LA MISMA que hoy tiene Render (es la clave del endpoint de sync del scraper).')
@secure()
param appSecretKey string

@description('ENCRYPTION_KEY (Fernet). TIENE que ser LA MISMA que hoy tiene Render: con otra, los tokens de plataformas guardados en la base no se pueden descifrar.')
@secure()
param encryptionKey string

@description('Resto de los secretos del backend, como objeto NOMBRE_DE_ENV_VAR: valor. Los vacíos se ignoran. Ej.: JWT_SECRET_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, META_APP_SECRET, GOOGLE_CLIENT_SECRET, GOOGLE_DEVELOPER_TOKEN, TIKTOK_APP_SECRET, DV360_CLIENT_SECRET, SFMC_CLIENT_SECRET, SENDGRID_API_KEY, REDIS_URL.')
@secure()
param secretosBackend object = {}

@description('Variables de entorno NO secretas del backend, como objeto NOMBRE: valor. Ej.: META_APP_ID, META_REDIRECT_URI, GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI, EMAIL_FROM, SFMC_SUBDOMAIN, MODELO_IA. La lista completa está en backend/.env.example.')
param envBackend object = {}

@description('URL pública del frontend, sin barra final (FRONTEND_URL: va en los mails de recuperación de contraseña y se agrega sola a CORS). Vacío = la URL por defecto de la Container App del frontend.')
param frontendUrl string = ''

@description('Orígenes extra permitidos por CORS, separados por coma (APP_ALLOWED_ORIGINS). Durante la transición conviene dejar también el dominio de Vercel.')
param origenesPermitidos string = ''

@description('MANTENIMIENTO_AL_ARRANCAR. true = producción: este backend corre migraciones, purga y los loops periódicos (sync con las plataformas, avisos, etc.). false = ENSAYO: sirve la app pero no corre nada de eso, para probar con una copia de los datos sin duplicar avisos ni sincronizaciones mientras Render sigue siendo producción.')
param mantenimientoAlArrancar bool = true

@description('CPU del backend (núcleos). Texto porque Bicep no tiene decimales.')
param backendCpu string = '1.0'

@description('Memoria del backend. En Render (512 MB) el render de cenefas ya murió por falta de memoria (backend/app/services/cenefas/jobs.py:42).')
param backendMemoria string = '2Gi'

// ── Frontend ─────────────────────────────────────────────────────────────────

param frontendCpu string = '0.5'
param frontendMemoria string = '1Gi'

@minValue(1)
param frontendMaxReplicas int = 2

// ── GitHub Actions (opcional) ────────────────────────────────────────────────

@description('Object ID del service principal (Enterprise Application) que usa GitHub Actions. Si se completa, este Bicep le da AcrPush sobre el registro y Contributor sobre el resource group. Vacío = IT asigna esos roles a mano.')
param githubPrincipalId string = ''

// ── Nombres ──────────────────────────────────────────────────────────────────

var nombreLogs = '${prefijo}-logs'
var nombreEntorno = '${prefijo}-env'
var nombreRegistro = toLower('${prefijo}acr${sufijoUnico}') // solo letras y números
var nombreIdentidad = '${prefijo}-apps-id'
var nombrePostgres = toLower('${prefijo}-pg-${sufijoUnico}')
var nombreBackend = '${prefijo}-backend'
var nombreFrontend = '${prefijo}-frontend'

// Roles integrados de Azure (IDs fijos, iguales en todos los tenants).
var rolAcrPull = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var rolAcrPush = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8311e382-0749-4cb8-b61a-304f252e45ec')
var rolContributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')

// ── Log Analytics ────────────────────────────────────────────────────────────

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: nombreLogs
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ── Registro de imágenes ─────────────────────────────────────────────────────

resource registro 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: nombreRegistro
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    // Sin usuario admin: las apps bajan imágenes con la identidad administrada
    // y GitHub las sube con su identidad federada. No hay contraseña que rotar.
    adminUserEnabled: false
  }
}

// ── Identidad con la que las apps bajan imágenes ─────────────────────────────

resource identidad 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: nombreIdentidad
  location: location
  tags: tags
}

resource permisoAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registro.id, identidad.id, 'AcrPull')
  scope: registro
  properties: {
    roleDefinitionId: rolAcrPull
    principalId: identidad.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource permisoGithubAcrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(githubPrincipalId)) {
  name: guid(registro.id, githubPrincipalId, 'AcrPush')
  scope: registro
  properties: {
    roleDefinitionId: rolAcrPush
    principalId: githubPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Contributor sobre el resource group: lo que necesita `az containerapp update`
// (escribir la app y "asignarle" la identidad administrada que ya tiene). Se
// puede achicar a un rol a medida más adelante.
resource permisoGithubContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(githubPrincipalId)) {
  name: guid(resourceGroup().id, githubPrincipalId, 'Contributor')
  properties: {
    roleDefinitionId: rolContributor
    principalId: githubPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ── Entorno de Container Apps ────────────────────────────────────────────────

resource entorno 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: nombreEntorno
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

// ── Postgres ─────────────────────────────────────────────────────────────────

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: nombrePostgres
  location: postgresLocation
  tags: tags
  sku: {
    name: postgresSkuName
    tier: postgresSkuTier
  }
  properties: {
    version: postgresVersion
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    authConfig: {
      passwordAuth: 'Enabled'
      activeDirectoryAuth: 'Disabled'
    }
    storage: {
      storageSizeGB: postgresStorageGb
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

resource baseDeDatos 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: postgresDatabase
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// "Permitir servicios de Azure": la regla especial 0.0.0.0–0.0.0.0. Deja entrar
// a CUALQUIER recurso de Azure (también de otros clientes), no solo a nuestras
// apps; lo único que protege la base es la contraseña + TLS. Es el punto de
// partida simple. Para endurecerlo: poner el entorno de Container Apps en una
// VNet y la base detrás de un private endpoint (o con integración de VNet), y
// borrar esta regla. Ese cambio obliga a recrear el entorno, así que conviene
// decidirlo ANTES del corte (ver docs/AZURE.md, decisiones abiertas).
resource reglaServiciosAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Temporal, solo para restaurar los datos desde afuera de Azure.
resource reglaMigracion 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = if (!empty(ipMigracion)) {
  parent: postgres
  name: 'migracion-temporal'
  properties: {
    startIpAddress: ipMigracion
    endIpAddress: ipMigracion
  }
  dependsOn: [
    reglaServiciosAzure // las reglas de firewall de un mismo servidor no se crean en paralelo
  ]
}

// ── Valores derivados ────────────────────────────────────────────────────────

var dominioEntorno = entorno.properties.defaultDomain
var urlBackend = 'https://${nombreBackend}.${dominioEntorno}'
var urlFrontendPorDefecto = 'https://${nombreFrontend}.${dominioEntorno}'
var urlFrontend = empty(frontendUrl) ? urlFrontendPorDefecto : frontendUrl

// SIN parámetro de SSL en la URL, a propósito. El backend usa la misma
// DATABASE_URL con dos drivers: asyncpg (la app) y psycopg2 (Alembic,
// backend/migrations/env.py:36, que solo cambia el prefijo). `?ssl=require` lo
// entiende asyncpg y rompe psycopg2; `?sslmode=require` es al revés. Sin
// parámetro los dos negocian TLS solos ("prefer"), y Azure rechaza las
// conexiones sin TLS (require_secure_transport=on por defecto), así que la
// conexión va cifrada igual. Lo que NO hace es verificar el certificado.
var databaseUrl = 'postgresql+asyncpg://${postgresAdminUser}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${postgresDatabase}'

// Los nombres de secreto de Container Apps van en minúsculas y con guiones:
// ANTHROPIC_API_KEY → anthropic-api-key.
var secretosOpcionales = filter(items(secretosBackend), s => !empty(s.value))
var secretosOpcionalesApp = [
  for s in secretosOpcionales: {
    name: toLower(replace(s.key, '_', '-'))
    value: string(s.value)
  }
]
var envSecretosOpcionales = [
  for s in secretosOpcionales: {
    name: s.key
    secretRef: toLower(replace(s.key, '_', '-'))
  }
]
var envPlanoBackend = [
  for e in items(envBackend): {
    name: e.key
    value: string(e.value)
  }
]

// ── Backend ──────────────────────────────────────────────────────────────────

resource backend 'Microsoft.App/containerApps@2024-03-01' = if (desplegarApps) {
  name: nombreBackend
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identidad.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: entorno.id
    configuration: {
      // Una sola revisión activa: cada deploy reemplaza a la anterior.
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        // CORS lo resuelve la app (backend/app/main.py:276), no el ingress.
      }
      registries: [
        {
          server: registro.properties.loginServer
          identity: identidad.id
        }
      ]
      secrets: concat(
        [
          {
            name: 'database-url'
            value: databaseUrl
          }
          {
            name: 'app-secret-key'
            value: appSecretKey
          }
          {
            name: 'encryption-key'
            value: encryptionKey
          }
        ],
        secretosOpcionalesApp
      )
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: '${registro.properties.loginServer}/${repoBackend}:${imagenTag}'
          resources: {
            cpu: json(backendCpu)
            memory: backendMemoria
          }
          env: concat(
            [
              {
                name: 'APP_ENV'
                value: 'production'
              }
              // Explícito, además de la detección por CONTAINER_APP_NAME
              // (backend/app/core/config.py, es_servidor_desplegado): este es
              // EL servidor, corre migraciones, purga y los loops periódicos.
              // En false (ensayo) el valor explícito le gana a la detección.
              {
                name: 'MANTENIMIENTO_AL_ARRANCAR'
                value: mantenimientoAlArrancar ? 'true' : 'false'
              }
              // Lo que muestra /health. El workflow lo pisa en cada deploy.
              {
                name: 'GIT_COMMIT'
                value: imagenTag
              }
              {
                name: 'FRONTEND_URL'
                value: urlFrontend
              }
              {
                name: 'APP_ALLOWED_ORIGINS'
                value: empty(origenesPermitidos) ? urlFrontend : origenesPermitidos
              }
              {
                name: 'DATABASE_URL'
                secretRef: 'database-url'
              }
              {
                name: 'APP_SECRET_KEY'
                secretRef: 'app-secret-key'
              }
              {
                name: 'ENCRYPTION_KEY'
                secretRef: 'encryption-key'
              }
            ],
            envSecretosOpcionales,
            envPlanoBackend
          )
          probes: [
            // Arranque: hasta ~2 minutos para que uvicorn conteste /health.
            // Las migraciones corren en segundo plano y no lo demoran.
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 3
              periodSeconds: 5
              timeoutSeconds: 5
              failureThreshold: 24
            }
            // Listo para recibir tráfico: /health, que además prueba la base
            // (devuelve 503 si no llega, backend/app/main.py:307).
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 6
            }
            // Vivo: por TCP y NO por /health, a propósito. /health da 503 si
            // la BASE no contesta; si eso reiniciara el contenedor, un corte
            // corto de Postgres mataría el render de cenefas en curso, y al
            // rearrancar recuperar_jobs_huerfanos le vacía el Excel y el PPTX
            // a esa corrida (backend/app/services/cenefas/jobs.py:634). Reiniciar el
            // backend no arregla una base caída.
            {
              type: 'Liveness'
              tcpSocket: {
                port: 8000
              }
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      // EXACTAMENTE una réplica, siempre. El backend corre adentro del proceso
      // los loops periódicos (sync de métricas, watchlists, alertas, cotización,
      // curaduría, purga, avisos del calendario — backend/app/main.py:98-151) y
      // un semáforo en memoria que serializa los renders de cenefas
      // (backend/app/services/cenefas/jobs.py:49). Con 0 réplicas los loops no
      // corren; con 2 se duplican (los candados de Redis que los protegerían
      // son opcionales y hoy no hay Redis).
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    permisoAcrPull // sin el permiso, la primera bajada de imagen falla
    baseDeDatos
    reglaServiciosAzure
  ]
}

// ── Frontend ─────────────────────────────────────────────────────────────────

resource frontend 'Microsoft.App/containerApps@2024-03-01' = if (desplegarApps) {
  name: nombreFrontend
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identidad.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: entorno.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registro.properties.loginServer
          identity: identidad.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          // NEXT_PUBLIC_API_URL NO se configura acá: queda incrustada en la
          // imagen al construirla (frontend/Dockerfile:37). Cambiar la URL del
          // backend exige reconstruir la imagen.
          image: '${registro.properties.loginServer}/${repoFrontend}:${imagenTag}'
          resources: {
            cpu: json(frontendCpu)
            memory: frontendMemoria
          }
          env: [
            {
              name: 'GIT_COMMIT'
              value: imagenTag
            }
          ]
          probes: [
            {
              type: 'Startup'
              tcpSocket: {
                port: 3000
              }
              periodSeconds: 3
              failureThreshold: 30
            }
            {
              type: 'Liveness'
              tcpSocket: {
                port: 3000
              }
              periodSeconds: 30
              failureThreshold: 3
            }
          ]
        }
      ]
      // El frontend no guarda estado: puede tener más de una réplica. Mínimo 1
      // para que la primera visita del día no espere un arranque en frío.
      scale: {
        minReplicas: 1
        maxReplicas: frontendMaxReplicas
        rules: [
          {
            name: 'http'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    permisoAcrPull
  ]
}

// ── Salidas (lo que hay que copiar a las variables de GitHub) ─────────────────

@description('→ variable de GitHub AZURE_ACR_NAME')
output acrName string = registro.name

output acrLoginServer string = registro.properties.loginServer

@description('→ variable de GitHub AZURE_BACKEND_APP')
output backendAppName string = nombreBackend

@description('→ variable de GitHub AZURE_FRONTEND_APP')
output frontendAppName string = nombreFrontend

@description('→ variable de GitHub AZURE_API_URL (se conoce ya desde la Fase 1)')
output apiUrl string = '${urlBackend}/api/v1'

output backendUrl string = urlBackend
output frontendUrl string = urlFrontendPorDefecto
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output postgresDatabase string = postgresDatabase

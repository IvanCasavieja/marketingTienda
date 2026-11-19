import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    # Producción por defecto: si un despliegue nuevo olvida setear esta env var,
    # que falle "cerrado" (docs/openapi deshabilitados) en vez de exponerlos.
    APP_ENV: str = "production"
    APP_SECRET_KEY: str  # Required — used for the scraper sync endpoint (X-Sync-Key header)
    JWT_SECRET_KEY: str = ""  # JWT signing key — defaults to APP_SECRET_KEY if not set
    APP_ALLOWED_ORIGINS: str = "http://localhost:3000"
    FRONTEND_URL: str = "https://marketing-tienda.vercel.app"
    API_V1_PREFIX: str = "/api/v1"

    # Auto-sync de métricas (0 = desactivado)
    SYNC_INTERVAL_HOURS: int = 6

    # Chequeo diario de listas de monitoreo de precios (0 = desactivado)
    WATCHLIST_CHECK_INTERVAL_HOURS: int = 24

    # Chequeo de anomalías de campañas de Medios — dashboard/canales/campaigns (0 = desactivado)
    CAMPAIGN_ALERTS_CHECK_INTERVAL_HOURS: int = 24

    # Actualización diaria (8am hora Montevideo) de la cotización del dólar BROU
    COTIZACION_AUTO_UPDATE: bool = True

    # Curaduría diaria del conocimiento de cenefas: funde duplicados y
    # propone resumir o archivar. Nunca cambia lo que ya se decidió.
    CENEFAS_CURADURIA: bool = True

    # Retención de archivos de cenefas (0 = desactivada). El PPTX de una
    # corrida SIN verificar se borra a los N días; el número de la corrida
    # queda para siempre, y el archivo de una corrida VERIFICADA también.
    CENEFAS_RETENCION_DIAS: int = 7

    # Fotos de colocación (las que suben los locales, ver
    # services/colocacion.py). Se borran a los N días de que termina la acción
    # (0 = no se borran nunca). Y un tope de lo que pueden ocupar entre todas:
    # pasado ese, el local no puede subir más y se le dice que avise. La base
    # gratis es de 500 MB para TODA la plataforma; ahí está la cuenta.
    COLOCACION_RETENCION_DIAS: int = 30
    COLOCACION_TOPE_MB: int = 80
    # El freno de espacio (app/services/espacio.py): si la base pasa de esto,
    # no se guarda ninguna imagen nueva (las de las entregas, las fotos de
    # colocación) y se avisa. Supabase gratis tiene 500 MB para TODA la
    # plataforma y no se va a pagar más: el margen es para que lo demás (el
    # calendario, las cenefas, los logins) nunca se quede sin lugar.
    # 0 = sin freno.
    BASE_TOPE_MB: int = 400
    # El ZIP original de cada ronda (0081, 19/11/2026) se guarda solo si
    # después siguen libres ZIP_RESERVA_MB debajo de BASE_TOPE_MB. Un ZIP pesa
    # mucho más que las imágenes (hasta 40 MB contra 50-250 KB): sin esta
    # reserva, unos pocos ZIP llenarían la base y las imágenes —las que hacen
    # falta para ver y marcar la pieza— dejarían de guardarse. Si el ZIP no
    # entra, la entrega se hace igual sin él y la ficha lo dice; no se borra
    # nada para hacerle lugar. 50 MB son unos meses de imágenes. 0 = sin reserva.
    ZIP_RESERVA_MB: int = 50

    # Cuánto del calendario ve cada persona ya no es un número de días fijo
    # para las cuentas externas: desde la 0070 cada usuario tiene su alcance
    # (No lo ve / 1 mes / 2 meses / 12 meses / Todo), que elige un admin en el
    # panel. Ver app/core/alcance.py.

    # El tablero de tarjetas (16/11/2026): una tarjeta finalizada pasa sola a
    # "Archivado" a los tantos días si nadie la archivó antes. Pedido de Ivan:
    # "una vez finalizadas, 10 días después pasan solas a Archivado". Se
    # calcula al leer el tablero y además lo deja guardado el loop diario
    # (app/services/entregas.py: archivar_finalizadas).
    ARCHIVAR_TARJETAS_DIAS: int = 10
    # Y a los tantos días en Archivado, se archiva "de verdad": no se muestra
    # ni se carga en el tablero (queda en la base y la encuentra el buscador).
    # Lo que más molesta del Trello de hoy es que anda lentísimo porque carga
    # miles de tarjetas viejas.
    OCULTAR_ARCHIVADAS_DIAS: int = 30

    # El modelo de Anthropic que usan TODOS los agentes: Don Tino, Tinín,
    # Doña Tina, Dogti, la extracción de facturas y la pata de Claude en la
    # Tríada. Estaba hardcodeado y repetido en seis archivos, cada uno con un
    # comentario que decía "mismo modelo que los otros" — que es justo la forma
    # en que seis copias se separan sin que nadie se entere.
    #
    # Al 2026-08-29: claude-sonnet-5 reemplaza a claude-sonnet-4-6 — más nuevo
    # y más barato (US$2/US$10 por millón contra US$3/US$15).
    #
    # OJO al cambiarlo: la familia 5 NO acepta `temperature` ni `top_p`;
    # mandarlos devuelve 400. Si hay que volver atrás en caliente, se puede
    # setear por env var en Render sin desplegar código.
    MODELO_IA: str = "claude-sonnet-5"

    # La IA que revisa las piezas de las entregas antes que el aprobador
    # (app/services/revision_ia.py): ortografía, logo de otro mundo, falta del
    # legal, precio o vigencia distintos al pedido, QR ilegible.
    #
    # IA_REVISION_ACTIVA=false la apaga sin tocar código: no se llama a la IA
    # y la pantalla no muestra nada (ni lo que ya se había revisado).
    IA_REVISION_ACTIVA: bool = True
    # Un modelo propio y no MODELO_IA: acá todo depende de LEER la imagen
    # (letra chica de legales, una tilde, un precio), y la guía de Anthropic
    # recomienda Opus 5.5 para visión: lee imágenes con más precisión que
    # Sonnet 5 en cualquier nivel de esfuerzo. Cuesta el doble por token
    # (US$4/US$20 por millón contra US$2/US$10), unos centavos por versión:
    # ver el docstring del servicio. Si hay que bajar el costo, se cambia por
    # env var sin desplegar (claude-sonnet-5 acepta el mismo pedido).
    MODELO_IA_REVISION: str = "claude-opus-5-5"
    # Cuántas versiones se le mandan a la IA por día (hora de Uruguay), entre
    # todos. Pasado el tope, las nuevas no se revisan (y no se muestra nada):
    # es el freno si algo se dispara. Con el uso esperado (unas 4 versiones
    # por día hábil) no se llega nunca.
    IA_REVISION_POR_DIA: int = 200

    # Demo mode — cuando True, sync_metrics retorna inmediatamente sin llamar APIs externas
    DEMO_MODE: bool = False

    # ¿Este proceso corre las tareas de mantenimiento al arrancar (migraciones,
    # recuperación de jobs huérfanos, purga de archivos) y los loops periódicos?
    #
    # None = automático: SOLO si es el servidor desplegado (ver es_servidor_desplegado).
    # True/False = forzar, para el caso raro que lo necesite. En Azure se
    # declara en true a propósito (infra/azure/main.bicep), además de la
    # detección automática.
    #
    # El problema que resuelve: backend/.env de una PC de trabajo apunta a la
    # MISMA base de producción (ONBOARDING/PENDIENTES lo indican así), y varias
    # de esas tareas son destructivas — recuperar_jobs_huerfanos marca error y
    # VACÍA staged_data/staged_source_pptx/staged_excel_bytes de todo job
    # pending/running anterior al arranque, así que levantar el backend en una
    # laptop mataba la corrida que alguien tuviera en curso, sin deshacer. La
    # purga borra archivos apenas arranca, y alembic aplicaría a producción una
    # migración que todavía no está desplegada. Nada de eso es del servidor,
    # así que no lo hace nadie que no sea el servidor.
    MANTENIMIENTO_AL_ARRANCAR: bool | None = None

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Encryption
    ENCRYPTION_KEY: str

    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Claude
    ANTHROPIC_API_KEY: str = ""

    # OpenAI (debate feature)
    OPENAI_API_KEY: str = ""

    # Groq / Llama (debate feature)
    GROQ_API_KEY: str = ""

    # Meta Ads
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_REDIRECT_URI: str = ""

    # Google Ads
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    GOOGLE_DEVELOPER_TOKEN: str = ""

    # TikTok Ads
    TIKTOK_APP_ID: str = ""
    TIKTOK_APP_SECRET: str = ""
    TIKTOK_REDIRECT_URI: str = ""

    # DV360
    DV360_CLIENT_ID: str = ""
    DV360_CLIENT_SECRET: str = ""
    DV360_REDIRECT_URI: str = ""

    # Salesforce Marketing Cloud
    SFMC_CLIENT_ID: str = ""
    SFMC_CLIENT_SECRET: str = ""
    SFMC_SUBDOMAIN: str = ""
    SFMC_ACCOUNT_ID: str = ""

    # Mails (hoy: recuperar la contraseña). Ver app/services/email_service.py
    # y docs/AZURE.md, "Mails". EMAIL_PROVIDER: "resend", "smtp", "sendgrid" o vacío
    # (Resend si hay clave; si no SMTP si hay SMTP_HOST; si no SendGrid).
    EMAIL_PROVIDER: str = ""
    # Cuántos proxies propios agregan su eslabón al final de X-Forwarded-For
    # (ver app/core/rate_limit.py::ip_de_la_cadena). 0 = el primero, como antes.
    PROXY_SALTOS_DE_CONFIANZA: int = 0
    # Resend (API web, la que usa Tuki): la recomendada en Render gratis, que
    # no deja salir SMTP. Remitente de un dominio verificado en Resend.
    RESEND_API_KEY: str = ""
    # SMTP: Zoho Mail (smtppro.zoho.com, 465 con "ssl"), Azure Communication
    # Services Email o Microsoft 365.
    # SMTP_SEGURIDAD: "starttls" (puerto 587), "ssl" (465) o "ninguna".
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SEGURIDAD: str = "starttls"
    # SendGrid — Single Sender Verification en sendgrid.com, sin necesitar
    # dominio propio (ver EMAIL_FROM)
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = "Core Tienda <onboarding@example.com>"

    @field_validator("ENCRYPTION_KEY", mode="after")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        try:
            from cryptography.fernet import Fernet
            Fernet(v.encode())
        except Exception:
            raise ValueError(
                "ENCRYPTION_KEY inválida. Generá una con: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        return v

    @property
    def es_servidor_desplegado(self) -> bool:
        """¿Somos el servidor desplegado, o una copia corriendo en una PC?

        Dos señales, una por plataforma, y las dos las pone la plataforma sola
        (no hay que configurar nada para que esto funcione):

        - RENDER_GIT_COMMIT la inyecta Render en cada deploy. Es la misma que
          /health usa para reportar el commit desplegado, verificada contra
          los dos entornos: producción devuelve el hash, local devuelve "dev".
        - CONTAINER_APP_NAME la inyecta Azure Container Apps en todo contenedor
          que corre ahí (ver docs/AZURE.md).

        En una PC no existe ninguna de las dos. GIT_COMMIT (ver
        commit_desplegado) NO cuenta como señal a propósito: es un nombre
        genérico que cualquier herramienta puede dejar definido en una máquina
        de trabajo, y esta propiedad es el freno que evita que esa máquina
        toque la base de producción.
        """
        return bool(
            os.environ.get("RENDER_GIT_COMMIT")
            or os.environ.get("CONTAINER_APP_NAME")
        )

    @property
    def corre_mantenimiento(self) -> bool:
        """Si este proceso puede tocar/borrar datos de producción al arrancar."""
        if self.MANTENIMIENTO_AL_ARRANCAR is not None:
            return self.MANTENIMIENTO_AL_ARRANCAR
        return self.es_servidor_desplegado

    @property
    def allowed_origins(self) -> List[str]:
        origins = [o.strip() for o in self.APP_ALLOWED_ORIGINS.split(",") if o.strip()]
        if self.FRONTEND_URL and self.FRONTEND_URL not in origins:
            origins.append(self.FRONTEND_URL)
        return origins


def commit_desplegado() -> str:
    """El commit que está corriendo, recortado a 7 caracteres ("dev" en una PC).

    Render lo expone solo en RENDER_GIT_COMMIT. Azure Container Apps no tiene
    un equivalente, así que ahí lo pasa el deploy en GIT_COMMIT
    (.github/workflows/deploy-azure.yml). Gana RENDER_GIT_COMMIT para que en
    Render nada cambie.
    """
    return (
        os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("GIT_COMMIT")
        or "dev"
    )[:7]


settings = Settings()

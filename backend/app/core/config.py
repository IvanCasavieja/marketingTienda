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

    # Demo mode — cuando True, sync_metrics retorna inmediatamente sin llamar APIs externas
    DEMO_MODE: bool = False

    # ¿Este proceso corre las tareas de mantenimiento al arrancar (migraciones,
    # recuperación de jobs huérfanos, purga de archivos) y los loops periódicos?
    #
    # None = automático: SOLO si es el servidor desplegado (ver es_servidor_desplegado).
    # True/False = forzar, para el caso raro que lo necesite.
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

    # SendGrid (password reset emails) — Single Sender Verification en
    # sendgrid.com, sin necesitar dominio propio (ver EMAIL_FROM)
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = "MKTG Platform <onboarding@example.com>"

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
        """¿Somos la instancia de Render, o una copia corriendo en una PC?

        RENDER_GIT_COMMIT la inyecta Render en cada deploy; en una PC no
        existe. Es la misma señal que /health ya usa para reportar el commit
        desplegado ("dev" cuando falta), verificada contra los dos entornos:
        producción devuelve el hash, local devuelve "dev". No hay que
        configurar nada en Render para que esto funcione.
        """
        return bool(os.environ.get("RENDER_GIT_COMMIT"))

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


settings = Settings()

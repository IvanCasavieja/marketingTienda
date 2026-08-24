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

    # Demo mode — cuando True, sync_metrics retorna inmediatamente sin llamar APIs externas
    DEMO_MODE: bool = False

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
    def allowed_origins(self) -> List[str]:
        origins = [o.strip() for o in self.APP_ALLOWED_ORIGINS.split(",") if o.strip()]
        if self.FRONTEND_URL and self.FRONTEND_URL not in origins:
            origins.append(self.FRONTEND_URL)
        return origins


settings = Settings()

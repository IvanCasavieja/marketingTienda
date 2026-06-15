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
    APP_ENV: str = "development"
    APP_SECRET_KEY: str  # Required — must be set in .env; no default prevents silent token invalidation on restart
    APP_ALLOWED_ORIGINS: str = "http://localhost:3000"
    FRONTEND_URL: str = "https://marketing-tienda.vercel.app"
    API_V1_PREFIX: str = "/api/v1"

    # Auto-sync de métricas (0 = desactivado)
    SYNC_INTERVAL_HOURS: int = 6

    # Demo mode — devuelve datos ficticios en todos los endpoints de métricas
    DEMO_MODE: bool = False

    # Meta desconectado temporalmente — sirve desde meta_campaigns.json en lugar de la API live.
    # Para reconectar: poner META_DISABLED=False en .env y reiniciar el backend.
    # El token / la conexión en DB no se toca — se puede volver a activar sin reconfigurar nada.
    META_DISABLED: bool = False

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

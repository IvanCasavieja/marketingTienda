from datetime import datetime
from sqlalchemy import DateTime, String, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# ---------------------------------------------------------------------------
# Catálogo de permisos disponibles en la plataforma
# ---------------------------------------------------------------------------
ALL_PERMISSIONS: dict[str, str] = {
    # Plataforma / Admin
    "platform.super":          "Control total: gestionar roles, editar cualquier usuario y recurso sin restricción",
    "platform.admin":          "Acceso al panel de administración",
    "platform.users.view":     "Ver la lista completa de usuarios registrados",
    "platform.users.manage":   "Crear, editar, activar/desactivar y cambiar el rol de usuarios",

    # Cenefas
    "cenefas.view":            "Ver templates de cenefas guardados",
    "cenefas.generate":        "Generar cenefas desde un archivo Excel y exportar a PPTX",
    "cenefas.edit":            "Crear y editar templates en el editor visual",
    "cenefas.import":          "Importar templates desde archivos PPTX",
    "cenefas.delete":          "Eliminar templates (propios y de otros usuarios)",

    # Analytics
    "analytics.view":          "Ver el dashboard de métricas y campañas",
    "analytics.export":        "Exportar datos de analytics a CSV/Excel",

    # Conexiones de plataformas
    "connections.view":        "Ver las conexiones de plataformas vinculadas (Meta, Google, etc.)",
    "connections.manage":      "Agregar, configurar y eliminar conexiones de plataformas",

    # Precios
    "precios.search":          "Buscar y comparar precios en vivo en supermercados",

    # IA
    "ai.use":                  "Usar el chat de IA, análisis automáticos y debate de campañas",
}

# Permisos por rol predeterminado (is_system=True, no se pueden eliminar)
DEFAULT_ROLES: list[dict] = [
    {
        "name":        "Superadmin",
        "description": "Acceso total a todas las funcionalidades y configuración de la plataforma",
        "permissions": list(ALL_PERMISSIONS.keys()),
        "is_system":   True,
    },
    {
        "name":        "Admin",
        "description": "Administrador con acceso al panel de gestión de usuarios, sin poder modificar otros admins",
        "permissions": [
            "platform.admin", "platform.users.view", "platform.users.manage",
            "cenefas.view", "cenefas.generate", "cenefas.edit", "cenefas.import", "cenefas.delete",
            "analytics.view", "analytics.export",
            "connections.view", "connections.manage",
            "precios.search",
            "ai.use",
        ],
        "is_system": True,
    },
    {
        "name":        "Editor",
        "description": "Puede crear y exportar cenefas; ve analytics e IA. Sin acceso a gestión de usuarios",
        "permissions": [
            "cenefas.view", "cenefas.generate", "cenefas.edit", "cenefas.import",
            "analytics.view",
            "precios.search",
            "ai.use",
        ],
        "is_system": True,
    },
    {
        "name":        "Viewer",
        "description": "Solo lectura: puede ver cenefas y analytics, pero no crear ni exportar",
        "permissions": [
            "cenefas.view",
            "analytics.view",
        ],
        "is_system": True,
    },
]


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="role")

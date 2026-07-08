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

# Sufijo que marca un permiso como "de solo lectura" — usado para restringir
# qué puede tildarse en un usuario con rol view_only (Viewer).
_VIEW_SUFFIX = ".view"


def is_view_permission(permission: str) -> bool:
    return permission.endswith(_VIEW_SUFFIX)


# Roles del sistema (is_system=True, no se pueden eliminar ni renombrar).
# Los permisos acá son solo el punto de partida al ASIGNAR el rol a un
# usuario — de ahí en más los permisos reales viven en User.permissions y se
# afinan uno por uno desde el perfil de cada usuario.
DEFAULT_ROLES: list[dict] = [
    {
        "name":        "Superadmin",
        "description": "Acceso total sin restricciones — reservado para la cuenta principal, no asignable desde el panel",
        "permissions": list(ALL_PERMISSIONS.keys()),
        "is_system":   True,
        "view_only":   False,
    },
    {
        "name":        "Admin",
        "description": "Arranca con todos los permisos; se pueden destildar puntualmente por usuario. No puede modificar a otros Admins",
        "permissions": list(ALL_PERMISSIONS.keys()),
        "is_system":   True,
        "view_only":   False,
    },
    {
        "name":        "Usuario",
        "description": "Arranca sin permisos — se le arman a medida desde su perfil",
        "permissions": [],
        "is_system":   True,
        "view_only":   False,
    },
    {
        "name":        "Viewer",
        "description": "Arranca sin permisos y solo puede tener tildados permisos de solo lectura (\"ver\")",
        "permissions": [],
        "is_system":   True,
        "view_only":   True,
    },
]


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    view_only: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="role")

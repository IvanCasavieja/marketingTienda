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
    "cenefas.view":            "Ver templates de cenefas guardados y usar el Convertidor de Excel",
    "cenefas.diccionario":     "Ver y corregir el Diccionario: el catálogo compartido de descripciones y los grupos unificados",
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

    # Redexpres
    "redexpres.view":          "Ver y completar la planilla de pedidos Redexpres",
    "redexpres.manage":        "Administrar Redexpres: crear meses, gestionar asignaciones de sucursales y desconfirmar pedidos",

    # Facturación
    "facturacion.view":        "Ver el dashboard de Finanzas (presupuesto y canjes)",
    "facturacion.upload":      "Subir facturas PDF, revisar la extracción de DogTi y confirmar o descartar movimientos y canjes",
    "facturacion.manage":      "Administrar las cuentas de Finanzas (crear, renombrar, desactivar)",

    # Redes sociales
    "rrss.view":               "Ver la Validación de RRSS y su historial de validaciones",
    "rrss.validate":           "Validar placas de redes sociales contra el mailing con CatTi y borrar las validaciones propias",

    # Calendario
    "calendario.view":         "Ver el calendario comercial, el de Retail Media y los headers de la home",
    "calendario.edit":         "Crear, editar y borrar acciones, campañas y banners del calendario, mover el estado de las piezas y configurar los avisos de cada acción",
    "calendario.pedidos":      "Crear tareas en las acciones del calendario y pedir sus piezas y materiales (Banners, Mailing, Cenefas…): a cada pieza le nace su tarjeta en el tablero y le llega el aviso a quien la hace",
    "calendario.retail_media": "Mover las posiciones del header que Retail Media tiene reservadas (avisa a quien lleva Retail Media)",
    "calendario.tareas":       "Crear, asignar y borrar las tareas de cada acción del calendario (a quien se le asigna una le llega un aviso)",

    # IA — un permiso por agente de la familia "Tino" + La Triada
    "ai.don_tino":             "Usar el chat de Don Tino, la guía general de la plataforma",
    "ai.dona_tina":            "Usar a Doña Tina — consultas y reportes de precios con IA",
    "ai.tinin":                "Usar a Tinín — generar descripciones con IA en el Convertidor de Excel",
    "ai.triada":               "Usar La Triada — debate y análisis automático de campañas",
    "ai.dogti":                "Usar a DogTi — lectura de facturas PDF con IA y chat sobre el presupuesto",

    # Clientes VIP (0091) — datos confidenciales: no vienen con ningún rol,
    # se tildan a mano a cada persona (Ivan, 25/11/2026: "tengo acceso yo y
    # Emi Perdomo… que tenga permiso para ver la sección así se le da a un usuario").
    "clientes_vip.view":       "Ver el tablero de Clientes VIP: compras, segmentos, riesgo y predicción, y recibir su informe por mail",
    "clientes_vip.cargar":     "Cargar los archivos mensuales de compras de los clientes VIP",
}

# Los permisos que ningún rol trae de fábrica (ni Admin): se dan uno por uno.
SOLO_A_MANO = frozenset({"clientes_vip.view", "clientes_vip.cargar"})

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
        "permissions": [p for p in ALL_PERMISSIONS if p not in SOLO_A_MANO],
        "is_system":   True,
        "view_only":   False,
    },
    {
        "name":        "Usuario",
        "description": "Acceso operativo estándar: cenefas, analytics, precios e IA — sin gestión de usuarios ni conexiones",
        "permissions": [
            "platform.users.view",
            "cenefas.view", "cenefas.generate", "cenefas.edit", "cenefas.import", "cenefas.delete",
            "cenefas.diccionario",
            "analytics.view", "analytics.export",
            "connections.view",
            "precios.search",
            "calendario.view", "calendario.edit", "calendario.pedidos",
            "ai.don_tino", "ai.dona_tina", "ai.tinin", "ai.triada",
        ],
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

"""Clientes VIP (0091): el resumen por cliente y por mes, y lo que se calcula
con él. Qué es cada tabla, en migrations/versions/0091_clientes_vip.py; cómo
se usa, en app/services/clientes_vip.py.

Los datos son confidenciales: viven solo acá, en la base, y los ve quien tiene
`clientes_vip.view`. Nunca en el repo ni en los mails más que en resumen.
"""
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VipCarga(Base):
    __tablename__ = "vip_cargas"

    id: Mapped[int] = mapped_column(primary_key=True)
    archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    meses: Mapped[list] = mapped_column(JSON, nullable=False)
    filas_archivo: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    filas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clientes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    venta: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # cargando → lista. Una que quedó "cargando" se cortó a la mitad.
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="cargando")
    subido_por_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VipClienteMes(Base):
    __tablename__ = "vip_cliente_mes"

    id_cliente: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mes: Mapped[date] = mapped_column(Date, primary_key=True)  # el día 1 del mes
    venta: Mapped[int] = mapped_column(Integer, nullable=False)
    margen: Mapped[int] = mapped_column(Integer, nullable=False)
    unidades: Mapped[int] = mapped_column(Integer, nullable=False)
    tickets: Mapped[int] = mapped_column(Integer, nullable=False)
    dias: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    venta_ecommerce: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    venta_smart: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    venta_marca_propia: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sucursal: Mapped[str | None] = mapped_column(String(80), nullable=True)  # donde más compró
    # Las 3 categorías donde más compró: "Almacén=4523;Bebidas=1200;Lácteos=800"
    categorias: Mapped[str | None] = mapped_column(String(240), nullable=True)
    carga_id: Mapped[int] = mapped_column(Integer, nullable=False)


class VipMesDimension(Base):
    __tablename__ = "vip_mes_dimension"

    mes: Mapped[date] = mapped_column(Date, primary_key=True)
    dimension: Mapped[str] = mapped_column(String(20), primary_key=True)  # categoria | sucursal | canal | marca_propia
    valor: Mapped[str] = mapped_column(String(120), primary_key=True)
    venta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    margen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unidades: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tickets: Mapped[int] = mapped_column(Integer, nullable=False)
    clientes: Mapped[int] = mapped_column(Integer, nullable=False)


class VipCliente(Base):
    __tablename__ = "vip_clientes"

    id_cliente: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    segmento: Mapped[str] = mapped_column(String(20), nullable=False)
    riesgo: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0 a 100
    venta_esperada: Mapped[int] = mapped_column(Integer, nullable=False)  # el mes que viene
    venta_12m: Mapped[int] = mapped_column(BigInteger, nullable=False)
    venta_3m: Mapped[int] = mapped_column(Integer, nullable=False)
    venta_3m_antes: Mapped[int] = mapped_column(Integer, nullable=False)
    margen_12m: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tickets_12m: Mapped[int] = mapped_column(Integer, nullable=False)
    meses_con_compra: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ultimo_mes: Mapped[date | None] = mapped_column(Date, nullable=True)
    sucursal: Mapped[str | None] = mapped_column(String(80), nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parte_ecommerce: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # % de su venta


class VipInforme(Base):
    __tablename__ = "vip_informes"

    id: Mapped[int] = mapped_column(primary_key=True)
    carga_id: Mapped[int | None] = mapped_column(ForeignKey("vip_cargas.id", ondelete="SET NULL"), nullable=True)
    mes: Mapped[date] = mapped_column(Date, nullable=False)  # el último mes con datos
    analisis: Mapped[str] = mapped_column(Text, nullable=False)  # Markdown
    prediccion: Mapped[dict] = mapped_column(JSON, nullable=False)
    con_ia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enviado_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

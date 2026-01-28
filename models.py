from __future__ import annotations

from datetime import datetime, date
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --- Legacy tables (kept for backward compatibility) ---
class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=True, index=True)
    barcode: Mapped[str] = mapped_column(String(80), nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    sales: Mapped[list["Sale"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    qty_sold: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="sales")


# --- New Uzum-aware tables ---
class ProductGroup(Base):
    __tablename__ = "product_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Uzum "productId" (main product id) if available
    uzum_product_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True, unique=True)

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str] = mapped_column(String(800), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    variants: Mapped[list["Variant"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Variant(Base):
    __tablename__ = "variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_groups.id", ondelete="CASCADE"), index=True, nullable=False)

    # Uzum SKU / offer key
    sku: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    barcode: Mapped[str] = mapped_column(String(120), nullable=True, index=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # Useful for UI (color/size)
    color: Mapped[str] = mapped_column(String(80), nullable=True)
    size: Mapped[str] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=True)
    avg_daily_sales: Mapped[float] = mapped_column(Float, nullable=True, default=0.0)

    price_sum: Mapped[int] = mapped_column(Integer, nullable=True)  # price in sum if available

    uzum_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # "На складе" in Uzum
    warehouse_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # local warehouse qty

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    group: Mapped["ProductGroup"] = relationship(back_populates="variants")

    sales: Mapped[list["VariantSale"]] = relationship(
        back_populates="variant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class VariantSale(Base):
    __tablename__ = "variant_sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(Integer, ForeignKey("variants.id", ondelete="CASCADE"), index=True, nullable=False)

    date: Mapped[date] = mapped_column(Date, nullable=False)
    qty_sold: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    variant: Mapped["Variant"] = relationship(back_populates="sales")

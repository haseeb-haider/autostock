"""Data model. Stock is never stored directly - it is derived from Purchases and Sales."""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String
)
from sqlalchemy.orm import relationship

from .database import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, default="")
    lead_time_days = Column(Integer, default=7)

    ingredients = relationship("Ingredient", back_populates="supplier")


class Ingredient(Base):
    __tablename__ = "ingredients"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    unit = Column(String, default="unit")          # kg, g, litre, piece...
    cost_per_unit = Column(Float, default=0.0)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    # Optional manual override; when 0/None the dynamic reorder point is used.
    manual_reorder_level = Column(Float, default=0.0)

    supplier = relationship("Supplier", back_populates="ingredients")
    recipe_items = relationship("RecipeItem", back_populates="ingredient")
    purchases = relationship("Purchase", back_populates="ingredient")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    retail_price = Column(Float, default=0.0)

    recipe_items = relationship("RecipeItem", back_populates="product", cascade="all, delete-orphan")
    sales = relationship("Sale", back_populates="product")


class RecipeItem(Base):
    """One line of a product's bill of materials: how much of an ingredient per unit sold."""
    __tablename__ = "recipe_items"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    qty_per_unit = Column(Float, default=0.0)

    product = relationship("Product", back_populates="recipe_items")
    ingredient = relationship("Ingredient", back_populates="recipe_items")


class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    qty = Column(Float, default=0.0)
    unit_cost = Column(Float, default=0.0)
    order_date = Column(Date, default=date.today)
    status = Column(String, default="ordered")     # ordered | delivered
    delivered_date = Column(Date, nullable=True)
    auto_generated = Column(Boolean, default=False)

    ingredient = relationship("Ingredient", back_populates="purchases")


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    payment_method = Column(String, default="")
    sale_date = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="sales")


class Expense(Base):
    """Operating expenses (rent, salaries, utilities...) - not tied to any ingredient."""
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    expense_date = Column(Date, default=date.today)
    category = Column(String, default="Other")
    description = Column(String, default="")
    amount = Column(Float, default=0.0)
    notes = Column(String, default="")

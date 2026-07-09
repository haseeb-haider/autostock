"""Populate a small demo dataset (a bakery) so the dashboard shows something real."""
import random
from datetime import date, timedelta

from .database import SessionLocal, init_db
from .models import Ingredient, Product, Purchase, RecipeItem, Sale, Supplier


def seed():
    random.seed(42)  # deterministic demo
    init_db()
    db = SessionLocal()
    if db.query(Ingredient).count() > 0:
        db.close()
        print("Data already present, skipping seed.")
        return

    flourco = Supplier(name="FlourCo", email="orders@flourco.example", lead_time_days=5)
    dairy = Supplier(name="Dairy Direct", email="sales@dairydirect.example", lead_time_days=3)
    sundry = Supplier(name="Sundries Ltd", email="hello@sundries.example", lead_time_days=10)
    db.add_all([flourco, dairy, sundry])
    db.flush()

    flour = Ingredient(name="Flour", unit="kg", cost_per_unit=0.8, supplier=flourco)
    sugar = Ingredient(name="Sugar", unit="kg", cost_per_unit=1.1, supplier=flourco)
    butter = Ingredient(name="Butter", unit="kg", cost_per_unit=6.5, supplier=dairy)
    eggs = Ingredient(name="Eggs", unit="piece", cost_per_unit=0.2, supplier=dairy)
    choc = Ingredient(name="Chocolate", unit="kg", cost_per_unit=9.0, supplier=sundry)
    db.add_all([flour, sugar, butter, eggs, choc])
    db.flush()

    croissant = Product(name="Croissant", retail_price=2.5)
    brownie = Product(name="Brownie", retail_price=3.0)
    cookie = Product(name="Cookie", retail_price=1.5)
    db.add_all([croissant, brownie, cookie])
    db.flush()

    db.add_all([
        RecipeItem(product=croissant, ingredient=flour, qty_per_unit=0.08),
        RecipeItem(product=croissant, ingredient=butter, qty_per_unit=0.03),
        RecipeItem(product=croissant, ingredient=eggs, qty_per_unit=0.5),
        RecipeItem(product=brownie, ingredient=flour, qty_per_unit=0.04),
        RecipeItem(product=brownie, ingredient=sugar, qty_per_unit=0.05),
        RecipeItem(product=brownie, ingredient=butter, qty_per_unit=0.04),
        RecipeItem(product=brownie, ingredient=choc, qty_per_unit=0.05),
        RecipeItem(product=brownie, ingredient=eggs, qty_per_unit=1.0),
        RecipeItem(product=cookie, ingredient=flour, qty_per_unit=0.03),
        RecipeItem(product=cookie, ingredient=sugar, qty_per_unit=0.03),
        RecipeItem(product=cookie, ingredient=butter, qty_per_unit=0.02),
        RecipeItem(product=cookie, ingredient=choc, qty_per_unit=0.02),
    ])

    # Opening deliveries (stock in).
    today = date.today()
    # Opening deliveries sized so the demo shows a mix of ok / reorder / out.
    def opening(ingredient, sup_id, qty, cost):
        return Purchase(ingredient=ingredient, supplier_id=sup_id, qty=qty, unit_cost=cost,
                        order_date=today - timedelta(days=35), status="delivered",
                        delivered_date=today - timedelta(days=33))
    db.add_all([
        opening(flour, flourco.id, 212, 0.8),    # -> ok
        opening(sugar, flourco.id, 78, 1.1),     # -> reorder
        opening(butter, dairy.id, 123, 6.5),     # -> ok
        opening(eggs, dairy.id, 1500, 0.2),      # -> reorder
        opening(choc, sundry.id, 54, 9.0),       # -> out
    ])

    # 30 days of sales so consumption rates are meaningful.
    products = [croissant, brownie, cookie]
    for d in range(30, 0, -1):
        day = today - timedelta(days=d)
        for prod in products:
            qty = random.randint(15, 45)
            db.add(Sale(product=prod, qty=qty, unit_price=prod.retail_price, sale_date=day))

    db.commit()
    db.close()
    print("Seed complete.")


if __name__ == "__main__":
    seed()

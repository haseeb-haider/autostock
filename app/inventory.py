"""The stock engine.

Nothing here is typed by a human. Every number below is derived from two logs:
  - Purchases marked "delivered"  -> stock in
  - Sales, exploded through each product's recipe (BOM) -> stock out

This is the same idea as multiplying the recipe matrix by the vector of units
sold, done in Python so it recomputes the instant a sale or delivery is logged.
"""
from collections import defaultdict
from datetime import date, timedelta
from math import ceil

from .config import DEFAULT_LEAD_DAYS, SAFETY_DAYS, WINDOW_DAYS
from .models import Ingredient, Product, Purchase, RecipeItem, Sale, Supplier


def _recipe_map(db):
    """product_id -> list of (ingredient_id, qty_per_unit)."""
    m = defaultdict(list)
    for r in db.query(RecipeItem).all():
        m[r.product_id].append((r.ingredient_id, r.qty_per_unit or 0.0))
    return m


def snapshot(db, window_days: int = WINDOW_DAYS):
    """Return a list of per-ingredient dicts describing the live state of stock."""
    recipe = _recipe_map(db)
    ingredients = db.query(Ingredient).all()
    suppliers = {s.id: s for s in db.query(Supplier).all()}

    delivered_in = defaultdict(float)
    for p in db.query(Purchase).filter(Purchase.status == "delivered").all():
        delivered_in[p.ingredient_id] += p.qty or 0.0

    consumed_total = defaultdict(float)
    consumed_window = defaultdict(float)
    cutoff = date.today() - timedelta(days=window_days)

    for s in db.query(Sale).all():
        for ing_id, per_unit in recipe.get(s.product_id, []):
            used = (s.qty or 0.0) * per_unit
            consumed_total[ing_id] += used
            if s.sale_date and s.sale_date >= cutoff:
                consumed_window[ing_id] += used

    rows = []
    for ing in ingredients:
        stock = delivered_in[ing.id] - consumed_total[ing.id]
        daily_rate = consumed_window[ing.id] / window_days if window_days else 0.0

        sup = suppliers.get(ing.supplier_id)
        lead = (sup.lead_time_days if sup and sup.lead_time_days else DEFAULT_LEAD_DAYS)

        dynamic_rop = daily_rate * (lead + SAFETY_DAYS)
        manual = ing.manual_reorder_level or 0.0
        reorder_point = manual if manual > 0 else dynamic_rop

        days_left = (stock / daily_rate) if daily_rate > 0 else None

        if stock <= 0:
            status = "out"
        elif stock <= reorder_point:
            status = "reorder"
        else:
            status = "ok"

        rows.append({
            "id": ing.id,
            "name": ing.name,
            "unit": ing.unit,
            "supplier": sup.name if sup else "-",
            "supplier_id": ing.supplier_id,
            "cost_per_unit": ing.cost_per_unit or 0.0,
            "stock": round(stock, 3),
            "daily_rate": round(daily_rate, 3),
            "lead_days": lead,
            "reorder_point": round(reorder_point, 3),
            "days_left": round(days_left, 1) if days_left is not None else None,
            "value": round(stock * (ing.cost_per_unit or 0.0), 2),
            "status": status,
        })

    rows.sort(key=lambda r: {"out": 0, "reorder": 1, "ok": 2}[r["status"]])
    return rows


def kpis(rows):
    """Headline numbers for the dashboard."""
    total_value = sum(r["value"] for r in rows if r["value"] > 0)
    reorder = [r for r in rows if r["status"] in ("reorder", "out")]
    return {
        "ingredient_count": len(rows),
        "total_value": round(total_value, 2),
        "reorder_count": len(reorder),
        "out_count": len([r for r in rows if r["status"] == "out"]),
    }


def suggest_order_qty(row, cover_days: int):
    """How much to buy: enough to cover lead time + cover_days, minus what we have."""
    target = row["daily_rate"] * (row["lead_days"] + cover_days)
    if target <= 0:
        # No recent sales but flagged (e.g. manual level) -> top back up to 2x reorder point.
        target = max(row["reorder_point"] * 2, 1)
    need = target - row["stock"]
    return max(ceil(need), 0)

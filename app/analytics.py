"""Reporting helpers for the dashboard: monthly sales/profit, breakdowns, and P&L.
Cost of goods sold is computed from each product's recipe; if a product has no
recipe yet, its cost is 0 - accurate once recipes are filled in, harmless until then.
"""
from collections import defaultdict
from datetime import date

from .models import Expense, Product, RecipeItem, Sale

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _product_unit_cost(db):
    """product_id -> cost to make one unit, from its recipe (0 if no recipe)."""
    cost = defaultdict(float)
    q = (
        db.query(RecipeItem.product_id, RecipeItem.qty_per_unit, RecipeItem.ingredient_id)
        .all()
    )
    if not q:
        return cost
    from .models import Ingredient
    ing_cost = {i.id: (i.cost_per_unit or 0.0) for i in db.query(Ingredient).all()}
    for product_id, qty_per_unit, ingredient_id in q:
        cost[product_id] += (qty_per_unit or 0.0) * ing_cost.get(ingredient_id, 0.0)
    return cost


def monthly_profit_loss(db, year: int):
    """Per-month revenue, cost of goods sold, gross profit, expenses, and net profit."""
    unit_cost = _product_unit_cost(db)
    revenue = [0.0] * 12
    cogs = [0.0] * 12
    for s in db.query(Sale).filter(Sale.sale_date >= date(year, 1, 1),
                                    Sale.sale_date <= date(year, 12, 31)).all():
        m = s.sale_date.month - 1
        line = (s.qty or 0.0) * (s.unit_price or 0.0)
        revenue[m] += line
        cogs[m] += (s.qty or 0.0) * unit_cost.get(s.product_id, 0.0)

    expenses = [0.0] * 12
    for e in db.query(Expense).filter(Expense.expense_date >= date(year, 1, 1),
                                       Expense.expense_date <= date(year, 12, 31)).all():
        expenses[e.expense_date.month - 1] += e.amount or 0.0

    gross_profit = [round(revenue[i] - cogs[i], 2) for i in range(12)]
    net_profit = [round(gross_profit[i] - expenses[i], 2) for i in range(12)]
    revenue = [round(v, 2) for v in revenue]
    cogs = [round(v, 2) for v in cogs]
    expenses = [round(v, 2) for v in expenses]

    total_revenue = round(sum(revenue), 2)
    total_cogs = round(sum(cogs), 2)
    total_expenses = round(sum(expenses), 2)
    total_gross_profit = round(total_revenue - total_cogs, 2)
    total_net_profit = round(total_gross_profit - total_expenses, 2)

    return {
        "months": MONTH_LABELS,
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "expenses": expenses,
        "net_profit": net_profit,
        "totals": {
            "revenue": total_revenue,
            "cogs": total_cogs,
            "gross_profit": total_gross_profit,
            "expenses": total_expenses,
            "net_profit": total_net_profit,
            "gpm": round(total_gross_profit / total_revenue * 100, 1) if total_revenue else 0.0,
            "npm": round(total_net_profit / total_revenue * 100, 1) if total_revenue else 0.0,
        },
    }


def payment_method_breakdown(db):
    """{payment method: total revenue}, unspecified methods grouped as 'Unspecified'."""
    totals = defaultdict(float)
    for s in db.query(Sale).all():
        method = (s.payment_method or "").strip() or "Unspecified"
        totals[method] += (s.qty or 0.0) * (s.unit_price or 0.0)
    return {k: round(v, 2) for k, v in totals.items()}


def stock_status_breakdown(rows):
    """Distinct in-stock / low-stock / no-stock counts from an inventory snapshot."""
    counts = {"ok": 0, "reorder": 0, "out": 0}
    for r in rows:
        counts[r["status"]] += 1
    return {"In Stock": counts["ok"], "Low Stock": counts["reorder"], "No Stock": counts["out"]}

"""AutoStock web application."""
import io
import secrets
from datetime import date, datetime

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload, selectinload

from . import config
from .analytics import monthly_profit_loss, payment_method_breakdown, stock_status_breakdown
from .automation import build_reorder_plan, run_daily
from .database import get_db, init_db
from .export import build_workbook
from .inventory import kpis, snapshot
from .models import Expense, Ingredient, Product, Purchase, RecipeItem, Sale, Supplier
from .scheduler import start_scheduler

app = FastAPI(title="AutoStock")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["currency"] = config.CURRENCY_SYMBOL
_basic = HTTPBasic(auto_error=False)


def guard(creds: HTTPBasicCredentials = Depends(_basic)):
    """Optional HTTP Basic auth over the UI; a no-op unless APP_USER/APP_PASS are set."""
    if not (config.APP_USER and config.APP_PASS):
        return
    ok = creds and secrets.compare_digest(creds.username, config.APP_USER) and \
        secrets.compare_digest(creds.password, config.APP_PASS)
    if not ok:
        raise HTTPException(status_code=401, detail="Auth required",
                            headers={"WWW-Authenticate": "Basic"})


def require_token(token: str):
    if not secrets.compare_digest(token or "", config.ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid token")


@app.on_event("startup")
def _startup():
    init_db()
    start_scheduler()


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# --- Dashboard ------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, year: int = None, db: Session = Depends(get_db), _=Depends(guard)):
    rows = snapshot(db)
    plan = build_reorder_plan(db)
    suggestions = []
    for entry in plan.values():
        for ln in entry["lines"]:
            suggestions.append({**ln, "supplier": entry["supplier"].name
                                if entry["supplier"] else "-"})

    low_stock_rows = [r for r in rows if r["status"] == "reorder"]
    out_of_stock_rows = [r for r in rows if r["status"] == "out"]
    year = year or date.today().year
    pl = monthly_profit_loss(db, year)
    stock_breakdown = stock_status_breakdown(rows)
    payment_breakdown = payment_method_breakdown(db)

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "rows": rows, "kpis": kpis(rows),
        "suggestions": suggestions, "business": config.BUSINESS_NAME,
        "low_stock_rows": low_stock_rows, "out_of_stock_rows": out_of_stock_rows,
        "pl": pl, "year": year, "stock_breakdown": stock_breakdown,
        "payment_breakdown": payment_breakdown,
    })


# --- Ingredients ----------------------------------------------------------
@app.get("/ingredients", response_class=HTMLResponse)
def ingredients_page(request: Request, db: Session = Depends(get_db), _=Depends(guard)):
    ingredients = (
        db.query(Ingredient).options(joinedload(Ingredient.supplier))
        .order_by(Ingredient.name).all()
    )
    return templates.TemplateResponse("ingredients.html", {
        "request": request, "ingredients": ingredients,
        "suppliers": db.query(Supplier).order_by(Supplier.name).all(), "business": config.BUSINESS_NAME,
    })


@app.post("/ingredients")
def add_ingredient(name: str = Form(...), unit: str = Form("unit"),
                   cost_per_unit: float = Form(0.0), supplier_id: int = Form(None),
                   manual_reorder_level: float = Form(0.0),
                   db: Session = Depends(get_db), _=Depends(guard)):
    db.add(Ingredient(name=name, unit=unit, cost_per_unit=cost_per_unit,
                      supplier_id=supplier_id or None,
                      manual_reorder_level=manual_reorder_level))
    db.commit()
    return RedirectResponse("/ingredients", status_code=303)


# --- Suppliers ------------------------------------------------------------
@app.get("/suppliers", response_class=HTMLResponse)
def suppliers_page(request: Request, db: Session = Depends(get_db), _=Depends(guard)):
    return templates.TemplateResponse("suppliers.html", {
        "request": request, "suppliers": db.query(Supplier).all(),
        "business": config.BUSINESS_NAME,
    })


@app.post("/suppliers")
def add_supplier(name: str = Form(...), email: str = Form(""),
                 lead_time_days: int = Form(7),
                 db: Session = Depends(get_db), _=Depends(guard)):
    db.add(Supplier(name=name, email=email, lead_time_days=lead_time_days))
    db.commit()
    return RedirectResponse("/suppliers", status_code=303)


# --- Products & recipes ---------------------------------------------------
@app.get("/products", response_class=HTMLResponse)
def products_page(request: Request, db: Session = Depends(get_db), _=Depends(guard)):
    products = (
        db.query(Product)
        .options(selectinload(Product.recipe_items).joinedload(RecipeItem.ingredient))
        .order_by(Product.name)
        .all()
    )
    return templates.TemplateResponse("products.html", {
        "request": request, "products": products,
        "ingredients": db.query(Ingredient).order_by(Ingredient.name).all(), "business": config.BUSINESS_NAME,
    })


@app.post("/products")
def add_product(name: str = Form(...), retail_price: float = Form(0.0),
                db: Session = Depends(get_db), _=Depends(guard)):
    db.add(Product(name=name, retail_price=retail_price))
    db.commit()
    return RedirectResponse("/products", status_code=303)


@app.post("/recipe")
def add_recipe_item(product_id: int = Form(...), ingredient_id: int = Form(...),
                    qty_per_unit: float = Form(...),
                    db: Session = Depends(get_db), _=Depends(guard)):
    db.add(RecipeItem(product_id=product_id, ingredient_id=ingredient_id,
                      qty_per_unit=qty_per_unit))
    db.commit()
    return RedirectResponse("/products", status_code=303)


# --- Quick entry: sales & purchases --------------------------------------
@app.get("/log", response_class=HTMLResponse)
def log_page(request: Request, db: Session = Depends(get_db), _=Depends(guard)):
    pending = (
        db.query(Purchase).options(joinedload(Purchase.ingredient))
        .filter(Purchase.status == "ordered").order_by(Purchase.order_date).all()
    )
    return templates.TemplateResponse("log.html", {
        "request": request, "products": db.query(Product).order_by(Product.name).all(),
        "ingredients": db.query(Ingredient).order_by(Ingredient.name).all(),
        "suppliers": db.query(Supplier).order_by(Supplier.name).all(),
        "pending": pending,
        "business": config.BUSINESS_NAME,
    })


@app.post("/sales")
def add_sale(product_id: int = Form(...), qty: float = Form(...),
             unit_price: float = Form(0.0), sale_date: str = Form(""),
             payment_method: str = Form(""),
             db: Session = Depends(get_db), _=Depends(guard)):
    d = date.fromisoformat(sale_date) if sale_date else date.today()
    db.add(Sale(product_id=product_id, qty=qty, unit_price=unit_price,
                payment_method=payment_method, sale_date=d))
    db.commit()
    return RedirectResponse("/log", status_code=303)


@app.post("/purchases")
def add_purchase(ingredient_id: int = Form(...), supplier_id: int = Form(None),
                 qty: float = Form(...), unit_cost: float = Form(0.0),
                 status: str = Form("ordered"),
                 db: Session = Depends(get_db), _=Depends(guard)):
    deliv = date.today() if status == "delivered" else None
    db.add(Purchase(ingredient_id=ingredient_id, supplier_id=supplier_id or None,
                    qty=qty, unit_cost=unit_cost, status=status, delivered_date=deliv))
    db.commit()
    return RedirectResponse("/log", status_code=303)


@app.post("/purchases/{purchase_id}/deliver")
def mark_delivered(purchase_id: int, db: Session = Depends(get_db), _=Depends(guard)):
    p = db.get(Purchase, purchase_id)
    if p:
        p.status = "delivered"
        p.delivered_date = date.today()
        db.commit()
    return RedirectResponse("/log", status_code=303)


# --- Expenses ---------------------------------------------------------------
EXPENSE_CATEGORIES = ["Salaries", "Utilities", "Rent", "Maintenance", "Supplies", "Other"]


@app.get("/expenses", response_class=HTMLResponse)
def expenses_page(request: Request, db: Session = Depends(get_db), _=Depends(guard)):
    expenses = db.query(Expense).order_by(Expense.expense_date.desc()).all()
    total = round(sum(e.amount or 0.0 for e in expenses), 2)
    by_category = {}
    for e in expenses:
        by_category[e.category] = round(by_category.get(e.category, 0.0) + (e.amount or 0.0), 2)
    return templates.TemplateResponse("expenses.html", {
        "request": request, "expenses": expenses, "total": total,
        "by_category": by_category, "categories": EXPENSE_CATEGORIES,
        "business": config.BUSINESS_NAME,
    })


@app.post("/expenses")
def add_expense(category: str = Form("Other"), description: str = Form(""),
                 amount: float = Form(0.0), expense_date: str = Form(""),
                 notes: str = Form(""),
                 db: Session = Depends(get_db), _=Depends(guard)):
    d = date.fromisoformat(expense_date) if expense_date else date.today()
    db.add(Expense(category=category, description=description, amount=amount,
                   expense_date=d, notes=notes))
    db.commit()
    return RedirectResponse("/expenses", status_code=303)


@app.post("/expenses/{expense_id}/delete")
def delete_expense(expense_id: int, db: Session = Depends(get_db), _=Depends(guard)):
    e = db.get(Expense, expense_id)
    if e:
        db.delete(e)
        db.commit()
    return RedirectResponse("/expenses", status_code=303)


# --- Export -----------------------------------------------------------------
@app.get("/export.xlsx")
def export_xlsx(db: Session = Depends(get_db), _=Depends(guard)):
    """Download the current inventory, products, suppliers, purchases, and sales as an Excel workbook."""
    wb = build_workbook(db)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{config.BUSINESS_NAME.replace(' ', '_')}_export_{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Automation + integration endpoints (token protected) -----------------
@app.post("/tasks/run-daily")
def tasks_run_daily(token: str = "", db: Session = Depends(get_db)):
    """Hit by the GitHub Action once a day. Runs reorder detection + notifications."""
    require_token(token)
    return run_daily(db)


@app.get("/tasks/preview", response_class=PlainTextResponse)
def tasks_preview(token: str = "", db: Session = Depends(get_db)):
    require_token(token)
    plan = build_reorder_plan(db)
    if not plan:
        return "Nothing to reorder."
    from .automation import _po_text
    return "\n\n".join(_po_text(e) for e in plan.values())


@app.post("/api/sale")
def api_sale(token: str = "", product_id: int = Form(...), qty: float = Form(...),
             unit_price: float = Form(0.0), db: Session = Depends(get_db)):
    """POS/webhook entry point so sales can flow in with zero human interaction."""
    require_token(token)
    db.add(Sale(product_id=product_id, qty=qty, unit_price=unit_price, sale_date=date.today()))
    db.commit()
    return {"status": "recorded"}

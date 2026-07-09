"""The part that runs itself: detect shortfalls, draft purchase orders, notify."""
import smtplib
from collections import defaultdict
from datetime import date
from email.message import EmailMessage

from . import config
from .inventory import snapshot, suggest_order_qty
from .models import Purchase, Supplier


def build_reorder_plan(db):
    """Return {supplier_id: {"supplier": Supplier, "lines": [...], "total": float}}."""
    rows = snapshot(db)
    suppliers = {s.id: s for s in db.query(Supplier).all()}
    plan = defaultdict(lambda: {"supplier": None, "lines": [], "total": 0.0})

    for r in rows:
        if r["status"] not in ("reorder", "out"):
            continue
        qty = suggest_order_qty(r, config.COVER_DAYS)
        if qty <= 0:
            continue
        sid = r["supplier_id"]
        line_cost = qty * r["cost_per_unit"]
        plan[sid]["supplier"] = suppliers.get(sid)
        plan[sid]["lines"].append({
            "ingredient_id": r["id"],
            "name": r["name"],
            "unit": r["unit"],
            "qty": qty,
            "unit_cost": r["cost_per_unit"],
            "line_cost": round(line_cost, 2),
            "stock": r["stock"],
            "reorder_point": r["reorder_point"],
        })
        plan[sid]["total"] += line_cost

    for sid in plan:
        plan[sid]["total"] = round(plan[sid]["total"], 2)
    return dict(plan)


def _po_text(entry):
    sup = entry["supplier"]
    name = sup.name if sup else "Unassigned supplier"
    out = [f"Purchase order - {name}", f"Date: {date.today().isoformat()}", ""]
    for ln in entry["lines"]:
        out.append(
            f"  {ln['qty']} {ln['unit']} x {ln['name']} "
            f"@ {ln['unit_cost']:.2f} = {ln['line_cost']:.2f} "
            f"(stock {ln['stock']}, reorder at {ln['reorder_point']})"
        )
    out += ["", f"Order total: {entry['total']:.2f}", ""]
    return "\n".join(out)


def _send_email(to_addr, subject, body):
    if not (config.SMTP_HOST and to_addr):
        return False, "email not configured"
    msg = EmailMessage()
    msg["From"] = config.MAIL_FROM
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASS)
            smtp.send_message(msg)
        return True, "sent"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the job
        return False, f"send failed: {exc}"


def run_daily(db):
    """The scheduled routine. Returns a summary dict for the endpoint/log."""
    plan = build_reorder_plan(db)
    result = {"date": date.today().isoformat(), "suppliers": [], "emails": [],
              "created_purchases": 0}

    digest_parts = []
    for sid, entry in plan.items():
        text = _po_text(entry)
        digest_parts.append(text)
        sup = entry["supplier"]
        result["suppliers"].append({
            "supplier": sup.name if sup else "Unassigned",
            "lines": len(entry["lines"]),
            "total": entry["total"],
        })

        if config.AUTO_CREATE_PO:
            for ln in entry["lines"]:
                db.add(Purchase(
                    ingredient_id=ln["ingredient_id"], supplier_id=sid,
                    qty=ln["qty"], unit_cost=ln["unit_cost"],
                    order_date=date.today(), status="ordered", auto_generated=True,
                ))
                result["created_purchases"] += 1

        if config.AUTO_SEND_PO and sup and sup.email:
            ok, info = _send_email(sup.email, f"Purchase order - {config.BUSINESS_NAME}", text)
            result["emails"].append({"to": sup.email, "ok": ok, "info": info})

    if config.AUTO_CREATE_PO:
        db.commit()

    # Always send the owner a digest if there is anything to reorder.
    if digest_parts and config.ALERT_EMAIL and not config.AUTO_SEND_PO:
        body = ("AutoStock daily reorder digest\n\n" + "\n".join(digest_parts))
        ok, info = _send_email(config.ALERT_EMAIL,
                               f"Reorder digest - {len(plan)} supplier(s)", body)
        result["emails"].append({"to": config.ALERT_EMAIL, "ok": ok, "info": info})

    result["digest"] = "\n\n".join(digest_parts) if digest_parts else "Nothing to reorder."
    return result

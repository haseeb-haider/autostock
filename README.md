# AutoStock — self-driving inventory

A small web app that runs your stock control with almost no manual work. You log
**sales** (by hand, CSV, or a POS webhook) and click **delivered** when orders
arrive. Everything else is derived and automated.

## What it does

- **Stock is never typed.** Current stock is calculated: delivered purchases add,
  sales consume raw ingredients through each product's recipe (bill of materials).
- **Dynamic reorder points.** Instead of a fixed threshold you guess, each
  ingredient's reorder point = recent daily consumption × (supplier lead time +
  safety days). It adapts to how fast things actually sell.
- **Auto purchase orders.** A daily job finds everything below its reorder point,
  groups the shortfall by supplier, sizes each order to cover lead time + a buffer,
  and emails you a digest (or emails the suppliers directly, or auto-creates the
  orders — your choice via env flags).
- **Zero-touch intake option.** A token-protected `/api/sale` endpoint lets a POS
  or webhook feed sales in automatically.

## The automation loop

```
log sale ──▶ stock recalculates ──▶ daily job checks reorder points
   ▲                                          │
   └──── mark delivered ◀── you approve ◀── drafted purchase orders / email
```

## Free hosting stack

| Piece      | Service               | Why |
|------------|-----------------------|-----|
| Web app    | Render (free web service) | Free; sleeps after 15 min idle |
| Database   | Neon (free Postgres)  | Permanent free tier — Render's own free DB self-deletes after 30 days |
| Daily job  | GitHub Actions cron   | Free; the scheduled request also wakes the sleeping Render service |
| Email      | Any SMTP (e.g. Gmail app password) | Free |

## Run locally

```bash
pip install -r requirements.txt
python run.py          # seeds demo data, starts http://127.0.0.1:8000
```

Uses SQLite automatically when `DATABASE_URL` is unset.

## Deploy (all free)

1. **Database — Neon.** Create a free project at neon.tech, copy the connection
   string (looks like `postgresql://...?sslmode=require`).
2. **Push to GitHub.** Put this folder in a repo.
3. **Web service — Render.** New → Blueprint, point it at the repo (it reads
   `render.yaml`). In the dashboard set `DATABASE_URL` to your Neon string.
   `ADMIN_TOKEN` is generated for you — copy its value. Deploy.
4. **Seed / create tables.** Tables auto-create on first boot. To load demo data
   once, run `python -m app.seed` from Render's shell (or skip and add your own
   data through the UI).
5. **Daily automation — GitHub Actions.** In the repo settings → Secrets, add:
   - `APP_URL` = your Render URL (e.g. `https://autostock.onrender.com`)
   - `ADMIN_TOKEN` = the token from Render
   The workflow in `.github/workflows/daily.yml` runs every morning and can be
   triggered manually from the Actions tab.

## Configuration (env vars)

See `.env.example`. Key ones:

- `WINDOW_DAYS` — days of sales history used for the consumption rate (default 30)
- `DEFAULT_LEAD_DAYS`, `SAFETY_DAYS`, `COVER_DAYS` — tune reorder sizing
- `AUTO_CREATE_PO` — daily job creates `ordered` purchase rows automatically
- `AUTO_SEND_PO` — email POs to suppliers instead of a digest to you
- `APP_USER` / `APP_PASS` — optional HTTP Basic login over the UI
- `SMTP_*`, `ALERT_EMAIL` — email delivery

## Endpoints

- `GET /` dashboard · `GET /log` quick entry · `/products` `/ingredients` `/suppliers`
- `GET /export.xlsx` download ingredients, products & recipes, suppliers, purchases, and sales as an Excel workbook
- `POST /tasks/run-daily?token=...` run automation (called by the cron)
- `GET /tasks/preview?token=...` plain-text preview of the drafted POs
- `POST /api/sale?token=...` record a sale from a POS/webhook
- `GET /health` health check

## Adapting to a non-food business

The "ingredient → recipe → product" model is a generic bill of materials. For a
business that resells finished goods (no assembly), give each product a one-line
recipe mapping it to a single stock item at `qty_per_unit = 1`, and it behaves
like a straight stock tracker.

## Security notes

Automation and webhook endpoints are token-protected; the UI can be put behind
HTTP Basic via `APP_USER`/`APP_PASS`. For real multi-user use, add proper
sessions/roles and put it behind HTTPS (Render provides TLS by default).

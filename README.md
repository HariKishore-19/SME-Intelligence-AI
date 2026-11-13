# SME Intelligence AI

**Buyer update:** Buyer/Seller login, buyer signup with username and contact number, storefront offers, cart, cash-on-delivery orders and loyalty points are included. See [BUYER_SETUP.md](BUYER_SETUP.md). Buyer demo: `demo_buyer` / `Buyer@12345`; seller demo: `demo@sme.lk` / `Demo@12345`. Points are earned when sellers confirm paid/completed purchases.

**Comparison buttons:** select a product and click Compare with Daraz or Compare with eBay for an immediate site-specific analysis.

**Marketplace update:** choose Daraz Sri Lanka or eBay for competitor discovery. eBay supports an optional official Browse API token; Daraz uses clearly labelled search excerpts. See AUTOMATION_SETUP.md.

**Automation update:** automatic web competitor discovery and Facebook/Instagram campaign publishing are included. Read [AUTOMATION_SETUP.md](AUTOMATION_SETUP.md) for API keys, Meta account setup, schedules and limitations. These integrations need your credentials; no social post has been sent during development.

Runnable hackathon MVP for Sri Lankan SMEs. Full React / TypeScript / Vite / Tailwind frontend and FastAPI / SQLAlchemy backend. A compiled frontend is included: Node.js is only needed when editing/rebuilding the UI.

## Quick start — Windows / VS Code

1. Install Python 3.12+ (enable “Add Python to PATH”).
2. Extract this ZIP fully. Open the `sme-intelligence-ai` folder in VS Code.
3. Double-click `start-windows.bat`, or run it from a VS Code terminal:

```powershell
.\start-windows.bat
```

4. Keep that terminal open. Visit **http://localhost:8000**.

First launch needs internet to install Python dependencies. The SQLite database and demo account are initialized automatically. No PostgreSQL, Node.js, or AI key is needed for basic packaged mode. Automatic web discovery needs a Tavily key, and social posting needs Meta credentials. If port 8000 is busy, stop the other server or change the port in the script.

Demo email: **demo@sme.lk**
Demo password: **Demo@12345**

Linux/macOS: `bash start.sh` (Python 3.12+ and venv support required).

## Manual backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe -m uvicorn main:app --reload` directly.

## Edit the frontend

Install Node.js 22+. Keep backend running on port 8000. In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite forwards `/api` to FastAPI. Run `npm run build` after edits to update the bundled frontend; restart Uvicorn if necessary.

## Included functionality

- Seller registration, Argon2 password hashing, expiring JWT login, logout.
- Separate business workspace per account; all business-owned queries enforce business ownership.
- Editable business profile, location and currency label (no currency conversion).
- Product create/edit/delete, search, category filter, computed unit costs/profit/margins, stock counts and validation.
- Backend-calculated competitive, target-margin and penetration pricing, using recorded competitor observations.
- Manual competitor management and price observations; comparison chart and price differences.
- Sales API supports multiple line items, duplicates aggregate, stock checks and transactional inventory update. UI records one product per transaction. Historical unit prices and costs are preserved.
- Transaction history, individual details, date filter, operating expense recording.
- Actual and seeded-demo financial KPI cards are separate; charts are clearly marked when they include demo sales.
- Revenue/profit charts, best sellers, low-stock list and product margin insights.
- Marketing campaigns, saved campaign history, copyable Facebook/Instagram/headline content, backend-calculated promotion profit and loss warning.
- Contextual business assistant with calculated fallback answers.
- Responsive navigation, mobile layout, loading/error/empty states.

## Optional Gemini

Copy `backend/.env.example` to `backend/.env`, supply `GEMINI_API_KEY`, and restart. Without a key or if a provider request fails, deterministic guidance is returned and labelled. Numeric financial outputs always come from Python calculations; generated prose is advisory. Provider access was not live-tested with credentials. `GEMINI_MODEL` is configurable if your account uses a different model.

Only the authenticated workspace's context is sent to the configured provider. No API key is exposed in frontend code. Do not commit `.env`.

Without `JWT_SECRET`, a random process secret is used; restarting logs users out. For stable sessions, set a long random secret in `.env`.

## Database and schema

Default: SQLite `backend/sme.db` when started using included scripts. SQLAlchemy creates tables at startup. Set `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE` for PostgreSQL. PostgreSQL configuration is supported but was not verified against a live instance.

Core business data uses three relational tables rather than the full normalized schema requested in the specification. Two additional tables store automation configuration and persistent jobs:

- `users`: id, unique email, name, password hash.
- `businesses`: id, unique user_id foreign key, name, category, location, currency.
- `records`: id, indexed business_id foreign key, indexed kind, JSON-text data, created_at. Kinds: product, competitor, price, sale, expense, campaign, discovery.
- `automation_state`: business primary/foreign key, configuration, encrypted connection credentials.
- `automation_jobs`: business foreign key, unique business/job key, kind, platform, due time, state, payload, platform ID and errors.

Product/competitor references inside payloads are checked in the API, not via database foreign keys. Sale items are historical snapshots. Product deletion retains sales history. Tenant ownership is enforced in every API operation. This structure is suitable for a local MVP; normalize records into dedicated tables and add migrations before scaling.

Seeded sale history represents sample historical activity; seeded current stock represents opening inventory and is not decremented again for historical samples. Actual sales decrement current stock. Actual net profit subtracts cost of sold inventory plus recorded operating expenses. Demo metrics exclude operating expenses. Monetary inputs allow two decimals; calculations are rounded to two decimals in Python. JSON payload storage uses numbers rather than fixed-precision SQL numeric columns.

To reset a local demo, stop the server and delete `backend/sme.db` (this permanently removes local accounts and transactions). Restart to recreate. Set `SEED_DEMO=false` before first startup to disable demo creation; this does not remove existing demo data.

## API documentation

Interactive Swagger: **http://localhost:8000/docs**. OpenAPI JSON: **http://localhost:8000/openapi.json**. Login, copy `access_token`, then use Swagger's Authorize button with the bearer token.

Routes:

- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET/PUT /api/business`
- `GET/POST /api/products`, `PUT/DELETE /api/products/{id}`
- `POST /api/pricing/analyze/{id}` body `{ "margin": 25 }`
- `GET/POST /api/competitors`, `POST /api/competitors/prices`
- `GET/POST /api/sales` body `{ "items": [{ "product_id": 1, "quantity": 2 }] }`
- `GET/POST /api/expenses`
- `POST /api/marketing/generate`, `GET /api/marketing/campaigns`
- `GET /api/analytics/overview`, `/api/analytics/revenue`, `/api/analytics/products`
- `POST /api/ai/chat` body `{ "message": "What discount can I safely offer?" }`
- `GET /api/health`

Product IDs are database-generated; get `/api/products` first rather than assuming IDs. Product payload: name, category, description, image_url, purchase_cost, transportation_cost, additional_expenses, selling_price, stock.

## Verification

```powershell
cd backend
python -m pytest -q
cd ../frontend
npm run build
```

14 tests verify the business flow and new automation paths; see AUTOMATION_SETUP.md for coverage and live-integration limitations. Frontend TypeScript and production build were checked. Full visual browser QA was not completed because Chromium was blocked by this execution environment.

## Deployment and remaining scope

This is a working hackathon MVP, not a production-complete SaaS. Before public hosting: disable seeded demo registration, configure a strong stable secret, exact HTTPS CORS origins, persistent PostgreSQL, HTTPS hosting, backups, authentication rate limiting, password reset/email verification, request logs and operational monitoring. Buyer/seller roles are included; an admin role and tenant membership sharing are not included.

For Vercel, deploy `frontend` with build command `npm run build` and output `dist`, setting `VITE_API_URL` to the public backend origin. For Render, use root `backend`, install requirements, run `uvicorn main:app --host 0.0.0.0 --port $PORT`, configure database/secrets/CORS. Hosting has not been deployed or verified.

Not implemented: normalized per-entity tables/Alembic migrations, verified live product feeds or site-specific scraping, one-click Meta OAuth or automatic token renewal, demand forecasting, persisted AI recommendation records, category-sales chart, separate product-profitability chart, multi-line manual seller sale UI (buyer cart supports multiple lines), multi-currency conversion, business switching, notification inbox, image uploads, BOGO/bundle optimization or automated ad spend. Business selector, top search and notifications from the original design brief were simplified to functional workspace navigation and product search. Automatic campaigns rotate deterministic templates without an LLM key; manual campaign generation remains template based. Demo campaign history begins empty until a campaign is generated.

Buyer accounts add role, username, contact number and points fields to users. New store_offers/customer_orders tables implement buyer transactions; existing installations are upgraded on startup. See BUYER_SETUP.md for setup, purchase semantics and limitations.

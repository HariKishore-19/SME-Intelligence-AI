# Buyer dashboard, offers and loyalty points

## Run and sign in

Start the app with `start-windows.bat`, then open http://localhost:8000. The login page has **Buyer** and **Seller** options. Account roles are enforced in the backend; selecting a different option does not grant access to the other role.

Demo credentials (only with demo seeding enabled):

| Role | Username/email | Password |
| --- | --- | --- |
| Seller | demo@sme.lk | Demo@12345 |
| Buyer | demo_buyer | Buyer@12345 |

The buyer contact number `+94770000000` is a demo placeholder. No SMS or messages are sent.

Choose Buyer → Create a buyer account to register your name, email, username, contact number and password. A contact number is required; it is stored with the buyer profile and is shared only with the seller fulfilling that buyer's order. There is no phone ownership verification. New sellers can also choose a username; existing sellers can continue signing in with email. Usernames and email identities are normalized to lowercase and are unique. A single account has one role; use separate accounts/emails if you need both roles.

## Buyer dashboard

- **Shop:** browse LKR products from seller businesses, search and filter by category, see stock and the best active eligible offer.
- **Offers:** products with a live seller-published discount, showing title, percentage, regular price, discounted price, savings and end date.
- **Cart:** add items, adjust quantities, refresh changed prices, and place an order with one seller at a time.
- **My purchases:** see pending/completed/cancelled orders, purchased item snapshots, offer details and pending/earned points. Buyers can cancel their own pending orders.
- **My profile:** name, username, email, contact number and total earned points.

Seller purchase costs and unit profit are never exposed by buyer catalog/order APIs. Buyer API routes reject seller tokens; seller business routes reject buyer tokens. Buyers can view only their own order history. Sellers can see only their own store's orders and the contact details needed to fulfill those orders.

## Points policy

The implemented default is **1 point for each Rs. 100 paid**, rounded down separately for each completed order, based on the discounted order total.

| Completed order total | Points earned |
| --- | ---: |
| Rs. 99 | 0 |
| Rs. 100 | 1 |
| Rs. 299 | 2 |
| Rs. 600 | 6 |

This version uses **cash on delivery / pay at collection**, with seller confirmation. It does not collect online payments. At checkout the app reserves stock and shows estimated pending points. Once the seller confirms that payment and fulfillment are complete, it records the sale and awards the points atomically. Cancelling a pending order restores stock and awards no points. A completed order cannot be cancelled through this MVP; returns/refunds and points reversal are future work.

Points accumulate only: redemption, point cash value, expiry, tiers and transfer are not implemented. The point rate was assumed to be 1 per Rs. 100; it is not a configurable seller setting.

## Seller workflow

Open **Buyer Store** in the seller sidebar.

1. Publish an offer by choosing a product, title, percentage discount and future end date. It starts immediately. Existing future-start offers are supported by the API.
2. The server blocks offers that would sell below unit cost. If costs later rise or the offer expires, an unsafe/expired offer is not used by the buyer catalog or a new checkout. When multiple valid offers apply, the lowest eligible price wins; offers are not stacked.
3. Manage active offers from the same page. Disabling an offer stops it applying to future checkouts; existing orders retain their purchase-price snapshots.
4. View customer orders and their contact number.
5. After collecting payment and fulfilling the order, choose **Confirm paid & completed**. This records a seller sale and credits buyer points once.
6. Cancel an unfulfilled pending order to restore inventory without awarding points.

Marketing campaigns remain drafts/advice; publishing a campaign to social media does not create a buyer discount automatically. Publish the corresponding storefront offer in Buyer Store when you want it to apply at checkout. This keeps customer prices under the seller's control.

## Upgrade an existing installation

Stop the old server before changing files. Preserve your existing `backend/sme.db`, `.env` and `.social-token.key`. Install the new project files (including the rebuilt `frontend/dist`, `backend/buyers.py` and updated `backend/main.py`), run the startup script, and refresh the browser with Ctrl+F5.

Startup performs a non-destructive users-table upgrade: existing accounts become sellers, and nullable username/contact fields plus a zero point balance are added. Existing products, sales, credentials and businesses are preserved. New `store_offers` and `customer_orders` tables are created automatically. Back up the database first. The older-schema upgrade was verified with SQLite; PostgreSQL remains unverified against a live server.

## New endpoints

- `POST /api/auth/register`: role `buyer` or `seller`; buyers require username/phone; sellers require business_name.
- `POST /api/auth/login`: username or email, password, role. Response includes role and JWT.
- `GET /api/auth/me`: authenticated account role/profile/points.
- `GET /api/buyer/catalog`
- `GET /api/buyer/orders`
- `POST /api/buyer/checkout`: items (product_id, quantity, expected_price) plus idempotency_key.
- `POST /api/buyer/orders/{id}/cancel`
- `GET /api/store/orders`
- `PUT /api/store/orders/{id}/status`: completed/cancelled.
- `GET/POST /api/store/offers`
- `DELETE /api/store/offers/{id}`: deactivate an offer.

Checkout prices and loyalty amounts are calculated by the backend. Client expected_price detects a stale/expired offer instead of silently increasing the purchase price. An idempotency key prevents repeat requests from creating duplicate orders. Repeated completion does not record another sale or award points twice. Customer orders include seller/buyer foreign keys and historical line snapshots. Product deletion is blocked while pending orders reference it. The local SQLite transaction serializes checkout/status writes; PostgreSQL paths use row locks but have not been live-tested.

## Verification and limits

14 API tests pass, including buyer role/contact validation, cross-role access denial, private catalog/order responses, discounted checkout, stock reservation, stale-price/oversell rejection, checkout deduplication, completion deduplication, accurate loyalty flooring, cancellation restocking, tenant isolation and loss-making offer rejection. The frontend TypeScript and production build pass. An older SQLite database was upgraded and its seller login/business remained valid.

No live payment processor, delivery integration, SMS verification, buyer address collection, returns/refunds, point redemption or admin dashboard is included. Buyer storefront supports LKR purchases only. Demo history remains labelled in seller analytics. Browser visual testing was not completed because Chromium was blocked in this environment; review both dashboards locally before presenting.

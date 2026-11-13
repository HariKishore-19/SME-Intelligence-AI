# Automatic competitor analysis and Facebook / Instagram marketing

## What this update does

1. Searches the web for your product names using Tavily, without entering competitor URLs by hand.
2. Records candidate sellers, source URLs, excerpts, check times, name-token similarity and possible LKR prices.
3. Calculates provisional lowest/highest/average comparable prices and shows an analysis.
4. Selects a product using available stock and profitability, calculates an affordable discount, and creates campaign copy.
5. Publishes generated posts to your connected Facebook Page and Instagram professional account when you enable automatic publishing, or lets you review and schedule them first.
6. Retains per-business job history and platform IDs; failed, blocked, processing, published and unknown jobs are distinguished.

No social post has been sent as part of preparing this project. Automation starts only after you connect services and enable it in your local app.

## Start the updated project

Extract the ZIP and run `start-windows.bat`, then open http://localhost:8000. Python 3.12+ is required. First-time dependency installation requires internet. Login with `demo@sme.lk` / `Demo@12345`, or register your own business.

If upgrading a running copy: stop the old server first. Preserve your `backend/sme.db`, `.env`, and `.social-token.key` if you have them. Replace source/build files, install the updated requirements, and restart. New automation tables are created automatically. Do not delete the database to update the project.

## A. Automatic competitor discovery

1. Add products with precise names, including **brand, size and variant**. “Rice 5kg” is less reliable than a specific brand and rice variety.
2. Obtain a search API key at https://app.tavily.com.
3. In **Competitor Analysis → Connect web discovery**, enter the key and save it. Do not paste secrets into chat or commit them to Git.
4. Click **Analyze now** to test.
5. Inspect the source-linked findings. Expand each product to see evidence, possible prices and comparison advice.
6. Enable **Automatically search for competitors**, choose an interval of 6–168 hours, and save preferences.

Each run checks up to 20 products, oldest analyzed first. A search request is made per product. Provider quotas and usage charges apply. If a key is absent, invalid, or a request fails, the job fails explicitly; no competitors or prices are fabricated.

### What is and is not verified

This is automatic web discovery and heuristic price extraction from search excerpts. It is **not a guarantee of exact product matching or fresh checkout prices**. Search indexes may be cached; variants, stock, shipping, promotions and pack sizes can differ. A check time records when the search was run, not when the retailer last changed its price.

The extractor requires all normalized product-name tokens in a result title and exactly one unambiguous currency-qualified price (or an official eBay structured price) before including that result in a provisional comparison. Ambiguous prices are left blank. Listing currencies are preserved. Only prices matching the business currency are averaged or accepted into pricing intelligence; exchange-rate conversion is not implemented. Automatic findings do not silently change selling prices or enter the main pricing engine as verified observations.

If a result is the exact product/quantity, choose **Confirm product match & use price**. That records a seller-reviewed observation for the existing pricing engine. Reaccepting the same finding is idempotent. The pricing engine uses the latest observation per competitor rather than averaging historical duplicates.

## B. Connect Meta accounts

This update uses the **Facebook Login / Facebook Graph API** flow for both platforms. It has developer-token setup screens, not one-click OAuth. A personal Facebook profile and a consumer Instagram account are not publishing targets.

You need:

- A Facebook **Page** you can manage, its Page ID and its Page access token.
- An Instagram **professional account** linked to that Page, its Instagram account ID and an appropriate Page token with Instagram permissions.
- A Meta developer app with the permissions/access required for your accounts. Posting for other businesses can require app review and additional access.

Official references:

- https://developers.facebook.com/docs/pages-api/posts/
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing/
- https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api

Typical Facebook publishing permission is `pages_manage_posts`; Page reads can need `pages_read_engagement`. Instagram publishing in this chosen Facebook Login flow uses `instagram_basic`, `instagram_content_publish`, and `pages_read_engagement`; Page discovery uses `pages_show_list`. Check the official documentation and your Meta app for the exact permission/access requirements.

In **AI Marketing Agent → Connect Facebook & Instagram**:

1. Enter Facebook Page ID and Page access token.
2. Enter Instagram professional account ID and its appropriate token.
3. Save connections.
4. Use each **Test** button to check the account identity. This read test does not guarantee every publishing permission is available.

Tokens are encrypted at rest using Fernet. Without `SOCIAL_TOKEN_KEY`, a persistent local `backend/.social-token.key` is created on the first credential save. Back up this key with your database, keep it private and never commit it. Hosted deployments must set a stable `SOCIAL_TOKEN_KEY` and persist the database. Tokens are never returned by connection/status APIs. Blank token fields preserve existing credentials; Disconnect removes them and cancels queued posts for that connection. Token expiry requires reconnection; OAuth and refresh-token handling are not included.

## C. Generate and publish

1. Add your own products and realistic costs/stock.
2. For Instagram, set each product's **Image URL** to a publicly accessible HTTPS JPEG that Meta can download. The app does not create or host product images.
3. Set the minimum stock, minimum margin, maximum discount and objective under **Marketing agent settings**.
4. Click **Run marketing agent now**. It chooses eligible inventory by stock × unit profit and caps the discount to preserve your configured margin. Without eligible inventory, it creates no campaign.
5. Review the campaign preview and calculated offer. Competitor context shows any latest provisional web analysis and any manually entered/reviewed price average; unverified comparisons are not published as factual claims.
6. Select Facebook or Instagram. Leave the time blank to publish now, or choose a future local date/time to schedule. The UI converts the time to UTC for storage.
7. Review job history. Facebook posts are text posts. Instagram publishes a product image with a caption through container creation, processing and final publication.

For unattended operation, turn on **Automatically generate campaigns**, then optionally enable automatic Facebook and/or Instagram publishing and save preferences. Enabling the posting checkbox authorizes future generated campaigns to be queued for that connected account. Without automatic posting, campaigns remain drafts for review.

Schedules are interval buckets in UTC, not a fixed Sri Lankan clock-time calendar. Enabling a schedule can run it immediately, then at the next interval boundary. The worker checks due work approximately once a minute. Keep the backend and its internet connection running, or host it on an always-on server. If your computer is off, jobs do not execute. Missed recurring intervals are not replayed; already queued posts are processed after startup. Cancelling a queued job prevents its future execution. Disabling automatic campaign posting stops new auto-queued posts; cancel already queued jobs separately.

The same campaign/platform pair is queued only once. Price, cost and stock are checked again before publication, and Instagram checks again before its final publish step. A timeout or interrupted worker may leave a post **unknown**: verify the real account before creating another post. These uncertain jobs are not automatically retried to avoid duplicate public posts. Published jobs cannot be cancelled from this app.

The discounted advertised price does not change your product's regular selling price or reserve inventory. Sales are still entered by the seller; a separate buyer checkout now supports explicit seller-published offers; see BUYER_SETUP.md. Generated marketing copy should be reviewed for your business's factual claims when you first configure the agent.

## D. Optional Gemini

Set `GEMINI_API_KEY` in `backend/.env` and restart. The agent requests a short post opening and appends the calculated offer price itself. Without a key or on provider failure, rotating deterministic templates are used and labelled. The agent does not invent financial figures. Full social image design, image generation, paid advertising, performance optimization, Reels and comment handling are outside this update.

## Environment settings

```dotenv
TAVILY_API_KEY=
GEMINI_API_KEY=
META_GRAPH_VERSION=v26.0
AUTOMATION_WORKER=true
# Generate once and keep stable:
SOCIAL_TOKEN_KEY=
```

Generate a Fernet key using:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Per-business search keys entered in the app take precedence over the optional server-wide Tavily key. Use separate business keys if you need separate billing.

## New API endpoints

- `GET /api/automation`: configuration, masked connection state, recent reports/jobs.
- `PUT /api/automation/config`: validated schedules and marketing rules.
- `PUT /api/automation/connections`: encrypted search/Meta credentials.
- `DELETE /api/automation/connections/{platform}`: disconnect tavily/facebook/instagram.
- `POST /api/automation/connections/{platform}/test`: read account identity.
- `POST /api/automation/discover` body `{}` or `{ "product_id": 1 }`.
- `POST /api/automation/reports/{id}/accept` body `{ "candidate_index": 0 }`.
- `POST /api/automation/marketing/run`.
- `POST /api/automation/posts` body `{ "campaign_id": 1, "platform": "facebook", "scheduled_at": null }`.
- `POST /api/automation/jobs/{id}/run`: run a due queued social post or poll a processing post.
- `DELETE /api/automation/jobs/{id}`: cancel a queued job.

All endpoints require the authenticated business token. New tables are `automation_state` (one per business, encrypted credentials/configuration) and `automation_jobs` (persistent queue, business/key uniqueness, states and platform IDs). Existing business data tables remain compatible.

## Validation and limitations

Ten tests cover the original business flow plus missing search credentials, evidence-only search results, ambiguous-price rejection, tenant isolation, encrypted token storage, safe discount generation, queued-post deduplication, stale cost blocking, scheduler idempotency, cancellation, uncertain-post handling and the Meta adapter's request sequence. External providers are mocked in these tests. The frontend TypeScript / production build passes.

Live Tavily, Gemini and Meta publishing have not been tested with real credentials. No post was published during development. Browser visual QA was attempted but the available Chromium process was blocked by the execution environment; complete browser testing on your computer before a live demonstration. The app is still a hackathon MVP. One always-on Uvicorn worker is the intended deployment; distributed scheduling, token refresh, provider webhooks, automated deletion and publication analytics are not implemented.


## Marketplace source update — Daraz and eBay

In **Competitor Analysis → Discovery schedule**, select **Daraz Sri Lanka**, **eBay**, and/or **Other websites**. Save preferences before running Analyze now. New businesses default to Daraz and eBay. Existing saved preferences get the same default when no source selection was previously saved.

- **Daraz Sri Lanka:** Tavily search restricted to `daraz.lk`. This is indexed discovery, not a Daraz live-price API or a checkout scraper. Result cards show title, URL, excerpt, an unambiguous price when available and check time. Seller, stock, shipping and image details remain “not supplied” when the source does not provide them. No seller credentials are required for this search route; a Tavily key is required.
- **eBay search mode:** Tavily search restricted to eBay domains. Price is shown only when its currency is explicit. A bare `$` is not assumed to mean USD.
- **eBay API mode:** Enter an OAuth **production application access token** in the new eBay token field, or set `EBAY_APPLICATION_TOKEN` in the backend environment. With this token, eBay results use the official Browse `item_summary/search` endpoint with fixed-price filtering. Choose US, UK or Australia. Result cards include listing title, item price/currency, seller username, feedback percentage, condition, image, location and shipping quote when the API supplies them. This requires eligible eBay production API access. The application token expires and must be replaced; automatic OAuth token minting is not included. A personal eBay password is never used.
- **Other websites:** generic Tavily discovery, not a dedicated integration for every shop. Coverage depends on search indexing. Unsupported fields remain unavailable.

An eBay token alone can run eBay API discovery; Daraz and generic sources still need Tavily. Source-specific errors are displayed in each report so an unavailable source is not mistaken for “no competitors.” If there are no matches, add brand/model/size to the product name. No example marketplace results are seeded or fabricated.

The price difference is calculated only for candidate matches in the same currency as the seller. Shipping quotes from eBay reflect marketplace-default context, not a confirmed Sri Lankan delivery address. Duties/taxes are not calculated. Review brand, pack quantity, condition, shipping destination and availability on the source listing before using an observation. An API-sourced listing price is not a guarantee of product equivalence.

Daraz Open Platform seller authorization should not be confused with public competitor search access. A direct Daraz-wide competitor API integration is not included. The implemented route uses marketplace-restricted search excerpts.

Official eBay references:
- https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search
- https://developer.ebay.com/api-docs/static/oauth-client-credentials-grant.html

New regression tests validate marketplace-domain filtering (including misleading domain suffixes), eBay request parameters and seller fields, ambiguous dollar symbols, and exclusion of USD listings from an LKR comparison. All ten backend tests pass, and the frontend production build passes. Live eBay/Tavily access remains untested without credentials.


## Compare one product with one site

At the top of **Competitor Analysis**, select your product and click **Compare with Daraz** or **Compare with eBay**. This immediately analyzes that product on only the chosen source, independently of saved schedule preferences. It does not redirect you to a marketplace instead of running an analysis.

The returned analysis shows your selling price/cost/profit/margin, the observed comparable price range, average price, price difference and percentage difference, and your position relative to the observed range. It warns if matching the lowest observed price would leave no positive profit. Reports include only the selected marketplace; same-currency candidate matching and source limitations still apply. Different currencies remain visible in listing details but are excluded from averages and percentage differences. If there are no supported matches, no price is invented. Search/provider failures are displayed separately.

Choose **View listing details** to see the matching listings. **Show all reports** returns to the full history; Daraz and eBay reports for the same product are retained separately. Product selling prices are not changed automatically.

New endpoint: `POST /api/automation/compare` with `{ "product_id": 1, "marketplace": "daraz" }` or `"ebay"`. Requires a product owned by the authenticated business and credentials for the selected source. Daraz needs Tavily; eBay can use a production Browse application token or Tavily. The new regression test verifies exact source isolation, calculated price differences, foreign-currency exclusion and preservation of schedule configuration. Ten tests pass.

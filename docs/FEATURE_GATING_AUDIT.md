## Feature-gating audit (2026-03-18)

### Doel
Controleren dat premium functionaliteit **backend-protected** is en dat losse `plan_code` / `subscription_status` checks waar logisch zijn gecentraliseerd via `app/billing/features.py` en `app/billing/dependencies.py`.

### Aangepast
- **`app/verticals/paintly/router_app.py`**
  - `POST /app/leads/{lead_id}/send`
    - Feature gate toegevoegd: `Feature.BASIC_SENDING` (redirect naar billing bij ontbrekende feature)
    - `subscription_status` check gecentraliseerd via `is_subscription_accessible(...)`
    - Route gebruikt nu `check_entitlement(..., Action.SEND_QUOTE)` (geen losse plan checks)
    - Bestaande usage/paywall (quote_limit) checks intact gelaten
  - **`GET /app/leads/{lead_id}/export-pdf`** (nieuwe premium endpoint)
    - PDF download van estimate HTML; beschermd met `Depends(require_entitlement(Action.EXPORT_PDF))`
    - 403 met entitlement payload als tenant geen PDF export heeft; 404 als lead/estimate ontbreekt
    - Smoke test: Pro/Business + lead met estimate_html_key → 200 + PDF; Starter → 403
  - Template context uitgebreid met:
    - `feature_flags` (booleans)
    - `features` (UI viewmodel incl. upgrade_url/hint)
    - `entitlements` (per-actie status voor templates)

### Al correct / centraal
- **`app/billing/features.py`**: centrale registry + plan mapping + helpers (pure business logic)
- **`app/billing/dependencies.py`**: `require_feature(...)`, `require_any_feature(...)`, `ensure_feature_or_redirect(...)` (herbruikbaar voor routes)
- **`app/billing/ui.py`**: UI helper op basis van dezelfde gating rules (geen frontend-only gating)

### Bewust niet vervangen (usage/paywall of niet-gating)
- **`app/services/billing_summary_service.py`**: gebruikt `tenant.plan_code` voor usage summary / limieten (geen feature access control)
- **`app/verticals/paintly/router_app.py`**: `plan_code` selectie voor `quote_limit` (usage/paywall)
- **Templates**: `subscription_status` wordt gebruikt voor weergave (geen access control)

### Handmatige review aanbevolen
- **PDF export**
  - **Paintly**: `GET /app/leads/{lead_id}/export-pdf` is de eerste echte premium endpoint; beschermd met `require_entitlement(Action.EXPORT_PDF)`.
  - `app/services/quote_renderer.py` (legacy/quote stack) genereert PDF met WeasyPrint; niet gebruikt door Paintly export-pdf.

- **Branding/logo + whitelabel routes**
  - `logo_url` leeft vooral in `TenantSettings`/templates; er is geen aparte update/upload route gevonden.
  - Als/wanneer er settings endpoints komen:
    - Branding: `Feature.BRANDING`
    - Whitelabel: `Feature.WHITELABEL`

- **Debug/legacy endpoints**
  - `app/routers/quote_debug.py` is ongeauthenticeerd en triggert compute logic (geen expliciete premium gate).
  - Advies: in productie afschermen (auth/flag) of feature-gate als het premium output levert.

### Kleine cleanup notes
- `app/billing/dependencies.py`: ongebruikte imports verwijderd; denied feature access logging toegevoegd (zonder gevoelige data).


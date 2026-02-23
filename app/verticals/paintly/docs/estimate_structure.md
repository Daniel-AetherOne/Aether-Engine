# US Painters — Estimate Structure (Step 5.2)

Goal: Every job uses the same section order and framing to match US expectations.
Document type: **Estimate** (never "Quote/Proposal/Offer/Bid").

---

## Global rules

- Currency is **USD ($)** everywhere.
- Use labels from `app/verticals/painters_us/copy.py`.
- If `pricing_ready = false`:
  - Show **Estimated Total Range** (never a single total).
  - Show “Estimate Needs Review” badge/title variant.
- Itemized breakdown is always present (even in needs review).
- Section order below is fixed.

---

## Fixed section order

### 1) Header (project + customer)
Include:
- Title: **Painting Estimate** (or **Estimate Needs Review** badge when applicable)
- Customer name (and location/address if available)
- Estimate ID / Reference (lead_id or estimate_id)
- Date created
- Valid until (e.g., 14 days)
- Company/contractor info (branding block)

### 2) Scope summary (what’s included)
Purpose: quick clarity in <10 seconds.
Format: 2–5 bullets.
Include:
- Areas included (e.g., Interior walls, ceilings, trim, doors)
- Work included (prep, prime as needed, finish coats)
- Protection & cleanup (masking, floor protection, cleanup)
Add line: “See Exclusions below.”

Needs review add-on:
- “Final scope will be confirmed after additional photos/site verification.”

### 3) Itemized breakdown (per surface / per area)
Purpose: transparency aligned with vision output.
Render as a table/list with stable columns:
- Item / Area (surface_type + label)
- Quantity (sq ft or count, with unit)
- Prep level (Light / Standard / Heavy)
- Access risk (Low / Medium / High)
- Line total (USD) OR “TBD” for uncertain items

Ordering rule (stable):
- Interior → Exterior → Trim/Doors → Ceilings (or a consistent mapping)

Needs review:
- Optional: show a subtle “Low confidence” note per uncertain item (no clutter).

### 4) Labor vs Materials (summary)
Purpose: US-style breakdown without over-detailing.
Show:
- Labor: $X
- Materials: $Y
Footnote allowed:
- “Materials include paint & consumables unless noted.”

Needs review:
- Use “(est.)” labels if totals are provisional.

### 5) Estimated total (or range)
If `pricing_ready = true`:
- Label: **Estimated Total**
- Value: `$X,XXX.XX`

If `pricing_ready = false`:
- Label: **Estimated Total Range**
- Value: `$X,XXX.XX – $Y,YYY.YY`
- Subline: “Pending review of uncertain areas.”

Never use: “Total price”, “Final price”, “Guaranteed”.

### 6) Assumptions
Purpose: prevent scope creep.
Short bullet list, e.g.:
- Access to work areas during scheduled hours
- Surfaces are structurally sound; no hidden moisture/rot
- Customer clears/moves small items unless specified
- Color/coverage assumptions if relevant

Needs review add-on:
- “Assumptions may be updated after site verification.”

### 7) Disclaimer
Use the matching disclaimer from `copy.py`:
- `disclaimer_pricing_ready` when `pricing_ready = true`
- `disclaimer_needs_review` when `pricing_ready = false`

This is always the final section.

---

## Definition of Done (Step 5.2)

- The 7 sections above exist in every estimate.
- The section order never changes across jobs.
- Needs-review estimates show a range and a needs-review framing.
- All wording remains “Estimate”-based (no quote/proposal language).

## Billing & Entitlement – Paintly Release Checklist

Korte, handmatige QA-checklist voor release en regressie.

---

### 1. Plan matrix (handmatig verifiëren)

- **Starter (starter_99)**  
  - Kan offertes verzenden (basic sending).  
  - **Geen** PDF export, **geen** branding, **geen** whitelabel.

- **Pro (pro_199)**  
  - Kan offertes verzenden.  
  - PDF export endpoint werkt.  
  - Branding settings (logo) kunnen worden opgeslagen en zijn zichtbaar.  
  - **Geen** whitelabel.

- **Business (business_399)**  
  - Kan offertes verzenden.  
  - PDF export endpoint werkt.  
  - Branding werkt.  
  - Whitelabel (verbergen van Paintly-branding) is actief.

---

### 2. Billing states (per plan kort testen)

Voor elk plan (Starter, Pro, Business) test minimaal:

- **active**  
  - Entitlements volgens planmatrix zijn toegestaan.

- **trialing**  
  - Gedraagt zich als active (features volgens plan beschikbaar).

- **inactive / past_due / canceled**  
  - Offerte verzenden, PDF export, branding write en whitelabel: allemaal **geblokkeerd** (403 of redirect naar billing).

- **unknown / None plan_code**  
  - Alle premium features (PDF, branding, whitelabel) zijn **geblokkeerd**.

---

### 3. End-to-end feature checks

- **Offerte verzenden (SEND_QUOTE)**  
  - Starter/Pro/Business met geldige subscription: verzenden werkt tot aan usage-limit.  
  - Bij overschreden usage-limit: bestaande paywall-UX blijft werken (redirect/boodschap).  
  - Bij inactieve/past_due/canceled subscription: geen verzenden; duidelijke billing-redirect/melding.

- **PDF export endpoint (`GET /app/leads/{id}/export-pdf`)**  
  - Starter: 403 met `error="entitlement_denied"`.  
  - Pro/Business: 200 + valide PDF.

- **Branding settings update (`POST /app/settings/branding`)**  
  - Starter: 403 met `error="entitlement_denied"`.  
  - Pro/Business: 200 en `logo_url` wordt opgeslagen.

- **Branding zichtbaar in HTML/PDF**  
  - Pro/Business met `logo_url`: logo in estimate-HTML (top bar) en in PDF.  
  - Starter met `logo_url` in settings: **geen** custom logo in HTML/PDF (fallback-icoon).

- **Whitelabel zichtbaar in HTML/PDF**  
  - Business:  
    - Geen Paintly-favicon.  
    - Geen “Paintly” merknaam in estimate-header/footer waar whitelabel actief is.  
  - Starter/Pro: Paintly-branding blijft zichtbaar.

- **Directe API-call zonder entitlement**  
  - Aanroepen van premium endpoints (PDF export, branding update) met een tenant zonder recht → altijd 403 met gestructureerde entitlement-payload.

- **HTML upgrade UX / redirects**  
  - Bij geblokkeerde acties vanuit UI (bv. send/ PDF/ branding) wordt naar `/app/billing` of relevante upgrade-URL gestuurd met duidelijke query-parameters.

---

### 4. Logging & privacy

- **Denied entitlements worden gelogd**  
  - Controleer logs op entries voor feature/entitlement-denies met:  
    - tenant_id, plan_code, subscription_status, action/feature, path.

- **Geen gevoelige details in responses**  
  - 403 responses bevatten geen intern stacktrace of geheimen; alleen reden, plan, subscription-status en upgrade/billing-URLs.

- **Geen onnodige interne details in logs**  
  - PDF/HTML-fouten loggen geen volledige paden of content, alleen een korte oorzaak (bijv. exception-type).

---

### 5. Downgrade / regressie checks

- **Starter**  
  - Geen PDF export, geen branding-logo in output, geen whitelabel.  
  - Offerte-verzend flow blijft werken binnen usage-limit.

- **Pro**  
  - Heeft PDF export en branding (logo in HTML/PDF).  
  - **Geen** whitelabel (Paintly-merk blijft zichtbaar).

- **Business**  
  - Behoudt alle premium output: PDF, branding, whitelabel.  
  - Whitelabel verbergt Paintly-branding zoals bedoeld, zonder andere functionaliteit te breken.


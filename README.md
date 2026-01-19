# Aether Engine – Decision Infrastructure Platform

Aether Engine is a modular, API-first decision engine that combines rule-based logic with AI reasoning to automate complex business decisions (pricing, classification, quotations) for B2B wholesalers and other verticals.

> This repository contains documentation and a high-level overview only.  
> Full source code is available under NDA during the hiring process – please ask for a read-only invite.

---

## 1. What it does
- Ingests structured / unstructured data (API calls, files, text)  
- Applies domain rules + LLM-based interpretation  
- Returns a **binding decision** (price, outcome, document) to ERP / CRM / web portals  
- Horizontal core – vertical-specific "engines" plug in on top

---

## 2. Architecture (high-level)
┌─ External systems (ERP/CRM) ─┐
│        REST / JSON           │
└──────────┬──────────┬────────┘
│          │
┌──────▼──────┐  ┌─▼──────────────┐
│  Aether     │  │  AI reasoning  │
│  Rules      │  │  (LLM)         │
└──────┬──────┘  └─┬──────────────┘
│           │
└─────┬─────┘
▼
┌──────────────┐
│   Decision   │──► Output (JSON / PDF / UBL)
└──────────────┘
Copy

---

## 3. Implemented vertical
**Aether Commerce Engine (ACE)** – live MVP  
- Scope: B2B wholesale pricing & quotation automation  
- Handles customer-specific agreements, tier prices, margin rules, one-off quotes  
- Integrated with Exact Online and SAP S/4 HANA sandboxes

---

## 4. Tech snapshot
- Backend: Python 3.11, FastAPI (async), Pydantic  
- AI: OpenAI GPT-4 + in-house rule engine (ANTLR)  
- Task queue: Celery + Redis  
- Observability: Prometheus, Grafana, Loki  
- Infra: Docker, AWS (S3, IAM, RDS), Terraform  
- Testing: pytest (unit 92 %), Postman (contract), Locust (load)

---

## 5. Key metrics (ACE MVP)
- 500 price requests/min P95 < 220 ms  
- 99.8 % uptime last 3 months (Grafana)  
- 40 % reduction in quotation turnaround time (pilot customer, n=1 200 quotes)

---

## 6. Repository content
├── docs/               # Architecture diagrams
├── demos/              # Postman collections & sample payloads
├── README.md           # This file
└── LICENSE             # Proprietary – collaboration on request
Copy

---

## 7. Collaboration & code access
The platform is proprietary.  
For recruitment purposes I can provide:
- time-boxed, read-only GitHub invite, or  
- anonymised ZIP + architecture walkthrough (video call)  
Both under mutual NDA. Please contact me via the e-mail in my CV.

---

## 8. Links
- Product site: https://aetherone.tech  
- Vertical page: https://aetherone.tech/b2b-groothandels  

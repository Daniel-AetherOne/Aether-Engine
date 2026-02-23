# Aether Engine

**Aether Engine** is a Python-based backend system that demonstrates how AI-assisted decision logic can be integrated into a clean, production-style service.

The project focuses on **applied AI engineering**: structuring decision pipelines, combining deterministic rules with AI-derived signals, and keeping outcomes explainable, testable, and extensible.

**Status:** Work in progress — built as a learning and portfolio project.

---

## Overview

Modern AI systems rarely rely on model output alone. Real-world decision systems must be:

- explainable  
- auditable  
- controllable  
- resilient to edge cases  

Aether Engine explores a hybrid approach where **AI provides signals** and **rules provide control**, producing decisions that remain transparent and debuggable.

The system is organized around a decision pipeline that separates:

1. Input validation  
2. Rule evaluation  
3. AI-derived signals  
4. Final decision assembly  

---

## What this project demonstrates

- Structuring AI-related logic beyond notebooks and scripts  
- Combining deterministic business rules with AI-derived signals  
- Designing modular backend services using FastAPI  
- Keeping AI outputs separate from final decision logic  
- Engineering for explainability, validation, and extensibility  
- Building systems that remain debuggable in production environments  

---

## Why this matters in real systems

In production environments:

- AI outputs alone are rarely sufficient  
- decisions must be explainable and auditable  
- rule layers provide control, compliance, and safety  
- hybrid AI + rules systems are common in finance, insurance, logistics, and SaaS platforms  

This project explores these engineering realities.

---

## Example use case: Pricing & intake automation

One vertical implemented in this repository demonstrates an automated pricing and intake workflow.

### High-level flow

1. Structured input is received via an API  
2. Domain-specific rules and heuristics are applied  
3. Optional AI-derived signals (e.g., scoring or classification) influence the outcome  
4. A structured decision object is returned  

This use case serves as a technical example rather than a finished business product.

---

## Real-world application: Paintly

**Paintly** is a practical implementation built on top of Aether Engine.  
It is an AI-assisted intake and quotation engine designed for painting contractors.

Paintly automates the **intake → estimation → quotation** workflow while keeping decisions transparent and rule-driven.

### What Paintly does

Paintly processes customer requests and generates structured work estimates and quotations.

**Input**

- Customer request form  
- Uploaded photos of spaces or surfaces  

**Automated analysis includes**

- Estimation of rooms and surfaces using image analysis  
- Detection of work type (interior, exterior, renovation, new build)  
- Complexity indicators such as height, edges, and surface condition  

**Combined with**

- Pricing rules  
- Labor and material logic  
- Company-specific settings (rates, margins)  

**Output**

- Structured work estimate  
- Price calculation  
- Professional quotation (HTML/PDF)  

Paintly does not replace skilled craftsmen.  
It automates administrative and estimation tasks so professionals can focus on their work.

---

## Value for painting businesses

### Reduced time spent on quotations

Instead of manually reviewing photos, estimating measurements, calculating pricing, and drafting quotes, the system prepares a structured estimate automatically.

This reduces daily administrative workload for owners, planners, and office staff.

### Faster response times increase win rates

Quotes can be generated within minutes rather than days, increasing the likelihood of securing jobs before competitors respond.

### Consistent and predictable pricing

Rule-based pricing ensures repeatable margins and reduces underpricing, errors, and inconsistencies.

### Reduced dependency on individual expertise

Operational knowledge moves from individuals into system rules, making the business more scalable and resilient.

### Foundation for future automation

Structured intake data enables:

- Job history insights  
- Pricing analytics  
- Datasets linking images to work scope  
- Smarter future estimations  
- Planning and duration forecasting  

Today: quotation automation  
Tomorrow: operational intelligence  
Future: workflow automation support  

---

## Project structure

## PDF export (WeasyPrint) – runtime notes

De Paintly PDF export endpoint rendert opgeslagen estimate-HTML met **WeasyPrint**.
WeasyPrint heeft **native (OS) dependencies** nodig. Als die ontbreken krijg je errors zoals:
`OSError: cannot load library 'libgobject-2.0-0'`.

---

### Waar WeasyPrint wordt gebruikt

- **Paintly route**: `GET /app/leads/{lead_id}/export-pdf`  
  Importeert `weasyprint.HTML` en roept `HTML(string=html_content).write_pdf()` aan.

---

### Lokaal (Windows) – wat ontbreekt?

De fout `cannot load library 'libgobject-2.0-0'` betekent dat de **GTK/GLib stack** die
WeasyPrint onder water gebruikt niet beschikbaar is op je systeem.

Opties:

- **Gebruik Docker** (aanrader): draai de app via de project `Dockerfile` (Linux) zodat je
  dezelfde libs hebt als in productie.
- **Installeer de benodigde native libs op Windows**:
  - Installeer GTK runtime (die o.a. `libgobject-2.0-0` levert) + dependencies.
  - Alternatief: gebruik WSL2 en installeer de Linux packages (zie hieronder).

---

### Linux runtime (Render/Cloud Run) – minimale packages

Minimaal nodig voor de meeste WeasyPrint setups:

- `libglib2.0-0`  (levert o.a. `libgobject-2.0-0`)
- In veel gevallen ook:
  - `libpango-1.0-0`
  - `libpangocairo-1.0-0`
  - `libcairo2`
  - `libgdk-pixbuf-2.0-0`
  - fonts (bijv. `fonts-dejavu-core`)

Let op: welke subset exact nodig is kan afhangen van jouw HTML/CSS/fonts.

---

### Deployment: wat moet er op Render ingesteld worden?

Als je op Render bouwt met een **Docker image**, installeer bovenstaande packages in je Dockerfile
met `apt-get install`.

Als je op Render **zonder Docker** bouwt, voeg een build stap toe die packages installeert
(Render supports apt packages afhankelijk van je setup), of schakel over naar Docker deployment.

---

### Dit project: huidige status

De repository `Dockerfile` installeert al `libglib2.0-0`.  
Als je WeasyPrint nog errors ziet op Linux, voeg dan de aanvullende packages toe
onder dezelfde `apt-get install` regel.


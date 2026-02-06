import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple
import jinja2
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from app.models.tenant_settings import TenantSettings
from app.services.storage import Storage, get_storage, LocalStorage

class QuoteRenderer:
    """Service voor het renderen van offertes naar HTML en PDF met tenant branding."""
    
    def __init__(self, templates_dir: str = "app/templates", storage: Storage = None):
        """
        Initialiseer de QuoteRenderer.
        
        Args:
            templates_dir: Pad naar de templates directory
            storage: Storage adapter voor bestandsopslag (optioneel, gebruikt factory functie als niet gegeven)
        """
        self.templates_dir = Path(templates_dir)
        self.storage = storage or get_storage()
        
        # Jinja2 template loader
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            autoescape=True
        )
    
    def render_quote(self, lead: Dict[str, Any], prediction: Dict[str, Any], 
                    pricing: Dict[str, Any], tenant_settings: TenantSettings) -> Dict[str, str]:
        """
        Render een offerte naar HTML en PDF met tenant branding.
        
        Args:
            lead: Klantgegevens (naam, email, telefoon, adres, square_meters)
            prediction: Voorspelling resultaten (substrate, issues, confidences)
            pricing: Prijsberekening resultaten (subtotal, vat_amount, total, etc.)
            tenant_settings: Tenant configuratie voor branding
            
        Returns:
            Dict met html_path, pdf_path en public_url
        """
        # Genereer unieke quote ID en datum
        quote_id = str(uuid.uuid4())[:8].upper()
        current_date = datetime.now()
        validity_date = current_date + timedelta(days=30)
        
        # Maak tenant-specifieke directory structuur
        year_month = current_date.strftime("%Y-%m")
        
        # Bereid template data voor met tenant branding
        template_data = self._prepare_template_data(
            lead, prediction, pricing, quote_id, current_date, validity_date, tenant_settings
        )
        
        # Render HTML
        html_content = self._render_html_template(template_data)
        
        # Genereer PDF
        pdf_content = self._generate_pdf_bytes(html_content, tenant_settings)
        
        # Sla bestanden op via storage adapter
        html_key = f"offers/{year_month}/{quote_id}/{quote_id}.html"
        pdf_key = f"offers/{year_month}/{quote_id}/{quote_id}.pdf"
        
        # Sla HTML op
        html_bytes = html_content.encode('utf-8')
        self.storage.save_bytes(tenant_settings.tenant_id, html_key, html_bytes)
        
        # Sla PDF op
        self.storage.save_bytes(tenant_settings.tenant_id, pdf_key, pdf_content)
        
        # Genereer public URLs via storage adapter
        html_url = self.storage.public_url(tenant_settings.tenant_id, html_key)
        pdf_url = self.storage.public_url(tenant_settings.tenant_id, pdf_key)
        
        return {
            "html_path": html_key,  # Nu een storage key in plaats van lokaal pad
            "pdf_path": pdf_key,    # Nu een storage key in plaats van lokaal pad
            "public_url": pdf_url,  # PDF URL als primaire public URL
            "html_url": html_url,
            "quote_id": quote_id,
            "year_month": year_month,
            "tenant_id": tenant_settings.tenant_id
        }
    
    def _prepare_template_data(self, lead: Dict[str, Any], prediction: Dict[str, Any],
                              pricing: Dict[str, Any], quote_id: str, 
                              current_date: datetime, validity_date: datetime,
                              tenant_settings: TenantSettings) -> Dict[str, Any]:
        """Bereid template data voor met tenant branding."""
        
        # Bereid pricing data voor met surcharges
        pricing_data = {
            "subtotal": pricing.get("subtotal", 0),
            "vat_amount": pricing.get("vat_amount", 0),
            "total": pricing.get("total", 0),
            "aannames": pricing.get("aannames", []),
            "doorlooptijd": pricing.get("doorlooptijd", "2-3 werkdagen"),
            "base_per_m2": pricing.get("base_per_m2", 0)
        }
        
        # Bereken surcharges voor issues
        surcharges = []
        if prediction.get("issues"):
            base_price_per_m2 = pricing.get("base_per_m2", 0)
            for issue in prediction["issues"]:
                # Simpele surcharge berekening (kan uitgebreid worden)
                surcharge_percent = 0.15  # 15% extra per issue
                surcharge_amount = base_price_per_m2 * surcharge_percent
                surcharge_total = surcharge_amount * lead.get("square_meters", 0)
                
                surcharges.append({
                    "description": f"Extra behandeling voor {issue}",
                    "amount": surcharge_amount,
                    "total": surcharge_total
                })
        
        pricing_data["surcharges"] = surcharges
        
        return {
            "lead": lead,
            "prediction": prediction,
            "pricing": pricing_data,
            "quote_id": quote_id,
            "current_date": current_date.strftime("%d-%m-%Y"),
            "validity_date": validity_date.strftime("%d-%m-%Y"),
            "tenant": {
                "company_name": tenant_settings.company_name,
                "logo_url": tenant_settings.logo_url,
                "primary_color": tenant_settings.primary_color,
                "secondary_color": tenant_settings.secondary_color
            }
        }
    
    def _render_html_template(self, template_data: Dict[str, Any]) -> str:
        """Render de HTML template met de gegeven data."""
        template = self.jinja_env.get_template("quote.html")
        return template.render(**template_data)
    
    def _generate_pdf_bytes(self, html_content: str, tenant_settings: TenantSettings) -> bytes:
        """
        Genereer PDF van HTML content met tenant-specifieke styling.
        
        Args:
            html_content: HTML content als string
            tenant_settings: Tenant configuratie voor styling
            
        Returns:
            PDF content als bytes
        """
        try:
            # Font configuratie voor betere PDF rendering
            font_config = FontConfiguration()
            
            # HTML object maken
            html_doc = HTML(string=html_content)
            
            # CSS voor print optimalisatie met tenant branding
            css_content = f"""
                @page {{
                    size: A4;
                    margin: 2cm;
                }}
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }}
                .header {{
                    page-break-after: avoid;
                }}
                .section {{
                    page-break-inside: avoid;
                }}
                .pricing-table {{
                    page-break-inside: avoid;
                }}
                .tenant-branding {{
                    color: {tenant_settings.primary_color};
                }}
                .tenant-secondary {{
                    color: {tenant_settings.secondary_color};
                }}
            """
            
            css_doc = CSS(string=css_content, font_config=font_config)
            
            # PDF genereren naar bytes
            pdf_bytes = html_doc.write_pdf(
                stylesheets=[css_doc],
                font_config=font_config
            )
            
            return pdf_bytes
            
        except Exception as e:
            # Fallback: probeer zonder custom CSS
            try:
                html_doc = HTML(string=html_content)
                pdf_bytes = html_doc.write_pdf()
                return pdf_bytes
            except Exception as fallback_error:
                raise RuntimeError(f"PDF generatie mislukt: {e}. Fallback ook mislukt: {fallback_error}")
    
    def get_quote_info(self, quote_id: str, tenant_id: str, year_month: str = None) -> Dict[str, Any]:
        """
        Haal offerte informatie op voor een specifieke tenant.
        
        Args:
            quote_id: ID van de offerte
            tenant_id: Tenant identifier
            year_month: Jaar-maand (optioneel, wordt automatisch bepaald als niet gegeven)
            
        Returns:
            Dict met offerte informatie
        """
        # Zoek in alle jaar-maand directories voor deze tenant
        if not year_month:
            # Voor S3: dit zou een list_objects call kunnen zijn, maar voor nu houden we het simpel
            # Voor LocalStorage: behouden we de oude logica
            if isinstance(self.storage, LocalStorage):
                # Fallback naar oude logica voor LocalStorage
                return self._get_quote_info_local(quote_id, tenant_id, year_month)
            else:
                # Voor S3: probeer de meest recente jaar-maand
                current_date = datetime.now()
                year_month = current_date.strftime("%Y-%m")
        
        html_key = f"offers/{year_month}/{quote_id}/{quote_id}.html"
        pdf_key = f"offers/{year_month}/{quote_id}/{quote_id}.pdf"
        
        # Controleer of bestanden bestaan
        html_exists = self.storage.exists(tenant_id, html_key)
        pdf_exists = self.storage.exists(tenant_id, pdf_key)
        
        if not html_exists and not pdf_exists:
            raise FileNotFoundError(f"Offerte {quote_id} niet gevonden in {year_month} voor tenant {tenant_id}")
        
        # Genereer URLs
        html_url = self.storage.public_url(tenant_id, html_key) if html_exists else None
        pdf_url = self.storage.public_url(tenant_id, pdf_key) if pdf_exists else None
        
        return {
            "quote_id": quote_id,
            "year_month": year_month,
            "tenant_id": tenant_id,
            "html_path": html_key if html_exists else None,
            "pdf_path": pdf_key if pdf_exists else None,
            "html_url": html_url,
            "pdf_url": pdf_url
        }
    
    def _get_quote_info_local(self, quote_id: str, tenant_id: str, year_month: str = None) -> Dict[str, Any]:
        """Fallback methode voor lokale bestandsopslag (behoudt oude logica)."""
        # Behoud de oude logica voor LocalStorage
        offers_dir = Path("data/offers")
        tenant_offers_dir = offers_dir / tenant_id
        
        if not year_month:
            # Zoek in alle jaar-maand directories voor deze tenant
            for ym_dir in tenant_offers_dir.iterdir():
                if ym_dir.is_dir() and ym_dir.name.count('-') == 1:
                    quote_dir = ym_dir / quote_id
                    if quote_dir.exists():
                        year_month = ym_dir.name
                        break
        
        if not year_month:
            raise FileNotFoundError(f"Offerte {quote_id} niet gevonden voor tenant {tenant_id}")
        
        quote_dir = tenant_offers_dir / year_month / quote_id
        
        if not quote_dir.exists():
            raise FileNotFoundError(f"Offerte {quote_id} niet gevonden in {year_month} voor tenant {tenant_id}")
        
        html_path = quote_dir / f"{quote_id}.html"
        pdf_path = quote_dir / f"{quote_id}.pdf"
        
        return {
            "quote_id": quote_id,
            "year_month": year_month,
            "tenant_id": tenant_id,
            "html_path": str(html_path) if html_path.exists() else None,
            "pdf_path": str(pdf_path) if pdf_path.exists() else None,
            "html_url": f"/files/{tenant_id}/{year_month}/{quote_id}/{quote_id}.html",
            "pdf_url": f"/files/{tenant_id}/{year_month}/{quote_id}/{quote_id}.pdf"
        }
    
    def get_tenant_quotes(self, tenant_id: str, year_month: str = None) -> Dict[str, Any]:
        """
        Haal alle offertes op voor een specifieke tenant.
        
        Args:
            tenant_id: Tenant identifier
            year_month: Jaar-maand (optioneel)
            
        Returns:
            Dict met offerte overzicht
        """
        # Voor nu: beperkte implementatie die alleen werkt met bekende jaar-maanden
        # In productie zou dit uitgebreid kunnen worden met storage-specifieke listing functionaliteit
        
        quotes = []
        total_count = 0
        
        if year_month:
            # Specifieke jaar-maand
            try:
                # Probeer een paar bekende quote IDs te vinden
                for i in range(1, 11):  # Zoek naar max 10 quotes
                    quote_id = f"QUOTE{i:03d}"
                    try:
                        quote_info = self.get_quote_info(quote_id, tenant_id, year_month)
                        quotes.append(quote_info)
                        total_count += 1
                    except FileNotFoundError:
                        continue
            except Exception:
                pass
        else:
            # Probeer huidige jaar-maand
            current_date = datetime.now()
            current_year_month = current_date.strftime("%Y-%m")
            try:
                quote_info = self.get_tenant_quotes(tenant_id, current_year_month)
                quotes.extend(quote_info.get("quotes", []))
                total_count += quote_info.get("total_count", 0)
            except Exception:
                pass
        
        return {
            "quotes": quotes,
            "total_count": total_count,
            "tenant_id": tenant_id
        }

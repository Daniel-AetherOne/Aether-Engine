import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple
import jinja2

class QuoteRendererSimple:
    """Vereenvoudigde service voor het renderen van offertes naar HTML."""
    
    def __init__(self, templates_dir: str = "app/templates", offers_dir: str = "data/offers"):
        """
        Initialiseer de QuoteRenderer.
        
        Args:
            templates_dir: Pad naar de templates directory
            offers_dir: Pad naar de offers directory
        """
        self.templates_dir = Path(templates_dir)
        self.offers_dir = Path(offers_dir)
        
        # Zorg dat de offers directory bestaat
        self.offers_dir.mkdir(parents=True, exist_ok=True)
        
        # Jinja2 template loader
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            autoescape=True
        )
    
    def render_quote(self, lead: Dict[str, Any], prediction: Dict[str, Any], 
                    pricing: Dict[str, Any]) -> Dict[str, str]:
        """
        Render een offerte naar HTML.
        
        Args:
            lead: Klantgegevens (naam, email, telefoon, adres, square_meters)
            prediction: Voorspelling resultaten (substrate, issues, confidences)
            pricing: Prijsberekening resultaten (subtotal, vat_amount, total, etc.)
            
        Returns:
            Dict met html_path en public_url
        """
        # Genereer unieke quote ID en datum
        quote_id = str(uuid.uuid4())[:8].upper()
        current_date = datetime.now()
        validity_date = current_date + timedelta(days=30)
        
        # Maak jaar-maand directory structuur
        year_month = current_date.strftime("%Y-%m")
        quote_dir = self.offers_dir / year_month / quote_id
        quote_dir.mkdir(parents=True, exist_ok=True)
        
        # Bereid template data voor
        template_data = self._prepare_template_data(
            lead, prediction, pricing, quote_id, current_date, validity_date
        )
        
        # Render HTML
        html_content = self._render_html_template(template_data)
        html_path = quote_dir / f"{quote_id}.html"
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Genereer public URLs
        html_url = f"/files/{year_month}/{quote_id}/{quote_id}.html"
        
        return {
            "html_path": str(html_path),
            "pdf_path": None,  # Geen PDF in deze versie
            "public_url": html_url,  # HTML URL als primaire public URL
            "html_url": html_url,
            "quote_id": quote_id,
            "year_month": year_month
        }
    
    def _prepare_template_data(self, lead: Dict[str, Any], prediction: Dict[str, Any],
                              pricing: Dict[str, Any], quote_id: str, 
                              current_date: datetime, validity_date: datetime) -> Dict[str, Any]:
        """Bereid template data voor."""
        
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
            "validity_date": validity_date.strftime("%d-%m-%Y")
        }
    
    def _render_html_template(self, template_data: Dict[str, Any]) -> str:
        """Render de HTML template met de gegeven data."""
        template = self.jinja_env.get_template("quote.html")
        return template.render(**template_data)
    
    def get_quote_info(self, quote_id: str, year_month: str = None) -> Dict[str, Any]:
        """
        Haal offerte informatie op.
        
        Args:
            quote_id: ID van de offerte
            year_month: Jaar-maand (optioneel, wordt automatisch bepaald als niet gegeven)
            
        Returns:
            Dict met offerte informatie
        """
        if not year_month:
            # Zoek in alle jaar-maand directories
            for ym_dir in self.offers_dir.iterdir():
                if ym_dir.is_dir() and ym_dir.name.count('-') == 1:
                    quote_dir = ym_dir / quote_id
                    if quote_dir.exists():
                        year_month = ym_dir.name
                        break
        
        if not year_month:
            raise FileNotFoundError(f"Offerte {quote_id} niet gevonden")
        
        quote_dir = self.offers_dir / year_month / quote_id
        
        if not quote_dir.exists():
            raise FileNotFoundError(f"Offerte {quote_id} niet gevonden in {year_month}")
        
        html_path = quote_dir / f"{quote_id}.html"
        
        return {
            "quote_id": quote_id,
            "year_month": year_month,
            "html_path": str(html_path) if html_path.exists() else None,
            "pdf_path": None,  # Geen PDF in deze versie
            "html_url": f"/files/{year_month}/{quote_id}/{quote_id}.html",
            "pdf_url": None
        }

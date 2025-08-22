import json
import os
from typing import List, Dict, Union
from pathlib import Path


class PricingEngine:
    """Prijsengine voor het berekenen van totaalprijzen op basis van m², substrate en issues."""
    
    def __init__(self, rules_file: str = "rules/pricing_rules.json"):
        """Initialiseer de pricing engine met regels uit JSON bestand."""
        self.rules_file = rules_file
        self.rules = self._load_rules()
    
    def _load_rules(self) -> Dict:
        """Laad prijsregels uit JSON bestand."""
        try:
            # Probeer relatief pad eerst
            rules_path = Path(self.rules_file)
            if not rules_path.exists():
                # Probeer absoluut pad vanuit workspace root
                workspace_root = Path(__file__).parent.parent.parent
                rules_path = workspace_root / self.rules_file
            
            with open(rules_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Kon prijsregels niet laden: {e}")
    
    def compute_price(self, m2: float, substrate: str, issues: List[str] = None) -> Dict:
        """
        Bereken totaalprijs op basis van m², substrate en issues.
        
        Args:
            m2: Oppervlakte in vierkante meters
            substrate: Type substrate (gipsplaat, beton, bestaand)
            issues: Lijst van issues (vocht, scheuren)
            
        Returns:
            Dict met subtotal, discount, vat_amount, total, aannames en doorlooptijd
        """
        if issues is None:
            issues = []
        
        # Valideer input
        if m2 <= 0:
            raise ValueError("m2 moet groter zijn dan 0")
        
        if substrate not in self.rules["base_per_m2"]:
            raise ValueError(f"Ongeldig substrate: {substrate}. Geldige opties: {list(self.rules['base_per_m2'].keys())}")
        
        # Bereken basisprijs
        base_price_per_m2 = self.rules["base_per_m2"][substrate]
        subtotal = m2 * base_price_per_m2
        
        # Pas surcharges toe voor issues
        total_surcharge = 0.0
        for issue in issues:
            if issue in self.rules["surcharge"]:
                total_surcharge += self.rules["surcharge"][issue]
        
        if total_surcharge > 0:
            subtotal *= (1 + total_surcharge)
        
        # Pas minimum totaal toe
        if subtotal < self.rules["min_total"]:
            subtotal = self.rules["min_total"]
        
        # Bereken BTW
        vat_amount = subtotal * (self.rules["vat_percent"] / 100)
        
        # Totaalprijs
        total = subtotal + vat_amount
        
        # Bepaal aannames en doorlooptijd op basis van eenvoudige regels
        aannames = self._determine_aannames(m2, substrate, issues)
        doorlooptijd = self._determine_doorlooptijd(m2, substrate, issues)
        
        return {
            "subtotal": round(subtotal, 2),
            "discount": 0.0,  # Geen korting volgens specificaties
            "vat_amount": round(vat_amount, 2),
            "total": round(total, 2),
            "aannames": aannames,
            "doorlooptijd": doorlooptijd
        }
    
    def _determine_aannames(self, m2: float, substrate: str, issues: List[str]) -> List[str]:
        """Bepaal aannames op basis van input parameters."""
        aannames = []
        
        # Basis aannames per substrate
        if substrate == "gipsplaat":
            aannames.append("Gipsplaat is beschikbaar en in goede staat")
            aannames.append("Onderliggende constructie is stabiel")
        elif substrate == "beton":
            aannames.append("Beton is voldoende droog en stabiel")
            aannames.append("Geen structurele problemen aanwezig")
        elif substrate == "bestaand":
            aannames.append("Bestaand oppervlak is geschikt voor behandeling")
            aannames.append("Geen verborgen gebreken")
        
        # Issue-specifieke aannames
        if "vocht" in issues:
            aannames.append("Vochtprobleem is lokaal en niet structureel")
            aannames.append("Voldoende ventilatie mogelijk")
        
        if "scheuren" in issues:
            aannames.append("Scheuren zijn oppervlakkig")
            aannames.append("Geen structurele schade")
        
        # Algemene aannames
        aannames.append(f"Werkruimte is {m2}m² en toegankelijk")
        aannames.append("Materiaal en gereedschap beschikbaar")
        
        return aannames
    
    def _determine_doorlooptijd(self, m2: float, substrate: str, issues: List[str]) -> str:
        """Bepaal geschatte doorlooptijd op basis van eenvoudige regels."""
        # Basis doorlooptijd per m²
        base_days_per_10m2 = {
            "gipsplaat": 1,
            "beton": 1.5,
            "bestaand": 1.2
        }
        
        base_days = (m2 / 10) * base_days_per_10m2[substrate]
        
        # Extra tijd voor issues
        extra_days = 0
        if "vocht" in issues:
            extra_days += 1  # Extra dag voor droging
        if "scheuren" in issues:
            extra_days += 0.5  # Extra halve dag voor reparatie
        
        total_days = base_days + extra_days
        
        # Rond af naar halve dagen
        total_days = round(total_days * 2) / 2
        
        if total_days <= 1:
            return "1 werkdag"
        elif total_days <= 2:
            return f"{total_days} werkdagen"
        else:
            weeks = total_days / 5
            if weeks <= 1:
                return f"{total_days} werkdagen"
            else:
                return f"{weeks:.1f} werkweken"

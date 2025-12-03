import json
from typing import List, Dict, Optional
from pathlib import Path
import logging

from app.schemas.intake import IntakePayload
from app.schemas.quote import Quote, QuoteItem
from app.models import Lead


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
            
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Kon prijsregels niet laden: {e}")
    
    def compute_price(self, m2: float, substrate: str, issues: Optional[List[str]] = None) -> Dict:
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
            valid = list(self.rules["base_per_m2"].keys())
            raise ValueError(f"Ongeldig substrate: {substrate}. Geldige opties: {valid}")
        
        # Bereken basisprijs
        base_price_per_m2 = self.rules["base_per_m2"][substrate]
        subtotal = m2 * base_price_per_m2
        
        # Pas surcharges toe voor issues
        total_surcharge = 0.0
        for issue in issues:
            if issue in self.rules.get("surcharge", {}):
                total_surcharge += self.rules["surcharge"][issue]
        
        if total_surcharge > 0:
            subtotal *= (1 + total_surcharge)
        
        # Pas minimum totaal toe
        min_total = self.rules.get("min_total")
        if min_total is not None and subtotal < min_total:
            subtotal = min_total
        
        # Bereken BTW
        vat_percent = self.rules.get("vat_percent", 21)
        vat_amount = subtotal * (vat_percent / 100)
        
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
            "doorlooptijd": doorlooptijd,
            "vat_percent": vat_percent,
            "base_price_per_m2": base_price_per_m2,
        }
    
    def _determine_aannames(self, m2: float, substrate: str, issues: List[str]) -> List[str]:
        """Bepaal aannames op basis van input parameters."""
        aannames: List[str] = []
        
        # Basis aannames per substrate
        if substrate == "gipsplaat":
            aannames.append("Gipsplaat is beschikbaar en in goede staat.")
            aannames.append("Onderliggende constructie is stabiel.")
        elif substrate == "beton":
            aannames.append("Beton is voldoende droog en stabiel.")
            aannames.append("Geen structurele problemen aanwezig.")
        elif substrate == "bestaand":
            aannames.append("Bestaand oppervlak is geschikt voor behandeling.")
            aannames.append("Geen verborgen gebreken aanwezig.")
        
        # Issue-specifieke aannames
        if "vocht" in issues:
            aannames.append("Vochtprobleem is lokaal en niet structureel.")
            aannames.append("Voldoende ventilatie is mogelijk.")
        
        if "scheuren" in issues:
            aannames.append("Scheuren zijn oppervlakkig en niet structureel.")
        
        # Algemene aannames
        aannames.append(f"Werkruimte is circa {m2} m² en goed toegankelijk.")
        aannames.append("Materiaal, stroom en water zijn op locatie beschikbaar.")
        
        return aannames
    
    def _determine_doorlooptijd(self, m2: float, substrate: str, issues: List[str]) -> str:
        """Bepaal geschatte doorlooptijd op basis van eenvoudige regels."""
        # Basis doorlooptijd per m²
        base_days_per_10m2 = {
            "gipsplaat": 1.0,
            "beton": 1.5,
            "bestaand": 1.2,
        }
        
        base_days = (m2 / 10.0) * base_days_per_10m2[substrate]
        
        # Extra tijd voor issues
        extra_days = 0.0
        if "vocht" in issues:
            extra_days += 1.0  # Extra dag voor droging
        if "scheuren" in issues:
            extra_days += 0.5  # Extra halve dag voor reparatie
        
        total_days = base_days + extra_days
        
        # Rond af naar halve dagen
        total_days = round(total_days * 2) / 2
        
        if total_days <= 1:
            return "circa 1 werkdag"
        elif total_days <= 2:
            return f"circa {total_days} werkdagen"
        else:
            weeks = total_days / 5
            if weeks <= 1:
                return f"circa {total_days} werkdagen"
            else:
                return f"circa {weeks:.1f} werkweken"


# --------------------------------------------------------------------
# High-level API voor LevelAI / Aether Engine: calculate_quote(...)
# --------------------------------------------------------------------

def _infer_substrate_from_payload(payload: IntakePayload) -> str:
    """
    Probeer het juiste substrate af te leiden uit de intake.
    Valt terug op 'bestaand' als er niets expliciet is ingevuld.
    """
    # Als het model al een veld heeft voor substrate, gebruik die.
    if hasattr(payload, "substrate") and payload.substrate:
        return str(payload.substrate)

    if hasattr(payload, "surface_type") and payload.surface_type:
        return str(payload.surface_type)

    # TODO: later: AI/LLM laten bepalen op basis van project_description / foto's
    return "bestaand"


def _infer_issues_from_payload(payload: IntakePayload) -> List[str]:
    """
    Probeer issues (vocht, scheuren, etc.) uit de intake te halen.
    Nu vooral rule-based; later kan hier AI/detectie bij komen.
    """
    issues: List[str] = []

    # Als er direct een issues-lijst in de payload zit
    if hasattr(payload, "issues") and payload.issues:
        return list(payload.issues)

    if hasattr(payload, "detected_issues") and payload.detected_issues:
        return list(payload.detected_issues)

    # Eenvoudige tekst-heuristiek op project_description
    desc = getattr(payload, "project_description", "") or ""
    desc_lower = desc.lower()

    if "vocht" in desc_lower or "schimmel" in desc_lower:
        issues.append("vocht")
    if "scheur" in desc_lower or "barst" in desc_lower:
        issues.append("scheuren")

    # later: AI call op basis van beschrijving + foto-analyse
    return issues


def calculate_quote(payload: IntakePayload, lead: Optional[Lead] = None) -> Quote:
    """
    Hoog-niveau functie zoals in de roadmap (6.2).
    
    - gebruikt intake payload (en optioneel lead) als input
    - bepaalt m2, substrate & issues
    - roept PricingEngine aan
    - zet resultaat om in een Quote Pydantic object
    """
    engine = PricingEngine()

    m2_raw = getattr(payload, "square_meters", None)

    try:
        m2 = float(m2_raw) if m2_raw is not None else 0.0
    except (TypeError, ValueError):
        m2 = 0.0

    # Als m2 nog steeds 0 of ongeldig is, kies een veilige fallback
    if m2 <= 0:
        logger = logging.getLogger(__name__)
        logger.warning(
            "calculate_quote: square_meters ontbreekt of is ongeldig (%r), fallback naar 50 m²",
            m2_raw,
        )
        m2 = 50.0


    substrate = _infer_substrate_from_payload(payload)
    issues = _infer_issues_from_payload(payload)

    pricing_result = engine.compute_price(m2=m2, substrate=substrate, issues=issues)

    subtotal = pricing_result["subtotal"]
    vat_amount = pricing_result["vat_amount"]
    total = pricing_result["total"]
    base_price_per_m2 = pricing_result["base_price_per_m2"]
    aannames = pricing_result["aannames"]
    doorlooptijd = pricing_result["doorlooptijd"]

    # Effectieve prijs per m2 (na surcharges, min_total, etc.)
    effective_unit_price = round(subtotal / m2, 2) if m2 > 0 else base_price_per_m2

    # 1 regel in de offerte (je kunt dit later uitbreiden naar meerdere items)
    item = QuoteItem(
        description=f"Stucwerk ({substrate}) op basis van intake",
        quantity_m2=m2,
        unit_price=effective_unit_price,
        total_price=subtotal,
    )

    notes_parts = []

    # Tekstuele beschrijving vanuit intake
    desc = getattr(payload, "project_description", "") or ""
    if desc:
        notes_parts.append(f"Projectbeschrijving klant:\n{desc}")

    # Doorlooptijd + aannames
    notes_parts.append(f"Geschatte doorlooptijd: {doorlooptijd}.")
    if aannames:
        notes_parts.append("Belangrijkste aannames:")
        for a in aannames:
            notes_parts.append(f"- {a}")

    # Issues vermelden
    if issues:
        issues_str = ", ".join(issues)
        notes_parts.append(f"Bijzonderheden gedetecteerd: {issues_str}.")

    notes_parts.append("Let op: dit is een indicatieve prijs op basis van de online intake.")

    notes = "\n".join(notes_parts)

    return Quote(
        lead_id=lead.id if lead is not None else 0,
        subtotal=subtotal,
        vat=vat_amount,
        total=total,
        currency="EUR",
        items=[item],
        notes=notes,
    )

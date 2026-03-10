import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.models import Lead
from app.schemas.intake import IntakePayload
from app.schemas.quote import Quote, QuoteItem


class PricingEngine:
    """Prijsengine voor het berekenen van totaalprijzen op basis van m², substrate, work_type en issues."""

    def __init__(self, rules_file: str = "rules/pricing_rules.json"):
        """Initialiseer de pricing engine met regels uit JSON bestand."""
        self.rules_file = rules_file
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict:
        """Laad prijsregels uit JSON bestand."""
        try:
            rules_path = Path(self.rules_file)
            if not rules_path.exists():
                workspace_root = Path(__file__).parent.parent.parent
                rules_path = workspace_root / self.rules_file

            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Kon prijsregels niet laden: {e}")

    def compute_price(
        self,
        m2: float,
        substrate: str,
        work_type: str = "Binnenwerk",
        issues: Optional[List[str]] = None,
    ) -> Dict:
        """
        Bereken totaalprijs op basis van m², substrate, work_type en issues.

        Args:
            m2: Oppervlakte in vierkante meters
            substrate: Type ondergrond (gipsplaat, beton, bestaand)
            work_type: Binnenwerk, Buitenwerk of Beide
            issues: Lijst van issues (vocht, scheuren)

        Returns:
            Dict met subtotal, discount, vat_amount, total, aannames en doorlooptijd
        """
        if issues is None:
            issues = []

        if m2 <= 0:
            raise ValueError("m2 moet groter zijn dan 0")

        if substrate not in self.rules["base_per_m2"]:
            valid = list(self.rules["base_per_m2"].keys())
            raise ValueError(
                f"Ongeldig substrate: {substrate}. Geldige opties: {valid}"
            )

        base_price_per_m2 = self.rules["base_per_m2"][substrate]
        subtotal = m2 * base_price_per_m2

        work_type_factors = self.rules.get("work_type_factors", {})
        subtotal *= work_type_factors.get(work_type, 1.0)

        total_surcharge = 0.0
        for issue in issues:
            if issue in self.rules.get("surcharge", {}):
                total_surcharge += self.rules["surcharge"][issue]

        if total_surcharge > 0:
            subtotal *= 1 + total_surcharge

        min_total = self.rules.get("min_total")
        if min_total is not None and subtotal < min_total:
            subtotal = min_total

        vat_percent = self.rules.get("vat_percent", 21)
        vat_amount = subtotal * (vat_percent / 100)
        total = subtotal + vat_amount

        aannames = self._determine_aannames(m2, substrate, work_type, issues)
        doorlooptijd = self._determine_doorlooptijd(m2, substrate, work_type, issues)

        return {
            "subtotal": round(subtotal, 2),
            "discount": 0.0,
            "vat_amount": round(vat_amount, 2),
            "total": round(total, 2),
            "aannames": aannames,
            "doorlooptijd": doorlooptijd,
            "vat_percent": vat_percent,
            "base_price_per_m2": base_price_per_m2,
            "work_type": work_type,
        }

    def _determine_aannames(
        self, m2: float, substrate: str, work_type: str, issues: List[str]
    ) -> List[str]:
        """Bepaal aannames op basis van input parameters."""
        aannames: List[str] = []

        if substrate == "gipsplaat":
            aannames.append("Gipsplaat is beschikbaar en in goede staat.")
            aannames.append("Onderliggende constructie is stabiel.")
        elif substrate == "beton":
            aannames.append("Beton is voldoende droog en stabiel.")
            aannames.append("Geen structurele problemen aanwezig.")
        elif substrate == "bestaand":
            aannames.append("Bestaand oppervlak is geschikt voor behandeling.")
            aannames.append("Geen verborgen gebreken aanwezig.")

        if work_type == "Buitenwerk":
            aannames.append(
                "Buitenwerk is normaal bereikbaar en weersomstandigheden zijn werkbaar."
            )
        elif work_type == "Beide":
            aannames.append(
                "Prijs is gebaseerd op een combinatie van binnen- en buitenwerk."
            )

        if "vocht" in issues:
            aannames.append("Vochtprobleem is lokaal en niet structureel.")
            aannames.append("Voldoende ventilatie is mogelijk.")

        if "scheuren" in issues:
            aannames.append("Scheuren zijn oppervlakkig en niet structureel.")

        aannames.append(f"Werkruimte is circa {m2} m² en goed toegankelijk.")
        aannames.append("Materiaal, stroom en water zijn op locatie beschikbaar.")

        return aannames

    def _determine_doorlooptijd(
        self, m2: float, substrate: str, work_type: str, issues: List[str]
    ) -> str:
        """Bepaal geschatte doorlooptijd op basis van eenvoudige regels."""
        base_days_per_10m2 = {
            "gipsplaat": 1.0,
            "beton": 1.5,
            "bestaand": 1.2,
        }

        base_days = (m2 / 10.0) * base_days_per_10m2[substrate]

        if work_type == "Buitenwerk":
            base_days *= 1.2
        elif work_type == "Beide":
            base_days *= 1.1

        extra_days = 0.0
        if "vocht" in issues:
            extra_days += 1.0
        if "scheuren" in issues:
            extra_days += 0.5

        total_days = base_days + extra_days
        total_days = round(total_days * 2) / 2

        if total_days <= 1:
            return "circa 1 werkdag"
        if total_days <= 2:
            return f"circa {total_days} werkdagen"

        weeks = total_days / 5
        if weeks <= 1:
            return f"circa {total_days} werkdagen"
        return f"circa {weeks:.1f} werkweken"


# ----------------------------------------------------------
# High-level API voor / Aether Engine: calculate_quote(...)
# ----------------------------------------------------------


def _infer_substrate_from_payload(payload: IntakePayload) -> str:
    """
    Probeer het juiste substrate af te leiden uit de intake.
    Valt terug op 'bestaand' als er niets expliciet is ingevuld.
    """
    if hasattr(payload, "substrate") and payload.substrate:
        return str(payload.substrate)

    if hasattr(payload, "surface_type") and payload.surface_type:
        return str(payload.surface_type)

    return "bestaand"


def _infer_work_type_from_payload(payload: IntakePayload) -> str:
    if hasattr(payload, "job_type") and payload.job_type:
        return str(payload.job_type)

    if hasattr(payload, "work_type") and payload.work_type:
        return str(payload.work_type)

    if hasattr(payload, "soort_werk") and payload.soort_werk:
        return str(payload.soort_werk)

    return "Binnenwerk"


def _infer_issues_from_payload(payload: IntakePayload) -> List[str]:
    """
    Probeer issues (vocht, scheuren, etc.) uit de intake te halen.
    Nu vooral rule-based; later kan hier AI/detectie bij komen.
    """
    issues: List[str] = []

    if hasattr(payload, "issues") and payload.issues:
        return list(payload.issues)

    if hasattr(payload, "detected_issues") and payload.detected_issues:
        return list(payload.detected_issues)

    desc = getattr(payload, "project_description", "") or ""
    desc_lower = desc.lower()

    if "vocht" in desc_lower or "schimmel" in desc_lower:
        issues.append("vocht")
    if "scheur" in desc_lower or "barst" in desc_lower:
        issues.append("scheuren")

    return issues


def calculate_quote(payload: IntakePayload, lead: Optional[Lead] = None) -> Quote:
    """
    Hoog-niveau functie voor offerteberekening op basis van intake payload.
    """
    logger = logging.getLogger(__name__)
    engine = PricingEngine()

    m2_raw = getattr(payload, "square_meters", None)

    try:
        m2 = float(m2_raw) if m2_raw is not None else 0.0
    except (TypeError, ValueError):
        m2 = 0.0

    if m2 <= 0:
        logger.warning(
            "calculate_quote: square_meters ontbreekt of is ongeldig (%r), fallback naar 50 m²",
            m2_raw,
        )
        m2 = 50.0

    substrate = _infer_substrate_from_payload(payload)
    work_type = _infer_work_type_from_payload(payload)
    issues = _infer_issues_from_payload(payload)

    pricing_result = engine.compute_price(
        m2=m2,
        substrate=substrate,
        work_type=work_type,
        issues=issues,
    )

    subtotal = pricing_result["subtotal"]
    vat_amount = pricing_result["vat_amount"]
    total = pricing_result["total"]
    base_price_per_m2 = pricing_result["base_price_per_m2"]
    aannames = pricing_result["aannames"]
    doorlooptijd = pricing_result["doorlooptijd"]

    effective_unit_price = round(subtotal / m2, 2) if m2 > 0 else base_price_per_m2

    item = QuoteItem(
        description=f"Schilderwerk ({work_type}, {substrate}) op basis van intake",
        quantity_m2=m2,
        unit_price=effective_unit_price,
        total_price=subtotal,
    )

    notes_parts = []

    desc = getattr(payload, "project_description", "") or ""
    if desc:
        notes_parts.append(f"Projectbeschrijving klant:\n{desc}")

    notes_parts.append(f"Soort werk: {work_type}.")
    notes_parts.append(f"Geschatte doorlooptijd: {doorlooptijd}.")

    if aannames:
        notes_parts.append("Belangrijkste aannames:")
        for a in aannames:
            notes_parts.append(f"- {a}")

    if issues:
        issues_str = ", ".join(issues)
        notes_parts.append(f"Bijzonderheden gedetecteerd: {issues_str}.")

    notes_parts.append(
        "Let op: dit is een indicatieve prijs op basis van de online intake."
    )

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

from __future__ import annotations

from decimal import Decimal
from .base import D, Rule, RuleResult, register


@register
class ApprovalDiscountRule(Rule):
    type_name = "approval_discount"

    def apply(self, ctx, line_state) -> RuleResult:
        """
        6.3 Approval Rule (engine-level):
        - Engine beslist of approval nodig is (niet UI)
        - Override (requested discount) is altijd zichtbaar in breakdown
        - Warnings bevatten expliciete, uitlegbare tekst
        - Vermijd duplicate warnings/breakdown als rules per line worden toegepast
        """

        requested = ctx.input.discount_percent
        if requested is None:
            return RuleResult.skipped(
                {"reason": "no_requested_discount", "approval_required": False}
            )

        # --- Guard tegen duplicates (als rule per line wordt aangeroepen) ---
        # We proberen een "once per quote" latch te zetten.
        # Dit werkt als ctx een dict-achtig attribuut heeft (memo/state/cache).
        # Als jouw ctx dit niet heeft, laat dit blok weg en verplaats de rule naar quote-level evaluatie.
        latch = None
        for attr in ("memo", "state", "cache", "meta"):
            latch = getattr(ctx, attr, None)
            if isinstance(latch, dict):
                break
            latch = None

        if latch is not None:
            if latch.get("_approval_discount_checked"):
                return RuleResult.skipped(
                    {"reason": "already_checked", "approval_required": False}
                )
            latch["_approval_discount_checked"] = True

        segment = (ctx.input.customer_segment or "A").strip().upper()
        max_extra_map = (ctx.data.tables or {}).get(
            "customer_max_extra_discount_pct"
        ) or {
            "A": "0",
            "B": "2",
            "C": "4",
        }
        max_pct = D(str(max_extra_map.get(segment, "0")))
        req = D(str(requested))

        # --- Breakdown: altijd zichtbaar ---
        # MVP: we tonen altijd dat er een override/extra korting gevraagd is.
        # (Ook als het binnen profiel valt.)
        if req > max_pct:
            breakdown = (
                f"Override korting: -{req}% (profiel {max_pct}%) — approval vereist"
            )
        else:
            breakdown = (
                f"Override korting: -{req}% (profiel {max_pct}%) — binnen profiel"
            )

        # Als je breakdown op quote-level wil, maar alleen line_state hebt:
        # voeg 'm één keer toe op de eerste line (en latch hierboven voorkomt duplicates).
        line_state.add_breakdown(breakdown)

        # --- Beslissing + warning ---
        if req > max_pct:
            # Expliciete warning tekst, exact wat UI moet tonen.
            msg = f"Extra korting {req}% > profiel {max_pct}% — approval vereist"
            ctx.warn(
                "APPROVAL_REQUIRED",
                msg,
                segment=segment,
                requested=str(req),
                allowed=str(max_pct),
            )
            # RuleResult: geen prijsdelta hier; alleen policy decision (approvalRequired)
            return RuleResult.applied(D("0.00"), {"approval_required": True})

        # Binnen profiel: géén warning, maar wel breakdown (visibility)
        return RuleResult.applied(D("0.00"), {"approval_required": False})

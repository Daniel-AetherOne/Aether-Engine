from __future__ import annotations

from typing import Any
from openpyxl import Workbook

from app.verticals.ace.explain.formatter import (
    format_steps_newlines,
)


def export_quote_to_excel(quote_output: dict, path: str) -> None:
    """
    MVP Excel export.
    Uses explain.formatter — no custom string logic allowed.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Quotes"

    # Header
    ws.append(
        [
            "Line ID",
            "SKU",
            "Qty",
            "Net sell",
            "Margin %",
            "Price breakdown",
        ]
    )

    for line in quote_output.get("lines", []):
        steps = line.get("steps", [])
        breakdown_cell = format_steps_newlines(steps)

        ws.append(
            [
                line.get("line_id"),
                line.get("sku"),
                line.get("qty"),
                line.get("net_sell", {}).get("amount"),
                line.get("margin_pct"),
                breakdown_cell,
            ]
        )

    wb.save(path)

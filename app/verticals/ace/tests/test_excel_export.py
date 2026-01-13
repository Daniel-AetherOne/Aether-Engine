from app.verticals.ace.export.excel_export import export_quote_to_excel
from pathlib import Path


def test_excel_export_uses_formatter(tmp_path):
    out = {
        "lines": [
            {
                "line_id": "l1",
                "sku": "SKU1",
                "qty": "3",
                "net_sell": {"amount": "100.00", "currency": "EUR"},
                "margin_pct": "20",
                "steps": [
                    "Netto inkoop: €80",
                    "Transport: €10",
                    "Minimummarge: OK",
                ],
            }
        ]
    }

    path = tmp_path / "quote.xlsx"
    export_quote_to_excel(out, str(path))

    assert path.exists()

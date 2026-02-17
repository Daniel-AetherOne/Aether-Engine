from __future__ import annotations

from datetime import datetime, timezone

from app.services.storage import get_storage, put_text


def make_estimate_html_key(*, lead_id: int) -> str:
    # tenant-prefix NIET hier plakken; storage._tenant_key doet dat veilig.
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"dev/estimates/lead_{lead_id}_{ts}.html"


def save_estimate_html(*, tenant_id: str, lead_id: int, html: str) -> str:
    storage = get_storage()
    key = make_estimate_html_key(lead_id=lead_id)

    put_text(
        storage,
        tenant_id=str(tenant_id),
        key=key,
        text=html,
        content_type="text/html; charset=utf-8",
    )

    # return tenant-less key (DB bewaart key zonder tenant prefix)
    return key

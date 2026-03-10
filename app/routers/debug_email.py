# app/routers/debug_email.py
from fastapi import APIRouter, Query
from app.services.email_service import send_email

router = APIRouter(prefix="/debug", tags=["debug-email"])


@router.post("/send-test-email")
async def send_test_email(to: str = Query(...)):
    result = await send_email(
        to=to,
        subject="Paintly test email",
        html_body="""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h1>Paintly email test</h1>
            <p>Als je dit ziet, werkt Postmark.</p>
          </body>
        </html>
        """,
        text_body="Paintly email test. Als je dit ziet, werkt Postmark.",
        tag="debug-test",
        metadata={"flow": "debug_test"},
    )
    return result